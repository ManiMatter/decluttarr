from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.jobs import removal_job
from src.jobs.remove_stalled import RemoveStalled
from src.web.events import EventType


def _job(protected_ids):
    arr = MagicMock()
    arr.name = "Sonarr"
    arr.arr_type = "sonarr"
    arr.tracker = SimpleNamespace(protected=list(protected_ids))
    settings = MagicMock()
    settings.general.test_run = False
    settings.jobs.remove_stalled.max_strikes = None
    job = RemoveStalled(arr=arr, settings=settings, job_name="remove_stalled", event_bus=MagicMock(emit=AsyncMock()))
    job.affected_downloads = {
        "AAA": {"title": "Protected one"},
        "BBB": {"title": "Normal one"},
    }
    return job


def _emitted(job):
    return [(c.args[0].event_type, c.args[0].data["download_id"]) for c in job.event_bus.emit.await_args_list]


@pytest.mark.asyncio
async def test_protected_download_is_not_flagged_but_skipped_once():
    removal_job._REPORTED_PROTECTED_SKIPS.clear()
    job = _job(["AAA"])
    protected = {k: v for k, v in job.affected_downloads.items() if k in job.arr.tracker.protected}
    job._ignore_protected()

    for _ in range(3):  # three cycles
        await job._emit_flagged_events()
        await job._emit_protected_skip_events(protected)

    events = _emitted(job)
    assert events.count((EventType.ITEM_SKIPPED, "AAA")) == 1
    assert (EventType.ITEM_FLAGGED, "AAA") not in events
    assert events.count((EventType.ITEM_FLAGGED, "BBB")) == 3
