from unittest.mock import MagicMock

from src.settings._jobs import Jobs


def _make_settings(obsolete_tag="Obsolete"):
    settings = MagicMock()
    settings.general.obsolete_tag = obsolete_tag
    return settings


def test_job_defaults_apply_to_arr_removal_jobs():
    config = {
        "job_defaults": {
            "action_mode": "tag_only",
            "handoff_tag": "cleanup-ready",
            "deferred_arr_followup": True,
            "followup_trigger": "on_download_removed",
        },
        "jobs": {
            "remove_orphans": {},
            "remove_stalled": {},
        },
    }

    jobs = Jobs(config, _make_settings())

    assert jobs.remove_orphans.action_mode == "tag_only"
    assert jobs.remove_orphans.handoff_tag == "cleanup-ready"
    assert jobs.remove_orphans.deferred_arr_followup is True
    assert jobs.remove_orphans.followup_trigger == "on_download_removed"

    assert jobs.remove_stalled.action_mode == "tag_only"
    assert jobs.remove_stalled.handoff_tag == "cleanup-ready"
    assert jobs.remove_stalled.deferred_arr_followup is True


def test_job_level_overrides_job_defaults_for_handoff_fields():
    config = {
        "job_defaults": {
            "action_mode": "remove",
            "handoff_tag": "Obsolete",
            "deferred_arr_followup": False,
            "followup_trigger": "on_download_removed",
        },
        "jobs": {
            "remove_orphans": {
                "action_mode": "tag_only",
                "handoff_tag": "cleanup-ready",
                "deferred_arr_followup": True,
                "followup_trigger": "on_download_removed",
            },
        },
    }

    jobs = Jobs(config, _make_settings())

    assert jobs.remove_orphans.action_mode == "tag_only"
    assert jobs.remove_orphans.handoff_tag == "cleanup-ready"
    assert jobs.remove_orphans.deferred_arr_followup is True
    assert jobs.remove_orphans.followup_trigger == "on_download_removed"
