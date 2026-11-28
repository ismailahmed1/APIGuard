"""Tests for authentication. Made by APIGuard from tests.json; do not edit."""


def test_authentication_me_happy_admin(api):
    'Admin retrieves own profile and gets 200'
    api.check(
        method='GET',
        path='/api/auth/me',
        role='admin',
        expected_status=200,
        path_params={},
        query_params={},
        body=None,
        test_id='authentication-me-happy-admin',
        test_type='happy_path',
    )


def test_authentication_me_happy_manager(api):
    'Manager retrieves own profile and gets 200'
    api.check(
        method='GET',
        path='/api/auth/me',
        role='manager',
        expected_status=200,
        path_params={},
        query_params={},
        body=None,
        test_id='authentication-me-happy-manager',
        test_type='happy_path',
    )


def test_authentication_me_no_token(api):
    'Requesting the current user profile without a token is rejected with 401'
    api.check(
        method='GET',
        path='/api/auth/me',
        role='anonymous',
        expected_status=401,
        path_params={},
        query_params={},
        body=None,
        test_id='authentication-me-no-token',
        test_type='authentication',
    )


def test_authentication_login_happy_admin(api):
    'Admin logs in with valid credentials and gets 200'
    api.check(
        method='POST',
        path='/api/auth/login',
        role='anonymous',
        expected_status=200,
        path_params={},
        query_params={},
        body={'email': '{{admin.email}}', 'password': '{{admin.password}}'},
        test_id='authentication-login-happy-admin',
        test_type='happy_path',
    )


def test_authentication_login_happy_manager(api):
    'Manager logs in with valid credentials and gets 200'
    api.check(
        method='POST',
        path='/api/auth/login',
        role='anonymous',
        expected_status=200,
        path_params={},
        query_params={},
        body={'email': '{{manager.email}}', 'password': '{{manager.password}}'},
        test_id='authentication-login-happy-manager',
        test_type='happy_path',
    )


def test_authentication_login_missing_email(api):
    'Login without the required email field is rejected with 422'
    api.check(
        method='POST',
        path='/api/auth/login',
        role='anonymous',
        expected_status=422,
        path_params={},
        query_params={},
        body={'password': '{{admin.password}}'},
        test_id='authentication-login-missing-email',
        test_type='schema_validation',
    )


def test_authentication_login_missing_password(api):
    'Login without the required password field is rejected with 422'
    api.check(
        method='POST',
        path='/api/auth/login',
        role='anonymous',
        expected_status=422,
        path_params={},
        query_params={},
        body={'email': '{{admin.email}}'},
        test_id='authentication-login-missing-password',
        test_type='schema_validation',
    )


def test_authentication_login_invalid_email_format(api):
    'Login with an email that is not a valid email address is rejected with 422'
    api.check(
        method='POST',
        path='/api/auth/login',
        role='anonymous',
        expected_status=422,
        path_params={},
        query_params={},
        body={'email': 'not-an-email', 'password': '{{admin.password}}'},
        test_id='authentication-login-invalid-email-format',
        test_type='schema_validation',
    )


def test_authentication_login_password_wrong_type(api):
    'Login with a numeric password instead of a string is rejected with 422'
    api.check(
        method='POST',
        path='/api/auth/login',
        role='anonymous',
        expected_status=422,
        path_params={},
        query_params={},
        body={'email': '{{admin.email}}', 'password': 12345678},
        test_id='authentication-login-password-wrong-type',
        test_type='schema_validation',
    )


def test_authentication_login_empty_body(api):
    'Login with an empty JSON object is rejected with 422'
    api.check(
        method='POST',
        path='/api/auth/login',
        role='anonymous',
        expected_status=422,
        path_params={},
        query_params={},
        body={},
        test_id='authentication-login-empty-body',
        test_type='schema_validation',
    )


def test_authentication_login_password_7_chars(api):
    'Password of 7 characters, one below the minimum length of 8, is rejected with 422'
    api.check(
        method='POST',
        path='/api/auth/login',
        role='anonymous',
        expected_status=422,
        path_params={},
        query_params={},
        body={'email': '{{admin.email}}', 'password': 'abcdefg'},
        test_id='authentication-login-password-7-chars',
        test_type='boundary_value',
    )


def test_authentication_login_password_empty(api):
    'Empty password string is below the minimum length and is rejected with 422'
    api.check(
        method='POST',
        path='/api/auth/login',
        role='anonymous',
        expected_status=422,
        path_params={},
        query_params={},
        body={'email': '{{admin.email}}', 'password': ''},
        test_id='authentication-login-password-empty',
        test_type='boundary_value',
    )
