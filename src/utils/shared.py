# Shared Functions
import logging, verboselogs
logger = verboselogs.VerboseLogger(__name__)
from src.utils.rest import (rest_get, rest_delete, rest_post)
from src.utils.nest_functions import (add_keys_nested_dict, nested_get)
import sys, os, traceback

async def get_queue(BASE_URL, API_KEY, params = {}):
    # Retrieves the current queue
    await rest_post(url=BASE_URL+'/command', json={'name': 'RefreshMonitoredDownloads'}, headers={'X-Api-Key': API_KEY})
    totalRecords = (await rest_get(f'{BASE_URL}/queue', API_KEY, params))['totalRecords']
    if totalRecords == 0:
        return None
    queue = await rest_get(f'{BASE_URL}/queue', API_KEY, {'page': '1', 'pageSize': totalRecords}|params) 
    return queue

def privateTrackerCheck(settings_dict, affectedItems, failType, privateDowloadIDs):
    # Ignores private tracker items (if setting is turned on)
    for affectedItem in reversed(affectedItems):
        if settings_dict['IGNORE_PRIVATE_TRACKERS'] and affectedItem['downloadId'] in privateDowloadIDs:
            affectedItems.remove(affectedItem) 
    return affectedItems

def protectedDownloadCheck(settings_dict, affectedItems, failType, protectedDownloadIDs):
    # Checks if torrent is protected and skips
    for affectedItem in reversed(affectedItems):
        if affectedItem['downloadId'] in protectedDownloadIDs:
            logger.verbose('>>> Detected %s download, tagged not to be killed: %s',failType, affectedItem['title'])
            affectedItems.remove(affectedItem)
    return affectedItems


async def execute_checks(settings_dict, affectedItems, failType, BASE_URL, API_KEY, NAME, deleted_downloads, defective_tracker, privateDowloadIDs, protectedDownloadIDs, addToBlocklist, doPrivateTrackerCheck, doProtectedDownloadCheck, doPermittedAttemptsCheck):
    # Goes over the affected items and performs the checks that are parametrized
    try:
        # De-duplicates the affected items (one downloadid may be shared by multiple affected items)
        downloadIDs = []
        for affectedItem in reversed(affectedItems):
            if affectedItem['downloadId'] not in downloadIDs:
                downloadIDs.append(affectedItem['downloadId'])
            else:
                affectedItems.remove(affectedItem)
        # Skips protected items
        if doPrivateTrackerCheck:
            affectedItems = privateTrackerCheck(settings_dict, affectedItems, failType, privateDowloadIDs)
        if doProtectedDownloadCheck:
            affectedItems = protectedDownloadCheck(settings_dict, affectedItems, failType, protectedDownloadIDs)
        # Checks if failing more often than permitted 
        if doPermittedAttemptsCheck:
            affectedItems = permittedAttemptsCheck(settings_dict, affectedItems, failType, BASE_URL, defective_tracker)
        # Deletes all downloads that have not survived the checks
        for affectedItem in affectedItems:
            await remove_download(settings_dict, BASE_URL, API_KEY, affectedItem, failType, addToBlocklist, deleted_downloads)
        # Exit Logs
        if settings_dict['LOG_LEVEL'] == 'DEBUG':
            queue = await get_queue(BASE_URL, API_KEY)      
            logger.debug('execute_checks/queue OUT (failType: %s): %s', failType, formattedQueueInfo(queue))
        # Return removed items
        return affectedItems
    except Exception as error:
        errorDetails(NAME, error)
        return []

def permittedAttemptsCheck(settings_dict, affectedItems, failType, BASE_URL, defective_tracker):
    # Checks if downloads are repeatedly found as stalled / stuck in metadata. Removes the items that are not exeeding permitted attempts
    # Shows all affected items (for debugging)
    logger.debug('permittedAttemptsCheck/affectedItems: %s', ', '.join(f"{affectedItem['id']}:{affectedItem['title']}:{affectedItem['downloadId']}" for affectedItem in affectedItems))

    # 2. Check if those that were previously defective are no longer defective -> those are recovered
    affectedDownloadIDs = [affectedItem['downloadId'] for affectedItem in affectedItems]
    try:
        recoveredDownloadIDs = [trackedDownloadIDs for trackedDownloadIDs in defective_tracker.dict[BASE_URL][failType] if trackedDownloadIDs not in affectedDownloadIDs]
    except KeyError:
        recoveredDownloadIDs = []
    logger.debug('permittedAttemptsCheck/recoveredDownloadIDs: %s', str(recoveredDownloadIDs)) 
    for recoveredDownloadID in recoveredDownloadIDs:
       del defective_tracker.dict[BASE_URL][failType][recoveredDownloadID]
    logger.debug('permittedAttemptsCheck/defective_tracker.dict IN: %s', str(defective_tracker.dict))

    # 3. For those that are defective, add attempt + 1 if present before, or make attempt = 1. 
    for affectedItem in reversed(affectedItems):
        try: 
            defective_tracker.dict[BASE_URL][failType][affectedItem['downloadId']]['Attempts'] += 1
        except KeyError:
            add_keys_nested_dict(defective_tracker.dict,[BASE_URL, failType, affectedItem['downloadId']], {'title': affectedItem['title'], 'Attempts': 1})
        logger.info('>>> Detected %s download (%s out of %s permitted times): %s', failType, str(defective_tracker.dict[BASE_URL][failType][affectedItem['downloadId']]['Attempts']), str(settings_dict['PERMITTED_ATTEMPTS']), affectedItem['title'])
        # If not exceeding the number of permitted times, remove from being affected
        if defective_tracker.dict[BASE_URL][failType][affectedItem['downloadId']]['Attempts'] <= settings_dict['PERMITTED_ATTEMPTS']:
            affectedItems.remove(affectedItem)
        # else:
        #     # Will be deleted - reset the counter to 0
        #     del defective_tracker.dict[BASE_URL][failType][affectedItem['downloadId']]
    logger.debug('permittedAttemptsCheck/defective_tracker.dict OUT: %s', str(defective_tracker.dict))
    return affectedItems

async def remove_download(settings_dict, BASE_URL, API_KEY, affectedItem, failType, addToBlocklist, deleted_downloads):
    # Removes downloads and creates log entry
    logger.debug('remove_download/deleted_downloads.dict IN: %s', str(deleted_downloads.dict)) 
    if affectedItem['downloadId'] not in deleted_downloads.dict:
        logger.info('>>> Removing %s download: %s', failType, affectedItem['title'])
        if not settings_dict['TEST_RUN']: 
            await rest_delete(f'{BASE_URL}/queue/{affectedItem["id"]}', API_KEY, {'removeFromClient': True, 'blocklist': addToBlocklist}) 
        deleted_downloads.dict.append(affectedItem['downloadId'])   
    
    logger.debug('remove_download/deleted_downloads.dict OUT: %s', str(deleted_downloads.dict)) 
    return


def errorDetails(NAME, error):
    exc_type, exc_obj, exc_tb = sys.exc_info()
    fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
    logger.warning('>>> Queue cleaning failed on %s. (File: %s / Line: %s / Error Message: %s / Error Type: %s)', NAME, fname, exc_tb.tb_lineno, error, exc_type)
    logger.debug(traceback.format_exc())
    return    

def formattedQueueInfo(queue):
    # Returns queueID, title, and downloadID
    formatted_list = []
    for record in queue['records']:
        download_id = record['downloadId']
        title = record['title']
        item_id = record['id']
        # Check if there is an entry with the same download_id and title
        existing_entry = next((item for item in formatted_list if item['downloadId'] == download_id), None)
        if existing_entry:
            existing_entry['IDs'].append(item_id)
        else:
            new_entry = {'downloadId': download_id, 'downloadTitle': title, 'IDs': [item_id]}
            formatted_list.append(new_entry)
    return(formatted_list)
