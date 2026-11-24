import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.jobs.remove_bad_files import RemoveBadFiles


# Fixture for arr mock
@pytest.fixture(name="removal_job")
def fixture_removal_job():
    arr = AsyncMock()
    removal_job = RemoveBadFiles(arr=arr, settings=MagicMock(), job_name="test")
    removal_job.arr = arr
    removal_job.job = MagicMock()
    removal_job.job.keep_archives = False
    return removal_job


@pytest.mark.parametrize(
    "file_name, expected_result, keep_archives",
    [
        ("file.mp4", False, False),  # Good extension
        ("file.mkv", False, False),  # Good extension
        ("file.avi", False, False),  # Good extension
        ("file.exe", True, False),  # Bad extension
        ("file.jpg", True, False),  # Bad extension
        ("file.zip", True, False),  # Archive - Don't keep archives
        ("file.zip", False, True),  # Archive - Keep archives
    ],
)
def test_is_bad_extension(removal_job, file_name, expected_result, keep_archives):
    """This test will verify that files with bad extensions are properly identified."""
    # Fix
    removal_job.job.keep_archives = keep_archives

    # Act
    file = {"name": file_name}  # Simulating a file object
    file["file_extension"] = Path(file["name"]).suffix.lower()
    result = removal_job._is_bad_extension(file)  # pylint: disable=W0212

    # Assert
    assert result == expected_result


@pytest.mark.parametrize(
    ("name", "size_bytes", "expected_result"),
    [
        (
            "My.Movie.2024.2160/Subfolder/sample.mkv",
            100 * 1024,
            True,
        ),  # 100 KB, 'sample' keyword in filename
        (
            "My.Movie.2024.2160/Subfolder/Sample.mkv",
            100 * 1024,
            True,
        ),  # 100 KB, case-insensitive match
        (
            "My.Movie.2024.2160/Subfolder/sample movie.mkv",
            100 * 1024,
            True,
        ),  # 100 KB, 'sample' keyword with space
        (
            "My.Movie.2024.2160/Subfolder/samplemovie.mkv",
            100 * 1024,
            True,
        ),  # 100 KB, 'sample' keyword concatenated
        (
            "My.Movie.2024.2160/Subfolder/Movie sample.mkv",
            100 * 1024,
            True,
        ),  # 100 KB, 'sample' keyword at end
        (
            "My.Movie.2024.2160/Sample/Movie.mkv",
            100 * 1024,
            True,
        ),  # 100 KB, 'sample' keyword in folder name
        (
            "My.Movie.2024.2160/sample/Movie.mkv",
            100 * 1024,
            True,
        ),  # 100 KB, lowercase folder name
        (
            "My.Movie.2024.2160/Samples/Movie.mkv",
            100 * 1024,
            True,
        ),  # 100 KB, plural form in folder name
        (
            "My.Movie.2024.2160/Big Samples/Movie.mkv",
            700 * 1024 * 1024,
            False,
        ),  # 700 MB, large file, should NOT be flagged
        (
            "My.Movie.2024.2160/Some Folder/Movie.mkv",
            100 * 1024,
            False,
        ),  # 100 KB, no 'sample' keyword, should not flag
    ],
)
def test_contains_bad_keyword(removal_job, name, size_bytes, expected_result):
    """Test detection of bad keywords with uniform small size except a large sample file."""
    file = {
        "name": name,
        "size": size_bytes,
    }
    result = removal_job._contains_bad_keyword(file)  # pylint: disable=W0212
    assert result == expected_result


@pytest.mark.parametrize(
    ("file", "is_incomplete_partial"),
    [
        ({"availability": 1, "progress": 1}, False),  # Fully available
        ({"availability": 0.5, "progress": 0.5}, True),  # Low availability
        ({"availability": 0.5, "progress": 1}, False),  # Downloaded, low availability
        ({"availability": 0.9, "progress": 0.8}, True),  # Low availability
    ],
)
def test_is_complete_partial(removal_job, file, is_incomplete_partial):
    """Check if the availability logic works correctly."""
    # Act
    result = removal_job._is_complete_partial(file)  # pylint: disable=W0212

    # Assert
    assert result == is_incomplete_partial


@pytest.mark.parametrize(
    ("qbit_item", "expected_processed"),
    [
        # Case 1: Torrent without metadata
        (
            {
                "hash": "hash",
                "has_metadata": False,
                "state": "downloading",
                "availability": 0.5,
            },
            False,
        ),
        # Case 2: Torrent with different status
        (
            {
                "hash": "hash",
                "has_metadata": True,
                "state": "uploading",
                "availability": 0.5,
            },
            False,
        ),
        # Case 3: Torrent checked before and full availability
        (
            {
                "hash": "checked-hash",
                "has_metadata": True,
                "state": "downloading",
                "availability": 1.0,
            },
            False,
        ),
        # Case 4: Torrent not checked before and full availability
        (
            {
                "hash": "not-checked-hash",
                "has_metadata": True,
                "state": "downloading",
                "availability": 1.0,
            },
            True,
        ),
        # Case 5: Torrent checked before and partial availability
        (
            {
                "hash": "checked-hash",
                "has_metadata": True,
                "state": "downloading",
                "availability": 0.8,
            },
            True,
        ),
        # Case 6: Torrent with partial availability (downloading)
        (
            {
                "hash": "hash",
                "has_metadata": True,
                "state": "downloading",
                "availability": 0.8,
            },
            True,
        ),
        # Case 7: Torrent with partial availability (forcedDL)
        (
            {
                "hash": "hash",
                "has_metadata": True,
                "state": "forcedDL",
                "availability": 0.8,
            },
            True,
        ),
        # Case 8: Torrent with partial availability (stalledDL)
        (
            {
                "hash": "hash",
                "has_metadata": True,
                "state": "forcedDL",
                "availability": 0.8,
            },
            True,
        ),
    ],
)
@pytest.mark.asyncio
async def test_get_items_to_process(qbit_item, expected_processed, removal_job):
    """Test the _get_items_to_process method of RemoveBadFiles class."""
    # Mocking the tracker extension_checked to simulate which torrents have been checked
    removal_job.arr.tracker = AsyncMock()
    removal_job.arr.tracker.extension_checked = {"checked-hash"}

    # Act
    processed_items = removal_job._get_items_to_process(  # pylint: disable=W0212
        [qbit_item]
    )

    # Extract the hash from the processed items
    processed_hashes = [item["hash"] for item in processed_items]

    # Assert
    if expected_processed:
        assert qbit_item["hash"] in processed_hashes
    else:
        assert qbit_item["hash"] not in processed_hashes


@pytest.mark.parametrize(
    ("file", "should_be_stoppable"),
    [
        # Stopped files - No need to stop again
        (
            {
                "index": 0,
                "name": "file.exe",
                "priority": 0,
                "availability": 1.0,
                "progress": 1.0,
            },
            False,
        ),
        (
            {
                "index": 0,
                "name": "file.mp3",
                "priority": 0,
                "availability": 1.0,
                "progress": 1.0,
            },
            False,
        ),
        # Bad file extension - Always stop (if not alredy stopped)
        (
            {
                "index": 0,
                "name": "file.exe",
                "priority": 1,
                "availability": 1.0,
                "progress": 1.0,
            },
            True,
        ),
        (
            {
                "index": 0,
                "name": "file.exe",
                "priority": 1,
                "availability": 0.5,
                "progress": 1.0,
            },
            True,
        ),
        (
            {
                "index": 0,
                "name": "file.exe",
                "priority": 1,
                "availability": 0.0,
                "progress": 1.0,
            },
            True,
        ),
        # Good file extension - Stop only if availability < 1 **and** progress < 1
        (
            {
                "index": 0,
                "name": "file.mp3",
                "priority": 1,
                "availability": 1.0,
                "progress": 1.0,
            },
            False,
        ),  # Fully done and fully available
        (
            {
                "index": 0,
                "name": "file.mp3",
                "priority": 1,
                "availability": 0.3,
                "progress": 1.0,
            },
            False,
        ),  # Fully done and partially available
        (
            {
                "index": 0,
                "name": "file.mp3",
                "priority": 1,
                "availability": 1.0,
                "progress": 0.5,
            },
            False,
        ),  # Fully available
        (
            {
                "index": 0,
                "name": "file.mp3",
                "priority": 1,
                "availability": 0.3,
                "progress": 0.9,
            },
            True,
        ),  # Partially done and not available
    ],
)
def test_get_stoppable_file_single(removal_job, file, should_be_stoppable):
    # Add file_extension based on the file name
    file["file_extension"] = Path(file["name"]).suffix.lower()
    stoppable = removal_job._get_stoppable_files([file])  # pylint: disable=W0212
    is_stoppable = bool(stoppable)
    assert is_stoppable == should_be_stoppable


@pytest.fixture(name="torrent_files")
def fixture_torrent_files():
    return [
        {"index": 0, "name": "file1.mp3", "priority": 0},  # Already stopped
        {"index": 1, "name": "file2.mp3", "priority": 0},  # Already stopped
        {"index": 2, "name": "file3.exe", "priority": 1},
        {"index": 3, "name": "file4.exe", "priority": 1},
        {"index": 4, "name": "file5.mp3", "priority": 1},
    ]


@pytest.mark.parametrize(
    ("stoppable_indexes", "all_files_stopped"),
    [
        ([0], False),  # Case 1: Nothing changes (stopping an already stopped file)
        ([2], False),  # Case 2: One additional file stopped
        ([2, 3, 4], True),  # Case 3: All remaining files stopped
        ([0, 1, 2, 3, 4], True),  # Case 4: Mix of both
    ],
)
def test_all_files_stopped(
    removal_job,
    torrent_files,
    stoppable_indexes,
    all_files_stopped,
):
    # Create stoppable_files using only the index for each file and a dummy reason
    stoppable_files = [({"index": idx}, "some reason") for idx in stoppable_indexes]
    result = removal_job._all_files_stopped(  # pylint: disable=W0212
        torrent_files, stoppable_files
    )
    assert result == all_files_stopped


def _low_availability_file():
    return {
        "name": "Show/episode.mkv",
        "file_name": "episode.mkv",
        "file_extension": ".mkv",
        "size": 100 * 1024 * 1024,
        "priority": 1,
        "progress": 0.1,
        "availability": 0.4,
        "index": 0,
    }


@pytest.mark.parametrize(
    ("min_days", "age_days", "expected"),
    [
        (0, 0, False),  # Disabled: never too new
        (3, 1, True),  # Younger than the minimum
        (3, 5, False),  # Older than the minimum
    ],
)
def test_is_too_new_for_availability_check(removal_job, min_days, age_days, expected):
    removal_job.job.min_days_low_availability = min_days
    qbit_item = {"added_on": time.time() - age_days * 86400}

    # pylint: disable=W0212
    assert removal_job._is_too_new_for_availability_check(qbit_item) is expected


def test_low_availability_ignored_while_torrent_is_new(removal_job):
    files = [_low_availability_file()]

    stoppable = removal_job._get_stoppable_files(  # pylint: disable=W0212
        files, check_availability=False
    )

    assert not stoppable


def test_new_torrent_still_checked_for_bad_extension(removal_job):
    file = {**_low_availability_file(), "file_extension": ".exe"}

    stoppable = removal_job._get_stoppable_files(  # pylint: disable=W0212
        [file], check_availability=False
    )

    assert len(stoppable) == 1
    assert stoppable[0][1] == ["Bad extension: .exe"]


@pytest.mark.asyncio
@pytest.mark.parametrize(("age_days", "removed"), [(1, False), (5, True)])
async def test_handle_qbit_respects_min_days_low_availability(
    removal_job, age_days, removed
):
    removal_job.job.min_days_low_availability = 3
    removal_job.arr.tracker.extension_checked = []
    removal_job.arr.tracker.protected = []
    removal_job.queue = [{"downloadId": "ABC"}]
    qbit_client = AsyncMock()
    qbit_client.get_qbit_items.return_value = [
        {
            "hash": "abc",
            "name": "Show",
            "has_metadata": True,
            "state": "downloading",
            "availability": 0.4,
            "added_on": time.time() - age_days * 86400,
        }
    ]
    qbit_client.get_torrent_files.return_value = [_low_availability_file()]

    affected = await removal_job._handle_qbit(  # pylint: disable=W0212
        qbit_client, {"ABC"}
    )

    assert bool(affected) is removed
