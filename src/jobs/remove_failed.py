import verboselogs

from src.utils.shared import (
    errorDetails,
    formattedQueueInfo,
    get_queue,
    execute_checks,
    qBitOffline,
)

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
        queue = await get_queue(BASE_URL, API_KEY, settingsDict)
        logger.debug("remove_failed/queue IN: %s", formattedQueueInfo(queue))

        if not queue or await qBitOffline(settingsDict, failType, NAME):
            return 0

        # Find items affected
        affectedItems = [
            item for item in queue if item.get("status") == failType and "errorMessage" in item
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
            addToBlocklist=False,
            doPrivateTrackerCheck=True,
            doProtectedDownloadCheck=True,
            doPermittedAttemptsCheck=False,
        )
        return len(affectedItems)

    except Exception as error:
        errorDetails(NAME, error)
        return 0
