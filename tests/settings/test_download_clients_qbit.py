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
