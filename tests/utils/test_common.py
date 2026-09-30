from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.utils.common import make_request


@pytest.mark.asyncio
async def test_make_request_uses_general_request_timeout_by_default():
    settings = MagicMock()
    settings.general.test_run = False
    settings.general.ssl_verification = True
    settings.general.request_timeout = 42

    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()

    with patch(
        "src.utils.common.asyncio.to_thread", new_callable=AsyncMock
    ) as to_thread:
        to_thread.return_value = mock_response

        await make_request("get", "http://example.com/api", settings)

    assert to_thread.await_count == 1
    assert to_thread.await_args.kwargs["timeout"] == 42


@pytest.mark.asyncio
async def test_make_request_allows_explicit_timeout_override():
    settings = MagicMock()
    settings.general.test_run = False
    settings.general.ssl_verification = True
    settings.general.request_timeout = 42

    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()

    with patch(
        "src.utils.common.asyncio.to_thread", new_callable=AsyncMock
    ) as to_thread:
        to_thread.return_value = mock_response

        await make_request("get", "http://example.com/api", settings, timeout=7)

    assert to_thread.await_count == 1
    assert to_thread.await_args.kwargs["timeout"] == 7


def test_sanitize_kwargs_redacts_authorization_header():
    """The Bearer token must never survive into logs."""
    from src.utils.common import sanitize_kwargs

    data = {"headers": {"Authorization": "Bearer qbt_supersecrettoken"}}
    result = sanitize_kwargs(data)

    assert result["headers"]["Authorization"] == "[**redacted**]"
    assert "qbt_supersecrettoken" not in str(result)
