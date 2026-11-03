# pylint: disable=W0212
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.deletion_handler.download_remover import DownloadRemover

HASH = "ABC123"


def make_remover(
    tmp_path,
    *,
    existing_files,
    tags="",
    test_run=False,
    private=False,
    private_handling="remove",
    public_handling="remove",
):
    existing = []
    for name in existing_files:
        path = tmp_path / name
        path.write_text("x")
        existing.append(str(path))

    qbit = MagicMock()
    qbit.name = "qBittorrent"
    qbit.ready = True
    qbit.get_qbit_items = AsyncMock(
        return_value=[
            {"hash": HASH.lower(), "name": "Pack", "tags": tags, "private": private}
        ]
    )
    qbit.remove_download = AsyncMock()
    qbit.set_tag = AsyncMock()

    arr = MagicMock()
    arr.settings.download_clients.qbittorrent = [qbit]
    arr.settings.general.protected_tag = "Keep"
    arr.settings.general.test_run = test_run
    arr.settings.general.obsolete_tag = "Obsolete"
    arr.settings.general.private_tracker_handling = private_handling
    arr.settings.general.public_tracker_handling = public_handling
    arr.tracker.private = []
    arr.get_import_history = AsyncMock(
        return_value=[(1, HASH, "2026-01-01", None), (2, HASH, "2026-01-01", None)]
    )
    # Paths known by the arr: media 1 was deleted from disk, media 2 exists if any file does
    arr.get_media_file_paths = AsyncMock(
        return_value={
            1: str(tmp_path / "deleted.mkv"),
            2: existing[0] if existing else str(tmp_path / "deleted2.mkv"),
        }
    )
    return DownloadRemover(arr), qbit


ITEM = {"id": 7, "title": "Show"}


@pytest.mark.asyncio
async def test_removes_when_all_media_gone(tmp_path):
    remover, qbit = make_remover(tmp_path, existing_files=[])
    await remover.remove_for_item(ITEM)
    qbit.remove_download.assert_awaited_once()
    assert qbit.remove_download.await_args.args[0].upper() == HASH


@pytest.mark.asyncio
async def test_keeps_season_pack_while_other_episode_exists(tmp_path):
    remover, qbit = make_remover(tmp_path, existing_files=["s01e02.mkv"])
    await remover.remove_for_item(ITEM)
    qbit.remove_download.assert_not_awaited()


@pytest.mark.asyncio
async def test_keeps_protected_torrent(tmp_path):
    remover, qbit = make_remover(tmp_path, existing_files=[], tags="foo, Keep")
    await remover.remove_for_item(ITEM)
    qbit.remove_download.assert_not_awaited()


@pytest.mark.asyncio
async def test_keeps_when_no_imports_in_history(tmp_path):
    remover, qbit = make_remover(tmp_path, existing_files=[])
    remover.arr.get_import_history = AsyncMock(return_value=[])
    await remover.remove_for_item(ITEM)
    qbit.remove_download.assert_not_awaited()


@pytest.mark.asyncio
async def test_errors_do_not_propagate(tmp_path):
    remover, _ = make_remover(tmp_path, existing_files=[])
    remover.arr.get_import_history = AsyncMock(side_effect=RuntimeError("boom"))
    await remover.remove_for_item(ITEM)


@pytest.mark.asyncio
async def test_removes_superseded_torrent_even_though_upgrade_file_exists(tmp_path):
    remover, qbit = make_remover(tmp_path, existing_files=["2160p.mkv"])
    remover.arr.get_import_history = AsyncMock(
        return_value=[(1, HASH, "2026-01-01", None), (1, "NEWHASH", "2026-02-01", None)]
    )
    await remover.remove_for_item(ITEM)
    qbit.remove_download.assert_awaited_once()


@pytest.mark.asyncio
async def test_keeps_current_torrent_of_upgraded_media(tmp_path):
    remover, qbit = make_remover(tmp_path, existing_files=["2160p.mkv"])
    remover.arr.get_import_history = AsyncMock(
        return_value=[(1, "OLDHASH", "2026-01-01", None), (1, HASH, "2026-02-01", None)]
    )
    remover.arr.get_media_file_paths = AsyncMock(
        return_value={1: str(tmp_path / "2160p.mkv")}
    )
    await remover.remove_for_item(ITEM)
    qbit.remove_download.assert_not_awaited()


@pytest.mark.asyncio
async def test_keeps_pack_when_later_import_has_no_download_id(tmp_path):
    remover, qbit = make_remover(tmp_path, existing_files=["s04e05.mkv"])
    remover.arr.get_import_history = AsyncMock(
        return_value=[(1, HASH, "2026-01-01", None), (2, HASH, "2026-01-01", None), (2, None, "2026-02-01", None)]
    )
    await remover.remove_for_item(ITEM)
    qbit.remove_download.assert_not_awaited()


@pytest.mark.asyncio
async def test_skips_download_unrelated_to_deleted_files(tmp_path):
    remover, qbit = make_remover(tmp_path, existing_files=[])
    remover.arr.get_import_history = AsyncMock(return_value=[(3, HASH, "2026-01-01", None)])
    remover.arr.get_media_file_paths = AsyncMock(
        return_value={3: str(tmp_path / "s02e01.mkv")}
    )
    await remover.remove_for_item(ITEM, deleted_paths={str(tmp_path / "s01e01.mkv")})
    qbit.remove_download.assert_not_awaited()
    remover.arr.get_media_file_paths.assert_awaited_once()


@pytest.mark.asyncio
async def test_checks_download_related_to_deleted_files(tmp_path):
    remover, qbit = make_remover(tmp_path, existing_files=[])
    await remover.remove_for_item(
        ITEM, deleted_paths={str(tmp_path / "deleted.mkv"), str(tmp_path / "deleted2.mkv")}
    )
    qbit.remove_download.assert_awaited_once()


@pytest.mark.asyncio
async def test_matches_manually_imported_pack_by_source_path(tmp_path):
    remover, qbit = make_remover(tmp_path, existing_files=[])
    qbit.get_qbit_items.return_value = [
        {"hash": HASH.lower(), "name": "Show.S01.1080p", "tags": ""}
    ]
    source = "/downloads/complete/Show.S01.1080p/Show.S01E01.mkv"
    remover.arr.get_import_history = AsyncMock(
        return_value=[(1, None, "2026-01-01", source), (2, None, "2026-01-01", source)]
    )
    await remover.remove_for_item(ITEM)
    qbit.remove_download.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("handling", ["skip", "remove_from_queue"])
async def test_keeps_private_torrent_when_handling_does_not_remove(tmp_path, handling):
    remover, qbit = make_remover(
        tmp_path, existing_files=[], private=True, private_handling=handling
    )
    await remover.remove_for_item(ITEM)
    qbit.remove_download.assert_not_awaited()
    qbit.set_tag.assert_not_awaited()


@pytest.mark.asyncio
async def test_tags_private_torrent_as_obsolete_instead_of_removing(tmp_path):
    remover, qbit = make_remover(
        tmp_path, existing_files=[], private=True, private_handling="obsolete_tag"
    )
    await remover.remove_for_item(ITEM)
    qbit.remove_download.assert_not_awaited()
    qbit.set_tag.assert_awaited_once_with(tags=["Obsolete"], hashes=[HASH.lower()])


@pytest.mark.asyncio
async def test_does_not_retag_already_obsolete_torrent(tmp_path):
    remover, qbit = make_remover(
        tmp_path,
        existing_files=[],
        tags="Obsolete",
        private=True,
        private_handling="obsolete_tag",
    )
    await remover.remove_for_item(ITEM)
    qbit.set_tag.assert_not_awaited()


@pytest.mark.asyncio
async def test_removes_private_torrent_when_handling_is_remove(tmp_path):
    remover, qbit = make_remover(
        tmp_path, existing_files=[], private=True, private_handling="remove", public_handling="skip"
    )
    await remover.remove_for_item(ITEM)
    qbit.remove_download.assert_awaited_once()


@pytest.mark.asyncio
async def test_public_torrent_uses_public_handling(tmp_path):
    remover, qbit = make_remover(
        tmp_path, existing_files=[], private=False, private_handling="remove", public_handling="skip"
    )
    await remover.remove_for_item(ITEM)
    qbit.remove_download.assert_not_awaited()


@pytest.mark.asyncio
async def test_private_status_falls_back_to_tracker_list(tmp_path):
    remover, qbit = make_remover(
        tmp_path, existing_files=[], private=False, private_handling="skip"
    )
    remover.arr.tracker.private = [HASH.upper()]
    await remover.remove_for_item(ITEM)
    qbit.remove_download.assert_not_awaited()
