from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.jobs.remove_stalled import RemoveStalled
from src.settings._download_clients import DownloadClients
from src.settings._instances import Tracker
from tests.jobs.utils import shared_fix_affected_items, shared_test_affected_items


# Test to check if items with the specific error message are included in affected items with parameterized data
@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("queue_data", "expected_download_ids"),
    [
        (
            [
                {
                    "downloadId": "1",
                    "status": "warning",
                    "errorMessage": "The download is stalled with no connections",
                },  # Valid item
                {
                    "downloadId": "2",
                    "status": "completed",
                    "errorMessage": "The download is stalled with no connections",
                },  # Wrong status
                {
                    "downloadId": "3",
                    "status": "warning",
                    "errorMessage": "Some other error",
                },  # Incorrect errorMessage
            ],
            [
                "1"
            ],  # Only the item with "warning" status and the correct errorMessage should be affected
        ),
        (
            [
                {
                    "downloadId": "1",
                    "status": "warning",
                    "errorMessage": "Some other error",
                },  # Incorrect errorMessage
                {
                    "downloadId": "2",
                    "status": "completed",
                    "errorMessage": "The download is stalled with no connections",
                },  # Wrong status
                {
                    "downloadId": "3",
                    "status": "warning",
                    "errorMessage": "The download is stalled with no connections",
                },  # Correct item
            ],
            [
                "3"
            ],  # Only the item with "warning" status and the correct errorMessage should be affected
        ),
        (
            [
                {
                    "downloadId": "1",
                    "status": "warning",
                    "errorMessage": "The download is stalled with no connections",
                },  # Valid item
                {
                    "downloadId": "2",
                    "status": "warning",
                    "errorMessage": "The download is stalled with no connections",
                },  # Another valid item
            ],
            ["1", "2"],  # Both items match the condition
        ),
        (
            [
                {
                    "downloadId": "1",
                    "status": "completed",
                    "errorMessage": "The download is stalled with no connections",
                },  # Wrong status
                {
                    "downloadId": "2",
                    "status": "warning",
                    "errorMessage": "Some other error",
                },  # Incorrect errorMessage
            ],
            [],  # No items match the condition
        ),
    ],
)
async def test_find_affected_items(queue_data, expected_download_ids):
    # Arrange
    removal_job = shared_fix_affected_items(RemoveStalled, queue_data)
    removal_job.job.min_days_stalled = 0

    # Act and Assert
    await shared_test_affected_items(removal_job, expected_download_ids)


NOW = 1_800_000_000
DAY = 86400
STALLED_MESSAGE = "The download is stalled with no connections"


@pytest.fixture(autouse=True)
def _frozen_time(monkeypatch):
    monkeypatch.setattr(
        "src.jobs.remove_stalled.time", SimpleNamespace(time=lambda: NOW)
    )


def _qbit(name, torrents):
    return SimpleNamespace(
        name=name, ready=True, get_qbit_items=AsyncMock(return_value=torrents)
    )


def _stalled_job(qbits, min_days_stalled=7, max_strikes=3):
    download_clients = DownloadClients.__new__(DownloadClients)
    download_clients.qbittorrent = qbits
    download_clients.sabnzbd = []

    settings = MagicMock()
    settings.download_clients = download_clients
    settings.jobs.remove_stalled.min_days_stalled = min_days_stalled
    settings.jobs.remove_stalled.max_strikes = max_strikes

    arr = MagicMock()
    arr.tracker = Tracker()
    return RemoveStalled(arr=arr, settings=settings, job_name="remove_stalled")


def _stalled_item(download_id, client="qBittorrent"):
    return {
        "downloadId": download_id,
        "downloadClient": client,
        "title": f"Title-{download_id}",
        "status": "warning",
        "errorMessage": STALLED_MESSAGE,
    }


async def _affected_ids(job, *items):
    job.queue = list(items)
    return [item["downloadId"] for item in await job._find_affected_items()]


async def _run_job_checks(job, *items):
    job.queue = list(items)
    affected_items = await job._find_affected_items()
    affected_downloads = job.queue_manager.group_by_download_id(affected_items)
    job.strikes_handler.filter_strike_exceeds(affected_downloads, job.queue)


@pytest.mark.asyncio
async def test_min_days_stalled_spares_recently_active_download():
    qbit = _qbit("qBittorrent", [{"hash": "AAA", "last_activity": NOW - DAY}])
    job = _stalled_job([qbit])

    assert await _affected_ids(job, _stalled_item("AAA")) == []


@pytest.mark.asyncio
async def test_min_days_stalled_flags_download_inactive_for_longer():
    qbit = _qbit("qBittorrent", [{"hash": "AAA", "last_activity": NOW - 30 * DAY}])
    job = _stalled_job([qbit])

    assert await _affected_ids(job, _stalled_item("AAA")) == ["AAA"]


@pytest.mark.asyncio
async def test_min_days_stalled_off_does_not_query_qbittorrent():
    qbit = _qbit("qBittorrent", [{"hash": "AAA", "last_activity": NOW}])
    job = _stalled_job([qbit], min_days_stalled=0)

    assert await _affected_ids(job, _stalled_item("AAA")) == ["AAA"]
    qbit.get_qbit_items.assert_not_awaited()


@pytest.mark.asyncio
async def test_min_days_stalled_matches_hashes_case_insensitively():
    qbit = _qbit("qBittorrent", [{"hash": "aaa", "last_activity": NOW - DAY}])
    job = _stalled_job([qbit])

    assert await _affected_ids(job, _stalled_item("AAA")) == []


@pytest.mark.asyncio
async def test_min_days_stalled_does_not_spare_download_unknown_to_client():
    job = _stalled_job([_qbit("qBittorrent", [])])

    assert await _affected_ids(job, _stalled_item("AAA")) == ["AAA"]


@pytest.mark.asyncio
async def test_min_days_stalled_does_not_spare_download_of_other_client():
    qbit = _qbit("qBittorrent", [{"hash": "AAA", "last_activity": NOW}])
    job = _stalled_job([qbit])

    assert await _affected_ids(job, _stalled_item("AAA", client="Other")) == ["AAA"]
    qbit.get_qbit_items.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("added_days_ago", "expected_ids"),
    [(1, []), (30, ["AAA"])],
)
async def test_min_days_stalled_counts_never_active_download_from_when_added(
    added_days_ago, expected_ids
):
    torrent = {
        "hash": "AAA",
        "last_activity": 0,
        "added_on": NOW - added_days_ago * DAY,
    }
    job = _stalled_job([_qbit("qBittorrent", [torrent])])

    assert await _affected_ids(job, _stalled_item("AAA")) == expected_ids


@pytest.mark.asyncio
async def test_min_days_stalled_queries_each_client_for_its_own_downloads():
    qbit_one = _qbit("qBit-1", [{"hash": "AAA", "last_activity": NOW}])
    qbit_two = _qbit("qBit-2", [{"hash": "BBB", "last_activity": NOW - 30 * DAY}])
    job = _stalled_job([qbit_one, qbit_two])

    affected = await _affected_ids(
        job, _stalled_item("AAA", "qBit-1"), _stalled_item("BBB", "qBit-2")
    )

    assert affected == ["BBB"]
    qbit_one.get_qbit_items.assert_awaited_once_with(hashes=["AAA"])
    qbit_two.get_qbit_items.assert_awaited_once_with(hashes=["BBB"])


@pytest.mark.asyncio
async def test_min_days_stalled_keeps_strikes_while_sparing_and_resumes_after():
    torrent = {"hash": "AAA", "last_activity": NOW - DAY}
    job = _stalled_job([_qbit("qBittorrent", [torrent])])
    job.arr.tracker.defective["remove_stalled"] = {
        "AAA": {"title": "Title-AAA", "strikes": 2}
    }
    entry = job.arr.tracker.defective["remove_stalled"]["AAA"]

    await _run_job_checks(job, _stalled_item("AAA"))

    assert entry["strikes"] == 2
    assert entry["tracking_paused"] is True

    torrent["last_activity"] = NOW - 30 * DAY
    await _run_job_checks(job, _stalled_item("AAA"))

    assert entry["strikes"] == 3
    assert "tracking_paused" not in entry
