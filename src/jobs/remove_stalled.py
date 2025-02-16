import verboselogs

from src.utils.shared import (
    errorDetails,
    formattedQueueInfo,
    get_queue,
    execute_checks,
    qBitOffline,
)

logger = verboselogs.VerboseLogger(__name__)

async def remove_stalled(
    settingsDict,
    BASE_URL,
    API_KEY,
    NAME,
    deleted_downloads,
    defective_tracker,
    protectedDownloadIDs,
    privateDowloadIDs,
):
    # Detects stalled downloads and triggers deletion. Adds to blocklist.
    try:
        failType = "stalled"
        queue = await get_queue(BASE_URL, API_KEY, settingsDict)
        logger.debug("remove_stalled/queue IN: %s", formattedQueueInfo(queue))

        if not queue or await qBitOffline(settingsDict, failType, NAME):
            return 0

        # Find stalled downloads
        affectedItems = [
            item for item in queue
            if item.get("status") == "warning"
            and item.get("errorMessage") == "The download is stalled with no connections"
        ]

        if not affectedItems:
            return 0

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
            addToBlocklist=True,
            doPrivateTrackerCheck=True,
            doProtectedDownloadCheck=True,
            doPermittedAttemptsCheck=True,
        )

        return len(affectedItems)

    except Exception as error:
        errorDetails(NAME, error)
        return 0