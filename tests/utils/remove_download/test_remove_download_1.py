import pytest
from remove_download_utils import run_test

# Parameters identical across all tests
mock_data_file = "tests/utils/remove_download/mock_data/mock_data_1.json"
failType = "failed import"


@pytest.mark.asyncio
async def test_removal_with_removal_messages(monkeypatch, caplog):
    settingsDict = {"TEST_RUN": True}
    removeFromClient = True
    expected_removal_messages = {
        ">>> Removing failed import download: Sonarr Title 1",
        ">>>>> Tracked Download State: importBlocked",
        ">>>>> Status Messages (matching specified patterns):",
        ">>>>> - Episode XYZ was not found in the grabbed release: Sonarr Title 2.mkv",
        ">>>>> - And yet another message",
    }
    await run_test(
        settingsDict=settingsDict,
        expected_removal_messages=expected_removal_messages,
        failType=failType,
        removeFromClient=removeFromClient,
        mock_data_file=mock_data_file,
        monkeypatch=monkeypatch,
        caplog=caplog,
    )


@pytest.mark.asyncio
async def test_schizophrenic_removal_with_removal_messages(monkeypatch, caplog):
    settingsDict = {"TEST_RUN": True}
    removeFromClient = False
    expected_removal_messages = {
        ">>> Removing failed import download (without removing from torrent client): Sonarr Title 1",
        ">>>>> Tracked Download State: importBlocked",
        ">>>>> Status Messages (matching specified patterns):",
        ">>>>> - Episode XYZ was not found in the grabbed release: Sonarr Title 2.mkv",
        ">>>>> - And yet another message",
    }
    await run_test(
        settingsDict=settingsDict,
        expected_removal_messages=expected_removal_messages,
        failType=failType,
        removeFromClient=removeFromClient,
        mock_data_file=mock_data_file,
        monkeypatch=monkeypatch,
        caplog=caplog,
    )
