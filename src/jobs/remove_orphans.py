from src.utils.shared import (errorDetails, formattedQueueInfo, get_queue, privateTrackerCheck, protectedDownloadCheck, execute_checks, permittedAttemptsCheck, remove_download)
import sys, os, traceback
import logging, verboselogs
logger = verboselogs.VerboseLogger(__name__)

async def remove_orphans(settingsDict, BASE_URL, API_KEY, NAME, deleted_downloads, defective_tracker, protectedDownloadIDs, privateDowloadIDs, full_queue_param):
    # Removes downloads belonging to movies/tv shows that have been deleted in the meantime. Does not add to blocklist
    try:
        failType = 'orphan'
        full_queue = await get_queue(BASE_URL, API_KEY, params = {full_queue_param: True})
        queue = await get_queue(BASE_URL, API_KEY) 
        logger.debug('remove_orphans/full queue IN: %s', str(full_queue)) 
        if not full_queue: return 0 # By now the queue may be empty 
        logger.debug('remove_orphans/queue IN: %s', str(queue))

        # Find items affected
        # 1. create a list of the "known" queue items
        queueIDs = [queueItem['id'] for queueItem in queue['records']] if queue else []
        affectedItems = []
        # 2. compare all queue items against the known ones, and those that are not found are the "unknown" or "orphan" ones
        for queueItem in full_queue['records']: 
            if queueItem['id'] not in queueIDs:
                affectedItems.append(queueItem)

        affectedItems = await execute_checks(settingsDict, affectedItems, failType, BASE_URL, API_KEY, NAME, deleted_downloads, defective_tracker, privateDowloadIDs, protectedDownloadIDs, 
                                            addToBlocklist = False, 
                                            doPrivateTrackerCheck = True, 
                                            doProtectedDownloadCheck = True, 
                                            doPermittedAttemptsCheck = False)
        logger.debug('remove_orphans/full queue OUT: %s', str(await get_queue(BASE_URL, API_KEY, params = {full_queue_param: True})))
        return len(affectedItems)
    except Exception as error:
        errorDetails(NAME, error)
        return 0        