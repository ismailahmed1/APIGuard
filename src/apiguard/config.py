import math
from pathlib import Path
from urllib.parse import urlsplit

import yaml


class ConfigError(Exception):
    """A configuration problem that we can explain to the user."""


def load_config(path):
    path = Path(path)

    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigError(f"Cannot read configuration file: {path}") from exc

    try:
        config = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ConfigError(f"Invalid YAML in configuration file: {path}") from exc

    if not isinstance(config, dict):
        raise ConfigError("Configuration must contain named settings.")

    for key in ("name", "base_url", "spec_location"):
        value = config.get(key)
        if not isinstance(value, str) or not value.strip():
            raise ConfigError(f"'{key}' must be a nonempty string.")

    validate_http_url(config["base_url"], "base_url")

    # A specification may be a URL or a local file.
    spec_location = config["spec_location"]
    if "://" in spec_location:
        validate_http_url(spec_location, "spec_location")

    timeouts = config.get("timeouts")
    if not isinstance(timeouts, dict):
        raise ConfigError("'timeouts' must contain request and run limits.")

    for key in ("request_seconds", "run_seconds"):
        value = timeouts.get(key)
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            or value <= 0
        ):
            raise ConfigError(f"'timeouts.{key}' must be a positive number.")

    for key in ("auth", "reset"):
        if not isinstance(config.get(key), dict):
            raise ConfigError(f"'{key}' must contain named settings.")

    return config


def validate_http_url(value, field):
    try:
        parts = urlsplit(value)
        valid = (
            parts.scheme in ("http", "https")
            and bool(parts.hostname)
            and parts.username is None
            and parts.password is None
            and not any(character.isspace() for character in value)
        )
        # Accessing port also detects invalid port values.
        _ = parts.port
    except ValueError:
        valid = False

    if not valid:
        raise ConfigError(f"'{field}' must be an HTTP or HTTPS URL without embedded credentials.")
