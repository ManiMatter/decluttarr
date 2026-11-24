from unittest.mock import patch

import pytest

from src.settings._jobs import JobParams


def test_job_params_truthiness_is_false_by_default():
    assert not JobParams()


def test_job_params_truthiness_reflects_enabled_flag():
    assert JobParams(enabled=True)
    assert not JobParams(enabled=False)


class _FakeSettings:
    class general:
        obsolete_tag = "Obsolete"


def _jobs(jobs_config):
    from src.settings._jobs import Jobs

    return Jobs({"jobs": jobs_config}, _FakeSettings())


def test_bool_true_keeps_job_defaults():
    # Regression: JobParams.__bool__ made the pre-built defaults object falsy
    # (enabled=False), so `remove_failed_imports: true` was replaced by a bare
    # JobParams(enabled=True) and lost message_patterns -> AttributeError at runtime.
    jobs = _jobs({"remove_failed_imports": True, "remove_stalled": True})
    assert jobs.remove_failed_imports.enabled is True
    assert jobs.remove_failed_imports.message_patterns == ["*"]
    assert jobs.remove_stalled.enabled is True
    assert jobs.remove_stalled.max_strikes == 3


def test_bool_false_keeps_job_defaults():
    jobs = _jobs({"remove_failed_imports": False})
    assert jobs.remove_failed_imports.enabled is False
    assert jobs.remove_failed_imports.message_patterns == ["*"]


def test_dict_merges_onto_job_defaults():
    jobs = _jobs({"remove_failed_imports": {"message_patterns": ["Not an upgrade*"]}, "remove_stalled": {"max_strikes": 5}})
    assert jobs.remove_failed_imports.enabled is True
    assert jobs.remove_failed_imports.message_patterns == ["Not an upgrade*"]
    assert jobs.remove_stalled.max_strikes == 5


def test_skip_unreleased_defaults_to_true():
    jobs = _jobs({"search_missing": True, "search_unmet_cutoff": True})
    assert jobs.search_missing.skip_unreleased is True
    assert jobs.search_unmet_cutoff.skip_unreleased is True


def test_skip_unreleased_from_job_defaults_and_job_override():
    from src.settings._jobs import Jobs

    config = {
        "job_defaults": {"skip_unreleased": False},
        "jobs": {
            "search_missing": True,
            "search_unmet_cutoff": {"skip_unreleased": True},
        },
    }
    jobs = Jobs(config, _FakeSettings())
    assert jobs.search_missing.skip_unreleased is False
    assert jobs.search_unmet_cutoff.skip_unreleased is True


def test_remove_stalled_min_days_stalled_defaults_to_zero():
    """The bare `remove_stalled:` YAML form keeps the job defaults."""
    jobs = _jobs({"remove_stalled": None})

    assert jobs.remove_stalled.min_days_stalled == 0


def test_remove_stalled_min_days_stalled_read_from_job_config():
    jobs = _jobs({"remove_stalled": {"min_days_stalled": 7}})

    assert jobs.remove_stalled.min_days_stalled == 7


@pytest.mark.parametrize(("job_defaults", "warned"), [({"min_days_stalled": 7}, True), ({}, False)])
def test_min_days_stalled_under_job_defaults_warns(job_defaults, warned):
    from src.settings._jobs import Jobs

    with patch("src.settings._jobs.logger") as logger:
        jobs = Jobs({"job_defaults": job_defaults, "jobs": {}}, _FakeSettings())

    assert logger.warning.called is warned
    assert jobs.remove_stalled.min_days_stalled == 0


def test_remove_bad_files_min_days_low_availability_defaults_to_zero():
    jobs = _jobs({"remove_bad_files": None})

    assert jobs.remove_bad_files.min_days_low_availability == 0


def test_remove_bad_files_min_days_low_availability_read_from_job_config():
    jobs = _jobs({"remove_bad_files": {"min_days_low_availability": 3}})

    assert jobs.remove_bad_files.min_days_low_availability == 3
