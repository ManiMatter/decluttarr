from src.settings._config_as_yaml import get_config_as_yaml
from src.settings._validate_data_types import validate_data_types
from src.utils.log_setup import logger

VALID_TRACKER_HANDLING = {"remove", "skip", "obsolete_tag"}


class General:
    """Represents general settings for the application."""

    log_level: str = "INFO"
    test_run: bool = False
    timer: float = 10.0
    request_timeout: float = 15.0
    ssl_verification: bool = True
    request_timeout: int = 15
    ignored_download_clients: list = []
    private_tracker_handling: str = "remove"
    public_tracker_handling: str = "remove"
    obsolete_tag: str = "Obsolete"
    protected_tag: str = "Keep"

    def __init__(self, config):
        general_config = config.get("general", {})
        self.log_level = general_config.get("log_level", self.log_level.upper())
        self.test_run = general_config.get("test_run", self.test_run)
        self.timer = general_config.get("timer", self.timer)
        self.request_timeout = general_config.get(
            "request_timeout", self.request_timeout
        )
        self.ssl_verification = general_config.get(
            "ssl_verification", self.ssl_verification
        )
        self.request_timeout = general_config.get("request_timeout", self.request_timeout)
        self.ignored_download_clients = general_config.get(
            "ignored_download_clients", self.ignored_download_clients
        )

        self.private_tracker_handling = general_config.get(
            "private_tracker_handling", self.private_tracker_handling
        )
        self.public_tracker_handling = general_config.get(
            "public_tracker_handling", self.public_tracker_handling
        )

        self.obsolete_tag = general_config.get("obsolete_tag", self.obsolete_tag)
        self.protected_tag = general_config.get("protected_tag", self.protected_tag)

        # Validate tracker handling settings
        self.private_tracker_handling = self._validate_tracker_handling(
            self.private_tracker_handling, "private_tracker_handling"
        )
        self.public_tracker_handling = self._validate_tracker_handling(
            self.public_tracker_handling, "public_tracker_handling"
        )

        validate_data_types(self)
        self._remove_none_attributes()

    def _remove_none_attributes(self):
        """Remove attributes that are None to keep the object clean."""
        for attr in list(vars(self)):
            if getattr(self, attr) is None:
                delattr(self, attr)

    @staticmethod
    def _validate_tracker_handling(value, field_name) -> str:
        """Validate tracker handling options. Defaults to 'remove' if invalid."""
        if value not in VALID_TRACKER_HANDLING:
            logger.error(
                f"Invalid value '{value}' for {field_name}. Defaulting to 'remove'.",
            )
            return "remove"
        return value

    def config_as_yaml(self):
        """Log all general settings."""
        config_yaml = get_config_as_yaml(
            vars(self),
        )
        return config_yaml
