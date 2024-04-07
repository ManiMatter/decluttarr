########### Import Libraries
import asyncio 
import logging, verboselogs
logger = verboselogs.VerboseLogger(__name__)

########### Import Functions
from config.config import settingsDict
from src.utils.loadScripts import *
from src.decluttarr import queueCleaner
from src.utils.rest import rest_get, rest_post 

# Hide SSL Verification Warnings
if settingsDict['SSL_VERIFICATION']==False:
    import warnings
    warnings.filterwarnings("ignore", message="Unverified HTTPS request")

########### Enabling Logging
# Set up logging
setLoggingFormat(settingsDict)

class Defective_Tracker:
    # Keeps track of which downloads were already caught as stalled previously
    def __init__(self, dict):
        self.dict = dict
class Download_Sizes_Tracker:
    # Keeps track of the file sizes of the downloads
    def __init__(self, dict):
        self.dict = dict

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
        protectedDownloadIDs = []
        privateDowloadIDs = []
        if settingsDict['QBITTORRENT_URL']:
            protectedDowloadItems = await rest_get(settingsDict['QBITTORRENT_URL']+'/torrents/info',params={'tag': settingsDict['NO_STALLED_REMOVAL_QBIT_TAG']}, cookies=settingsDict['QBIT_COOKIE']  )
            logger.debug('main/protectedDowloadItems: %s', str(protectedDowloadItems))
            protectedDownloadIDs = [str.upper(item['hash']) for item in protectedDowloadItems]
            if settingsDict['IGNORE_PRIVATE_TRACKERS']:
                privateDowloadItems = await rest_get(settingsDict['QBITTORRENT_URL']+'/torrents/info',params={}, cookies=settingsDict['QBIT_COOKIE']  )
                privateDowloadIDs = [str.upper(item['hash']) for item in privateDowloadItems if item.get('is_private', False)]

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


