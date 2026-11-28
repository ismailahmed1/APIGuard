# APIGuard tests for the NexStock Categories operations.
# Each test runs on freshly reset seed data. Writes use the admin role.


# ---------------------------------------------------------------------------
# GET /api/categories
# ---------------------------------------------------------------------------

def test_categories_list_admin_happy_path(api):
    api.check("GET", "/api/categories", "admin", 200,
              test_id="categories-list-admin-200", test_type="happy_path")


def test_categories_list_manager_happy_path(api):
    api.check("GET", "/api/categories", "manager", 200,
              test_id="categories-list-manager-200", test_type="happy_path")


def test_categories_list_contains_seed_categories(api):
    resp = api.request("admin", "GET", "/api/categories")
    assert resp.status_code == 200
    data = resp.json()
    items = data if isinstance(data, list) else data.get("items", data.get("data", []))
    names = {item.get("name") for item in items if isinstance(item, dict)}
    assert "Electronics" in names
    assert "Consumables" in names


def test_categories_list_anonymous_unauthorized(api):
    api.check("GET", "/api/categories", "anonymous", 401,
              test_id="categories-list-anonymous-401", test_type="authentication")


# ---------------------------------------------------------------------------
# POST /api/categories
# ---------------------------------------------------------------------------

def test_categories_create_happy_path(api):
    api.check("POST", "/api/categories", "admin", 201,
              body={"name": "APIGuard Test Category", "description": "Created by APIGuard"},
              test_id="categories-create-201", test_type="happy_path")


def test_categories_create_without_description(api):
    api.check("POST", "/api/categories", "admin", 201,
              body={"name": "APIGuard No Description"},
              test_id="categories-create-no-description-201", test_type="happy_path")


def test_categories_create_null_description(api):
    api.check("POST", "/api/categories", "admin", 201,
              body={"name": "APIGuard Null Description", "description": None},
              test_id="categories-create-null-description-201", test_type="schema_validation")


def test_categories_create_anonymous_unauthorized(api):
    api.check("POST", "/api/categories", "anonymous", 401,
              body={"name": "APIGuard Anonymous Category"},
              test_id="categories-create-anonymous-401", test_type="authentication")


def test_categories_create_missing_name(api):
    api.check("POST", "/api/categories", "admin", 422,
              body={"description": "No name given"},
              test_id="categories-create-missing-name-422", test_type="schema_validation")


def test_categories_create_empty_body(api):
    api.check("POST", "/api/categories", "admin", 422,
              body={},
              test_id="categories-create-empty-body-422", test_type="schema_validation")


def test_categories_create_name_wrong_type(api):
    api.check("POST", "/api/categories", "admin", 422,
              body={"name": {"nested": "object"}},
              test_id="categories-create-name-wrong-type-422", test_type="schema_validation")


def test_categories_create_name_null(api):
    api.check("POST", "/api/categories", "admin", 422,
              body={"name": None},
              test_id="categories-create-name-null-422", test_type="schema_validation")


def test_categories_create_name_empty_below_min(api):
    api.check("POST", "/api/categories", "admin", 422,
              body={"name": ""},
              test_id="categories-create-name-empty-422", test_type="boundary_value")


def test_categories_create_name_min_length(api):
    api.check("POST", "/api/categories", "admin", 201,
              body={"name": "Q"},
              test_id="categories-create-name-len1-201", test_type="boundary_value")


def test_categories_create_name_max_length(api):
    api.check("POST", "/api/categories", "admin", 201,
              body={"name": "N" * 100},
              test_id="categories-create-name-len100-201", test_type="boundary_value")


def test_categories_create_name_above_max_length(api):
    api.check("POST", "/api/categories", "admin", 422,
              body={"name": "N" * 101},
              test_id="categories-create-name-len101-422", test_type="boundary_value")


def test_categories_create_description_max_length(api):
    api.check("POST", "/api/categories", "admin", 201,
              body={"name": "APIGuard Long Description", "description": "D" * 255},
              test_id="categories-create-description-len255-201", test_type="boundary_value")


def test_categories_create_description_above_max_length(api):
    api.check("POST", "/api/categories", "admin", 422,
              body={"name": "APIGuard Too Long Description", "description": "D" * 256},
              test_id="categories-create-description-len256-422", test_type="boundary_value")


def test_categories_create_description_wrong_type(api):
    api.check("POST", "/api/categories", "admin", 422,
              body={"name": "APIGuard Bad Description", "description": ["not", "a", "string"]},
              test_id="categories-create-description-wrong-type-422", test_type="schema_validation")


# ---------------------------------------------------------------------------
# GET /api/categories/{category_id}
# ---------------------------------------------------------------------------

def test_categories_get_admin_happy_path(api):
    api.check("GET", "/api/categories/{category_id}", "admin", 200,
              path_params={"category_id": "1"},
              test_id="categories-get-1-admin-200", test_type="happy_path")


def test_categories_get_manager_happy_path(api):
    api.check("GET", "/api/categories/{category_id}", "manager", 200,
              path_params={"category_id": "10"},
              test_id="categories-get-10-manager-200", test_type="happy_path")


def test_categories_get_returns_seed_name(api):
    resp = api.request("admin", "GET", "/api/categories/1")
    assert resp.status_code == 200
    assert resp.json().get("name") == "Electronics"


def test_categories_get_anonymous_unauthorized(api):
    api.check("GET", "/api/categories/{category_id}", "anonymous", 401,
              path_params={"category_id": "1"},
              test_id="categories-get-anonymous-401", test_type="authentication")


def test_categories_get_non_integer_id(api):
    api.check("GET", "/api/categories/{category_id}", "admin", 422,
              path_params={"category_id": "abc"},
              test_id="categories-get-non-integer-422", test_type="schema_validation")


def test_categories_get_decimal_id(api):
    api.check("GET", "/api/categories/{category_id}", "admin", 422,
              path_params={"category_id": "1.5"},
              test_id="categories-get-decimal-422", test_type="schema_validation")


# ---------------------------------------------------------------------------
# PUT /api/categories/{category_id}
# ---------------------------------------------------------------------------

def test_categories_update_happy_path(api):
    api.check("PUT", "/api/categories/{category_id}", "admin", 200,
              path_params={"category_id": "1"},
              body={"description": "Updated by APIGuard"},
              test_id="categories-update-description-200", test_type="happy_path")


def test_categories_update_name_happy_path(api):
    api.check("PUT", "/api/categories/{category_id}", "admin", 200,
              path_params={"category_id": "2"},
              body={"name": "APIGuard Renamed Category", "description": "Renamed"},
              test_id="categories-update-name-200", test_type="happy_path")


def test_categories_update_persists(api):
    resp = api.request("admin", "PUT", "/api/categories/3",
                       json={"description": "APIGuard persisted description"})
    assert resp.status_code == 200
    follow = api.request("admin", "GET", "/api/categories/3")
    assert follow.status_code == 200
    assert follow.json().get("description") == "APIGuard persisted description"


def test_categories_update_anonymous_unauthorized(api):
    api.check("PUT", "/api/categories/{category_id}", "anonymous", 401,
              path_params={"category_id": "1"},
              body={"description": "Anonymous update"},
              test_id="categories-update-anonymous-401", test_type="authentication")


def test_categories_update_non_integer_id(api):
    api.check("PUT", "/api/categories/{category_id}", "admin", 422,
              path_params={"category_id": "abc"},
              body={"description": "Bad id"},
              test_id="categories-update-non-integer-422", test_type="schema_validation")


def test_categories_update_name_empty_below_min(api):
    api.check("PUT", "/api/categories/{category_id}", "admin", 422,
              path_params={"category_id": "1"},
              body={"name": ""},
              test_id="categories-update-name-empty-422", test_type="boundary_value")


def test_categories_update_name_min_length(api):
    api.check("PUT", "/api/categories/{category_id}", "admin", 200,
              path_params={"category_id": "4"},
              body={"name": "Z"},
              test_id="categories-update-name-len1-200", test_type="boundary_value")


def test_categories_update_name_max_length(api):
    api.check("PUT", "/api/categories/{category_id}", "admin", 200,
              path_params={"category_id": "4"},
              body={"name": "U" * 100},
              test_id="categories-update-name-len100-200", test_type="boundary_value")


def test_categories_update_name_above_max_length(api):
    api.check("PUT", "/api/categories/{category_id}", "admin", 422,
              path_params={"category_id": "1"},
              body={"name": "U" * 101},
              test_id="categories-update-name-len101-422", test_type="boundary_value")


def test_categories_update_description_max_length(api):
    api.check("PUT", "/api/categories/{category_id}", "admin", 200,
              path_params={"category_id": "5"},
              body={"description": "D" * 255},
              test_id="categories-update-description-len255-200", test_type="boundary_value")


def test_categories_update_description_above_max_length(api):
    api.check("PUT", "/api/categories/{category_id}", "admin", 422,
              path_params={"category_id": "1"},
              body={"description": "D" * 256},
              test_id="categories-update-description-len256-422", test_type="boundary_value")


def test_categories_update_name_wrong_type(api):
    api.check("PUT", "/api/categories/{category_id}", "admin", 422,
              path_params={"category_id": "1"},
              body={"name": ["not", "a", "string"]},
              test_id="categories-update-name-wrong-type-422", test_type="schema_validation")


# ---------------------------------------------------------------------------
# DELETE /api/categories/{category_id}
# ---------------------------------------------------------------------------

def test_categories_delete_happy_path(api):
    created = api.request("admin", "POST", "/api/categories",
                          json={"name": "APIGuard Category To Delete", "description": "Temporary"})
    assert created.status_code == 201
    new_id = created.json()["id"]
    api.check("DELETE", "/api/categories/{category_id}", "admin", 200,
              path_params={"category_id": str(new_id)},
              test_id="categories-delete-200", test_type="happy_path")


def test_categories_delete_anonymous_unauthorized(api):
    api.check("DELETE", "/api/categories/{category_id}", "anonymous", 401,
              path_params={"category_id": "1"},
              test_id="categories-delete-anonymous-401", test_type="authentication")


def test_categories_delete_non_integer_id(api):
    api.check("DELETE", "/api/categories/{category_id}", "admin", 422,
              path_params={"category_id": "abc"},
              test_id="categories-delete-non-integer-422", test_type="schema_validation")
