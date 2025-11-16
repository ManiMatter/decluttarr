# Cleans the download queue
from src.jobs.remove_bad_files import RemoveBadFiles
from src.jobs.remove_done_seeding import RemoveDoneSeeding
from src.jobs.remove_failed_downloads import RemoveFailedDownloads
from src.jobs.remove_failed_imports import RemoveFailedImports
from src.jobs.remove_metadata_missing import RemoveMetadataMissing
from src.jobs.remove_missing_files import RemoveMissingFiles
from src.jobs.remove_orphans import RemoveOrphans
from src.jobs.remove_slow import RemoveSlow
from src.jobs.remove_stalled import RemoveStalled
from src.jobs.remove_unmonitored import RemoveUnmonitored
from src.jobs.search_handler import SearchHandler
from src.settings._download_clients import DOWNLOAD_CLIENT_TYPES
from src.utils.log_setup import logger
from src.utils.queue_manager import QueueManager


class JobManager:
    arr = None

    def __init__(self, settings):
        self.settings = settings

    async def run_jobs(self, arr):
        self.arr = arr
        logger.info(f"*** Running jobs on {self.arr.name} ({self.arr.base_url}) ***")
        await self.removal_jobs()
        await self.search_jobs()

    async def run_download_client_jobs(self):
        """Run jobs that operate on download clients directly."""
        if not await self._download_clients_connected():
            return None

        items_detected = 0
        for download_client_type in DOWNLOAD_CLIENT_TYPES:
            download_clients = getattr(
                self.settings.download_clients,
                download_client_type,
                [],
            )

            for client in download_clients:
                # Get jobs for this client
                download_client_jobs = self._get_download_client_jobs_for_client(
                    client,
                    download_client_type,
                )

                if not any(job.job.enabled for job in download_client_jobs):
                    continue

                logger.info(
                    f"*** Running jobs on {client.name} ({client.base_url}) ***",
                )

                for download_client_job in download_client_jobs:
                    if download_client_job.job.enabled:
                        items_detected += await download_client_job.run()

        return items_detected

    async def removal_jobs(self):
        # Check removal jobs
        removal_jobs = self._get_removal_jobs()
        if not any(removal_job.job.enabled for removal_job in removal_jobs):
            logger.verbose("Removal Jobs: None triggered (No jobs active)")
            return

        if not await self._queue_has_items():
            return

        if not await self._download_clients_connected():
            return

        # Refresh trackers
        await self.arr.tracker.refresh_private_and_protected(self.settings)

        # Run Remval Jobs

        items_detected = 0
        for removal_job in removal_jobs:
            items_detected += await removal_job.run()

        if items_detected == 0:
            logger.verbose("Removal Jobs: All jobs passed (Queue is clean)")

    async def search_jobs(self):
        if (
            self.arr.arr_type == "whisparr"
        ):  # Whisparr does not support this endpoint (yet?)
            return

        if self.arr.jobs.search_missing.enabled:
            await SearchHandler(
                arr=self.arr,
                settings=self.settings,
                missing_or_cutoff="missing",
                job_name="search_missing",
            ).handle_search()

        if self.arr.jobs.search_unmet_cutoff.enabled:
            await SearchHandler(
                arr=self.arr,
                settings=self.settings,
                missing_or_cutoff="cutoff",
                job_name="search_cutoff_unmet",
            ).handle_search()

    async def _queue_has_items(self):
        logger.debug(
            "job_manager.py/_queue_has_items (Before any removal jobs): Checking if any items in full queue",
        )
        queue_manager = QueueManager(self.arr, self.settings)
        full_queue = await queue_manager.get_queue_items("full")
        if full_queue:
            logger.debug(
                "job_runner/full_queue at start: %s",
                queue_manager.format_queue(full_queue),
            )
            return True

        self.arr.tracker.reset()
        logger.verbose("Removal Jobs: None triggered (Queue is empty)")
        return False

    async def _download_clients_connected(self):
        for clients in [
            self.settings.download_clients.qbittorrent,
            self.settings.download_clients.sabnzbd,
        ]:
            if not await self._check_client_connection_status(clients):
                return False
        return True

    async def _check_client_connection_status(self, clients):
        for client in clients:
            logger.debug(
                f"job_manager.py/_check_client_connection_status: Checking if {client.name} is connected",
            )
            if not await client.check_connected():
                logger.warning(
                    f">>> {client.name} is disconnected. Skipping queue cleaning on {self.arr.name}.",
                )
                return False
        return True

    def _get_removal_jobs(self):
        """
        Return a list of enabled removal job instances based on the provided settings.

        Each job is included if the corresponding attribute exists and is truthy in
        instance-specific jobs (arr.jobs) or global settings.jobs.
        """
        removal_job_classes = {
            "remove_bad_files": RemoveBadFiles,
            "remove_failed_imports": RemoveFailedImports,
            "remove_failed_downloads": RemoveFailedDownloads,
            "remove_metadata_missing": RemoveMetadataMissing,
            "remove_missing_files": RemoveMissingFiles,
            "remove_orphans": RemoveOrphans,
            "remove_slow": RemoveSlow,
            "remove_stalled": RemoveStalled,
            "remove_unmonitored": RemoveUnmonitored,
        }

        jobs = []
        for removal_job_name, removal_job_class in removal_job_classes.items():
            if getattr(self.arr.jobs, removal_job_name, False):
                jobs.append(
                    removal_job_class(self.arr, self.settings, removal_job_name),
                )
        return jobs

    def _get_download_client_jobs_for_client(self, client, client_type):
        """
        Return a list of download client job instances for a specific download client.

        Each job is included if the corresponding attribute exists and is truthy in settings.jobs.
        """
        download_client_job_classes = {
            "remove_done_seeding": RemoveDoneSeeding,
        }

        jobs = []
        for job_name, job_class in download_client_job_classes.items():
            if getattr(self.settings.jobs, job_name, False):
                jobs.append(
                    job_class(
                        client,
                        client_type,
                        self.settings,
                        job_name,
                    ),
                )
        return jobs
