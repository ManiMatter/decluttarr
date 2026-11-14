from packaging import version

from src.settings._constants import MinVersions
from src.utils.common import is_definitive_setup_error, make_request
from src.utils.log_setup import logger


class SabnzbdError(Exception):
    def __init__(self, message, tip="", definitive=False):
        super().__init__(message)
        self.tip = tip
        self.definitive = definitive


class SabnzbdClients(list):
    """Represents all SABnzbd clients."""

    def __init__(self, config, settings):
        super().__init__()
        self._set_sabnzbd_clients(config, settings)

    def _set_sabnzbd_clients(self, config, settings):
        sabnzbd_config = config.get("download_clients", {}).get("sabnzbd", [])

        if not isinstance(sabnzbd_config, list):
            logger.error(
                "Invalid config format for sabnzbd clients. Expected a list.",
            )
            return

        for client_config in sabnzbd_config:
            try:
                self.append(SabnzbdClient(settings, **client_config))
            except (TypeError, ValueError) as e:
                logger.error(f"Error parsing sabnzbd client config: {e}")


class SabnzbdClient:
    """Represents a single SABnzbd client."""

    version: str = None
    ready: bool = False
    failure_kind: str = None  # None | "transient" | "definitive"
    last_error: str = None
    setup_tip: str = ""

    def __init__(
        self,
        settings,
        base_url: str = None,
        api_key: str = None,
        name: str = None,
        timeout: int | None = None,
    ):
        self.settings = settings
        self._timeout = timeout
        if not base_url:
            logger.error("Skipping SABnzbd client entry: 'base_url' is required.")
            error = "SABnzbd client must have a 'base_url'."
            raise ValueError(error)

        if not api_key:
            logger.error("Skipping SABnzbd client entry: 'api_key' is required.")
            error = "SABnzbd client must have an 'api_key'."
            raise ValueError(error)

        self.base_url = base_url.rstrip("/")
        self.api_url = self.base_url + "/api"
        self.min_version = MinVersions.sabnzbd
        self.api_key = api_key
        self.name = name
        if not self.name:
            logger.verbose(
                "No name provided for sabnzbd client, assuming 'SABnzbd'. If the name used in your *arr is different, please correct either the name in your *arr, or set the name in your config"
            )
            self.name = "SABnzbd"

        self._remove_none_attributes()

    @property
    def timeout(self):
        instance_timeout = getattr(self, "_timeout", None)
        if instance_timeout is not None:
            return instance_timeout
        return getattr(getattr(self.settings, "general", None), "request_timeout", 15)

    def _remove_none_attributes(self):
        """Remove attributes that are None to keep the object clean."""
        for attr in list(vars(self)):
            if getattr(self, attr) is None:
                delattr(self, attr)

    async def fetch_version(self):
        """Fetch the current SABnzbd version."""
        logger.debug(
            "_download_clients_sabnzbd.py/fetch_version: Getting SABnzbd Version"
        )
        params = {"mode": "version", "apikey": self.api_key, "output": "json"}
        response = await make_request("get", self.api_url, self.settings, timeout=self.timeout, params=params)
        response_data = response.json()
        self.version = response_data.get("version", "unknown")
        logger.debug(
            f"_download_clients_sabnzbd.py/fetch_version: SABnzbd version={self.version}"
        )

    async def validate_version(self):
        """Check if the SABnzbd version meets minimum requirements."""
        min_version = self.settings.min_versions.sabnzbd

        if version.parse(self.version) < version.parse(min_version):
            logger.error(
                f"Please update SABnzbd to at least version {min_version}. Current version: {self.version}",
            )
            error = f"SABnzbd version {self.version} is too old. Please update."
            raise SabnzbdError(error, definitive=True)

    async def check_sabnzbd_reachability(self):
        """Check if the SABnzbd URL is reachable (and the API key works)."""
        try:
            logger.debug(
                "_download_clients_sabnzbd.py/check_sabnzbd_reachability: Checking if SABnzbd is reachable"
            )
            params = {"mode": "version", "apikey": self.api_key, "output": "json"}
            response = await make_request(
                "get",
                self.api_url,
                self.settings,
                timeout=self.timeout,
                params=params,
                log_error=False,
                ignore_test_run=True,
            )
        except Exception as e:  # noqa: BLE001
            tip = "💡 Tip: Did you specify the URL and API key correctly?"
            if str(e) != self.last_error:  # Only report new failure modes in full
                logger.error(f"-- | SABnzbd\n❗️ {e}\n{tip}\n")
            raise SabnzbdError(e, tip=tip) from e

        # Bad API key: SABnzbd answers HTTP 200 with {"error": "API Key Incorrect"}.
        # Treat as a definitive config error so we don't retry-loop forever.
        try:
            error_msg = response.json().get("error")
        except (ValueError, AttributeError):
            error_msg = None
        if error_msg:
            tip = "💡 Tip: Check the SABnzbd API key."
            error = f"SABnzbd rejected the request: {error_msg}"
            if error != self.last_error:
                logger.error(f"-- | SABnzbd\n❗️ {error}\n{tip}\n")
            raise SabnzbdError(error, tip=tip, definitive=True)

    async def check_connected(self):
        """Check if SABnzbd is connected and operational."""
        logger.debug(
            "_download_clients_sabnzbd.py/check_connected: Checking if SABnzbd is connected"
        )
        params = {"mode": "status", "apikey": self.api_key, "output": "json"}
        response = await make_request(
            "get",
            self.api_url,
            self.settings,
            timeout=self.timeout,
            params=params,
        )
        status_data = response.json()
        # SABnzbd doesn't have a direct "disconnected" status like qBittorrent
        # We check if we can get status successfully
        return "status" in status_data

    async def setup(self):
        """Perform the SABnzbd setup; degrade instead of exiting on failure."""
        try:
            await self.check_sabnzbd_reachability()

            # Fetch version and validate it
            await self.fetch_version()
            await self.validate_version()

            logger.info(f"OK | SABnzbd ({self.base_url})")
            self.ready = True
            self.failure_kind = None
            self.last_error = None
            self.setup_tip = ""
        except Exception as e:  # noqa: BLE001
            if not isinstance(e, SabnzbdError) and str(e) != self.last_error:
                logger.error(
                    f"Unhandled error during SABnzbd setup: {e}", exc_info=True
                )
            self.ready = False
            self.failure_kind = (
                "definitive" if is_definitive_setup_error(e) else "transient"
            )
            self.last_error = str(e)
            self.setup_tip = getattr(e, "tip", "")
        return self.ready

    async def get_queue_items(self):
        """Fetch queue items from SABnzbd."""
        logger.debug(
            "_download_clients_sabnzbd.py/get_queue_items: Getting queue items"
        )
        params = {"mode": "queue", "apikey": self.api_key, "output": "json"}
        response = await make_request(
            "get",
            self.api_url,
            self.settings,
            timeout=self.timeout,
            params=params,
        )
        queue_data = response.json()
        return queue_data.get("queue", {}).get("slots", [])

    async def get_history_items(self):
        """Fetch history items from SABnzbd."""
        logger.debug(
            "_download_clients_sabnzbd.py/get_history_items: Getting history items"
        )
        params = {"mode": "history", "apikey": self.api_key, "output": "json"}
        response = await make_request(
            "get",
            self.api_url,
            self.settings,
            timeout=self.timeout,
            params=params,
        )
        history_data = response.json()
        return history_data.get("history", {}).get("slots", [])

    async def remove_download(self, nzo_id: str):
        """Remove a download from SABnzbd queue."""
        logger.debug(
            f"_download_clients_sabnzbd.py/remove_download: Removing download {nzo_id}"
        )
        params = {
            "mode": "queue",
            "name": "delete",
            "value": nzo_id,
            "apikey": self.api_key,
            "output": "json",
        }
        await make_request(
            "get",
            self.api_url,
            self.settings,
            timeout=self.timeout,
            params=params,
        )

    async def pause_download(self, nzo_id: str):
        """Pause a download in SABnzbd queue."""
        logger.debug(
            f"_download_clients_sabnzbd.py/pause_download: Pausing download {nzo_id}"
        )
        params = {
            "mode": "queue",
            "name": "pause",
            "value": nzo_id,
            "apikey": self.api_key,
            "output": "json",
        }
        await make_request(
            "get",
            self.api_url,
            self.settings,
            timeout=self.timeout,
            params=params,
        )

    async def resume_download(self, nzo_id: str):
        """Resume a download in SABnzbd queue."""
        logger.debug(
            f"_download_clients_sabnzbd.py/resume_download: Resuming download {nzo_id}"
        )
        params = {
            "mode": "queue",
            "name": "resume",
            "value": nzo_id,
            "apikey": self.api_key,
            "output": "json",
        }
        await make_request(
            "get",
            self.api_url,
            self.settings,
            timeout=self.timeout,
            params=params,
        )

    async def retry_download(self, nzo_id: str):
        """Retry a failed download from SABnzbd history."""
        logger.debug(
            f"_download_clients_sabnzbd.py/retry_download: Retrying download {nzo_id}"
        )
        params = {
            "mode": "retry",
            "value": nzo_id,
            "apikey": self.api_key,
            "output": "json",
        }
        await make_request(
            "get",
            self.api_url,
            self.settings,
            timeout=self.timeout,
            params=params,
        )

    async def fetch_download_progress(self, nzo_id: str):
        """Get progress of a specific download in bytes."""
        queue_items = await self.get_queue_items()
        for item in queue_items:
            if item.get("nzo_id") == nzo_id:
                # Calculate progress in bytes
                size_total_mb = float(item.get("mb", 0))
                size_left_mb = float(item.get("mbleft", 0))
                downloaded_mb = size_total_mb - size_left_mb
                downloaded_bytes = downloaded_mb * 1024 * 1024  # Convert MB to bytes
                return downloaded_bytes
        return None

    async def get_item_download_speed(self, nzo_id: str):
        """Get download speed for a specific item using mbleft and timeleft."""
        queue_items = await self.get_queue_items()
        for item in queue_items:
            if item.get("nzo_id") == nzo_id:
                mbleft = float(item.get("mbleft", 0))
                timeleft_str = item.get("timeleft", "0:00:00")
                timeleft_seconds = self._parse_timeleft_to_seconds(timeleft_str)
                # Calculate speed in KB/s: remaining MB divided by remaining time
                speed_kbs = 0.0
                if timeleft_seconds > 0 and mbleft > 0:
                    speed_mbs = mbleft / timeleft_seconds  # MB per second
                    speed_kbs = speed_mbs * 1024  # Convert to KB/s
                return speed_kbs
        return None

    def _parse_timeleft_to_seconds(self, timeleft_str: str) -> int:
        """Parse timeleft format like '0:16:44' or '3:11:03:24' to total seconds."""
        try:
            parts = timeleft_str.split(":")
            if len(parts) == 4:  # "D:HH:MM:SS"
                days, hours, minutes, seconds = map(int, parts)
                return days * 86400 + hours * 3600 + minutes * 60 + seconds
            if len(parts) == 3:  # "H:MM:SS"
                hours, minutes, seconds = map(int, parts)
                return hours * 3600 + minutes * 60 + seconds
            if len(parts) == 2:  # "MM:SS"
                minutes, seconds = map(int, parts)
                return minutes * 60 + seconds
            return 0
        except (ValueError, AttributeError):
            return 0

    async def get_download_speed(self):
        """Get current download speed from SABnzbd status."""
        params = {"mode": "status", "apikey": self.api_key, "output": "json"}
        response = await make_request(
            "get",
            self.api_url,
            self.settings,
            timeout=self.timeout,
            params=params,
        )
        status_data = response.json()
        speed_str = status_data.get("status", {}).get("speed", "0 KB/s")
        # Convert speed string to KB/s
        # SABnzbd returns speed like "1.2 MB/s", "500 KB/s", etc.
        if "MB/s" in speed_str:
            speed_value = float(speed_str.replace(" MB/s", ""))
            return speed_value * 1024  # Convert MB/s to KB/s
        if "KB/s" in speed_str:
            speed_value = float(speed_str.replace(" KB/s", ""))
            return speed_value
        return 0.0
