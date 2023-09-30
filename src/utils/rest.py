########### Functions to call radarr/sonarr APIs
import logging
import asyncio
import requests
from requests.exceptions import RequestException
import json
from config.config import (TEST_RUN)

# GET
async def rest_get(url, api_key, params=None):
    try:
        headers = {'X-Api-Key': api_key} # | {'accept': 'application/json'}
        response = await asyncio.get_event_loop().run_in_executor(None, lambda: requests.get(url, params=params, headers=headers))
        response.raise_for_status()
        return response.json()
    except RequestException as e:
        logging.error(f'Error making API request to {url}: {e}')
        return None
    except ValueError as e:
        logging.error(f'Error parsing JSON response from {url}: {e}')
        return None

# DELETE
async def rest_delete(url, api_key, params=None):
    if TEST_RUN: return
    try:
        headers = {'X-Api-Key': api_key}
        response = await asyncio.get_event_loop().run_in_executor(None, lambda: requests.delete(url, params=params, headers=headers))
        response.raise_for_status()
        if response.status_code in [200, 204]:
            return None
        return response.json()
    except RequestException as e:
        logging.error(f'Error making API request to {url}: {e}')
        return None
    except ValueError as e:
        logging.error(f'Error parsing JSON response from {url}: {e}')
        return None

# POST
async def rest_post(url, api_key, data):
    if TEST_RUN: return
    try:
        headers = {'X-Api-Key': api_key} | {"content-type": "application/json"}
        response = await asyncio.get_event_loop().run_in_executor(None, lambda: requests.post(url, data=data, headers=headers))
        response.raise_for_status()
        if response.status_code == 201:
            return None
        return response.json()
    except RequestException as e:
        logging.error(f'Error making API request to {url}: {e}')
        return None
    except ValueError as e:
        logging.error(f'Error parsing JSON response from {url}: {e}')
        return None


# PUT
async def rest_put(url, api_key, data):
    if TEST_RUN: return
    try:
        headers = {'X-Api-Key': api_key} | {"content-type": "application/json"}
        response = await asyncio.get_event_loop().run_in_executor(None, lambda: requests.put(url, data=data, headers=headers))
        response.raise_for_status()
        return response.json()
    except RequestException as e:
        logging.error(f'Error making API request to {url}: {e}')
        return None
    except ValueError as e:
        logging.error(f'Error parsing JSON response from {url}: {e}')
        return None

