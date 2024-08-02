import os
os.environ['IS_IN_PYTEST'] = 'true'
import logging
import json
import pytest
from typing import Dict, Set, Any
from unittest.mock import AsyncMock
from src.jobs.remove_failed_imports import remove_failed_imports


# Utility function to load mock data
def load_mock_data(file_name):
    with open(file_name, 'r') as file:
        return json.load(file)

async def mock_get_queue(mock_data):
    logging.debug("Mock get_queue called")
    return mock_data

async def run_test(
    settingsDict: Dict[str, Any], 
    expected_removal_messages: Dict[int, Set[str]],
    mock_data_file: str,
    monkeypatch: pytest.MonkeyPatch
) -> None:
    # Load mock data
    mock_data = load_mock_data(mock_data_file)

    # Create an AsyncMock for execute_checks with side effect
    execute_checks_mock = AsyncMock()

    # Define a side effect function
    def side_effect(*args, **kwargs):
        logging.debug("Mock execute_checks called with kwargs: %s", kwargs)
        # Return the affectedItems from kwargs
        return kwargs.get('affectedItems', [])

    # Attach side effect to the mock
    execute_checks_mock.side_effect = side_effect

    # Create an async mock for get_queue that returns mock_data
    mock_get_queue = AsyncMock(return_value=mock_data)

    # Patch the methods
    monkeypatch.setattr('src.jobs.remove_failed_imports.get_queue', mock_get_queue)
    monkeypatch.setattr('src.jobs.remove_failed_imports.execute_checks', execute_checks_mock)

    # Call the function
    await remove_failed_imports(settingsDict=settingsDict, BASE_URL='', API_KEY='', NAME='', deleted_downloads=set(), defective_tracker=set(), protectedDownloadIDs=set(), privateDowloadIDs=set())

    # Assertions
    assert execute_checks_mock.called  # Ensure the mock was called

    # Assert expected items are there
    args, kwargs = execute_checks_mock.call_args
    affectedItems = kwargs.get('affectedItems', []) 
    affectedItems_ids = {item['id'] for item in affectedItems}
    expectedItems_ids = set(expected_removal_messages.keys())
    assert len(affectedItems) == len(expected_removal_messages)
    assert affectedItems_ids == expectedItems_ids

    # Assert all expected messages are there
    for affectedItem in affectedItems:
        assert 'removal_messages' in affectedItem
        assert expected_removal_messages[affectedItem['id']] == set(affectedItem.get('removal_messages', []))
