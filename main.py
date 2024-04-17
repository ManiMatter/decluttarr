# Import Libraries
import asyncio 
import logging, verboselogs
logger = verboselogs.VerboseLogger(__name__)
import json
# Import Functions
from config.config import settingsDict
from src.utils.loadScripts import *
from src.decluttarr import queueCleaner
from src.utils.rest import rest_get, rest_post 

# Hide SSL Verification Warnings
if settingsDict['SSL_VERIFICATION']==False:
    import warnings
    warnings.filterwarnings("ignore", message="Unverified HTTPS request")

# Set up logging
setLoggingFormat(settingsDict)

# Set up classes that allow tracking of items from one loop to the next
class Defective_Tracker:
    # Keeps track of which downloads were already caught as stalled previously
    def __init__(self, dict):
        self.dict = dict
class Download_Sizes_Tracker:
    # Keeps track of the file sizes of the downloads
    def __init__(self, dict):
        self.dict = dict

#

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
    
    logger.debug('main/getProtectedAndPrivateFromQbit/qbitItems: %s', str([{"hash": str.upper(item["hash"]), "name": item["name"], "tags": item["tags"], "is_private": item.get("is_private", None)} for item in qbitItems]))
    logger.debug('main/getProtectedAndPrivateFromQbit/protectedDownloadIDs: %s', str(protectedDownloadIDs))
    logger.debug('main/getProtectedAndPrivateFromQbit/privateDowloadIDs: %s', str(privateDowloadIDs))   

    return protectedDownloadIDs, privateDowloadIDs
        
# Main function
async def main(settingsDict):
# Adds to settings Dict the instances that are actually configures
    arrApplications  = ['RADARR', 'SONARR', 'LIDARR', 'READARR']
    settingsDict['INSTANCES'] = []
    for arrApplication in arrApplications:
        if settingsDict[arrApplication + '_URL']:
            settingsDict['INSTANCES'].append(arrApplication)

    # Pre-populates the dictionaries (in classes) that track the items that were already caught as having problems or removed
    defectiveTrackingInstances = {} 
    for instance in settingsDict['INSTANCES']:
        defectiveTrackingInstances[instance] = {}
    defective_tracker = Defective_Tracker(defectiveTrackingInstances)
    download_sizes_tracker = Download_Sizes_Tracker({})

    # Get name of arr-instances
    for instance in settingsDict['INSTANCES']:
        settingsDict = await getArrInstanceName(settingsDict, instance)

    # Display current settings when loading script
    showSettings(settingsDict)

    # Check Minimum Version and if instances are reachable and retrieve qbit cookie
    settingsDict['RADARR_MIN_VERSION']   = '5.3.6.8608'
    settingsDict['SONARR_MIN_VERSION']   = '4.0.1.1131'
    settingsDict['LIDARR_MIN_VERSION']   = None
    settingsDict['READARR_MIN_VERSION']  = None
    settingsDict['QBITTORRENT_MIN_VERSION']  = '4.3.0'
    settingsDict = await instanceChecks(settingsDict)

    # Create qBit protection tag if not existing
    await createQbitProtectionTag(settingsDict)

    # Show Logger settings
    showLoggerSettings(settingsDict)

    # Start Cleaning
    while True:
        logger.verbose('-' * 50)
        # Cache protected (via Tag) and private torrents 
        protectedDownloadIDs, privateDowloadIDs = await getProtectedAndPrivateFromQbit(settingsDict)

        # Run script for each instance
        for instance in settingsDict['INSTANCES']:
            await queueCleaner(settingsDict, instance, defective_tracker, download_sizes_tracker, protectedDownloadIDs, privateDowloadIDs)
        logger.verbose('')  
        logger.verbose('Queue clean-up complete!')  

        # Wait for the next run
        await asyncio.sleep(settingsDict['REMOVE_TIMER']*60)
    return

if __name__ == '__main__':
    asyncio.run(main(settingsDict))


