import verboselogs

from src.utils.shared import (
    errorDetails,
    formattedQueueInfo,
    get_queue,
    execute_checks
)

logger = verboselogs.VerboseLogger(__name__)

async def remove_orphans(
    settingsDict,
    BASE_URL,
    API_KEY,
    NAME,
    deleted_downloads,
    defective_tracker,
    protectedDownloadIDs,
    privateDowloadIDs,
    full_queue_param,
):
    # Removes downloads belonging to deleted movies/TV shows. Does not add to blocklist.
    try:
        failType = "orphan"
        full_queue = await get_queue(BASE_URL, API_KEY, settingsDict, params={full_queue_param: True})
        queue = await get_queue(BASE_URL, API_KEY, settingsDict)

        logger.debug("remove_orphans/full queue IN: %s", formattedQueueInfo(full_queue))

        if not full_queue:
            return 0

        logger.debug("remove_orphans/queue IN: %s", formattedQueueInfo(queue))

        # Get a set of known queue IDs
        queueIDs = {item["id"] for item in queue} if queue else set()

        # Find orphaned items (those not in queueIDs)
        affectedItems = [item for item in full_queue if item["id"] not in queueIDs]

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


        logger.debug(
            "remove_orphans/full queue OUT: %s",
            formattedQueueInfo(
                await get_queue(BASE_URL, API_KEY, settingsDict, params={full_queue_param: True})
            ),
        )

        return len(affectedItems)

    except Exception as error:
        errorDetails(NAME, error)
        return 0