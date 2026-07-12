import logging
from unittest.mock import AsyncMock, MagicMock

import pytest
import requests

from src.jobs.remove_unmonitored import RemoveUnmonitored
from tests.jobs.utils import shared_fix_affected_items, shared_test_affected_items


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("queue_data", "monitored_ids", "expected_download_ids"),
    [
        # All items monitored -> no affected items
        (
            [
                {"downloadId": "1", "detail_item_id": 101},
                {"downloadId": "2", "detail_item_id": 102},
            ],
            {101: True, 102: True},
            [],
        ),
        # All items unmonitored -> all affected
        (
            [
                {"downloadId": "1", "detail_item_id": 101},
                {"downloadId": "2", "detail_item_id": 102},
            ],
            {101: False, 102: False},
            ["1", "2"],
        ),
        # One monitored, one not
        (
            [
                {"downloadId": "1", "detail_item_id": 101},
                {"downloadId": "2", "detail_item_id": 102},
            ],
            {101: True, 102: False},
            ["2"],
        ),
        # Shared downloadId, only one monitored -> not affected
        (
            [
                {"downloadId": "1", "detail_item_id": 101},
                {"downloadId": "1", "detail_item_id": 102},
            ],
            {101: False, 102: True},
            [],
        ),
        # Shared downloadId, none monitored -> affected
        (
            [
                {"downloadId": "1", "detail_item_id": 101},
                {"downloadId": "1", "detail_item_id": 102},
            ],
            {101: False, 102: False},
            ["1", "1"],
        ),
        # One monitored, one not, one not matched yet
        (
            [
                {"downloadId": "1", "detail_item_id": 101},
                {"downloadId": "2", "detail_item_id": 102},
                {"downloadId": "3", "detail_item_id": None},
            ],
            {101: True, 102: False},
            ["2"],
        ),
    ],
)
async def test_find_affected_items(queue_data, monitored_ids, expected_download_ids):
    # Arrange
    removal_job = shared_fix_affected_items(RemoveUnmonitored, queue_data)
    removal_job.arr.is_monitored = AsyncMock(side_effect=lambda id_: monitored_ids[id_])
    # Act and Assert
    await shared_test_affected_items(removal_job, expected_download_ids)


@pytest.mark.asyncio
async def test_stale_queue_item_is_skipped_and_processing_continues(caplog):
    queue_data = [
        {"downloadId": "stale", "detail_item_id": 101},
        {"downloadId": "unmonitored", "detail_item_id": 102},
    ]
    removal_job = shared_fix_affected_items(RemoveUnmonitored, queue_data)
    removal_job.arr.detail_item_key = "book"
    removal_job.arr.name = "Readarr"

    not_found = requests.exceptions.HTTPError("404 Not Found")
    not_found.response = MagicMock(status_code=404)
    removal_job.arr.is_monitored = AsyncMock(side_effect=[not_found, False])

    with caplog.at_level(logging.WARNING, logger="src.utils.log_setup"):
        await shared_test_affected_items(removal_job, ["unmonitored"])

    removal_job.arr.is_monitored.assert_awaited()
    assert "Skipping stale queue item stale" in caplog.text
    assert "book 101 no longer exists on Readarr" in caplog.text


@pytest.mark.asyncio
async def test_non_404_monitoring_error_is_raised():
    queue_data = [{"downloadId": "failed", "detail_item_id": 101}]
    removal_job = shared_fix_affected_items(RemoveUnmonitored, queue_data)
    server_error = requests.exceptions.HTTPError("500 Server Error")
    server_error.response = MagicMock(status_code=500)
    removal_job.arr.is_monitored = AsyncMock(side_effect=server_error)

    with pytest.raises(requests.exceptions.HTTPError, match="500 Server Error"):
        await removal_job._find_affected_items()  # pylint: disable=protected-access
