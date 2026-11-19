"""A small FastAPI-style specification shared by the generation, validation and runner tests."""

BEARER = [{"OAuth2PasswordBearer": []}]

SHOP = {
    "openapi": "3.1.0",
    "info": {"title": "Shop", "version": "1"},
    "paths": {
        "/api/auth/login": {
            "post": {
                "tags": ["Auth"],
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {"schema": {"$ref": "#/components/schemas/Login"}}
                    },
                },
                "responses": {"200": {"description": "OK"}, "422": {"description": "Invalid"}},
            }
        },
        "/api/products": {
            "get": {
                "tags": ["Products"],
                "responses": {
                    "200": {
                        "description": "OK",
                        "content": {
                            "application/json": {"schema": {"type": "object", "required": ["data"]}}
                        },
                    }
                },
                "security": BEARER,
            },
            "post": {
                "tags": ["Products"],
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {"schema": {"$ref": "#/components/schemas/New"}}
                    },
                },
                "responses": {"201": {"description": "Created"}, "422": {"description": "Bad"}},
                "security": BEARER,
            },
        },
        "/api/products/{product_id}": {
            "delete": {
                "tags": ["Products"],
                "parameters": [
                    {
                        "name": "product_id",
                        "in": "path",
                        "required": True,
                        "schema": {"type": "integer"},
                    }
                ],
                "responses": {"200": {"description": "OK"}, "422": {"description": "Bad"}},
                "security": BEARER,
            }
        },
        "/api/upload": {
            "post": {
                "tags": ["Other"],
                "requestBody": {"content": {"multipart/form-data": {"schema": {"type": "object"}}}},
                "responses": {"200": {"description": "OK"}},
            }
        },
    },
    "components": {
        "schemas": {
            "Login": {
                "type": "object",
                "required": ["email", "password"],
                "properties": {"email": {"type": "string"}, "password": {"type": "string"}},
            },
            "New": {
                "title": "New",
                "type": "object",
                "required": ["name", "price"],
                "properties": {
                    "name": {"type": "string", "minLength": 1},
                    "price": {"type": "number", "exclusiveMinimum": 0},
                },
            },
        },
        "securitySchemes": {
            "OAuth2PasswordBearer": {
                "type": "oauth2",
                "flows": {"password": {"tokenUrl": "/api/auth/login", "scopes": {}}},
            }
        },
    },
}


def raw_test(**changes):
    """A valid generated definition for POST /api/products, with optional changes."""
    test = {
        "id": "products-001",
        "type": "happy_path",
        "description": "Admin creates a product",
        "method": "POST",
        "path": "/api/products",
        "role": "admin",
        "path_params": [],
        "query_params": [],
        "body_json": '{"name": "Lamp", "price": 9.5}',
        "expected_status": 201,
    }
    test.update(changes)
    return test
