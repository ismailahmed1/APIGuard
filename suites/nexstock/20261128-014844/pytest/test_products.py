"""APIGuard tests for NexStock Products operations."""


def _new_product(sku="TEST-001", **overrides):
    body = {
        "sku": sku,
        "name": "Test Product",
        "description": "Created by APIGuard",
        "category_id": 1,
        "unit_price": 19.99,
        "minimum_quantity": 5,
        "maximum_quantity": 100,
    }
    body.update(overrides)
    return body


# ---------------- GET /api/products ----------------

def test_products_list_admin_happy(api):
    api.check("GET", "/api/products", "admin", 200, test_id="products-list-admin", test_type="happy_path")


def test_products_list_manager_happy(api):
    api.check("GET", "/api/products", "manager", 200, test_id="products-list-manager", test_type="happy_path")


def test_products_list_filter_by_category(api):
    api.check("GET", "/api/products", "admin", 200, query_params={"category_id": "1"}, test_id="products-list-filter-category", test_type="happy_path")


def test_products_list_filter_category_contents(api):
    resp = api.request("admin", "GET", "/api/products", params={"category_id": "1"})
    assert resp.status_code == 200
    data = resp.json()
    items = data if isinstance(data, list) else data.get("items", data.get("data", []))
    assert len(items) >= 1
    for item in items:
        if isinstance(item, dict) and "category_id" in item:
            assert item["category_id"] == 1


def test_products_list_filter_invalid_category_type(api):
    api.check("GET", "/api/products", "admin", 422, query_params={"category_id": "abc"}, test_id="products-list-filter-invalid-type", test_type="schema_validation")


def test_products_list_anonymous_unauthorized(api):
    api.check("GET", "/api/products", "anonymous", 401, test_id="products-list-anonymous", test_type="authentication")


# ---------------- POST /api/products ----------------

def test_products_create_admin_happy(api):
    api.check("POST", "/api/products", "admin", 201, body=_new_product("TEST-001"), test_id="products-create-admin", test_type="happy_path")


def test_products_create_required_fields_only(api):
    body = {"sku": "TEST-002", "name": "Minimal Product", "category_id": 2, "unit_price": 5.5}
    api.check("POST", "/api/products", "admin", 201, body=body, test_id="products-create-minimal", test_type="happy_path")


def test_products_create_then_get(api):
    resp = api.request("admin", "POST", "/api/products", json=_new_product("TEST-003", name="Chained Product"))
    assert resp.status_code == 201
    product_id = resp.json()["id"]
    get_resp = api.request("admin", "GET", f"/api/products/{product_id}")
    assert get_resp.status_code == 200
    data = get_resp.json()
    assert data["sku"] == "TEST-003"
    assert data["name"] == "Chained Product"


def test_products_create_anonymous_unauthorized(api):
    api.check("POST", "/api/products", "anonymous", 401, body=_new_product("TEST-004"), test_id="products-create-anonymous", test_type="authentication")


def test_products_create_missing_sku(api):
    body = _new_product()
    del body["sku"]
    api.check("POST", "/api/products", "admin", 422, body=body, test_id="products-create-missing-sku", test_type="schema_validation")


def test_products_create_missing_name(api):
    body = _new_product("TEST-005")
    del body["name"]
    api.check("POST", "/api/products", "admin", 422, body=body, test_id="products-create-missing-name", test_type="schema_validation")


def test_products_create_missing_category(api):
    body = _new_product("TEST-006")
    del body["category_id"]
    api.check("POST", "/api/products", "admin", 422, body=body, test_id="products-create-missing-category", test_type="schema_validation")


def test_products_create_missing_unit_price(api):
    body = _new_product("TEST-007")
    del body["unit_price"]
    api.check("POST", "/api/products", "admin", 422, body=body, test_id="products-create-missing-price", test_type="schema_validation")


def test_products_create_invalid_category_type(api):
    api.check("POST", "/api/products", "admin", 422, body=_new_product("TEST-008", category_id="abc"), test_id="products-create-category-type", test_type="schema_validation")


def test_products_create_empty_body(api):
    api.check("POST", "/api/products", "admin", 422, body={}, test_id="products-create-empty-body", test_type="schema_validation")


def test_products_create_sku_min_length_valid(api):
    api.check("POST", "/api/products", "admin", 201, body=_new_product("ABC"), test_id="products-create-sku-len-3", test_type="boundary")


def test_products_create_sku_too_short(api):
    api.check("POST", "/api/products", "admin", 422, body=_new_product("AB"), test_id="products-create-sku-len-2", test_type="boundary")


def test_products_create_sku_max_length_valid(api):
    api.check("POST", "/api/products", "admin", 201, body=_new_product("S" * 50), test_id="products-create-sku-len-50", test_type="boundary")


def test_products_create_sku_too_long(api):
    api.check("POST", "/api/products", "admin", 422, body=_new_product("S" * 51), test_id="products-create-sku-len-51", test_type="boundary")


def test_products_create_name_empty(api):
    api.check("POST", "/api/products", "admin", 422, body=_new_product("TEST-009", name=""), test_id="products-create-name-empty", test_type="boundary")


def test_products_create_name_min_length_valid(api):
    api.check("POST", "/api/products", "admin", 201, body=_new_product("TEST-010", name="N"), test_id="products-create-name-len-1", test_type="boundary")


def test_products_create_name_max_length_valid(api):
    api.check("POST", "/api/products", "admin", 201, body=_new_product("TEST-011", name="N" * 100), test_id="products-create-name-len-100", test_type="boundary")


def test_products_create_name_too_long(api):
    api.check("POST", "/api/products", "admin", 422, body=_new_product("TEST-012", name="N" * 101), test_id="products-create-name-len-101", test_type="boundary")


def test_products_create_description_max_length_valid(api):
    api.check("POST", "/api/products", "admin", 201, body=_new_product("TEST-013", description="D" * 255), test_id="products-create-desc-len-255", test_type="boundary")


def test_products_create_description_too_long(api):
    api.check("POST", "/api/products", "admin", 422, body=_new_product("TEST-014", description="D" * 256), test_id="products-create-desc-len-256", test_type="boundary")


def test_products_create_unit_price_zero(api):
    api.check("POST", "/api/products", "admin", 422, body=_new_product("TEST-015", unit_price=0), test_id="products-create-price-zero", test_type="boundary")


def test_products_create_unit_price_negative(api):
    api.check("POST", "/api/products", "admin", 422, body=_new_product("TEST-016", unit_price=-1.5), test_id="products-create-price-negative", test_type="boundary")


def test_products_create_unit_price_small_positive(api):
    api.check("POST", "/api/products", "admin", 201, body=_new_product("TEST-017", unit_price=0.01), test_id="products-create-price-small", test_type="boundary")


def test_products_create_minimum_quantity_zero(api):
    api.check("POST", "/api/products", "admin", 201, body=_new_product("TEST-018", minimum_quantity=0), test_id="products-create-minqty-zero", test_type="boundary")


def test_products_create_minimum_quantity_negative(api):
    api.check("POST", "/api/products", "admin", 422, body=_new_product("TEST-019", minimum_quantity=-1), test_id="products-create-minqty-negative", test_type="boundary")


def test_products_create_maximum_quantity_negative(api):
    api.check("POST", "/api/products", "admin", 422, body=_new_product("TEST-020", maximum_quantity=-1), test_id="products-create-maxqty-negative", test_type="boundary")


# ---------------- GET /api/products/{product_id} ----------------

def test_products_get_admin_happy(api):
    api.check("GET", "/api/products/{product_id}", "admin", 200, path_params={"product_id": "1"}, test_id="products-get-admin", test_type="happy_path")


def test_products_get_manager_happy(api):
    api.check("GET", "/api/products/{product_id}", "manager", 200, path_params={"product_id": "30"}, test_id="products-get-manager", test_type="happy_path")


def test_products_get_seed_values(api):
    resp = api.request("admin", "GET", "/api/products/1")
    assert resp.status_code == 200
    data = resp.json()
    assert data["sku"] == "ELEC-001"
    assert data["name"] == "Electronics Item 1"
    assert data["category_id"] == 1


def test_products_get_invalid_id_type(api):
    api.check("GET", "/api/products/{product_id}", "admin", 422, path_params={"product_id": "abc"}, test_id="products-get-invalid-id", test_type="schema_validation")


def test_products_get_anonymous_unauthorized(api):
    api.check("GET", "/api/products/{product_id}", "anonymous", 401, path_params={"product_id": "1"}, test_id="products-get-anonymous", test_type="authentication")


# ---------------- PUT /api/products/{product_id} ----------------

def test_products_update_admin_happy(api):
    api.check("PUT", "/api/products/{product_id}", "admin", 200, path_params={"product_id": "1"}, body={"name": "Updated Electronics Item 1", "unit_price": 29.99}, test_id="products-update-admin", test_type="happy_path")


def test_products_update_then_get(api):
    resp = api.request("admin", "PUT", "/api/products/2", json={"description": "Updated description"})
    assert resp.status_code == 200
    get_resp = api.request("admin", "GET", "/api/products/2")
    assert get_resp.status_code == 200
    assert get_resp.json()["description"] == "Updated description"


def test_products_update_empty_body(api):
    api.check("PUT", "/api/products/{product_id}", "admin", 200, path_params={"product_id": "3"}, body={}, test_id="products-update-empty-body", test_type="happy_path")


def test_products_update_anonymous_unauthorized(api):
    api.check("PUT", "/api/products/{product_id}", "anonymous", 401, path_params={"product_id": "1"}, body={"name": "Nope"}, test_id="products-update-anonymous", test_type="authentication")


def test_products_update_invalid_id_type(api):
    api.check("PUT", "/api/products/{product_id}", "admin", 422, path_params={"product_id": "abc"}, body={"name": "X"}, test_id="products-update-invalid-id", test_type="schema_validation")


def test_products_update_invalid_category_type(api):
    api.check("PUT", "/api/products/{product_id}", "admin", 422, path_params={"product_id": "1"}, body={"category_id": "abc"}, test_id="products-update-category-type", test_type="schema_validation")


def test_products_update_sku_too_short(api):
    api.check("PUT", "/api/products/{product_id}", "admin", 422, path_params={"product_id": "1"}, body={"sku": "AB"}, test_id="products-update-sku-len-2", test_type="boundary")


def test_products_update_sku_too_long(api):
    api.check("PUT", "/api/products/{product_id}", "admin", 422, path_params={"product_id": "1"}, body={"sku": "S" * 51}, test_id="products-update-sku-len-51", test_type="boundary")


def test_products_update_sku_max_length_valid(api):
    api.check("PUT", "/api/products/{product_id}", "admin", 200, path_params={"product_id": "1"}, body={"sku": "U" * 50}, test_id="products-update-sku-len-50", test_type="boundary")


def test_products_update_name_empty(api):
    api.check("PUT", "/api/products/{product_id}", "admin", 422, path_params={"product_id": "1"}, body={"name": ""}, test_id="products-update-name-empty", test_type="boundary")


def test_products_update_name_too_long(api):
    api.check("PUT", "/api/products/{product_id}", "admin", 422, path_params={"product_id": "1"}, body={"name": "N" * 101}, test_id="products-update-name-len-101", test_type="boundary")


def test_products_update_name_max_length_valid(api):
    api.check("PUT", "/api/products/{product_id}", "admin", 200, path_params={"product_id": "1"}, body={"name": "N" * 100}, test_id="products-update-name-len-100", test_type="boundary")


def test_products_update_description_too_long(api):
    api.check("PUT", "/api/products/{product_id}", "admin", 422, path_params={"product_id": "1"}, body={"description": "D" * 256}, test_id="products-update-desc-len-256", test_type="boundary")


def test_products_update_unit_price_zero(api):
    api.check("PUT", "/api/products/{product_id}", "admin", 422, path_params={"product_id": "1"}, body={"unit_price": 0}, test_id="products-update-price-zero", test_type="boundary")


def test_products_update_minimum_quantity_negative(api):
    api.check("PUT", "/api/products/{product_id}", "admin", 422, path_params={"product_id": "1"}, body={"minimum_quantity": -1}, test_id="products-update-minqty-negative", test_type="boundary")


def test_products_update_maximum_quantity_negative(api):
    api.check("PUT", "/api/products/{product_id}", "admin", 422, path_params={"product_id": "1"}, body={"maximum_quantity": -1}, test_id="products-update-maxqty-negative", test_type="boundary")


# ---------------- DELETE /api/products/{product_id} ----------------

def test_products_delete_admin_happy(api):
    api.check("DELETE", "/api/products/{product_id}", "admin", 200, path_params={"product_id": "30"}, test_id="products-delete-admin", test_type="happy_path")


def test_products_delete_created_product(api):
    resp = api.request("admin", "POST", "/api/products", json=_new_product("TEST-DEL-001"))
    assert resp.status_code == 201
    product_id = resp.json()["id"]
    del_resp = api.request("admin", "DELETE", f"/api/products/{product_id}")
    assert del_resp.status_code == 200


def test_products_delete_invalid_id_type(api):
    api.check("DELETE", "/api/products/{product_id}", "admin", 422, path_params={"product_id": "abc"}, test_id="products-delete-invalid-id", test_type="schema_validation")


def test_products_delete_anonymous_unauthorized(api):
    api.check("DELETE", "/api/products/{product_id}", "anonymous", 401, path_params={"product_id": "30"}, test_id="products-delete-anonymous", test_type="authentication")
