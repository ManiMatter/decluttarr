# Import Libraries
import asyncio 
import logging, verboselogs
logger = verboselogs.VerboseLogger(__name__)
import json
# Import Functions
from config.definitions import settingsDict
from src.utils.loadScripts import *
from src.decluttarr import queueCleaner
from src.utils.rest import rest_get, rest_post 
from src.utils.trackers import Defective_Tracker, Download_Sizes_Tracker  

# Hide SSL Verification Warnings
if settingsDict['SSL_VERIFICATION']==False:
    import warnings
    warnings.filterwarnings("ignore", message="Unverified HTTPS request")

# Set up logging
setLoggingFormat(settingsDict)

# Main function
async def main(settingsDict):
# Adds to settings Dict the instances that are actually configures
    settingsDict['INSTANCES'] = []
    for arrApplication in settingsDict['SUPPORTED_ARR_APPS']:
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

    # Check outdated
    upgradeChecks(settingsDict)

    # Welcome Message
    showWelcome() 

    # Current Settings
    showSettings(settingsDict)

    # Check Minimum Version and if instances are reachable and retrieve qbit cookie
    settingsDict = await instanceChecks(settingsDict)

    # Create qBit protection tag if not existing
    await createQbitProtectionTag(settingsDict)

    # Show Logger Level
    showLoggerLevel(settingsDict)

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


