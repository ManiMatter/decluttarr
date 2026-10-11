from unittest.mock import AsyncMock, Mock

import pytest

from src.utils.wanted_manager import WantedManager


# ---------- Fixtures ----------
@pytest.fixture(name="mock_wanted_manager")
def fixture_mock_wanted_manager():
    mock_arr = Mock()
    mock_arr.detail_item_key = "episode"
    mock_settings = Mock()
    return WantedManager(arr=mock_arr, settings=mock_settings)


# ---------- Tests ----------
@pytest.mark.asyncio
async def test_get_arr_records_empty_returns_early(mock_wanted_manager):
    mock_wanted_manager.fetch_wanted_field = AsyncMock()
    result = await mock_wanted_manager._get_arr_records("missing", 0)  # pylint: disable=W0212
    assert result == []
    mock_wanted_manager.fetch_wanted_field.assert_not_called()


@pytest.mark.asyncio
async def test_get_arr_records_sorts_ascending(mock_wanted_manager):
    # Regression test for #376: without an explicit ascending sortDirection the
    # *arr API returns most-recently-searched items first, re-searching the same
    # top N forever while never-searched items are starved.
    mock_wanted_manager.fetch_wanted_field = AsyncMock(return_value=[{"id": 1}])

    await mock_wanted_manager._get_arr_records("missing", 42)  # pylint: disable=W0212

    _, kwargs = mock_wanted_manager.fetch_wanted_field.call_args
    params = kwargs["params"]
    assert params["sortKey"] == "episodes.lastSearchTime"
    assert params["sortDirection"] == "ascending"
    assert params["pageSize"] == 42
