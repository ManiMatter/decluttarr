########### Import Libraries
import logging, verboselogs
logger = verboselogs.VerboseLogger(__name__)
from dateutil.relativedelta import relativedelta as rd
import requests 
from src.utils.rest import rest_get, rest_post # 
import asyncio
from packaging import version

def setLoggingFormat(settingsDict):
    # Sets logger output to specific format
    log_level_num=logging.getLevelName(settingsDict['LOG_LEVEL'])
    logging.basicConfig(
        format=('' if settingsDict['IS_IN_DOCKER'] else '%(asctime)s ') + ('[%(levelname)-7s]' if settingsDict['LOG_LEVEL']=='VERBOSE' else '[%(levelname)s]') + ': %(message)s', 
        level=log_level_num 
    )
    return 


async def getArrInstanceName(settingsDict, arrApp):
    # Retrieves the names of the arr instances, and if not defined, sets a default (should in theory not be requried, since UI already enforces a value)
    try:
        if settingsDict[arrApp + '_URL']:
            settingsDict[arrApp + '_NAME'] = (await rest_get(settingsDict[arrApp + '_URL']+'/system/status', settingsDict[arrApp + '_KEY']))['instanceName']
    except:
            settingsDict[arrApp + '_NAME'] = arrApp.title()
    return settingsDict

async def getProtectedAndPrivateFromQbit(settingsDict):
    # Returns two lists containing the hashes of Qbit that are either protected by tag, or are private trackers (if IGNORE_PRIVATE_TRACKERS is true)
    protectedDownloadIDs = []
    privateDowloadIDs = []
    if settingsDict['QBITTORRENT_URL']:
        # Fetch all torrents
        qbitItems = await rest_get(settingsDict['QBITTORRENT_URL']+'/torrents/info',params={}, cookies=settingsDict['QBIT_COOKIE'])
        # Fetch protected torrents (by tag)
        for qbitItem in qbitItems:
            if settingsDict['NO_STALLED_REMOVAL_QBIT_TAG'] in qbitItem.get('tags'):
                protectedDownloadIDs.append(str.upper(qbitItem['hash']))
        # Fetch private torrents
        if settingsDict['IGNORE_PRIVATE_TRACKERS']:
            for qbitItem in qbitItems:           
                qbitItemProperties = await rest_get(settingsDict['QBITTORRENT_URL']+'/torrents/properties',params={'hash': qbitItem['hash']}, cookies=settingsDict['QBIT_COOKIE'])
                qbitItem['is_private'] = qbitItemProperties.get('is_private', None) # Adds the is_private flag to qbitItem info for simplified logging
                if qbitItemProperties.get('is_private', False):
                    privateDowloadIDs.append(str.upper(qbitItem['hash']))
        logger.debug('main/getProtectedAndPrivateFromQbit/qbitItems: %s', str([{"hash": str.upper(item["hash"]), "name": item["name"], "category": item["category"], "tags": item["tags"], "is_private": item.get("is_private", None)} for item in qbitItems]))
    
    logger.debug('main/getProtectedAndPrivateFromQbit/protectedDownloadIDs: %s', str(protectedDownloadIDs))
    logger.debug('main/getProtectedAndPrivateFromQbit/privateDowloadIDs: %s', str(privateDowloadIDs))   

    return protectedDownloadIDs, privateDowloadIDs
    
def showWelcome():
    # Welcome Message
    logger.info('#' * 50)
    logger.info('Decluttarr - Application Started!')
    logger.info('')      
    logger.info('Like this app? Thanks for giving it a ⭐️ on GitHub!')      
    logger.info('https://github.com/ManiMatter/decluttarr/')   
    logger.info('')  
    return

def showSettings(settingsDict):
    # Settings Message
    fmt = '{0.days} days {0.hours} hours {0.minutes} minutes'     
    logger.info('*** Current Settings ***') 
    logger.info('Version: %s', settingsDict['IMAGE_TAG']) 
    logger.info('Commit: %s', settingsDict['SHORT_COMMIT_ID'])    
    logger.info('')       
    logger.info('%s | Removing failed downloads (%s)', str(settingsDict['REMOVE_FAILED']), 'REMOVE_FAILED')
    logger.info('%s | Removing failed imports (%s)', str(settingsDict['REMOVE_FAILED_IMPORTS']), 'REMOVE_FAILED_IMPORTS')
    if settingsDict['REMOVE_FAILED_IMPORTS'] and not settingsDict['FAILED_IMPORT_MESSAGE_PATTERNS']:
        logger.verbose ('> Any imports with a warning flag are considered failed, as no patterns specified (%s).', 'FAILED_IMPORT_MESSAGE_PATTERNS')
    elif settingsDict['REMOVE_FAILED_IMPORTS'] and settingsDict['FAILED_IMPORT_MESSAGE_PATTERNS']:
        logger.verbose ('> Imports with a warning flag are considered failed if the status message contains any of the following patterns:')
        for pattern in settingsDict['FAILED_IMPORT_MESSAGE_PATTERNS']: 
            logger.verbose('  - "%s"', pattern)
    logger.info('%s | Removing downloads missing metadata (%s)', str(settingsDict['REMOVE_METADATA_MISSING']), 'REMOVE_METADATA_MISSING') 
    logger.info('%s | Removing downloads missing files (%s)', str(settingsDict['REMOVE_MISSING_FILES']), 'REMOVE_MISSING_FILES')
    logger.info('%s | Removing orphan downloads (%s)', str(settingsDict['REMOVE_ORPHANS']), 'REMOVE_ORPHANS')  
    logger.info('%s | Removing slow downloads (%s)', str(settingsDict['REMOVE_SLOW']), 'REMOVE_SLOW')
    logger.info('%s | Removing stalled downloads (%s)', str(settingsDict['REMOVE_STALLED']), 'REMOVE_STALLED')
    logger.info('%s | Removing downloads belonging to unmonitored items (%s)', str(settingsDict['REMOVE_UNMONITORED']), 'REMOVE_UNMONITORED') 
    logger.info('')          
    logger.info('Running every: %s', fmt.format(rd(minutes=settingsDict['REMOVE_TIMER'])))  
    if settingsDict['REMOVE_SLOW']: 
        logger.info('Minimum speed enforced: %s KB/s', str(settingsDict['MIN_DOWNLOAD_SPEED'])) 
    logger.info('Permitted number of times before stalled/missing metadata/slow downloads are removed: %s', str(settingsDict['PERMITTED_ATTEMPTS']))      
    if settingsDict['QBITTORRENT_URL']: 
        logger.info('Downloads with this tag will be skipped: \"%s\"', settingsDict['NO_STALLED_REMOVAL_QBIT_TAG'])  
        logger.info('Private Trackers will be skipped: %s', settingsDict['IGNORE_PRIVATE_TRACKERS'])        
    
    logger.info('') 
    logger.info('*** Configured Instances ***')
    
    for instance in settingsDict['INSTANCES']:
        if settingsDict[instance + '_URL']: 
            logger.info(
                    '%s%s: %s',
                    instance.title(),
                    f" ({settingsDict.get(instance + '_NAME')})" if settingsDict.get(instance + '_NAME') != instance.title() else "",
                    (settingsDict[instance + '_URL']).split('/api')[0]
                )

    if settingsDict['QBITTORRENT_URL']: 
        logger.info(
            'qBittorrent: %s', 
            (settingsDict['QBITTORRENT_URL']).split('/api')[0]
        )    

    logger.info('') 
    return   

def upgradeChecks(settingsDict):
    if settingsDict['REMOVE_NO_FORMAT_UPGRADE']:
        logger.warn('❗️' * 10 + ' OUTDATED SETTINGS ' + '❗️' * 10 )
        logger.warn('')        
        logger.warn("❗️ %s was replaced with %s.", 'REMOVE_NO_FORMAT_UPGRADE', 'REMOVE_FAILED_IMPORTS')        
        logger.warn("❗️ Please check the ReadMe and update your settings.")
        logger.warn("❗️ Specifically read the section on %s.", 'FAILED_IMPORT_MESSAGE_PATTERNS')
        logger.warn('')
        logger.warn('❗️' * 29)
        logger.warn('')
    return

async def instanceChecks(settingsDict):
    # Checks if the arr and qbit instances are reachable, and returns the settings dictionary with the qbit cookie 
    logger.info('*** Check Instances ***')
    error_occured = False
    # Check ARR-apps
    for instance in settingsDict['INSTANCES']:
        if settingsDict[instance + '_URL']:    
            # Check instance is reachable
            try: 
                response = await asyncio.get_event_loop().run_in_executor(None, lambda: requests.get(settingsDict[instance + '_URL']+'/system/status', params=None, headers={'X-Api-Key': settingsDict[instance + '_KEY']}, verify=settingsDict['SSL_VERIFICATION']))
                response.raise_for_status()
            except Exception as error:
                error_occured = True
                logger.error('!! %s Error: !!', instance.title())
                logger.error('> %s', error)
                if isinstance(error, requests.exceptions.HTTPError) and error.response.status_code == 401:
                    logger.error ('> Have you configured %s correctly?', instance + '_KEY')

            if not error_occured:  
                # Check if network settings are pointing to the right Arr-apps
                current_app = (await rest_get(settingsDict[instance + '_URL']+'/system/status', settingsDict[instance + '_KEY']))['appName']
                if current_app.upper() != instance:
                    error_occured = True
                    logger.error('!! %s Error: !!', instance.title())                    
                    logger.error('> Your %s points to a %s instance, rather than %s. Did you specify the wrong IP?', instance + '_URL', current_app, instance.title())
 
            if not error_occured:
                # Check minimum version requirements are met
                current_version = (await rest_get(settingsDict[instance + '_URL']+'/system/status', settingsDict[instance + '_KEY']))['version']
                if settingsDict[instance + '_MIN_VERSION']:
                    if version.parse(current_version) < version.parse(settingsDict[instance + '_MIN_VERSION']):
                        error_occured = True
                        logger.error('!! %s Error: !!', instance.title())
                        logger.error('> Please update %s to at least version %s. Current version: %s', instance.title(), settingsDict[instance + '_MIN_VERSION'], current_version)
            if not error_occured:
                logger.info('OK | %s', instance.title())     
                logger.debug('Current version of %s: %s', instance, current_version)  

    # Check Bittorrent
    if settingsDict['QBITTORRENT_URL']:
        # Checking if qbit can be reached, and checking if version is OK
        try: 
            response = await asyncio.get_event_loop().run_in_executor(None, lambda: requests.post(settingsDict['QBITTORRENT_URL']+'/auth/login', data={'username': settingsDict['QBITTORRENT_USERNAME'], 'password': settingsDict['QBITTORRENT_PASSWORD']}, headers={'content-type': 'application/x-www-form-urlencoded'}, verify=settingsDict['SSL_VERIFICATION']))
            if response.text == 'Fails.':
                raise ConnectionError('Login failed.')
            response.raise_for_status()
            settingsDict['QBIT_COOKIE'] = {'SID': response.cookies['SID']} 
        except Exception as error:
            error_occured = True
            logger.error('!! %s Error: !!', 'qBittorrent')
            logger.error('> %s', error)
            logger.error('> Details:')
            logger.error(response.text)

        if not error_occured:
            qbit_version = await rest_get(settingsDict['QBITTORRENT_URL']+'/app/version',cookies=settingsDict['QBIT_COOKIE'])
            qbit_version = qbit_version[1:] # version without _v
            if version.parse(qbit_version) < version.parse(settingsDict['QBITTORRENT_MIN_VERSION']):
                error_occured = True
                logger.error('-- | %s *** Error: %s ***', 'qBittorrent', 'Please update qBittorrent to at least version %s Current version: %s',settingsDict['QBITTORRENT_MIN_VERSION'], qbit_version)

        if not error_occured:
            logger.info('OK | %s', 'qBittorrent')
            logger.debug('Current version of %s: %s', 'qBittorrent', qbit_version)  


    if error_occured:
        logger.warning('At least one instance had a problem. Waiting for 60 seconds, then exiting Decluttarr.')      
        await asyncio.sleep(60)
        exit()

    logger.info('') 
    return settingsDict

async def createQbitProtectionTag(settingsDict):
    # Creates the qBit Protection tag if not already present
    if settingsDict['QBITTORRENT_URL']:
        current_tags = await rest_get(settingsDict['QBITTORRENT_URL']+'/torrents/tags',cookies=settingsDict['QBIT_COOKIE'])
        if not settingsDict['NO_STALLED_REMOVAL_QBIT_TAG'] in current_tags:
            if settingsDict['QBITTORRENT_URL']: 
                logger.info('Creating tag in qBittorrent: %s', settingsDict['NO_STALLED_REMOVAL_QBIT_TAG'])  
                if not settingsDict['TEST_RUN']:
                    await rest_post(url=settingsDict['QBITTORRENT_URL']+'/torrents/createTags', data={'tags': settingsDict['NO_STALLED_REMOVAL_QBIT_TAG']}, headers={'content-type': 'application/x-www-form-urlencoded'}, cookies=settingsDict['QBIT_COOKIE'])

def showLoggerLevel(settingsDict):
    logger.info('#' * 50)
    if settingsDict['LOG_LEVEL'] == 'INFO':
        logger.info('LOG_LEVEL = INFO: Only logging changes (switch to VERBOSE for more info)')      
    else:
        logger.info(f'')
    if settingsDict['TEST_RUN']:
        logger.info(f'*'* 50)
        logger.info(f'*'* 50)
        logger.info(f'')
        logger.info(f'!! TEST_RUN FLAG IS SET !!')       
        logger.info(f'NO UPDATES/DELETES WILL BE PERFORMED')
        logger.info(f'')
        logger.info(f'*'* 50)
        logger.info(f'*'* 50)





