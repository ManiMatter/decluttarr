import asyncio
import os
import time

import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from src.web.config_manager import ConfigManager
from src.web.database import ActivityRecorder, Database
from src.web.events import EventBus, EventType
from src.web.routes import api_router, page_router


# Content-Security-Policy for the UI. script-src is strict 'self': all JS is
# vendored locally (htmx, the CSP build of Alpine) with no inline scripts and no
# eval, so no 'unsafe-inline'/'unsafe-eval' is needed. style-src allows
# 'unsafe-inline' for the inline style= attributes and Pico/Alpine style hooks;
# everything else (fetch, EventSource, images) is same-origin.
_CSP_POLICY = "; ".join(
    [
        "default-src 'self'",
        "script-src 'self'",
        "style-src 'self' 'unsafe-inline'",
        "img-src 'self' data:",
        "font-src 'self'",
        "connect-src 'self'",
        "base-uri 'self'",
        "form-action 'self'",
        "frame-ancestors 'self'",
    ]
)


def create_app(settings, event_bus: EventBus, trigger_event: asyncio.Event = None) -> FastAPI:
    app = FastAPI(title="Decluttarr", docs_url="/api/docs", redoc_url=None)

    @app.middleware("http")
    async def _security_headers(request, call_next):
        response = await call_next(request)
        # Swagger UI (/api/docs) loads its assets from a CDN and uses inline
        # scripts/styles, so a strict CSP would break it — skip that one page.
        if "/api/docs" not in request.url.path:
            response.headers.setdefault("Content-Security-Policy", _CSP_POLICY)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        return response

    # Static files and templates
    web_dir = os.path.dirname(__file__)
    app.mount("/static", StaticFiles(directory=os.path.join(web_dir, "static")), name="static")

    templates = Jinja2Templates(directory=os.path.join(web_dir, "templates"))

    # Store shared state
    app.state.settings = settings
    app.state.event_bus = event_bus
    app.state.templates = templates
    app.state.start_time = time.time()
    app.state.trigger_event = trigger_event
    app.state.first_cycle_done = False

    # Register routes
    app.include_router(api_router)
    app.include_router(page_router)

    return app


async def start_web_server(settings, event_bus: EventBus, trigger_event: asyncio.Event = None):
    """Start the web server as an async task."""
    from src.utils.log_setup import logger

    # Initialize database. Precedence: web.db_path (yaml) > DECLUTTARR_DB_PATH env > default.
    database = Database(getattr(settings.web, "db_path", None))
    await database.init()

    host = settings.web.host
    port = settings.web.port
    proxy_prefix = getattr(settings.web, "proxy_prefix", None)
    # proxy_prefix is the literal path prefix the reverse proxy strips before
    # forwarding to us — e.g. "decluttarr" or "proxy/9999" for code-server.
    root_path = f"/{proxy_prefix.strip('/')}" if proxy_prefix else ""

    # Create app
    app = create_app(settings, event_bus, trigger_event)
    app.state.database = database

    # Config manager
    config_manager = ConfigManager(database, settings)
    await config_manager.apply_all_overrides()
    app.state.config_manager = config_manager

    # Start activity recorder
    recorder = ActivityRecorder(database, event_bus)
    await recorder.start()
    app.state.recorder = recorder

    # Track when the first main-loop cycle finishes so partials can show
    # a "waiting" message instead of hanging on arr API calls during startup.
    async def _mark_first_cycle_done():
        queue = event_bus.subscribe()
        try:
            while True:
                event = await queue.get()
                if event.event_type == EventType.CYCLE_END:
                    app.state.first_cycle_done = True
                    break
        finally:
            event_bus.unsubscribe(queue)

    # Schedule daily cleanup of old activity log entries
    async def _periodic_cleanup():
        while True:
            await asyncio.sleep(86400)  # 24 hours
            try:
                deleted = await database.cleanup_old_activity(days=90)
                if deleted:
                    logger.info(f"Activity log cleanup: removed {deleted} entries older than 90 days")
            except Exception as e:  # noqa: BLE001
                logger.debug(f"Activity log cleanup error: {e}")

    # asyncio holds only weak refs to tasks, so we keep our own strong refs
    # on app.state to prevent them from being garbage-collected mid-flight.
    app.state.background_tasks = [
        asyncio.create_task(_mark_first_cycle_done()),
        asyncio.create_task(_periodic_cleanup()),
    ]

    # Run initial cleanup on startup
    try:
        deleted = await database.cleanup_old_activity(days=90)
        if deleted:
            logger.info(f"Activity log cleanup: removed {deleted} entries older than 90 days")
    except Exception as e:  # noqa: BLE001
        logger.debug(f"Activity log cleanup error: {e}")

    logger.info(f"Web UI starting on http://{host}:{port}")
    if proxy_prefix:
       logger.debug(f"Web UI root path:{root_path}") 

    # Map the app's log level to one uvicorn understands. VERBOSE is custom,
    # so fall back to info; anything unrecognized also defaults to info.
    _uvicorn_levels = {
        "DEBUG": "debug",
        "VERBOSE": "info",
        "INFO": "info",
        "WARNING": "warning",
        "ERROR": "error",
        "CRITICAL": "critical",
    }
    uvicorn_log_level = _uvicorn_levels.get(
        settings.general.log_level.upper(), "info",
    )

    config = uvicorn.Config(
        app,
        host=host,
        port=port,
        log_level=uvicorn_log_level,
        access_log=False,
        root_path=root_path,
    )
    server = uvicorn.Server(config)
    await server.serve()