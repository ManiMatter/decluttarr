import asyncio
import json
import time

from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse

from src.utils.log_setup import logger
from src.web.events import Event, EventType

api_router = APIRouter(prefix="/api")
page_router = APIRouter()


def _cached_json(data: dict, max_age: int = 5) -> JSONResponse:
    """Return a JSONResponse with Cache-Control headers."""
    return JSONResponse(
        content=data,
        headers={"Cache-Control": f"private, max-age={max_age}"},
    )

# Derive allowed config keys from settings classes so they stay in sync automatically.
# Keys that should NOT be overridable at runtime:
_GENERAL_SKIP = {"ignored_download_clients"}


def _get_allowed_general_keys() -> set:
    from src.settings._general import General
    return {
        k for k in General.__annotations__
        if k not in _GENERAL_SKIP
    }


def _get_allowed_job_attrs() -> set:
    import inspect
    from src.settings._jobs import JobParams
    sig = inspect.signature(JobParams.__init__)
    return {p for p in sig.parameters if p != "self"}


# ─── API: Status ───────────────────────────────────────────────

@api_router.get("/status")
async def api_status(request: Request):
    settings = request.app.state.settings
    app_state = request.app.state

    instances = []
    for arr in settings.instances:
        instances.append({
            "name": arr.name,
            "arr_type": arr.arr_type,
            "base_url": arr.base_url,
        })

    return _cached_json({
        "uptime": time.time() - app_state.start_time,
        "test_run": settings.general.test_run,
        "timer_minutes": settings.general.timer,
        "instance_count": len(settings.instances),
        "instances": instances,
        "version": getattr(settings.envs, "image_tag", "Local"),
        "web_enabled": True,
    }, max_age=10)


# ─── API: Queue ────────────────────────────────────────────────

async def _fetch_queue(request: Request) -> list:
    """Fetch queue data from all instances. Returns list of queue items."""
    settings = request.app.state.settings
    db = request.app.state.database

    cursor = await db.db.execute("SELECT download_id FROM protected_downloads")
    ui_protected = {row[0] for row in await cursor.fetchall()}

    all_queues = []
    for arr in settings.instances:
        try:
            from src.utils.queue_manager import QueueManager
            qm = QueueManager(arr, settings)
            queue_items = await qm.get_queue_items("full")
            strikes_data = arr.tracker.defective

            for item in (queue_items or []):
                download_id = item.get("downloadId", "")
                item_strikes = {}
                for job_name, job_strikes in strikes_data.items():
                    if download_id in job_strikes:
                        entry = job_strikes[download_id]
                        item_strikes[job_name] = {
                            "strikes": entry.get("strikes", 0),
                            "max_strikes": None,
                        }

                is_protected = (
                    download_id in arr.tracker.protected
                    or download_id in ui_protected
                )

                all_queues.append({
                    "arr_name": arr.name,
                    "arr_type": arr.arr_type,
                    "title": item.get("title", "Unknown"),
                    "status": item.get("status", ""),
                    "download_id": download_id,
                    "queue_id": item.get("id"),
                    "size": item.get("size", 0),
                    "sizeleft": item.get("sizeleft", 0),
                    "protocol": item.get("protocol", ""),
                    "download_client": item.get("downloadClient", ""),
                    "strikes": item_strikes,
                    "protected": is_protected,
                    "status_messages": [
                        msg.get("title", "") for msg in item.get("statusMessages", [])
                    ],
                })
        except Exception as e:
            logger.warning(f"Failed to fetch queue for {arr.name}: {e}")

    return all_queues


@api_router.get("/queue")
async def api_queue(request: Request):
    all_queues = await _fetch_queue(request)
    return _cached_json({"items": all_queues, "total": len(all_queues)}, max_age=5)


@api_router.get("/queue/{arr_name}")
async def api_queue_by_arr(arr_name: str, request: Request):
    all_queues = await _fetch_queue(request)
    filtered = [item for item in all_queues if item["arr_name"] == arr_name]
    return _cached_json({"items": filtered, "total": len(filtered)}, max_age=5)


# ─── API: Activity ─────────────────────────────────────────────

def _row_to_activity(row):
    return {
        "id": row[0],
        "timestamp": row[1],
        "arr_name": row[2],
        "arr_type": row[3],
        "job_name": row[4],
        "action": row[5],
        "download_id": row[6],
        "title": row[7],
        "strikes": row[8],
        "max_strikes": row[9],
        "details": json.loads(row[10]) if row[10] else None,
        "test_run": bool(row[11]),
    }


@api_router.get("/activity")
async def api_activity(
    request: Request,
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    job: str = Query(None),
    arr: str = Query(None),
    action: str = Query(None),
    search: str = Query(None),
    date_from: str = Query(None),
    date_to: str = Query(None),
):
    db = request.app.state.database
    conditions = []
    params = []

    if job:
        conditions.append("job_name = ?")
        params.append(job)
    if arr:
        conditions.append("arr_name = ?")
        params.append(arr)
    if action:
        conditions.append("action = ?")
        params.append(action)
    if search:
        conditions.append("title LIKE ?")
        params.append(f"%{search}%")
    if date_from:
        conditions.append("timestamp >= ?")
        params.append(date_from)
    if date_to:
        # Append time to include the entire end date
        conditions.append("timestamp <= ?")
        params.append(date_to + " 23:59:59")

    where = " AND ".join(conditions) if conditions else "1=1"

    # Count total
    cursor = await db.db.execute(
        f"SELECT COUNT(*) FROM activity_log WHERE {where}", params
    )
    total = (await cursor.fetchone())[0]

    # Fetch page
    offset = (page - 1) * per_page
    cursor = await db.db.execute(
        f"SELECT * FROM activity_log WHERE {where} ORDER BY timestamp DESC LIMIT ? OFFSET ?",
        params + [per_page, offset],
    )
    rows = await cursor.fetchall()
    items = [_row_to_activity(row) for row in rows]

    return {
        "items": items,
        "total": total,
        "page": page,
        "per_page": per_page,
        "total_pages": max(1, (total + per_page - 1) // per_page),
    }


# ─── API: Strikes ──────────────────────────────────────────────

@api_router.get("/strikes")
async def api_strikes(request: Request):
    settings = request.app.state.settings
    all_strikes = {}
    for arr in settings.instances:
        arr_strikes = {}
        for job_name, job_data in arr.tracker.defective.items():
            for download_id, entry in job_data.items():
                arr_strikes.setdefault(download_id, {
                    "title": entry.get("title", "Unknown"),
                    "jobs": {},
                })
                arr_strikes[download_id]["jobs"][job_name] = {
                    "strikes": entry.get("strikes", 0),
                    "tracking_paused": entry.get("tracking_paused", False),
                }
        if arr_strikes:
            all_strikes[arr.name] = arr_strikes
    return all_strikes


# ─── API: Protected Downloads ──────────────────────────────────

@api_router.post("/protected/{download_id}")
async def api_protect(download_id: str, request: Request):
    db = request.app.state.database
    event_bus = request.app.state.event_bus
    content_type = request.headers.get("content-type", "")
    body = await request.json() if content_type.startswith("application/json") else {}
    title = body.get("title", "Unknown")
    arr_name = body.get("arr_name", "")
    reason = body.get("reason", "")

    await db.db.execute(
        """INSERT INTO protected_downloads (download_id, title, arr_name, reason)
           VALUES (?, ?, ?, ?)
           ON CONFLICT(download_id) DO UPDATE SET reason=?, protected_at=datetime('now')""",
        (download_id, title, arr_name, reason, reason),
    )
    await db.db.commit()

    await event_bus.emit(Event(EventType.ITEM_PROTECTED, {
        "download_id": download_id,
        "title": title,
        "arr_name": arr_name,
        "reason": reason,
    }))

    return {"status": "protected", "download_id": download_id}


@api_router.delete("/protected/{download_id}")
async def api_unprotect(download_id: str, request: Request):
    db = request.app.state.database
    event_bus = request.app.state.event_bus

    cursor = await db.db.execute(
        "SELECT title, arr_name FROM protected_downloads WHERE download_id=?",
        (download_id,),
    )
    row = await cursor.fetchone()

    await db.db.execute("DELETE FROM protected_downloads WHERE download_id=?", (download_id,))
    await db.db.commit()

    if row is not None:
        await event_bus.emit(Event(EventType.ITEM_UNPROTECTED, {
            "download_id": download_id,
            "title": row[0],
            "arr_name": row[1],
        }))

    return {"status": "unprotected", "download_id": download_id}


@api_router.get("/protected")
async def api_list_protected(request: Request):
    db = request.app.state.database
    cursor = await db.db.execute("SELECT * FROM protected_downloads ORDER BY protected_at DESC")
    rows = await cursor.fetchall()
    items = []
    for row in rows:
        items.append({
            "download_id": row[0],
            "title": row[1],
            "arr_name": row[2],
            "protected_at": row[3],
            "reason": row[4],
        })
    return {"items": items}


# ─── API: Config ───────────────────────────────────────────────

def _validate_config_key(key: str, settings) -> bool:
    """Validate that a config override key is allowed."""
    parts = key.split(".")
    if len(parts) == 2 and parts[0] == "general":  # noqa: PLR2004
        return parts[1] in _get_allowed_general_keys()
    if len(parts) == 3 and parts[0] == "jobs":  # noqa: PLR2004
        # parts[1] must be a real job; otherwise the override is persisted
        # but silently no-ops on apply, polluting the DB.
        job = getattr(settings.jobs, parts[1], None)
        if job is None or not hasattr(job, "enabled"):
            return False
        return parts[2] in _get_allowed_job_attrs()
    return False


@api_router.get("/config")
async def api_get_config(request: Request):
    config_manager = request.app.state.config_manager
    config = config_manager.get_current_config()
    overrides = await config_manager.get_overrides()
    return _cached_json({"config": config, "overrides": overrides}, max_age=5)


@api_router.patch("/config")
async def api_update_config(request: Request):
    settings = request.app.state.settings
    config_manager = request.app.state.config_manager
    event_bus = request.app.state.event_bus
    body = await request.json()
    updates = body.get("updates", {})

    applied = {}
    rejected = {}
    for key, value in updates.items():
        if _validate_config_key(key, settings):
            await config_manager.set_override(key, value)
            applied[key] = value
        else:
            rejected[key] = "invalid key"

    if applied:
        await event_bus.emit(Event(EventType.CONFIG_CHANGED, {"updates": applied}))

    result = {"status": "ok", "applied": applied}
    if rejected:
        result["rejected"] = rejected
    return result


@api_router.post("/config/reload")
async def api_reload_config(request: Request):
    config_manager = request.app.state.config_manager
    await config_manager.clear_all_overrides()
    return {"status": "reloaded"}


@api_router.post("/config/test-run")
async def api_toggle_test_run(request: Request):
    settings = request.app.state.settings
    config_manager = request.app.state.config_manager
    event_bus = request.app.state.event_bus

    new_value = not settings.general.test_run
    await config_manager.set_override("general.test_run", new_value)

    await event_bus.emit(Event(EventType.CONFIG_CHANGED, {
        "updates": {"general.test_run": new_value},
    }))

    return {"test_run": new_value}


# ─── API: SSE Events ──────────────────────────────────────────

@api_router.get("/events")
async def api_events(request: Request):
    event_bus = request.app.state.event_bus
    queue = event_bus.subscribe()

    async def event_generator():
        try:
            # Send initial heartbeat
            yield "event: connected\ndata: {}\n\n"
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=30)
                    yield event.to_sse()
                except asyncio.TimeoutError:
                    yield ": heartbeat\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            event_bus.unsubscribe(queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ─── API: Trigger ──────────────────────────────────────────────

@api_router.post("/trigger")
async def api_trigger(request: Request):
    trigger_event = request.app.state.trigger_event
    if trigger_event:
        trigger_event.set()
        return {"status": "triggered"}
    return {"status": "no_trigger_available"}


# ─── Page Routes ───────────────────────────────────────────────

@page_router.get("/", response_class=HTMLResponse)
async def page_dashboard(request: Request):
    templates = request.app.state.templates
    settings = request.app.state.settings

    instances = []
    for arr in settings.instances:
        instances.append({
            "name": arr.name,
            "arr_type": arr.arr_type,
            "base_url": arr.base_url,
        })

    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "settings": settings,
        "instances": instances,
    })


@page_router.get("/activity", response_class=HTMLResponse)
async def page_activity(request: Request):
    templates = request.app.state.templates
    return templates.TemplateResponse("activity.html", {
        "request": request,
        "settings": request.app.state.settings,
    })


@page_router.get("/settings", response_class=HTMLResponse)
async def page_settings(request: Request):
    templates = request.app.state.templates
    config_manager = request.app.state.config_manager
    config = config_manager.get_current_config()
    overrides = await config_manager.get_overrides()
    return templates.TemplateResponse("settings.html", {
        "request": request,
        "settings": request.app.state.settings,
        "config": config,
        "overrides": overrides,
    })


# ─── Partials (for HTMX) ──────────────────────────────────────

@page_router.get("/partials/queue-table", response_class=HTMLResponse)
async def partial_queue_table(request: Request):
    templates = request.app.state.templates
    if not getattr(request.app.state, "first_cycle_done", True):
        return HTMLResponse(
            '<p><em>Waiting for first cycle to complete\u2026</em></p>'
        )
    items = await _fetch_queue(request)
    return templates.TemplateResponse("partials/queue_table.html", {
        "request": request,
        "items": items,
        "total": len(items),
    })


@page_router.get("/partials/activity-feed", response_class=HTMLResponse)
async def partial_activity_feed(request: Request):
    templates = request.app.state.templates
    db = request.app.state.database
    if not getattr(request.app.state, "first_cycle_done", True):
        return HTMLResponse(
            '<p><em>Waiting for first cycle to complete\u2026</em></p>'
        )
    cursor = await db.db.execute(
        "SELECT * FROM activity_log ORDER BY timestamp DESC LIMIT 20"
    )
    rows = await cursor.fetchall()
    items = [_row_to_activity(row) for row in rows]
    return templates.TemplateResponse("partials/activity_feed.html", {
        "request": request,
        "items": items,
    })


@page_router.get("/partials/status-bar", response_class=HTMLResponse)
async def partial_status_bar(request: Request):
    templates = request.app.state.templates
    settings = request.app.state.settings
    return templates.TemplateResponse("partials/status_bar.html", {
        "request": request,
        "settings": settings,
    })
