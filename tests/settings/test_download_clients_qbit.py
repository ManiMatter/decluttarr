import pytest
from requests.cookies import RequestsCookieJar

from src.settings._download_clients_qbit import QbitClient, QbitError


@pytest.mark.parametrize(
    "cookie_name, cookie_value, expected",
    [
        # Legacy format
        ("SID", "abc", {"SID": "abc"}),
        # New dynamic port format (qBit 5.2+)
        ("QBT_SID_8080", "xyz", {"QBT_SID_8080": "xyz"}),
        ("QBT_SID_12345", "token123", {"QBT_SID_12345": "token123"}),
    ],
)
def test_extract_sid_success(cookie_name, cookie_value, expected):
    """Test successful extraction for various valid cookie names."""
    jar = RequestsCookieJar()
    jar.set(cookie_name, cookie_value)

    assert QbitClient.extract_sid(jar) == expected


@pytest.mark.parametrize(
    "cookies",
    [
        {},  # Empty jar
        {"WRONG_NAME": "value"},  # Incorrect name
        {"sid": "lowercase_fails"},  # Case sensitivity check
    ],
)
def test_extract_sid_failures(cookies):
    """Test that invalid cookies properly raise QbitError."""
    jar = RequestsCookieJar()
    for name, val in cookies.items():
        jar.set(name, val)

    with pytest.raises(QbitError, match="No qBit cookie found"):
        QbitClient.extract_sid(jar)


from unittest.mock import AsyncMock, MagicMock, patch

import requests


@pytest.mark.asyncio
async def test_setup_reachability_timeout_marks_transient():
    settings = MagicMock()
    client = QbitClient(settings, base_url="http://qbit:8080")

    with patch(
        "src.settings._download_clients_qbit.make_request",
        new_callable=AsyncMock,
        side_effect=requests.exceptions.ReadTimeout("Read timed out."),
    ):
        result = await client.setup()

    assert result is False
    assert client.ready is False
    assert client.failure_kind == "transient"
    assert "Read timed out." in client.last_error


@pytest.mark.asyncio
async def test_setup_old_version_marks_definitive():
    settings = MagicMock()
    settings.min_versions.qbittorrent = "4.3.0"
    client = QbitClient(settings, base_url="http://qbit:8080")
    client.check_qbit_reachability = AsyncMock()
    client.refresh_cookie = AsyncMock()
    client.fetch_version = AsyncMock()
    client.version = "3.0.0"

    await client.setup()

    assert client.ready is False
    assert client.failure_kind == "definitive"


@pytest.mark.asyncio
async def test_setup_cookie_refresh_failure_marks_transient():
    settings = MagicMock()
    client = QbitClient(settings, base_url="http://qbit:8080")
    client.check_qbit_reachability = AsyncMock()
    client.refresh_cookie = AsyncMock(
        side_effect=QbitError(ConnectionError("Login failed."))
    )

    await client.setup()

    assert client.ready is False
    assert client.failure_kind == "transient"


@pytest.mark.asyncio
async def test_setup_bad_password_marks_definitive():
    """Wrong qBit password (HTTP 200 + 'Fails.') is definitive, not retried forever."""
    settings = MagicMock()
    client = QbitClient(
        settings, base_url="http://qbit:8080", username="u", password="wrong"
    )
    resp = MagicMock(text="Fails.")
    with patch(
        "src.settings._download_clients_qbit.make_request",
        new_callable=AsyncMock,
        return_value=resp,
    ):
        await client.setup()

    assert client.ready is False
    assert client.failure_kind == "definitive"


# --- API-key (qBit 5.2+) authentication ---

VALID_KEY = "qbt_" + "a" * 28


def test_auth_kwargs_key_mode_uses_bearer_header():
    client = QbitClient(MagicMock(), base_url="http://qbit:8080", api_key=VALID_KEY)
    assert client._auth_kwargs() == {
        "headers": {"Authorization": f"Bearer {VALID_KEY}"}
    }


def test_auth_kwargs_password_mode_uses_cookie():
    client = QbitClient(
        MagicMock(), base_url="http://qbit:8080", username="u", password="p"
    )
    client.cookie = {"SID": "abc"}
    assert client._auth_kwargs() == {"cookies": {"SID": "abc"}}


def test_empty_api_key_falls_back_to_password_mode():
    client = QbitClient(
        MagicMock(),
        base_url="http://qbit:8080",
        api_key="   ",
        username="u",
        password="p",
    )
    client.cookie = {"SID": "abc"}
    # Whitespace-only key is treated as unset.
    assert client._auth_kwargs() == {"cookies": {"SID": "abc"}}


def test_both_provided_key_wins_and_logs(caplog):
    with caplog.at_level("INFO"):
        client = QbitClient(
            MagicMock(),
            base_url="http://qbit:8080",
            api_key=VALID_KEY,
            username="u",
            password="p",
        )
    assert "Authorization" in client._auth_kwargs()["headers"]
    assert any("using api_key" in r.message for r in caplog.records)


def test_old_version_with_api_key_warns_without_raising(caplog):
    client = QbitClient(MagicMock(), base_url="http://qbit:8080", api_key=VALID_KEY)
    client.version = "5.1.2"

    with caplog.at_level("WARNING"):
        client.log_auth_version_guidance()

    assert "does not support API-key authentication" in caplog.text
    assert "API key did not authenticate this connection" in caplog.text


def test_supported_version_with_password_recommends_api_key(caplog):
    client = QbitClient(
        MagicMock(), base_url="http://qbit:8080", username="u", password="p"
    )
    client.version = "5.2.0"

    with caplog.at_level("INFO"):
        client.log_auth_version_guidance()

    assert "supports API-key authentication" in caplog.text
    assert "replacing username/password with api_key" in caplog.text


@pytest.mark.parametrize(
    ("version_value", "credentials"),
    [
        ("5.2.0", {"api_key": VALID_KEY}),
        ("5.1.2", {"username": "u", "password": "p"}),
    ],
)
def test_auth_version_guidance_omits_irrelevant_advice(
    caplog, version_value, credentials
):
    client = QbitClient(MagicMock(), base_url="http://qbit:8080", **credentials)
    client.version = version_value

    with caplog.at_level("INFO"):
        client.log_auth_version_guidance()

    assert "API-key authentication" not in caplog.text


@pytest.mark.asyncio
async def test_fetch_version_key_mode_sends_bearer_not_cookie():
    client = QbitClient(MagicMock(), base_url="http://qbit:8080", api_key=VALID_KEY)

    with patch(
        "src.settings._download_clients_qbit.make_request", new_callable=AsyncMock
    ) as mock_req:
        mock_req.return_value = MagicMock(text="_v5.2.0")
        await client.fetch_version()

    kwargs = mock_req.call_args.kwargs
    assert kwargs["headers"] == {"Authorization": f"Bearer {VALID_KEY}"}
    assert "cookies" not in kwargs


@pytest.mark.asyncio
async def test_refresh_cookie_noop_in_key_mode():
    client = QbitClient(MagicMock(), base_url="http://qbit:8080", api_key=VALID_KEY)

    with patch(
        "src.settings._download_clients_qbit.make_request", new_callable=AsyncMock
    ) as mock_req:
        await client.refresh_cookie()

    mock_req.assert_not_awaited()


@pytest.mark.asyncio
async def test_reachability_key_mode_probes_app_version():
    client = QbitClient(MagicMock(), base_url="http://qbit:8080", api_key=VALID_KEY)

    with patch(
        "src.settings._download_clients_qbit.make_request", new_callable=AsyncMock
    ) as mock_req:
        await client.check_qbit_reachability()

    method, endpoint = mock_req.call_args.args[0], mock_req.call_args.args[1]
    assert method == "get"
    assert endpoint.endswith("/app/version")


@pytest.mark.asyncio
async def test_reachability_password_mode_still_posts_login():
    client = QbitClient(
        MagicMock(), base_url="http://qbit:8080", username="u", password="p"
    )

    with patch(
        "src.settings._download_clients_qbit.make_request", new_callable=AsyncMock
    ) as mock_req:
        await client.check_qbit_reachability()

    method, endpoint = mock_req.call_args.args[0], mock_req.call_args.args[1]
    assert method == "post"
    assert endpoint.endswith("/auth/login")


@pytest.mark.asyncio
async def test_setup_bad_key_403_marks_definitive_with_tip():
    http_error = requests.exceptions.HTTPError("403 Forbidden")
    http_error.response = MagicMock(status_code=403)

    client = QbitClient(MagicMock(), base_url="http://qbit:8080", api_key=VALID_KEY)

    with patch(
        "src.settings._download_clients_qbit.make_request",
        new_callable=AsyncMock,
        side_effect=http_error,
    ):
        result = await client.setup()

    assert result is False
    assert client.ready is False
    assert client.failure_kind == "definitive"
    assert "5.2" in client.setup_tip
