"""
Tests for the zebra_day authentication module.
"""

import sys
from types import SimpleNamespace
from unittest.mock import Mock

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
        verify_token=lambda token: (
            {"sub": "access-sub", "username": "atlas-user"}
            if token == "access-token"
            else pytest.fail("expected access token verification")
        )
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

    def _verify_id_token(token, *, access_token=None):
        assert access_token == "access-token"
        if token != "id-token":
            pytest.fail("expected id token verification")
        return {
            "sub": "profile-sub",
            "email": "user@example.com",
            "name": "Atlas User",
            "aud": "client-id",
        }

    binding._verify_id_token = _verify_id_token

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
        verify_token=lambda token: (
            {"sub": "access-sub", "username": "atlas-user"}
            if token == "access-token"
            else pytest.fail("expected access token verification")
        )
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

    def _verify_id_token(token, *, access_token=None):
        assert access_token == "access-token"
        raise ValueError("jwt failed")

    binding._verify_id_token = _verify_id_token
    binding._decode_id_token_unverified = lambda token: (
        {
            "email": "fallback@example.com",
            "name": "Fallback User",
        }
        if token == "id-token"
        else pytest.fail("expected id token fallback decode")
    )

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
        verify_token=lambda token: (
            {"sub": "access-sub", "username": "atlas-user"}
            if token == "access-token"
            else pytest.fail("expected access token verification")
        )
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

    def _verify_id_token(token, *, access_token=None):
        assert access_token == "access-token"
        raise ValueError("jwt failed")

    binding._verify_id_token = _verify_id_token
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


def test_redirect_and_logout_uris_prefer_daycog_contract_urls():
    binding = auth.CognitoBinding(
        settings=SimpleNamespace(),
        config=SimpleNamespace(
            callback_url="https://127.0.0.1:8118/auth/callback",
            logout_url="https://0.0.0.0:8118/login",
        ),
        auth=SimpleNamespace(),
        oauth=SimpleNamespace(),
        jwks=SimpleNamespace(),
    )

    assert binding.redirect_uri(SimpleNamespace()) == "https://localhost:8118/auth/callback"
    assert binding.logout_uri(SimpleNamespace()) == "https://localhost:8118/login"


def test_load_daycog_contract_prefers_process_env_and_normalizes_domain(monkeypatch):
    monkeypatch.setenv("COGNITO_REGION", "us-west-2")
    monkeypatch.setenv("COGNITO_USER_POOL_ID", "pool-123")
    monkeypatch.setenv("COGNITO_APP_CLIENT_ID", "client-123")
    monkeypatch.setenv("COGNITO_DOMAIN", "https://example.auth.us-west-2.amazoncognito.com")
    monkeypatch.setattr(
        auth,
        "_load_daycog_file_values",
        lambda: (_ for _ in ()).throw(AssertionError("daycog config file should not be read")),
    )

    contract = auth.load_daycog_contract()

    assert contract["cognito_domain"] == "example.auth.us-west-2.amazoncognito.com"
    assert contract["region"] == "us-west-2"
    assert contract["user_pool_id"] == "pool-123"
    assert contract["app_client_id"] == "client-123"


def test_load_daycog_contract_falls_back_to_daycog_config_file_when_env_missing(monkeypatch):
    monkeypatch.delenv("COGNITO_REGION", raising=False)
    monkeypatch.delenv("COGNITO_USER_POOL_ID", raising=False)
    monkeypatch.delenv("COGNITO_APP_CLIENT_ID", raising=False)
    monkeypatch.delenv("COGNITO_DOMAIN", raising=False)
    monkeypatch.setattr(
        auth,
        "_load_daycog_file_values",
        lambda: {
            "COGNITO_REGION": "us-west-2",
            "COGNITO_USER_POOL_ID": "pool-123",
            "COGNITO_APP_CLIENT_ID": "client-123",
            "COGNITO_DOMAIN": "https://example.auth.us-west-2.amazoncognito.com",
        },
    )

    contract = auth.load_daycog_contract()

    assert contract["cognito_domain"] == "example.auth.us-west-2.amazoncognito.com"


def test_verify_id_token_passes_paired_access_token_to_jose_decode(monkeypatch):
    decode_kwargs = {}

    def fake_get_unverified_header(token):
        assert token == "id-token"
        return {"kid": "kid-123"}

    def fake_decode(
        token, key, algorithms=None, options=None, issuer=None, audience=None, access_token=None
    ):
        decode_kwargs.update(
            token=token,
            key=key,
            algorithms=algorithms,
            options=options,
            issuer=issuer,
            audience=audience,
            access_token=access_token,
        )
        return {"sub": "user-123", "email": "user@example.com"}

    fake_jwt = SimpleNamespace(
        get_unverified_header=fake_get_unverified_header,
        decode=fake_decode,
    )
    monkeypatch.setitem(
        sys.modules,
        "jose",
        SimpleNamespace(JWTError=ValueError, jwt=fake_jwt),
    )

    jwks_cache = SimpleNamespace(get_key=lambda kid: f"jwk-for-{kid}")
    binding = auth.CognitoBinding(
        settings=SimpleNamespace(),
        config=SimpleNamespace(
            app_client_id="client-id",
            region="us-west-2",
            user_pool_id="pool-id",
        ),
        auth=SimpleNamespace(_jwks_cache=jwks_cache),
        oauth=SimpleNamespace(),
        jwks=SimpleNamespace(
            JWKSCache=lambda region, pool_id: pytest.fail("unexpected JWKS cache init")
        ),
    )

    claims = binding._verify_id_token("id-token", access_token="access-token")

    assert claims["email"] == "user@example.com"
    assert decode_kwargs["access_token"] == "access-token"
    assert decode_kwargs["audience"] == "client-id"


def test_decode_id_token_unverified_disables_at_hash_verification(monkeypatch):
    binding = auth.CognitoBinding(
        settings=SimpleNamespace(),
        config=SimpleNamespace(),
        auth=SimpleNamespace(),
        oauth=SimpleNamespace(),
        jwks=SimpleNamespace(),
    )

    decode_mock = Mock(return_value={"email": "user@example.com"})
    monkeypatch.setitem(
        sys.modules,
        "jose",
        SimpleNamespace(
            JWTError=ValueError,
            jwt=SimpleNamespace(decode=decode_mock),
        ),
    )
    claims = binding._decode_id_token_unverified("id-token")

    assert claims["email"] == "user@example.com"
    assert decode_mock.call_args.kwargs["options"]["verify_at_hash"] is False
