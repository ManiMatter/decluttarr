import pytest
from remove_failed_imports_utils import run_test

mock_data_file = "tests/jobs/remove_failed_imports/mock_data/mock_data_1.json"


@pytest.mark.asyncio
async def test_with_pattern_one_message(monkeypatch):
    settingsDict = {
        "FAILED_IMPORT_MESSAGE_PATTERNS": ["not found in the grabbed release"]
    }
    expected_removal_messages = {
        2: {
            ">>>>> Tracked Download State: importBlocked",
            ">>>>> Status Messages (matching specified patterns):",
            ">>>>> - Episode XYZ was not found in the grabbed release: Sonarr Title 2.mkv",
        }
    }
    await run_test(settingsDict, expected_removal_messages, mock_data_file, monkeypatch)


@pytest.mark.asyncio
async def test_with_empty_pattern_one_message(monkeypatch):
    settingsDict = {"FAILED_IMPORT_MESSAGE_PATTERNS": []}
    expected_removal_messages = {
        2: {
            ">>>>> Tracked Download State: importBlocked",
            ">>>>> Status Messages (All):",
            ">>>>> - Episode XYZ was not found in the grabbed release: Sonarr Title 2.mkv",
        }
    }
    await run_test(settingsDict, expected_removal_messages, mock_data_file, monkeypatch)


@pytest.mark.asyncio
async def test_without_pattern_one_message(monkeypatch):
    settingsDict = {}
    expected_removal_messages = {
        2: {
            ">>>>> Tracked Download State: importBlocked",
            ">>>>> Status Messages (All):",
            ">>>>> - Episode XYZ was not found in the grabbed release: Sonarr Title 2.mkv",
        }
    }
    await run_test(settingsDict, expected_removal_messages, mock_data_file, monkeypatch)
