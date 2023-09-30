# **Decluttarr**

## Overview
Decluttarr keeps the radarr & sonarr queue free of stalled / redundant downloads.

Feature overview:
- Automatically delete failed downloads
- Automatically delete downloads belonging to Movies/TV shows that have been deleted in the meantime ('Orphan downloads')
- Automatically delete stalled downloads, after they have been found to be stalled multiple times in a row
- Automatically delete downloads that are stuck downloading metadata
- Automatically delete downloads belonging to Movies/TV shows that are unmonitored

You may run this locally by launch main.py, or by mounting it inside a docker container.
A sample docker-compose.yml is included.

## Getting started
If you want to run in docker:
1) Pull the decluttarr into "your-docker-folder/own_coding/decluttarr"
2) Study the config file to understand the settings
3) Update your docker-compose (see the template)
4) Run the docker-compose
5) Enjoy

If you want to run locally:
1) Pull decluttarr into whatever location you want
2) Study the config file to understand the settings
3) Edit the config file to your liking
4) run main.py
5) Enjoy

## Credits
- Script for detecting stalled downloads expanded on code by MattDGTL/sonarr-radarr-queue-cleaner
- Script to read out config expanded on code by syncarr/syncarr 
- SONARR/RADARR team & contributors for their great product, API documenation, and guidance in their Discord channel
- Particular thanks to them for adding an additional flag to their API that allowed this script detect downloads stuck finding metadata

## Disclaimer
This script comes free of any warranty, and you are using it at your own risk.
I do not intend to maintain this repo, feel free to fork & create PRs if you want to expand it for your own use 
