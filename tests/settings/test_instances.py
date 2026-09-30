from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import requests

from src.settings._instances import ArrInstance


def _make_settings(min_version="4.0.0"):
    settings = MagicMock()
    settings.min_versions.sonarr = min_version
    return settings


def _response(json_data):
    response = MagicMock()
    response.json = MagicMock(return_value=json_data)
    return response


def _healthy_responses(app_name="Sonarr", app_version="9.9.9", ui_language=1):
    """Responses for the three make_request calls in a full successful setup."""
    return [
        _response(
            {"instanceName": "MockSonarr", "appName": app_name, "version": app_version}
        ),
        _response({"uiLanguage": ui_language}),
        _response([]),  # downloadclient list
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "arr_type, expected_key",
    [
        ("radarr", "movie"),
        ("sonarr", "series"),
    ],
)
async def test_get_refresh_item_calls_make_request_with_correct_params(
    arr_type, expected_key
):
    base_url = f"http://{arr_type}/"
    api_key = "test_key"
    settings = {}

    arr = ArrInstance(settings, arr_type, base_url, api_key)

    # Fake response data your get_refresh_item expects
    fake_json = [{"id": 1, "path": "/media/example"}]

    # Patch make_request to return an object whose .json() coroutine returns fake_json
    with patch(
        "src.settings._instances.make_request", new_callable=AsyncMock
    ) as mock_make_request:
        mock_response = AsyncMock()
        mock_response.json = MagicMock(return_value=fake_json)
        mock_make_request.return_value = mock_response

        result = await arr.get_refresh_item()

        mock_make_request.assert_awaited_once_with(
            "get",
            arr.api_url + "/" + expected_key,
            settings,
            timeout=arr.timeout,
            headers={"X-Api-Key": api_key},
        )
        assert result == fake_json


@pytest.mark.asyncio
async def test_get_refresh_item_by_path_returns_correct_item():
    arr = ArrInstance({}, "radarr", "http://radarr/", "test_key")

    mock_items = [
        {"id": 123, "path": "/media/folder1"},
        {"id": 456, "path": "/media/folder2"},
    ]

    with patch.object(
        arr, "get_refresh_item", AsyncMock(return_value=mock_items)
    ) as mock_method:
        result = await arr.get_refresh_item_by_path("/media/folder2/some_subfolder")

        mock_method.assert_awaited_once()
        assert result == {"id": 456, "path": "/media/folder2"}


@pytest.mark.asyncio
async def test_setup_timeout_marks_transient_and_does_not_exit():
    arr = ArrInstance(_make_settings(), "sonarr", "http://sonarr/", "test_key")

    with (
        patch(
            "src.settings._instances.make_request",
            new_callable=AsyncMock,
            side_effect=requests.exceptions.ReadTimeout("Read timed out."),
        ),
        patch("src.settings._instances.wait_and_exit") as mock_exit,
    ):
        result = await arr.setup()

    mock_exit.assert_not_called()
    assert result is False
    assert arr.ready is False
    assert arr.failure_kind == "transient"
    assert "Read timed out." in arr.last_error


@pytest.mark.asyncio
async def test_setup_401_marks_definitive():
    http_error = requests.exceptions.HTTPError("401 Client Error")
    http_error.response = MagicMock(status_code=401)

    arr = ArrInstance(_make_settings(), "sonarr", "http://sonarr/", "test_key")

    with (
        patch(
            "src.settings._instances.make_request",
            new_callable=AsyncMock,
            side_effect=http_error,
        ),
        patch("src.settings._instances.wait_and_exit") as mock_exit,
    ):
        await arr.setup()

    mock_exit.assert_not_called()
    assert arr.ready is False
    assert arr.failure_kind == "definitive"
    assert "API_KEY" in arr.setup_tip


@pytest.mark.asyncio
async def test_setup_non_english_ui_marks_definitive():
    arr = ArrInstance(_make_settings(), "sonarr", "http://sonarr/", "test_key")

    with patch(
        "src.settings._instances.make_request",
        new_callable=AsyncMock,
        side_effect=_healthy_responses(ui_language=2),
    ):
        await arr.setup()

    assert arr.ready is False
    assert arr.failure_kind == "definitive"


@pytest.mark.asyncio
async def test_setup_recovers_on_retry():
    arr = ArrInstance(_make_settings(), "sonarr", "http://sonarr/", "test_key")

    with patch(
        "src.settings._instances.make_request",
        new_callable=AsyncMock,
        side_effect=requests.exceptions.ReadTimeout("Read timed out."),
    ):
        assert await arr.setup() is False

    with patch(
        "src.settings._instances.make_request",
        new_callable=AsyncMock,
        side_effect=_healthy_responses(),
    ):
        assert await arr.setup() is True

    assert arr.ready is True
    assert arr.failure_kind is None
    assert arr.last_error is None
    assert arr.name == "MockSonarr"


@pytest.mark.asyncio
async def test_setup_same_error_logs_tip_block_once(caplog):
    arr = ArrInstance(_make_settings(), "sonarr", "http://sonarr/", "test_key")

    with patch(
        "src.settings._instances.make_request",
        new_callable=AsyncMock,
        side_effect=requests.exceptions.ReadTimeout("Read timed out."),
    ):
        with caplog.at_level("ERROR"):
            await arr.setup()
            await arr.setup()

    tip_blocks = [r for r in caplog.records if "❗️" in r.message]
    assert len(tip_blocks) == 1


@pytest.mark.asyncio
async def test_setup_wrong_arr_type_and_old_version_still_pass():
    arr = ArrInstance(_make_settings(), "sonarr", "http://sonarr/", "test_key")

    with patch(
        "src.settings._instances.make_request",
        new_callable=AsyncMock,
        side_effect=_healthy_responses(app_name="Radarr", app_version="0.0.1"),
    ):
        assert await arr.setup() is True

    assert arr.ready is True


def _arr_for_queue_removal():
    arr = ArrInstance.__new__(ArrInstance)
    arr.api_url = "http://sonarr/api/v3"
    arr.api_key = "test_key"
    arr.settings = MagicMock()
    arr._timeout = 15
    return arr


@pytest.mark.asyncio
async def test_remove_queue_item_deletes_from_client_by_default():
    arr = _arr_for_queue_removal()

    with patch(
        "src.settings._instances.make_request", new=AsyncMock()
    ) as mocked_request:
        mocked_request.return_value = MagicMock(status_code=200)
        await arr.remove_queue_item(queue_id=7, blocklist=True)

    assert mocked_request.call_args.kwargs["params"]["removeFromClient"] is True


@pytest.mark.asyncio
async def test_remove_queue_item_can_leave_the_torrent_in_the_client():
    """remove_from_client=False clears the queue entry but keeps the torrent seeding."""
    arr = _arr_for_queue_removal()

    with patch(
        "src.settings._instances.make_request", new=AsyncMock()
    ) as mocked_request:
        mocked_request.return_value = MagicMock(status_code=200)
        await arr.remove_queue_item(
            queue_id=7, blocklist=True, remove_from_client=False
        )

    params = mocked_request.call_args.kwargs["params"]
    assert params["removeFromClient"] is False
    assert params["blocklist"] is True
