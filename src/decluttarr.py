# Cleans the download queue
import logging, verboselogs
logger = verboselogs.VerboseLogger(__name__)
from src.utils.shared import (errorDetails, get_queue)
from src.jobs.remove_failed import remove_failed
from src.jobs.remove_failed_imports import remove_failed_imports
from src.jobs.remove_metadata_missing import remove_metadata_missing
from src.jobs.remove_missing_files import remove_missing_files
from src.jobs.remove_orphans import remove_orphans
from src.jobs.remove_slow import remove_slow
from src.jobs.remove_stalled import remove_stalled
from src.jobs.remove_unmonitored import remove_unmonitored
from src.jobs.cancel_unavailable_files import cancel_unavailable_files
from src.utils.trackers import Deleted_Downloads

async def queueCleaner(settingsDict, arr_type, defective_tracker, download_sizes_tracker, protectedDownloadIDs, privateDowloadIDs):
    # Read out correct instance depending on radarr/sonarr flag
    run_dict = {}
    if arr_type == 'RADARR':
        BASE_URL    = settingsDict['RADARR_URL']
        API_KEY     = settingsDict['RADARR_KEY']
        NAME        = settingsDict['RADARR_NAME']
        full_queue_param = 'includeUnknownMovieItems'
    elif arr_type == 'SONARR':
        BASE_URL    = settingsDict['SONARR_URL']
        API_KEY     = settingsDict['SONARR_KEY']
        NAME        = settingsDict['SONARR_NAME']
        full_queue_param = 'includeUnknownSeriesItems'
    elif arr_type == 'LIDARR':
        BASE_URL    = settingsDict['LIDARR_URL']
        API_KEY     = settingsDict['LIDARR_KEY']
        NAME        = settingsDict['LIDARR_NAME']
        full_queue_param = 'includeUnknownArtistItems'
    elif arr_type == 'READARR':
        BASE_URL    = settingsDict['READARR_URL']
        API_KEY     = settingsDict['READARR_KEY']
        NAME        = settingsDict['READARR_NAME']
        full_queue_param = 'includeUnknownAuthorItems'   
    elif arr_type == 'WHISPARR':
        BASE_URL    = settingsDict['WHISPARR_URL']
        API_KEY     = settingsDict['WHISPARR_KEY']
        NAME        = settingsDict['WHISPARR_NAME']
        full_queue_param = 'includeUnknownSeriesItems'      
    else:
        logger.error('Unknown arr_type specified, exiting: %s', str(arr_type))
        sys.exit()
        
    # Cleans up the downloads queue
    logger.verbose('Cleaning queue on %s:', NAME)
    # Refresh queue:
    
    full_queue = await get_queue(BASE_URL, API_KEY, params = {full_queue_param: True})
    if not full_queue: 
        logger.verbose('>>> Queue is empty.')
        return
    else:
        logger.debug('queueCleaner/full_queue at start:')
        logger.debug(full_queue)        
        
    deleted_downloads = Deleted_Downloads([])
    items_detected = 0
    try:   
        if settingsDict['CANCEL_UNAVAILABLE_FILES']: 
            await cancel_unavailable_files(                   settingsDict, BASE_URL, API_KEY, NAME, protectedDownloadIDs, privateDowloadIDs, arr_type)

        if settingsDict['REMOVE_FAILED']:
            items_detected += await remove_failed(            settingsDict, BASE_URL, API_KEY, NAME, deleted_downloads, defective_tracker, protectedDownloadIDs, privateDowloadIDs)

        if settingsDict['REMOVE_FAILED_IMPORTS']: 
            items_detected += await remove_failed_imports(    settingsDict, BASE_URL, API_KEY, NAME, deleted_downloads, defective_tracker, protectedDownloadIDs, privateDowloadIDs)

        if settingsDict['REMOVE_METADATA_MISSING']: 
            items_detected += await remove_metadata_missing(  settingsDict, BASE_URL, API_KEY, NAME, deleted_downloads, defective_tracker, protectedDownloadIDs, privateDowloadIDs)

        if settingsDict['REMOVE_MISSING_FILES']: 
            items_detected += await remove_missing_files(     settingsDict, BASE_URL, API_KEY, NAME, deleted_downloads, defective_tracker, protectedDownloadIDs, privateDowloadIDs)

        if settingsDict['REMOVE_ORPHANS']: 
            items_detected += await remove_orphans(           settingsDict, BASE_URL, API_KEY, NAME, deleted_downloads, defective_tracker, protectedDownloadIDs, privateDowloadIDs, full_queue_param)

        if settingsDict['REMOVE_SLOW']:
            items_detected += await remove_slow(              settingsDict, BASE_URL, API_KEY, NAME, deleted_downloads, defective_tracker, protectedDownloadIDs, privateDowloadIDs, download_sizes_tracker)

        if settingsDict['REMOVE_STALLED']: 
            items_detected += await remove_stalled(           settingsDict, BASE_URL, API_KEY, NAME, deleted_downloads, defective_tracker, protectedDownloadIDs, privateDowloadIDs)

        if settingsDict['REMOVE_UNMONITORED']: 
            items_detected += await remove_unmonitored(       settingsDict, BASE_URL, API_KEY, NAME, deleted_downloads, defective_tracker, protectedDownloadIDs, privateDowloadIDs, arr_type)

        if items_detected == 0:
            logger.verbose('>>> Queue is clean.')
    except Exception as error:
        errorDetails(NAME, error)
    return
