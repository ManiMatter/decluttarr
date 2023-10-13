# Cleans the download queue
import logging, verboselogs
logger = verboselogs.VerboseLogger(__name__)
from src.utils.rest import (rest_get, rest_delete, rest_post)
import json
from src.utils.nest_functions import (add_keys_nested_dict, nested_get)
import sys, os

class Deleted_Downloads:
    # Keeps track of which downloads have already been deleted (to not double-delete)
    def __init__(self, dict):
        self.dict = dict

async def get_queue(BASE_URL, API_KEY, params = {}):
    await rest_post(url=BASE_URL+'/command', json={'name': 'RefreshMonitoredDownloads'}, headers={'X-Api-Key': API_KEY})
    totalRecords = (await rest_get(f'{BASE_URL}/queue', API_KEY, params))['totalRecords']
    if totalRecords == 0:
        return None
    queue = await rest_get(f'{BASE_URL}/queue', API_KEY, {'page': '1', 'pageSize': totalRecords}|params) 
    return queue

async def remove_failed(settings_dict, radarr_or_sonarr, BASE_URL, API_KEY, deleted_downloads):
    # Detects failed and triggers delete. Does not add to blocklist
    queue = await get_queue(BASE_URL, API_KEY)
    if not queue: return 0
    failedItems = []    
    for queueItem in queue['records']:
        if 'errorMessage' in queueItem and 'status' in queueItem:
            if  queueItem['status']       == 'failed' or \
               (queueItem['status']       == 'warning' and queueItem['errorMessage'] == 'The download is missing files'):
                await remove_download(BASE_URL, API_KEY, queueItem['id'], queueItem['title'], queueItem['downloadId'], 'failed', False, deleted_downloads, settings_dict['TEST_RUN'])
                failedItems.append(queueItem)
    return len(failedItems)

async def remove_stalled(settings_dict, radarr_or_sonarr, BASE_URL, API_KEY, deleted_downloads, defective_tracker):
    # Detects stalled and triggers repeat check and subsequent delete. Adds to blocklist   
    queue = await get_queue(BASE_URL, API_KEY)
    if not queue: return 0    
    logger.debug('remove_stalled/queue: %s', str(queue))
    if settings_dict['QBITTORRENT_URL']:
        protected_dowloadItems = await rest_get(settings_dict['QBITTORRENT_URL']+'/torrents/info',params={'tag': settings_dict['NO_STALLED_REMOVAL_QBIT_TAG']}, cookies=settings_dict['QBIT_COOKIE']  )
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
    await check_permitted_attempts(settings_dict, stalledItems, 'stalled', True, deleted_downloads, BASE_URL, API_KEY, defective_tracker)
    return len(stalledItems)

async def test_remove_ALL(settings_dict, radarr_or_sonarr, BASE_URL, API_KEY, deleted_downloads, defective_tracker):
    # Detects stalled and triggers repeat check and subsequent delete. Adds to blocklist   
    queue = await get_queue(BASE_URL, API_KEY)
    if not queue: return 0    
    logger.debug('remove_stalled_test/queue: %s', str(queue))
    if settings_dict['QBITTORRENT_URL']:
        protected_dowloadItems = await rest_get(settings_dict['QBITTORRENT_URL']+'/torrents/info',params={'tag': settings_dict['NO_STALLED_REMOVAL_QBIT_TAG']}, cookies=settings_dict['QBIT_COOKIE']  )
        protected_downloadIDs = [str.upper(item['hash']) for item in protected_dowloadItems]
    else:
        protected_downloadIDs = []
    stalledItems = []    
    for queueItem in queue['records']:
        stalledItems.append(queueItem)
    await check_permitted_attempts(settings_dict, stalledItems, 'stalled', True, deleted_downloads, BASE_URL, API_KEY, defective_tracker)
    return len(stalledItems)


async def remove_metadata_missing(settings_dict, radarr_or_sonarr, BASE_URL, API_KEY, deleted_downloads, defective_tracker):
    # Detects downloads stuck downloading meta data and triggers repeat check and subsequent delete. Adds to blocklist  
    queue = await get_queue(BASE_URL, API_KEY)
    if not queue: return 0    
    logger.debug('remove_metadata_missing/queue: %s', str(queue))
    missing_metadataItems = []
    for queueItem in queue['records']:
        if 'errorMessage' in queueItem and 'status' in queueItem:
            if  queueItem['status']        == 'queued' and \
                queueItem['errorMessage']  == 'qBittorrent is downloading metadata':
                    missing_metadataItems.append(queueItem)
    await check_permitted_attempts(settings_dict, missing_metadataItems, 'missing metadata', True, deleted_downloads, BASE_URL, API_KEY, defective_tracker)
    return len(missing_metadataItems)

async def remove_orphans(settings_dict, radarr_or_sonarr, BASE_URL, API_KEY, deleted_downloads):
    # Removes downloads belonging to movies/tv shows that have been deleted in the meantime
    full_queue = await get_queue(BASE_URL, API_KEY, params = {'includeUnknownMovieItems' if radarr_or_sonarr == 'radarr' else 'includeUnknownSeriesItems': 'true'})
    if not full_queue: return 0 # By now the queue may be empty 
    queue = await get_queue(BASE_URL, API_KEY) 
    full_queue_items = [{'id': queueItem['id'], 'title': queueItem['title'], 'downloadId': queueItem['downloadId']} for queueItem in full_queue['records']]
    if queue:
        queue_ids = [queueItem['id'] for queueItem in queue['records']]
    else:
        queue_ids = []
    orphanItems = [{'id': queueItem['id'], 'title': queueItem['title'], 'downloadId': queueItem['downloadId']} for queueItem in full_queue_items if queueItem['id'] not in queue_ids]
    for queueItem in orphanItems:
        await remove_download(settings_dict, BASE_URL, API_KEY, queueItem['id'], queueItem['title'], queueItem['downloadId'], 'orphan', False, deleted_downloads)
    return len(orphanItems)

async def remove_unmonitored(settings_dict, radarr_or_sonarr, BASE_URL, API_KEY, deleted_downloads):
    # Removes downloads belonging to movies/tv shows that are not monitored
    queue = await get_queue(BASE_URL, API_KEY) 
    if not queue: return 0
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
        await remove_download(settings_dict, BASE_URL, API_KEY, queueItem['id'], queueItem['title'], queueItem['downloadId'], 'unmonitored', False, deleted_downloads)
    return len(unmonitoredItems)

async def check_permitted_attempts(settings_dict, current_defective_items, failType, blocklist, deleted_downloads, BASE_URL, API_KEY, defective_tracker):
    # Checks if downloads are repeatedly found as stalled / stuck in metadata and if yes, deletes them
    # 1. Create list of currently defective
    current_defective = {}
    for queueItem in current_defective_items:
        current_defective[queueItem['id']] = {'title': queueItem['title'],'downloadId': queueItem['downloadId']}
    logger.debug('check_permitted_attempts/current_defective: %s', str(current_defective))
    # 2. Check if those that were previously defective are no longer defective -> those are recovered
    try:
        recovered_ids = [tracked_id for tracked_id in defective_tracker.dict[BASE_URL][failType] if tracked_id not in current_defective]
    except KeyError:
        recovered_ids = []
    logger.debug('check_permitted_attempts/recovered_ids: %s' + str(recovered_ids))
    for recovered_id in recovered_ids:
       del defective_tracker.dict[BASE_URL][failType][recovered_id]
    logger.debug('check_permitted_attempts/defective_tracker.dict IN: %s', str(defective_tracker.dict))
    # 3. For those that are defective, add attempt + 1 if present before, or make attempt = 0. If exceeding number of permitted attempts, delete hem
    download_ids_stuck = []
    for queueId in current_defective:
        try: 
            defective_tracker.dict[BASE_URL][failType][queueId]['Attempts'] += 1
        except KeyError:
            await add_keys_nested_dict(defective_tracker.dict,[BASE_URL, failType, queueId], {'title': current_defective[queueId]['title'], 'downloadId': current_defective[queueId]['downloadId'], 'Attempts': 1})
        if current_defective[queueId]['downloadId'] not in download_ids_stuck:
            download_ids_stuck.append(current_defective[queueId]['downloadId'])
            logger.info('>>> Detected %s download (%s out of %s permitted times): %s', failType, str(defective_tracker.dict[BASE_URL][failType][queueId]['Attempts']), str(settings_dict['PERMITTED_ATTEMPTS']), defective_tracker.dict[BASE_URL][failType][queueId]['title'])
        if defective_tracker.dict[BASE_URL][failType][queueId]['Attempts'] > settings_dict['PERMITTED_ATTEMPTS']:
            await remove_download(settings_dict, BASE_URL, API_KEY, queueId, current_defective[queueId]['title'], current_defective[queueId]['downloadId'],  failType, blocklist, deleted_downloads)
    logger.debug('check_permitted_attempts/defective_tracker.dict OUT: %s', str(defective_tracker.dict))
    return

async def remove_download(settings_dict, BASE_URL, API_KEY, queueId, queueTitle, downloadId, failType, blocklist, deleted_downloads):
    # Removes downloads and creates log entry
    logger.debug('remove_download/deleted_downloads.dict IN: %s' + str(deleted_downloads.dict)) 
    if downloadId not in deleted_downloads.dict:
        logger.info('>>> Removing %s download: %s', failType, queueTitle)
        if not settings_dict['TEST_RUN']: await rest_delete(f'{BASE_URL}/queue/{queueId}', API_KEY, {'removeFromClient': True, 'blocklist': blocklist}) 
        deleted_downloads.dict.append(downloadId)   
    
    logger.debug('remove_download/deleted_downloads.dict OUT: %s' + str(deleted_downloads.dict)) 
    return

########### MAIN FUNCTION ###########
async def queue_cleaner(settings_dict, radarr_or_sonarr, defective_tracker):
    # Read out correct instance depending on radarr/sonarr flag
    run_dict = {}
    if radarr_or_sonarr == 'radarr':
        BASE_URL    = settings_dict['RADARR_URL']
        API_KEY     = settings_dict['RADARR_KEY']
        NAME        = settings_dict['RADARR_NAME']
    else:
        BASE_URL    = settings_dict['SONARR_URL']
        API_KEY     = settings_dict['SONARR_KEY']
        NAME        = settings_dict['SONARR_NAME']

    # Cleans up the downloads queue
    logger.verbose('Cleaning queue on %s:', NAME)
    try:
        full_queue = await get_queue(BASE_URL, API_KEY, params = {'includeUnknownMovieItems' if radarr_or_sonarr == 'radarr' else 'includeUnknownSeriesItems': 'true'})
        if not full_queue: 
            logger.verbose('>>> Queue is empty.')
            return
              
        deleted_downloads = Deleted_Downloads([])
        items_detected = 0

        #items_detected += await test_remove_ALL(           settings_dict, radarr_or_sonarr, BASE_URL, API_KEY, deleted_downloads, defective_tracker)

        if settings_dict['REMOVE_FAILED']:
            items_detected += await remove_failed(            settings_dict, radarr_or_sonarr, BASE_URL, API_KEY, deleted_downloads)
        
        if settings_dict['REMOVE_STALLED']: 
            items_detected += await remove_stalled(           settings_dict, radarr_or_sonarr, BASE_URL, API_KEY, deleted_downloads, defective_tracker)

        if settings_dict['REMOVE_METADATA_MISSING']: 
            items_detected += await remove_metadata_missing(  settings_dict, radarr_or_sonarr, BASE_URL, API_KEY, deleted_downloads, defective_tracker)

        if settings_dict['REMOVE_ORPHANS']: 
            items_detected += await remove_orphans(           settings_dict, radarr_or_sonarr, BASE_URL, API_KEY, deleted_downloads)

        if settings_dict['REMOVE_UNMONITORED']: 
            items_detected += await remove_unmonitored(       settings_dict, radarr_or_sonarr, BASE_URL, API_KEY, deleted_downloads)

        if items_detected == 0:
            logger.verbose('>>> Queue is clean.')
    except Exception as error:
            exc_type, exc_obj, exc_tb = sys.exc_info()
            fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
            logger.warning('>>> Queue cleaning failed on %s. (File: %s / Line: %s / Error Message: %s / Error Type: %s)', NAME, fname, exc_tb.tb_lineno, error, exc_type)



