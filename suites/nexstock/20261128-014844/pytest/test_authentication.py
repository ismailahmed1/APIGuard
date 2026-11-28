"""APIGuard tests for NexStock Authentication operations."""


# ---------------------------------------------------------------------------
# POST /api/auth/login
# ---------------------------------------------------------------------------

def test_authentication_login_admin_success(api):
    api.check(
        "POST",
        "/api/auth/login",
        "anonymous",
        200,
        body={"email": "{{admin.email}}", "password": "{{admin.password}}"},
        test_id="auth-login-admin-200",
        test_type="happy_path",
    )


def test_authentication_login_manager_success(api):
    api.check(
        "POST",
        "/api/auth/login",
        "anonymous",
        200,
        body={"email": "{{manager.email}}", "password": "{{manager.password}}"},
        test_id="auth-login-manager-200",
        test_type="happy_path",
    )


def test_authentication_login_missing_body_fields(api):
    api.check(
        "POST",
        "/api/auth/login",
        "anonymous",
        422,
        body={},
        test_id="auth-login-empty-body-422",
        test_type="schema_validation",
    )


def test_authentication_login_missing_password(api):
    api.check(
        "POST",
        "/api/auth/login",
        "anonymous",
        422,
        body={"email": "{{admin.email}}"},
        test_id="auth-login-missing-password-422",
        test_type="schema_validation",
    )


def test_authentication_login_missing_email(api):
    api.check(
        "POST",
        "/api/auth/login",
        "anonymous",
        422,
        body={"password": "{{admin.password}}"},
        test_id="auth-login-missing-email-422",
        test_type="schema_validation",
    )


def test_authentication_login_invalid_email_format(api):
    api.check(
        "POST",
        "/api/auth/login",
        "anonymous",
        422,
        body={"email": "not-an-email", "password": "{{admin.password}}"},
        test_id="auth-login-invalid-email-422",
        test_type="schema_validation",
    )


def test_authentication_login_email_wrong_type(api):
    api.check(
        "POST",
        "/api/auth/login",
        "anonymous",
        422,
        body={"email": 12345, "password": "{{admin.password}}"},
        test_id="auth-login-email-wrong-type-422",
        test_type="schema_validation",
    )


def test_authentication_login_password_below_min_length(api):
    # minLength is 8; 7 characters is just outside the documented limit
    api.check(
        "POST",
        "/api/auth/login",
        "anonymous",
        422,
        body={"email": "{{admin.email}}", "password": "abcdefg"},
        test_id="auth-login-password-len7-422",
        test_type="boundary_value",
    )


def test_authentication_login_password_empty(api):
    api.check(
        "POST",
        "/api/auth/login",
        "anonymous",
        422,
        body={"email": "{{admin.email}}", "password": ""},
        test_id="auth-login-password-empty-422",
        test_type="boundary_value",
    )


# ---------------------------------------------------------------------------
# GET /api/auth/me
# ---------------------------------------------------------------------------

def test_authentication_get_me_admin(api):
    api.check(
        "GET",
        "/api/auth/me",
        "admin",
        200,
        test_id="auth-me-admin-200",
        test_type="happy_path",
    )


def test_authentication_get_me_manager(api):
    api.check(
        "GET",
        "/api/auth/me",
        "manager",
        200,
        test_id="auth-me-manager-200",
        test_type="happy_path",
    )


def test_authentication_get_me_anonymous_unauthorized(api):
    api.check(
        "GET",
        "/api/auth/me",
        "anonymous",
        401,
        test_id="auth-me-anonymous-401",
        test_type="authentication",
    )
