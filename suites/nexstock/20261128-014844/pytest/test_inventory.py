"""APIGuard tests for NexStock Inventory operations."""


# ---------------------------------------------------------------------------
# GET /api/inventory
# ---------------------------------------------------------------------------

def test_inventory_list_admin_happy(api):
    api.check("GET", "/api/inventory", "admin", 200,
              test_id="INV-LIST-001", test_type="happy_path")


def test_inventory_list_manager_happy(api):
    api.check("GET", "/api/inventory", "manager", 200,
              test_id="INV-LIST-002", test_type="happy_path")


def test_inventory_list_anonymous_unauthorized(api):
    api.check("GET", "/api/inventory", "anonymous", 401,
              test_id="INV-LIST-003", test_type="authentication")


# ---------------------------------------------------------------------------
# GET /api/inventory/movements
# ---------------------------------------------------------------------------

def test_inventory_movements_admin_happy(api):
    api.check("GET", "/api/inventory/movements", "admin", 200,
              test_id="INV-MOV-001", test_type="happy_path")


def test_inventory_movements_manager_happy(api):
    api.check("GET", "/api/inventory/movements", "manager", 200,
              test_id="INV-MOV-002", test_type="happy_path")


def test_inventory_movements_filter_product(api):
    api.check("GET", "/api/inventory/movements", "admin", 200,
              query_params={"product_id": "1"},
              test_id="INV-MOV-003", test_type="happy_path")


def test_inventory_movements_filter_type_in(api):
    api.check("GET", "/api/inventory/movements", "admin", 200,
              query_params={"type": "IN"},
              test_id="INV-MOV-004", test_type="happy_path")


def test_inventory_movements_filter_type_out(api):
    api.check("GET", "/api/inventory/movements", "manager", 200,
              query_params={"type": "OUT"},
              test_id="INV-MOV-005", test_type="happy_path")


def test_inventory_movements_filter_date_range(api):
    api.check("GET", "/api/inventory/movements", "admin", 200,
              query_params={"from_date": "2000-01-01", "to_date": "2100-12-31"},
              test_id="INV-MOV-006", test_type="happy_path")


def test_inventory_movements_all_filters(api):
    api.check("GET", "/api/inventory/movements", "admin", 200,
              query_params={"product_id": "1", "type": "IN",
                            "from_date": "2000-01-01", "to_date": "2100-12-31"},
              test_id="INV-MOV-007", test_type="happy_path")


def test_inventory_movements_anonymous_unauthorized(api):
    api.check("GET", "/api/inventory/movements", "anonymous", 401,
              test_id="INV-MOV-008", test_type="authentication")


def test_inventory_movements_invalid_type_enum(api):
    api.check("GET", "/api/inventory/movements", "admin", 422,
              query_params={"type": "TRANSFER"},
              test_id="INV-MOV-009", test_type="schema_validation")


def test_inventory_movements_lowercase_type(api):
    api.check("GET", "/api/inventory/movements", "admin", 422,
              query_params={"type": "in"},
              test_id="INV-MOV-010", test_type="schema_validation")


def test_inventory_movements_non_integer_product_id(api):
    api.check("GET", "/api/inventory/movements", "admin", 422,
              query_params={"product_id": "abc"},
              test_id="INV-MOV-011", test_type="schema_validation")


def test_inventory_movements_invalid_from_date(api):
    api.check("GET", "/api/inventory/movements", "admin", 422,
              query_params={"from_date": "2024-13-01"},
              test_id="INV-MOV-012", test_type="schema_validation")


def test_inventory_movements_invalid_to_date(api):
    api.check("GET", "/api/inventory/movements", "admin", 422,
              query_params={"to_date": "not-a-date"},
              test_id="INV-MOV-013", test_type="schema_validation")


# ---------------------------------------------------------------------------
# GET /api/inventory/{product_id}
# ---------------------------------------------------------------------------

def test_inventory_detail_admin_happy(api):
    api.check("GET", "/api/inventory/{product_id}", "admin", 200,
              path_params={"product_id": "1"},
              test_id="INV-DET-001", test_type="happy_path")


def test_inventory_detail_manager_happy(api):
    api.check("GET", "/api/inventory/{product_id}", "manager", 200,
              path_params={"product_id": "6"},
              test_id="INV-DET-002", test_type="happy_path")


def test_inventory_detail_last_product(api):
    api.check("GET", "/api/inventory/{product_id}", "admin", 200,
              path_params={"product_id": "30"},
              test_id="INV-DET-003", test_type="boundary_value")


def test_inventory_detail_anonymous_unauthorized(api):
    api.check("GET", "/api/inventory/{product_id}", "anonymous", 401,
              path_params={"product_id": "1"},
              test_id="INV-DET-004", test_type="authentication")


def test_inventory_detail_non_integer_id(api):
    api.check("GET", "/api/inventory/{product_id}", "admin", 422,
              path_params={"product_id": "abc"},
              test_id="INV-DET-005", test_type="schema_validation")


def test_inventory_detail_float_id(api):
    api.check("GET", "/api/inventory/{product_id}", "admin", 422,
              path_params={"product_id": "1.5"},
              test_id="INV-DET-006", test_type="schema_validation")


def test_inventory_detail_nonexistent_product(api):
    resp = api.request("admin", "GET", "/api/inventory/31")
    assert resp.status_code in (404, 400, 422), resp.text


# ---------------------------------------------------------------------------
# POST /api/inventory/stock-in
# ---------------------------------------------------------------------------

def test_inventory_stock_in_admin_happy(api):
    api.check("POST", "/api/inventory/stock-in", "admin", 200,
              body={"product_id": 1, "quantity": 10, "remarks": "Restock delivery"},
              test_id="INV-IN-001", test_type="happy_path")


def test_inventory_stock_in_manager_happy(api):
    api.check("POST", "/api/inventory/stock-in", "manager", 200,
              body={"product_id": 6, "quantity": 5},
              test_id="INV-IN-002", test_type="happy_path")


def test_inventory_stock_in_null_remarks(api):
    api.check("POST", "/api/inventory/stock-in", "admin", 200,
              body={"product_id": 2, "quantity": 3, "remarks": None},
              test_id="INV-IN-003", test_type="happy_path")


def test_inventory_stock_in_anonymous_unauthorized(api):
    api.check("POST", "/api/inventory/stock-in", "anonymous", 401,
              body={"product_id": 1, "quantity": 10},
              test_id="INV-IN-004", test_type="authentication")


def test_inventory_stock_in_quantity_min_valid(api):
    api.check("POST", "/api/inventory/stock-in", "admin", 200,
              body={"product_id": 1, "quantity": 1},
              test_id="INV-IN-005", test_type="boundary_value")


def test_inventory_stock_in_quantity_zero(api):
    api.check("POST", "/api/inventory/stock-in", "admin", 422,
              body={"product_id": 1, "quantity": 0},
              test_id="INV-IN-006", test_type="boundary_value")


def test_inventory_stock_in_quantity_negative(api):
    api.check("POST", "/api/inventory/stock-in", "admin", 422,
              body={"product_id": 1, "quantity": -5},
              test_id="INV-IN-007", test_type="boundary_value")


def test_inventory_stock_in_remarks_max_length(api):
    api.check("POST", "/api/inventory/stock-in", "admin", 200,
              body={"product_id": 1, "quantity": 2, "remarks": "R" * 255},
              test_id="INV-IN-008", test_type="boundary_value")


def test_inventory_stock_in_remarks_too_long(api):
    api.check("POST", "/api/inventory/stock-in", "admin", 422,
              body={"product_id": 1, "quantity": 2, "remarks": "R" * 256},
              test_id="INV-IN-009", test_type="boundary_value")


def test_inventory_stock_in_missing_quantity(api):
    api.check("POST", "/api/inventory/stock-in", "admin", 422,
              body={"product_id": 1},
              test_id="INV-IN-010", test_type="schema_validation")


def test_inventory_stock_in_missing_product_id(api):
    api.check("POST", "/api/inventory/stock-in", "admin", 422,
              body={"quantity": 5},
              test_id="INV-IN-011", test_type="schema_validation")


def test_inventory_stock_in_string_quantity(api):
    api.check("POST", "/api/inventory/stock-in", "admin", 422,
              body={"product_id": 1, "quantity": "ten"},
              test_id="INV-IN-012", test_type="schema_validation")


def test_inventory_stock_in_float_quantity(api):
    api.check("POST", "/api/inventory/stock-in", "admin", 422,
              body={"product_id": 1, "quantity": 2.5},
              test_id="INV-IN-013", test_type="schema_validation")


def test_inventory_stock_in_empty_body(api):
    api.check("POST", "/api/inventory/stock-in", "admin", 422,
              body={},
              test_id="INV-IN-014", test_type="schema_validation")


def test_inventory_stock_in_changes_detail(api):
    before = api.request("admin", "GET", "/api/inventory/1")
    assert before.status_code == 200, before.text
    resp = api.request("admin", "POST", "/api/inventory/stock-in",
                       json={"product_id": 1, "quantity": 7, "remarks": "chain test"})
    assert resp.status_code == 200, resp.text
    after = api.request("admin", "GET", "/api/inventory/1")
    assert after.status_code == 200, after.text
    assert after.json() != before.json()


def test_inventory_stock_in_nonexistent_product(api):
    resp = api.request("admin", "POST", "/api/inventory/stock-in",
                       json={"product_id": 31, "quantity": 5})
    assert resp.status_code in (400, 404, 422), resp.text


# ---------------------------------------------------------------------------
# POST /api/inventory/stock-out
# ---------------------------------------------------------------------------

def test_inventory_stock_out_admin_happy(api):
    api.check("POST", "/api/inventory/stock-out", "admin", 200,
              body={"product_id": 1, "quantity": 10, "remarks": "Customer order"},
              test_id="INV-OUT-001", test_type="happy_path")


def test_inventory_stock_out_manager_happy(api):
    api.check("POST", "/api/inventory/stock-out", "manager", 200,
              body={"product_id": 1, "quantity": 5},
              test_id="INV-OUT-002", test_type="happy_path")


def test_inventory_stock_out_anonymous_unauthorized(api):
    api.check("POST", "/api/inventory/stock-out", "anonymous", 401,
              body={"product_id": 1, "quantity": 5},
              test_id="INV-OUT-003", test_type="authentication")


def test_inventory_stock_out_quantity_min_valid(api):
    api.check("POST", "/api/inventory/stock-out", "admin", 200,
              body={"product_id": 1, "quantity": 1},
              test_id="INV-OUT-004", test_type="boundary_value")


def test_inventory_stock_out_entire_stock(api):
    api.check("POST", "/api/inventory/stock-out", "admin", 200,
              body={"product_id": 1, "quantity": 168},
              test_id="INV-OUT-005", test_type="boundary_value")


def test_inventory_stock_out_quantity_zero(api):
    api.check("POST", "/api/inventory/stock-out", "admin", 422,
              body={"product_id": 1, "quantity": 0},
              test_id="INV-OUT-006", test_type="boundary_value")


def test_inventory_stock_out_quantity_negative(api):
    api.check("POST", "/api/inventory/stock-out", "admin", 422,
              body={"product_id": 1, "quantity": -1},
              test_id="INV-OUT-007", test_type="boundary_value")


def test_inventory_stock_out_remarks_max_length(api):
    api.check("POST", "/api/inventory/stock-out", "admin", 200,
              body={"product_id": 1, "quantity": 1, "remarks": "X" * 255},
              test_id="INV-OUT-008", test_type="boundary_value")


def test_inventory_stock_out_remarks_too_long(api):
    api.check("POST", "/api/inventory/stock-out", "admin", 422,
              body={"product_id": 1, "quantity": 1, "remarks": "X" * 256},
              test_id="INV-OUT-009", test_type="boundary_value")


def test_inventory_stock_out_missing_quantity(api):
    api.check("POST", "/api/inventory/stock-out", "admin", 422,
              body={"product_id": 1},
              test_id="INV-OUT-010", test_type="schema_validation")


def test_inventory_stock_out_missing_product_id(api):
    api.check("POST", "/api/inventory/stock-out", "admin", 422,
              body={"quantity": 1},
              test_id="INV-OUT-011", test_type="schema_validation")


def test_inventory_stock_out_string_product_id(api):
    api.check("POST", "/api/inventory/stock-out", "admin", 422,
              body={"product_id": "abc", "quantity": 1},
              test_id="INV-OUT-012", test_type="schema_validation")


def test_inventory_stock_out_float_quantity(api):
    api.check("POST", "/api/inventory/stock-out", "admin", 422,
              body={"product_id": 1, "quantity": 1.5},
              test_id="INV-OUT-013", test_type="schema_validation")


def test_inventory_stock_out_exceeds_stock_rejected(api):
    before = api.request("admin", "GET", "/api/inventory/1")
    assert before.status_code == 200, before.text
    resp = api.request("admin", "POST", "/api/inventory/stock-out",
                       json={"product_id": 1, "quantity": 169})
    assert resp.status_code in (400, 409, 422), resp.text
    after = api.request("admin", "GET", "/api/inventory/1")
    assert after.status_code == 200, after.text
    assert after.json() == before.json()


def test_inventory_stock_out_changes_detail(api):
    before = api.request("manager", "GET", "/api/inventory/1")
    assert before.status_code == 200, before.text
    resp = api.request("manager", "POST", "/api/inventory/stock-out",
                       json={"product_id": 1, "quantity": 4, "remarks": "chain test"})
    assert resp.status_code == 200, resp.text
    after = api.request("manager", "GET", "/api/inventory/1")
    assert after.status_code == 200, after.text
    assert after.json() != before.json()


def test_inventory_stock_out_nonexistent_product(api):
    resp = api.request("admin", "POST", "/api/inventory/stock-out",
                       json={"product_id": 31, "quantity": 1})
    assert resp.status_code in (400, 404, 422), resp.text
