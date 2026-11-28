"""Tests for products. Made by APIGuard from tests.json; do not edit."""


def test_products_list_happy_admin(api):
    'Admin lists all products'
    api.check(
        method='GET',
        path='/api/products',
        role='admin',
        expected_status=200,
        path_params={},
        query_params={},
        body=None,
        test_id='products-list-happy-admin',
        test_type='happy_path',
    )


def test_products_list_happy_filter_manager(api):
    'Manager lists products filtered by existing category 1'
    api.check(
        method='GET',
        path='/api/products',
        role='manager',
        expected_status=200,
        path_params={},
        query_params={'category_id': '1'},
        body=None,
        test_id='products-list-happy-filter-manager',
        test_type='happy_path',
    )


def test_products_list_invalid_category_type(api):
    'Non-integer category_id query parameter is rejected'
    api.check(
        method='GET',
        path='/api/products',
        role='admin',
        expected_status=422,
        path_params={},
        query_params={'category_id': 'abc'},
        body=None,
        test_id='products-list-invalid-category-type',
        test_type='schema_validation',
    )


def test_products_list_no_token(api):
    'Listing products without a token is rejected'
    api.check(
        method='GET',
        path='/api/products',
        role='anonymous',
        expected_status=401,
        path_params={},
        query_params={},
        body=None,
        test_id='products-list-no-token',
        test_type='authentication',
    )


def test_products_get_happy(api):
    'Manager retrieves product 1'
    api.check(
        method='GET',
        path='/api/products/{product_id}',
        role='manager',
        expected_status=200,
        path_params={'product_id': '1'},
        query_params={},
        body=None,
        test_id='products-get-happy',
        test_type='happy_path',
    )


def test_products_get_not_found(api):
    'Retrieving non-existent product 999 returns 404'
    api.check(
        method='GET',
        path='/api/products/{product_id}',
        role='admin',
        expected_status=404,
        path_params={'product_id': '999'},
        query_params={},
        body=None,
        test_id='products-get-not-found',
        test_type='happy_path',
    )


def test_products_get_invalid_id(api):
    'Non-integer product_id is rejected'
    api.check(
        method='GET',
        path='/api/products/{product_id}',
        role='admin',
        expected_status=422,
        path_params={'product_id': 'abc'},
        query_params={},
        body=None,
        test_id='products-get-invalid-id',
        test_type='schema_validation',
    )


def test_products_get_no_token(api):
    'Retrieving a product without a token is rejected'
    api.check(
        method='GET',
        path='/api/products/{product_id}',
        role='anonymous',
        expected_status=401,
        path_params={'product_id': '1'},
        query_params={},
        body=None,
        test_id='products-get-no-token',
        test_type='authentication',
    )


def test_products_create_happy_admin(api):
    'Admin creates a valid product in category 1'
    api.check(
        method='POST',
        path='/api/products',
        role='admin',
        expected_status=201,
        path_params={},
        query_params={},
        body={'sku': 'NEWT-001',
         'name': 'New Test Product',
         'description': 'Created by test',
         'category_id': 1,
         'unit_price': 19.99,
         'minimum_quantity': 5,
         'maximum_quantity': 100},
        test_id='products-create-happy-admin',
        test_type='happy_path',
    )


def test_products_create_missing_sku(api):
    'Creating a product without required sku is rejected'
    api.check(
        method='POST',
        path='/api/products',
        role='admin',
        expected_status=422,
        path_params={},
        query_params={},
        body={'name': 'No Sku Product', 'category_id': 1, 'unit_price': 10.5},
        test_id='products-create-missing-sku',
        test_type='schema_validation',
    )


def test_products_create_missing_name(api):
    'Creating a product without required name is rejected'
    api.check(
        method='POST',
        path='/api/products',
        role='admin',
        expected_status=422,
        path_params={},
        query_params={},
        body={'sku': 'NEWT-002', 'category_id': 1, 'unit_price': 10.5},
        test_id='products-create-missing-name',
        test_type='schema_validation',
    )


def test_products_create_category_wrong_type(api):
    'Non-integer category_id in body is rejected'
    api.check(
        method='POST',
        path='/api/products',
        role='admin',
        expected_status=422,
        path_params={},
        query_params={},
        body={'sku': 'NEWT-003', 'name': 'Bad Category', 'category_id': 'abc', 'unit_price': 10.5},
        test_id='products-create-category-wrong-type',
        test_type='schema_validation',
    )


def test_products_create_empty_body(api):
    'Empty JSON object missing all required fields is rejected'
    api.check(
        method='POST',
        path='/api/products',
        role='admin',
        expected_status=422,
        path_params={},
        query_params={},
        body={},
        test_id='products-create-empty-body',
        test_type='schema_validation',
    )


def test_products_create_sku_too_short(api):
    'SKU of 2 characters (below minLength 3) is rejected'
    api.check(
        method='POST',
        path='/api/products',
        role='admin',
        expected_status=422,
        path_params={},
        query_params={},
        body={'sku': 'AB', 'name': 'Short Sku', 'category_id': 1, 'unit_price': 10.5},
        test_id='products-create-sku-too-short',
        test_type='boundary_value',
    )


def test_products_create_sku_min_length(api):
    'SKU of exactly 3 characters is accepted'
    api.check(
        method='POST',
        path='/api/products',
        role='admin',
        expected_status=201,
        path_params={},
        query_params={},
        body={'sku': 'XYZ', 'name': 'Min Sku', 'category_id': 1, 'unit_price': 10.5},
        test_id='products-create-sku-min-length',
        test_type='boundary_value',
    )


def test_products_create_sku_max_length(api):
    'SKU of exactly 50 characters is accepted'
    api.check(
        method='POST',
        path='/api/products',
        role='admin',
        expected_status=201,
        path_params={},
        query_params={},
        body={'sku': 'AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA',
         'name': 'Max Sku',
         'category_id': 1,
         'unit_price': 10.5},
        test_id='products-create-sku-max-length',
        test_type='boundary_value',
    )


def test_products_create_sku_too_long(api):
    'SKU of 51 characters is rejected'
    api.check(
        method='POST',
        path='/api/products',
        role='admin',
        expected_status=422,
        path_params={},
        query_params={},
        body={'sku': 'AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA',
         'name': 'Long Sku',
         'category_id': 1,
         'unit_price': 10.5},
        test_id='products-create-sku-too-long',
        test_type='boundary_value',
    )


def test_products_create_name_empty(api):
    'Empty name (below minLength 1) is rejected'
    api.check(
        method='POST',
        path='/api/products',
        role='admin',
        expected_status=422,
        path_params={},
        query_params={},
        body={'sku': 'NEWT-004', 'name': '', 'category_id': 1, 'unit_price': 10.5},
        test_id='products-create-name-empty',
        test_type='boundary_value',
    )


def test_products_create_name_max_length(api):
    'Name of exactly 100 characters is accepted'
    api.check(
        method='POST',
        path='/api/products',
        role='admin',
        expected_status=201,
        path_params={},
        query_params={},
        body={'sku': 'NEWT-005',
         'name': 'NNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNN',
         'category_id': 1,
         'unit_price': 10.5},
        test_id='products-create-name-max-length',
        test_type='boundary_value',
    )


def test_products_create_name_too_long(api):
    'Name of 101 characters is rejected'
    api.check(
        method='POST',
        path='/api/products',
        role='admin',
        expected_status=422,
        path_params={},
        query_params={},
        body={'sku': 'NEWT-006',
         'name': 'NNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNN',
         'category_id': 1,
         'unit_price': 10.5},
        test_id='products-create-name-too-long',
        test_type='boundary_value',
    )


def test_products_create_description_too_long(api):
    'Description of 256 characters is rejected'
    api.check(
        method='POST',
        path='/api/products',
        role='admin',
        expected_status=422,
        path_params={},
        query_params={},
        body={'sku': 'NEWT-007',
         'name': 'Long Desc',
         'description': 'DDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDD',
         'category_id': 1,
         'unit_price': 10.5},
        test_id='products-create-description-too-long',
        test_type='boundary_value',
    )


def test_products_create_price_zero(api):
    'Unit price of 0 (not greater than zero) is rejected'
    api.check(
        method='POST',
        path='/api/products',
        role='admin',
        expected_status=422,
        path_params={},
        query_params={},
        body={'sku': 'NEWT-008', 'name': 'Zero Price', 'category_id': 1, 'unit_price': 0},
        test_id='products-create-price-zero',
        test_type='boundary_value',
    )


def test_products_create_price_just_above_zero(api):
    'Unit price of 0.01 is accepted'
    api.check(
        method='POST',
        path='/api/products',
        role='admin',
        expected_status=201,
        path_params={},
        query_params={},
        body={'sku': 'NEWT-009', 'name': 'Cheap Product', 'category_id': 1, 'unit_price': 0.01},
        test_id='products-create-price-just-above-zero',
        test_type='boundary_value',
    )


def test_products_create_min_qty_negative(api):
    'Negative minimum_quantity is rejected'
    api.check(
        method='POST',
        path='/api/products',
        role='admin',
        expected_status=422,
        path_params={},
        query_params={},
        body={'sku': 'NEWT-010',
         'name': 'Neg Min',
         'category_id': 1,
         'unit_price': 10.5,
         'minimum_quantity': -1},
        test_id='products-create-min-qty-negative',
        test_type='boundary_value',
    )


def test_products_create_no_token(api):
    'Creating a product without a token is rejected'
    api.check(
        method='POST',
        path='/api/products',
        role='anonymous',
        expected_status=401,
        path_params={},
        query_params={},
        body={'sku': 'NEWT-011', 'name': 'Anon Product', 'category_id': 1, 'unit_price': 10.5},
        test_id='products-create-no-token',
        test_type='authentication',
    )


def test_products_update_happy(api):
    'Admin updates name and price of product 1'
    api.check(
        method='PUT',
        path='/api/products/{product_id}',
        role='admin',
        expected_status=200,
        path_params={'product_id': '1'},
        query_params={},
        body={'name': 'Electronics Item 1 Updated', 'unit_price': 25.5},
        test_id='products-update-happy',
        test_type='happy_path',
    )


def test_products_update_not_found(api):
    'Updating non-existent product 999 returns 404'
    api.check(
        method='PUT',
        path='/api/products/{product_id}',
        role='admin',
        expected_status=404,
        path_params={'product_id': '999'},
        query_params={},
        body={'name': 'Ghost'},
        test_id='products-update-not-found',
        test_type='happy_path',
    )


def test_products_update_invalid_id(api):
    'Non-integer product_id on update is rejected'
    api.check(
        method='PUT',
        path='/api/products/{product_id}',
        role='admin',
        expected_status=422,
        path_params={'product_id': 'abc'},
        query_params={},
        body={'name': 'Bad Id'},
        test_id='products-update-invalid-id',
        test_type='schema_validation',
    )


def test_products_update_category_wrong_type(api):
    'Non-integer category_id on update is rejected'
    api.check(
        method='PUT',
        path='/api/products/{product_id}',
        role='admin',
        expected_status=422,
        path_params={'product_id': '1'},
        query_params={},
        body={'category_id': 'abc'},
        test_id='products-update-category-wrong-type',
        test_type='schema_validation',
    )


def test_products_update_sku_too_short(api):
    'Updating SKU to 2 characters is rejected'
    api.check(
        method='PUT',
        path='/api/products/{product_id}',
        role='admin',
        expected_status=422,
        path_params={'product_id': '1'},
        query_params={},
        body={'sku': 'AB'},
        test_id='products-update-sku-too-short',
        test_type='boundary_value',
    )


def test_products_update_sku_min_length(api):
    'Updating SKU to exactly 3 characters is accepted'
    api.check(
        method='PUT',
        path='/api/products/{product_id}',
        role='admin',
        expected_status=200,
        path_params={'product_id': '1'},
        query_params={},
        body={'sku': 'XYZ'},
        test_id='products-update-sku-min-length',
        test_type='boundary_value',
    )


def test_products_update_name_empty(api):
    'Updating name to empty string is rejected'
    api.check(
        method='PUT',
        path='/api/products/{product_id}',
        role='admin',
        expected_status=422,
        path_params={'product_id': '1'},
        query_params={},
        body={'name': ''},
        test_id='products-update-name-empty',
        test_type='boundary_value',
    )


def test_products_update_price_zero(api):
    'Updating unit price to 0 is rejected'
    api.check(
        method='PUT',
        path='/api/products/{product_id}',
        role='admin',
        expected_status=422,
        path_params={'product_id': '1'},
        query_params={},
        body={'unit_price': 0},
        test_id='products-update-price-zero',
        test_type='boundary_value',
    )


def test_products_update_max_qty_negative(api):
    'Updating maximum_quantity to -1 is rejected'
    api.check(
        method='PUT',
        path='/api/products/{product_id}',
        role='admin',
        expected_status=422,
        path_params={'product_id': '1'},
        query_params={},
        body={'maximum_quantity': -1},
        test_id='products-update-max-qty-negative',
        test_type='boundary_value',
    )


def test_products_update_no_token(api):
    'Updating a product without a token is rejected'
    api.check(
        method='PUT',
        path='/api/products/{product_id}',
        role='anonymous',
        expected_status=401,
        path_params={'product_id': '1'},
        query_params={},
        body={'name': 'Anon Update'},
        test_id='products-update-no-token',
        test_type='authentication',
    )


def test_products_delete_happy(api):
    'Admin deletes product 1'
    api.check(
        method='DELETE',
        path='/api/products/{product_id}',
        role='admin',
        expected_status=200,
        path_params={'product_id': '1'},
        query_params={},
        body=None,
        test_id='products-delete-happy',
        test_type='happy_path',
    )


def test_products_delete_not_found(api):
    'Deleting non-existent product 999 returns 404'
    api.check(
        method='DELETE',
        path='/api/products/{product_id}',
        role='admin',
        expected_status=404,
        path_params={'product_id': '999'},
        query_params={},
        body=None,
        test_id='products-delete-not-found',
        test_type='happy_path',
    )


def test_products_delete_invalid_id(api):
    'Non-integer product_id on delete is rejected'
    api.check(
        method='DELETE',
        path='/api/products/{product_id}',
        role='admin',
        expected_status=422,
        path_params={'product_id': 'abc'},
        query_params={},
        body=None,
        test_id='products-delete-invalid-id',
        test_type='schema_validation',
    )


def test_products_delete_no_token(api):
    'Deleting a product without a token is rejected'
    api.check(
        method='DELETE',
        path='/api/products/{product_id}',
        role='anonymous',
        expected_status=401,
        path_params={'product_id': '1'},
        query_params={},
        body=None,
        test_id='products-delete-no-token',
        test_type='authentication',
    )
