import pytest
import yaml

from apiguard.config import ConfigError, load_config


def valid_config():
    return {
        "name": "nexstock",
        "base_url": "http://127.0.0.1:8000",
        "spec_location": "http://127.0.0.1:8000/openapi.json",
        "timeouts": {
            "request_seconds": 10,
            "run_seconds": 120,
        },
        "auth": {},
        "reset": {},
    }


def save_config(tmp_path, config):
    path = tmp_path / "nexstock.yaml"
    path.write_text(yaml.safe_dump(config), encoding="utf-8")
    return path


def test_valid_config_loads(tmp_path):
    path = save_config(tmp_path, valid_config())

    config = load_config(path)

    assert config["name"] == "nexstock"
    assert config["timeouts"]["request_seconds"] == 10


def test_missing_file_has_clear_error(tmp_path):
    with pytest.raises(ConfigError, match="Cannot read"):
        load_config(tmp_path / "missing.yaml")


def test_malformed_yaml_has_clear_error(tmp_path):
    path = tmp_path / "broken.yaml"
    path.write_text("name: [", encoding="utf-8")

    with pytest.raises(ConfigError, match="Invalid YAML"):
        load_config(path)


def test_missing_required_key(tmp_path):
    config = valid_config()
    del config["base_url"]
    path = save_config(tmp_path, config)

    with pytest.raises(ConfigError, match="base_url"):
        load_config(path)


def test_invalid_url(tmp_path):
    config = valid_config()
    config["base_url"] = "not-a-url"
    path = save_config(tmp_path, config)

    with pytest.raises(ConfigError, match="base_url"):
        load_config(path)


@pytest.mark.parametrize("field", ["request_seconds", "run_seconds"])
@pytest.mark.parametrize("value", [0, -1, "ten", True, float("inf")])
def test_invalid_timeout(tmp_path, field, value):
    config = valid_config()
    config["timeouts"][field] = value
    path = save_config(tmp_path, config)

    with pytest.raises(ConfigError, match=field):
        load_config(path)
