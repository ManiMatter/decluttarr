from unittest.mock import Mock

from src.settings._instances import ArrInstances


def make_settings():
    s = Mock()
    s.general.request_timeout = 15
    return s


def test_api_key_read_from_file(tmp_path):
    key_file = tmp_path / "radarr_api_key"
    key_file.write_text("secret-key\n", encoding="utf-8")
    config = {
        "instances": {
            "radarr": [{"base_url": "http://radarr/", "api_key_file": str(key_file)}]
        }
    }
    instances = ArrInstances(config, make_settings())
    assert instances[0].api_key == "secret-key"


def test_api_key_file_takes_precedence(tmp_path):
    key_file = tmp_path / "sonarr_api_key"
    key_file.write_text("from-file", encoding="utf-8")
    config = {
        "instances": {
            "sonarr": [
                {
                    "base_url": "http://sonarr/",
                    "api_key": "from-config",
                    "api_key_file": str(key_file),
                }
            ]
        }
    }
    instances = ArrInstances(config, make_settings())
    assert instances[0].api_key == "from-file"


def test_missing_api_key_file_skips_instance(tmp_path):
    config = {
        "instances": {
            "radarr": [
                {"base_url": "http://radarr/", "api_key_file": str(tmp_path / "nope")},
                {"base_url": "http://radarr2/", "api_key": "k"},
            ]
        }
    }
    instances = ArrInstances(config, make_settings())
    assert [i.api_key for i in instances] == ["k"]
