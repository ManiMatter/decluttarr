import requests

from src.jobs.removal_job import RemovalJob
from src.utils.log_setup import logger


class RemoveUnmonitored(RemovalJob):
    queue_scope = "normal"
    blocklist = False

    async def _find_affected_items(self):
        # First pass: Check if items are monitored
        monitored_download_ids = []
        for item in self.queue:
            detail_item_id = item["detail_item_id"]
            try:
                is_monitored = detail_item_id is None or await self.arr.is_monitored(
                    detail_item_id
                )
            except requests.exceptions.HTTPError as err:
                response = getattr(err, "response", None)
                if response is None or response.status_code != 404:  # noqa: PLR2004
                    raise
                logger.warning(
                    "Skipping stale queue item %s: %s %s no longer exists on %s.",
                    item.get("downloadId"),
                    self.arr.detail_item_key,
                    detail_item_id,
                    self.arr.name,
                )
                is_monitored = True

            if is_monitored:
                # When queue item has been matched to artist (for instance in lidarr) but not yet to the detail (eg. album), then detail key is logically missing.
                # Thus we can't check if the item is monitored yet
                monitored_download_ids.append(item["downloadId"])

        # Second pass: Append queue items none that depends on download id is monitored
        affected_items = []
        for queue_item in self.queue:
            if queue_item["downloadId"] not in monitored_download_ids:
                affected_items.append(
                    queue_item
                )  # One downloadID may be shared by multiple queue_items. Only removes it if ALL queueitems are unmonitored
        return affected_items
