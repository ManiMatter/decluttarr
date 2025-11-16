"""Test loading the user configuration from environment variables."""

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


# ---- Test instance-level job overrides ----

def test_instance_level_job_overrides_from_env():
    """Test that instance-level job overrides work through environment variables."""
    sonarr_with_jobs_yaml = textwrap.dedent(
        """
        - base_url: "http://sonarr1:8989"
          api_key: "sonarr1_key"
          jobs:
            remove_stalled: false
            remove_slow:
              min_speed: 200
              max_strikes: 5
        - base_url: "http://sonarr2:8989"
          api_key: "sonarr2_key"
    """,
    ).strip()

    env = {
        "SONARR": sonarr_with_jobs_yaml,
        "REMOVE_STALLED": "true",  # Globally enabled
        "REMOVE_SLOW": "min_speed: 100",  # Global config
    }

    with patch.dict(os.environ, env, clear=True):
        config = _load_from_env()

        # Check that the config was loaded
        assert "instances" in config
        assert "sonarr" in config["instances"]

        sonarr_instances = config["instances"]["sonarr"]
        assert len(sonarr_instances) == 2

        # First instance has job overrides
        sonarr1 = sonarr_instances[0]
        assert sonarr1["base_url"] == "http://sonarr1:8989"
        assert sonarr1["api_key"] == "sonarr1_key"
        assert "jobs" in sonarr1
        assert sonarr1["jobs"]["remove_stalled"] is False
        assert sonarr1["jobs"]["remove_slow"]["min_speed"] == 200
        assert sonarr1["jobs"]["remove_slow"]["max_strikes"] == 5

        # Second instance has no job overrides
        sonarr2 = sonarr_instances[1]
        assert sonarr2["base_url"] == "http://sonarr2:8989"
        assert sonarr2["api_key"] == "sonarr2_key"
        assert "jobs" not in sonarr2


def test_instance_job_overrides_integration_with_env():
    """Integration test: instance job overrides work end-to-end with env vars."""
    from src.settings.settings import Settings

    radarr_with_jobs_yaml = textwrap.dedent(
        """
        - base_url: "http://radarr-1080p:7878"
          api_key: "radarr_1080p_key"
        - base_url: "http://radarr-4k:7878"
          api_key: "radarr_4k_key"
          jobs:
            remove_slow:
              min_speed: 500
            search_missing: false
    """,
    ).strip()

    env = {
        "LOG_LEVEL": "INFO",
        "TEST_RUN": "true",
        "TIMER": "10",
        "REMOVE_SLOW": "min_speed: 100\nmax_strikes: 3",
        "SEARCH_MISSING": "true",
        "RADARR": radarr_with_jobs_yaml,
        "IN_DOCKER": "true",  # Mock being in Docker so env vars are used
    }

    with patch.dict(os.environ, env, clear=True):
        # Create full Settings and verify instances
        settings_full = Settings()

        # Verify global jobs
        assert settings_full.jobs.remove_slow.enabled is True
        assert settings_full.jobs.remove_slow.min_speed == 100
        assert settings_full.jobs.remove_slow.max_strikes == 3
        assert settings_full.jobs.search_missing.enabled is True

        radarr_instances = [
            arr for arr in settings_full.instances if arr.arr_type == "radarr"
        ]
        assert len(radarr_instances) == 2

        radarr_1080p, radarr_4k = radarr_instances

        # 1080p instance uses global settings
        assert radarr_1080p.base_url == "http://radarr-1080p:7878"
        assert radarr_1080p.jobs.remove_slow.min_speed == 100
        assert radarr_1080p.jobs.remove_slow.max_strikes == 3
        assert radarr_1080p.jobs.search_missing.enabled is True

        # 4K instance has overrides
        assert radarr_4k.base_url == "http://radarr-4k:7878"
        assert radarr_4k.jobs.remove_slow.min_speed == 500  # Overridden
        assert radarr_4k.jobs.remove_slow.max_strikes == 3  # Inherited
        assert radarr_4k.jobs.search_missing.enabled is False  # Overridden
