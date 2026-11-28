from shop_spec import SHOP

from apiguard.coverage import applicable_types, coverage, format_coverage, missing_cells
from apiguard.operations import extract_operations

OPERATIONS = {f"{op.method} {op.path}": op for op in extract_operations(SHOP)}
PERMISSIONS = {"DELETE /api/products/{product_id}": ["admin"]}
ROLES = ["admin", "manager"]


def test_applicable_types():
    def types(key):
        return applicable_types(OPERATIONS[key], PERMISSIONS, ROLES)

    assert types("GET /api/products") == {"happy_path", "authentication"}
    assert types("POST /api/products") == {
        "happy_path",
        "authentication",
        "schema_validation",
        "fuzz",
        "boundary_value",
        "stateful_workflow",
    }
    assert "authorization" in types("DELETE /api/products/{product_id}")
    # Login does not need a token, so it has no authentication or workflow tests.
    assert types("POST /api/auth/login") == {"happy_path", "schema_validation", "fuzz"}


def test_coverage_table_and_missing_cells():
    operations = [OPERATIONS["GET /api/products"]]
    tests = [{"method": "GET", "path": "/api/products", "type": "happy_path"}]
    table = coverage(tests, operations, PERMISSIONS, ROLES)
    assert table["GET /api/products"]["happy_path"] == 1
    assert table["GET /api/products"]["fuzz"] is None
    assert missing_cells(table) == [("GET /api/products", "authentication")]
    text = format_coverage(table)
    assert "MISSING" in text
    assert "1 applicable cells have no test." in text
