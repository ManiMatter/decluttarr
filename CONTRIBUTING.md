# **Contributing to Decluttarr**

## Table of contents
- [Overview](#overview)
- [Feature Requests](#feature--requests)
- [Bug Reports](#bug--reports)
- [Code Contributions](#code--contributions)

## Overview
Thank you for wanting to contribute to this project.
The below provides guidance how you can propose new features, raise bugs, or contribute with code.

## Feature Requests
To raise a new feature request, please go through the following steps:
- Check in the open and closed issues if this feature has already been requested before creating a new one
- Open only feature requests that are within scope of decluttarr: clear up the download pipeline; managing complete torrents is not in scope
- Add [Feature request] at the beginning of the issue title
- Add a short description of what you would like to have
- Be willing to provide more details if asked for them and help testing the feature

## Bug Reports
Bugs in this application are scarce. If there are any, they're most likely features ;-)
Please go follow these steps to submit a bug:
- Check if this bug has previously been reported
- Add [Bug] at the beginning of the issue title
- Describe the problem (what is it you experience and what is it that you would have expected to see)
- Create meaningful logs by:
1) Switch decluttarr to debug mode (setting LOG_LEVEL: DEBUG)
2) Turn off all remove functions but one where you expect a removal (example: REMOVE_STALLED: True and the rest on False)
3) Let it run until the supposed remove should be trigged
4) Paste the full logs to a pastebin
5) Share your settings (docker-compose or config.conf) 
6) Optional: If helpful, share screenshots showing the problem (from your arr-app or qbit) 
7) Be responsive and provide more details if asked for them, and help testing the bug fix

### Code Contributions
Code contributions are very welcome - thanks for helping improve this app!
1) Always branch out from the "dev" branch, not from the "main" branch
2) Test your code locally
3) Only commit code that you have written yourself and is not owned by anybody else
4) Create a PR against the "dev" branch
5) Be responsive to code review 
5) Once the code is reviewed and OK, it will be merged to dev branch, which will create the "dev"-docker image
6) Help testing that the dev image works
7= Finally, we will then commit the change to the main branch, which will create the "latest"-docker image

You do not need to know about how to create docker images to contribute here.
To get started:
1) Create a fork of decluttarr
2) Clone the git repository from the dev branch to your local machine `git clone -b dev https://github.com/yourName/decluttarr`
2) Create a virtual python environment (`python3 -m venv venv`)
3) Activate the virtual environment (`source venv/bin/activate`)
4) Install python libraries (`pip install -r docker/requirements.txt`)
5) Adjust the config/config.conf to your needs
6) Adjust the code in the files as needed
7) Run the script (`python3 main.py`)
8) Push your changes to your own git repo
9) Test the dev-image it creates automatically
10) Create the PR from your repo to ManiMatter/decluttarr (dev branch)


