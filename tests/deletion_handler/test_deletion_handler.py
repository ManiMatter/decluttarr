# pylint: disable=W0212
import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.deletion_handler.deletion_handler import DeletionHandler, WatcherManager


@pytest.mark.asyncio
async def test_get_folders_to_watch(caplog):
    arr_mock = MagicMock()
    arr_mock.name = "Sonarr"
    arr_mock.base_url = "http://sonarr:8989"
    arr_mock.arr_type = "sonarr"

    arr_mock.get_root_folders = AsyncMock(
        return_value=[
            {"accessible": True, "path": "/valid/path"},
            {"accessible": True, "path": "/missing/path"},
            {"accessible": False, "path": "/ignored/path"},
            {"path": "/no_access_field"},
            {"accessible": True},  # Missing "path"
        ]
    )

    settings = MagicMock()
    settings.instances = [arr_mock]
    watcher_manager = WatcherManager(settings)

    # Patch Path.exists to simulate filesystem behavior
    def fake_exists(self):
        return str(self) == "/valid/path"

    with patch("pathlib.Path.exists", new=fake_exists):
        with caplog.at_level("WARNING"):
            folders = await watcher_manager.get_folders_to_watch()

    assert folders == [(arr_mock, "/valid/path")]

    assert any(
        " does not have access to this path" in record.message
        and "/missing/path" in record.message
        for record in caplog.records
    )


class FakeEvent:
    def __init__(self, src_path, is_directory=False):
        self.src_path = src_path
        self.is_directory = is_directory


@pytest.mark.asyncio
async def test_deletion_handler_batch_processing():
    """This test verifies that DeletionHandler batches multiple file deletions, processes their parent folder once after a delay, and correctly calls the arr API with the expected folder path."""
    arr_mock = AsyncMock()
    arr_mock.name = "Sonarr"
    arr_mock.arr_type = "sonarr"
    arr_mock.get_refresh_item_by_path = AsyncMock(
        side_effect=lambda path: {"id": f"id_for_{path}", "title": "abc"}
    )
    arr_mock.refresh_item = AsyncMock()
    loop = asyncio.get_running_loop()
    handler = DeletionHandler(arr_mock, loop)
    handler.delay = 0  # immediate execution for tests

    # Trigger deletions
    handler.on_deleted(FakeEvent("/folder/file1.txt"))
    handler.on_deleted(FakeEvent("/folder/file2.txt"))
    # Let the event loop process scheduled task
    await asyncio.sleep(0.01)
    # Await batch completion
    await handler.await_completion()

    # Validate the call
    expected_calls = {"/folder"}
    actual_calls = {
        call.args[0] for call in arr_mock.get_refresh_item_by_path.call_args_list
    }
    assert actual_calls == expected_calls

    arr_mock.refresh_item.assert_called_once_with("id_for_/folder")


def test_group_deletions_by_folder():
    """Check that files are grouped by their parent folder correctly"""
    files = {
        "/tmp/folder1/file1.txt",
        "/tmp/folder1/file2.txt",
        "/tmp/folder2/file3.txt",
    }
    expected = {
        str(Path("/tmp/folder1")): ["file1.txt", "file2.txt"],
        str(Path("/tmp/folder2")): ["file3.txt"],
    }
    deletions = DeletionHandler._group_deletions_by_folder(files)

    # Since the value lists could be in any order due to set input, compare after sorting
    for folder, files in expected.items():
        assert sorted(deletions.get(folder, [])) == sorted(files)

    # Also check no extra keys
    assert set(deletions.keys()) == set(expected.keys())


@pytest.mark.asyncio
async def test_process_deletes_after_delay_clears_deleted_files(monkeypatch):
    """Tests that _process_deletes_after_delay clears deleted files and correctly processes their parent folders asynchronously."""

    class DummyArr:
        def __init__(self):
            self.called = []
            self.name = "DummyArr"  # add this attribute

        async def get_refresh_item_id_by_path(self, path):
            self.called.append(path)
            return "id"

    arr = DummyArr()
    loop = asyncio.get_running_loop()
    handler = DeletionHandler(arr, loop)
    handler.delay = 0  # no delay for test

    handler.deleted_files = {
        "/tmp/folder1/file1.txt",
        "/tmp/folder2/file2.txt",
    }

    async def no_sleep(_):
        return

    monkeypatch.setattr(asyncio, "sleep", no_sleep)

    # Patch _handle_folders to actually call dummy arr method and record calls
    async def fake_handle_folders(folders):
        for folder_path in folders:
            await arr.get_refresh_item_id_by_path(folder_path)

    handler._handle_folders = fake_handle_folders

    await handler._process_deletes_after_delay()

    assert not handler.deleted_files

    expected_folders = {
        str(Path(f).parent)
        for f in ["/tmp/folder1/file1.txt", "/tmp/folder2/file2.txt"]
    }
    assert set(arr.called) == expected_folders


@pytest.mark.asyncio
async def test_file_deletion_triggers_handler_with_watchermanager(tmp_path):
    """Tests that when a file is deleted in a watched directory,
    the WatcherManager’s DeletionHandler receives the event and
    calls the appropriate methods on the arr instance with the correct folder path."""

    folder_to_watch = tmp_path / "watched"
    folder_to_watch.mkdir()

    class TestArr:
        def __init__(self):
            self.name = "Test"
            self.arr_type = "sonarr"
            self.base_url = "http://localhost"
            self.ready = True
            self.called_paths = []
            self.refreshed_ids = []

        async def get_root_folders(self):
            return [{"accessible": True, "path": str(folder_to_watch)}]

        async def get_refresh_item_by_path(self, path):
            self.called_paths.append(path)
            # Return a dict with a 'title' key (and any other keys needed)
            return {"id": f"id_for_{path}", "title": f"Title for {path}"}

        async def refresh_item(self, item_id):
            self.refreshed_ids.append(item_id)

    settings = MagicMock()
    test_arr_instance = TestArr()
    settings.instances = [test_arr_instance]

    watcher = WatcherManager(settings)
    await watcher.setup()

    # Reduce delay for faster test execution
    for handler in watcher.handlers:
        handler.delay = 0.1

    try:
        test_file = folder_to_watch / "file1.txt"
        test_file.write_text("hello")
        test_file.unlink()  # delete the file to trigger the handler

        # Wait enough time for deletion event and async processing to complete
        await asyncio.sleep(0.3)

        # Await completion for all handlers to ensure background tasks done
        for handler in watcher.handlers:
            await handler.await_completion()

        # Assert the folder path was passed to get_refresh_item_id_by_path
        assert str(folder_to_watch) in test_arr_instance.called_paths
        # Assert that refresh_item was called with the expected IDs
        expected_id = f"id_for_{str(folder_to_watch)}"
        assert expected_id in test_arr_instance.refreshed_ids

    finally:
        watcher.stop()


@pytest.mark.asyncio
async def test_get_folders_to_watch_skips_not_ready_arr():
    arr_mock = MagicMock()
    arr_mock.arr_type = "sonarr"
    arr_mock.ready = False
    arr_mock.get_root_folders = AsyncMock()

    settings = MagicMock()
    settings.instances = [arr_mock]
    watcher_manager = WatcherManager(settings)

    folders = await watcher_manager.get_folders_to_watch()

    assert folders == []
    arr_mock.get_root_folders.assert_not_awaited()
