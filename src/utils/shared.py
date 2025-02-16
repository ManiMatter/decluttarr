# Shared Functions
import logging, verboselogs
import asyncio
import requests
logger = verboselogs.VerboseLogger(__name__)
from src.utils.rest import rest_get, rest_delete, rest_post
from src.utils.nest_functions import add_keys_nested_dict, nested_get
import sys, os, traceback


async def get_arr_records(BASE_URL, API_KEY, params={}, end_point=""):
    # Fetch all records from a given endpoint
    url = f"{BASE_URL}/{end_point}"
    params_with_pagination = {"page": "1", "pageSize": (await rest_get(url, API_KEY, params)).get("totalRecords", 0)} | params

    if params_with_pagination["pageSize"] == 0:
        return []

    return (await rest_get(url, API_KEY, params_with_pagination)).get("records", [])

async def get_queue(BASE_URL, API_KEY, settingsDict, params={}):
    # Refreshes and retrieves the current queue
    await rest_post(
        url=f"{BASE_URL}/command",
        json={"name": "RefreshMonitoredDownloads"},
        headers={"X-Api-Key": API_KEY},
    )

    queue = await get_arr_records(BASE_URL, API_KEY, params=params, end_point="queue")

    if not queue:  # Avoids unnecessary processing if queue is empty
        return []

    return filterOutIgnoredDownloadClients(
        filterOutDelayedQueueItems(queue), settingsDict
    )

def filterOutDelayedQueueItems(queue):
    # Ignores delayed queue items
    if not queue:
        return queue  # Returns early if queue is None or empty

    seen_combinations = set()
    filtered_queue = []

    for item in queue:
        title = item.get("title")
        protocol = item.get("protocol", "No protocol")
        indexer = item.get("indexer", "No indexer")
        combination = (title, protocol, indexer)

        if item.get("status") == "delay":
            if combination not in seen_combinations:
                seen_combinations.add(combination)
                logger.debug(
                    ">>> Delayed queue item ignored: %s (Protocol: %s, Indexer: %s)",
                    title,
                    protocol,
                    indexer,
                )
        else:
            filtered_queue.append(item)

    return filtered_queue

def filterOutIgnoredDownloadClients(queue, settingsDict):
    """
    Filters out queue items whose download client is listed in IGNORED_DOWNLOAD_CLIENTS.
    """
    if not queue:
        return queue  # Early return if queue is None or empty

    ignored_clients = set(settingsDict.get("IGNORED_DOWNLOAD_CLIENTS", []))  # Use .get() for safety
    filtered_queue = [
        item for item in queue
        if (client := item.get("downloadClient", "Unknown client")) not in ignored_clients
        or not logger.debug(
            ">>> Queue item ignored due to ignored download client: %s (Download Client: %s)",
            item.get("title"),
            client,
        )
    ]

    return filtered_queue

def privateTrackerCheck(settingsDict, affectedItems, failType, privateDowloadIDs):
    # Ignores private tracker items (if setting is turned on)
    if not settingsDict.get("IGNORE_PRIVATE_TRACKERS"):  # Use .get() for safety
        return affectedItems  # Return early if the setting is off

    privateDowloadIDs = set(privateDowloadIDs)  # Convert to set for O(1) lookups

    return [item for item in affectedItems if item.get("downloadId") not in privateDowloadIDs]

def protectedDownloadCheck(settingsDict, affectedItems, failType, protectedDownloadIDs):
    # Checks if torrent is protected and skips
    protectedDownloadIDs = set(protectedDownloadIDs)  # Convert to set for faster lookups

    filtered_items = []
    for item in affectedItems:
        if item.get("downloadId") in protectedDownloadIDs:
            logger.verbose(
                ">>> Detected %s download, tagged not to be killed: %s",
                failType,
                item.get("title"),
            )
            logger.debug(
                ">>> DownloadID of above %s download (%s): %s",
                failType,
                item.get("title"),
                item.get("downloadId"),
            )
        else:
            filtered_items.append(item)

    return filtered_items

def permittedAttemptsCheck(settingsDict, affectedItems, failType, BASE_URL, defective_tracker):
    # Ensure downloads are removed ONLY when they exceed `PERMITTED_ATTEMPTS`

    permitted_attempts = settingsDict["PERMITTED_ATTEMPTS"]
    to_remove = []

    for item in affectedItems:
        download_id = item["downloadId"]
        title = item["title"]

        # Ensure nested dictionary exists and update attempt count
        tracker = defective_tracker.dict.setdefault(BASE_URL, {}).setdefault(failType, {})
        tracker.setdefault(download_id, {"title": title, "Attempts": 0})["Attempts"] += 1

        attempts = tracker[download_id]["Attempts"]
        attempts_left = permitted_attempts - attempts

        if attempts_left >= 0:
            logger.info(
                ">>> Keeping %s download (%s out of %s permitted times): %s",
                failType, attempts, permitted_attempts, title,
            )
        else:
            logger.info(
                ">>> %s download exceeded permitted attempts (%s out of %s): %s",
                failType, attempts, permitted_attempts, title,
            )
            to_remove.append(item)

    return to_remove

async def execute_checks(
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
    addToBlocklist,
    doPrivateTrackerCheck,
    doProtectedDownloadCheck,
    doPermittedAttemptsCheck,
    extraParameters={},
):
    try:
        # De-duplicate affected items by downloadId
        seen_ids = set()
        affectedItems = [item for item in affectedItems if not (item["downloadId"] in seen_ids or seen_ids.add(item["downloadId"]))]

        # Apply checks
        if doPrivateTrackerCheck:
            affectedItems = privateTrackerCheck(settingsDict, affectedItems, failType, privateDownloadIDs)

        if doProtectedDownloadCheck:
            affectedItems = protectedDownloadCheck(settingsDict, affectedItems, failType, protectedDownloadIDs)

        if doPermittedAttemptsCheck:
            affectedItems = permittedAttemptsCheck(settingsDict, affectedItems, failType, BASE_URL, defective_tracker)

        # Remove exceeded attempts items
        keep_private_torrents = extraParameters.get("keepTorrentForPrivateTrackers", False)
        ignore_private_trackers = settingsDict.get("IGNORE_PRIVATE_TRACKERS", False)

        tasks = [
            remove_download(
                settingsDict,
                BASE_URL,
                API_KEY,
                item,
                failType,
                addToBlocklist,
                deleted_downloads,
                not (keep_private_torrents and ignore_private_trackers and item["downloadId"] in privateDownloadIDs),
            )
            for item in affectedItems
        ]

        await asyncio.gather(*tasks)  # Execute removals concurrently

        # Exit Logs
        if settingsDict.get("LOG_LEVEL") == "DEBUG":
            queue = await get_queue(BASE_URL, API_KEY, settingsDict)
            logger.debug("execute_checks/queue OUT (failType: %s): %s", failType, formattedQueueInfo(queue))

        return affectedItems  # Return the list of removed items

    except Exception as error:
        errorDetails(NAME, error)
        return []


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
    logger.debug("remove_download/deleted_downloads.dict IN: %s", str(deleted_downloads.dict))

    download_id = affectedItem["downloadId"]

    if download_id not in deleted_downloads.dict:
        # Log removal action
        log_msg = (
            f">>> Removing {failType} download: {affectedItem['title']}"
            if removeFromClient
            else f">>> Removing {failType} download (without removing from torrent client): {affectedItem['title']}"
        )
        logger.info(log_msg)

        # Log any additional removal messages
        for message in affectedItem.get("removal_messages", []):
            logger.info(message)

        # Perform deletion unless it's a test run
        if not settingsDict.get("TEST_RUN", False):
            await rest_delete(
                f"{BASE_URL}/queue/{affectedItem['id']}",
                API_KEY,
                {"removeFromClient": removeFromClient, "blocklist": addToBlocklist},
            )

        deleted_downloads.dict.append(download_id)

    logger.debug("remove_download/deleted_downloads.dict OUT: %s", str(deleted_downloads.dict))

def errorDetails(NAME, error):
    exc_type, exc_obj, exc_tb = sys.exc_info()
    if exc_tb:  # Ensure traceback exists before accessing attributes
        fname = os.path.basename(exc_tb.tb_frame.f_code.co_filename)
        lineno = exc_tb.tb_lineno
    else:
        fname, lineno = "Unknown", "Unknown"

    logger.warning(
        ">>> Queue cleaning failed on %s. (File: %s / Line: %s / %s)",
        NAME,
        fname,
        lineno,
        traceback.format_exc(),
    )

def formattedQueueInfo(queue):
    try:
        if not queue:
            return "empty"

        formatted_dict = {}

        for item in queue:
            download_id = item.get("downloadId")
            item_id = item.get("id")
            title = item.get("title")
            protocol = item.get("protocol")
            status = item.get("status")

            if download_id in formatted_dict:
                formatted_dict[download_id]["IDs"].append(item_id)
                formatted_dict[download_id]["protocol"].append(protocol)
                formatted_dict[download_id]["status"].append(status)
            else:
                formatted_dict[download_id] = {
                    "downloadId": download_id,
                    "downloadTitle": title,
                    "IDs": [item_id],
                    "protocol": [protocol],
                    "status": [status],
                }

        return list(formatted_dict.values())

    except Exception as error:
        errorDetails("formattedQueueInfo", error)
        logger.debug("formattedQueueInfo/queue for debug: %s", str(queue))
        return "error"


async def qBitOffline(settingsDict, failType, NAME):
    qbit_url = settingsDict.get("QBITTORRENT_URL")

    if not qbit_url:
        return False  # Early return if no URL is set

    try:
        response = await rest_get(f"{qbit_url}/sync/maindata", cookies=settingsDict.get("QBIT_COOKIE", {}))
        if response.get("server_state", {}).get("connection_status") == "disconnected":
            logger.warning(
                ">>> qBittorrent is disconnected. Skipping %s queue cleaning on %s.",
                failType,
                NAME,
            )
            return True
    except Exception as error:
        errorDetails("qBitOffline", error)

    return False

import asyncio
import requests

async def qBitRefreshCookie(settingsDict):
    try:
        url = f"{settingsDict['QBITTORRENT_URL']}/auth/login"
        data = {
            "username": settingsDict["QBITTORRENT_USERNAME"],
            "password": settingsDict["QBITTORRENT_PASSWORD"],
        }
        headers = {"content-type": "application/x-www-form-urlencoded"}

        response = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: requests.post(url, data=data, headers=headers, verify=settingsDict.get("SSL_VERIFICATION", True)),
        )

        response.raise_for_status()
        if response.text.strip() == "Fails.":
            raise ConnectionError("Login failed.")

        settingsDict["QBIT_COOKIE"] = {"SID": response.cookies.get("SID", "")}
        logger.debug("qBit cookie refreshed!")

    except Exception as error:
        logger.error("!! qBittorrent Error: !!")
        logger.error("> %s", error)
        if "response" in locals():
            logger.error("> Details: %s", response.text.strip())

        settingsDict["QBIT_COOKIE"] = {}