from src.utils.shared import (has_keys, errorDetails, formattedQueueInfo, get_queue, privateTrackerCheck, protectedDownloadCheck, execute_checks, permittedAttemptsCheck, remove_download)
import sys, os, traceback
import logging, verboselogs
logger = verboselogs.VerboseLogger(__name__)

async def remove_metadata_missing(settingsDict, BASE_URL, API_KEY, NAME, deleted_downloads, defective_tracker, protectedDownloadIDs, privateDowloadIDs):
    # Detects downloads stuck downloading meta data and triggers repeat check and subsequent delete. Adds to blocklist   
    try:
        failType = 'missing metadata'
        queue = await get_queue(BASE_URL, API_KEY)
        logger.debug('remove_metadata_missing/queue IN: %s', formattedQueueInfo(queue))
        if not queue: return 0
        # Find items affected
        affectedItems = []
        for queueItem in queue['records']: 
            # Check if the Status is downloading, and is size 0 (no metadata downloaded yet/stuck)
            if has_keys(queueItem, ['status', 'size', 'sizeleft', 'title']):
                ## If the File is stuck on "downloading metadata" -- e.g. a magnet link, resolving to a torrent. This may also be true
                ## However, for that case the size == 0, (since it doesn't exist yet). all other files are >0            
                if queueItem['status'] == 'downloading' and queueItem['sizeleft'] == 0 and queue['size'] == 0:
                    logger.info('>>> Detected Metadata %s download that is 0kb is slow or stuck. (Failed Metadata) Adding to missing metadata list.',queueItem['title'])    
                    affectedItems.append(queueItem)
            
            ## Checking if Status is queued , and has an error
            if has_keys(queueItem, ['errorMessage', 'status']):
                if  queueItem['status'] == 'queued' and queueItem['errorMessage'] == 'qBittorrent is downloading metadata':
                    affectedItems.append(queueItem)
        affectedItems = await execute_checks(settingsDict, affectedItems, failType, BASE_URL, API_KEY, NAME, deleted_downloads, defective_tracker, privateDowloadIDs, protectedDownloadIDs, 
                                            addToBlocklist = True, 
                                            doPrivateTrackerCheck = True, 
                                            doProtectedDownloadCheck = True, 
                                            doPermittedAttemptsCheck = True)
        return len(affectedItems)
    except Exception as error:
        errorDetails(NAME, error)
        return 0
