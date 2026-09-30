from src.settings._config_as_yaml import get_config_as_yaml
from src.settings._download_clients_qbit import QbitClients
from src.settings._download_clients_sabnzbd import SabnzbdClients

DOWNLOAD_CLIENT_TYPES = ["qbittorrent", "sabnzbd"]


class DownloadClients:
    """Represents all download clients."""

    qbittorrent = None
    sabnzbd = None

    def __init__(self, config, settings):
        self._set_qbit_clients(config, settings)
        self._set_sabnzbd_clients(config, settings)
        self.check_unique_download_client_types()

    def _set_qbit_clients(self, config, settings):
        download_clients = config.get("download_clients", {})
        if isinstance(download_clients, dict):
            self.qbittorrent = QbitClients(config, settings)
            if (
                not self.qbittorrent
            ):  # Unsets settings in general section needed for qbit (if no qbit is defined)
                for key in [
                    "private_tracker_handling",
                    "public_tracker_handling",
                    "obsolete_tag",
                    "protected_tag",
                ]:
                    setattr(settings.general, key, None)

    def _set_sabnzbd_clients(self, config, settings):
        download_clients = config.get("download_clients", {})
        if isinstance(download_clients, dict):
            self.sabnzbd = SabnzbdClients(config, settings)
        if not self.sabnzbd:
            self.sabnzbd = SabnzbdClients({}, settings)  # Initialize empty list

    def config_as_yaml(self):
        """Log all download clients."""
        return get_config_as_yaml(
            {"qbittorrent": self.qbittorrent, "sabnzbd": self.sabnzbd},
            sensitive_attributes={"username", "password", "cookie", "api_key"},
            internal_attributes={"api_url", "cookie", "settings", "min_version"},
            hide_internal_attr=True,
        )

    def check_unique_download_client_types(self):
        """
        Ensure that all download client names are unique.

        This is important since downloadClient in arr goes by name, and
        this is needed to link it to the right IP set up in the yaml config
        (which may be different to the one configured in arr)
        """
        seen = set()
        for download_client_type in DOWNLOAD_CLIENT_TYPES:
            download_clients = getattr(self, download_client_type, [])

            # Check each client in the list
            for client in download_clients:
                name = getattr(client, "name", None)
                if name is None:
                    error = f"{download_client_type} client does not have a name ({client.base_url}).\nMake sure that the name corresponds with the name set in your *arr app for that download client."
                    raise ValueError(error)

                if name.lower() in seen:
                    error = (
                        f"Duplicate download client name detected: '{name}'.\n"
                        "Download client names must be unique across all *arr instances.\n"
                        "Ensure that the name configured for each download client in your *arr apps exactly matches the one used in your decluttarr configuration.\n"
                        "Even if the names are unique within each individual *arr instance, they must also be globally unique across all configured instances.\n"
                        "To fix this, assign a unique name to each download client in your *arr apps, and use that exact name in the decluttarr config.\n"
                        "Example:\n"
                        "If you use two qBittorrent clients—one for Radarr and one for Sonarr—name them distinctly in their respective *arr apps (e.g., 'qbittorrent_radarr' and 'qbittorrent_sonarr'), "
                        "and refer to them with those names in the decluttarr config."
                    )
                    raise ValueError(error)
                seen.add(name.lower())

    def get_download_client_by_name(
        self,
        name: str,
        download_client_type: str | None = None,
        ready_only: bool = False,
    ):
        """
        Retrieve the download client and download client type by its name.
        If download_client_type is provided, search only in that type.
        If ready_only is True, a client that failed its startup check (not ready)
        is treated as unavailable, so degraded clients never get called from jobs.
        """
        name_lower = name.lower()
        types_to_search = (
            [download_client_type] if download_client_type else DOWNLOAD_CLIENT_TYPES
        )

        for client_type in types_to_search:
            download_clients = getattr(self, client_type, [])

            for download_client in download_clients:
                if download_client.name.lower() == name_lower:
                    if ready_only and not getattr(download_client, "ready", False):
                        return None, None
                    return download_client, client_type

        return None, None

    @staticmethod
    def get_download_client_type_from_implementation(
        arr_download_client_implementation: str,
    ) -> str | None:
        """
        Maps *arr download client implementation names to decluttarr download client type
        """
        mapping = {
            "QBittorrent": "qbittorrent",
            "SABnzbd": "sabnzbd",
        }
        download_client_type = mapping.get(arr_download_client_implementation)
        return download_client_type

    def list_download_clients(self) -> dict[str, list[str]]:
        """
        Return a dict mapping download_client_type to list of client names
        for all configured download clients.
        """
        result: dict[str, list[str]] = {}

        for client_type in DOWNLOAD_CLIENT_TYPES:
            download_clients = getattr(self, client_type, [])
            result[client_type] = [client.name for client in download_clients]

        return result
