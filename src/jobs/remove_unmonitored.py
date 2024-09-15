from src.utils.shared import (
    errorDetails,
    formattedQueueInfo,
    get_queue,
    privateTrackerCheck,
    protectedDownloadCheck,
    execute_checks,
    permittedAttemptsCheck,
    remove_download,
)
import sys, os, traceback
import logging, verboselogs

logger = verboselogs.VerboseLogger(__name__)
from src.utils.rest import rest_get


async def remove_unmonitored(
    settingsDict,
    BASE_URL,
    API_KEY,
    NAME,
    deleted_downloads,
    defective_tracker,
    protectedDownloadIDs,
    privateDowloadIDs,
    arr_type,
):
    # Removes downloads belonging to movies/tv shows that are not monitored. Does not add to blocklist
    try:
        failType = "unmonitored"
        queue = await get_queue(BASE_URL, API_KEY)
        logger.debug("remove_unmonitored/queue IN: %s", formattedQueueInfo(queue))
        if not queue:
            return 0
        # Find items affected
        monitoredDownloadIDs = []
        for queueItem in queue:
            if arr_type == "SONARR":
                isMonitored = (
                    await rest_get(
                        f'{BASE_URL}/episode/{str(queueItem["episodeId"])}', API_KEY
                    )
                )["monitored"]
            elif arr_type == "RADARR":
                isMonitored = (
                    await rest_get(
                        f'{BASE_URL}/movie/{str(queueItem["movieId"])}', API_KEY
                    )
                )["monitored"]
            elif arr_type == "LIDARR":
                isMonitored = (
                    await rest_get(
                        f'{BASE_URL}/album/{str(queueItem["albumId"])}', API_KEY
                    )
                )["monitored"]
            elif arr_type == "READARR":
                isMonitored = (
                    await rest_get(
                        f'{BASE_URL}/book/{str(queueItem["bookId"])}', API_KEY
                    )
                )["monitored"]
            elif arr_type == "WHISPARR":
                isMonitored = (
                    await rest_get(
                        f'{BASE_URL}/episode/{str(queueItem["episodeId"])}', API_KEY
                    )
                )["monitored"]
            if isMonitored:
                monitoredDownloadIDs.append(queueItem["downloadId"])

        affectedItems = []
        for queueItem in queue:
            if queueItem["downloadId"] not in monitoredDownloadIDs:
                affectedItems.append(
                    queueItem
                )  # One downloadID may be shared by multiple queueItems. Only removes it if ALL queueitems are unmonitored

        affectedItems = await execute_checks(
            settingsDict,
            affectedItems,
            failType,
            BASE_URL,
            API_KEY,
            NAME,
            deleted_downloads,
            defective_tracker,
            privateDowloadIDs,
            protectedDownloadIDs,
            addToBlocklist=False,
            doPrivateTrackerCheck=True,
            doProtectedDownloadCheck=True,
            doPermittedAttemptsCheck=False,
        )
        return len(affectedItems)
    except Exception as error:
        errorDetails(NAME, error)
        return 0
