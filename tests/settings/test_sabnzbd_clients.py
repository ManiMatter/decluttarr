from unittest.mock import AsyncMock, Mock

import pytest

from src.settings._download_clients_sabnzbd import SabnzbdClient, SabnzbdClients


class TestSabnzbdClient:
    def test_init_minimal_config(self):
        """Test SabnzbdClient initialization with minimal required config."""
        settings = Mock()
        settings.min_versions = Mock()
        settings.min_versions.sabnzbd = "4.0.0"
        client = SabnzbdClient(
            settings=settings, base_url="http://sabnzbd:8080", api_key="test_api_key"
        )
        assert client.base_url == "http://sabnzbd:8080"
        assert client.api_url == "http://sabnzbd:8080/api"
        assert client.api_key == "test_api_key"
        assert client.name == "SABnzbd"

    def test_init_full_config(self):
        """Test SabnzbdClient initialization with full config."""
        settings = Mock()
        settings.min_versions = Mock()
        settings.min_versions.sabnzbd = "4.0.0"
        client = SabnzbdClient(
            settings=settings,
            base_url="http://sabnzbd:8080/",
            api_key="test_api_key",
            name="Custom SABnzbd",
        )
        assert client.base_url == "http://sabnzbd:8080"
        assert client.api_url == "http://sabnzbd:8080/api"
        assert client.api_key == "test_api_key"
        assert client.name == "Custom SABnzbd"

    def test_init_missing_base_url(self):
        """Test SabnzbdClient initialization fails without base_url."""
        settings = Mock()
        with pytest.raises(ValueError, match="SABnzbd client must have a 'base_url'"):
            SabnzbdClient(settings=settings, api_key="test_api_key")

    def test_init_missing_api_key(self):
        """Test SabnzbdClient initialization fails without api_key."""
        settings = Mock()
        with pytest.raises(ValueError, match="SABnzbd client must have an 'api_key'"):
            SabnzbdClient(settings=settings, base_url="http://sabnzbd:8080")

    @pytest.mark.asyncio
    async def test_get_download_progress(self):
        """Test getting download progress for a specific download."""
        settings = Mock()
        settings.min_versions = Mock()
        settings.min_versions.sabnzbd = "4.0.0"
        client = SabnzbdClient(
            settings=settings, base_url="http://sabnzbd:8080", api_key="test_api_key"
        )
        # Mock the get_queue_items method
        client.get_queue_items = AsyncMock(
            return_value=[
                {"nzo_id": "test_id_1", "mb": "1000", "mbleft": "200"},
                {"nzo_id": "test_id_2", "mb": "2000", "mbleft": "1000"},
            ]
        )
        # Test getting progress for existing download
        progress = await client.fetch_download_progress("test_id_1")
        expected_bytes = (1000 - 200) * 1024 * 1024  # 800 MB in bytes
        assert progress == expected_bytes
        # Test getting progress for non-existing download
        progress = await client.fetch_download_progress("non_existing_id")
        assert progress is None


class TestSabnzbdClients:
    def test_init_empty_config(self):
        """Test SabnzbdClients initialization with empty config."""
        config = {"download_clients": {}}
        settings = Mock()
        clients = SabnzbdClients(config, settings)
        assert len(clients) == 0

    def test_init_valid_config(self):
        """Test SabnzbdClients initialization with valid config."""
        config = {
            "download_clients": {
                "sabnzbd": [
                    {"base_url": "http://sabnzbd1:8080", "api_key": "api_key_1"},
                    {
                        "base_url": "http://sabnzbd2:8080",
                        "api_key": "api_key_2",
                        "name": "SABnzbd 2",
                    },
                ]
            }
        }
        settings = Mock()
        settings.min_versions = Mock()
        settings.min_versions.sabnzbd = "4.0.0"
        clients = SabnzbdClients(config, settings)
        assert len(clients) == 2
        assert clients[0].base_url == "http://sabnzbd1:8080"
        assert clients[0].api_key == "api_key_1"
        assert clients[0].name == "SABnzbd"
        assert clients[1].base_url == "http://sabnzbd2:8080"
        assert clients[1].api_key == "api_key_2"
        assert clients[1].name == "SABnzbd 2"

    def test_init_invalid_config_format(self, caplog):
        """Test SabnzbdClients initialization with invalid config format."""
        config = {"download_clients": {"sabnzbd": "not_a_list"}}
        settings = Mock()
        clients = SabnzbdClients(config, settings)
        assert len(clients) == 0
        assert "Invalid config format for sabnzbd clients" in caplog.text

    def test_init_missing_required_field(self, caplog):
        """Test SabnzbdClients initialization with missing required fields."""
        config = {
            "download_clients": {
                "sabnzbd": [
                    {
                        "base_url": "http://sabnzbd:8080"
                        # Missing api_key
                    }
                ]
            }
        }
        settings = Mock()
        clients = SabnzbdClients(config, settings)
        assert len(clients) == 0
        assert "Error parsing sabnzbd client config" in caplog.text


class TestSabnzbdSetupDegradation:
    @pytest.mark.asyncio
    async def test_setup_reachability_timeout_marks_transient(self):
        from unittest.mock import patch

        import requests

        settings = Mock()
        settings.min_versions.sabnzbd = "4.0.0"
        client = SabnzbdClient(
            settings=settings, base_url="http://sabnzbd:8080", api_key="key"
        )

        with patch(
            "src.settings._download_clients_sabnzbd.make_request",
            new_callable=AsyncMock,
            side_effect=requests.exceptions.ReadTimeout("Read timed out."),
        ):
            result = await client.setup()

        assert result is False
        assert client.ready is False
        assert client.failure_kind == "transient"

    @pytest.mark.asyncio
    async def test_setup_old_version_marks_definitive(self):
        settings = Mock()
        settings.min_versions.sabnzbd = "4.0.0"
        client = SabnzbdClient(
            settings=settings, base_url="http://sabnzbd:8080", api_key="key"
        )
        client.check_sabnzbd_reachability = AsyncMock()
        client.fetch_version = AsyncMock()
        client.version = "3.0.0"

        await client.setup()

        assert client.ready is False
        assert client.failure_kind == "definitive"


class TestSabnzbdBadKey:
    @pytest.mark.asyncio
    async def test_setup_bad_api_key_marks_definitive(self):
        from unittest.mock import MagicMock, patch

        settings = Mock()
        settings.min_versions.sabnzbd = "4.0.0"
        client = SabnzbdClient(
            settings=settings, base_url="http://sabnzbd:8080", api_key="bad"
        )
        resp = MagicMock()
        resp.json = MagicMock(return_value={"error": "API Key Incorrect"})
        with patch(
            "src.settings._download_clients_sabnzbd.make_request",
            new_callable=AsyncMock,
            return_value=resp,
        ):
            await client.setup()

        assert client.ready is False
        assert client.failure_kind == "definitive"
