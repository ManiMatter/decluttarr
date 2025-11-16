from abc import ABC, abstractmethod

from src.jobs.removal_handler import RemovalHandler
from src.jobs.strikes_handler import StrikesHandler
from src.utils.log_setup import logger
from src.utils.queue_manager import QueueManager


class RemovalJob(ABC):
    job_name = None
    blocklist = True
    queue_scope = None
    affected_items = None
    affected_downloads = None
    job = None
    max_strikes = None
    queue = []

    # Default class attributes (can be overridden in subclasses)
    def __init__(self, arr, settings, job_name) -> None:
        self.arr = arr
        self.settings = settings
        self.job_name = job_name
        self.job = getattr(self.arr.jobs, self.job_name)
        self.queue_manager = QueueManager(self.arr, self.settings)
        self.max_strikes = getattr(self.job, "max_strikes", None)
        if self.max_strikes:
            self.strikes_handler = StrikesHandler(
                job_name=self.job_name, arr=self.arr, max_strikes=self.max_strikes
            )

    async def run(self) -> int:
        if not self.job.enabled:
            return 0
        logger.debug(
            f"removal_job.py/run: Launching job '{self.job_name}', and checking if any items in queue (queue_scope='{self.queue_scope}')."
        )
        self.queue = await self.queue_manager.get_queue_items(
            queue_scope=self.queue_scope
        )

        # Handle empty queue
        if not self.queue:
            return 0

        self.affected_items = await self._find_affected_items()
        self.affected_downloads = self.queue_manager.group_by_download_id(
            self.affected_items
        )

        # -- Checks --
        self._ignore_protected()
        if self.max_strikes:
            self.affected_downloads = self.strikes_handler.filter_strike_exceeds(
                self.affected_downloads, self.queue
            )

        # -- Removal --
        await RemovalHandler(
            arr=self.arr,
            settings=self.settings,
            job_name=self.job_name,
        ).remove_downloads(self.affected_downloads, self.blocklist)

        return len(self.affected_downloads)

    def _ignore_protected(self):
        """
        Filter out downloads that are in the protected tracker.

        Directly updates self.affected_downloads.
        """
        self.affected_downloads = {
            download_id: queue_items
            for download_id, queue_items in self.affected_downloads.items()
            if download_id not in self.arr.tracker.protected
        }

    @abstractmethod  # Implemented on level of each removal job
    async def _find_affected_items(self) -> None:
        pass
