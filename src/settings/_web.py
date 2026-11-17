from src.settings._config_as_yaml import get_config_as_yaml
from src.settings._validate_data_types import validate_data_types


class Web:
    """Represents web UI settings."""

    enabled: bool = True
    host: str = "0.0.0.0"
    port: int = 9999
    proxy_prefix: str | None = None
    db_path: str | None = None

    def __init__(self, config):
        web_config = config.get("web", {})
        self.enabled = web_config.get("enabled", self.enabled)
        self.host = web_config.get("host", self.host)
        self.port = web_config.get("port", self.port)
        self.proxy_prefix = web_config.get("proxy_prefix", self.proxy_prefix)
        self.db_path = web_config.get("db_path", self.db_path)

        validate_data_types(self)
        self._remove_none_attributes()

    def _remove_none_attributes(self):
        """Remove attributes that are None to keep the object clean."""
        for attr in list(vars(self)):
            if getattr(self, attr) is None:
                delattr(self, attr)

    def config_as_yaml(self):
        return get_config_as_yaml(vars(self))
