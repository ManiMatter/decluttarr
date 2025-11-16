"""Tests for instance-level job configuration overrides."""

from unittest.mock import MagicMock

from src.settings._instances import ArrInstance
from src.settings._jobs import JobParams, Jobs
from src.settings.settings import Settings


def create_mock_settings():
    """Create a mock Settings object with global jobs."""
    settings = MagicMock()
    settings.general = MagicMock()
    settings.general.obsolete_tag = "Obsolete"

    # Create global jobs
    config = {
        "job_defaults": {"max_strikes": 3, "min_speed": 100},
        "jobs": {
            "remove_stalled": {"max_strikes": 5},
            "remove_slow": {"min_speed": 150, "max_strikes": 3},
            "remove_failed_downloads": None,  # Enabled with defaults
        },
    }
    settings.jobs = Jobs(config, settings)
    return settings


def test_instance_without_job_overrides_uses_global_jobs():
    """Test that an instance without job overrides uses global jobs."""
    settings = create_mock_settings()
    arr = ArrInstance(settings, "sonarr", "http://test", "test_key", jobs_config={})

    # Should return global jobs
    assert arr.jobs is settings.jobs
    assert arr.jobs.remove_stalled.max_strikes == 5
    assert arr.jobs.remove_slow.min_speed == 150


def test_instance_with_job_override_creates_merged_jobs():
    """Test that instance with job overrides creates a merged Jobs object."""
    settings = create_mock_settings()

    jobs_config = {"remove_stalled": {"max_strikes": 10}}

    arr = ArrInstance(
        settings, "sonarr", "http://test", "test_key", jobs_config=jobs_config,
    )

    # Should create a new Jobs object, not the same as global
    assert arr.jobs is not settings.jobs

    # Instance override should be applied
    assert arr.jobs.remove_stalled.max_strikes == 10

    # Other jobs should inherit from global
    assert arr.jobs.remove_slow.min_speed == 150
    assert arr.jobs.remove_slow.max_strikes == 3


def test_instance_can_disable_globally_enabled_job():
    """Test that instance can disable a globally-enabled job."""
    settings = create_mock_settings()

    jobs_config = {"remove_failed_downloads": False}

    arr = ArrInstance(
        settings, "sonarr", "http://test", "test_key", jobs_config=jobs_config,
    )

    # Global job is enabled
    assert settings.jobs.remove_failed_downloads.enabled is True

    # Instance job should be disabled
    assert arr.jobs.remove_failed_downloads.enabled is False


def test_instance_can_enable_globally_disabled_job():
    """Test that instance can enable a globally-disabled job."""
    settings = create_mock_settings()

    # search_missing is not in global config, so disabled
    assert settings.jobs.search_missing.enabled is False

    jobs_config = {"search_missing": {"max_concurrent_searches": 5}}

    arr = ArrInstance(
        settings, "sonarr", "http://test", "test_key", jobs_config=jobs_config,
    )

    # Instance should enable the job
    assert arr.jobs.search_missing.enabled is True
    assert arr.jobs.search_missing.max_concurrent_searches == 5


def test_instance_partial_parameter_override():
    """Test that instance can override specific parameters while inheriting others."""
    settings = create_mock_settings()

    # Global has min_speed=150, max_strikes=3
    jobs_config = {"remove_slow": {"min_speed": 300}}  # Only override min_speed

    arr = ArrInstance(
        settings, "sonarr", "http://test", "test_key", jobs_config=jobs_config,
    )

    # min_speed should be overridden
    assert arr.jobs.remove_slow.min_speed == 300

    # max_strikes should be inherited from global
    assert arr.jobs.remove_slow.max_strikes == 3


def test_instance_override_with_none_enables_job():
    """Test that instance override with None value enables the job."""
    settings = create_mock_settings()

    # search_unmet_cutoff is disabled globally
    assert settings.jobs.search_unmet_cutoff.enabled is False

    jobs_config = {"search_unmet_cutoff": None}  # Enable with defaults

    arr = ArrInstance(
        settings, "sonarr", "http://test", "test_key", jobs_config=jobs_config,
    )

    # Should be enabled
    assert arr.jobs.search_unmet_cutoff.enabled is True


def test_instance_override_with_bool_sets_enabled_status():
    """Test that instance override with boolean sets enabled status."""
    settings = create_mock_settings()

    jobs_config = {
        "remove_failed_downloads": False,  # Disable
        "search_missing": True,  # Enable
    }

    arr = ArrInstance(
        settings, "sonarr", "http://test", "test_key", jobs_config=jobs_config,
    )

    assert arr.jobs.remove_failed_downloads.enabled is False
    assert arr.jobs.search_missing.enabled is True


def test_multiple_instances_have_independent_job_configs():
    """Test that multiple instances can have different job configurations."""
    settings = create_mock_settings()

    # Instance 1: Override remove_stalled
    arr1 = ArrInstance(
        settings,
        "sonarr",
        "http://sonarr1",
        "key1",
        jobs_config={"remove_stalled": {"max_strikes": 10}},
    )

    # Instance 2: Override remove_slow
    arr2 = ArrInstance(
        settings,
        "sonarr",
        "http://sonarr2",
        "key2",
        jobs_config={"remove_slow": {"min_speed": 500}},
    )

    # Instance 3: No overrides
    arr3 = ArrInstance(settings, "radarr", "http://radarr", "key3")

    # Each should have different configurations
    assert arr1.jobs.remove_stalled.max_strikes == 10
    assert arr1.jobs.remove_slow.min_speed == 150  # Global

    assert arr2.jobs.remove_stalled.max_strikes == 5  # Global
    assert arr2.jobs.remove_slow.min_speed == 500

    assert arr3.jobs.remove_stalled.max_strikes == 5  # Global
    assert arr3.jobs.remove_slow.min_speed == 150  # Global


def test_jobs_create_with_overrides_deep_copies_job_params():
    """Test that create_with_overrides deep copies JobParams to avoid shared state."""
    settings = create_mock_settings()

    # Create first instance with override
    arr1 = ArrInstance(
        settings,
        "sonarr",
        "http://sonarr1",
        "key1",
        jobs_config={"remove_stalled": {"max_strikes": 15}},
    )

    # Modify instance 1's job
    arr1.jobs.remove_stalled.max_strikes = 20

    # Create second instance - should not be affected by arr1 modification
    arr2 = ArrInstance(
        settings,
        "sonarr",
        "http://sonarr2",
        "key2",
        jobs_config={"remove_stalled": {"max_strikes": 15}},
    )

    # arr2 should have original override value, not arr1's modified value
    assert arr2.jobs.remove_stalled.max_strikes == 15

    # Global should also be unaffected
    assert settings.jobs.remove_stalled.max_strikes == 5


def test_jobs_create_with_overrides_handles_list_parameters():
    """Test that list parameters are deep copied and not shared."""
    settings = create_mock_settings()

    # Configure global with message_patterns
    settings.jobs.remove_failed_imports = JobParams(
        enabled=True, message_patterns=["pattern1", "pattern2"],
    )

    # Instance overrides message_patterns
    arr1 = ArrInstance(
        settings,
        "sonarr",
        "http://sonarr1",
        "key1",
        jobs_config={
            "remove_failed_imports": {"message_patterns": ["custom_pattern"]},
        },
    )

    # Modify arr1's list
    arr1.jobs.remove_failed_imports.message_patterns.append("added_pattern")

    # Create another instance
    arr2 = ArrInstance(
        settings,
        "sonarr",
        "http://sonarr2",
        "key2",
        jobs_config={
            "remove_failed_imports": {"message_patterns": ["custom_pattern"]},
        },
    )

    # arr2 should not see arr1's modification
    assert arr2.jobs.remove_failed_imports.message_patterns == ["custom_pattern"]

    # Global should be unchanged
    assert settings.jobs.remove_failed_imports.message_patterns == [
        "pattern1",
        "pattern2",
    ]


def test_instance_override_with_dict_enables_by_default():
    """Test that dict override without 'enabled' key enables the job."""
    settings = create_mock_settings()

    # search_missing is disabled globally
    assert settings.jobs.search_missing.enabled is False

    # Override with dict but no 'enabled' key
    jobs_config = {"search_missing": {"max_concurrent_searches": 10}}

    arr = ArrInstance(
        settings, "sonarr", "http://test", "test_key", jobs_config=jobs_config,
    )

    # Should be enabled by default when using dict override
    assert arr.jobs.search_missing.enabled is True
    assert arr.jobs.search_missing.max_concurrent_searches == 10


def test_instance_override_with_dict_respects_explicit_enabled_false():
    """Test that dict override with enabled=False disables the job."""
    settings = create_mock_settings()

    # remove_failed_downloads is enabled globally
    assert settings.jobs.remove_failed_downloads.enabled is True

    # Override with enabled=False
    jobs_config = {"remove_failed_downloads": {"enabled": False}}

    arr = ArrInstance(
        settings, "sonarr", "http://test", "test_key", jobs_config=jobs_config,
    )

    # Should be disabled
    assert arr.jobs.remove_failed_downloads.enabled is False


def test_lazy_initialization_of_instance_jobs():
    """Test that instance jobs are lazily initialized only when accessed."""
    settings = create_mock_settings()

    arr = ArrInstance(
        settings,
        "sonarr",
        "http://test",
        "test_key",
        jobs_config={"remove_stalled": {"max_strikes": 10}},
    )

    # _jobs should be None before first access
    assert arr._jobs is None

    # Access jobs property
    _ = arr.jobs

    # _jobs should now be initialized
    assert arr._jobs is not None

    # Second access should return same object
    jobs1 = arr.jobs
    jobs2 = arr.jobs
    assert jobs1 is jobs2


def test_full_integration_with_settings(tmp_path, monkeypatch):
    """Integration test with full Settings initialization."""
    # Create a temporary config file
    config_content = """
general:
  log_level: INFO
  test_run: true
  timer: 10

job_defaults:
  max_strikes: 3

jobs:
  remove_stalled:
    max_strikes: 5
  remove_slow:
    min_speed: 100

instances:
  sonarr:
    - base_url: "http://sonarr1:8989"
      api_key: "test_key_1"
      jobs:
        remove_stalled:
          max_strikes: 15
        remove_slow: false

    - base_url: "http://sonarr2:8989"
      api_key: "test_key_2"
      # No job overrides - uses global
"""

    config_path = tmp_path / "config.yaml"
    config_path.write_text(config_content)

    # Monkeypatch the Paths class to use our temporary config file
    from src.settings._constants import Paths

    monkeypatch.setattr(Paths, "config_file", str(config_path))

    settings = Settings()

    # Check that we have 2 sonarr instances
    sonarr_instances = [arr for arr in settings.instances if arr.arr_type == "sonarr"]
    assert len(sonarr_instances) == 2

    sonarr1, sonarr2 = sonarr_instances

    # Sonarr1 has overrides
    assert sonarr1.jobs.remove_stalled.max_strikes == 15
    assert sonarr1.jobs.remove_slow.enabled is False

    # Sonarr2 uses global config
    assert sonarr2.jobs.remove_stalled.max_strikes == 5
    assert sonarr2.jobs.remove_slow.min_speed == 100
    assert sonarr2.jobs.remove_slow.enabled is True
