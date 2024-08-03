from src.utils.shared import (errorDetails, formattedQueueInfo, get_queue, execute_checks)
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

        # Check if any patterns have been specified
        patterns = settingsDict.get('FAILED_IMPORT_MESSAGE_PATTERNS', [])
        if not patterns:  # If patterns is empty or not present
            patterns = None

        for queueItem in queue['records']: 
            if 'status' in queueItem  \
                and 'trackedDownloadStatus' in queueItem  \
                and 'trackedDownloadState' in queueItem  \
                and 'statusMessages' in queueItem:

                removal_messages = []
                if queueItem['status'] == 'completed' \
                    and queueItem['trackedDownloadStatus'] == 'warning' \
                    and queueItem['trackedDownloadState'] in {'importPending', 'importFailed', 'importBlocked'}:

                    # Find messages that find specified pattern and put them into a "removal_message" that will be displayed in the logger when removing the affected item
                    if not patterns: 
                        # No patterns defined - including all status messages in the removal_messages
                        removal_messages.append ('>>>>> Status Messages (All):')
                        for statusMessage in queueItem['statusMessages']:
                            removal_messages.extend(f">>>>> - {message}" for message in statusMessage.get('messages', []))
                    else:
                        # Specific patterns defined - only removing if any of these are matched
                        for statusMessage in queueItem['statusMessages']:
                            messages = statusMessage.get('messages', [])
                            for message in messages:
                                if any(pattern in message for pattern in patterns):
                                    removal_messages.append(f">>>>> - {message}")
                            if removal_messages:
                                removal_messages.insert (0, '>>>>> Status Messages (matching specified patterns):')
                
                if removal_messages:
                    removal_messages = list(dict.fromkeys(removal_messages)) # deduplication
                    removal_messages.insert(0,'>>>>> Tracked Download State: ' + queueItem['trackedDownloadState'])
                    queueItem['removal_messages'] = removal_messages
                    affectedItems.append(queueItem)
                    
        check_kwargs = {
            'settingsDict': settingsDict,
            'affectedItems': affectedItems,
            'failType': failType,
            'BASE_URL': BASE_URL,
            'API_KEY': API_KEY,
            'NAME': NAME,
            'deleted_downloads': deleted_downloads,
            'defective_tracker': defective_tracker,
            'privateDowloadIDs': privateDowloadIDs,
            'protectedDownloadIDs': protectedDownloadIDs,
            'addToBlocklist': True,
            'doPrivateTrackerCheck': False,
            'doProtectedDownloadCheck': True,
            'doPermittedAttemptsCheck': False,
            'extraParameters': {'keepTorrentForPrivateTrackers': True}
        }
        affectedItems = await execute_checks(**check_kwargs)

        return len(affectedItems)
    except Exception as error:
        errorDetails(NAME, error)
        return 0
