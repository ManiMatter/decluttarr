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
    ):
        self.enabled = enabled
        self.keep_archives = keep_archives
        self.message_patterns = message_patterns
        self.max_strikes = max_strikes
        self.min_speed = min_speed
        self.max_concurrent_searches = max_concurrent_searches
        self.min_days_between_searches = min_days_between_searches
        self.target_tags = target_tags

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

    def __init__(self, config, settings):
        job_defaults_config = config.get("job_defaults", {})
        self.target_tags.append(settings.general.obsolete_tag)
        self.max_strikes = job_defaults_config.get("max_strikes", self.max_strikes)
        self.max_concurrent_searches = job_defaults_config.get("max_concurrent_searches", self.max_concurrent_searches)
        self.min_days_between_searches = job_defaults_config.get(
            "min_days_between_searches",
            self.min_days_between_searches,
        )
        validate_data_types(self)


class Jobs:
    """Represent all jobs explicitly."""

    def __init__(self, config, settings):
        self.job_defaults = JobDefaults(config, settings)
        self._set_job_defaults()
        self._set_job_configs(config)
        del self.job_defaults

    @classmethod
    def create_with_overrides(cls, overrides, global_jobs):
        """
        Create a new Jobs instance with instance-level overrides applied.

        This method creates a merged Jobs object where instance-specific settings
        override global job settings while preserving unspecified parameters.

        Args:
            overrides: Dict of instance-specific job configurations
            global_jobs: Global Jobs object to use as base

        Returns:
            Jobs object with instance overrides applied

        """
        # Create a new Jobs instance without calling __init__
        merged = cls.__new__(cls)

        # Copy all job objects from global jobs
        for attr_name in dir(global_jobs):
            if attr_name.startswith("_"):
                continue
            attr_value = getattr(global_jobs, attr_name)
            if isinstance(attr_value, JobParams):
                # Deep copy the job params
                setattr(merged, attr_name, cls._deep_copy_job_params(attr_value))

        # Apply instance overrides
        for job_name, job_override_config in overrides.items():
            if hasattr(merged, job_name):
                merged._apply_override(job_name, job_override_config)
            else:
                logger.warning(
                    f"Instance job override for unknown job '{job_name}' ignored. "
                    f"Valid job names: {', '.join([name for name in dir(merged) if not name.startswith('_') and isinstance(getattr(merged, name), JobParams)])}",
                )

        return merged

    @staticmethod
    def _deep_copy_job_params(job_params):
        """
        Create a deep copy of a JobParams object.

        Args:
            job_params: JobParams object to copy

        Returns:
            New JobParams object with copied attributes

        """
        copied = JobParams()
        for attr_name, attr_value in vars(job_params).items():
            # Deep copy lists to avoid shared references
            if isinstance(attr_value, list):
                setattr(copied, attr_name, attr_value.copy())
            else:
                setattr(copied, attr_name, attr_value)
        return copied

    def _apply_override(self, job_name, override_config) -> None:
        """
        Apply instance-level override to a specific job.

        Handles three configuration formats:
        - None: Enable the job with existing parameters
        - bool: Set enabled status
        - dict: Merge parameters (instance values override global)

        Args:
            job_name: Name of the job to override
            override_config: Override configuration (None, bool, or dict)

        """
        job = getattr(self, job_name)

        if override_config is None:
            # None means enable the job with existing parameters
            job.enabled = True
        elif isinstance(override_config, bool):
            # Boolean directly sets enabled status
            job.enabled = override_config
        elif isinstance(override_config, dict):
            # Dict means merge parameters
            # Set enabled=True by default unless explicitly specified
            if "enabled" in override_config:
                job.enabled = override_config["enabled"]
            else:
                job.enabled = True

            # Merge other parameters
            for key, value in override_config.items():
                if key != "enabled":
                    setattr(job, key, value)

    def _set_job_defaults(self):
        self.remove_bad_files = JobParams(keep_archives=self.job_defaults.keep_archives)
        self.remove_done_seeding = JobParams(target_tags=self.job_defaults.target_tags)
        self.remove_failed_downloads = JobParams()
        self.remove_failed_imports = JobParams(
            message_patterns=self.job_defaults.message_patterns,
        )
        self.remove_metadata_missing = JobParams(
            max_strikes=self.job_defaults.max_strikes,
        )
        self.remove_missing_files = JobParams()
        self.remove_orphans = JobParams()
        self.remove_slow = JobParams(
            max_strikes=self.job_defaults.max_strikes,
            min_speed=self.job_defaults.min_speed,
        )
        self.remove_stalled = JobParams(max_strikes=self.job_defaults.max_strikes)
        self.remove_unmonitored = JobParams()
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
