import pytest
from remove_failed_imports_utils import run_test

mock_data_file = "tests/jobs/remove_failed_imports/mock_data/mock_data_2.json"


@pytest.mark.asyncio
async def test_multiple_status_messages_multiple_pattern(monkeypatch):
    settingsDict = {"FAILED_IMPORT_MESSAGE_PATTERNS": ["world", "all"]}
    expected_removal_messages = {
        1: {
            ">>>>> Tracked Download State: importBlocked",
            ">>>>> Status Messages (matching specified patterns):",
            ">>>>> - Message 1 - hello world",
            ">>>>> - Message 2 - goodbye all",
        }
    }
    await run_test(settingsDict, expected_removal_messages, mock_data_file, monkeypatch)


@pytest.mark.asyncio
async def test_multiple_status_messages_single_pattern(monkeypatch):
    settingsDict = {"FAILED_IMPORT_MESSAGE_PATTERNS": ["world"]}
    expected_removal_messages = {
        1: {
            ">>>>> Tracked Download State: importBlocked",
            ">>>>> Status Messages (matching specified patterns):",
            ">>>>> - Message 1 - hello world",
        }
    }
    await run_test(settingsDict, expected_removal_messages, mock_data_file, monkeypatch)


@pytest.mark.asyncio
async def test_multiple_status_messages_no_pattern(monkeypatch):
    settingsDict = {}
    expected_removal_messages = {
        1: {
            ">>>>> Tracked Download State: importBlocked",
            ">>>>> Status Messages (All):",
            ">>>>> - Message 1 - hello world",
            ">>>>> - Message 2 - goodbye all",
        }
    }
    await run_test(settingsDict, expected_removal_messages, mock_data_file, monkeypatch)
