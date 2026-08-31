from pathlib import Path

import requests
from packaging import version

from src.settings._config_as_yaml import get_config_as_yaml
from src.settings._constants import (
    ApiEndpoints,
    DetailItemKey,
    DetailItemSearchCommand,
    FullQueueParameter,
    MinVersions,
    RefreshItemCommand,
    RefreshItemKey,
)
from src.utils.common import (
    extract_json_from_response,
    is_definitive_setup_error,
    make_request,
    wait_and_exit,
)
from src.utils.log_setup import logger


class Tracker:
    def __init__(self):
        self.protected = []
        self.private = []
        self.defective = {}
        self.download_progress = {}
        self.deleted = []
        self.extension_checked = []

    def reset(self) -> None:
        for attr in (
            self.protected,
            self.private,
            self.defective,
            self.download_progress,
            self.deleted,
            self.extension_checked,
        ):
            attr.clear()

    async def refresh_private_and_protected(self, settings):
        protected_downloads = []
        private_downloads = []

        for qbit in settings.download_clients.qbittorrent:
            if not qbit.ready:
                continue
            protected, private = await qbit.get_protected_and_private()
            protected_downloads.extend(protected)
            private_downloads.extend(private)

        # Include UI-protected downloads from the web database
        try:
            import os
            from src.web.database import DEFAULT_DB_PATH
            db_path = os.environ.get("DECLUTTARR_DB_PATH", DEFAULT_DB_PATH)
            if os.path.exists(db_path):
                import aiosqlite
                async with aiosqlite.connect(db_path) as conn:
                    cursor = await conn.execute("SELECT download_id FROM protected_downloads")
                    rows = await cursor.fetchall()
                    for row in rows:
                        if row[0] not in protected_downloads:
                            protected_downloads.append(row[0])
        except Exception:
            pass  # Database may not exist if web is disabled

        self.protected = protected_downloads
        self.private = private_downloads


class ArrError(Exception):
    def __init__(self, message, tip="", definitive=False):
        super().__init__(message)
        self.tip = tip
        self.definitive = definitive


class ArrInstances(list):
    """Represents all Arr clients (Sonarr, Radarr, etc.)."""

    def __init__(self, config, settings):
        super().__init__()
        self._load_clients(config, settings)
        self.check_any_arrs()

    def config_as_yaml(self, *, hide_internal_attr=True):
        internal_attributes = {
            "tracker",
            "settings",
            "api_url",
            "min_version",
            "arr_type",
            "full_queue_parameter",
            "monitored_item",
            "detail_item_key",
            "detail_item_id_key",
            "detail_item_ids_key",
            "detail_item_search_command",
            "refresh_item_key",
            "refresh_item_id_key",
            "refresh_item_command",
        }

        outputs = []
        for arr_type in ["sonarr", "radarr", "readarr", "lidarr", "whisparr"]:
            arrs = self.get_by_arr_type(arr_type)
            if arrs:
                output = get_config_as_yaml(
                    {arr_type.capitalize(): arrs},
                    sensitive_attributes={"api_key"},
                    internal_attributes=internal_attributes,
                    hide_internal_attr=hide_internal_attr,
                )
                outputs.append(output)

        return "\n".join(outputs)

    def get_by_arr_type(self, arr_type):
        return [arr for arr in self if arr.arr_type == arr_type]

    def check_any_arrs(self):
        if not self:
            logger.error("No valid Arr instances found in the config.")
            wait_and_exit()

    def _load_clients(self, config, settings):
        instances_config = config.get("instances", {})

        if not isinstance(instances_config, dict):
            logger.error("Invalid format for 'instances'. Expected a dictionary.")
            return

        for arr_type, clients in instances_config.items():
            if not isinstance(clients, list):
                logger.error(f"Invalid config format for {arr_type}. Expected a list.")
                continue

            for client_config in clients:
                try:
                    self.append(
                        ArrInstance(
                            settings,
                            arr_type=arr_type,
                            base_url=client_config["base_url"],
                            api_key=client_config["api_key"],
                            timeout=client_config.get("timeout"),
                        ),
                    )
                except KeyError as e:
                    error = f"Missing required key {e} in {arr_type} client config."
                    logger.error(error)


class ArrInstance:
    """Represents an individual Arr instance (Sonarr, Radarr, etc.)."""

    version: str = None
    name: str = None
    ready: bool = False
    failure_kind: str = None  # None | "transient" | "definitive"
    last_error: str = None
    setup_tip: str = ""

    def __init__(self, settings, arr_type: str, base_url: str, api_key: str, timeout: int | None = None):
        if not base_url:
            logger.error(f"Skipping {arr_type} client entry: 'base_url' is required.")
            error = f"{arr_type} client must have a 'base_url'."
            raise ValueError(error)

        if not api_key:
            logger.error(f"Skipping {arr_type} client entry: 'api_key' is required.")
            error = f"{arr_type} client must have an 'api_key'."
            raise ValueError(error)

        self.settings = settings
        self._timeout = timeout
        self.tracker = Tracker()
        self.arr_type = arr_type
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.api_url = self.base_url + getattr(ApiEndpoints, arr_type)
        self.min_version = getattr(MinVersions, arr_type)
        self.full_queue_parameter = getattr(FullQueueParameter, arr_type)
        self.detail_item_key = getattr(DetailItemKey, arr_type)
        self.detail_item_id_key = self.detail_item_key + "Id"
        self.detail_item_ids_key = self.detail_item_key + "Ids"
        self.detail_item_search_command = getattr(DetailItemSearchCommand, arr_type)
        if self.arr_type in ("radarr", "sonarr"):
            self.refresh_item_key = getattr(RefreshItemKey, arr_type)
            self.refresh_item_id_key = self.refresh_item_key + "Id"
            self.refresh_item_command = getattr(RefreshItemCommand, arr_type)

    @property
    def timeout(self):
        if self._timeout is not None:
            return self._timeout
        return getattr(getattr(self.settings, "general", None), "request_timeout", 15)

    async def _check_ui_language(self):
        """Check if the UI language is set to English."""
        endpoint = self.api_url + "/config/ui"
        headers = {"X-Api-Key": self.api_key}
        response = await make_request("get", endpoint, self.settings, timeout=self.timeout, headers=headers)
        ui_language = (response.json())["uiLanguage"]
        if ui_language > 1:  # Not English
            logger.error("!! %s Error: !!", self.name)
            logger.error(
                f"> Decluttarr only works correctly if UI language is set to English (under Settings/UI in {self.name})",
            )
            logger.error(
                "> Details: https://github.com/ManiMatter/decluttarr/issues/132)",
            )
            error = "Not English"
            tip = f"💡 Tip: Set the UI language to English in {self.name} (under Settings/UI)"
            raise ArrError(error, tip=tip, definitive=True)

    def _check_min_version(self, status):
        """Check if ARR instance meets minimum version requirements."""
        self.version = status["version"]
        min_version = getattr(self.settings.min_versions, self.arr_type)

        if min_version and version.parse(self.version) < version.parse(min_version):
            logger.error("!! %s Error: !!", self.name)
            logger.error(
                f"> Please update {self.name} ({self.base_url}) to at least version {min_version}. Current version: {self.version}",
            )
            error = f"Not meeting minimum version requirements: {min_version}"
            logger.error(error)

    def _check_arr_type(self, status):
        """Check if the ARR instance is of the correct type."""
        actual_arr_type = status["appName"]
        if actual_arr_type.lower() != self.arr_type:
            logger.error("!! %s Error: !!", self.name)
            logger.error(
                f"> Your {self.name} ({self.base_url}) points to a {actual_arr_type} instance, rather than {self.arr_type}. Did you specify the wrong IP?",
            )
            error = "Wrong Arr Type"
            logger.error(error)

    async def _check_reachability(self):
        """Check if ARR instance is reachable."""
        try:
            logger.debug(
                "_instances.py/_check_reachability: Checking if arr instance is reachable"
            )
            endpoint = self.api_url + "/system/status"
            headers = {"X-Api-Key": self.api_key}
            response = await make_request(
                "get",
                endpoint,
                self.settings,
                timeout=self.timeout,
                headers=headers,
                log_error=False,
            )
            return response.json()
        except Exception as e:
            if isinstance(e, requests.exceptions.HTTPError):
                response = getattr(e, "response", None)
                if (
                    response is not None and response.status_code == 401
                ):  # noqa: PLR2004
                    tip = "💡 Tip: Have you configured the API_KEY correctly?"
                else:
                    tip = f"💡 Tip: HTTP error occurred. Status: {getattr(response, 'status_code', 'unknown')}"
            elif isinstance(e, requests.exceptions.RequestException):
                tip = "💡 Tip: Have you configured the URL correctly?"
            else:
                tip = ""

            if str(e) != self.last_error:  # Only report new failure modes in full
                logger.error(f"-- | {self.arr_type} ({self.base_url})\n❗️ {e}\n{tip}\n")
            raise ArrError(e, tip=tip) from e

    async def setup(self):
        """Check on specific ARR instance; degrade instead of exiting on failure."""
        try:
            status = await self._check_reachability()
            self.name = status.get("instanceName", self.arr_type)
            self._check_arr_type(status)
            self._check_min_version(status)
            await self._check_ui_language()

            # Display result
            logger.info(f"OK | {self.name} ({self.base_url})")
            logger.debug(f"Current version of {self.name}: {self.version}")
            await self._check_matching_decluttarr_download_clients()

            self.ready = True
            self.failure_kind = None
            self.last_error = None
            self.setup_tip = ""
        except Exception as e:  # noqa: BLE001
            if not isinstance(e, ArrError) and str(e) != self.last_error:
                logger.error(f"Unhandled error: {e}", exc_info=True)
            self.ready = False
            self.failure_kind = (
                "definitive" if is_definitive_setup_error(e) else "transient"
            )
            self.last_error = str(e)
            self.setup_tip = getattr(e, "tip", "")
        return self.ready

    async def fetch_arr_download_clients(self) -> list[dict[str, object]]:
        """Fetch the list of download clients from the *arr API."""
        logger.debug(
            "_instances.py/fetch_download_clients: Fetching download client list from arr API"
        )
        endpoint = self.api_url + "/downloadclient"
        headers = {"X-Api-Key": self.api_key}

        response = await make_request("get", endpoint, self.settings, timeout=self.timeout, headers=headers)
        return extract_json_from_response(response)

    async def _check_matching_decluttarr_download_clients(self):
        """Checks if there are any matching decluttarr settings for the download clients present in the arr"""
        arr_download_clients = await self.fetch_arr_download_clients()
        download_clients = self.settings.download_clients
        for arr_download_client in arr_download_clients:
            # Check if the download client in arr corresponds to one that decluttarr supports
            arr_download_client_name = arr_download_client.get("name")
            arr_implementation = arr_download_client.get("implementation")
            download_client_type = (
                download_clients.get_download_client_type_from_implementation(
                    arr_implementation
                )
            )
            # If it is supported, check if there are any configured in decluttarr that match on the name
            if download_client_type:
                download_client, _ = download_clients.get_download_client_by_name(
                    name=arr_download_client_name,
                    download_client_type=download_client_type,
                )
                if not download_client:
                    download_client_list = download_clients.list_download_clients().get(
                        download_client_type
                    )
                    if not download_client_list:
                        tip = (
                            f"💡 Tip: In the settings of your {self.name} instance, you have a {download_client_type} download client configured named '{arr_download_client_name}'.\n"
                            "However, in your decluttarr settings under 'download_clients', there is nothing configured.\n"
                            "Adding a matching entry to your decluttarr settings will enable you to fully leverage the features and benefits that decluttarr brings."
                        )
                    else:
                        tip = (
                            f"💡 Tip: In the settings of your {self.name} instance, you have a {download_client_type} download client configured named '{arr_download_client_name}'.\n"
                            "However, in your decluttarr settings under 'download_clients', there is no entry that matches this name.\n"
                            "Adding a matching entry to your decluttarr settings will enable you to fully leverage the features and benefits that decluttarr brings.\n"
                            f"Currently, your configured download clients are: {download_client_list}"
                        )
                    logger.info(tip)
        return

    async def remove_queue_item(self, queue_id, *, blocklist=False):
        """
        Remove a specific queue item from the queue by its queue id.

        Sends a delete request to the API to remove the item.

        Args:
            queue_id (str): The queue ID of the queue item to be removed.
            blocklist (bool): Whether to add the item to the blocklist. Default is False.

        Returns:
            bool: Returns True if the removal was successful, False otherwise.

        """
        logger.debug(
            f"_instances.py/remove_queue_item: Removing queue item, blocklist: {blocklist}"
        )
        endpoint = f"{self.api_url}/queue/{queue_id}"
        headers = {"X-Api-Key": self.api_key}
        query = {"removeFromClient": True, "blocklist": blocklist}

        # Send the request to remove the download from the queue
        response = await make_request(
            "delete",
            endpoint,
            self.settings,
            timeout=self.timeout,
            headers=headers,
            params=query,
        )

        # If the response is successful, return True, else return False
        return response.status_code == 200  # noqa: PLR2004

    async def is_monitored(self, detail_id):
        """Check if detail item (like a book, series, etc) is monitored."""
        logger.debug(f"_instances.py/is_monitored: Checking if item is monitored")
        endpoint = f"{self.api_url}/{self.detail_item_key}/{detail_id}"
        headers = {"X-Api-Key": self.api_key}

        response = await make_request("get", endpoint, self.settings, timeout=self.timeout, headers=headers)
        return response.json()["monitored"]

    async def get_series(self):
        """Fetch download client information and return the implementation value."""
        endpoint = self.api_url + "/series"
        headers = {"X-Api-Key": self.api_key}
        response = await make_request("get", endpoint, self.settings, timeout=self.timeout, headers=headers)
        return response.json()

    async def get_root_folders(self):
        """Fetch Root folders."""
        endpoint = self.api_url + "/rootFolder"
        headers = {"X-Api-Key": self.api_key}
        response = await make_request("get", endpoint, self.settings, timeout=self.timeout, headers=headers)
        return response.json()

    async def get_refresh_item(self):
        endpoint = self.api_url + "/" + self.refresh_item_key
        headers = {"X-Api-Key": self.api_key}
        response = await make_request("get", endpoint, self.settings, timeout=self.timeout, headers=headers)
        return response.json()

    async def get_refresh_item_by_path(self, folder_path):
        """Returns the movie/series id that matches a given folder"""
        items = await self.get_refresh_item()
        for item in items:
            if Path(folder_path).is_relative_to(Path(item.get("path"))):
                return item
        return None

    async def refresh_item(self, refresh_item_id):
        # Refresh the queue by making the POST request using an external make_request function
        logger.debug("_instances.py/_refresh_item: Refreshing Item")
        await make_request(
            method="POST",
            endpoint=f"{self.api_url}/command",
            settings=self.settings,
            timeout=self.timeout,
            json={
                "name": self.refresh_item_command,
                self.refresh_item_id_key: refresh_item_id,
            },
            headers={"X-Api-Key": self.api_key},
        )
        return
