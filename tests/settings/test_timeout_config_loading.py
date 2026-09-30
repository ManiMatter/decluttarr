"""Tests that timeout values load correctly from YAML config text."""
import textwrap
from unittest.mock import Mock

import yaml

from src.settings._download_clients_qbit import QbitClients
from src.settings._download_clients_sabnzbd import SabnzbdClients
from src.settings._general import General
from src.settings._instances import ArrInstances


def parse(text):
    return yaml.safe_load(textwrap.dedent(text))


def make_settings(request_timeout=15):
    s = Mock()
    s.general.request_timeout = request_timeout
    return s


# ---------------------------------------------------------------------------
# General.request_timeout
# ---------------------------------------------------------------------------

class TestGeneralFromYaml:
    def test_request_timeout_loaded(self):
        config = parse("""
            general:
              request_timeout: 45
        """)
        assert General(config).request_timeout == 45

    def test_request_timeout_default_when_absent(self):
        config = parse("""
            general:
              log_level: INFO
        """)
        assert General(config).request_timeout == 15

    def test_request_timeout_as_string_coerced(self):
        # YAML may deliver it as int already, but verify string also works
        config = {"general": {"request_timeout": "30"}}
        assert General(config).request_timeout == 30


# ---------------------------------------------------------------------------
# ArrInstance timeout via ArrInstances loader
# ---------------------------------------------------------------------------

class TestArrInstanceFromYaml:
    def test_instance_timeout_loaded(self):
        config = parse("""
            instances:
              radarr:
                - base_url: "http://radarr/"
                  api_key: "k"
                  timeout: 60
        """)
        instances = ArrInstances(config, make_settings())
        assert instances[0].timeout == 60

    def test_instance_timeout_absent_uses_general(self):
        config = parse("""
            instances:
              radarr:
                - base_url: "http://radarr/"
                  api_key: "k"
        """)
        instances = ArrInstances(config, make_settings(request_timeout=30))
        assert instances[0].timeout == 30

    def test_mixed_instances(self):
        config = parse("""
            instances:
              radarr:
                - base_url: "http://radarr/"
                  api_key: "k"
                  timeout: 60
              sonarr:
                - base_url: "http://sonarr/"
                  api_key: "k"
        """)
        instances = ArrInstances(config, make_settings(request_timeout=20))
        radarr = next(i for i in instances if i.arr_type == "radarr")
        sonarr = next(i for i in instances if i.arr_type == "sonarr")
        assert radarr.timeout == 60
        assert sonarr.timeout == 20


# ---------------------------------------------------------------------------
# QbitClient timeout via QbitClients loader
# ---------------------------------------------------------------------------

class TestQbitClientFromYaml:
    def test_timeout_loaded(self):
        config = parse("""
            download_clients:
              qbittorrent:
                - base_url: "http://qbit/"
                  timeout: 55
        """)
        clients = QbitClients(config, make_settings())
        assert clients[0].timeout == 55

    def test_timeout_absent_uses_general(self):
        config = parse("""
            download_clients:
              qbittorrent:
                - base_url: "http://qbit/"
        """)
        clients = QbitClients(config, make_settings(request_timeout=40))
        assert clients[0].timeout == 40


# ---------------------------------------------------------------------------
# SabnzbdClient timeout via SabnzbdClients loader
# ---------------------------------------------------------------------------

class TestSabnzbdClientFromYaml:
    def test_timeout_loaded(self):
        config = parse("""
            download_clients:
              sabnzbd:
                - base_url: "http://sabnzbd/"
                  api_key: "k"
                  timeout: 70
        """)
        clients = SabnzbdClients(config, make_settings())
        assert clients[0].timeout == 70

    def test_timeout_absent_uses_general(self):
        config = parse("""
            download_clients:
              sabnzbd:
                - base_url: "http://sabnzbd/"
                  api_key: "k"
        """)
        clients = SabnzbdClients(config, make_settings(request_timeout=35))
        assert clients[0].timeout == 35
