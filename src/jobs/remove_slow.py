from src.jobs.removal_job import RemovalJob
from src.utils.log_setup import logger

DISABLE_OVER_BANDWIDTH_USAGE = 0.8


class RemoveSlow(RemovalJob):
    queue_scope = "normal"
    blocklist = True

    async def _find_affected_items(self):
        affected_items = []
        checked_ids = set()

        # Refreshes bandwidth usage for each client
        await self.add_download_client_to_queue_items()
        await self.update_bandwidth_usage()

        for item in self.queue:

            # Already checked downloadId -> skip
            if self._checked_before(item, checked_ids):
                continue

            # Keys not present -> skip
            if self._missing_keys(item):
                continue

            # Not Downloading -> skip
            if self._not_downloading(item):
                continue

            # Completed but stuck -> skip
            if self._is_completed_but_stuck(item):
                logger.info(
                    f">>> '{self.job_name}' detected download marked as slow as well as completed. Files most likely in process of being moved. Not removing: {item['title']}",
                )
                continue

            # High bandwidth usage -> skip
            if self._high_bandwidth_usage(item):
                continue

            downloaded, previous, increment, speed = await self._get_progress_stats(
                item
            )

            # Not slow -> skip
            if self._not_slow(speed):
                continue

            # None of above, hence truly slow
            affected_items.append(item)
            logger.debug(
                f'remove_slow/slow speed detected: {item["title"]} '
                f"(Speed: {speed} KB/s, KB now: {downloaded}, KB previous: {previous}, "
                f"Diff: {increment}, In Minutes: {self.settings.general.timer})",
            )

        return affected_items

    @staticmethod
    def _checked_before(item, checked_ids):
        download_id = item.get("downloadId", "None")
        if download_id in checked_ids:
            return True  # One downloadId may occur in multiple items - only check once for all of them per iteration
        checked_ids.add(download_id)
        return False

    @staticmethod
    def _missing_keys(item) -> bool:
        required_keys = {
            "downloadId",
            "size",
            "sizeleft",
            "status",
            "protocol",
            "download_client",
            "download_client_type",
        }
        return not required_keys.issubset(item)

    @staticmethod
    def _not_downloading(item) -> bool:
        return item.get("status") != "downloading"

    @staticmethod
    def _is_completed_but_stuck(item) -> bool:
        return item["size"] > 0 and item["sizeleft"] == 0

    def _not_slow(self, speed):
        return speed is None or speed >= self.job.min_speed

    async def _get_progress_stats(self, item):
        download_id = item["downloadId"]

        download_progress = await self._get_download_progress(item, download_id)
        previous_progress, increment, speed = self._compute_increment_and_speed(
            download_id,
            download_progress,
        )

        # For SABnzbd, use calculated speed from API data
        if item["download_client_type"] == "sabnzbd":
            try:
                api_speed = await item["download_client"].get_item_download_speed(
                    download_id
                )
                if api_speed is not None:
                    speed = api_speed
                    logger.debug(f"SABnzbd API speed for {item['title']}: {speed} KB/s")
            except Exception as e:  # noqa: BLE001
                logger.debug(f"SABnzbd get_item_download_speed failed: {e}")
        self.arr.tracker.download_progress[download_id] = download_progress
        return download_progress, previous_progress, increment, speed

    async def _get_download_progress(self, item, download_id):
        # Grabs the progress from qbit or SABnzbd if possible, else calculates it based on progress (imprecise)
        if item["download_client_type"] == "qbittorrent":
            try:
                progress = await item["download_client"].fetch_download_progress(
                    download_id
                )
                if progress is not None:
                    return progress
            except Exception:  # noqa: BLE001
                pass  # fall back below
        elif item["download_client_type"] == "sabnzbd":
            try:
                progress = await item["download_client"].fetch_download_progress(
                    download_id
                )
                if progress is not None:
                    return progress
            except Exception:  # noqa: BLE001
                pass  # fall back below
        return item["size"] - item["sizeleft"]

    def _compute_increment_and_speed(self, download_id, current_progress):
        # Calculates the increment based on progress since last check
        previous_progress = self.arr.tracker.download_progress.get(download_id)
        if previous_progress is not None:
            increment = current_progress - previous_progress
            speed = round(increment / 1000 / (self.settings.general.timer * 60), 1)
        else:
            # don't calculate a speed delta the first time a download comes up as it may not have done a full cycle
            increment = speed = None
        return previous_progress, increment, speed

    def _high_bandwidth_usage(self, item):
        download_id = item["downloadId"]
        download_client = item["download_client"]
        download_client_type = item["download_client_type"]

        self.strikes_handler.unpause_entry(download_id)

        if download_client_type == "qbittorrent":
            if download_client.bandwidth_usage > DISABLE_OVER_BANDWIDTH_USAGE:
                self.strikes_handler.pause_entry(download_id, "High Bandwidth Usage")
                return True
        # SABnzbd: Bandwidth checking isn't applicable to usenet usage

        return False

    async def add_download_client_to_queue_items(self):
        # Adds the download client to the queue item
        for item in self.queue:
            download_client_name = item["downloadClient"]
            download_client, download_client_type = (
                self.settings.download_clients.get_download_client_by_name(
                    download_client_name, ready_only=True
                )
            )
            item["download_client"] = download_client
            item["download_client_type"] = download_client_type

    async def update_bandwidth_usage(self):
        # Refreshes the current bandwidth usage for each client
        processed_clients = set()

        for item in self.queue:
            download_client = item["download_client"]
            if item["download_client"] in processed_clients:
                continue
            if item["download_client_type"] == "qbittorrent":
                await download_client.set_bandwidth_usage()
            # SABnzbd: Since bandwith checking isn't applicable, setting bandwidth usage is irrelevant
            processed_clients.add(item["download_client"])
