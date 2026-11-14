from types import SimpleNamespace
from unittest.mock import MagicMock

from src.jobs.remove_stalled import RemoveStalled
from src.utils.queue_manager import QueueManager


def _job_with_clients():
    """A RemovalJob (via a concrete subclass) whose settings resolve clients by name."""
    job = RemoveStalled.__new__(RemoveStalled)
    job.job_name = "remove_stalled"
    job.arr = MagicMock()
    job.arr.name = "Sonarr"

    ready = SimpleNamespace(name="qbit-ready", ready=True)
    degraded = SimpleNamespace(name="qbit-degraded", ready=False)

    def resolver(name, *args, **kwargs):
        return {
            "qbit-ready": (ready, "qbittorrent"),
            "qbit-degraded": (degraded, "qbittorrent"),
        }.get(name, (None, None))

    job.settings = MagicMock()
    job.settings.download_clients.get_download_client_by_name.side_effect = resolver
    return job


def test_ignore_degraded_client_downloads_is_fail_closed():
    """Downloads on a degraded client are left untouched; healthy and
    unconfigured clients are unaffected (this is the guard that prevents the
    data-loss scenario where a degraded qBit's protected torrents get deleted).

    affected_downloads is built via the real group_by_download_id so the grouped
    dict shape is exercised (a list-shaped fixture would hide a KeyError)."""
    job = _job_with_clients()
    grouped = QueueManager.group_by_download_id(
        None,
        [
            {"downloadId": "on_ready", "id": 1, "downloadClient": "qbit-ready"},
            {"downloadId": "on_degraded", "id": 2, "downloadClient": "qbit-degraded"},
            {
                "downloadId": "on_unconfigured",
                "id": 3,
                "downloadClient": "other-client",
            },
        ],
    )
    job.affected_downloads = grouped

    job._ignore_degraded_client_downloads()

    assert "on_ready" in job.affected_downloads  # healthy -> still removable
    assert "on_degraded" not in job.affected_downloads  # degraded -> protected
    assert "on_unconfigured" in job.affected_downloads  # unconfigured -> unchanged
