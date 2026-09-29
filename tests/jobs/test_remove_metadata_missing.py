from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.jobs.remove_metadata_missing import RemoveMetadataMissing
from tests.jobs.utils import shared_fix_affected_items, shared_test_affected_items


def _metadata_missing_job(
    *,
    max_strikes=None,
    protected=(),
    ignored_download_clients=(),
    detect_via_missing_size=False,
):
    arr = MagicMock()
    arr.name = "Sonarr"
    arr.detail_item_id_key = "episodeId"
    arr.tracker = SimpleNamespace(
        protected=list(protected),
        private=[],
        deleted=[],
        defective={},
    )
    arr.remove_queue_item = AsyncMock()

    job = SimpleNamespace(enabled=True, detect_via_missing_size=detect_via_missing_size)
    if max_strikes is not None:
        job.max_strikes = max_strikes

    settings = MagicMock()
    settings.jobs.remove_metadata_missing = job
    settings.general.ignored_download_clients = list(ignored_download_clients)
    settings.download_clients.qbittorrent = []
    settings.download_clients.get_download_client_by_name.return_value = (None, None)

    return RemoveMetadataMissing(arr, settings, "remove_metadata_missing")


def _metadata_queue_item(download_id="metadata-stuck", queue_id=101, **changes):
    item = {
        "id": queue_id,
        "downloadId": download_id,
        "title": "Metadata.Stuck.Release",
        "protocol": "torrent",
        "downloadClient": "qBittorrent",
        "status": "queued",
        "errorMessage": "qBittorrent is downloading metadata",
        "size": 0,
        "episodeId": None,
        "seriesId": None,
    }
    item.update(changes)
    return item


def _serve_api_queues(removal_job, *, normal, full):
    queues = {False: normal, True: full}
    removal_job.queue_manager._refresh_queue = AsyncMock()
    removal_job.queue_manager._get_total_records_count = AsyncMock(
        side_effect=lambda full_queue: len(queues[full_queue])
    )
    removal_job.queue_manager._get_arr_records = AsyncMock(
        side_effect=lambda full_queue, _total_records_count: [
            dict(item) for item in queues[full_queue]
        ]
    )


# Test to check if items with the specific error message are included in affected items with parameterized data
@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("queue_data", "expected_download_ids"),
    [
        (
            [
                {
                    "downloadId": "1",
                    "status": "queued",
                    "errorMessage": "qBittorrent is downloading metadata",
                },  # Valid item
                {
                    "downloadId": "2",
                    "status": "completed",
                    "errorMessage": "qBittorrent is downloading metadata",
                },  # Wrong status
                {
                    "downloadId": "3",
                    "status": "queued",
                    "errorMessage": "Some other error",
                },  # Incorrect errorMessage
            ],
            [
                "1"
            ],  # Only the item with "queued" status and the correct errorMessage should be affected
        ),
        (
            [
                {
                    "downloadId": "1",
                    "status": "queued",
                    "errorMessage": "Some other error",
                },  # Incorrect errorMessage
                {
                    "downloadId": "2",
                    "status": "completed",
                    "errorMessage": "qBittorrent is downloading metadata",
                },  # Wrong status
                {
                    "downloadId": "3",
                    "status": "queued",
                    "errorMessage": "qBittorrent is downloading metadata",
                },  # Correct item
            ],
            [
                "3"
            ],  # Only the item with "queued" status and the correct errorMessage should be affected
        ),
        (
            [
                {
                    "downloadId": "1",
                    "status": "queued",
                    "errorMessage": "qBittorrent is downloading metadata",
                },  # Valid item
                {
                    "downloadId": "2",
                    "status": "queued",
                    "errorMessage": "qBittorrent is downloading metadata",
                },  # Another valid item
            ],
            ["1", "2"],  # Both items match the condition
        ),
        (
            [
                {
                    "downloadId": "1",
                    "status": "completed",
                    "errorMessage": "qBittorrent is downloading metadata",
                },  # Wrong status
                {
                    "downloadId": "2",
                    "status": "queued",
                    "errorMessage": "Some other error",
                },  # Incorrect errorMessage
            ],
            [],  # No items match the condition
        ),
    ],
)
async def test_find_affected_items(queue_data, expected_download_ids):
    # Arrange
    removal_job = shared_fix_affected_items(RemoveMetadataMissing, queue_data)
    removal_job.job = SimpleNamespace(detect_via_missing_size=False)

    # Act and Assert
    await shared_test_affected_items(removal_job, expected_download_ids)


# Tests the opt-in, client-agnostic detection of items stuck without metadata
# (status "queued" + size 0), e.g. on Transmission/Deluge which do not surface the
# qBittorrent "downloading metadata" message in the *arr queue (see issue #57).
@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("detect_via_missing_size", "queue_data", "expected_download_ids"),
    [
        # Disabled (default): a queued size-0 item is NOT flagged; only the qBit message is.
        (
            False,
            [
                {
                    "id": 1,
                    "downloadId": "a",
                    "status": "queued",
                    "size": 0,
                    "errorMessage": None,
                },
                {
                    "id": 2,
                    "downloadId": "b",
                    "status": "queued",
                    "errorMessage": "qBittorrent is downloading metadata",
                },
            ],
            ["b"],
        ),
        # Enabled: queued + size 0 is flagged; size > 0 and non-queued are left alone.
        (
            True,
            [
                {
                    "id": 1,
                    "downloadId": "a",
                    "status": "queued",
                    "size": 0,
                    "errorMessage": None,
                },
                {
                    "id": 2,
                    "downloadId": "b",
                    "status": "queued",
                    "size": 1234,
                    "errorMessage": None,
                },
                {
                    "id": 3,
                    "downloadId": "c",
                    "status": "downloading",
                    "size": 0,
                    "errorMessage": None,
                },
            ],
            ["a"],
        ),
        # Enabled: an item matching BOTH the qBit message and size 0 is not duplicated.
        (
            True,
            [
                {
                    "id": 1,
                    "downloadId": "a",
                    "status": "queued",
                    "size": 0,
                    "errorMessage": "qBittorrent is downloading metadata",
                },
                {
                    "id": 2,
                    "downloadId": "b",
                    "status": "queued",
                    "size": 0,
                    "errorMessage": None,
                },
            ],
            ["a", "b"],
        ),
        # Enabled but no size key present (e.g. partial item): not matched.
        (
            True,
            [
                {"id": 1, "downloadId": "a", "status": "queued", "errorMessage": None},
            ],
            [],
        ),
    ],
)
async def test_find_affected_items_via_missing_size(
    detect_via_missing_size, queue_data, expected_download_ids
):
    # Arrange
    removal_job = shared_fix_affected_items(RemoveMetadataMissing, queue_data)
    removal_job.job = MagicMock(detect_via_missing_size=detect_via_missing_size)
    removal_job.queue_manager.get_queue_items = AsyncMock(
        return_value=[dict(item) for item in queue_data]
    )

    # Act and Assert
    await shared_test_affected_items(removal_job, expected_download_ids)


@pytest.mark.asyncio
async def test_run_detects_metadata_stuck_item_present_only_in_full_queue():
    removal_job = _metadata_missing_job()
    full_only_item = _metadata_queue_item()
    queues = {"normal": [], "full": [full_only_item]}
    removal_job.queue_manager.get_queue_items = AsyncMock(
        side_effect=lambda queue_scope: queues[queue_scope]
    )

    removed = await removal_job.run()

    assert removed == 1
    removal_job.queue_manager.get_queue_items.assert_awaited_once_with(
        queue_scope="full"
    )
    removal_job.arr.remove_queue_item.assert_awaited_once_with(
        queue_id=full_only_item["id"], blocklist=True, remove_from_client=True
    )


@pytest.mark.asyncio
async def test_run_still_detects_metadata_stuck_item_in_normal_queue():
    removal_job = _metadata_missing_job()
    normal_item = _metadata_queue_item(
        download_id="normal-metadata-stuck",
        queue_id=201,
        episodeId=42,
        seriesId=7,
    )
    _serve_api_queues(removal_job, normal=[normal_item], full=[normal_item])

    removed = await removal_job.run()

    assert removed == 1
    removal_job.arr.remove_queue_item.assert_awaited_once_with(
        queue_id=normal_item["id"], blocklist=True, remove_from_client=True
    )


@pytest.mark.asyncio
async def test_run_ignores_full_only_items_without_exact_status_and_error():
    removal_job = _metadata_missing_job()
    full_only_items = [
        _metadata_queue_item(
            download_id="wrong-status", queue_id=211, status="downloading"
        ),
        _metadata_queue_item(
            download_id="wrong-error",
            queue_id=212,
            errorMessage="Some other error",
        ),
        _metadata_queue_item(
            download_id="size-zero-only", queue_id=213, errorMessage=None
        ),
    ]
    _serve_api_queues(removal_job, normal=[], full=full_only_items)

    removed = await removal_job.run()

    assert removed == 0
    removal_job.arr.remove_queue_item.assert_not_awaited()


@pytest.mark.asyncio
async def test_run_keeps_ignored_client_and_protected_tag_downloads():
    removal_job = _metadata_missing_job(
        protected=["protected-download"],
        ignored_download_clients=["Ignored qBittorrent"],
    )
    ignored_item = _metadata_queue_item(
        download_id="ignored-download",
        queue_id=221,
        downloadClient="Ignored qBittorrent",
    )
    protected_item = _metadata_queue_item(
        download_id="protected-download", queue_id=222
    )
    removable_item = _metadata_queue_item(
        download_id="removable-download", queue_id=223
    )
    _serve_api_queues(
        removal_job,
        normal=[],
        full=[ignored_item, protected_item, removable_item],
    )

    removed = await removal_job.run()

    assert removed == 1
    removal_job.arr.remove_queue_item.assert_awaited_once_with(
        queue_id=removable_item["id"], blocklist=True, remove_from_client=True
    )
    assert removal_job.arr.tracker.deleted == [removable_item["downloadId"]]


@pytest.mark.asyncio
async def test_run_preserves_strikes_and_blocklist_for_full_only_item():
    removal_job = _metadata_missing_job(max_strikes=1)
    full_only_item = _metadata_queue_item(download_id="struck-download", queue_id=231)
    _serve_api_queues(removal_job, normal=[], full=[full_only_item])

    first_removed = await removal_job.run()

    assert first_removed == 0
    removal_job.arr.remove_queue_item.assert_not_awaited()
    assert (
        removal_job.arr.tracker.defective["remove_metadata_missing"][
            full_only_item["downloadId"]
        ]["strikes"]
        == 1
    )

    second_removed = await removal_job.run()

    assert second_removed == 1
    assert (
        removal_job.arr.tracker.defective["remove_metadata_missing"][
            full_only_item["downloadId"]
        ]["strikes"]
        == 2
    )
    removal_job.arr.remove_queue_item.assert_awaited_once_with(
        queue_id=full_only_item["id"], blocklist=True, remove_from_client=True
    )


@pytest.mark.asyncio
async def test_run_removes_duplicate_queue_rows_only_once():
    removal_job = _metadata_missing_job()
    first_row = _metadata_queue_item(download_id="duplicate-download", queue_id=241)
    second_row = _metadata_queue_item(download_id="duplicate-download", queue_id=242)
    _serve_api_queues(removal_job, normal=[], full=[first_row, second_row])

    removed = await removal_job.run()

    assert removed == 1
    removal_job.arr.remove_queue_item.assert_awaited_once_with(
        queue_id=first_row["id"], blocklist=True, remove_from_client=True
    )
    assert removal_job.arr.tracker.deleted == [first_row["downloadId"]]


@pytest.mark.asyncio
async def test_missing_size_opt_in_remains_limited_to_normal_queue():
    removal_job = _metadata_missing_job(detect_via_missing_size=True)
    full_only_size_zero = _metadata_queue_item(
        download_id="full-only-size-zero", queue_id=251, errorMessage=None
    )
    normal_size_zero = _metadata_queue_item(
        download_id="normal-size-zero",
        queue_id=252,
        errorMessage=None,
        episodeId=52,
        seriesId=8,
    )
    _serve_api_queues(
        removal_job,
        normal=[normal_size_zero],
        full=[full_only_size_zero, normal_size_zero],
    )

    removed = await removal_job.run()

    assert removed == 1
    removal_job.arr.remove_queue_item.assert_awaited_once_with(
        queue_id=normal_size_zero["id"], blocklist=True, remove_from_client=True
    )
    assert removal_job.arr.tracker.deleted == [normal_size_zero["downloadId"]]
