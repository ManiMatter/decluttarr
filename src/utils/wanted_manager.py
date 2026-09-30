from src.utils.common import extract_json_from_response, make_request


class WantedManager:
    def __init__(self, arr, settings):
        self.arr = arr
        self.settings = settings

    async def get_wanted_items(self, missing_or_cutoff):
        """
        Retrieve wanted items.

        missing_or_cutoff: Drives whether missing or cutoff items are retrieved
        """
        total_records_count = await self._get_total_records_count(missing_or_cutoff)
        return await self._get_arr_records(missing_or_cutoff, total_records_count)

    async def _get_total_records_count(self, missing_or_cutoff: str) -> int:
        total_records = await self.fetch_wanted_field(
            missing_or_cutoff, key="totalRecords"
        )
        return total_records

    async def _get_arr_records(self, missing_or_cutoff, total_records_count):
        # Get all records based on the count (with pagination)
        if total_records_count == 0:
            return []

        sort_key = f"{self.arr.detail_item_key}s.lastSearchTime"
        params = {"page": "1", "pageSize": total_records_count, "sortKey": sort_key}

        records = await self.fetch_wanted_field(
            missing_or_cutoff, params=params, key="records"
        )
        return records

    async def fetch_wanted_field(
        self, missing_or_cutoff: str, params: dict | None = None, key: str | None = None
    ):
        # Gets the response of the /queue endpoint and extracts a specific field from the json response
        response = await make_request(
            method="GET",
            endpoint=f"{self.arr.api_url}/wanted/{missing_or_cutoff}",
            settings=self.settings,
            timeout=self.arr.timeout,
            params=params,
            headers={"X-Api-Key": self.arr.api_key},
        )
        return extract_json_from_response(response, key=key)

    async def search_items(self, detail_ids):
        """Search items by detail IDs."""
        if isinstance(detail_ids, str):
            detail_ids = [detail_ids]

        json = {
            "name": self.arr.detail_item_search_command,
            self.arr.detail_item_ids_key: detail_ids,
        }
        await make_request(
            method="POST",
            endpoint=f"{self.arr.api_url}/command",
            settings=self.settings,
            timeout=self.arr.timeout,
            json=json,
            headers={"X-Api-Key": self.arr.api_key},
        )
