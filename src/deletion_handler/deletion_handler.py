import asyncio
from collections import defaultdict
from pathlib import Path

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from src.utils.log_setup import logger


class DeletionHandler(FileSystemEventHandler):
    def __init__(self, arr, loop):
        super().__init__()
        self.arr = arr
        self.deleted_files = set()  # store deleted file paths
        self._process_task = None
        self._lock = asyncio.Lock()
        self.delay = 5  # Group deletes into 5 second badges
        self.loop = loop

    def on_deleted(self, event):
        if event.is_directory:
            return

        deleted_file = event.src_path
        asyncio.run_coroutine_threadsafe(self._queue_delete(deleted_file), self.loop)

    async def _queue_delete(self, deleted_file):
        async with self._lock:
            self.deleted_files.add(deleted_file)
            if self._process_task is None or self._process_task.done():
                # Schedule batch processing 5 seconds from now
                self._process_task = asyncio.create_task(
                    self._process_deletes_after_delay()
                )

    async def _process_deletes_after_delay(self):
        """Retrieve all files that were deleted, wait a few seconds, and then handle the parent folders"""
        await asyncio.sleep(self.delay)
        async with self._lock:
            # Copy and clear the deleted files set
            files_to_process = self.deleted_files.copy()
            logger.debug(
                f"deletion_handler.py/_process_deletes_after_delay: Deleted files: {' '.join(files_to_process)}"
            )
            for handler in logger.handlers:
                handler.flush()
            self.deleted_files.clear()

        # Extract parent folder paths, deduplicate them
        deletions = self._group_deletions_by_folder(files_to_process)
        logger.debug(
            f"deletion_handler.py/_process_deletes_after_delay: Folders with deletes: {' '.join(deletions.keys())}"
        )

        await self._handle_folders(deletions)

    @staticmethod
    def _group_deletions_by_folder(files_to_process):
        deletions = defaultdict(list)
        for f in files_to_process:
            deletions[str(Path(f).parent)].append(Path(f).name)
        return dict(deletions)

    async def _handle_folders(self, deletions):
        """Async handle folder paths: lookup item IDs and log results."""
        for folder_path, files in deletions.items():
            refresh_item = await self.arr.get_refresh_item_by_path(folder_path)
            if refresh_item:
                logger.info(
                    f"Job 'detect_deletions' triggered media refresh on {self.arr.name} ({self.arr.base_url}): {refresh_item['title']}"
                )
                await self.arr.refresh_item(refresh_item["id"])
            else:
                logger.verbose(
                    f"Job 'detect_deletions' detected a deleted file, but couldn't find a corresponding media item on {self.arr.name} ({self.arr.base_url})"
                )
            logger.verbose(f"Deleted Files:")
            for file in files:
                logger.verbose(f"- {Path(folder_path) / file}")

    async def await_completion(self):
        # For pytests to know when background task has finsished
        if self._process_task:
            await self._process_task


class WatcherManager:
    # Checks which folders are set up on arr and sets a watcher on them for deletes
    def __init__(self, settings):
        self.settings = settings
        self.observers = []
        self.handlers = []
        self.loop = None

    async def setup(self):
        self.loop = asyncio.get_running_loop()
        folders_to_watch = await self.get_folders_to_watch()
        for arr, folder_path in folders_to_watch:
            self.set_watcher(arr, folder_path)

    async def setup_for_arr(self, arr):
        """Set up deletion watchers for a single arr (e.g. one that rejoined after a degraded startup)."""
        if self.loop is None:
            self.loop = asyncio.get_running_loop()
        for folder_path in await self.get_folders_to_watch_for_arr(arr):
            self.set_watcher(arr, folder_path)

    async def get_folders_to_watch(self):
        """Gets from all arrs the root folders and lists those that are accessible for the arr, and have present for decluttarr."""
        folders_to_watch = []
        logger.verbose("")
        logger.verbose("*** Setting up monitoring for deletions ***")
        for arr in self.settings.instances:
            for folder_path in await self.get_folders_to_watch_for_arr(arr):
                folders_to_watch.append((arr, folder_path))

        return folders_to_watch

    async def get_folders_to_watch_for_arr(self, arr):
        """Root folder paths of one arr that are accessible for both the arr and decluttarr."""
        folders_to_watch = []
        if arr.arr_type not in (
            "sonarr",
            "sportarr",
            "radarr",
        ):  # only working for sonarr / radarr for now
            return folders_to_watch
        if not arr.ready:  # degraded instance; watchers are added when it rejoins
            return folders_to_watch
        root_folders = await arr.get_root_folders()

        for folder in root_folders:
            if folder.get("accessible") and "path" in folder:
                path = Path(folder["path"])
                if path.exists():
                    folders_to_watch.append(folder["path"])
                else:
                    logger.warning(
                        f"Job 'detect_deletions' on {arr.name} ({arr.base_url}) does not have access to this path and will not monitor it: '{path}'"
                    )
                    logger.info(
                        ">>> 💡 Tip: Make sure that the paths in decluttarr and in your arr instance are identical."
                    )
                    if self.settings.envs.in_docker:
                        logger.info(
                            ">>> 💡 Tip: Make sure decluttarr and your arr instance have the same mount points"
                        )

        return folders_to_watch

    def set_watcher(self, arr, folder_to_watch):
        """Adds a file deletion watcher for the specified folder and arr instance, creating an event handler to process deletion events and an observer to monitor the filesystem; starts the observer and stores both the handler and observer for later management"""
        event_handler = DeletionHandler(arr, self.loop)
        observer = Observer()
        observer.schedule(event_handler, folder_to_watch, recursive=True)
        observer.start()
        self.handlers.append(event_handler)
        logger.verbose(
            f"Job 'detect_deletions' started monitoring folder on {arr.name} ({arr.base_url}): {folder_to_watch}"
        )
        self.observers.append(observer)

    def stop(self):
        for observer in self.observers:
            observer.stop()
            observer.join()
