"""
Tests for the zebra_day authentication module.
"""
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

