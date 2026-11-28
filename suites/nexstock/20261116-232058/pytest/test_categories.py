"""Tests for categories. Made by APIGuard from tests.json; do not edit."""


def test_categories_list_admin_happy(api):
    'Admin can list all categories'
    api.check(
        method='GET',
        path='/api/categories',
        role='admin',
        expected_status=200,
        path_params={},
        query_params={},
        body=None,
        test_id='categories-list-admin-happy',
        test_type='happy_path',
    )


def test_categories_list_manager_happy(api):
    'Manager can list all categories'
    api.check(
        method='GET',
        path='/api/categories',
        role='manager',
        expected_status=200,
        path_params={},
        query_params={},
        body=None,
        test_id='categories-list-manager-happy',
        test_type='happy_path',
    )


def test_categories_list_no_token(api):
    'Listing categories without a token is rejected'
    api.check(
        method='GET',
        path='/api/categories',
        role='anonymous',
        expected_status=401,
        path_params={},
        query_params={},
        body=None,
        test_id='categories-list-no-token',
        test_type='authentication',
    )


def test_categories_get_happy(api):
    'Admin retrieves category 1 Electronics'
    api.check(
        method='GET',
        path='/api/categories/{category_id}',
        role='admin',
        expected_status=200,
        path_params={'category_id': '1'},
        query_params={},
        body=None,
        test_id='categories-get-happy',
        test_type='happy_path',
    )


def test_categories_get_not_found(api):
    'Retrieving a nonexistent category returns 404'
    api.check(
        method='GET',
        path='/api/categories/{category_id}',
        role='admin',
        expected_status=404,
        path_params={'category_id': '999'},
        query_params={},
        body=None,
        test_id='categories-get-not-found',
        test_type='happy_path',
    )


def test_categories_get_invalid_id(api):
    'Non-integer category id is rejected'
    api.check(
        method='GET',
        path='/api/categories/{category_id}',
        role='admin',
        expected_status=422,
        path_params={'category_id': 'abc'},
        query_params={},
        body=None,
        test_id='categories-get-invalid-id',
        test_type='schema_validation',
    )


def test_categories_get_no_token(api):
    'Retrieving a category without a token is rejected'
    api.check(
        method='GET',
        path='/api/categories/{category_id}',
        role='anonymous',
        expected_status=401,
        path_params={'category_id': '1'},
        query_params={},
        body=None,
        test_id='categories-get-no-token',
        test_type='authentication',
    )


def test_categories_create_happy(api):
    'Admin creates a new category with name and description'
    api.check(
        method='POST',
        path='/api/categories',
        role='admin',
        expected_status=201,
        path_params={},
        query_params={},
        body={'name': 'Test Category APIGuard', 'description': 'Category created by test'},
        test_id='categories-create-happy',
        test_type='happy_path',
    )


def test_categories_create_no_token(api):
    'Creating a category without a token is rejected'
    api.check(
        method='POST',
        path='/api/categories',
        role='anonymous',
        expected_status=401,
        path_params={},
        query_params={},
        body={'name': 'Anonymous Category'},
        test_id='categories-create-no-token',
        test_type='authentication',
    )


def test_categories_create_missing_name(api):
    'Creating a category without the required name fails'
    api.check(
        method='POST',
        path='/api/categories',
        role='admin',
        expected_status=422,
        path_params={},
        query_params={},
        body={'description': 'No name given'},
        test_id='categories-create-missing-name',
        test_type='schema_validation',
    )


def test_categories_create_name_wrong_type(api):
    'Creating a category with a non-string name fails'
    api.check(
        method='POST',
        path='/api/categories',
        role='admin',
        expected_status=422,
        path_params={},
        query_params={},
        body={'name': {'value': 123}},
        test_id='categories-create-name-wrong-type',
        test_type='schema_validation',
    )


def test_categories_create_description_wrong_type(api):
    'Creating a category with a non-string description fails'
    api.check(
        method='POST',
        path='/api/categories',
        role='admin',
        expected_status=422,
        path_params={},
        query_params={},
        body={'name': 'Bad Description Category', 'description': [1, 2]},
        test_id='categories-create-description-wrong-type',
        test_type='schema_validation',
    )


def test_categories_create_description_null(api):
    'Creating a category with a null description succeeds'
    api.check(
        method='POST',
        path='/api/categories',
        role='admin',
        expected_status=201,
        path_params={},
        query_params={},
        body={'name': 'Null Description Category', 'description': None},
        test_id='categories-create-description-null',
        test_type='happy_path',
    )


def test_categories_create_name_empty(api):
    'Empty name is below minimum length 1'
    api.check(
        method='POST',
        path='/api/categories',
        role='admin',
        expected_status=422,
        path_params={},
        query_params={},
        body={'name': ''},
        test_id='categories-create-name-empty',
        test_type='boundary_value',
    )


def test_categories_create_name_min(api):
    'Name of exactly 1 character is accepted'
    api.check(
        method='POST',
        path='/api/categories',
        role='admin',
        expected_status=201,
        path_params={},
        query_params={},
        body={'name': 'Q'},
        test_id='categories-create-name-min',
        test_type='boundary_value',
    )


def test_categories_create_name_max(api):
    'Name of exactly 100 characters is accepted'
    api.check(
        method='POST',
        path='/api/categories',
        role='admin',
        expected_status=201,
        path_params={},
        query_params={},
        body={'name': 'ABCDEFGHIJABCDEFGHIJABCDEFGHIJABCDEFGHIJABCDEFGHIJABCDEFGHIJABCDEFGHIJABCDEFGHIJABCDEFGHIJABCDEFGHIJ'},
        test_id='categories-create-name-max',
        test_type='boundary_value',
    )


def test_categories_create_name_too_long(api):
    'Name of 101 characters exceeds maximum length'
    api.check(
        method='POST',
        path='/api/categories',
        role='admin',
        expected_status=422,
        path_params={},
        query_params={},
        body={'name': 'ABCDEFGHIJABCDEFGHIJABCDEFGHIJABCDEFGHIJABCDEFGHIJABCDEFGHIJABCDEFGHIJABCDEFGHIJABCDEFGHIJABCDEFGHIJK'},
        test_id='categories-create-name-too-long',
        test_type='boundary_value',
    )


def test_categories_create_description_max(api):
    'Description of exactly 255 characters is accepted'
    api.check(
        method='POST',
        path='/api/categories',
        role='admin',
        expected_status=201,
        path_params={},
        query_params={},
        body={'name': 'Long Description Category',
         'description': 'abcdefghijabcdefghijabcdefghijabcdefghijabcdefghijabcdefghijabcdefghijabcdefghijabcdefghijabcdefghijabcdefghijabcdefghijabcdefghijabcdefghijabcdefghijabcdefghijabcdefghijabcdefghijabcdefghijabcdefghijabcdefghijabcdefghijabcdefghijabcdefghijabcdefghijabcde'},
        test_id='categories-create-description-max',
        test_type='boundary_value',
    )


def test_categories_create_description_too_long(api):
    'Description of 256 characters exceeds maximum length'
    api.check(
        method='POST',
        path='/api/categories',
        role='admin',
        expected_status=422,
        path_params={},
        query_params={},
        body={'name': 'Too Long Description Category',
         'description': 'abcdefghijabcdefghijabcdefghijabcdefghijabcdefghijabcdefghijabcdefghijabcdefghijabcdefghijabcdefghijabcdefghijabcdefghijabcdefghijabcdefghijabcdefghijabcdefghijabcdefghijabcdefghijabcdefghijabcdefghijabcdefghijabcdefghijabcdefghijabcdefghijabcdefghijabcdef'},
        test_id='categories-create-description-too-long',
        test_type='boundary_value',
    )


def test_categories_update_happy(api):
    'Admin updates name and description of category 1'
    api.check(
        method='PUT',
        path='/api/categories/{category_id}',
        role='admin',
        expected_status=200,
        path_params={'category_id': '1'},
        query_params={},
        body={'name': 'Electronics Updated', 'description': 'Updated by test'},
        test_id='categories-update-happy',
        test_type='happy_path',
    )


def test_categories_update_no_token(api):
    'Updating a category without a token is rejected'
    api.check(
        method='PUT',
        path='/api/categories/{category_id}',
        role='anonymous',
        expected_status=401,
        path_params={'category_id': '1'},
        query_params={},
        body={'description': 'Anonymous update'},
        test_id='categories-update-no-token',
        test_type='authentication',
    )


def test_categories_update_not_found(api):
    'Updating a nonexistent category returns 404'
    api.check(
        method='PUT',
        path='/api/categories/{category_id}',
        role='admin',
        expected_status=404,
        path_params={'category_id': '999'},
        query_params={},
        body={'description': 'Does not exist'},
        test_id='categories-update-not-found',
        test_type='happy_path',
    )


def test_categories_update_invalid_id(api):
    'Updating with a non-integer category id is rejected'
    api.check(
        method='PUT',
        path='/api/categories/{category_id}',
        role='admin',
        expected_status=422,
        path_params={'category_id': 'abc'},
        query_params={},
        body={'description': 'Invalid id'},
        test_id='categories-update-invalid-id',
        test_type='schema_validation',
    )


def test_categories_update_name_wrong_type(api):
    'Updating with a non-string name is rejected'
    api.check(
        method='PUT',
        path='/api/categories/{category_id}',
        role='admin',
        expected_status=422,
        path_params={'category_id': '2'},
        query_params={},
        body={'name': ['Raw']},
        test_id='categories-update-name-wrong-type',
        test_type='schema_validation',
    )


def test_categories_update_name_empty(api):
    'Updating with an empty name is below minimum length'
    api.check(
        method='PUT',
        path='/api/categories/{category_id}',
        role='admin',
        expected_status=422,
        path_params={'category_id': '2'},
        query_params={},
        body={'name': ''},
        test_id='categories-update-name-empty',
        test_type='boundary_value',
    )


def test_categories_update_name_max(api):
    'Updating with a 100-character name is accepted'
    api.check(
        method='PUT',
        path='/api/categories/{category_id}',
        role='admin',
        expected_status=200,
        path_params={'category_id': '2'},
        query_params={},
        body={'name': 'ABCDEFGHIJABCDEFGHIJABCDEFGHIJABCDEFGHIJABCDEFGHIJABCDEFGHIJABCDEFGHIJABCDEFGHIJABCDEFGHIJABCDEFGHIJ'},
        test_id='categories-update-name-max',
        test_type='boundary_value',
    )


def test_categories_update_name_too_long(api):
    'Updating with a 101-character name is rejected'
    api.check(
        method='PUT',
        path='/api/categories/{category_id}',
        role='admin',
        expected_status=422,
        path_params={'category_id': '2'},
        query_params={},
        body={'name': 'ABCDEFGHIJABCDEFGHIJABCDEFGHIJABCDEFGHIJABCDEFGHIJABCDEFGHIJABCDEFGHIJABCDEFGHIJABCDEFGHIJABCDEFGHIJK'},
        test_id='categories-update-name-too-long',
        test_type='boundary_value',
    )


def test_categories_update_description_too_long(api):
    'Updating with a 256-character description is rejected'
    api.check(
        method='PUT',
        path='/api/categories/{category_id}',
        role='admin',
        expected_status=422,
        path_params={'category_id': '3'},
        query_params={},
        body={'description': 'abcdefghijabcdefghijabcdefghijabcdefghijabcdefghijabcdefghijabcdefghijabcdefghijabcdefghijabcdefghijabcdefghijabcdefghijabcdefghijabcdefghijabcdefghijabcdefghijabcdefghijabcdefghijabcdefghijabcdefghijabcdefghijabcdefghijabcdefghijabcdefghijabcdefghijabcdef'},
        test_id='categories-update-description-too-long',
        test_type='boundary_value',
    )


def test_categories_delete_happy(api):
    'Admin deletes category 10 Consumables'
    api.check(
        method='DELETE',
        path='/api/categories/{category_id}',
        role='admin',
        expected_status=200,
        path_params={'category_id': '10'},
        query_params={},
        body=None,
        test_id='categories-delete-happy',
        test_type='happy_path',
    )


def test_categories_delete_no_token(api):
    'Deleting a category without a token is rejected'
    api.check(
        method='DELETE',
        path='/api/categories/{category_id}',
        role='anonymous',
        expected_status=401,
        path_params={'category_id': '10'},
        query_params={},
        body=None,
        test_id='categories-delete-no-token',
        test_type='authentication',
    )


def test_categories_delete_not_found(api):
    'Deleting a nonexistent category returns 404'
    api.check(
        method='DELETE',
        path='/api/categories/{category_id}',
        role='admin',
        expected_status=404,
        path_params={'category_id': '999'},
        query_params={},
        body=None,
        test_id='categories-delete-not-found',
        test_type='happy_path',
    )


def test_categories_delete_invalid_id(api):
    'Deleting with a non-integer category id is rejected'
    api.check(
        method='DELETE',
        path='/api/categories/{category_id}',
        role='admin',
        expected_status=422,
        path_params={'category_id': 'abc'},
        query_params={},
        body=None,
        test_id='categories-delete-invalid-id',
        test_type='schema_validation',
    )
