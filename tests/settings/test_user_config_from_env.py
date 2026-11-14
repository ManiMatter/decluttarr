"""Test loading the user configuration from environment variables."""

import logging
import os
import textwrap
from unittest.mock import patch

import pytest
import yaml

from src.settings._user_config import _load_from_env

# ---- Pytest Fixtures ----
# Pre-define multiline YAML snippets with dedent and strip for clarity
# Single values as plain strings (not YAML block strings)
LOG_LEVEL_VALUE = "VERBOSE"
TIMER_VALUE = "10"
REQUEST_TIMEOUT_VALUE = "35"
SSL_VERIFICATION_VALUE = "true"

# List
ignored_download_clients_yaml = textwrap.dedent(
    """
    - emulerr
    - napster
"""
).strip()

# Job: No settings
remove_bad_files_yaml = (  # pylint: disable=C0103; empty string represents flag enabled with no config
    ""
)

# Job: One Setting
remove_slow_yaml = textwrap.dedent(
    """
    - max_strikes: 3
"""
).strip()

# Job: Multiple Setting
remove_stalled_yaml = textwrap.dedent(
    """
    - min_speed: 100
    - max_strikes: 3
    - some_bool_upper: TRUE
    - some_bool_lower: false
    - some_bool_sentence: False
"""
).strip()

# Arr Instances
radarr_yaml = textwrap.dedent(
    """
    - base_url: "http://radarr:7878"
      api_key: "radarr1_key"
"""
).strip()

sonarr_yaml = textwrap.dedent(
    """
    - base_url: "sonarr_1_api_key"
      api_key: "sonarr1_api_url"
    - base_url: "sonarr_2_api_key"
      api_key: "sonarr2_api_url"
"""
).strip()

# Qbit Instances
qbit_yaml = textwrap.dedent(
    """
    - base_url: "http://qbittorrent:8080"
      username: "qbit_username1"
      password: "qbit_password1"
"""
).strip()


@pytest.fixture(name="env_vars")
def fixture_env_vars():
    env = {
        "LOG_LEVEL": LOG_LEVEL_VALUE,
        "TIMER": TIMER_VALUE,
        "REQUEST_TIMEOUT": REQUEST_TIMEOUT_VALUE,
        "SSL_VERIFICATION": SSL_VERIFICATION_VALUE,
        "IGNORED_DOWNLOAD_CLIENTS": ignored_download_clients_yaml,
        "REMOVE_BAD_FILES": remove_bad_files_yaml,
        "REMOVE_SLOW": remove_slow_yaml,
        "REMOVE_STALLED": remove_stalled_yaml,
        "RADARR": radarr_yaml,
        "SONARR": sonarr_yaml,
        "QBITTORRENT": qbit_yaml,
    }
    with patch.dict(os.environ, env, clear=True):
        yield env


# ---- Parametrized Tests ----
remove_ignored_download_clients_expected = yaml.safe_load(ignored_download_clients_yaml)
remove_bad_files_expected = yaml.safe_load(remove_bad_files_yaml)
remove_slow_expected = yaml.safe_load(remove_slow_yaml)
remove_stalled_expected = yaml.safe_load(remove_stalled_yaml)
radarr_expected = yaml.safe_load(radarr_yaml)
sonarr_expected = yaml.safe_load(sonarr_yaml)
qbit_expected = yaml.safe_load(qbit_yaml)


@pytest.mark.parametrize(
    ("section", "key", "expected"),
    [
        ("general", "log_level", LOG_LEVEL_VALUE),
        ("general", "timer", int(TIMER_VALUE)),
        ("general", "request_timeout", int(REQUEST_TIMEOUT_VALUE)),
        ("general", "ssl_verification", True),
        (
            "general",
            "ignored_download_clients",
            remove_ignored_download_clients_expected,
        ),
        ("jobs", "remove_bad_files", remove_bad_files_expected),
        ("jobs", "remove_slow", remove_slow_expected),
        ("jobs", "remove_stalled", remove_stalled_expected),
        ("instances", "radarr", radarr_expected),
        ("instances", "sonarr", sonarr_expected),
        ("download_clients", "qbittorrent", qbit_expected),
    ],
)
def test_env_loading_parametrized(
    env_vars, section, key, expected
):  # pylint: disable=unused-argument  # noqa: ARG001
    config = _load_from_env()
    assert section in config
    assert key in config[section]
    value = config[section][key]

    if isinstance(expected, list):
        # Compare as lists
        assert value == expected
    else:
        assert value == expected


def test_invalid_download_client_yaml_logs_actionable_error(caplog):
    malformed_qbit_yaml = '- base_url: "http://qbittorrent:8080'

    with (
        patch.dict(os.environ, {"QBITTORRENT": malformed_qbit_yaml}, clear=True),
        caplog.at_level(logging.ERROR, logger="src.utils.log_setup"),
    ):
        config = _load_from_env()

    assert config["download_clients"]["qbittorrent"] == {}
    assert len(caplog.records) == 1
    message = caplog.records[0].getMessage()
    assert "Could not parse QBITTORRENT as YAML" in message
    assert "smart quotes or incorrect indentation" in message
    assert "Configuration from this variable was ignored" in message
