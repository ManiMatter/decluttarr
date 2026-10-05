from pathlib import Path

from src.utils.log_setup import logger


class DownloadRemover:
    """
    Removes the qBittorrent torrents that belong to a movie/series whose files were deleted.

    The torrent hash is the `downloadId` stored in the arr history, so no name matching is needed.
    Only media whose latest import came from a torrent depend on it (upgraded media no longer do).
    A torrent is removed if none of its dependent media (e.g. all episodes of a season pack) has a file on disk.
    """

    def __init__(self, arr):
        self.arr = arr
        self.settings = arr.settings

    async def remove_for_item(self, item, deleted_paths=None):
        """
        Remove torrents no longer needed by any media on disk; never raises, so the refresh can proceed.

        If deleted_paths is given, torrents whose media is untouched by those deletions are skipped
        (e.g. other seasons of the same series). Torrents without any dependent media (fully superseded) are always checked.
        """
        try:
            imports = await self.arr.get_import_history(item["id"])
            torrents, imports = await self._find_torrents(imports)
            logger.debug(
                f"download_remover.py/remove_for_item: {len(torrents)} torrents in qBittorrent behind the imports of '{item.get('title')}'"
            )
            if not torrents:
                logger.verbose(
                    f"Job 'detect_deletions' found no qBittorrent torrent behind the imports of '{item.get('title')}'"
                )
                return
            media_paths = await self.arr.get_media_file_paths(
                {media_id for media_id, _, _ in imports}
            )
            for download_id, (qbit, torrent) in torrents.items():
                dependent_media = self._dependent_media(imports, download_id)
                if (
                    deleted_paths is not None
                    and dependent_media
                    and not any(media_paths.get(m) in deleted_paths for m in dependent_media)
                ):
                    continue
                logger.debug(
                    f"download_remover.py/remove_for_item: '{torrent['name']}' has dependent media {sorted(dependent_media)}"
                )
                await self._remove_if_unused(
                    item, dependent_media, media_paths, qbit, torrent
                )
        except Exception as e:  # noqa: BLE001
            logger.warning(
                f"Job 'detect_deletions' could not remove downloads of '{item.get('title')}': {e}"
            )

    @staticmethod
    def _dependent_media(imports, download_id):
        """Media imported from the download, minus those later replaced by an import from another download."""
        wanted = download_id.upper()
        media = set()
        for media_id, imported_from, _ in imports:  # oldest first
            if imported_from and imported_from.upper() == wanted:
                media.add(media_id)
            elif imported_from:
                media.discard(media_id)
        return media

    async def _find_torrents(self, imports):
        """
        Find the torrents behind the imports.

        Returns ({hash: (qbit client, torrent)}, imports as (media_id, hash, date)). Imports done without a
        download id (manual imports) are matched by their source path: inside the torrent's content path,
        or having the torrent name as a path component (arr and qBittorrent may map paths differently).
        """
        available = {}
        for qbit in self.settings.download_clients.qbittorrent:
            if not qbit.ready:
                continue
            for torrent in await qbit.get_qbit_items():
                available.setdefault(torrent["hash"].upper(), (qbit, torrent))

        def match_by_path(source_path):
            if not source_path:
                return None
            source = Path(source_path)
            for torrent_hash, (_, torrent) in available.items():
                content_path = torrent.get("content_path")
                if (content_path and source.is_relative_to(content_path)) or torrent.get(
                    "name"
                ) in source.parts:
                    return torrent_hash
            return None

        resolved = [
            (
                media_id,
                download_id.upper() if download_id else match_by_path(source_path),
                date,
            )
            for media_id, download_id, date, source_path in imports
        ]
        found = {
            torrent_hash: available[torrent_hash]
            for torrent_hash in {key for _, key, _ in resolved if key}
            if torrent_hash in available
        }
        return found, resolved

    async def _remove_if_unused(self, item, dependent_media, media_paths, qbit, torrent):
        protected_tag = self.settings.general.protected_tag
        tags = [tag.strip() for tag in torrent.get("tags", "").split(",")]
        if protected_tag in tags:
            logger.verbose(
                f"Job 'detect_deletions' keeps '{torrent['name']}' on {qbit.name}: it has the protected tag"
            )
            return

        if self._is_still_in_use(dependent_media, media_paths):
            logger.verbose(
                f"Job 'detect_deletions' keeps '{torrent['name']}' on {qbit.name}: other media from this download still exist"
            )
            return

        prefix = "[Test Run] " if self.settings.general.test_run else ""
        handling = self._handling_method(torrent)
        if handling == "obsolete_tag":
            obsolete_tag = self.settings.general.obsolete_tag
            if obsolete_tag not in tags:
                logger.info(
                    f"{prefix}Job 'detect_deletions' tags '{torrent['name']}' on {qbit.name} as obsolete (related media deleted: {item['title']})"
                )
                await qbit.set_tag(tags=[obsolete_tag], hashes=[torrent["hash"]])
            return
        if handling != "remove":  # skip, or remove_from_queue (which leaves the torrent untouched)
            logger.verbose(
                f"Job 'detect_deletions' keeps '{torrent['name']}' on {qbit.name}: tracker handling is '{handling}'"
            )
            return

        logger.info(
            f"{prefix}Job 'detect_deletions' removes '{torrent['name']}' from {qbit.name} (related media deleted: {item['title']})"
        )
        await qbit.remove_download(torrent["hash"], delete_files=True)

    def _handling_method(self, torrent):
        """Same private/public tracker handling that the removal jobs apply."""
        general = self.settings.general
        is_private = bool(torrent.get("private")) or (
            torrent["hash"].upper() in self.arr.tracker.private
        )
        handling = (
            general.private_tracker_handling
            if is_private
            else general.public_tracker_handling
        )
        return handling or "remove"

    @staticmethod
    def _is_still_in_use(dependent_media, media_paths):
        return any(
            Path(media_paths[media_id]).exists()
            for media_id in dependent_media
            if media_id in media_paths
        )
