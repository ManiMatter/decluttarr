from pathlib import Path

from src.jobs.removal_job import RemovalJob
from src.utils.log_setup import logger

# fmt: off
STANDARD_EXTENSIONS = [
    # Movies, TV Shows (Radarr, Sonarr, Whisparr)
    ".webm", ".m4v", ".3gp", ".nsv", ".ty", ".strm", ".rm", ".rmvb", ".m3u", ".ifo", ".mov", ".qt", ".divx", ".xvid", ".bivx", ".nrg", ".pva", ".wmv", ".asf", ".asx", ".ogm", ".ogv", ".m2v", ".avi", ".bin", ".dat", ".dvr-ms", ".mpg", ".mpeg", ".mp4", ".avc", ".vp3", ".svq3", ".nuv", ".viv", ".dv", ".fli", ".flv", ".wpl", ".img", ".iso", ".vob", ".mkv", ".mk3d", ".ts", ".wtv", ".m2ts",
    # Subs (Radarr, Sonarr, Whisparr)
    ".sub", ".srt", ".idx", "vtt",
    # Audio (Lidarr, Readarr)
    ".aac", ".aif", ".aiff", ".aifc", ".ape", ".flac", ".mp2", ".mp3", ".m4a", ".m4b", ".m4p", ".mp4a", ".oga", ".ogg", ".opus", ".vorbis", ".wma", ".wav", ".wv", "wavepack",
    # Text (Readarr)
    ".epub", ".kepub", ".mobi", ".azw3", ".pdf",
]

# Archives can be handled by tools such as unpackerr:
ARCHIVE_EXTENSIONS = [
    ".rar", ".tar", ".tgz", ".gz", ".zip", ".7z", ".bz2", ".tbz2", ".iso",
]

BAD_KEYWORDS = ["Sample", "Trailer"]
BAD_KEYWORD_LIMIT = 500 # Megabyte; do not remove items larger than that
# fmt: on


class RemoveBadFiles(RemovalJob):
    queue_scope = "normal"
    blocklist = True

    async def _find_affected_items(self):
        # Get in-scope download IDs
        result = self._group_download_ids_by_client()

        affected_items = []
        for download_client, info in result.items():
            download_client_type = info["download_client_type"]
            download_ids = info["download_ids"]

            if download_client_type == "qbittorrent":
                client_items = await self._handle_qbit(download_client, download_ids)
                affected_items.extend(client_items)
            elif download_client_type == "sabnzbd":
                # SABnzbd doesn't support bad file removal in the same way as BitTorrent
                # Usenet doesn't have the concept of "availability" or individual file selection
                continue
        return affected_items

    def _group_download_ids_by_client(self):
        """
        Group all relevant download IDs by download client.

        Limited to qbittorrent currently, as no other download clients implemented
        """
        result = {}

        for item in self.queue:
            download_client_name = item.get("downloadClient")
            if not download_client_name:
                continue

            download_client, download_client_type = (
                self.settings.download_clients.get_download_client_by_name(
                    download_client_name, ready_only=True
                )
            )
            if not download_client or not download_client_type:
                continue

            # Skip non-qBittorrent clients for now
            if download_client_type != "qbittorrent":
                continue

            result.setdefault(
                download_client,
                {
                    "download_client_type": download_client_type,
                    "download_ids": set(),
                },
            )["download_ids"].add(item["downloadId"])

        return result

    async def _handle_qbit(self, qbit_client, hashes):
        """Handle qBittorrent-specific logic for marking files as 'Do Not Download'."""
        affected_items = []
        qbit_items = await qbit_client.get_qbit_items(hashes=hashes)

        for qbit_item in self._get_items_to_process(qbit_items):

            self.arr.tracker.extension_checked.append(qbit_item["hash"])

            if (
                qbit_item["hash"].upper() in self.arr.tracker.protected
            ):  # Do not stop files in protected torrents
                continue

            torrent_files = await self._get_active_files(qbit_client, qbit_item["hash"])
            stoppable_files = self._get_stoppable_files(torrent_files)

            if not stoppable_files:
                continue

            await self._mark_files_as_stopped(
                qbit_client, qbit_item["hash"], stoppable_files
            )
            self._log_stopped_files(stoppable_files, qbit_item["name"])

            if self._all_files_stopped(torrent_files, stoppable_files):
                logger.verbose(
                    ">>> All files in this torrent have been marked as 'Do not Download'.  Removing torrent."
                )
                affected_items.extend(self._match_queue_items(qbit_item["hash"]))

        return affected_items

    # -- Helper functions for qbit handling --
    def _get_items_to_process(self, qbit_items):
        """
        Return only downloads that have metadata, are supposedly downloading.

        This is to prevent the case where a download has metadata but is not actually downloading.
        Additionally, each download should be checked at least once (for bad extensions), and thereafter only if availability drops to less than 100%
        """
        return [
            item
            for item in qbit_items
            if (
                item.get("has_metadata")
                and item["state"] in {"downloading", "forcedDL", "stalledDL"}
                and (
                    item["hash"] not in self.arr.tracker.extension_checked
                    or item["availability"] < 1
                )
            )
        ]

    @staticmethod
    async def _get_active_files(qbit_client, torrent_hash) -> list[dict]:
        """Return only files from the torrent that are still set to download, with file extension and name."""
        files = await qbit_client.get_torrent_files(
            torrent_hash
        )  # Await the async method
        return [
            {
                **f,  # Include all original file properties
                "file_name": Path(
                    f["name"]
                ).name,  # Add proper filename (without folder)
                "file_extension": Path(
                    f["name"]
                ).suffix,  # Add file_extension (e.g., .mp3)
            }
            for f in files
            if f["priority"] > 0
        ]

    def _log_stopped_files(self, stopped_files, torrent_name) -> None:
        logger.verbose(
            f"Job '{self.job_name}' stopped downloading {len(stopped_files)} file{'s' if len(stopped_files) != 1 else ''} in: {torrent_name}",
        )

        for file, reasons in stopped_files:
            logger.verbose(f"- {file['file_name']} ({' & '.join(reasons)})")

    def _get_stoppable_files(self, torrent_files):
        """Return files that can be marked as 'Do not Download' based on specific conditions."""
        stoppable_files = []

        for file in torrent_files:
            # If the file has metadata and its priority is greater than 0, we can check it
            if file["priority"] > 0:
                reasons = []

                # Check for bad extension
                if self._is_bad_extension(file):
                    reasons.append(f"Bad extension: {file['file_extension']}")

                # Check for bad keywords
                if self._contains_bad_keyword(file):
                    reasons.append("Contains bad keyword in path")

                # Check if the file has low availability
                if self._is_complete_partial(file):
                    reasons.append(
                        f"Low availability: {file['availability'] * 100:.1f}%"
                    )

                # Only add to stoppable_files if there are reasons to stop the file
                if reasons:
                    stoppable_files.append((file, reasons))

        return stoppable_files

    def _is_bad_extension(self, file) -> bool:
        """Check if the file has a bad extension."""
        return file["file_extension"].lower() not in self.get_good_extensions()

    def get_good_extensions(self):
        good_extensions = list(STANDARD_EXTENSIONS)
        if self.job.keep_archives:
            good_extensions += ARCHIVE_EXTENSIONS
        return good_extensions

    def _contains_bad_keyword(self, file):
        """Check if the file path contains a bad keyword and is smaller than the limit."""
        file_path = file.get("name", "").lower()
        file_size_mb = file.get("size", 0) / 1024 / 1024

        return (
            any(keyword.lower() in file_path for keyword in BAD_KEYWORDS)
            and file_size_mb <= BAD_KEYWORD_LIMIT
        )

    @staticmethod
    def _is_complete_partial(file) -> bool:
        """Check if the availability is less than 100% and the file is not fully downloaded."""
        return file["availability"] < 1 and file["progress"] != 1

    async def _mark_files_as_stopped(self, qbit_client, torrent_hash, stoppable_files):
        """Mark specific files as 'Do Not Download' in qBittorrent."""
        for file, _ in stoppable_files:
            await qbit_client.set_torrent_file_priority(torrent_hash, file["index"], 0)

    @staticmethod
    def _all_files_stopped(torrent_files, stoppable_files) -> bool:
        """Check if all files are either stopped (priority 0) or in the stoppable files list."""
        stoppable_file_indexes = {file[0]["index"] for file in stoppable_files}
        return all(
            f["priority"] == 0 or f["index"] in stoppable_file_indexes
            for f in torrent_files
        )

    def _match_queue_items(self, download_hash) -> list:
        """Find matching queue item(s) by downloadId (uppercase)."""
        return [
            item
            for item in self.queue
            if item["downloadId"].upper() == download_hash.upper()
        ]
