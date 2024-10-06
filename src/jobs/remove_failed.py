from src.utils.shared import (
    errorDetails,
    formattedQueueInfo,
    get_queue,
    privateTrackerCheck,
    protectedDownloadCheck,
    execute_checks,
    permittedAttemptsCheck,
    remove_download,
    qBitOffline,
)
import sys, os, traceback
import logging, verboselogs

logger = verboselogs.VerboseLogger(__name__)


async def remove_failed(
    settingsDict,
    BASE_URL,
    API_KEY,
    NAME,
    deleted_downloads,
    defective_tracker,
    protectedDownloadIDs,
    privateDowloadIDs,
):
    # Detects failed and triggers delete. Does not add to blocklist
    try:
        failType = "failed"
        queue = await get_queue(BASE_URL, API_KEY)
        logger.debug("remove_failed/queue IN: %s", formattedQueueInfo(queue))

        if not queue:
            return 0

        if await qBitOffline(settingsDict, failType, NAME):
            return 0
        # Find items affected
        affectedItems = []
        for queueItem in queue:
            if "errorMessage" in queueItem and "status" in queueItem:
                if queueItem["status"] == "failed":
                    affectedItems.append(queueItem)
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
