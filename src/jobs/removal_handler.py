from src.utils.log_setup import logger


class RemovalHandler:
    def __init__(self, arr, settings, job_name, event_bus=None):
        self.arr = arr
        self.settings = settings
        self.job_name = job_name
        self.event_bus = event_bus

    async def remove_downloads(self, affected_downloads, blocklist):
        for download_id in list(affected_downloads.keys()):

            affected_download = affected_downloads[download_id]
            handling_method = await self._get_handling_method(
                download_id, affected_download
            )

            if download_id in self.arr.tracker.deleted or handling_method == "skip":
                del affected_downloads[download_id]
                continue

            if handling_method == "remove":
                await self._remove_download(affected_download, download_id, blocklist)
            elif handling_method == "obsolete_tag":
                await self._tag_as_obsolete(affected_download, download_id)

            # Print out detailed removal messages (if any)
            if "removal_messages" in affected_download:
                for msg in affected_download["removal_messages"]:
                    logger.verbose(msg)

            self.arr.tracker.deleted.append(download_id)

            # Emit removal event
            if self.event_bus:
                from src.web.events import Event, EventType
                await self.event_bus.emit(Event(EventType.ITEM_REMOVED, {
                    "arr_name": self.arr.name,
                    "arr_type": self.arr.arr_type,
                    "job_name": self.job_name,
                    "download_id": download_id,
                    "title": affected_download.get("title", "Unknown"),
                    "handling_method": handling_method,
                    "test_run": self.settings.general.test_run,
                }))

    async def _remove_download(self, affected_download, download_id, blocklist):
        queue_id = affected_download["queue_ids"][0]
        logger.info(
            f"Job '{self.job_name}' triggered removal: {affected_download['title']}"
        )
        logger.debug(f"remove_handler.py/_remove_download: download_id={download_id}")
        await self.arr.remove_queue_item(queue_id=queue_id, blocklist=blocklist)

    async def _tag_as_obsolete(self, affected_download, download_id):
        logger.info(
            f"Job '{self.job_name}' triggered obsolete-tagging: {affected_download['title']}"
        )
        for qbit in self.settings.download_clients.qbittorrent:
            if not qbit.ready:
                continue
            await qbit.set_tag(
                tags=[self.settings.general.obsolete_tag], hashes=[download_id]
            )

    async def _get_handling_method(self, download_id, affected_download):
        if affected_download["protocol"] != "torrent":
            return "remove"  # handling is only implemented for torrent

        download_client_name = affected_download["downloadClient"]
        _, download_client_type = (
            self.settings.download_clients.get_download_client_by_name(
                download_client_name, ready_only=True
            )
        )

        if download_client_type != "qbittorrent":
            return "remove"  # handling is only implemented for qbit (and only if ready)

        if len(self.settings.download_clients.qbittorrent) == 0:
            return "remove"  # qbit not configured, thus can't tag

        if download_id in self.arr.tracker.private:
            return self.settings.general.private_tracker_handling

        return self.settings.general.public_tracker_handling
