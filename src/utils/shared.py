# Shared Functions
import logging, verboselogs

logger = verboselogs.VerboseLogger(__name__)
from src.utils.rest import rest_get, rest_delete, rest_post
from src.utils.nest_functions import add_keys_nested_dict, nested_get
import sys, os, traceback


async def get_queue(BASE_URL, API_KEY, params={}):
    # Retrieves the current queue
    await rest_post(
        url=BASE_URL + "/command",
        json={"name": "RefreshMonitoredDownloads"},
        headers={"X-Api-Key": API_KEY},
    )
    totalRecords = (await rest_get(f"{BASE_URL}/queue", API_KEY, params))[
        "totalRecords"
    ]
    if totalRecords == 0:
        return None
    queue = await rest_get(
        f"{BASE_URL}/queue", API_KEY, {"page": "1", "pageSize": totalRecords} | params
    )
    queue = filterOutDelayedQueueItems(queue)
    return queue


def filterOutDelayedQueueItems(queue):
    # Ignores delayed queue items
    if queue is None:
        return None
    seen_combinations = set()
    filtered_records = []
    for record in queue["records"]:
        # Use get() method with default value "No indexer" if 'indexer' key does not exist
        indexer = record.get("indexer", "No indexer")
        protocol = record.get("protocol", "No protocol")
        combination = (record["title"], protocol, indexer)
        if record["status"] == "delay":
            if combination not in seen_combinations:
                seen_combinations.add(combination)
                logger.debug(
                    ">>> Delayed queue item ignored: %s (Protocol: %s, Indexer: %s)",
                    record["title"],
                    protocol,
                    indexer,
                )
        else:
            filtered_records.append(record)
    if not filtered_records:
        return None
    queue["records"] = filtered_records
    return queue


def privateTrackerCheck(settingsDict, affectedItems, failType, privateDowloadIDs):
    # Ignores private tracker items (if setting is turned on)
    for affectedItem in reversed(affectedItems):
        if (
            settingsDict["IGNORE_PRIVATE_TRACKERS"]
            and affectedItem["downloadId"] in privateDowloadIDs
        ):
            affectedItems.remove(affectedItem)
    return affectedItems


def protectedDownloadCheck(settingsDict, affectedItems, failType, protectedDownloadIDs):
    # Checks if torrent is protected and skips
    for affectedItem in reversed(affectedItems):
        if affectedItem["downloadId"] in protectedDownloadIDs:
            logger.verbose(
                ">>> Detected %s download, tagged not to be killed: %s",
                failType,
                affectedItem["title"],
            )
            logger.debug(
                ">>> DownloadID of above %s download (%s): %s",
                failType,
                affectedItem["title"],
                affectedItem["downloadId"],
            )
            affectedItems.remove(affectedItem)
    return affectedItems


async def execute_checks(
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
    addToBlocklist,
    doPrivateTrackerCheck,
    doProtectedDownloadCheck,
    doPermittedAttemptsCheck,
    extraParameters={},
):
    # Goes over the affected items and performs the checks that are parametrized
    try:
        # De-duplicates the affected items (one downloadid may be shared by multiple affected items)
        downloadIDs = []
        for affectedItem in reversed(affectedItems):
            if affectedItem["downloadId"] not in downloadIDs:
                downloadIDs.append(affectedItem["downloadId"])
            else:
                affectedItems.remove(affectedItem)
        # Skips protected items
        if doPrivateTrackerCheck:
            affectedItems = privateTrackerCheck(
                settingsDict, affectedItems, failType, privateDowloadIDs
            )
        if doProtectedDownloadCheck:
            affectedItems = protectedDownloadCheck(
                settingsDict, affectedItems, failType, protectedDownloadIDs
            )
        # Checks if failing more often than permitted
        if doPermittedAttemptsCheck:
            affectedItems = permittedAttemptsCheck(
                settingsDict, affectedItems, failType, BASE_URL, defective_tracker
            )

        # Deletes all downloads that have not survived the checks
        for affectedItem in affectedItems:
            # Checks whether when removing the queue item from the *arr app the torrent should be kept
            removeFromClient = True
            if extraParameters.get("keepTorrentForPrivateTrackers", False):
                if (
                    settingsDict["IGNORE_PRIVATE_TRACKERS"]
                    and affectedItem["downloadId"] in privateDowloadIDs
                ):
                    removeFromClient = False

            # Removes the queue item
            await remove_download(
                settingsDict,
                BASE_URL,
                API_KEY,
                affectedItem,
                failType,
                addToBlocklist,
                deleted_downloads,
                removeFromClient,
            )
        # Exit Logs
        if settingsDict["LOG_LEVEL"] == "DEBUG":
            queue = await get_queue(BASE_URL, API_KEY)
            logger.debug(
                "execute_checks/queue OUT (failType: %s): %s",
                failType,
                formattedQueueInfo(queue),
            )
        # Return removed items
        return affectedItems
    except Exception as error:
        errorDetails(NAME, error)
        return []


def permittedAttemptsCheck(
    settingsDict, affectedItems, failType, BASE_URL, defective_tracker
):
    # Checks if downloads are repeatedly found as stalled / stuck in metadata. Removes the items that are not exeeding permitted attempts
    # Shows all affected items (for debugging)
    logger.debug(
        "permittedAttemptsCheck/affectedItems: %s",
        ", ".join(
            f"{affectedItem['id']}:{affectedItem['title']}:{affectedItem['downloadId']}"
            for affectedItem in affectedItems
        ),
    )

    # 2. Check if those that were previously defective are no longer defective -> those are recovered
    affectedDownloadIDs = [affectedItem["downloadId"] for affectedItem in affectedItems]
    try:
        recoveredDownloadIDs = [
            trackedDownloadIDs
            for trackedDownloadIDs in defective_tracker.dict[BASE_URL][failType]
            if trackedDownloadIDs not in affectedDownloadIDs
        ]
    except KeyError:
        recoveredDownloadIDs = []
    logger.debug(
        "permittedAttemptsCheck/recoveredDownloadIDs: %s", str(recoveredDownloadIDs)
    )
    for recoveredDownloadID in recoveredDownloadIDs:
        logger.info(
            ">>> Download no longer marked as %s: %s",
            failType,
            defective_tracker.dict[BASE_URL][failType][recoveredDownloadID]["title"],
        )
        del defective_tracker.dict[BASE_URL][failType][recoveredDownloadID]
    logger.debug(
        "permittedAttemptsCheck/defective_tracker.dict IN: %s",
        str(defective_tracker.dict),
    )

    # 3. For those that are defective, add attempt + 1 if present before, or make attempt = 1.
    for affectedItem in reversed(affectedItems):
        try:
            defective_tracker.dict[BASE_URL][failType][affectedItem["downloadId"]][
                "Attempts"
            ] += 1
        except KeyError:
            add_keys_nested_dict(
                defective_tracker.dict,
                [BASE_URL, failType, affectedItem["downloadId"]],
                {"title": affectedItem["title"], "Attempts": 1},
            )
        attempts_left = (
            settingsDict["PERMITTED_ATTEMPTS"]
            - defective_tracker.dict[BASE_URL][failType][affectedItem["downloadId"]][
                "Attempts"
            ]
        )
        # If not exceeding the number of permitted times, remove from being affected
        if attempts_left >= 0:  # Still got attempts left
            logger.info(
                ">>> Detected %s download (%s out of %s permitted times): %s",
                failType,
                str(
                    defective_tracker.dict[BASE_URL][failType][
                        affectedItem["downloadId"]
                    ]["Attempts"]
                ),
                str(settingsDict["PERMITTED_ATTEMPTS"]),
                affectedItem["title"],
            )
            affectedItems.remove(affectedItem)
        if attempts_left <= -1:  # Too many attempts
            logger.info(
                ">>> Detected %s download too many times (%s out of %s permitted times): %s",
                failType,
                str(
                    defective_tracker.dict[BASE_URL][failType][
                        affectedItem["downloadId"]
                    ]["Attempts"]
                ),
                str(settingsDict["PERMITTED_ATTEMPTS"]),
                affectedItem["title"],
            )
        if (
            attempts_left <= -2
        ):  # Too many attempts and should already have been removed
            # If supposedly deleted item keeps coming back, print out guidance for "Reject Blocklisted Torrent Hashes While Grabbing"
            logger.verbose(
                '>>> [Tip!] Since this download should already have been removed in a previous iteration but keeps coming back, this indicates the blocking of the torrent does not work correctly. Consider turning on the option "Reject Blocklisted Torrent Hashes While Grabbing" on the indexer in the *arr app: %s',
                affectedItem["title"],
            )
    logger.debug(
        "permittedAttemptsCheck/defective_tracker.dict OUT: %s",
        str(defective_tracker.dict),
    )
    return affectedItems


async def remove_download(
    settingsDict,
    BASE_URL,
    API_KEY,
    affectedItem,
    failType,
    addToBlocklist,
    deleted_downloads,
    removeFromClient,
):
    # Removes downloads and creates log entry
    logger.debug(
        "remove_download/deleted_downloads.dict IN: %s", str(deleted_downloads.dict)
    )
    if affectedItem["downloadId"] not in deleted_downloads.dict:
        # "schizophrenic" removal:
        # Yes, the failed imports are removed from the -arr apps (so the removal kicks still in)
        # But in the torrent client they are kept
        if removeFromClient:
            logger.info(">>> Removing %s download: %s", failType, affectedItem["title"])
        else:
            logger.info(
                ">>> Removing %s download (without removing from torrent client): %s",
                failType,
                affectedItem["title"],
            )

        # Print out detailed removal messages (if any were added in the jobs)
        if "removal_messages" in affectedItem:
            for removal_message in affectedItem["removal_messages"]:
                logger.info(removal_message)

        if not settingsDict["TEST_RUN"]:
            await rest_delete(
                f'{BASE_URL}/queue/{affectedItem["id"]}',
                API_KEY,
                {"removeFromClient": removeFromClient, "blocklist": addToBlocklist},
            )
        deleted_downloads.dict.append(affectedItem["downloadId"])

    logger.debug(
        "remove_download/deleted_downloads.dict OUT: %s", str(deleted_downloads.dict)
    )
    return


def errorDetails(NAME, error):
    exc_type, exc_obj, exc_tb = sys.exc_info()
    fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
    logger.warning(
        ">>> Queue cleaning failed on %s. (File: %s / Line: %s / Error Message: %s / Error Type: %s)",
        NAME,
        fname,
        exc_tb.tb_lineno,
        error,
        exc_type,
    )
    logger.debug(traceback.format_exc())
    return


def formattedQueueInfo(queue):
    try:
        # Returns queueID, title, and downloadID
        if not queue:
            return "empty"
        formatted_list = []
        for record in queue["records"]:
            download_id = record["downloadId"]
            title = record["title"]
            item_id = record["id"]
            # Check if there is an entry with the same download_id and title
            existing_entry = next(
                (item for item in formatted_list if item["downloadId"] == download_id),
                None,
            )
            if existing_entry:
                existing_entry["IDs"].append(item_id)
            else:
                new_entry = {
                    "downloadId": download_id,
                    "downloadTitle": title,
                    "IDs": [item_id],
                }
                formatted_list.append(new_entry)
        return formatted_list
    except Exception as error:
        errorDetails("formattedQueueInfo", error)
        logger.debug("formattedQueueInfo/queue for debug: %s", str(queue))
        return "error"


async def qBitOffline(settingsDict, failType, NAME):
    if settingsDict["QBITTORRENT_URL"]:
        qBitConnectionStatus = (
            await rest_get(
                settingsDict["QBITTORRENT_URL"] + "/sync/maindata",
                cookies=settingsDict["QBIT_COOKIE"],
            )
        )["server_state"]["connection_status"]
        if qBitConnectionStatus == "disconnected":
            logger.warning(
                ">>> qBittorrent is disconnected. Skipping %s queue cleaning failed on %s.",
                failType,
                NAME,
            )
            return True
    return False
