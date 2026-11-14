from unittest.mock import AsyncMock, MagicMock

import pytest

from src.jobs.remove_slow import RemoveSlow
from tests.jobs.utils import shared_fix_affected_items


# pylint: disable=W0212
@pytest.mark.parametrize(
    "checked_ids, item, expected_return, expected_checked_ids",
    [
        (set(), {"downloadId": "id1"}, False, {"id1"}),
        ({"id1"}, {"downloadId": "id1"}, True, {"id1"}),
        (set(), {"downloadId": "id2"}, False, {"id2"}),
        (set(), {}, False, {"None"}),  # no downloadId key, treated as "None"
        ({"None"}, {}, True, {"None"}),
        ({"id1", "id2"}, {"downloadId": "id3"}, False, {"id1", "id2", "id3"}),
        ({"id1", "id2"}, {"downloadId": "id1"}, True, {"id1", "id2"}),
    ],
)
def test_checked_before(checked_ids, item, expected_return, expected_checked_ids):
    result = RemoveSlow._checked_before(item, checked_ids)
    assert result == expected_return
    assert checked_ids == expected_checked_ids


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("item", "expected_result"),
    [
        (
            # Valid: has downloadId, size, sizeleft, and status = "downloading"
            {
                "downloadId": "abc",
                "size": 1000,
                "sizeleft": 500,
                "status": "downloading",
                "protocol": "torrent",
                "download_client": AsyncMock(),
                "download_client_type": "qbittorrent",
            },
            False,
        ),
        (
            # Invalid: missing one
            {
                "downloadId": "abc",
                "size": 1000,
                "sizeleft": 500,
                "status": "downloading",
                "protocol": "torrent",
                "download_client": AsyncMock(),
            },
            True,
        ),
        (
            # Invalid: missing multiple
            {
                "size": 1000,
                "sizeleft": 500,
            },
            True,
        ),
    ],
)
async def test_missing_keys(item, expected_result):
    removal_job = shared_fix_affected_items(RemoveSlow)
    result = removal_job._missing_keys(item)
    assert result == expected_result


@pytest.mark.parametrize(
    ("item", "expected_result"),
    [
        ({"status": "downloading"}, False),
        ({"status": "completed"}, True),
        ({"status": "paused"}, True),
        ({}, True),  # no status key
    ],
)
def test_not_downloading(item, expected_result):
    result = RemoveSlow._not_downloading(item)
    assert result == expected_result


@pytest.mark.parametrize(
    ("item", "expected_result"),
    [
        ({"size": 1000, "sizeleft": 0}, True),
        ({"size": 1000, "sizeleft": 1}, False),
        ({"size": 0, "sizeleft": 0}, False),
    ],
)
def test_is_completed_but_stuck(item, expected_result):
    removal_job = shared_fix_affected_items(RemoveSlow)
    result = removal_job._is_completed_but_stuck(item)
    assert result == expected_result


@pytest.mark.parametrize(
    ("speed", "expected_result"),
    [
        (None, True),  # speed is None -> not slow
        (0, False),  # speed less than min_speed -> slow (assuming min_speed > 0)
        (5, False),  # speed less than min_speed
        (10, True),  # speed equal or above min_speed (assuming min_speed=10)
        (15, True),  # speed above min_speed
    ],
)
def test_not_slow(speed, expected_result):
    removal_job = shared_fix_affected_items(RemoveSlow)
    removal_job.job.min_speed = 10
    result = removal_job._not_slow(speed)
    assert result == expected_result


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "client_type, expected_progress",
    [
        ("something_else", 100),
        (
            "qbittorrent",
            800,
        ),  # qbit is more updated, has progressed from 100 to 800 since arr refreshed last
        (
            "sabnzbd",
            800,
        ),  # sabnzbd is more updated, has progressed from 100 to 800 since arr refreshed last
    ],
)
async def test_get_download_progress(client_type, expected_progress):
    mock_client = AsyncMock()
    mock_client.fetch_download_progress.return_value = 800

    item = {
        "download_client_type": client_type,
        "download_client": mock_client,
        "size": 1000,
        "sizeleft": 900,
    }

    removal_job = shared_fix_affected_items(RemoveSlow)
    result = await removal_job._get_download_progress(item, "some_id")

    assert result == expected_progress


@pytest.mark.parametrize(
    "download_id, tracker_data, current_progress, expected",
    [
        (
            "id1",
            {"id1": 10_000_000},  # previous_progress = 10 MB
            16_000_000,  # current_progress = 16 MB
            (10_000_000, 6_000_000, 100),  # 6 MB in 1 min => 100 MB/h
        ),  # increment case
        ("id2", {}, 800, (None, None, None)),  # no previous_progress
    ],
)
def test_compute_increment_and_speed(
    download_id, tracker_data, current_progress, expected
):
    removal_job = shared_fix_affected_items(RemoveSlow)
    removal_job.arr.tracker.download_progress = tracker_data
    removal_job.settings.general.timer = 1  # 1 minute interval

    result = removal_job._compute_increment_and_speed(download_id, current_progress)
    assert result == expected


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "item, previous_progress, mock_progress, expected_increment, expected_speed",
    [
        (
            {"downloadId": "id1", "download_client_type": "qbittorrent"},
            1_000_000,
            1_600_000,
            600_000,
            10.0,
        ),
        (
            {"downloadId": "id2", "download_client_type": "qbittorrent"},
            None,
            800_000,
            None,
            None,
        ),
    ],
)
async def test_get_progress_stats(
    item, previous_progress, mock_progress, expected_increment, expected_speed
):
    """
    Test `_get_progress_stats` to ensure it correctly returns the current progress,
    previous progress, increment, and calculated speed. It also verifies that the
    download progress is updated in the tracker after execution.

    - If a previous progress value exists in the tracker, the increment and speed
    are calculated.
    - If no previous value exists, increment and speed should be None.
    """
    removal_job = shared_fix_affected_items(RemoveSlow)

    # Ensure tracker dict is initialized properly
    removal_job.arr.tracker.download_progress = {}

    download_id = item["downloadId"]
    if previous_progress is not None:
        removal_job.arr.tracker.download_progress[download_id] = previous_progress

    # Mock _get_download_progress to return a high fixed value
    removal_job._get_download_progress = AsyncMock(return_value=mock_progress)
    removal_job.settings.general.timer = 1  # 1-minute interval

    result = await removal_job._get_progress_stats(item)

    expected = (
        mock_progress,
        previous_progress,
        expected_increment,
        expected_speed,
    )
    assert result == expected
    assert removal_job.arr.tracker.download_progress[download_id] == mock_progress


@pytest.mark.parametrize(
    ("download_id", "download_client_type", "bandwidth_usage", "expected"),
    [
        (0, "qbittorrent", 0.81, True),  # above threshold 0.8
        (1, "qbittorrent", 0.8, False),  # equal to threshold 0.8
        (2, "qbittorrent", 0.79, False),  # below threshold 0.8
        (3, "sabnzbd", 0.9, False),  # SABnzbd client type (no bandwidth checking)
        (4, "other_client", 0.9, False),  # different client type
    ],
)
def test_high_bandwidth_usage(
    download_id, download_client_type, bandwidth_usage, expected
):
    """
    Test RemoveSlow._high_bandwidth_usage method.

    Checks if the method correctly identifies high bandwidth usage
    only when the download client type is 'qbittorrent' and the
    bandwidth usage exceeds the defined threshold (0.8).
    For other client types or bandwidth usage below or equal to threshold,
    it should return False.
    """

    class DummyClient:
        def __init__(self, usage):
            self.bandwidth_usage = usage

    item = {
        "download_client": DummyClient(bandwidth_usage),
        "download_client_type": download_client_type,
        "downloadId": download_id,
    }
    removal_job = shared_fix_affected_items(RemoveSlow)
    result = removal_job._high_bandwidth_usage(item)
    assert result == expected


@pytest.mark.asyncio
async def test_add_download_client_to_queue_items_simple():
    """
    Test that 'add_download_client_to_queue_items' correctly adds
    the download client object and its type to each queue item,
    based on the client's name retrieved from settings.
    """
    removal_job = shared_fix_affected_items(RemoveSlow)
    client_name = "MyQbitInstance"
    download_client_type = "qbittorrent"
    removal_job.queue = [{"downloadClient": client_name}]

    dummy_client = MagicMock(name="QBClient")
    removal_job.settings.download_clients = MagicMock()
    removal_job.settings.download_clients.get_download_client_by_name = MagicMock(
        return_value=(dummy_client, download_client_type)
    )

    await removal_job.add_download_client_to_queue_items()

    item = removal_job.queue[0]
    assert item["download_client"] == dummy_client
    assert item["download_client_type"] == download_client_type


@pytest.mark.asyncio
async def test_update_bandwidth_usage_calls_once_per_client():
    """
    Test that 'update_bandwidth_usage' calls 'set_bandwidth_usage' exactly once
    per unique download client of type 'qbittorrent' in the queue,
    and does not call it for other client types.
    """
    removal_job = shared_fix_affected_items(RemoveSlow)

    # Create two dummy clients
    qb_client1 = MagicMock(name="QBClient1")
    qb_client1.set_bandwidth_usage = AsyncMock()
    qb_client2 = MagicMock(name="QBClient2")
    qb_client2.set_bandwidth_usage = AsyncMock()
    sabnzbd_client = MagicMock(name="SABnzbdClient")
    other_client = MagicMock(name="OtherClient")
    other_client.set_bandwidth_usage = AsyncMock()

    removal_job.queue = [
        {"download_client": qb_client1, "download_client_type": "qbittorrent"},
        {
            "download_client": qb_client1,
            "download_client_type": "qbittorrent",
        },  # duplicate client
        {"download_client": qb_client2, "download_client_type": "qbittorrent"},
        {
            "download_client": sabnzbd_client,
            "download_client_type": "sabnzbd",
        },  # SABnzbd client
        {"download_client": other_client, "download_client_type": "other"},
    ]

    await removal_job.update_bandwidth_usage()

    # Verify set_bandwidth_usage called once per unique qbittorrent client
    qb_client1.set_bandwidth_usage.assert_awaited_once()
    qb_client2.set_bandwidth_usage.assert_awaited_once()
    # Verify SABnzbd and other client methods were not called (no bandwidth tracking for them)
    assert (
        not hasattr(sabnzbd_client, "set_bandwidth_usage")
        or not sabnzbd_client.set_bandwidth_usage.called
    )
    other_client.set_bandwidth_usage.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "queue_item, should_be_affected",
    [
        # Already checked downloadId -> skip (simulate by repeating downloadId)
        ({"downloadId": "checked_before"}, False),
        # Keys not present -> skip
        ({"downloadId": "keys_missing"}, False),
        # Not Downloading -> skip
        ({"downloadId": "not_downloading"}, False),
        # Completed but stuck -> skip
        ({"downloadId": "completed_but_stuck"}, False),
        # High bandwidth usage -> skip
        ({"downloadId": "high_bandwidth"}, False),
        # Not slow -> skip
        ({"downloadId": "not_slow"}, False),
        # None of above, hence truly slow
        ({"downloadId": "good"}, True),
    ],
)
async def test_find_affected_items_simple(queue_item, should_be_affected):
    # Add minimum fields required
    queue_item["title"] = queue_item.get("downloadId", "dummy")
    removal_job = shared_fix_affected_items(RemoveSlow, queue_data=[queue_item])

    # Mock async methods
    removal_job.add_download_client_to_queue_items = AsyncMock()
    removal_job.update_bandwidth_usage = AsyncMock()
    removal_job._get_progress_stats = AsyncMock(return_value=(1000, 900, 100, 10))

    # Setup checks to pass except in for the designated tests
    removal_job._checked_before = (
        lambda item, checked_ids: item.get("downloadId") == "checked_before"
    )
    removal_job._missing_keys = lambda item: item.get("downloadId") == "keys_missing"
    removal_job._not_downloading = (
        lambda item: item.get("downloadId") == "not_downloading"
    )
    removal_job._is_completed_but_stuck = (
        lambda item: item.get("downloadId") == "completed_but_stuck"
    )
    removal_job._high_bandwidth_usage = (
        lambda download_client, download_client_type=None: queue_item.get("downloadId")
        == "high_bandwidth"
    )
    removal_job._not_slow = lambda speed: queue_item.get("downloadId") == "not_slow"

    # Run the method under test
    affected_items = await removal_job._find_affected_items()

    if should_be_affected:
        assert affected_items, f"Item {queue_item.get('downloadId')} should be affected"
        assert affected_items[0]["downloadId"] == queue_item["downloadId"]
    else:
        assert (
            not affected_items
        ), f"Item {queue_item.get('downloadId')} should NOT be affected"


@pytest.mark.asyncio
async def test_add_download_client_resolves_ready_only():
    """A not-ready client resolves to None so downstream job logic skips it."""
    job = RemoveSlow.__new__(RemoveSlow)
    job.settings = MagicMock()
    job.settings.download_clients.get_download_client_by_name.return_value = (
        None,
        None,
    )
    job.queue = [{"downloadClient": "qBittorrent"}]

    await job.add_download_client_to_queue_items()

    job.settings.download_clients.get_download_client_by_name.assert_called_once_with(
        "qBittorrent", ready_only=True
    )
    assert job.queue[0]["download_client"] is None
    assert job.queue[0]["download_client_type"] is None


@pytest.mark.asyncio
async def test_update_bandwidth_usage_skips_degraded_client():
    """A degraded client (mapped to None) must not have set_bandwidth_usage called."""
    job = RemoveSlow.__new__(RemoveSlow)
    job.queue = [{"download_client": None, "download_client_type": None}]

    # Should be a no-op — no client to call, no exception.
    await job.update_bandwidth_usage()


@pytest.mark.asyncio
async def test_update_bandwidth_usage_calls_ready_qbit():
    """A ready qbit client still gets its bandwidth refreshed (regression)."""
    client = AsyncMock()
    job = RemoveSlow.__new__(RemoveSlow)
    job.queue = [{"download_client": client, "download_client_type": "qbittorrent"}]

    await job.update_bandwidth_usage()

    client.set_bandwidth_usage.assert_awaited_once()
