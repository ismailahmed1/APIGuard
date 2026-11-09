"""Load, validate and snapshot self-contained OpenAPI 3.x documents."""

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

import httpx
import yaml
from openapi_spec_validator import (
    OpenAPIV30SpecValidator,
    OpenAPIV31SpecValidator,
    OpenAPIV32SpecValidator,
)
from referencing.exceptions import Unresolvable


class SpecError(Exception):
    """An unreadable or invalid specification."""


@dataclass(frozen=True)
class LoadedSpec:
    document: dict
    raw: bytes


def get_response(url, timeout):
    """Leave HTTP exceptions for the CLI to translate into exit code 1."""
    response = httpx.get(url, timeout=timeout, follow_redirects=True)
    response.raise_for_status()
    return response


def pointer(parts):
    """Format a location as a JSON Pointer, escaping special characters."""
    return "#" + "".join("/" + str(p).replace("~", "~0").replace("/", "~1") for p in parts)


def check_structure(value, path=(), ancestors=None):
    """Reject non-JSON YAML values and external references before validation."""
    ancestors = set() if ancestors is None else ancestors
    if isinstance(value, (dict, list)):
        if id(value) in ancestors:
            raise SpecError(f"{pointer(path)}: recursive YAML aliases are not supported.")
        ancestors.add(id(value))
        items = value.items() if isinstance(value, dict) else enumerate(value)
        for key, child in items:
            if isinstance(value, dict) and not isinstance(key, str):
                raise SpecError(f"{pointer(path)}: object keys must be strings.")
            if (
                key in ("$ref", "$dynamicRef")
                and isinstance(child, str)
                and not child.startswith("#")
            ):
                raise SpecError(
                    f"{pointer((*path, key))}: external references are not supported; "
                    "use a self-contained specification."
                )
            check_structure(child, (*path, key), ancestors)
        ancestors.remove(id(value))
    elif value is not None and not isinstance(value, (str, bool, int, float)):
        raise SpecError(f"{pointer(path)}: value is not a JSON-compatible value.")


def validate_spec(document):
    if not isinstance(document, dict):
        raise SpecError("#: specification must be an object.")
    check_structure(document)
    try:
        json.dumps(document, allow_nan=False)
    except (ValueError, OverflowError) as exc:
        raise SpecError("#: specification contains a non-finite number.") from exc

    version = document.get("openapi")
    if not isinstance(version, str) or not re.fullmatch(r"3\.[012]\.\d+", version):
        raise SpecError("#/openapi: expected a supported OpenAPI version (3.0, 3.1 or 3.2).")
    validators = {
        "3.0": OpenAPIV30SpecValidator,
        "3.1": OpenAPIV31SpecValidator,
        "3.2": OpenAPIV32SpecValidator,
    }
    try:
        errors = list(validators[version[:3]](document).iter_errors())
    except Unresolvable as exc:
        raise SpecError("#: a local $ref could not be resolved; check its target.") from exc
    if errors:
        details = sorted(f"{pointer(error.absolute_path)}: {error.message}" for error in errors)
        raise SpecError("Invalid OpenAPI specification:\n" + "\n".join(details))


def load_spec(location, timeout):
    """Relative file paths resolve from the current working directory."""
    if "://" in location:
        if urlsplit(location).scheme not in ("http", "https"):
            raise SpecError("Specification URL must use HTTP or HTTPS.")
        raw = get_response(location, timeout).content
        filename = urlsplit(location).path
    else:
        try:
            raw = Path(location).read_bytes()
        except OSError as exc:
            raise SpecError(f"Cannot read specification file: {location}") from exc
        filename = location
    try:
        text = raw.decode("utf-8-sig")
        if filename.lower().endswith(".json") or text.lstrip().startswith(("{", "[")):
            document = json.loads(text)
        else:
            document = yaml.safe_load(text)
    except (UnicodeError, json.JSONDecodeError, yaml.YAMLError) as exc:
        raise SpecError("Cannot parse specification as UTF-8 JSON or YAML.") from exc
    validate_spec(document)
    return LoadedSpec(document=document, raw=raw)


def save_snapshot(spec, suite_directory):
    """Save exact source bytes and their hash; JSON is also valid YAML."""
    directory = Path(suite_directory)
    digest = hashlib.sha256(spec.raw).hexdigest()
    try:
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "openapi.yaml").write_bytes(spec.raw)
        (directory / "openapi.sha256").write_text(digest + "\n", encoding="ascii")
    except OSError as exc:
        raise SpecError(f"Cannot save specification snapshot in: {directory}") from exc
    return digest
