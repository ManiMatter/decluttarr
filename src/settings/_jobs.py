from src.settings._config_as_yaml import get_config_as_yaml
from src.settings._validate_data_types import validate_data_types
from src.utils.log_setup import logger


class JobParams:
    """Represents individual job settings, with an 'enabled' flag and optional parameters."""

    enabled: bool = False
    keep_archives = False
    message_patterns: list
    max_strikes: int
    min_speed: int
    max_concurrent_searches: int
    min_days_between_searches: int
    target_tags: list
    action_mode: str = "remove"
    handoff_tag: str
    deferred_arr_followup: bool = False
    followup_trigger: str = "on_download_removed"

    def __init__(
        self,
        enabled=None,
        keep_archives=None,
        message_patterns=None,
        max_strikes=None,
        min_speed=None,
        max_concurrent_searches=None,
        min_days_between_searches=None,
        target_tags=None,
        action_mode=None,
        handoff_tag=None,
        deferred_arr_followup=None,
        followup_trigger=None,
    ):
        self.enabled = enabled
        self.keep_archives = keep_archives
        self.message_patterns = message_patterns
        self.max_strikes = max_strikes
        self.min_speed = min_speed
        self.max_concurrent_searches = max_concurrent_searches
        self.min_days_between_searches = min_days_between_searches
        self.target_tags = target_tags
        self.action_mode = action_mode
        self.handoff_tag = handoff_tag
        self.deferred_arr_followup = deferred_arr_followup
        self.followup_trigger = followup_trigger

        # Remove attributes that are None to keep the object clean
        self._remove_none_attributes()

    def _remove_none_attributes(self):
        """Remove attributes that are None to keep the object clean."""
        for attr in list(vars(self)):
            if getattr(self, attr) is None:
                delattr(self, attr)


class JobDefaults:
    """Represents default job settings."""

    keep_archives: bool = False
    max_strikes: int = 3
    max_concurrent_searches: int = 3
    min_days_between_searches: int = 7
    min_speed: int = 100
    message_patterns = ["*"]
    target_tags = []
    action_mode: str = "remove"
    handoff_tag: str = ""
    deferred_arr_followup: bool = False
    followup_trigger: str = "on_download_removed"

    def __init__(self, config, settings):
        job_defaults_config = config.get("job_defaults", {})
        self.target_tags.append(settings.general.obsolete_tag)
        self.max_strikes = job_defaults_config.get("max_strikes", self.max_strikes)
        self.max_concurrent_searches = job_defaults_config.get(
            "max_concurrent_searches", self.max_concurrent_searches
        )
        self.min_days_between_searches = job_defaults_config.get(
            "min_days_between_searches",
            self.min_days_between_searches,
        )
        self.action_mode = job_defaults_config.get("action_mode", self.action_mode)
        self.handoff_tag = job_defaults_config.get("handoff_tag", self.handoff_tag)
        self.deferred_arr_followup = job_defaults_config.get(
            "deferred_arr_followup", self.deferred_arr_followup
        )
        self.followup_trigger = job_defaults_config.get(
            "followup_trigger", self.followup_trigger
        )
        validate_data_types(self)


class Jobs:
    """Represent all jobs explicitly."""

    def __init__(self, config, settings):
        self.job_defaults = JobDefaults(config, settings)
        self._set_job_defaults()
        self._set_job_configs(config)
        del self.job_defaults

    def _set_job_defaults(self):
        removal_defaults = {
            "action_mode": self.job_defaults.action_mode,
            "handoff_tag": self.job_defaults.handoff_tag,
            "deferred_arr_followup": self.job_defaults.deferred_arr_followup,
            "followup_trigger": self.job_defaults.followup_trigger,
        }
        self.remove_bad_files = JobParams(
            keep_archives=self.job_defaults.keep_archives,
            **removal_defaults,
        )
        self.remove_done_seeding = JobParams(target_tags=self.job_defaults.target_tags)
        self.remove_failed_downloads = JobParams(**removal_defaults)
        self.remove_failed_imports = JobParams(
            message_patterns=self.job_defaults.message_patterns,
            **removal_defaults,
        )
        self.remove_metadata_missing = JobParams(
            max_strikes=self.job_defaults.max_strikes,
            **removal_defaults,
        )
        self.remove_missing_files = JobParams(**removal_defaults)
        self.remove_orphans = JobParams(**removal_defaults)
        self.remove_slow = JobParams(
            max_strikes=self.job_defaults.max_strikes,
            min_speed=self.job_defaults.min_speed,
            **removal_defaults,
        )
        self.remove_stalled = JobParams(
            max_strikes=self.job_defaults.max_strikes,
            **removal_defaults,
        )
        self.remove_unmonitored = JobParams(**removal_defaults)
        self.search_unmet_cutoff = JobParams(
            max_concurrent_searches=self.job_defaults.max_concurrent_searches,
            min_days_between_searches=self.job_defaults.min_days_between_searches,
        )
        self.search_missing = JobParams(
            max_concurrent_searches=self.job_defaults.max_concurrent_searches,
            min_days_between_searches=self.job_defaults.min_days_between_searches,
        )
        self.detect_deletions = JobParams()

    def _set_job_configs(self, config):
        # Populate jobs from YAML config
        for job_name in self.__dict__:
            if job_name != "job_defaults" and job_name in config.get("jobs", {}):
                self._set_job_settings(job_name, config["jobs"][job_name])

    def _set_job_settings(self, job_name, job_config):
        """Set per-job config settings."""
        job = getattr(self, job_name, None)
        if (
            job_config is None
        ):  # this triggers only when reading from yaml-file. for docker-compose, empty configs are not loaded, thus the entire job would not be parsed
            job.enabled = True
        elif isinstance(job_config, bool):
            if job:
                job.enabled = job_config
            else:
                job = JobParams(enabled=job_config)
        elif isinstance(job_config, dict):
            job_config.setdefault("enabled", True)

            if job:
                for key, value in job_config.items():
                    setattr(job, key, value)
            else:
                job = JobParams(**job_config)

        else:
            job = JobParams(enabled=False)

        setattr(self, job_name, job)
        validate_data_types(
            job,
            self.job_defaults,
        )  # Validates and applies defaults from job_defaults

    def log_status(self):
        job_strings = []
        for job_name, job_obj in self.__dict__.items():
            if isinstance(job_obj, JobParams):
                job_strings.append(f"{job_name}: {job_obj.enabled}")
        status = "\n".join(job_strings)
        logger.info(status)

    def config_as_yaml(self):
        filtered = {
            k: v
            for k, v in vars(self).items()
            if not hasattr(v, "enabled") or v.enabled
        }
        return get_config_as_yaml(
            filtered,
            internal_attributes={"enabled"},
            hide_internal_attr=True,
        )

    def list_job_status(self):
        """Return a string showing each job and whether it's enabled or not using emojis."""
        lines = []
        for name, obj in vars(self).items():
            if hasattr(obj, "enabled"):
                status = "🟢" if obj.enabled else "⚪️"
                lines.append(f"{status} {name}")
        return "\n".join(lines)
