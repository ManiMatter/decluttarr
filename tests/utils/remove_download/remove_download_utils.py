import os
os.environ['IS_IN_PYTEST'] = 'true'
import logging
import json
import pytest
from typing import Dict, Set, Any
from src.utils.shared import remove_download
from src.utils.trackers import Deleted_Downloads



# Utility function to load mock data
def load_mock_data(file_name):
    with open(file_name, 'r') as file:
        return json.load(file)

async def mock_rest_delete() -> None:
    logger.debug(f"Mock rest_delete called with URL")


async def run_test(
    settingsDict: Dict[str, Any], 
    expected_removal_messages: Set[str],
    failType: str,
    removeFromClient: bool,
    mock_data_file: str,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture
) -> None:
    # Load mock data
    affectedItem = load_mock_data(mock_data_file)

    # Mock the `rest_delete` function
    monkeypatch.setattr('src.utils.shared.rest_delete', mock_rest_delete)
    
    # Call the function
    with caplog.at_level(logging.INFO):
        # Call the function and assert no exceptions
        try:   
            deleted_downloads = Deleted_Downloads([]) 
            await remove_download(settingsDict=settingsDict, BASE_URL='', API_KEY='', affectedItem=affectedItem, failType=failType, addToBlocklist=True, deleted_downloads=deleted_downloads, removeFromClient=removeFromClient)
        except Exception as e:
            pytest.fail(f"remove_download raised an exception: {e}")

    # Assertions:
    # Check that expected log messages are in the captured log
    log_messages = {record.message for record in caplog.records if record.levelname == 'INFO'}

    assert expected_removal_messages == log_messages

    # Check that the affectedItem's downloadId was added to deleted_downloads
    assert affectedItem['downloadId'] in deleted_downloads.dict
