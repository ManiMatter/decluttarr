# Cleans the download queue
import logging, verboselogs
logger = verboselogs.VerboseLogger(__name__)
from src.utils.shared import (errorDetails, get_queue)
from src.remove_failed import remove_failed
from src.remove_metadata_missing import remove_metadata_missing
from src.remove_missing_files import remove_missing_files
from src.remove_orphans import remove_orphans
from src.remove_slow import remove_slow
from src.remove_stalled import remove_stalled
from src.remove_unmonitored import remove_unmonitored

class Deleted_Downloads:
    # Keeps track of which downloads have already been deleted (to not double-delete)
    def __init__(self, dict):
        self.dict = dict


async def queueCleaner(settings_dict, arr_type, defective_tracker, download_sizes_tracker, protectedDownloadIDs, privateDowloadIDs):
    # Read out correct instance depending on radarr/sonarr flag
    run_dict = {}
    if arr_type == 'radarr':
        BASE_URL    = settings_dict['RADARR_URL']
        API_KEY     = settings_dict['RADARR_KEY']
        NAME        = settings_dict['RADARR_NAME']
        full_queue_param = 'includeUnknownMovieItems'
    elif arr_type == 'sonarr':
        BASE_URL    = settings_dict['SONARR_URL']
        API_KEY     = settings_dict['SONARR_KEY']
        NAME        = settings_dict['SONARR_NAME']
        full_queue_param = 'includeUnknownSeriesItems'
    elif arr_type == 'lidarr':
        BASE_URL    = settings_dict['LIDARR_URL']
        API_KEY     = settings_dict['LIDARR_KEY']
        NAME        = settings_dict['LIDARR_NAME']
        full_queue_param = 'includeUnknownArtistItems'
    else:
        logger.error('Unknown arr_type specified, exiting: %s', str(arr_type))
        sys.exit()
        
    # Cleans up the downloads queue
    logger.verbose('Cleaning queue on %s:', NAME)

    full_queue = await get_queue(BASE_URL, API_KEY, params = {full_queue_param: True})
    if not full_queue: 
        logger.verbose('>>> Queue is empty.')
        return
        
    deleted_downloads = Deleted_Downloads([])
    items_detected = 0
    try:    
        if settings_dict['REMOVE_FAILED']:
            items_detected += await remove_failed(            settings_dict, BASE_URL, API_KEY, NAME, deleted_downloads, defective_tracker, protectedDownloadIDs, privateDowloadIDs)
        
        if settings_dict['REMOVE_STALLED']: 
            items_detected += await remove_stalled(           settings_dict, BASE_URL, API_KEY, NAME, deleted_downloads, defective_tracker, protectedDownloadIDs, privateDowloadIDs)

        if settings_dict['REMOVE_METADATA_MISSING']: 
            items_detected += await remove_metadata_missing(  settings_dict, BASE_URL, API_KEY, NAME, deleted_downloads, defective_tracker, protectedDownloadIDs, privateDowloadIDs)

        if settings_dict['REMOVE_ORPHANS']: 
            items_detected += await remove_orphans(           settings_dict, BASE_URL, API_KEY, NAME, deleted_downloads, defective_tracker, protectedDownloadIDs, privateDowloadIDs, full_queue_param)

        if settings_dict['REMOVE_UNMONITORED']: 
            items_detected += await remove_unmonitored(       settings_dict, BASE_URL, API_KEY, NAME, deleted_downloads, defective_tracker, protectedDownloadIDs, privateDowloadIDs, arr_type)

        if settings_dict['REMOVE_MISSING_FILES']: 
            items_detected += await remove_missing_files(     settings_dict, BASE_URL, API_KEY, NAME, deleted_downloads, defective_tracker, protectedDownloadIDs, privateDowloadIDs)

        if settings_dict['REMOVE_SLOW']:
            items_detected += await remove_slow(              settings_dict, BASE_URL, API_KEY, NAME, deleted_downloads, defective_tracker, protectedDownloadIDs, privateDowloadIDs, download_sizes_tracker)

        if items_detected == 0:
            logger.verbose('>>> Queue is clean.')
    except Exception as error:
        errorDetails(NAME, error)
    return