"""Removes stalled downloads."""

import time

from src.jobs.removal_job import RemovalJob
from src.utils.log_setup import logger

SECONDS_PER_DAY = 86400


class RemoveStalled(RemovalJob):
    queue_scope = "normal"
    blocklist = True

    async def _find_affected_items(self):
        conditions = [("warning", "The download is stalled with no connections")]
        affected_items = self.queue_manager.filter_queue(self.queue, conditions)
        if self.job.min_days_stalled:
            affected_items = await self._ignore_recently_active(affected_items)
        return affected_items

    async def _ignore_recently_active(self, affected_items):
        """
        Drop qBittorrent downloads that transferred data less than min_days_stalled ago.

        The age is read from qBittorrent's 'last_activity' on every run, so unlike the
        strike counter it survives a restart of decluttarr. qBittorrent counts uploads
        as activity as well, and measures a torrent that never transferred anything from
        when it was added. Downloads from other clients, or that the client does not
        know about, are not spared.

        Spared downloads keep their strikes (tracking is paused), and only start
        collecting further strikes once they are old enough.
        """
        cutoff = time.time() - self.job.min_days_stalled * SECONDS_PER_DAY
        last_activity = await self._get_last_activity(affected_items)

        removable = []
        for item in affected_items:
            download_id = item["downloadId"]
            active_at = last_activity.get(download_id.upper())
            if active_at and active_at > cutoff:
                logger.debug(
                    "remove_stalled.py/_ignore_recently_active: Not flagging %s, last active %.1f days ago (min_days_stalled: %s)",
                    item["title"],
                    (time.time() - active_at) / SECONDS_PER_DAY,
                    self.job.min_days_stalled,
                )
                if self.max_strikes:
                    self.strikes_handler.pause_entry(
                        download_id, "Active within min_days_stalled"
                    )
                continue
            if self.max_strikes:
                self.strikes_handler.unpause_entry(download_id)
            removable.append(item)
        return removable

    async def _get_last_activity(self, affected_items):
        """Map the upper-cased hash of each qBittorrent download to when it last transferred data."""
        download_clients = {}
        download_ids = {}
        for item in affected_items:
            download_client, _ = (
                self.settings.download_clients.get_download_client_by_name(
                    item["downloadClient"],
                    download_client_type="qbittorrent",
                    ready_only=True,
                )
            )
            if download_client:
                download_clients[download_client.name] = download_client
                download_ids.setdefault(download_client.name, []).append(
                    item["downloadId"]
                )

        last_activity = {}
        for name, download_client in download_clients.items():
            for torrent in await download_client.get_qbit_items(hashes=download_ids[name]):
                last_activity[torrent["hash"].upper()] = (
                    torrent.get("last_activity") or torrent.get("added_on")
                )
        return last_activity
