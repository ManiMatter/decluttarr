# **Decluttarr**

## Overview
Decluttarr keeps the radarr & sonarr & lidarr queue free of stalled / redundant downloads.

Feature overview:
- Automatically delete downloads that are stuck downloading metadata (& trigger download from another source)
- Automatically delete failed downloads (& trigger download from another source)
- Automatically delete downloads belonging to Movies/TV shows/Music requests that have been deleted in the meantime ('Orphan downloads')
- Automatically delete stalled downloads, after they have been found to be stalled multiple times in a row
- Automatically delete downloads belonging to Movies/TV shows/Music that are unmonitored

You may run this locally by launching main.py, or by pulling the docker image.
You can find a sample docker-compose.yml in the docker folder.

## Getting started
If you want to run in docker:
1) Use `docker/Sample docker-compose.yml` to make your `docker-compose.yml` file
2) Look at `config/config.conf-Explained` for an explanation of the different settings
3) Run `sudo docker-compose up -d` in the directory where your `docker-compose.yml` is located to create the docker container
4) Have fun

If you want to run locally:
1) Pull decluttarr into whatever location you want with `git clone https://github.com/Fxsch/decluttarr.git`
3) Use `config/config.conf-Example` to make your `config.conf` file (needs to be located in the same folder as `main.py`)
2) Look at `config/config.conf-Explained` for an explanation of the different settings
4) run `main.py`
5) Enjoy

## Credits
- ManiMatter for making this, I just forked it to fix some stuff
- Script for detecting stalled downloads expanded on code by MattDGTL/sonarr-radarr-queue-cleaner
- Script to read out config expanded on code by syncarr/syncarr 
- SONARR/RADARR team & contributors for their great product, API documenation, and guidance in their Discord channel
- Particular thanks to them for adding an additional flag to their API that allowed this script detect downloads stuck finding metadata

## Disclaimer
This script comes free of any warranty, and you are using it at your own risk.
