import verboselogs

from src.utils.shared import (
    errorDetails,
    formattedQueueInfo,
    get_queue,
    execute_checks,
    qBitOffline,
)

logger = verboselogs.VerboseLogger(__name__)

async def remove_missing_files(
    settingsDict,
    BASE_URL,
    API_KEY,
    NAME,
    deleted_downloads,
    defective_tracker,
    protectedDownloadIDs,
    privateDownloadIDs,
):
    # Detects downloads broken due to missing files. Does not add to blocklist.
    try:
        failType = "missing files"
        queue = await get_queue(BASE_URL, API_KEY, settingsDict)
        logger.debug("remove_missing_files/queue IN: %s", formattedQueueInfo(queue))

        if not queue or await qBitOffline(settingsDict, failType, NAME):
            return 0

        # Define error messages indicating missing files
        missing_file_errors = {
            "DownloadClientQbittorrentTorrentStateMissingFiles",
            "The download is missing files",
            "qBittorrent is reporting missing files",
        }

        # Find affected items
        affectedItems = [
            item for item in queue
            if item.get("status") == "warning"
            and item.get("errorMessage") in missing_file_errors
        ]

        # Check for failed NZBs/bad files/empty directory cases
        affectedItems.extend([
            item for item in queue
            if item.get("status") == "completed"
            and any(
                "messages" in statusMessage
                and any(msg.startswith("No files found are eligible for import in") for msg in statusMessage["messages"])
                for statusMessage in item.get("statusMessages", [])
            )
        ])

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
            privateDownloadIDs,
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