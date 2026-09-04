from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import requests

from src.job_manager import JobManager
from src.jobs.removal_handler import RemovalHandler
from src.settings._instances import Tracker
from src.utils.queue_manager import QueueManager


@pytest.mark.asyncio
async def test_run_jobs_keeps_running_when_one_group_raises_request_error():
    settings = MagicMock()
    manager = JobManager(settings)
    arr = MagicMock()
    arr.name = "Sonarr"
    arr.base_url = "http://sonarr:8989"

    with (
        patch.object(
            manager,
            "removal_jobs",
            AsyncMock(side_effect=requests.exceptions.ReadTimeout("timed out")),
        ),
        patch.object(manager, "search_jobs", AsyncMock()) as search_jobs,
    ):
        await manager.run_jobs(arr)

    search_jobs.assert_awaited_once()


@pytest.mark.asyncio
async def test_run_download_client_jobs_handles_per_job_request_errors():
    settings = MagicMock()
    client = MagicMock()
    client.name = "qBittorrent"
    client.base_url = "http://qbittorrent:8080"
    settings.download_clients.qbittorrent = [client]
    settings.download_clients.sabnzbd = []

    manager = JobManager(settings)
    failing_job = MagicMock()
    failing_job.job.enabled = True
    failing_job.job_name = "remove_done_seeding"
    failing_job.run = AsyncMock(
        side_effect=requests.exceptions.ReadTimeout("timed out")
    )

    with (
        patch.object(
            manager, "_download_clients_connected", AsyncMock(return_value=True)
        ),
        patch.object(
            manager,
            "_get_download_client_jobs_for_client",
            MagicMock(return_value=[failing_job]),
        ),
    ):
        result = await manager.run_download_client_jobs()

    assert result == 0
    failing_job.run.assert_awaited_once()


@pytest.mark.asyncio
async def test_run_download_client_jobs_handles_connection_check_request_errors():
    settings = MagicMock()
    settings.download_clients.qbittorrent = []
    settings.download_clients.sabnzbd = []
    manager = JobManager(settings)

    with patch.object(
        manager,
        "_download_clients_connected",
        AsyncMock(side_effect=requests.exceptions.ReadTimeout("timed out")),
    ):
        result = await manager.run_download_client_jobs()

    assert result is None


def _job_manager_with_deleted(deleted):
    manager = JobManager(MagicMock())
    manager.arr = MagicMock()
    manager.arr.tracker = Tracker()
    manager.arr.tracker.deleted.extend(deleted)
    return manager


def _queue_item(download_id, queue_id=1):
    return {
        "id": queue_id,
        "downloadId": download_id,
        "title": "Some.Release",
        "protocol": "torrent",
        "downloadClient": "qBittorrent",
    }


@pytest.mark.asyncio
async def test_queue_has_items_forgets_deleted_downloads_that_are_back_in_queue():
    """A removal that did not stick must not block all future removals.

    The deleted tracker is otherwise only cleared once the queue is empty, so a
    download that keeps coming back would be silently skipped by RemovalHandler
    forever (strikes keep counting up, but no removal is ever triggered).
    """
    # Arrange
    manager = _job_manager_with_deleted(["still-in-queue", "actually-removed"])

    get_queue_items = AsyncMock(return_value=[_queue_item("still-in-queue")])

    # Act
    with patch.object(QueueManager, "get_queue_items", get_queue_items):
        has_items = await manager._queue_has_items()  # pylint: disable=W0212

    # Assert
    assert has_items is True
    assert manager.arr.tracker.deleted == ["actually-removed"]
    # The orphans job that triggered this bug only shows up in the full queue
    get_queue_items.assert_awaited_once_with("full")


@pytest.mark.asyncio
async def test_forgotten_download_is_removed_again_on_the_next_run():
    """After being forgotten, the download is removed instead of silently skipped."""
    # Arrange
    manager = _job_manager_with_deleted(["comes-back"])
    manager.settings.general.public_tracker_handling = "remove"
    manager.settings.download_clients.qbittorrent = []
    manager.settings.download_clients.get_download_client_by_name.return_value = (
        None,
        None,
    )
    manager.arr.remove_queue_item = AsyncMock()
    queue_item = _queue_item("comes-back", queue_id=42)

    # Act
    with patch.object(
        QueueManager, "get_queue_items", AsyncMock(return_value=[queue_item])
    ):
        await manager._queue_has_items()  # pylint: disable=W0212
    await RemovalHandler(
        arr=manager.arr,
        settings=manager.settings,
        job_name="remove_metadata_missing",
    ).remove_downloads(
        {"comes-back": {**queue_item, "queue_ids": [queue_item["id"]]}},
        blocklist=True,
    )

    # Assert
    manager.arr.remove_queue_item.assert_awaited_once_with(queue_id=42, blocklist=True)


@pytest.mark.asyncio
async def test_queue_has_items_keeps_deleted_downloads_that_are_gone():
    """Downloads that really were removed stay in the tracker (no double removal)."""
    # Arrange
    manager = _job_manager_with_deleted(["actually-removed"])

    # Act
    with patch.object(
        QueueManager,
        "get_queue_items",
        AsyncMock(return_value=[_queue_item("something-else")]),
    ):
        has_items = await manager._queue_has_items()  # pylint: disable=W0212

    # Assert
    assert has_items is True
    assert manager.arr.tracker.deleted == ["actually-removed"]


@pytest.mark.asyncio
async def test_obsolete_tagged_download_is_not_tagged_again_on_the_next_run():
    """Obsolete-tagged downloads stay in the queue by design and must not be re-tagged.

    With private_tracker_handling/public_tracker_handling set to "obsolete_tag",
    the download is tagged instead of removed and deliberately remains in the
    queue, so its presence is not evidence of a failed removal.
    """
    # Arrange
    manager = _job_manager_with_deleted([])
    manager.settings.general.public_tracker_handling = "obsolete_tag"
    manager.settings.general.obsolete_tag = "Obsolete"
    qbit = MagicMock(ready=True, set_tag=AsyncMock())
    manager.settings.download_clients.qbittorrent = [qbit]
    manager.settings.download_clients.get_download_client_by_name.return_value = (
        qbit,
        "qbittorrent",
    )
    queue_item = _queue_item("tagged", queue_id=7)

    # Act
    for _ in range(2):
        with patch.object(
            QueueManager, "get_queue_items", AsyncMock(return_value=[queue_item])
        ):
            await manager._queue_has_items()  # pylint: disable=W0212
        await RemovalHandler(
            arr=manager.arr,
            settings=manager.settings,
            job_name="remove_stalled",
        ).remove_downloads(
            {"tagged": {**queue_item, "queue_ids": [queue_item["id"]]}},
            blocklist=False,
        )

    # Assert
    qbit.set_tag.assert_awaited_once_with(tags=["Obsolete"], hashes=["tagged"])
    manager.arr.remove_queue_item.assert_not_called()
