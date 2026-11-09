import hashlib
import json

import httpx
import pytest
import yaml

from apiguard.openapi import SpecError, load_spec, save_snapshot, validate_spec


def valid_document(version="3.1.0"):
    return {
        "openapi": version,
        "info": {"title": "Test API", "version": "1.0.0"},
        "paths": {},
    }


@pytest.mark.parametrize("version", ["3.0.3", "3.1.0", "3.2.0"])
@pytest.mark.parametrize("extension", ["json", "yaml"])
def test_load_local_spec(tmp_path, version, extension):
    document = valid_document(version)
    text = json.dumps(document) if extension == "json" else yaml.safe_dump(document)
    path = tmp_path / f"openapi.{extension}"
    path.write_text(text, encoding="utf-8")
    loaded = load_spec(str(path), timeout=2)
    assert loaded.document == document
    assert loaded.raw == path.read_bytes()


@pytest.mark.parametrize("extension", ["json", "yaml"])
def test_load_url(monkeypatch, extension):
    document = valid_document()
    content = json.dumps(document) if extension == "json" else yaml.safe_dump(document)
    url = f"https://example.test/openapi.{extension}"

    def fake_get(request_url, **kwargs):
        assert request_url == url
        assert kwargs == {"timeout": 2, "follow_redirects": True}
        return httpx.Response(200, text=content, request=httpx.Request("GET", url))

    monkeypatch.setattr("apiguard.openapi.httpx.get", fake_get)
    assert load_spec(url, timeout=2).document == document


def test_relative_file_uses_working_directory(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "openapi.json").write_text(json.dumps(valid_document()), encoding="utf-8")
    assert load_spec("openapi.json", 2).document == valid_document()


def test_missing_file(tmp_path):
    with pytest.raises(SpecError, match="Cannot read"):
        load_spec(str(tmp_path / "missing.json"), 2)


@pytest.mark.parametrize(
    ("name", "raw"),
    [("bad.json", b'{"openapi":'), ("bad.yaml", b"openapi: ["), ("bad.yaml", b"\xff")],
)
def test_parse_errors(tmp_path, name, raw):
    path = tmp_path / name
    path.write_bytes(raw)
    with pytest.raises(SpecError, match="Cannot parse"):
        load_spec(str(path), 2)


@pytest.mark.parametrize("document", [None, [], "hello"])
def test_requires_object(document):
    with pytest.raises(SpecError, match="must be an object"):
        validate_spec(document)


@pytest.mark.parametrize("version", [None, "2.0", "3.9.0", "3.1", 3.1])
def test_unsupported_version(version):
    with pytest.raises(SpecError, match="#/openapi"):
        validate_spec(valid_document(version))


def test_reports_multiple_errors_with_locations():
    document = valid_document()
    document["info"] = {"title": 42, "version": False}
    with pytest.raises(SpecError) as error:
        validate_spec(document)
    assert "#/info/title" in str(error.value)
    assert "#/info/version" in str(error.value)


def document_with_reference(reference):
    document = valid_document()
    document["components"] = {"schemas": {"Item": {"type": "object"}}}
    document["paths"] = {
        "/items": {
            "get": {
                "responses": {
                    "200": {
                        "description": "Success",
                        "content": {"application/json": {"schema": {"$ref": reference}}},
                    }
                }
            }
        }
    }
    return document


def test_local_reference_is_valid():
    validate_spec(document_with_reference("#/components/schemas/Item"))


def test_missing_reference_has_clear_error():
    with pytest.raises(SpecError, match="could not be resolved"):
        validate_spec(document_with_reference("#/components/schemas/Missing"))


def test_external_reference_rejected_without_request(monkeypatch):
    def unexpected_request(*args, **kwargs):
        pytest.fail("External references must not trigger HTTP requests.")

    monkeypatch.setattr("httpx.get", unexpected_request)
    with pytest.raises(SpecError, match="external references"):
        validate_spec(document_with_reference("https://example.test/schema.json"))


def test_recursive_yaml_alias_has_clear_error():
    document = valid_document()
    document["x-recursive"] = document
    with pytest.raises(SpecError, match="recursive YAML"):
        validate_spec(document)


@pytest.mark.parametrize("value", [float("nan"), float("inf")])
def test_non_finite_values_rejected(value):
    document = valid_document()
    document["x-number"] = value
    with pytest.raises(SpecError, match="non-finite"):
        validate_spec(document)


@pytest.mark.parametrize("exception", [httpx.ConnectError, httpx.ReadTimeout])
def test_network_failure_propagates(monkeypatch, exception):
    def fake_get(url, **kwargs):
        raise exception("simulated failure", request=httpx.Request("GET", url))

    monkeypatch.setattr("apiguard.openapi.httpx.get", fake_get)
    with pytest.raises(exception):
        load_spec("https://example.test/openapi.json", 2)


def test_http_failure_propagates(monkeypatch):
    def fake_get(url, **kwargs):
        return httpx.Response(503, request=httpx.Request("GET", url))

    monkeypatch.setattr("apiguard.openapi.httpx.get", fake_get)
    with pytest.raises(httpx.HTTPStatusError):
        load_spec("https://example.test/openapi.json", 2)


def test_snapshot_preserves_bytes_and_hash(tmp_path):
    source = tmp_path / "source.yaml"
    raw = ("# Preserve this comment\n" + yaml.safe_dump(valid_document())).encode("utf-8")
    source.write_bytes(raw)
    spec = load_spec(str(source), 2)
    target = tmp_path / "suites" / "nexstock" / "run-1"
    digest = save_snapshot(spec, target)
    saved = (target / "openapi.yaml").read_bytes()
    assert saved == raw
    assert digest == hashlib.sha256(saved).hexdigest()
    assert (target / "openapi.sha256").read_text().strip() == digest
    assert save_snapshot(spec, target) == digest


def test_snapshot_write_failure(tmp_path):
    source = tmp_path / "source.json"
    source.write_text(json.dumps(valid_document()), encoding="utf-8")
    spec = load_spec(str(source), 2)
    occupied = tmp_path / "not-a-directory"
    occupied.write_text("occupied", encoding="utf-8")
    with pytest.raises(SpecError, match="Cannot save"):
        save_snapshot(spec, occupied)
