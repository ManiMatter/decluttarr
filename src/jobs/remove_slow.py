import verboselogs

from src.utils.rest import rest_get
from src.utils.shared import (
    errorDetails,
    formattedQueueInfo,
    get_queue,
    execute_checks,
    qBitOffline,
)

logger = verboselogs.VerboseLogger(__name__)

async def remove_slow(
    settingsDict,
    BASE_URL,
    API_KEY,
    NAME,
    deleted_downloads,
    defective_tracker,
    protectedDownloadIDs,
    privateDowloadIDs,
    download_sizes_tracker,
):
    # Detects slow downloads and triggers delete. Adds to blocklist.
    try:
        failType = "slow"
        queue = await get_queue(BASE_URL, API_KEY, settingsDict)
        logger.debug("remove_slow/queue IN: %s", formattedQueueInfo(queue))

        if not queue or await qBitOffline(settingsDict, failType, NAME):
            return 0

        affectedItems = []
        alreadyCheckedDownloadIDs = set()

        for queueItem in queue:
            if not {"downloadId", "size", "sizeleft", "status", "protocol"}.issubset(queueItem):
                continue

            downloadId = queueItem["downloadId"]

            if downloadId in alreadyCheckedDownloadIDs:
                continue
            alreadyCheckedDownloadIDs.add(downloadId)

            if queueItem["protocol"] == "usenet":
                continue  # Skip speed checks for Usenet

            if queueItem["status"] == "downloading":
                if queueItem["size"] > 0 and queueItem["sizeleft"] == 0:
                    logger.info(
                        ">>> Detected %s download that has completed downloading - skipping check (torrent files likely in process of being moved): %s",
                        failType,
                        queueItem["title"],
                    )
                    continue

                # Get speed and determine if it's below the threshold
                downloadedSize, previousSize, increment, speed = await getDownloadedSize(
                    settingsDict, queueItem, download_sizes_tracker, NAME
                )

                if speed is not None and speed < settingsDict["MIN_DOWNLOAD_SPEED"]:
                    affectedItems.append(queueItem)
                    logger.debug(
                        "remove_slow/slow speed detected: %s (Speed: %d KB/s, KB now: %s, KB previous: %s, Diff: %s, In Minutes: %s)",
                        queueItem["title"],
                        speed,
                        downloadedSize,
                        previousSize,
                        increment,
                        settingsDict["REMOVE_TIMER"],
                    )

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


async def getDownloadedSize(settingsDict, queueItem, download_sizes_tracker, NAME):
    # Determines the speed of download. If possible, fetch directly from qBit.
    try:
        downloadId = queueItem["downloadId"]

        if settingsDict.get("QBITTORRENT_URL") and queueItem["downloadClient"] == "qBittorrent":
            qbitInfo = await rest_get(
                f"{settingsDict['QBITTORRENT_URL']}/torrents/info",
                params={"hashes": downloadId},
                cookies=settingsDict.get("QBIT_COOKIE"),
            )
            downloadedSize = qbitInfo[0]["completed"]
        else:
            logger.debug(
                "getDownloadedSize/WARN: Using imprecise method to determine download increments because no direct qBIT query is possible"
            )
            downloadedSize = queueItem["size"] - queueItem["sizeleft"]

        previousSize = download_sizes_tracker.dict.get(downloadId)
        increment = (downloadedSize - previousSize) if previousSize is not None else None
        speed = round(increment / 1000 / (settingsDict["REMOVE_TIMER"] * 60), 1) if increment is not None else None

        download_sizes_tracker.dict[downloadId] = downloadedSize
        return downloadedSize, previousSize, increment, speed

    except Exception as error:
        errorDetails(NAME, error)
        return None, None, None, None