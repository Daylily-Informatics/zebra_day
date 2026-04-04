"""
Tests for the zebra_day authentication module.
"""

import os
from unittest import mock

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

    def test_public_paths_contains_docs(self):
        """Test PUBLIC_PATHS includes /docs."""
        assert "/docs" in auth.PUBLIC_PATHS


class TestSetupCognitoAuth:
    """Tests for setup_cognito_auth function."""

    def test_setup_cognito_raises_import_error_when_unavailable(self):
        """Test setup_cognito_auth raises ImportError when daylily-cognito not installed."""
        if not auth.is_cognito_available():
            with pytest.raises(ImportError) as exc_info:
                auth.setup_cognito_auth(None)
            assert "daylily-cognito" in str(exc_info.value)

    def test_setup_cognito_auth_prefers_process_env_over_context_store(self):
        """Process env should override the active daycog context when both are present."""
        if not auth.is_cognito_available():
            pytest.skip("daylily-cognito is required for this test")

        with mock.patch.dict(
            os.environ,
            {
                "COGNITO_REGION": "us-east-2",
                "COGNITO_USER_POOL_ID": "pool-from-env",
                "COGNITO_APP_CLIENT_ID": "client-from-env",
                "AWS_PROFILE": "profile-from-env",
                "COGNITO_DOMAIN": "domain-from-env",
            },
            clear=True,
        ), mock.patch("daylily_cognito.config.get_context_values", return_value={}), mock.patch.object(
            auth, "CognitoAuth"
        ) as mock_cognito_auth:
            auth.setup_cognito_auth(None)

        mock_cognito_auth.assert_called_once_with(
            region="us-east-2",
            user_pool_id="pool-from-env",
            app_client_id="client-from-env",
            profile="profile-from-env",
        )
