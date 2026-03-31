"""
Tests for the zebra_day authentication module.
"""

from types import SimpleNamespace

import pytest

from zebra_day.web import auth


class TestCognitoAvailability:
    """Tests for Cognito availability functions."""

    def test_is_cognito_available_returns_bool(self):
        """Test is_cognito_available returns a boolean."""
        result = auth.is_cognito_available()
        assert isinstance(result, bool)

    def test_get_cognito_import_error_returns_string_or_none(self):
        """Test get_cognito_import_error returns string or None."""
        result = auth.get_cognito_import_error()
        assert result is None or isinstance(result, str)

    def test_cognito_available_matches_import_error(self):
        """Test that availability and import error are consistent."""
        is_available = auth.is_cognito_available()
        import_error = auth.get_cognito_import_error()

        if is_available:
            assert import_error is None
        else:
            assert import_error is not None


class TestPublicPaths:
    """Tests for PUBLIC_PATHS configuration."""

    def test_public_paths_is_list(self):
        """Test PUBLIC_PATHS is a list."""
        assert isinstance(auth.PUBLIC_PATHS, list)

    def test_public_paths_contains_healthz(self):
        """Test PUBLIC_PATHS includes /healthz."""
        assert "/healthz" in auth.PUBLIC_PATHS

    def test_public_paths_does_not_expose_docs(self):
        """Docs are gated in the modern auth contract."""
        assert "/docs" not in auth.PUBLIC_PATHS


class TestSetupCognitoAuth:
    """Tests for setup_cognito_auth function."""

    def test_setup_cognito_raises_import_error_when_unavailable(self):
        """Test setup_cognito_auth raises ImportError when daylily-cognito not installed."""
        if not auth.is_cognito_available():
            with pytest.raises(ImportError) as exc_info:
                auth.setup_cognito_auth(None, None)
            assert "daylily-cognito" in str(exc_info.value)


def test_exchange_code_verifies_access_token_and_profiles_from_id_token():
    oauth = SimpleNamespace(
        exchange_authorization_code=lambda **kwargs: {
            "access_token": "access-token",
            "id_token": "id-token",
        }
    )
    auth_client = SimpleNamespace(
        verify_token=lambda token: {"sub": "access-sub", "username": "atlas-user"}
        if token == "access-token"
        else pytest.fail("expected access token verification")
    )
    jwks = SimpleNamespace()
    binding = auth.CognitoBinding(
        settings=SimpleNamespace(),
        config=SimpleNamespace(
            cognito_domain="example.com",
            app_client_id="client-id",
            region="us-west-2",
            user_pool_id="pool-id",
        ),
        auth=auth_client,
        oauth=oauth,
        jwks=jwks,
    )
    binding.redirect_uri = lambda request: "https://localhost:8118/auth/callback"
    binding._verify_id_token = lambda token: {
        "sub": "profile-sub",
        "email": "user@example.com",
        "name": "Atlas User",
        "aud": "client-id",
    } if token == "id-token" else pytest.fail("expected id token verification")

    result = binding.exchange_code(object(), "auth-code")

    assert result["claims"]["sub"] == "access-sub"
    assert result["profile_claims"]["email"] == "user@example.com"


def test_exchange_code_falls_back_to_unverified_id_token_profile_decode():
    oauth = SimpleNamespace(
        exchange_authorization_code=lambda **kwargs: {
            "access_token": "access-token",
            "id_token": "id-token",
        }
    )
    auth_client = SimpleNamespace(
        verify_token=lambda token: {"sub": "access-sub", "username": "atlas-user"}
        if token == "access-token"
        else pytest.fail("expected access token verification")
    )
    binding = auth.CognitoBinding(
        settings=SimpleNamespace(),
        config=SimpleNamespace(
            cognito_domain="example.com",
            app_client_id="client-id",
            region="us-west-2",
            user_pool_id="pool-id",
        ),
        auth=auth_client,
        oauth=oauth,
        jwks=SimpleNamespace(),
    )
    binding.redirect_uri = lambda request: "https://localhost:8118/auth/callback"
    binding._verify_id_token = lambda token: (_ for _ in ()).throw(ValueError("jwt failed"))
    binding._decode_id_token_unverified = lambda token: {
        "email": "fallback@example.com",
        "name": "Fallback User",
    } if token == "id-token" else pytest.fail("expected id token fallback decode")

    result = binding.exchange_code(object(), "auth-code")

    assert result["claims"]["sub"] == "access-sub"
    assert result["profile_claims"]["email"] == "fallback@example.com"


def test_exchange_code_continues_when_id_token_cannot_be_decoded():
    oauth = SimpleNamespace(
        exchange_authorization_code=lambda **kwargs: {
            "access_token": "access-token",
            "id_token": "id-token",
        }
    )
    auth_client = SimpleNamespace(
        verify_token=lambda token: {"sub": "access-sub", "username": "atlas-user"}
        if token == "access-token"
        else pytest.fail("expected access token verification")
    )
    binding = auth.CognitoBinding(
        settings=SimpleNamespace(),
        config=SimpleNamespace(
            cognito_domain="example.com",
            app_client_id="client-id",
            region="us-west-2",
            user_pool_id="pool-id",
        ),
        auth=auth_client,
        oauth=oauth,
        jwks=SimpleNamespace(),
    )
    binding.redirect_uri = lambda request: "https://localhost:8118/auth/callback"
    binding._verify_id_token = lambda token: (_ for _ in ()).throw(ValueError("jwt failed"))
    binding._decode_id_token_unverified = lambda token: (_ for _ in ()).throw(
        ValueError("payload failed")
    )

    result = binding.exchange_code(object(), "auth-code")

    assert result["claims"]["sub"] == "access-sub"
    assert result["profile_claims"] == {}


def test_build_user_identity_normalizes_cognito_groups_to_roles():
    settings = SimpleNamespace(
        cognito_group_role_map={
            "zebra-day-admin": "ADMIN",
            "zebra-day-operator": "OPERATOR",
        }
    )

    identity = auth.build_user_identity(
        {
            "sub": "abc123",
            "email": "user@example.com",
            "name": "Example User",
            "cognito:groups": ["zebra-day-admin"],
        },
        settings,
    )

    assert identity["cognito_groups"] == ["zebra-day-admin"]
    assert identity["roles"] == ["ADMIN", "OPERATOR"]
