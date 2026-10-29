from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.jobs.search_handler import SearchHandler


@pytest.fixture(name="mock_arr")
def fixture_mock_arr():
    arr = MagicMock()
    arr.arr_type = "radarr"
    arr.detail_item_key = "movie"
    return arr


@pytest.fixture(name="mock_settings")
def fixture_mock_settings():
    settings = MagicMock()
    settings.jobs.search_missing = MagicMock()
    settings.jobs.search_missing.enabled = True
    settings.jobs.search_missing.min_days_between_searches = 7
    settings.jobs.search_missing.max_concurrent_searches = 3
    settings.jobs.search_missing.check_availability = False

    settings.jobs.search_unmet_cutoff = MagicMock()
    settings.jobs.search_unmet_cutoff.enabled = True
    settings.jobs.search_unmet_cutoff.min_days_between_searches = 7
    settings.jobs.search_unmet_cutoff.max_concurrent_searches = 3
    settings.jobs.search_unmet_cutoff.check_availability = False
    return settings


def test_configure_search_target_missing(mock_arr, mock_settings):
    handler = SearchHandler(mock_arr, mock_settings, "missing", "search_missing")
    assert handler.job == mock_settings.jobs.search_missing
    assert handler.search_target_label == "missing movies"


def test_configure_search_target_cutoff(mock_arr, mock_settings):
    handler = SearchHandler(mock_arr, mock_settings, "cutoff", "search_cutoff_unmet")
    assert handler.job == mock_settings.jobs.search_unmet_cutoff
    assert handler.search_target_label == "movies with unmet cutoff"


def test_configure_search_target_unknown(mock_arr, mock_settings):
    with pytest.raises(ValueError, match="Unknown search type: invalid"):
        SearchHandler(mock_arr, mock_settings, "invalid", "job")


def test_filter_already_downloading(mock_arr, mock_settings):
    handler = SearchHandler(mock_arr, mock_settings, "missing", "search_missing")
    items = [{"id": 1, "title": "Movie 1"}, {"id": 2, "title": "Movie 2"}]
    queue = [{"detail_item_id": 1}]
    filtered = handler._filter_already_downloading(items, queue)
    assert filtered == [{"id": 2, "title": "Movie 2"}]


def test_filter_unavailable_skips_when_is_available_false(mock_arr, mock_settings):
    handler = SearchHandler(mock_arr, mock_settings, "missing", "search_missing")
    items = [
        {"id": 1, "title": "Released Movie", "isAvailable": True},
        {"id": 2, "title": "Unreleased Movie", "isAvailable": False},
        {"id": 3, "title": "Sonarr Episode"},  # Non-radarr item without isAvailable
    ]
    filtered = handler._filter_unavailable(items)
    assert len(filtered) == 2
    assert filtered[0]["id"] == 1
    assert filtered[1]["id"] == 3


def test_filter_wanted_items_check_availability_disabled(mock_arr, mock_settings):
    mock_settings.jobs.search_missing.check_availability = False
    handler = SearchHandler(mock_arr, mock_settings, "missing", "search_missing")

    items = [
        {"id": 1, "title": "Released Movie", "isAvailable": True},
        {"id": 2, "title": "Unreleased Movie", "isAvailable": False},
    ]
    queue = []
    filtered = handler._filter_wanted_items(items, queue)
    # Both items should be retained when check_availability is False
    assert len(filtered) == 2


def test_filter_wanted_items_check_availability_enabled(mock_arr, mock_settings):
    mock_settings.jobs.search_missing.check_availability = True
    handler = SearchHandler(mock_arr, mock_settings, "missing", "search_missing")

    items = [
        {"id": 1, "title": "Released Movie", "isAvailable": True},
        {"id": 2, "title": "Unreleased Movie", "isAvailable": False},
    ]
    queue = []
    filtered = handler._filter_wanted_items(items, queue)
    # Only available movie retained
    assert len(filtered) == 1
    assert filtered[0]["id"] == 1


def test_filter_wanted_items_all_unavailable(mock_arr, mock_settings):
    mock_settings.jobs.search_missing.check_availability = True
    handler = SearchHandler(mock_arr, mock_settings, "missing", "search_missing")

    items = [
        {"id": 1, "title": "Unreleased Movie 1", "isAvailable": False},
        {"id": 2, "title": "Unreleased Movie 2", "isAvailable": False},
    ]
    queue = []
    filtered = handler._filter_wanted_items(items, queue)
    assert filtered == []


def test_filter_recent_searches(mock_arr, mock_settings):
    handler = SearchHandler(mock_arr, mock_settings, "missing", "search_missing")
    now = datetime.now(timezone.utc)
    old_search = (now - timedelta(days=10)).isoformat()
    recent_search = (now - timedelta(days=2)).isoformat()

    items = [
        {"id": 1, "title": "Never searched"},
        {"id": 2, "title": "Searched 10 days ago", "lastSearchTime": old_search},
        {"id": 3, "title": "Searched 2 days ago", "lastSearchTime": recent_search},
    ]
    filtered = handler._filter_recent_searches(items)
    assert len(filtered) == 2
    assert filtered[0]["id"] == 1
    assert filtered[1]["id"] == 2


@pytest.mark.asyncio
async def test_handle_search_end_to_end_with_availability_check(
    mock_arr, mock_settings
):
    mock_settings.jobs.search_missing.check_availability = True
    handler = SearchHandler(mock_arr, mock_settings, "missing", "search_missing")

    items = [
        {"id": 1, "title": "Available Movie", "isAvailable": True},
        {"id": 2, "title": "Unreleased Movie", "isAvailable": False},
        {"id": 3, "title": "Downloading Movie", "isAvailable": True},
    ]
    queue = [{"detail_item_id": 3}]

    with (
        patch.object(
            handler, "_get_initial_wanted_items", AsyncMock(return_value=items)
        ),
        patch("src.jobs.search_handler.QueueManager") as mock_qm_class,
        patch.object(
            handler.wanted_manager, "search_items", AsyncMock()
        ) as mock_search,
    ):
        mock_qm = AsyncMock()
        mock_qm.get_queue_items = AsyncMock(return_value=queue)
        mock_qm_class.return_value = mock_qm

        await handler.handle_search()

        # Should only trigger search for id 1 (id 2 is not available, id 3 is already downloading)
        mock_search.assert_awaited_once_with([1])


@pytest.mark.asyncio
async def test_handle_search_no_search_when_all_unavailable(mock_arr, mock_settings):
    mock_settings.jobs.search_missing.check_availability = True
    handler = SearchHandler(mock_arr, mock_settings, "missing", "search_missing")

    items = [
        {"id": 1, "title": "Unreleased Movie 1", "isAvailable": False},
        {"id": 2, "title": "Unreleased Movie 2", "isAvailable": False},
    ]

    with (
        patch.object(
            handler, "_get_initial_wanted_items", AsyncMock(return_value=items)
        ),
        patch("src.jobs.search_handler.QueueManager") as mock_qm_class,
        patch.object(
            handler.wanted_manager, "search_items", AsyncMock()
        ) as mock_search,
    ):
        mock_qm = AsyncMock()
        mock_qm.get_queue_items = AsyncMock(return_value=[])
        mock_qm_class.return_value = mock_qm

        await handler.handle_search()

        mock_search.assert_not_called()


@pytest.mark.asyncio
async def test_get_initial_wanted_items(mock_arr, mock_settings):
    handler = SearchHandler(mock_arr, mock_settings, "missing", "search_missing")
    expected = [{"id": 1, "title": "Movie 1"}]

    with patch.object(
        handler.wanted_manager, "get_wanted_items", AsyncMock(return_value=expected)
    ):
        result = await handler._get_initial_wanted_items()
        assert result == expected
