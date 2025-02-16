from src.utils.shared import errorDetails, formattedQueueInfo, get_queue, execute_checks
import verboselogs

logger = verboselogs.VerboseLogger(__name__)


async def remove_failed_imports(
        settingsDict,
        BASE_URL,
        API_KEY,
        NAME,
        deleted_downloads,
        defective_tracker,
        protectedDownloadIDs,
        privateDownloadIDs,
):
    """Detect and remove downloads stuck in a failed import state."""
    try:
        failType = "failed import"
        queue = await get_queue(BASE_URL, API_KEY, settingsDict)
        logger.debug("remove_failed_imports/queue IN: %s", formattedQueueInfo(queue))

        if not queue:
            return 0

        # Load message patterns for filtering
        patterns = settingsDict.get("FAILED_IMPORT_MESSAGE_PATTERNS") or None
        affectedItems = []

        # Process queue items
        for queueItem in queue:
            if not all(k in queueItem for k in
                       ("status", "trackedDownloadStatus", "trackedDownloadState", "statusMessages")):
                continue  # Skip invalid queue items

            # Ensure the download meets failure conditions
            if queueItem["status"] == "completed" and queueItem["trackedDownloadStatus"] == "warning":
                if queueItem["trackedDownloadState"] in {"importPending", "importFailed", "importBlocked"}:
                    removal_messages = process_removal_messages(queueItem, patterns)

                    if removal_messages:
                        queueItem["removal_messages"] = removal_messages
                        affectedItems.append(queueItem)

        logger.verbose("🔥 Affected Items Before Checks: %s", affectedItems)

        # Execute checks
        affectedItems = await execute_checks(
            settingsDict=settingsDict,
            affectedItems=affectedItems,
            failType=failType,
            BASE_URL=BASE_URL,
            API_KEY=API_KEY,
            NAME=NAME,
            deleted_downloads=deleted_downloads,
            defective_tracker=defective_tracker,
            privateDownloadIDs=privateDownloadIDs,
            protectedDownloadIDs=protectedDownloadIDs,
            addToBlocklist=True,
            doPrivateTrackerCheck=False,
            doProtectedDownloadCheck=True,
            doPermittedAttemptsCheck=False,
            extraParameters={"keepTorrentForPrivateTrackers": True},
        )

        logger.verbose("✅ Affected Items After Checks: %s", affectedItems)

        return len(affectedItems)

    except Exception as error:
        errorDetails(NAME, error)
        return 0


def process_removal_messages(queueItem, patterns):
    """Generate removal messages based on queue item status and patterns."""
    removal_messages = []

    if not patterns:
        # No specific pattern: Include all status messages
        removal_messages.append(">>>>> Status Messages (All):")
        removal_messages.extend(
            f">>>>> - {message}" for status in queueItem["statusMessages"] for message in status.get("messages", [])
        )
    else:
        # Only include messages matching a pattern
        for status in queueItem["statusMessages"]:
            messages = status.get("messages", [])
            matched_messages = [f">>>>> - {msg}" for msg in messages if any(pat in msg for pat in patterns)]
            if matched_messages:
                removal_messages.append(">>>>> Status Messages (matching specified patterns):")
                removal_messages.extend(matched_messages)

    if removal_messages:
        removal_messages.insert(0, f">>>>> Tracked Download State: {queueItem['trackedDownloadState']}")
        return list(dict.fromkeys(removal_messages))  # Deduplicate
    return None