from src.utils.shared import (errorDetails, formattedQueueInfo, get_queue, privateTrackerCheck, protectedDownloadCheck, execute_checks, permittedAttemptsCheck, remove_download)
import sys, os, traceback
import logging, verboselogs
logger = verboselogs.VerboseLogger(__name__)

async def remove_slow(settings_dict, BASE_URL, API_KEY, NAME, deleted_downloads, defective_tracker, protectedDownloadIDs, privateDowloadIDs, download_sizes_tracker):
    # Detects slow downloads and triggers delete. Adds to blocklist
    try:
        failType = 'slow'
        logger.debug('remove_slow/queue IN: %s', formattedQueueInfo(queue))
        queue = await get_queue(BASE_URL, API_KEY)
        if not queue: return 0    
        # Find items affected
        affectedItems = []
        alreadyCheckedDownloadIDs = []
        for queueItem in queue['records']:
            if 'downloadId' in queueItem and 'size' in queueItem and 'sizeleft' in queueItem and 'status' in queueItem:
                if queueItem['downloadId'] not in alreadyCheckedDownloadIDs:
                    alreadyCheckedDownloadIDs.append(queueItem['downloadId']) # One downloadId may occur in multiple queueItems - only check once for all of them per iteration
                    # determine if the downloaded bit on average between this and the last iteration is greater than the min threshold
                    downloadedSize, previousSize, increment, speed = await getDownloadedSize(settings_dict, queueItem, download_sizes_tracker)
                    if  queueItem['status'] == 'downloading' and \
                        queueItem['downloadId'] in download_sizes_tracker.dict and \
                        speed is not None:
                        if speed < settings_dict['MIN_DOWNLOAD_SPEED']:
                            affectedItems.append(queueItem)
                            logger.debug('remove_slow/slow speed detected: %s (Speed: %d KB/s, KB now: %s, KB previous: %s, Diff: %s, In Minutes: %s', \
                                queueItem['title'], speed, downloadedSize, previousSize, increment, settings_dict['REMOVE_TIMER'])


        affectedItems = await execute_checks(settings_dict, affectedItems, failType, BASE_URL, API_KEY, NAME, deleted_downloads, defective_tracker, privateDowloadIDs, protectedDownloadIDs, 
                                            addToBlocklist = True, 
                                            doPrivateTrackerCheck = True, 
                                            doProtectedDownloadCheck = True, 
                                            doPermittedAttemptsCheck = True)
        return len(affectedItems)
    except Exception as error:
        errorDetails(NAME, error)
        return 0

from src.utils.rest import (rest_get)
async def getDownloadedSize(settings_dict, queueItem, download_sizes_tracker):
    # Determines the speed of download
    # Since Sonarr/Radarr do not update the downlodedSize on realtime, if possible, fetch it directly from qBit
    if settings_dict['QBITTORRENT_URL']:
        qbitInfo = await rest_get(settings_dict['QBITTORRENT_URL']+'/torrents/info',params={'hashes': queueItem['downloadId']}, cookies=settings_dict['QBIT_COOKIE']  )
        downloadedSize = qbitInfo[0]['completed']
    else:
        logger.debug('getDownloadedSize/WARN: Using imprecise method to determine download increments because no direct qBIT query is possible')
        downloadedSize = queueItem['size'] - queueItem['sizeleft']
    if queueItem['downloadId'] in download_sizes_tracker.dict:
        previousSize = download_sizes_tracker.dict.get(queueItem['downloadId'])
        increment = downloadedSize - previousSize
        speed = round(increment / 1000 / (settings_dict['REMOVE_TIMER'] * 60),1)
    else:
        previousSize = None
        increment = None
        speed = None

    download_sizes_tracker.dict[queueItem['downloadId']] = downloadedSize     
    return downloadedSize, previousSize, increment, speed
