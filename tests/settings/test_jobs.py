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
    jobs = _jobs(
        {
            "remove_failed_imports": {"message_patterns": ["Not an upgrade*"]},
            "remove_stalled": {"max_strikes": 5},
        }
    )
    assert jobs.remove_failed_imports.enabled is True
    assert jobs.remove_failed_imports.message_patterns == ["Not an upgrade*"]
    assert jobs.remove_stalled.max_strikes == 5


def test_search_jobs_check_availability_defaults():
    jobs = _jobs({})
    assert jobs.search_missing.check_availability is False
    assert jobs.search_unmet_cutoff.check_availability is False


def test_search_jobs_check_availability_from_job_defaults():
    from src.settings._jobs import Jobs

    config = {
        "job_defaults": {"check_availability": True},
        "jobs": {"search_missing": True, "search_unmet_cutoff": True},
    }
    jobs = Jobs(config, _FakeSettings())
    assert jobs.search_missing.check_availability is True
    assert jobs.search_unmet_cutoff.check_availability is True


def test_search_jobs_check_availability_override():
    from src.settings._jobs import Jobs

    config = {
        "job_defaults": {"check_availability": False},
        "jobs": {
            "search_missing": {"check_availability": True},
            "search_unmet_cutoff": {"check_availability": False},
        },
    }
    jobs = Jobs(config, _FakeSettings())
    assert jobs.search_missing.check_availability is True
    assert jobs.search_unmet_cutoff.check_availability is False
