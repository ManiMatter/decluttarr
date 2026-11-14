from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from src.jobs.search_handler import SearchHandler

PAST = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()
FUTURE = (datetime.now(timezone.utc) + timedelta(days=3)).isoformat()
FUTURE_NAIVE = (datetime.now(timezone.utc) + timedelta(days=3)).replace(tzinfo=None).isoformat()


@pytest.mark.parametrize(
    ("items", "expected_ids"),
    [
        # Radarr: isAvailable follows the movie's minimum availability
        (
            [
                {"id": 1, "isAvailable": True, "releaseDate": FUTURE},
                {"id": 2, "isAvailable": False, "releaseDate": PAST},
            ],
            [1],
        ),
        # Sonarr: episodes that have not aired yet are skipped
        ([{"id": 1, "airDateUtc": PAST}, {"id": 2, "airDateUtc": FUTURE}], [1]),
        # Lidarr / Readarr: future release dates are skipped, naive dates too
        (
            [
                {"id": 1, "releaseDate": PAST},
                {"id": 2, "releaseDate": FUTURE},
                {"id": 3, "releaseDate": FUTURE_NAIVE},
            ],
            [1],
        ),
        # No date info -> kept, as before
        ([{"id": 1}, {"id": 2, "airDateUtc": None}], [1, 2]),
        # Nothing released yet
        ([{"id": 1, "isAvailable": False}, {"id": 2, "airDateUtc": FUTURE}], []),
    ],
)
def test_filter_unreleased(items, expected_ids):
    result = SearchHandler._filter_unreleased(items)  # pylint: disable=W0212
    assert [item["id"] for item in result] == expected_ids


def _handler(skip_unreleased):
    arr = MagicMock()
    arr.arr_type = "radarr"
    arr.detail_item_key = "movie"
    settings = MagicMock()
    settings.jobs.search_missing.min_days_between_searches = 7
    settings.jobs.search_missing.max_concurrent_searches = 3
    settings.jobs.search_missing.skip_unreleased = skip_unreleased
    return SearchHandler(arr, settings, "missing", "search_missing")


@pytest.mark.parametrize(
    ("skip_unreleased", "expected_ids"),
    [(True, [1]), (False, [1, 2, 3])],
)
def test_filter_wanted_items_skip_unreleased_toggle(skip_unreleased, expected_ids):
    items = [
        {"id": 1, "airDateUtc": PAST},
        {"id": 2, "airDateUtc": FUTURE},
        {"id": 3, "isAvailable": False},
    ]
    result = _handler(skip_unreleased)._filter_wanted_items(items, [])  # pylint: disable=W0212
    assert [item["id"] for item in result] == expected_ids
