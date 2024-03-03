from src.utils.shared import (errorDetails, formattedQueueInfo, get_queue, privateTrackerCheck, protectedDownloadCheck, execute_checks, permittedAttemptsCheck, remove_download)
import sys, os, traceback
import logging, verboselogs
logger = verboselogs.VerboseLogger(__name__)

async def remove_stalled(settings_dict, BASE_URL, API_KEY, NAME, deleted_downloads, defective_tracker, protectedDownloadIDs, privateDowloadIDs):
    # Detects stalled and triggers repeat check and subsequent delete. Adds to blocklist   
    try:
        failType = 'stalled'
        queue = await get_queue(BASE_URL, API_KEY)
        logger.debug('remove_stalled/queue IN: %s', formattedQueueInfo(queue))
        if not queue: return 0
        # Find items affected
        affectedItems = []
        for queueItem in queue['records']: 
            if 'errorMessage' in queueItem and 'status' in queueItem:
                if  queueItem['status'] == 'warning' and queueItem['errorMessage'] == 'The download is stalled with no connections':
                    affectedItems.append(queueItem)
        affectedItems = await execute_checks(settings_dict, affectedItems, failType, BASE_URL, API_KEY, NAME, deleted_downloads, defective_tracker, privateDowloadIDs, protectedDownloadIDs, 
                                            addToBlocklist = True, 
                                            doPrivateTrackerCheck = True, 
                                            doProtectedDownloadCheck = True, 
                                            doPermittedAttemptsCheck = True)
        return len(affectedItems)
    except Exception as error:
        errorDetails(NAME, error)
        return 0
