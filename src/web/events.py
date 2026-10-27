import asyncio
import json
import time
from enum import Enum


class EventType(str, Enum):
    CYCLE_START = "cycle_start"
    CYCLE_END = "cycle_end"
    ITEM_FLAGGED = "item_flagged"
    ITEM_REMOVED = "item_removed"
    ITEM_RECOVERED = "item_recovered"
    ITEM_PROTECTED = "item_protected"
    ITEM_UNPROTECTED = "item_unprotected"
    STRIKE_APPLIED = "strike_applied"
    CONFIG_CHANGED = "config_changed"


class Event:
    def __init__(self, event_type: EventType, data: dict = None):
        self.event_type = event_type
        self.data = data or {}
        self.timestamp = time.time()

    def to_sse(self):
        payload = {
            "type": self.event_type.value,
            "data": self.data,
            "timestamp": self.timestamp,
        }
        return f"event: {self.event_type.value}\ndata: {json.dumps(payload)}\n\n"


class EventBus:
    def __init__(self):
        self._subscribers: list[asyncio.Queue] = []
        self._enabled = True

    def subscribe(self) -> asyncio.Queue:
        queue = asyncio.Queue(maxsize=100)
        self._subscribers.append(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue):
        if queue in self._subscribers:
            self._subscribers.remove(queue)

    async def emit(self, event: Event):
        if not self._enabled:
            return
        for queue in list(self._subscribers):
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                # Drop oldest event if queue is full
                try:
                    queue.get_nowait()
                    queue.put_nowait(event)
                except (asyncio.QueueEmpty, asyncio.QueueFull):
                    pass

    def disable(self):
        self._enabled = False

    def enable(self):
        self._enabled = True


# Global no-op event bus for when web is disabled
class NoOpEventBus:
    def subscribe(self):
        return None

    def unsubscribe(self, queue):
        pass

    async def emit(self, event):
        pass

    def disable(self):
        pass

    def enable(self):
        pass
