"""Tests for inventory. Made by APIGuard from tests.json; do not edit."""


def test_inventory_list_happy_admin(api):
    'Admin can list inventory records'
    api.check(
        method='GET',
        path='/api/inventory',
        role='admin',
        expected_status=200,
        path_params={},
        query_params={},
        body=None,
        test_id='inventory-list-happy-admin',
        test_type='happy_path',
    )


def test_inventory_list_happy_manager(api):
    'Manager can list inventory records'
    api.check(
        method='GET',
        path='/api/inventory',
        role='manager',
        expected_status=200,
        path_params={},
        query_params={},
        body=None,
        test_id='inventory-list-happy-manager',
        test_type='happy_path',
    )


def test_inventory_list_auth_anonymous(api):
    'Listing inventory without a token is rejected'
    api.check(
        method='GET',
        path='/api/inventory',
        role='anonymous',
        expected_status=401,
        path_params={},
        query_params={},
        body=None,
        test_id='inventory-list-auth-anonymous',
        test_type='authentication',
    )


def test_inventory_movements_happy_all(api):
    'Admin can list all stock movements without filters'
    api.check(
        method='GET',
        path='/api/inventory/movements',
        role='admin',
        expected_status=200,
        path_params={},
        query_params={},
        body=None,
        test_id='inventory-movements-happy-all',
        test_type='happy_path',
    )


def test_inventory_movements_happy_filtered(api):
    'Manager can filter stock movements by product 1 and type IN'
    api.check(
        method='GET',
        path='/api/inventory/movements',
        role='manager',
        expected_status=200,
        path_params={},
        query_params={'product_id': '1', 'type': 'IN'},
        body=None,
        test_id='inventory-movements-happy-filtered',
        test_type='happy_path',
    )


def test_inventory_movements_happy_date_range(api):
    'Filtering stock movements by a valid date range succeeds'
    api.check(
        method='GET',
        path='/api/inventory/movements',
        role='admin',
        expected_status=200,
        path_params={},
        query_params={'from_date': '2020-01-01', 'to_date': '2030-12-31'},
        body=None,
        test_id='inventory-movements-happy-date-range',
        test_type='happy_path',
    )


def test_inventory_movements_schema_invalid_type(api):
    'Movement type outside the IN/OUT enum is rejected'
    api.check(
        method='GET',
        path='/api/inventory/movements',
        role='admin',
        expected_status=422,
        path_params={},
        query_params={'type': 'TRANSFER'},
        body=None,
        test_id='inventory-movements-schema-invalid-type',
        test_type='schema_validation',
    )


def test_inventory_movements_schema_invalid_date(api):
    'Non-date from_date value is rejected'
    api.check(
        method='GET',
        path='/api/inventory/movements',
        role='admin',
        expected_status=422,
        path_params={},
        query_params={'from_date': 'not-a-date'},
        body=None,
        test_id='inventory-movements-schema-invalid-date',
        test_type='schema_validation',
    )


def test_inventory_movements_schema_invalid_product_id(api):
    'Non-integer product_id filter is rejected'
    api.check(
        method='GET',
        path='/api/inventory/movements',
        role='admin',
        expected_status=422,
        path_params={},
        query_params={'product_id': 'abc'},
        body=None,
        test_id='inventory-movements-schema-invalid-product-id',
        test_type='schema_validation',
    )


def test_inventory_movements_auth_anonymous(api):
    'Listing stock movements without a token is rejected'
    api.check(
        method='GET',
        path='/api/inventory/movements',
        role='anonymous',
        expected_status=401,
        path_params={},
        query_params={},
        body=None,
        test_id='inventory-movements-auth-anonymous',
        test_type='authentication',
    )


def test_inventory_detail_happy(api):
    'Admin can get the inventory detail of product 1'
    api.check(
        method='GET',
        path='/api/inventory/{product_id}',
        role='admin',
        expected_status=200,
        path_params={'product_id': '1'},
        query_params={},
        body=None,
        test_id='inventory-detail-happy',
        test_type='happy_path',
    )


def test_inventory_detail_not_found(api):
    'Inventory detail of a non-existent product returns 404'
    api.check(
        method='GET',
        path='/api/inventory/{product_id}',
        role='admin',
        expected_status=404,
        path_params={'product_id': '999'},
        query_params={},
        body=None,
        test_id='inventory-detail-not-found',
        test_type='happy_path',
    )


def test_inventory_detail_schema_invalid_id(api):
    'Non-integer product_id path parameter is rejected'
    api.check(
        method='GET',
        path='/api/inventory/{product_id}',
        role='admin',
        expected_status=422,
        path_params={'product_id': 'abc'},
        query_params={},
        body=None,
        test_id='inventory-detail-schema-invalid-id',
        test_type='schema_validation',
    )


def test_inventory_detail_auth_anonymous(api):
    'Getting inventory detail without a token is rejected'
    api.check(
        method='GET',
        path='/api/inventory/{product_id}',
        role='anonymous',
        expected_status=401,
        path_params={'product_id': '1'},
        query_params={},
        body=None,
        test_id='inventory-detail-auth-anonymous',
        test_type='authentication',
    )


def test_inventory_stockin_happy(api):
    'Admin can stock in 10 units of product 1 with remarks'
    api.check(
        method='POST',
        path='/api/inventory/stock-in',
        role='admin',
        expected_status=200,
        path_params={},
        query_params={},
        body={'product_id': 1, 'quantity': 10, 'remarks': 'Supplier delivery'},
        test_id='inventory-stockin-happy',
        test_type='happy_path',
    )


def test_inventory_stockin_happy_manager(api):
    'Manager can stock in units of product 2 without remarks'
    api.check(
        method='POST',
        path='/api/inventory/stock-in',
        role='manager',
        expected_status=200,
        path_params={},
        query_params={},
        body={'product_id': 2, 'quantity': 5},
        test_id='inventory-stockin-happy-manager',
        test_type='happy_path',
    )


def test_inventory_stockin_schema_missing_quantity(api):
    'Stock in without required quantity is rejected'
    api.check(
        method='POST',
        path='/api/inventory/stock-in',
        role='admin',
        expected_status=422,
        path_params={},
        query_params={},
        body={'product_id': 1},
        test_id='inventory-stockin-schema-missing-quantity',
        test_type='schema_validation',
    )


def test_inventory_stockin_schema_missing_product(api):
    'Stock in without required product_id is rejected'
    api.check(
        method='POST',
        path='/api/inventory/stock-in',
        role='admin',
        expected_status=422,
        path_params={},
        query_params={},
        body={'quantity': 10},
        test_id='inventory-stockin-schema-missing-product',
        test_type='schema_validation',
    )


def test_inventory_stockin_schema_wrong_type(api):
    'Stock in with a non-integer quantity is rejected'
    api.check(
        method='POST',
        path='/api/inventory/stock-in',
        role='admin',
        expected_status=422,
        path_params={},
        query_params={},
        body={'product_id': 1, 'quantity': 'ten'},
        test_id='inventory-stockin-schema-wrong-type',
        test_type='schema_validation',
    )


def test_inventory_stockin_boundary_quantity_1(api):
    'Stock in with the smallest valid quantity 1 succeeds'
    api.check(
        method='POST',
        path='/api/inventory/stock-in',
        role='admin',
        expected_status=200,
        path_params={},
        query_params={},
        body={'product_id': 1, 'quantity': 1},
        test_id='inventory-stockin-boundary-quantity-1',
        test_type='boundary_value',
    )


def test_inventory_stockin_boundary_quantity_0(api):
    'Stock in with quantity 0 is rejected'
    api.check(
        method='POST',
        path='/api/inventory/stock-in',
        role='admin',
        expected_status=422,
        path_params={},
        query_params={},
        body={'product_id': 1, 'quantity': 0},
        test_id='inventory-stockin-boundary-quantity-0',
        test_type='boundary_value',
    )


def test_inventory_stockin_boundary_remarks_255(api):
    'Stock in with remarks of exactly 255 characters succeeds'
    api.check(
        method='POST',
        path='/api/inventory/stock-in',
        role='admin',
        expected_status=200,
        path_params={},
        query_params={},
        body={'product_id': 1,
         'quantity': 3,
         'remarks': '012345678901234567890123456789012345678901234567890123456789012345678901234567890123456789012345678901234567890123456789012345678901234567890123456789012345678901234567890123456789012345678901234567890123456789012345678901234567890123456789012345678901234'},
        test_id='inventory-stockin-boundary-remarks-255',
        test_type='boundary_value',
    )


def test_inventory_stockin_boundary_remarks_256(api):
    'Stock in with remarks of 256 characters is rejected'
    api.check(
        method='POST',
        path='/api/inventory/stock-in',
        role='admin',
        expected_status=422,
        path_params={},
        query_params={},
        body={'product_id': 1,
         'quantity': 3,
         'remarks': '0123456789012345678901234567890123456789012345678901234567890123456789012345678901234567890123456789012345678901234567890123456789012345678901234567890123456789012345678901234567890123456789012345678901234567890123456789012345678901234567890123456789012345'},
        test_id='inventory-stockin-boundary-remarks-256',
        test_type='boundary_value',
    )


def test_inventory_stockin_auth_anonymous(api):
    'Stock in without a token is rejected'
    api.check(
        method='POST',
        path='/api/inventory/stock-in',
        role='anonymous',
        expected_status=401,
        path_params={},
        query_params={},
        body={'product_id': 1, 'quantity': 10},
        test_id='inventory-stockin-auth-anonymous',
        test_type='authentication',
    )


def test_inventory_stockout_happy(api):
    'Admin can stock out 5 units of product 1 which has 168 in stock'
    api.check(
        method='POST',
        path='/api/inventory/stock-out',
        role='admin',
        expected_status=200,
        path_params={},
        query_params={},
        body={'product_id': 1, 'quantity': 5, 'remarks': 'Customer order'},
        test_id='inventory-stockout-happy',
        test_type='happy_path',
    )


def test_inventory_stockout_happy_manager(api):
    'Manager can stock out 1 unit of product 1'
    api.check(
        method='POST',
        path='/api/inventory/stock-out',
        role='manager',
        expected_status=200,
        path_params={},
        query_params={},
        body={'product_id': 1, 'quantity': 1},
        test_id='inventory-stockout-happy-manager',
        test_type='happy_path',
    )


def test_inventory_stockout_schema_missing_quantity(api):
    'Stock out without required quantity is rejected'
    api.check(
        method='POST',
        path='/api/inventory/stock-out',
        role='admin',
        expected_status=422,
        path_params={},
        query_params={},
        body={'product_id': 1},
        test_id='inventory-stockout-schema-missing-quantity',
        test_type='schema_validation',
    )


def test_inventory_stockout_schema_missing_product(api):
    'Stock out without required product_id is rejected'
    api.check(
        method='POST',
        path='/api/inventory/stock-out',
        role='admin',
        expected_status=422,
        path_params={},
        query_params={},
        body={'quantity': 1},
        test_id='inventory-stockout-schema-missing-product',
        test_type='schema_validation',
    )


def test_inventory_stockout_schema_wrong_type(api):
    'Stock out with a non-integer product_id is rejected'
    api.check(
        method='POST',
        path='/api/inventory/stock-out',
        role='admin',
        expected_status=422,
        path_params={},
        query_params={},
        body={'product_id': 'one', 'quantity': 1},
        test_id='inventory-stockout-schema-wrong-type',
        test_type='schema_validation',
    )


def test_inventory_stockout_boundary_quantity_1(api):
    'Stock out with the smallest valid quantity 1 succeeds'
    api.check(
        method='POST',
        path='/api/inventory/stock-out',
        role='admin',
        expected_status=200,
        path_params={},
        query_params={},
        body={'product_id': 1, 'quantity': 1},
        test_id='inventory-stockout-boundary-quantity-1',
        test_type='boundary_value',
    )


def test_inventory_stockout_boundary_quantity_0(api):
    'Stock out with quantity 0 is rejected'
    api.check(
        method='POST',
        path='/api/inventory/stock-out',
        role='admin',
        expected_status=422,
        path_params={},
        query_params={},
        body={'product_id': 1, 'quantity': 0},
        test_id='inventory-stockout-boundary-quantity-0',
        test_type='boundary_value',
    )


def test_inventory_stockout_boundary_quantity_negative(api):
    'Stock out with negative quantity -1 is rejected'
    api.check(
        method='POST',
        path='/api/inventory/stock-out',
        role='admin',
        expected_status=422,
        path_params={},
        query_params={},
        body={'product_id': 1, 'quantity': -1},
        test_id='inventory-stockout-boundary-quantity-negative',
        test_type='boundary_value',
    )


def test_inventory_stockout_boundary_remarks_255(api):
    'Stock out with remarks of exactly 255 characters succeeds'
    api.check(
        method='POST',
        path='/api/inventory/stock-out',
        role='admin',
        expected_status=200,
        path_params={},
        query_params={},
        body={'product_id': 1,
         'quantity': 2,
         'remarks': '012345678901234567890123456789012345678901234567890123456789012345678901234567890123456789012345678901234567890123456789012345678901234567890123456789012345678901234567890123456789012345678901234567890123456789012345678901234567890123456789012345678901234'},
        test_id='inventory-stockout-boundary-remarks-255',
        test_type='boundary_value',
    )


def test_inventory_stockout_boundary_remarks_256(api):
    'Stock out with remarks of 256 characters is rejected'
    api.check(
        method='POST',
        path='/api/inventory/stock-out',
        role='admin',
        expected_status=422,
        path_params={},
        query_params={},
        body={'product_id': 1,
         'quantity': 2,
         'remarks': '0123456789012345678901234567890123456789012345678901234567890123456789012345678901234567890123456789012345678901234567890123456789012345678901234567890123456789012345678901234567890123456789012345678901234567890123456789012345678901234567890123456789012345'},
        test_id='inventory-stockout-boundary-remarks-256',
        test_type='boundary_value',
    )


def test_inventory_stockout_auth_anonymous(api):
    'Stock out without a token is rejected'
    api.check(
        method='POST',
        path='/api/inventory/stock-out',
        role='anonymous',
        expected_status=401,
        path_params={},
        query_params={},
        body={'product_id': 1, 'quantity': 1},
        test_id='inventory-stockout-auth-anonymous',
        test_type='authentication',
    )
