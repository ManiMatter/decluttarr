# Cleans the download queue
import logging, verboselogs
logger = verboselogs.VerboseLogger(__name__)
from src.utils.rest import (rest_get, rest_delete)
import json
from src.utils.nest_functions import (add_keys_nested_dict, nested_get)
class Deleted_Downloads:
    # Keeps track of which downloads have already been deleted (to not double-delete)
    def __init__(self, dict):
        self.dict = dict

async def get_queue(BASE_URL, API_KEY, params = {}):
    totalRecords = (await rest_get(f'{BASE_URL}/queue', API_KEY, params))['totalRecords']
    if totalRecords == 0:
        return None
    queue = await rest_get(f'{BASE_URL}/queue', API_KEY, {'page': '1', 'pageSize': totalRecords}|params) 
    return queue

async def remove_failed(radarr_or_sonarr, BASE_URL, API_KEY, PERMITTED_ATTEMPTS, queue, deleted_downloads, TEST_RUN):
    # Detects failed and triggers delete. Does not add to blocklist
    failedItems = []    
    for queueItem in queue['records']:
        if 'errorMessage' in queueItem and 'status' in queueItem:
            if  queueItem['status']        == 'failed' or \
               (queueItem['status']       == 'warning' and queueItem['errorMessage'] == 'The download is missing files'):
                await remove_download(BASE_URL, API_KEY, queueItem['id'], queueItem['title'], queueItem['downloadId'], 'failed', False, deleted_downloads, TEST_RUN)
                failedItems.append(queueItem)
    return len(failedItems)

async def remove_stalled(radarr_or_sonarr, BASE_URL, API_KEY, PERMITTED_ATTEMPTS, defective_tracker, queue, deleted_downloads, NO_STALLED_REMOVAL_QBIT_TAG, QBITTORRENT_URL, TEST_RUN):
    # Detects stalled and triggers repeat check and subsequent delete. Adds to blocklist   
    if QBITTORRENT_URL:
        protected_dowloadItems = await rest_get(QBITTORRENT_URL+'/torrents/info','',{'tag': NO_STALLED_REMOVAL_QBIT_TAG})
        protected_downloadIDs = [str.upper(item['hash']) for item in protected_dowloadItems]
    else:
        protected_downloadIDs = []
    stalledItems = []    
    for queueItem in queue['records']:
        if 'errorMessage' in queueItem and 'status' in queueItem:
            if  queueItem['status']        == 'warning' and \
                queueItem['errorMessage']  == 'The download is stalled with no connections':
                    if queueItem['downloadId'] in protected_downloadIDs:
                        logger.verbose('>>> Detected stalled download, tagged not to be killed: %s',queueItem['title'])
                    else:
                        stalledItems.append(queueItem)
    await check_permitted_attempts(stalledItems, 'stalled', True, deleted_downloads, BASE_URL, API_KEY, PERMITTED_ATTEMPTS, defective_tracker, TEST_RUN)
    return len(stalledItems)

async def remove_metadata_missing(radarr_or_sonarr, BASE_URL, API_KEY, PERMITTED_ATTEMPTS, defective_tracker, queue, deleted_downloads, TEST_RUN):
    # Detects downloads stuck downloading meta data and triggers repeat check and subsequent delete. Adds to blocklist  
    missing_metadataItems = []
    for queueItem in queue['records']:
        if 'errorMessage' in queueItem and 'status' in queueItem:
            if  queueItem['status']        == 'queued' and \
                queueItem['errorMessage']  == 'qBittorrent is downloading metadata':
                    missing_metadataItems.append(queueItem)
    await check_permitted_attempts(missing_metadataItems, 'missing metadata', True, deleted_downloads, BASE_URL, API_KEY, PERMITTED_ATTEMPTS, defective_tracker, TEST_RUN)
    return len(missing_metadataItems)

async def remove_orphans(radarr_or_sonarr, BASE_URL, API_KEY, PERMITTED_ATTEMPTS, queue, deleted_downloads, TEST_RUN):
    # Removes downloads belonging to movies/tv shows that have been deleted in the meantime
    full_queue = await get_queue(BASE_URL, API_KEY, params = {'includeUnknownMovieItems' if radarr_or_sonarr == 'radarr' else 'includeUnknownSeriesItems': 'true'})
    if not full_queue: return 0 # By now the queue may be empty 
    full_queue_items = [{'id': queueItem['id'], 'title': queueItem['title']} for queueItem in full_queue['records']]
    queue_ids = [queueItem['id'] for queueItem in queue['records']]
    orphanItems = [{'id': queueItem['id'], 'title': queueItem['title']} for queueItem in full_queue_items if queueItem['id'] not in queue_ids]
    for queueItem in orphanItems:
        await remove_download(BASE_URL, API_KEY, queueItem['id'], queueItem['title'], queueItem['downloadId'], 'orphan', False, deleted_downloads, TEST_RUN)
    return len(orphanItems)

async def remove_unmonitored(radarr_or_sonarr, BASE_URL, API_KEY, PERMITTED_ATTEMPTS, queue, deleted_downloads, TEST_RUN):
    # Removes downloads belonging to movies/tv shows that are not monitored
    unmonitoredItems= []
    downloadItems = []
    for queueItem in queue['records']:
        if radarr_or_sonarr == 'sonarr': 
            monitored = (await rest_get(f'{BASE_URL}/episode/{str(queueItem["episodeId"])}', API_KEY))['monitored']
        else: 
            monitored = (await rest_get(f'{BASE_URL}/movie/{str(queueItem["movieId"])}', API_KEY))['monitored']
        downloadItems.append({'downloadId': queueItem['downloadId'], 'id': queueItem['id'], 'monitored': monitored})
    monitored_downloadIds = [downloadItem['downloadId'] for downloadItem in downloadItems if downloadItem['monitored']]
    unmonitoredItems = [downloadItem for downloadItem in downloadItems if downloadItem['downloadId'] not in monitored_downloadIds]
    for unmonitoredItem in unmonitoredItems:
        await remove_download(BASE_URL, API_KEY, queueItem['id'], queueItem['title'], queueItem['downloadId'], 'unmonitored', False, deleted_downloads, TEST_RUN)
    return len(unmonitoredItems)

async def check_permitted_attempts(current_defective_items, failType, blocklist, deleted_downloads, BASE_URL, API_KEY, PERMITTED_ATTEMPTS, defective_tracker, TEST_RUN):
    # Checks if downloads are repeatedly found as stalled / stuck in metadata and if yes, deletes them
    # 1. Create list of currently defective
    current_defective = {}
    for queueItem in current_defective_items:
        current_defective[queueItem['id']] = {'title': queueItem['title'],'downloadId': queueItem['downloadId']}
        
    # 2. Check if those that were previously defective are no longer defective -> those are recovered
    try:
        recovered_ids = [tracked_id for tracked_id in defective_tracker.dict[BASE_URL][failType] if tracked_id not in current_defective]
    except KeyError:
        recovered_ids = []
    for recovered_id in recovered_ids:
       del defective_tracker.dict[BASE_URL][failType][recovered_id]
    # 3. For those that are defective, add attempt + 1 if present before, or make attempt = 0. If exceeding number of permitted attempts, delete hem
    download_ids_stuck = []
    for queueId in current_defective:
        try: 
            defective_tracker.dict[BASE_URL][failType][queueId]['Attempts'] += 1
        except KeyError:
            await add_keys_nested_dict(defective_tracker.dict,[BASE_URL, failType, queueId], {'title': current_defective[queueId]['title'], 'downloadId': current_defective[queueId]['downloadId'], 'Attempts': 1})
        if current_defective[queueId]['downloadId'] not in download_ids_stuck:
            download_ids_stuck.append(current_defective[queueId]['downloadId'])
            logger.info('>>> Detected %s download (%s out of %s permitted times): %s', failType, str(defective_tracker.dict[BASE_URL][failType][queueId]['Attempts']), str(PERMITTED_ATTEMPTS), defective_tracker.dict[BASE_URL][failType][queueId]['title'])
        if defective_tracker.dict[BASE_URL][failType][queueId]['Attempts'] > PERMITTED_ATTEMPTS:
            await remove_download(BASE_URL, API_KEY, queueId, current_defective[queueId]['title'], current_defective[queueId]['downloadId'],  failType, blocklist, deleted_downloads, TEST_RUN)
    return

async def remove_download(BASE_URL, API_KEY, queueId, queueTitle, downloadId, failType, blocklist, deleted_downloads, TEST_RUN):
    # Removes downloads and creates log entry
    if downloadId not in deleted_downloads.dict:
        logger.info('>>> Removing %s download: %s', failType, queueTitle)
        if not TEST_RUN: await rest_delete(f'{BASE_URL}/queue/{queueId}', API_KEY, {'removeFromClient': 'true', 'blocklist': blocklist}) 
        deleted_downloads.dict.append(downloadId)    
    return

########### MAIN FUNCTION ###########
async def queue_cleaner(radarr_or_sonarr, BASE_URL, API_KEY, NAME, REMOVE_FAILED, REMOVE_STALLED, REMOVE_METADATA_MISSING, REMOVE_ORPHANS, REMOVE_UNMONITORED, PERMITTED_ATTEMPTS, NO_STALLED_REMOVAL_QBIT_TAG, QBITTORRENT_URL, defective_tracker, TEST_RUN):
    # Cleans up the downloads queue
    logger.verbose('Cleaning queue on %s:', NAME)
    try:
        queue = await get_queue(BASE_URL, API_KEY)
        if not queue: 
            logger.verbose('>>> Queue is empty.')
            return

        deleted_downloads = Deleted_Downloads([])
        items_detected = 0
        if REMOVE_FAILED:
            items_detected += await remove_failed(radarr_or_sonarr, BASE_URL, API_KEY, PERMITTED_ATTEMPTS, queue, deleted_downloads, TEST_RUN)
        
        if REMOVE_STALLED:
            items_detected += await remove_stalled(radarr_or_sonarr, BASE_URL, API_KEY, PERMITTED_ATTEMPTS, defective_tracker, queue, deleted_downloads, NO_STALLED_REMOVAL_QBIT_TAG, QBITTORRENT_URL, TEST_RUN)

        if REMOVE_METADATA_MISSING:
            items_detected += await remove_metadata_missing(radarr_or_sonarr, BASE_URL, API_KEY, PERMITTED_ATTEMPTS, defective_tracker, queue, deleted_downloads, TEST_RUN)

        if REMOVE_ORPHANS:
            items_detected += await remove_orphans(radarr_or_sonarr, BASE_URL, API_KEY, PERMITTED_ATTEMPTS, queue, deleted_downloads, TEST_RUN)

        if REMOVE_UNMONITORED:
            items_detected += await remove_unmonitored(radarr_or_sonarr, BASE_URL, API_KEY, PERMITTED_ATTEMPTS, queue, deleted_downloads, TEST_RUN)

        if items_detected == 0:
            logger.verbose('>>> Queue is clean.')
    except:
            logger.warning('>>> Queue cleaning failed on %s.', NAME)



