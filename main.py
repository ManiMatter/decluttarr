########### Import Libraries
import asyncio
import logging, verboselogs
from src.utils.rest import (rest_get)
from requests.exceptions import RequestException
import json
from dateutil.relativedelta import relativedelta as rd
from config.config import (
    IS_IN_DOCKER, 
    LOG_LEVEL, TEST_RUN,
    REMOVE_TIMER, REMOVE_FAILED, REMOVE_STALLED, REMOVE_METADATA_MISSING, REMOVE_ORPHANS, REMOVE_UNMONITORED, PERMITTED_ATTEMPTS, NO_STALLED_REMOVAL_QBIT_TAG,
    RADARR_URL, RADARR_KEY,
    SONARR_URL, SONARR_KEY,
    QBITTORRENT_URL
)
from src.queue_cleaner import (queue_cleaner)

########### Enabling Logging
# Set up logging
log_level_num=logging.getLevelName(LOG_LEVEL)
logger = verboselogs.VerboseLogger(__name__)
logging.basicConfig(
    format=('' if IS_IN_DOCKER else '%(asctime)s ') + ('[%(levelname)-7s]' if LOG_LEVEL=='VERBOSE' else '[%(levelname)s]') + ': %(message)s', 
    level=log_level_num 
)


class Defective_Tracker:
    # Keeps track of which downloads were already caught as stalled previously
    def __init__(self, dict):
        self.dict = dict

# Main function
async def main():
    # Get name of Radarr / Sonarr instances
    if RADARR_URL:
        RADARR_NAME = (await rest_get(RADARR_URL+'/system/status', RADARR_KEY))['instanceName']
    if SONARR_URL:
        SONARR_NAME = (await rest_get(SONARR_URL+'/system/status', SONARR_KEY))['instanceName']
 
    # Print Settings
    fmt = '{0.days} days {0.hours} hours {0.minutes} minutes'
    logger.info('#' * 50)
    logger.info('Application Started!')
    logger.info('')      
    logger.info('*** Current Settings ***') 
    logger.info('%s | Removing failed downloads', str(REMOVE_FAILED))
    logger.info('%s | Removing stalled downloads', str(REMOVE_STALLED))
    logger.info('%s | Removing downloads missing metadata', str(REMOVE_METADATA_MISSING))
    logger.info('%s | Removing orphan downloads', str(REMOVE_ORPHANS))
    logger.info('%s | Removing downloads belonging to unmonitored TV shows/movies', str(REMOVE_UNMONITORED))
    logger.info('Running every %s.', fmt.format(rd(minutes=REMOVE_TIMER)))           
    logger.info('') 
    logger.info('*** Configured Instances ***')
    if RADARR_URL: logger.info('%s: %s', RADARR_NAME, RADARR_URL)
    if SONARR_URL: logger.info('%s: %s', SONARR_NAME, SONARR_URL)    
    if QBITTORRENT_URL: logger.info('qBittorrent: %s', QBITTORRENT_URL)    
    logger.info('') 
    logger.info('#' * 50)
    if LOG_LEVEL == 'INFO':
        logger.info('[LOG_LEVEL = INFO]: Only logging changes (switch to VERBOSE for more info)')      
    else:
        logger.info(f'')
    if TEST_RUN:
        logger.info(f'*'* 50)
        logger.info(f'*'* 50)
        logger.info(f'')
        logger.info(f'TEST_RUN FLAG IS SET!')       
        logger.info(f'THIS IS A TEST RUN AND NO UPDATES/DELETES WILL BE PERFORMED')
        logger.info(f'')
        logger.info(f'*'* 50)
        logger.info(f'*'* 50)

    # Start application
    while True:
        logger.verbose('-' * 50)
        if RADARR_URL: await queue_cleaner('radarr', RADARR_URL, RADARR_KEY, RADARR_NAME, REMOVE_FAILED, REMOVE_STALLED, REMOVE_METADATA_MISSING, REMOVE_ORPHANS, REMOVE_UNMONITORED, PERMITTED_ATTEMPTS, NO_STALLED_REMOVAL_QBIT_TAG, QBITTORRENT_URL, defective_tracker, TEST_RUN)
        if SONARR_URL: await queue_cleaner('sonarr', SONARR_URL, SONARR_KEY, SONARR_NAME, REMOVE_FAILED, REMOVE_STALLED, REMOVE_METADATA_MISSING, REMOVE_ORPHANS, REMOVE_UNMONITORED, PERMITTED_ATTEMPTS, NO_STALLED_REMOVAL_QBIT_TAG, QBITTORRENT_URL, defective_tracker, TEST_RUN)
        logger.verbose('')  
        logger.verbose('Queue clean-up complete!')  
        await asyncio.sleep(REMOVE_TIMER*60)

    return

if __name__ == '__main__':
    instances = {RADARR_URL: {}} if RADARR_URL else {} + \
                {SONARR_URL: {}} if SONARR_URL else {} 
    defective_tracker = Defective_Tracker(instances)
    asyncio.run(main())

