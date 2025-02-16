import verboselogs

from src.utils.shared import (
    errorDetails,
    formattedQueueInfo,
    get_queue,
    execute_checks,
    qBitOffline,
)

logger = verboselogs.VerboseLogger(__name__)


async def remove_metadata_missing(
    settingsDict,
    BASE_URL,
    API_KEY,
    NAME,
    deleted_downloads,
    defective_tracker,
    protectedDownloadIDs,
    privateDowloadIDs,
):
    # Detects metadata download issues and triggers deletion. Adds to blocklist.
    try:
        failType = "missing metadata"
        queue = await get_queue(BASE_URL, API_KEY, settingsDict)
        logger.debug("remove_metadata_missing/queue IN: %s", formattedQueueInfo(queue))

        if not queue or await qBitOffline(settingsDict, failType, NAME):
            return 0

        # Find affected items
        affectedItems = [
            item for item in queue
            if item.get("status") == "queued"
            and item.get("errorMessage") == "qBittorrent is downloading metadata"
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