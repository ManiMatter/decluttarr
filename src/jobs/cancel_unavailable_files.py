from src.utils.shared import (errorDetails, formattedQueueInfo, get_queue, privateTrackerCheck, protectedDownloadCheck, execute_checks, permittedAttemptsCheck, remove_download, qBitOffline)
import sys, os, traceback
import logging, verboselogs
logger = verboselogs.VerboseLogger(__name__)
from src.utils.rest import rest_get, rest_post


async def cancel_unavailable_files(settingsDict, BASE_URL, API_KEY, NAME, protectedDownloadIDs, privateDowloadIDs, arr_type):
    # Checks if downloads have less than 100% availability and marks the underyling files that cause it as 'do not download'
    # Only works in qbit
    try:
        failType = '>100% availability'        
        queue = await get_queue(BASE_URL, API_KEY)
        logger.debug('CANCEL_UNAVAILABLE_FILES/queue IN: %s', formattedQueueInfo(queue))
        if not queue: return 0
        if await qBitOffline(settingsDict, failType, NAME): return 
        # Find items affected

        qbitHashes = list(set(queueItem['downloadId'].upper() for queueItem in queue['records']))

        # Remove private and protected trackers
        if settingsDict['IGNORE_PRIVATE_TRACKERS']:
                for qbitHash in reversed(qbitHashes):
                        if qbitHash in privateDowloadIDs:
                                qbitHashes.remove(qbitHash)

        if settingsDict['IGNORE_PRIVATE_TRACKERS']:
                for qbitHash in reversed(qbitHashes):
                        if qbitHash in privateDowloadIDs:
                                qbitHashes.remove(qbitHash)

        qbitItems = await rest_get(settingsDict['QBITTORRENT_URL']+'/torrents/info',params={'hashes': ('|').join(qbitHashes)}, cookies=settingsDict['QBIT_COOKIE'])

        for qbitItem in qbitItems:
                if 'state' in qbitItem and 'availability' in qbitItem:
                        if qbitItem['state'] == 'downloading' and qbitItem['availability'] < 1:
                                logger.info('>>> Detected %s: %s', failType, qbitItem['name'])
                                logger.verbose('>>>>> Marking following files to "not download":')                                
                                qbitItemFiles = await rest_get(settingsDict['QBITTORRENT_URL']+'/torrents/files',params={'hash': qbitItem['hash']}, cookies=settingsDict['QBIT_COOKIE'])
                                for qbitItemFile in qbitItemFiles:
                                        if all(key in qbitItemFile for key in ['availability', 'progress', 'priority', 'index', 'name']):
                                                if qbitItemFile['availability'] < 1 and qbitItemFile['progress'] < 1 and qbitItemFile['priority'] != 0:
                                                        logger.verbose('>>>>> %s', qbitItemFile['name'].split('/')[-1])
                                                        if not settingsDict['TEST_RUN']:
                                                                await rest_post(url=settingsDict['QBITTORRENT_URL']+'/torrents/filePrio', data={'hash': qbitItem['hash'].lower(), 'id': qbitItemFile['index'], 'priority': 0}, cookies=settingsDict['QBIT_COOKIE'])

    except Exception as error:
        errorDetails(NAME, error)
        return 

