from src.utils.log_setup import logger

VALID_ACTION_MODES = {"remove", "skip", "tag_only"}
VALID_FOLLOWUP_TRIGGERS = {"on_download_removed"}


class RemovalHandler:
    def __init__(self, arr, settings, job_name):
        self.arr = arr
        self.settings = settings
        self.job_name = job_name
        self.job = getattr(self.settings.jobs, self.job_name)

    async def remove_downloads(self, affected_downloads, blocklist):
        action_mode = self._get_action_mode()
        deferred_arr_followup = self._is_deferred_arr_followup()
        followup_trigger = self._get_followup_trigger()
        handoff_tag = self._get_handoff_tag()

        for download_id in list(affected_downloads.keys()):

            affected_download = affected_downloads[download_id]
            tracker_handling_method = await self._get_handling_method(
                download_id, affected_download
            )
            handling_method = self._resolve_effective_handling_method(
                action_mode, tracker_handling_method
            )

            if download_id in self.arr.tracker.deleted or handling_method == "skip":
                del affected_downloads[download_id]
                continue

            if handling_method == "remove":
                await self._remove_download(affected_download, download_id, blocklist)
            elif handling_method == "obsolete_tag":
                await self._tag_as_obsolete(affected_download, download_id)
            elif handling_method == "tag_only":
                if not self._supports_tag_handoff(affected_download):
                    logger.warning(
                        "Job '%s' configured with action_mode='tag_only' but this download cannot be tagged for handoff "
                        "(protocol/client unsupported or missing qBittorrent mapping). Skipping download: %s",
                        self.job_name,
                        affected_download.get("title", download_id),
                    )
                    del affected_downloads[download_id]
                    continue

                await self._tag_with_custom_tag(
                    affected_download,
                    download_id,
                    handoff_tag,
                )

                if deferred_arr_followup and followup_trigger == "on_download_removed":
                    if await self._download_exists_in_client(download_id, affected_download):
                        logger.debug(
                            "Job '%s' deferred ARR follow-up pending removal from download client: %s",
                            self.job_name,
                            affected_download.get("title", download_id),
                        )
                    else:
                        logger.info(
                            "Job '%s' detected handoff-tagged download removed from client; triggering deferred ARR follow-up: %s",
                            self.job_name,
                            affected_download.get("title", download_id),
                        )
                        await self._remove_download(
                            affected_download,
                            download_id,
                            blocklist,
                        )

            # Print out detailed removal messages (if any)
            if "removal_messages" in affected_download:
                for msg in affected_download["removal_messages"]:
                    logger.verbose(msg)

            self.arr.tracker.deleted.append(download_id)

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
            await qbit.set_tag(
                tags=[self.settings.general.obsolete_tag], hashes=[download_id]
            )

    async def _tag_with_custom_tag(self, affected_download, download_id, handoff_tag):
        logger.info(
            "Job '%s' triggered handoff-tagging: %s (tag: %s)",
            self.job_name,
            affected_download.get("title", download_id),
            handoff_tag,
        )
        qbit_client, _ = self.settings.download_clients.get_download_client_by_name(
            affected_download["downloadClient"],
            download_client_type="qbittorrent",
        )
        if qbit_client is None:
            # this should not happen due _supports_tag_handoff guard, but keep defensive behavior
            return
        await qbit_client.set_tag(tags=[handoff_tag], hashes=[download_id])

    async def _get_handling_method(self, download_id, affected_download):
        if affected_download["protocol"] != "torrent":
            return "remove"  # handling is only implemented for torrent

        download_client_name = affected_download["downloadClient"]
        _, download_client_type = (
            self.settings.download_clients.get_download_client_by_name(
                download_client_name
            )
        )

        if download_client_type != "qbittorrent":
            return "remove"  # handling is only implemented for qbit

        if len(self.settings.download_clients.qbittorrent) == 0:
            return "remove"  # qbit not configured, thus can't tag

        if download_id in self.arr.tracker.private:
            return self.settings.general.private_tracker_handling

        return self.settings.general.public_tracker_handling

    def _resolve_effective_handling_method(self, action_mode, tracker_handling_method):
        if action_mode == "remove":
            return tracker_handling_method
        if action_mode == "skip":
            return "skip"
        if action_mode == "tag_only":
            return "tag_only"
        return tracker_handling_method

    def _get_action_mode(self):
        action_mode = getattr(self.job, "action_mode", "remove")
        if action_mode not in VALID_ACTION_MODES:
            logger.error(
                "Invalid action_mode '%s' for job '%s'. Falling back to 'remove'.",
                action_mode,
                self.job_name,
            )
            return "remove"
        return action_mode

    def _get_handoff_tag(self):
        handoff_tag = getattr(self.job, "handoff_tag", "")
        if handoff_tag:
            return handoff_tag
        return self.settings.general.obsolete_tag

    def _is_deferred_arr_followup(self):
        return bool(getattr(self.job, "deferred_arr_followup", False))

    def _get_followup_trigger(self):
        followup_trigger = getattr(self.job, "followup_trigger", "on_download_removed")
        if followup_trigger not in VALID_FOLLOWUP_TRIGGERS:
            logger.error(
                "Invalid followup_trigger '%s' for job '%s'. Falling back to 'on_download_removed'.",
                followup_trigger,
                self.job_name,
            )
            return "on_download_removed"
        return followup_trigger

    def _supports_tag_handoff(self, affected_download):
        if affected_download.get("protocol") != "torrent":
            return False
        if len(self.settings.download_clients.qbittorrent) == 0:
            return False
        qbit_client, client_type = (
            self.settings.download_clients.get_download_client_by_name(
                affected_download["downloadClient"],
                download_client_type="qbittorrent",
            )
        )
        return qbit_client is not None and client_type == "qbittorrent"

    async def _download_exists_in_client(self, download_id, affected_download):
        qbit_client, _ = self.settings.download_clients.get_download_client_by_name(
            affected_download["downloadClient"],
            download_client_type="qbittorrent",
        )
        if qbit_client is None:
            return False
        qbit_items = await qbit_client.get_qbit_items(download_id)
        return len(qbit_items) > 0
