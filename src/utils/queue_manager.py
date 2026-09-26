import logging
from typing import Union

from src.utils.common import extract_json_from_response, make_request
from src.utils.log_setup import logger


class QueueManager:
    def __init__(self, arr, settings):
        self.arr = arr
        self.settings = settings

    async def get_queue_items(self, queue_scope):
        """
        Retrieve queue items based on the scope.

        queue_scope:
            "normal" = normal queue
            "orphans" = orphaned queue items (in full queue but not in normal queue)
            "full" = full queue
        """
        logger.debug(
            "queue_manager.py/get_queue_items (%s): Refreshing and fetching queue",
            queue_scope,
        )

        await self._refresh_queue()

        if queue_scope == "normal":
            queue_items = await self._get_queue(full_queue=False)
        elif queue_scope == "orphans":
            full_queue = await self._get_queue(full_queue=True)
            normal_queue = await self._get_queue(full_queue=False)
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug(
                    f"queue_manager.py/get_queue_items (full) to determine orphans: Current queue ({len(full_queue)} items) = {self.format_queue(full_queue)}"
                )
                logger.debug(
                    f"queue_manager.py/get_queue_items (normal) to determine orphans: Current queue ({len(normal_queue)} items) = {self.format_queue(normal_queue)}"
                )
            # Compare by queue item id, not by whole record: the two fetches are separate
            # requests after a RefreshMonitoredDownloads, so sizeleft/timeleft of an active
            # download differ between them and a record comparison marks it as an orphan (#322)
            normal_ids = {nq.get("id") for nq in normal_queue}
            queue_items = [fq for fq in full_queue if fq.get("id") not in normal_ids]
        elif queue_scope == "full":
            queue_items = await self._get_queue(full_queue=True)
        else:
            error = f"Invalid queue_scope: {queue_scope}"
            raise ValueError(error)
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(
                f"queue_manager.py/get_queue_items ({queue_scope}): Current queue ({len(queue_items)} items) = {self.format_queue(queue_items)}"
            )
        return queue_items

    async def _get_queue(self, *, full_queue=False):
        # Step 1: Get the total number of records
        total_records_count = await self._get_total_records_count(full_queue)

        # Step 2: Get all records using `arr.full_queue_parameter`
        queue = await self._get_arr_records(full_queue, total_records_count)

        # Step 3: Filter the queue based on delayed items and ignored download clients
        queue = self._filter_out_ignored_statuses(queue)
        queue = self._filter_out_ignored_download_clients(queue)
        return self._add_detail_item_key(queue)

    def _add_detail_item_key(self, queue):
        """Normalize episodeID, bookID, etc. so it can just be called by 'detail_item_id'."""
        for items in queue:
            items["detail_item_id"] = items.get(self.arr.detail_item_id_key)
        return queue

    async def _refresh_queue(self):
        # Refresh the queue by making the POST request using an external make_request function
        logger.debug("queue_manager.py/_refresh_queue: Refreshing Queue")
        await make_request(
            method="POST",
            endpoint=f"{self.arr.api_url}/command",
            settings=self.settings,
            timeout=self.arr.timeout,
            json={"name": "RefreshMonitoredDownloads"},
            headers={"X-Api-Key": self.arr.api_key},
        )

    async def _get_total_records_count(self, full_queue):
        # Get the total number of records from the queue using `arr.full_queue_parameter`
        params = {self.arr.full_queue_parameter: full_queue}
        logger.debug(
            "queue_manager.py/_get_total_records_count: Getting Total Records Count"
        )
        total_records = await self.fetch_queue_field(params, key="totalRecords")
        return total_records

    async def _get_arr_records(self, full_queue, total_records_count):
        # Get all records based on the count (with pagination) using `arr.full_queue_parameter`
        if total_records_count == 0:
            return []

        params = {"page": "1", "pageSize": total_records_count}
        if full_queue:
            params |= {self.arr.full_queue_parameter: full_queue}

        logger.debug(
            f"queue_manager.py/_get_arr_records: Getting queue records ({total_records_count} items)"
        )
        records = await self.fetch_queue_field(params, key="records")
        return records

    async def fetch_queue_field(self, params, key: str | None = None):
        # Gets the response of the /queue endpoint and extracts a specific field from the json response
        response = await make_request(
            method="GET",
            endpoint=f"{self.arr.api_url}/queue",
            settings=self.settings,
            timeout=self.arr.timeout,
            params=params,
            headers={"X-Api-Key": self.arr.api_key},
        )
        return extract_json_from_response(response, key=key)

    def _filter_out_ignored_statuses(
        self, queue, ignored_statuses=("delay", "downloadClientUnavailable")
    ):
        """
        All matching items are removed from the queue. However, logging of ignored items
        is limited to one per (download title, protocol, indexer) combination to reduce log noise
        (since one download may be behind in multiple queue items)

        Args:
            queue (list[dict]): The queue to filter.
            ignored_statuses (tuple[str]): Status values to ignore.

        Returns:
            list[dict]: Filtered queue.
        """
        if queue is None:
            return None
        seen_combinations = set()
        filtered_queue = []

        for item in queue:
            status = item.get("status")
            title = item.get("title")
            protocol = item.get("protocol", "No protocol")
            indexer = item.get("indexer", "No indexer")
            combination = (title, protocol, indexer)

            if status in ignored_statuses:
                if combination not in seen_combinations:
                    seen_combinations.add(combination)
                    logger.debug(
                        f"queue_manager.py/_filter_out_ignored_statuses: Ignored queue item: {title} (Status: {status}, Protocol: {protocol}, Indexer: {indexer})"
                    )
                continue

            filtered_queue.append(item)

        return filtered_queue

    def _filter_out_ignored_download_clients(self, queue):
        # Filters out ignored download clients
        if queue is None:
            return queue
        filtered_queue = []

        for queue_item in queue:
            download_client = queue_item.get("downloadClient", "Unknown client")
            if download_client in self.settings.general.ignored_download_clients:
                logger.debug(
                    ">>> Queue item ignored due to ignored download client: %s (Download Client: %s)",
                    queue_item["title"],
                    download_client,
                )
            else:
                filtered_queue.append(queue_item)

        return filtered_queue

    def format_queue(self, queue_items) -> list | str:
        if not queue_items:
            return "empty"
        return self.group_by_download_id(queue_items)

    def group_by_download_id(self, queue_items):
        # Groups queue items by download ID and returns a dict where download ID is the key,
        # and the value is a dict with a list of IDs and other selected metadata.
        retain_keys = [
            "detail_item_id",
            "title",
            "size",
            "sizeleft",
            "downloadClient",
            "protocol",
            "status",
            "trackedDownloadState",
            "statusMessages",
            "removal_messages",
        ]

        grouped_dict = {}

        for queue_item in queue_items:
            download_id = queue_item.get("downloadId")
            item_id = queue_item.get("id")

            if download_id in grouped_dict:
                grouped_dict[download_id]["queue_ids"].append(item_id)
            else:
                grouped_dict[download_id] = {
                    "queue_ids": [item_id],
                    **{
                        key: queue_item[key] for key in retain_keys if key in queue_item
                    },
                }

        return grouped_dict

    @staticmethod
    def filter_queue(
        queue: list[dict],
        conditions: list[Union[str, tuple[str, str]]],
    ) -> list[dict]:
        """
        Filter queue items by status or (status, errorMessage) pairs.

        - If an entry in `conditions` is a string, only status is checked.
        - If it's a (status, errorMessage) tuple, both must match.
        """
        filtered_items = []
        for item in queue:
            item_status = item.get("status")
            item_error = item.get("errorMessage")

            for condition in conditions:
                if isinstance(condition, str):
                    if item_status == condition:
                        filtered_items.append(item)
                        break
                elif (
                    isinstance(condition, tuple)
                    and len(condition) == 2
                    and item_status == condition[0]
                    and item_error == condition[1]
                ):
                    filtered_items.append(item)
                    break
        return filtered_items

    @staticmethod
    def filter_missing_size(queue: list[dict]) -> list[dict]:
        """
        Return queued items whose size is not yet known (no metadata fetched).

        Unlike qBittorrent, clients such as Transmission or Deluge do not surface a
        "downloading metadata" message in the *arr queue, so a torrent stuck fetching
        metadata cannot be matched by message. Such items are reported by the *arr as
        status "queued" with size 0. This client-agnostic check catches them (see #57).

        The "size" key must be present so that incomplete items are not matched.
        """
        return [
            item
            for item in queue
            if item.get("status") == "queued" and "size" in item and not item["size"]
        ]
