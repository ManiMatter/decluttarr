from src.utils.shared import (errorDetails, formattedQueueInfo, get_queue, privateTrackerCheck, protectedDownloadCheck, execute_checks, permittedAttemptsCheck, remove_download)
import sys, os, traceback
import logging, verboselogs
logger = verboselogs.VerboseLogger(__name__)

async def remove_failed_imports(settingsDict, BASE_URL, API_KEY, NAME, deleted_downloads, defective_tracker, protectedDownloadIDs, privateDowloadIDs):
    # Detects downloads stuck downloading meta data and triggers repeat check and subsequent delete. Adds to blocklist   
    try:
        failType = 'failed import'
        queue = await get_queue(BASE_URL, API_KEY)
        logger.debug('remove_failed_imports/queue IN: %s', formattedQueueInfo(queue))
        if not queue: return 0
        # Find items affected
        affectedItems = []
        for queueItem in queue['records']: 
            if 'status' in queueItem  \
                and 'trackedDownloadStatus' in queueItem  \
                and 'trackedDownloadState' in queueItem  \
                and 'statusMessages' in queueItem:

                if queueItem['status'] == 'completed' \
                    and queueItem['trackedDownloadStatus'] == 'warning' \
                    and queueItem['trackedDownloadState'] == 'importPending':
                    
                    for statusMessage in queueItem['statusMessages']:
                        if not settingsDict['FAILED_IMPORT_MESSAGE_PATTERNS'] or any(any(pattern in message for pattern in settingsDict['FAILED_IMPORT_MESSAGE_PATTERNS']) for message in statusMessage.get('messages', [])):
                            affectedItems.append(queueItem)
                            break

        affectedItems = await execute_checks(settingsDict, affectedItems, failType, BASE_URL, API_KEY, NAME, deleted_downloads, defective_tracker, privateDowloadIDs, protectedDownloadIDs, 
                                            addToBlocklist = True, 
                                            doPrivateTrackerCheck = False, 
                                            doProtectedDownloadCheck = True, 
                                            doPermittedAttemptsCheck = False,
                                            extraParameters = ['keepTorrentForPrivateTrackers']
                                            )
        return len(affectedItems)
    except Exception as error:
        errorDetails(NAME, error)
        return 0
