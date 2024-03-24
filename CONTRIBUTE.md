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
Bugs in this application are scarce. If there are any, there most likely features ;-)
Please go follow these steps to submit a bug:
- Check if this bug has previously been reported
- Add [Bug] at the beginning of the issue title
- Describe the problem (what is it you experience and what is it that you would have expected to see)
- Create meaningful logs by:
1) Switch decluttarr to debug mode (setting LOG_LEVEL: DEBUG)
2) Turn off all remove functions but one where you expect a removal (example: REMOVE_STALLED: True and the rest on False)
3) Let it run until the supposed remove should be trigged
4) Paste the full logs to a pastebin
- If helpful: Paste a screenshot of qbit and the affected *arr app to a pasteimg
- Be willing to provide more details if asked for them and help testing the bug fix

### Code Contributions
Code contributions are very welcome - thanks for helping improve this app!
1) Please always branch out from the "dev" branch, not from the "main" branch
2) Please test your code locally
3) Please only commit code that you have written yourself and is not owned by anybody else
4) Please create a PR against the "dev" branch
5) Once I have reviewed it, I will merge it and it will create teh "dev" image
6) Please help testing that the dev image works, before we then commit it to the "latest" image (from main branch)