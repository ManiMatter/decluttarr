########### Import Libraries
import asyncio
import logging, verboselogs
from src.utils.rest import rest_get, rest_post
from requests.exceptions import RequestException
import json
from dateutil.relativedelta import relativedelta as rd
from config.config import settings_dict
from src.decluttarr import queueCleaner
#print(json.dumps(settings_dict,indent=4))
import requests
import platform
from packaging import version

# Hide SSL Verification Warnings
if settings_dict['SSL_VERIFICATION']==False:
    import warnings
    warnings.filterwarnings("ignore", message="Unverified HTTPS request")

########### Enabling Logging
# Set up logging
log_level_num=logging.getLevelName(settings_dict['LOG_LEVEL'])
logger = verboselogs.VerboseLogger(__name__)
logging.basicConfig(
    format=('' if settings_dict['IS_IN_DOCKER'] else '%(asctime)s ') + ('[%(levelname)-7s]' if settings_dict['LOG_LEVEL']=='VERBOSE' else '[%(levelname)s]') + ': %(message)s', 
    level=log_level_num 
)

class Defective_Tracker:
    # Keeps track of which downloads were already caught as stalled previously
    def __init__(self, dict):
        self.dict = dict
class Download_Sizes_Tracker:
    # Keeps track of the file sizes of the downloads
    def __init__(self, dict):
        self.dict = dict

# Main function
async def main():
    # Get name of Radarr / Sonarr instances
    try:
        if settings_dict['RADARR_URL']:
            settings_dict['RADARR_NAME'] = (await rest_get(settings_dict['RADARR_URL']+'/system/status', settings_dict['RADARR_KEY']))['instanceName']
    except:
            settings_dict['RADARR_NAME'] = 'Radarr'
    try:
        if settings_dict['SONARR_URL']:
            settings_dict['SONARR_NAME'] = (await rest_get(settings_dict['SONARR_URL']+'/system/status', settings_dict['SONARR_KEY']))['instanceName']
    except:
        settings_dict['SONARR_NAME'] = 'Sonarr'

    try:
        if settings_dict['LIDARR_URL']:
            settings_dict['LIDARR_NAME'] = (await rest_get(settings_dict['LIDARR_URL']+'/system/status', settings_dict['LIDARR_KEY']))['instanceName']
    except:
        settings_dict['LIDARR_NAME'] = 'Lidarr'

    try:
        if settings_dict['READARR_URL']:
            settings_dict['READARR_NAME'] = (await rest_get(settings_dict['READARR_URL']+'/system/status', settings_dict['READARR_KEY']))['instanceName']
    except:
        settings_dict['READARR_NAME'] = 'Readarr'

    # Print Settings
    fmt = '{0.days} days {0.hours} hours {0.minutes} minutes'
    logger.info('#' * 50)
    logger.info('Decluttarr - Application Started!')
    logger.info('')      
    logger.info('*** Current Settings ***') 
    logger.info('Version: %s', settings_dict['IMAGE_TAG']) 
    logger.info('Commit: %s', settings_dict['SHORT_COMMIT_ID'])    
    logger.info('')       
    logger.info('%s | Removing failed downloads', str(settings_dict['REMOVE_FAILED']))
    logger.info('%s | Removing downloads missing metadata', str(settings_dict['REMOVE_METADATA_MISSING'])) 
    logger.info('%s | Removing downloads missing files', str(settings_dict['REMOVE_MISSING_FILES']))
    logger.info('%s | Removing orphan downloads', str(settings_dict['REMOVE_ORPHANS']))  
    logger.info('%s | Removing slow downloads', str(settings_dict['REMOVE_SLOW']))
    logger.info('%s | Removing stalled downloads', str(settings_dict['REMOVE_STALLED']))
    logger.info('%s | Removing downloads belonging to unmonitored TV shows/movies', str(settings_dict['REMOVE_UNMONITORED'])) 
    logger.info('')          
    logger.info('Running every: %s', fmt.format(rd(minutes=settings_dict['REMOVE_TIMER'])))  
    if settings_dict['REMOVE_SLOW']: 
        logger.info('Minimum speed enforced: %s KB/s', str(settings_dict['MIN_DOWNLOAD_SPEED'])) 
    logger.info('Permitted number of times before stalled/missing metadata/slow downloads are removed: %s', str(settings_dict['PERMITTED_ATTEMPTS']))      
    if settings_dict['QBITTORRENT_URL']: 
        logger.info('Downloads with this tag will be skipped: \"%s\"', settings_dict['NO_STALLED_REMOVAL_QBIT_TAG'])  
        logger.info('Private Trackers will be skipped: %s', settings_dict['IGNORE_PRIVATE_TRACKERS'])        
    
    logger.info('') 
    logger.info('*** Configured Instances ***')
    if settings_dict['RADARR_URL']: logger.info('%s: %s', settings_dict['RADARR_NAME'], settings_dict['RADARR_URL'])
    if settings_dict['SONARR_URL']: logger.info('%s: %s', settings_dict['SONARR_NAME'], settings_dict['SONARR_URL'])   
    if settings_dict['LIDARR_URL']: logger.info('%s: %s', settings_dict['LIDARR_NAME'], settings_dict['LIDARR_URL'])    
    if settings_dict['READARR_URL']: logger.info('%s: %s', settings_dict['READARR_NAME'], settings_dict['READARR_URL'])    
    if settings_dict['QBITTORRENT_URL']: logger.info('qBittorrent: %s', settings_dict['QBITTORRENT_URL'])    

    logger.info('') 
    logger.info('*** Check Instances ***')
    if settings_dict['RADARR_URL']:
        error_occured = False
        try: 
            await asyncio.get_event_loop().run_in_executor(None, lambda: requests.get(settings_dict['RADARR_URL']+'/system/status', params=None, headers={'X-Api-Key': settings_dict['RADARR_KEY']}, verify=settings_dict['SSL_VERIFICATION']))
        except Exception as error:
            error_occured = True
            logger.error('-- | %s *** Error: %s ***', settings_dict['RADARR_NAME'], error)
        if not error_occured:
            radarr_version = (await rest_get(settings_dict['RADARR_URL']+'/system/status', settings_dict['RADARR_KEY']))['version']
            if version.parse(radarr_version) < version.parse('5.3.6.8608'):
                error_occured = True
                logger.error('-- | %s *** Error: %s ***', settings_dict['RADARR_NAME'], 'Please update Radarr to at least version 5.3.6.8608. Current version: ' + radarr_version)
        if not error_occured:
            logger.info('OK | %s', settings_dict['RADARR_NAME'])

    if settings_dict['SONARR_URL']:
        try: 
            await asyncio.get_event_loop().run_in_executor(None, lambda: requests.get(settings_dict['SONARR_URL']+'/system/status', params=None, headers={'X-Api-Key': settings_dict['SONARR_KEY']}, verify=settings_dict['SSL_VERIFICATION']))
        except Exception as error:
            error_occured = True
            logger.error('-- | %s *** Error: %s ***', settings_dict['SONARR_NAME'], error)
        if not error_occured:
            sonarr_version = (await rest_get(settings_dict['SONARR_URL']+'/system/status', settings_dict['SONARR_KEY']))['version']
            if version.parse(sonarr_version) < version.parse('4.0.1.1131'):
                error_occured = True
                logger.error('-- | %s *** Error: %s ***', settings_dict['SONARR_NAME'], 'Please update Sonarr to at least version 4.0.1.1131. Current version: ' + sonarr_version)
        if not error_occured:
            logger.info('OK | %s', settings_dict['SONARR_NAME'])

    if settings_dict['LIDARR_URL']:
        try: 
            await asyncio.get_event_loop().run_in_executor(None, lambda: requests.get(settings_dict['LIDARR_URL']+'/system/status', params=None, headers={'X-Api-Key': settings_dict['LIDARR_KEY']}, verify=settings_dict['SSL_VERIFICATION']))
            logger.info('OK | %s', settings_dict['LIDARR_NAME'])
        except Exception as error:
            error_occured = True
            logger.error('-- | %s *** Error: %s ***', settings_dict['LIDARR_NAME'], error)

    if settings_dict['READARR_URL']:
        try: 
            await asyncio.get_event_loop().run_in_executor(None, lambda: requests.get(settings_dict['READARR_URL']+'/system/status', params=None, headers={'X-Api-Key': settings_dict['READARR_KEY']}, verify=settings_dict['SSL_VERIFICATION']))
            logger.info('OK | %s', settings_dict['READARR_NAME'])
        except Exception as error:
            error_occured = True
            logger.error('-- | %s *** Error: %s ***', settings_dict['READARR_NAME'], error)

    if settings_dict['QBITTORRENT_URL']:
        # Checking if qbit can be reached, and checking if version is OK
        try: 
            response = await asyncio.get_event_loop().run_in_executor(None, lambda: requests.post(settings_dict['QBITTORRENT_URL']+'/auth/login', data={'username': settings_dict['QBITTORRENT_USERNAME'], 'password': settings_dict['QBITTORRENT_PASSWORD']}, headers={'content-type': 'application/x-www-form-urlencoded'}, verify=settings_dict['SSL_VERIFICATION']))
            if response.text == 'Fails.':
                raise ConnectionError('Login failed.')
            response.raise_for_status()
            settings_dict['QBIT_COOKIE'] = {'SID': response.cookies['SID']} 
        except Exception as error:
            error_occured = True
            logger.error('-- | %s *** Error: %s / Reponse: %s ***', 'qBittorrent', error, response.text)

        if not error_occured:
            qbit_version = await rest_get(settings_dict['QBITTORRENT_URL']+'/app/version',cookies=settings_dict['QBIT_COOKIE'])
            qbit_version = qbit_version[1:] # version without _v
            if version.parse(qbit_version) < version.parse('4.6.3'):
                error_occured = True
                logger.error('-- | %s *** Error: %s ***', 'qBittorrent', 'Please update qBittorrent to at least version 4.6.0. Current version: ' + qbit_version)

        if not error_occured:
            logger.info('OK | %s', 'qBittorrent')


    if error_occured:
        logger.warning('At least one instance was not reachable. Waiting for 60 seconds, then exiting Decluttarr.')      
        await asyncio.sleep(60)
        exit()

    logger.info('') 
    logger.info('#' * 50)
    if settings_dict['LOG_LEVEL'] == 'INFO':
        logger.info('LOG_LEVEL = INFO: Only logging changes (switch to VERBOSE for more info)')      
    else:
        logger.info(f'')
    if settings_dict['TEST_RUN']:
        logger.info(f'*'* 50)
        logger.info(f'*'* 50)
        logger.info(f'')
        logger.info(f'!! TEST_RUN FLAG IS SET !!')       
        logger.info(f'NO UPDATES/DELETES WILL BE PERFORMED')
        logger.info(f'')
        logger.info(f'*'* 50)
        logger.info(f'*'* 50)

    # Check if Qbit Tag exists:
    if settings_dict['QBITTORRENT_URL']:
        current_tags = await rest_get(settings_dict['QBITTORRENT_URL']+'/torrents/tags',cookies=settings_dict['QBIT_COOKIE'])
        if not settings_dict['NO_STALLED_REMOVAL_QBIT_TAG'] in current_tags:
            if settings_dict['QBITTORRENT_URL']: 
                logger.info('Creating tag in qBittorrent: %s', settings_dict['NO_STALLED_REMOVAL_QBIT_TAG'])  
                if not settings_dict['TEST_RUN']:
                    await rest_post(url=settings_dict['QBITTORRENT_URL']+'/torrents/createTags', data={'tags': settings_dict['NO_STALLED_REMOVAL_QBIT_TAG']}, headers={'content-type': 'application/x-www-form-urlencoded'}, cookies=settings_dict['QBIT_COOKIE'])

    # Start application
    while True:
        logger.verbose('-' * 50)
        # Cache protected (via Tag) and private torrents 
        protectedDownloadIDs = []
        privateDowloadIDs = []
        if settings_dict['QBITTORRENT_URL']:
            protectedDowloadItems = await rest_get(settings_dict['QBITTORRENT_URL']+'/torrents/info',params={'tag': settings_dict['NO_STALLED_REMOVAL_QBIT_TAG']}, cookies=settings_dict['QBIT_COOKIE']  )
            protectedDownloadIDs = [str.upper(item['hash']) for item in protectedDowloadItems]
            if settings_dict['IGNORE_PRIVATE_TRACKERS']:
                privateDowloadItems = await rest_get(settings_dict['QBITTORRENT_URL']+'/torrents/info',params={}, cookies=settings_dict['QBIT_COOKIE']  )
                privateDowloadIDs = [str.upper(item['hash']) for item in privateDowloadItems if item.get('is_private', False)]

        if settings_dict['RADARR_URL']: await queueCleaner(settings_dict, 'radarr', defective_tracker, download_sizes_tracker, protectedDownloadIDs, privateDowloadIDs)
        if settings_dict['SONARR_URL']: await queueCleaner(settings_dict, 'sonarr', defective_tracker, download_sizes_tracker, protectedDownloadIDs, privateDowloadIDs)
        if settings_dict['LIDARR_URL']: await queueCleaner(settings_dict, 'lidarr', defective_tracker, download_sizes_tracker, protectedDownloadIDs, privateDowloadIDs)
        if settings_dict['READARR_URL']: await queueCleaner(settings_dict, 'readarr', defective_tracker, download_sizes_tracker, protectedDownloadIDs, privateDowloadIDs)
        logger.verbose('')  
        logger.verbose('Queue clean-up complete!')  
        await asyncio.sleep(settings_dict['REMOVE_TIMER']*60)
    return

if __name__ == '__main__':
    instances = {settings_dict['RADARR_URL']: {}} if settings_dict['RADARR_URL'] else {} + \
                {settings_dict['SONARR_URL']: {}} if settings_dict['SONARR_URL'] else {} + \
                {settings_dict['LIDARR_URL']: {}} if settings_dict['LIDARR_URL'] else {} + \
                {settings_dict['READARR_URL']: {}} if settings_dict['READARR_URL'] else {} 
    defective_tracker = Defective_Tracker(instances)
    download_sizes_tracker = Download_Sizes_Tracker({})
    asyncio.run(main())


