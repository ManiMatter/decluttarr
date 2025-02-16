# Cleans the download queue
import sys
import verboselogs

logger = verboselogs.VerboseLogger(__name__)
from src.utils.shared import errorDetails, get_queue
from src.jobs.remove_failed import remove_failed
from src.jobs.remove_failed_imports import remove_failed_imports
from src.jobs.remove_metadata_missing import remove_metadata_missing
from src.jobs.remove_missing_files import remove_missing_files
from src.jobs.remove_orphans import remove_orphans
from src.jobs.remove_slow import remove_slow
from src.jobs.remove_stalled import remove_stalled
from src.jobs.remove_unmonitored import remove_unmonitored
from src.jobs.run_periodic_rescans import run_periodic_rescans
from src.utils.trackers import Deleted_Downloads

async def queuecleaner(
    settingsDict,
    arr_type,
    defective_tracker,
    download_sizes_tracker,
    protectedDownloadIDs,
    privateDowloadIDs,
):
    ARR_SETTINGS = {
        "RADARR": ("RADARR_URL", "RADARR_KEY", "RADARR_NAME", "includeUnknownMovieItems"),
        "SONARR": ("SONARR_URL", "SONARR_KEY", "SONARR_NAME", "includeUnknownSeriesItems"),
        "LIDARR": ("LIDARR_URL", "LIDARR_KEY", "LIDARR_NAME", "includeUnknownArtistItems"),
        "READARR": ("READARR_URL", "READARR_KEY", "READARR_NAME", "includeUnknownAuthorItems"),
        "WHISPARR": ("WHISPARR_URL", "WHISPARR_KEY", "WHISPARR_NAME", "includeUnknownSeriesItems"),
    }

    # Retrieve settings based on arr_type(instance)
    try:
        url_key, api_key, name_key, full_queue_param = ARR_SETTINGS[arr_type]
        BASE_URL = settingsDict[url_key]
        API_KEY = settingsDict[api_key]
        NAME = settingsDict[name_key]
    except KeyError:
        logger.error("Unknown arr_type specified, exiting: %s", str(arr_type))
        sys.exit()

    # Cleans up the downloads queue
    logger.verbose("Cleaning queue on %s:", NAME)
    # Refresh queue:
    try:
        full_queue = await get_queue(BASE_URL, API_KEY, settingsDict, params={full_queue_param: True})
        if full_queue:
            logger.debug("queueCleaner/full_queue at start:")
            logger.debug(full_queue)

            deleted_downloads = Deleted_Downloads([])
            items_detected = 0

            # Mapping removal functions to their corresponding settings keys
            removal_tasks = {
                "REMOVE_FAILED": remove_failed,
                "REMOVE_FAILED_IMPORTS": remove_failed_imports,
                "REMOVE_METADATA_MISSING": remove_metadata_missing,
                "REMOVE_MISSING_FILES": remove_missing_files,
                "REMOVE_ORPHANS": remove_orphans,
                "REMOVE_SLOW": remove_slow,
                "REMOVE_STALLED": remove_stalled,
                "REMOVE_UNMONITORED": remove_unmonitored,
            }

            # Common arguments for all functions
            common_args = (
                settingsDict,
                BASE_URL,
                API_KEY,
                NAME,
                deleted_downloads,
                defective_tracker,
                protectedDownloadIDs,
                privateDowloadIDs,
            )

            # Iterate over the mapping and call functions dynamically
            for key, func in removal_tasks.items():
                if settingsDict.get(key):
                    extra_args = ()

                    # Additional arguments for specific functions
                    if key == "REMOVE_ORPHANS":
                        extra_args = (full_queue_param,)
                    elif key == "REMOVE_SLOW":
                        extra_args = (download_sizes_tracker,)
                    elif key == "REMOVE_UNMONITORED":
                        extra_args = (arr_type,)

                    items_detected += await func(*common_args, *extra_args)

            if items_detected == 0:
                logger.verbose(">>> Queue is clean.")
        else:
            logger.verbose(">>> Queue is empty.")

        # Run periodic rescans if enabled
        if settingsDict.get("RUN_PERIODIC_RESCANS"):
            await run_periodic_rescans(settingsDict, BASE_URL, API_KEY, NAME, arr_type)

    except Exception as error:
        errorDetails(NAME, error)