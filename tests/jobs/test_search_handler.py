from datetime import datetime, timedelta, timezone

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
