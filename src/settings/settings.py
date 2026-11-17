from src.settings._constants import Envs, MinVersions, Paths
from src.settings._download_clients import DownloadClients
from src.settings._general import General
from src.settings._instances import ArrInstances
from src.settings._web import Web
from src.settings._jobs import Jobs
from src.settings._user_config import get_user_config
from src.utils.log_setup import configure_logging


class Settings:

    min_versions = MinVersions()
    paths = Paths()

    def __init__(self):
        self.envs = Envs()
        config = get_user_config(self)
        self.general = General(config)
        self.web = Web(config)
        self.jobs = Jobs(config, self)
        self.download_clients = DownloadClients(config, self)
        self.instances = ArrInstances(config, self)
        configure_logging(self)

    def __repr__(self):
        sections = [
            ("ENVIRONMENT SETTINGS", "envs"),
            ("GENERAL SETTINGS", "general"),
            ("WEB SETTINGS", "web"),
            ("ACTIVE JOBS", "jobs"),
            ("JOB SETTINGS", "jobs"),
            ("INSTANCE SETTINGS", "instances"),
            ("DOWNLOAD CLIENT SETTINGS", "download_clients"),
        ]
        messages = ["🛠️  Decluttarr - Settings 🛠️", "-" * 80]
        for title, attr_name in sections:
            section = getattr(self, attr_name, None)
            section_yaml = section.config_as_yaml()
            if title == "ACTIVE JOBS":
                messages.append(self._format_section_title(title))
                messages.append(self.jobs.list_job_status())
            elif section_yaml != "{}":
                messages.append(self._format_section_title(title))
                messages.append(section_yaml)
            messages.append("")  # Extra linebreak after section
        return "\n".join(messages)

    @staticmethod
    def _format_section_title(name, border_length=50, symbol="=") -> str:
        """Format section title with centered name and hash borders."""
        padding = max(border_length - len(name) - 2, 0)  # 4 for spaces
        left_hashes = right_hashes = padding // 2
        if padding % 2 != 0:
            right_hashes += 1
        return f"{symbol * left_hashes} {name} {symbol * right_hashes}"
