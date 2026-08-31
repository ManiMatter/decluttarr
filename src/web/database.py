import asyncio
import json
import os

import aiosqlite

from src.utils.log_setup import logger
from src.web.events import Event, EventType

DEFAULT_DB_PATH = os.environ.get("DECLUTTARR_DB_PATH", "./data/decluttarr.db")

MIGRATIONS = [
    # v1: initial schema
    """
    CREATE TABLE IF NOT EXISTS activity_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT NOT NULL DEFAULT (datetime('now')),
        arr_name TEXT NOT NULL,
        arr_type TEXT NOT NULL,
        job_name TEXT NOT NULL,
        action TEXT NOT NULL,
        download_id TEXT,
        title TEXT NOT NULL,
        strikes INTEGER,
        max_strikes INTEGER,
        details TEXT,
        test_run BOOLEAN NOT NULL DEFAULT 0
    );

    CREATE TABLE IF NOT EXISTS protected_downloads (
        download_id TEXT PRIMARY KEY,
        title TEXT NOT NULL,
        arr_name TEXT NOT NULL,
        protected_at TEXT NOT NULL DEFAULT (datetime('now')),
        reason TEXT
    );

    CREATE TABLE IF NOT EXISTS config_overrides (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL,
        updated_at TEXT NOT NULL DEFAULT (datetime('now'))
    );

    CREATE INDEX IF NOT EXISTS idx_activity_timestamp ON activity_log(timestamp);
    CREATE INDEX IF NOT EXISTS idx_activity_arr_name ON activity_log(arr_name);
    CREATE INDEX IF NOT EXISTS idx_activity_action ON activity_log(action);
    CREATE INDEX IF NOT EXISTS idx_activity_job_name ON activity_log(job_name);
    """,
]


class Database:
    def __init__(self, db_path=None):
        self.db_path = db_path or DEFAULT_DB_PATH
        self._db = None

    async def init(self):
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._db = await aiosqlite.connect(self.db_path)
        self._db.row_factory = aiosqlite.Row
        await self._migrate()

    async def _migrate(self):
        await self._db.execute(
            "CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL)"
        )
        cursor = await self._db.execute("SELECT version FROM schema_version")
        row = await cursor.fetchone()
        current = row[0] if row else 0

        # Seed the version row if missing so migration scripts can UPDATE it.
        if row is None:
            await self._db.execute(
                "INSERT INTO schema_version (version) VALUES (?)", (current,),
            )
            await self._db.commit()

        # Bundle each migration with its version bump in a single executescript
        # call so a partial failure leaves schema_version pointing at the last
        # fully-applied version (rather than skipping ahead or silently retrying).
        for i, migration in enumerate(MIGRATIONS, start=1):
            if i > current:
                script = f"{migration}\nUPDATE schema_version SET version = {i};"
                await self._db.executescript(script)
                logger.info(f"Database migrated to schema v{i}")
        await self._db.commit()

    async def close(self):
        if self._db:
            await self._db.close()

    @property
    def db(self):
        return self._db

    async def cleanup_old_activity(self, days: int = 90):
        """Delete activity_log entries older than the given number of days."""
        if self._db:
            cursor = await self._db.execute(
                "DELETE FROM activity_log WHERE timestamp < datetime('now', ?)",
                (f"-{days} days",),
            )
            await self._db.commit()
            return cursor.rowcount
        return 0


class ActivityRecorder:
    """Subscribes to EventBus and records activity to SQLite."""

    def __init__(self, database: Database, event_bus):
        self.database = database
        self.event_bus = event_bus
        self._task = None

    async def start(self):
        queue = self.event_bus.subscribe()
        self._task = asyncio.create_task(self._consume(queue))
        self._queue = queue

    async def stop(self):
        if self._task:
            self._task.cancel()
            self.event_bus.unsubscribe(self._queue)

    async def _consume(self, queue):
        while True:
            try:
                event = await queue.get()
                await self._record(event)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.debug(f"ActivityRecorder error: {e}")

    async def _record(self, event: Event):
        action_map = {
            EventType.ITEM_FLAGGED: "flagged",
            EventType.ITEM_REMOVED: "removed",
            EventType.ITEM_RECOVERED: "recovered",
            EventType.ITEM_PROTECTED: "protected",
            EventType.ITEM_UNPROTECTED: "unprotected",
            EventType.STRIKE_APPLIED: "strike",
        }
        action = action_map.get(event.event_type)
        if not action:
            return

        data = event.data
        details = json.dumps(data.get("details")) if data.get("details") else None

        await self.database.db.execute(
            """INSERT INTO activity_log
               (arr_name, arr_type, job_name, action, download_id, title, strikes, max_strikes, details, test_run)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                data.get("arr_name", ""),
                data.get("arr_type", ""),
                data.get("job_name", ""),
                action,
                data.get("download_id"),
                data.get("title", "Unknown"),
                data.get("strikes"),
                data.get("max_strikes"),
                details,
                data.get("test_run", False),
            ),
        )
        await self.database.db.commit()
