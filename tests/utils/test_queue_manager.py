from unittest.mock import Mock

import pytest

from src.utils.queue_manager import QueueManager


# ---------- Fixtures ----------
@pytest.fixture(name="mock_queue_manager")
def fixture_mock_queue_manager():
    mock_arr = Mock()
    mock_settings = Mock()
    return QueueManager(arr=mock_arr, settings=mock_settings)


# ---------- Tests ----------
def test_format_queue_empty(mock_queue_manager):
    result = mock_queue_manager.format_queue([])
    assert result == "empty"


def test_format_queue_single_item(mock_queue_manager):
    queue_items = [
        {
            "downloadId": "abc123",
            "title": "Example Download Title",
            "protocol": "torrent",
            "status": "queued",
            "id": 1,
        }
    ]
    expected = {
        "abc123": {
            "title": "Example Download Title",
            "protocol": "torrent",
            "status": "queued",
            "queue_ids": [1],
        }
    }
    result = mock_queue_manager.format_queue(queue_items)
    assert result == expected


def test_format_queue_multiple_same_download_id(mock_queue_manager):
    queue_items = [
        {
            "downloadId": "xyz789",
            "title": "Example Download Title",
            "protocol": "usenet",
            "status": "downloading",
            "id": 1,
        },
        {
            "downloadId": "xyz789",
            "title": "Example Download Title",
            "protocol": "usenet",
            "status": "downloading",
            "id": 2,
        },
    ]
    expected = {
        "xyz789": {
            "title": "Example Download Title",
            "protocol": "usenet",
            "status": "downloading",
            "queue_ids": [1, 2],
        }
    }
    result = mock_queue_manager.format_queue(queue_items)
    assert result == expected


def test_format_queue_multiple_different_download_ids(mock_queue_manager):
    queue_items = [
        {
            "downloadId": "aaa111",
            "title": "Example Download Title A",
            "protocol": "torrent",
            "status": "queued",
            "id": 10,
        },
        {
            "downloadId": "bbb222",
            "title": "Example Download Title B",
            "protocol": "usenet",
            "status": "completed",
            "id": 20,
        },
    ]
    expected = {
        "aaa111": {
            "queue_ids": [10],
            "title": "Example Download Title A",
            "protocol": "torrent",
            "status": "queued",
        },
        "bbb222": {
            "queue_ids": [20],
            "title": "Example Download Title B",
            "protocol": "usenet",
            "status": "completed",
        },
    }
    result = mock_queue_manager.format_queue(queue_items)
    assert result == expected



@pytest.mark.asyncio
async def test_orphans_ignore_progress_between_fetches(mock_queue_manager, monkeypatch):
    # An active download changes sizeleft between the full and the normal fetch.
    # It is in both, so it is not an orphan. Item 2 is only in the full queue.
    full = [
        {"id": 1, "downloadId": "a", "sizeleft": 900, "detail_item_id": 10},
        {"id": 2, "downloadId": "b", "sizeleft": 500, "detail_item_id": None},
    ]
    normal = [{"id": 1, "downloadId": "a", "sizeleft": 850, "detail_item_id": 10}]

    async def fake_refresh():
        return None

    async def fake_get_queue(*, full_queue=False):
        return list(full) if full_queue else list(normal)

    monkeypatch.setattr(mock_queue_manager, "_refresh_queue", fake_refresh)
    monkeypatch.setattr(mock_queue_manager, "_get_queue", fake_get_queue)

    result = await mock_queue_manager.get_queue_items("orphans")

    assert [item["id"] for item in result] == [2]
