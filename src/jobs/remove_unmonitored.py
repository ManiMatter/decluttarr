import verboselogs

from src.utils.shared import (
    errorDetails,
    formattedQueueInfo,
    get_queue,
    execute_checks,
)

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
    # Removes downloads belonging to unmonitored movies/TV shows. Does not add to blocklist.
    try:
        failType = "unmonitored"
        queue = await get_queue(BASE_URL, API_KEY, settingsDict)
        logger.debug("remove_unmonitored/queue IN: %s", formattedQueueInfo(queue))

        if not queue:
            return 0

        # API endpoints for different `arr_type`
        endpoint_map = {
            "SONARR": "episode",
            "RADARR": "movie",
            "LIDARR": "album",
            "READARR": "book",
            "WHISPARR": "episode",
        }

        monitoredDownloadIDs = set()

        for queueItem in queue:
            content_id_key = f"{endpoint_map[arr_type]}Id"
            content_id = queueItem.get(content_id_key)

            if content_id:
                isMonitored = (await rest_get(f"{BASE_URL}/{endpoint_map[arr_type]}/{content_id}", API_KEY)).get("monitored", False)

                if isMonitored:
                    monitoredDownloadIDs.add(queueItem["downloadId"])

        # Identify unmonitored items
        affectedItems = [item for item in queue if item["downloadId"] not in monitoredDownloadIDs]

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