"""Tests for configurable request timeouts (general + per-instance)."""
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from src.settings._download_clients_qbit import QbitClient
from src.settings._download_clients_sabnzbd import SabnzbdClient
from src.settings._general import General
from src.settings._instances import ArrInstance
from src.utils.common import make_request


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_settings(request_timeout=15):
    s = Mock()
    s.general.request_timeout = request_timeout
    s.general.test_run = False
    s.general.ssl_verification = True
    return s


def make_general(request_timeout=None):
    cfg = {}
    if request_timeout is not None:
        cfg["general"] = {"request_timeout": request_timeout}
    return General(cfg)


# ---------------------------------------------------------------------------
# General settings
# ---------------------------------------------------------------------------

class TestGeneralRequestTimeout:
    def test_default_is_15(self):
        g = make_general()
        assert g.request_timeout == 15

    def test_loads_from_config(self):
        g = make_general(request_timeout=60)
        assert g.request_timeout == 60

    def test_string_value_coerced_to_int(self):
        g = General({"general": {"request_timeout": "30"}})
        assert g.request_timeout == 30
        assert isinstance(g.request_timeout, int)


# ---------------------------------------------------------------------------
# ArrInstance.timeout property
# ---------------------------------------------------------------------------

class TestArrInstanceTimeout:
    def test_falls_back_to_15_with_empty_settings(self):
        arr = ArrInstance({}, "radarr", "http://radarr/", "key")
        assert arr.timeout == 15

    def test_falls_back_to_general_request_timeout(self):
        arr = ArrInstance(make_settings(request_timeout=20), "radarr", "http://radarr/", "key")
        assert arr.timeout == 20

    def test_per_instance_timeout_overrides_general(self):
        arr = ArrInstance(make_settings(request_timeout=20), "radarr", "http://radarr/", "key", timeout=45)
        assert arr.timeout == 45

    def test_general_timeout_change_reflected_dynamically(self):
        settings = make_settings(request_timeout=20)
        arr = ArrInstance(settings, "radarr", "http://radarr/", "key")
        assert arr.timeout == 20
        settings.general.request_timeout = 99
        assert arr.timeout == 99

    def test_instance_timeout_not_affected_by_general_change(self):
        settings = make_settings(request_timeout=20)
        arr = ArrInstance(settings, "radarr", "http://radarr/", "key", timeout=45)
        settings.general.request_timeout = 99
        assert arr.timeout == 45


# ---------------------------------------------------------------------------
# QbitClient.timeout property
# ---------------------------------------------------------------------------

class TestQbitClientTimeout:
    def _make_client(self, general_timeout=15, instance_timeout=None):
        settings = make_settings(request_timeout=general_timeout)
        kwargs = dict(settings=settings, base_url="http://qbit/", name="qBittorrent")
        if instance_timeout is not None:
            kwargs["timeout"] = instance_timeout
        return QbitClient(**kwargs)

    def test_falls_back_to_general_request_timeout(self):
        assert self._make_client(general_timeout=25).timeout == 25

    def test_per_instance_timeout_overrides_general(self):
        assert self._make_client(general_timeout=25, instance_timeout=50).timeout == 50

    def test_general_timeout_change_reflected_dynamically(self):
        client = self._make_client(general_timeout=25)
        client.settings.general.request_timeout = 77
        assert client.timeout == 77


# ---------------------------------------------------------------------------
# SabnzbdClient.timeout property
# ---------------------------------------------------------------------------

class TestSabnzbdClientTimeout:
    def _make_client(self, general_timeout=15, instance_timeout=None):
        settings = make_settings(request_timeout=general_timeout)
        kwargs = dict(settings=settings, base_url="http://sabnzbd/", api_key="key")
        if instance_timeout is not None:
            kwargs["timeout"] = instance_timeout
        return SabnzbdClient(**kwargs)

    def test_falls_back_to_general_request_timeout(self):
        assert self._make_client(general_timeout=25).timeout == 25

    def test_per_instance_timeout_overrides_general(self):
        assert self._make_client(general_timeout=25, instance_timeout=50).timeout == 50

    def test_general_timeout_change_reflected_dynamically(self):
        client = self._make_client(general_timeout=25)
        client.settings.general.request_timeout = 77
        assert client.timeout == 77


# ---------------------------------------------------------------------------
# make_request passes timeout through correctly
# ---------------------------------------------------------------------------

class TestMakeRequestTimeout:
    @pytest.mark.asyncio
    async def test_uses_explicit_timeout(self):
        settings = make_settings()
        captured = {}

        async def fake_thread(fn, *args, **kwargs):
            captured["timeout"] = kwargs.get("timeout")
            resp = MagicMock()
            resp.raise_for_status = MagicMock()
            return resp

        with patch("src.utils.common.asyncio.to_thread", side_effect=fake_thread):
            await make_request("get", "http://example.com", settings, timeout=42)

        assert captured["timeout"] == 42

    @pytest.mark.asyncio
    async def test_default_timeout_is_15(self):
        settings = make_settings()
        captured = {}

        async def fake_thread(fn, *args, **kwargs):
            captured["timeout"] = kwargs.get("timeout")
            resp = MagicMock()
            resp.raise_for_status = MagicMock()
            return resp

        with patch("src.utils.common.asyncio.to_thread", side_effect=fake_thread):
            await make_request("get", "http://example.com", settings)

        assert captured["timeout"] == 15
