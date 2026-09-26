from datetime import datetime, timedelta, timezone

import dateutil.parser

from src.utils.log_setup import logger
from src.utils.queue_manager import QueueManager
from src.utils.wanted_manager import WantedManager


class SearchHandler:
    def __init__(self, arr, settings, missing_or_cutoff, job_name):
        self.arr = arr
        self.settings = settings
        self.wanted_manager = WantedManager(self.arr, self.settings)
        self.missing_or_cutoff = missing_or_cutoff
        self._configure_search_target()
        self.job_name = job_name

    def _configure_search_target(self):
        logger.debug(
            f"search_handler.py/_configure_search_target: Setting job & search label ({self.missing_or_cutoff})"
        )
        if self.missing_or_cutoff == "missing":
            self.job = self.settings.jobs.search_missing
            self.search_target_label = f"missing {self.arr.detail_item_key}s"
        elif self.missing_or_cutoff == "cutoff":
            self.job = self.settings.jobs.search_unmet_cutoff
            self.search_target_label = f"{self.arr.detail_item_key}s with unmet cutoff"
        else:
            error = f"Unknown search type: {self.missing_or_cutoff}"
            raise ValueError(error)

    async def handle_search(self):
        logger.debug(
            f"search_handler.py/handle_search: Running '{self.missing_or_cutoff}' search"
        )

        logger.debug(
            f"search_handler.py/handle_search: Getting the list of wanted items ({self.missing_or_cutoff})"
        )
        wanted_items = await self._get_initial_wanted_items()
        if not wanted_items:
            return

        logger.debug(
            f"search_handler.py/handle_search: Getting list of queue items to only search for items that are not already downloading."
        )
        queue = await QueueManager(self.arr, self.settings).get_queue_items(
            queue_scope="normal",
        )
        wanted_items = self._filter_wanted_items(wanted_items, queue)
        if not wanted_items:
            return

        await self._log_items(wanted_items)
        logger.debug(
            f"search_handler.py/handle_search: Triggering search for wanted items ({self.missing_or_cutoff})"
        )
        await self._trigger_search(wanted_items)

    def _get_initial_wanted_items(self):
        wanted = self.wanted_manager.get_wanted_items(self.missing_or_cutoff)
        if not wanted:
            logger.verbose(
                f"Job '{self.job_name}' did not trigger a search: No {self.search_target_label}"
            )
        return wanted

    def _filter_wanted_items(self, items, queue):
        items = self._filter_already_downloading(items, queue)
        if not items:
            logger.verbose(
                f"Job '{self.job_name}' did not trigger a search: All {self.search_target_label} are already in the queue"
            )
            return []

        items = self._filter_recent_searches(items)
        if not items:
            logger.verbose(
                f"Job '{self.job_name}' did not trigger a search: All {self.search_target_label} were searched for in the last {self.job.min_days_between_searches} days"
            )
            return []

        return items[: self.job.max_concurrent_searches]

    def _filter_already_downloading(self, wanted_items, queue):
        queue_ids = {q["detail_item_id"] for q in queue}
        return [item for item in wanted_items if item["id"] not in queue_ids]

    async def _trigger_search(self, items):
        ids = [item["id"] for item in items]
        await self.wanted_manager.search_items(ids)

    def _filter_recent_searches(self, items):
        now = datetime.now(timezone.utc)
        result = []

        for item in items:
            last = item.get("lastSearchTime")
            if not last:
                item["lastSearchDateFormatted"] = "Never"
                item["daysSinceLastSearch"] = None
                result.append(item)
                continue

            last_time = dateutil.parser.isoparse(last)
            days_ago = (now - last_time).days

            if last_time + timedelta(days=self.job.min_days_between_searches) < now:
                item["lastSearchDateFormatted"] = last_time.strftime("%Y-%m-%d")
                item["daysSinceLastSearch"] = days_ago
                result.append(item)

        return result

    async def _log_items(self, items):
        logger.info(
            f"Job '{self.job_name}' triggered a search for {len(items)} {self.arr.detail_item_key}s"
        )
        for item in items:
            if self.arr.arr_type in ["radarr", "readarr", "lidarr"]:
                title = item.get("title", "Unknown")
                logger.verbose(f"- {title}")

            elif self.arr.arr_type in ("sonarr", "sportarr"):
                logger.debug(
                    "search_handler.py/_log_items: Getting series information for better display in output"
                )
                series = await self.arr.get_series()
                series_title = next(
                    (s["title"] for s in series if s["id"] == item.get("seriesId")),
                    "Unknown",
                )
                episode = item.get("episodeNumber", "00")
                season = item.get("seasonNumber", "00")
                season_numbering = f"S{int(season):02}/E{int(episode):02}"
                logger.verbose(f"- {series_title} ({season_numbering})")
