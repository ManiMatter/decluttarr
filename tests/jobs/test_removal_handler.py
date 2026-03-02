from unittest.mock import AsyncMock, MagicMock

import pytest

from src.jobs.removal_handler import RemovalHandler


@pytest.mark.parametrize(
    "qbittorrent_configured, is_private, client_type, protocol, expected",
    [
        (True, True, "qbittorrent", "torrent", "private_handling"),
        (True, False, "qbittorrent", "torrent", "public_handling"),
        (False, True, "qbittorrent", "torrent", "remove"),
        (False, False, "qbittorrent", "torrent", "remove"),
        (True, False, "transmission", "torrent", "remove"),  # unsupported client
        (True, False, "myusenetclient", "usenet", "remove"),  # unsupported protocol
    ],
)
@pytest.mark.asyncio
async def test_get_handling_method(
    qbittorrent_configured,
    is_private,
    client_type,
    protocol,
    expected,
):
    # Mock arr
    arr = AsyncMock()
    arr.tracker.private = ["A"] if is_private else []

    # Mock settings and get_download_client_by_name
    settings = MagicMock()
    settings.download_clients.qbittorrent = ["dummy"] if qbittorrent_configured else []

    # Simulate (client_name, client_type) return
    settings.download_clients.get_download_client_by_name.return_value = (
        "client_name",
        client_type,
    )

    settings.general.private_tracker_handling = "private_handling"
    settings.general.public_tracker_handling = "public_handling"

    handler = RemovalHandler(arr=arr, settings=settings, job_name="test")

    affected_download = {
        "downloadClient": "qBittorrent",
        "protocol": protocol,
    }

    result = await handler._get_handling_method(  # pylint: disable=W0212
        "A", affected_download
    )
    assert result == expected


def _make_tag_only_handler(*, deferred_arr_followup=True):
    arr = MagicMock()
    arr.tracker.private = []
    arr.tracker.deleted = []
    arr.remove_queue_item = AsyncMock(return_value=True)

    qbit_client = MagicMock()
    qbit_client.set_tag = AsyncMock()
    qbit_client.get_qbit_items = AsyncMock(return_value=[{"hash": "A"}])

    settings = MagicMock()
    settings.download_clients.qbittorrent = [qbit_client]
    settings.download_clients.get_download_client_by_name.return_value = (
        qbit_client,
        "qbittorrent",
    )
    settings.general.private_tracker_handling = "remove"
    settings.general.public_tracker_handling = "remove"
    settings.general.obsolete_tag = "Obsolete"

    settings.jobs.remove_orphans.action_mode = "tag_only"
    settings.jobs.remove_orphans.handoff_tag = "cleanup-ready"
    settings.jobs.remove_orphans.deferred_arr_followup = deferred_arr_followup
    settings.jobs.remove_orphans.followup_trigger = "on_download_removed"

    handler = RemovalHandler(arr=arr, settings=settings, job_name="remove_orphans")

    affected_downloads = {
        "A": {
            "downloadClient": "qBittorrent",
            "protocol": "torrent",
            "title": "Torrent A",
            "queue_ids": [11],
        }
    }
    return handler, arr, qbit_client, affected_downloads


@pytest.mark.asyncio
async def test_tag_only_handoff_waits_for_external_removal():
    handler, arr, qbit_client, affected_downloads = _make_tag_only_handler(
        deferred_arr_followup=True
    )
    qbit_client.get_qbit_items.return_value = [{"hash": "a"}]

    await handler.remove_downloads(affected_downloads, blocklist=True)

    qbit_client.set_tag.assert_awaited_once_with(tags=["cleanup-ready"], hashes=["A"])
    arr.remove_queue_item.assert_not_awaited()
    assert "A" in arr.tracker.deleted


@pytest.mark.asyncio
async def test_tag_only_handoff_triggers_followup_after_external_removal():
    handler, arr, qbit_client, affected_downloads = _make_tag_only_handler(
        deferred_arr_followup=True
    )
    qbit_client.get_qbit_items.return_value = []

    await handler.remove_downloads(affected_downloads, blocklist=False)

    qbit_client.set_tag.assert_awaited_once_with(tags=["cleanup-ready"], hashes=["A"])
    arr.remove_queue_item.assert_awaited_once_with(queue_id=11, blocklist=False)
    assert "A" in arr.tracker.deleted


@pytest.mark.asyncio
async def test_tag_only_handoff_skips_if_download_cannot_be_tagged():
    handler, arr, qbit_client, affected_downloads = _make_tag_only_handler(
        deferred_arr_followup=True
    )
    qbit_client.set_tag.reset_mock()
    settings = handler.settings
    settings.download_clients.get_download_client_by_name.return_value = (None, None)

    await handler.remove_downloads(affected_downloads, blocklist=False)

    qbit_client.set_tag.assert_not_awaited()
    arr.remove_queue_item.assert_not_awaited()
    assert "A" not in arr.tracker.deleted
