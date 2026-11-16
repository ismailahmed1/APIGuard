import copy

import pytest

from apiguard.openapi import SpecError, validate_spec
from apiguard.operations import Parameter, extract_operations

BEARER = {"OAuth2PasswordBearer": []}

# Shaped like FastAPI output: component schemas, a 422 validation error and OAuth2 bearer auth.
DOCUMENT = {
    "openapi": "3.1.0",
    "info": {"title": "Shop API", "version": "1.0.0"},
    "paths": {
        "/api/auth/login": {
            "post": {
                "operationId": "login",
                "summary": "Log in",
                "tags": ["Authentication"],
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/x-www-form-urlencoded": {
                            "schema": {"$ref": "#/components/schemas/Login"}
                        }
                    },
                },
                "responses": {
                    "200": {
                        "description": "OK",
                        "content": {"application/json": {"schema": {}}},
                    },
                    "422": {"$ref": "#/components/responses/Invalid"},
                },
            }
        },
        "/api/products/{product_id}": {
            "parameters": [
                {
                    "name": "product_id",
                    "in": "path",
                    "required": True,
                    "schema": {"type": "integer"},
                },
                {"name": "verbose", "in": "query", "schema": {"type": "boolean"}},
            ],
            "get": {
                "operationId": "get_product",
                "parameters": [{"$ref": "#/components/parameters/Verbose"}],
                "responses": {
                    "200": {
                        "description": "OK",
                        "content": {
                            "application/json": {"schema": {"$ref": "#/components/schemas/Product"}}
                        },
                    }
                },
                "security": [BEARER],
            },
            "delete": {
                "operationId": "delete_product",
                "responses": {"204": {"description": "Deleted"}},
                "security": [BEARER],
            },
        },
        "/api/catalog": {
            "get": {
                "responses": {"200": {"description": "OK"}},
                "security": [{}, BEARER],
            }
        },
    },
    "components": {
        "schemas": {
            "Login": {
                "title": "Login",
                "type": "object",
                "required": ["username", "password"],
                "properties": {"username": {"type": "string"}, "password": {"type": "string"}},
            },
            "Product": {
                "title": "Product",
                "type": "object",
                "properties": {
                    "id": {"type": "integer"},
                    "category": {"$ref": "#/components/schemas/Category"},
                },
            },
            "Category": {
                "title": "Category",
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "parent": {"$ref": "#/components/schemas/Category"},
                },
            },
            "Error": {"title": "Error", "type": "object"},
        },
        "parameters": {
            "Verbose": {
                "name": "verbose",
                "in": "query",
                "required": True,
                "schema": {"type": "boolean", "default": False},
            }
        },
        "responses": {
            "Invalid": {
                "description": "Validation error",
                "content": {"application/json": {"schema": {"$ref": "#/components/schemas/Error"}}},
            }
        },
        "securitySchemes": {
            "OAuth2PasswordBearer": {
                "type": "oauth2",
                "flows": {"password": {"tokenUrl": "/api/auth/login", "scopes": {}}},
            }
        },
    },
}


def by_key(operations):
    return {(operation.method, operation.path): operation for operation in operations}


def test_fixture_is_a_valid_spec():
    validate_spec(copy.deepcopy(DOCUMENT))


def test_extracts_every_operation_in_spec_order():
    operations = extract_operations(DOCUMENT)
    assert [(o.method, o.path) for o in operations] == [
        ("POST", "/api/auth/login"),
        ("GET", "/api/products/{product_id}"),
        ("DELETE", "/api/products/{product_id}"),
        ("GET", "/api/catalog"),
    ]
    login = operations[0]
    assert login.operation_id == "login"
    assert login.summary == "Log in"
    assert login.tags == ("Authentication",)


def test_resolves_request_body_and_response_references():
    login = by_key(extract_operations(DOCUMENT))[("POST", "/api/auth/login")]
    assert login.request_body.required is True
    form_schema = login.request_body.content["application/x-www-form-urlencoded"]
    assert form_schema["required"] == ["username", "password"]
    assert login.responses == {
        "200": {"application/json": {}},
        "422": {"application/json": {"title": "Error", "type": "object"}},
    }


def test_operation_parameters_replace_path_parameters():
    get_product = by_key(extract_operations(DOCUMENT))[("GET", "/api/products/{product_id}")]
    assert get_product.parameters == (
        Parameter("product_id", "path", True, {"type": "integer"}),
        # The operation's referenced parameter replaces the optional path-level one.
        Parameter("verbose", "query", True, {"type": "boolean", "default": False}),
    )
    delete_product = by_key(extract_operations(DOCUMENT))[("DELETE", "/api/products/{product_id}")]
    assert [p.required for p in delete_product.parameters] == [True, False]
    assert delete_product.request_body is None
    assert delete_product.responses == {"204": {}}


def test_recursive_schema_keeps_inner_reference():
    get_product = by_key(extract_operations(DOCUMENT))[("GET", "/api/products/{product_id}")]
    category = get_product.responses["200"]["application/json"]["properties"]["category"]
    assert category["title"] == "Category"
    assert category["properties"]["parent"] == {"$ref": "#/components/schemas/Category"}


def test_resolution_does_not_change_the_document():
    original = copy.deepcopy(DOCUMENT)
    extract_operations(DOCUMENT)
    assert DOCUMENT == original


@pytest.mark.parametrize(
    ("path", "method", "security", "requires_auth", "schemes"),
    [
        ("/api/auth/login", "POST", (), False, []),
        ("/api/products/{product_id}", "GET", (BEARER,), True, ["OAuth2PasswordBearer"]),
        ("/api/catalog", "GET", ({}, BEARER), False, ["OAuth2PasswordBearer"]),
    ],
)
def test_security_requirements(path, method, security, requires_auth, schemes):
    operation = by_key(extract_operations(DOCUMENT))[(method, path)]
    assert operation.security == security
    assert operation.requires_auth is requires_auth
    assert operation.security_schemes == schemes


def test_operation_security_overrides_global_security():
    document = copy.deepcopy(DOCUMENT)
    document["security"] = [BEARER]
    document["paths"]["/api/auth/login"]["post"]["security"] = []
    operations = by_key(extract_operations(document))
    assert operations[("POST", "/api/auth/login")].requires_auth is False
    del document["paths"]["/api/catalog"]["get"]["security"]
    operations = by_key(extract_operations(document))
    assert operations[("GET", "/api/catalog")].security == (BEARER,)


def test_reference_siblings_take_precedence():
    document = copy.deepcopy(DOCUMENT)
    response = document["paths"]["/api/auth/login"]["post"]["responses"]["200"]
    response["content"]["application/json"]["schema"] = {
        "$ref": "#/components/schemas/Error",
        "title": "LoginResult",
    }
    login = by_key(extract_operations(document))[("POST", "/api/auth/login")]
    assert login.responses["200"]["application/json"] == {"title": "LoginResult", "type": "object"}


def test_escaped_reference_tokens():
    document = copy.deepcopy(DOCUMENT)
    document["components"]["schemas"]["a/b~c"] = {"type": "string"}
    response = document["paths"]["/api/auth/login"]["post"]["responses"]["200"]
    response["content"]["application/json"]["schema"] = {"$ref": "#/components/schemas/a~1b~0c"}
    login = by_key(extract_operations(document))[("POST", "/api/auth/login")]
    assert login.responses["200"]["application/json"] == {"type": "string"}


def test_missing_reference_target():
    document = copy.deepcopy(DOCUMENT)
    response = document["paths"]["/api/auth/login"]["post"]["responses"]["200"]
    response["content"]["application/json"]["schema"] = {"$ref": "#/components/schemas/Missing"}
    with pytest.raises(SpecError, match="#/components/schemas/Missing"):
        extract_operations(document)


def test_empty_paths():
    assert extract_operations({"openapi": "3.1.0", "info": {}, "paths": {}}) == []
