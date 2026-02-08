"""
Tests for the mkcert integration module.
"""

from unittest import mock

from zebra_day import mkcert


class TestPlatformDetection:
    """Tests for platform-specific installation command detection."""

    def test_get_platform_install_command_darwin(self):
        """Test macOS returns brew install command."""
        with mock.patch("platform.system", return_value="Darwin"):
            cmd = mkcert.get_platform_install_command()
            assert cmd == "brew install mkcert"

    def test_get_platform_install_command_ubuntu(self):
        """Test Ubuntu returns apt install command."""
        with mock.patch("platform.system", return_value="Linux"):
            with mock.patch("builtins.open", mock.mock_open(read_data="ID=ubuntu\n")):
                cmd = mkcert.get_platform_install_command()
                assert "apt install mkcert" in cmd

    def test_get_platform_install_command_windows(self):
        """Test Windows returns choco install command."""
        with mock.patch("platform.system", return_value="Windows"):
            cmd = mkcert.get_platform_install_command()
            assert "choco install mkcert" in cmd


class TestMkcertChecks:
    """Tests for mkcert installation and CA checks."""

    def test_is_mkcert_installed_true(self):
        """Test mkcert detection when installed."""
        with mock.patch("shutil.which", return_value="/usr/local/bin/mkcert"):
            assert mkcert.is_mkcert_installed() is True

    def test_is_mkcert_installed_false(self):
        """Test mkcert detection when not installed."""
        with mock.patch("shutil.which", return_value=None):
            assert mkcert.is_mkcert_installed() is False

    def test_is_ca_installed_true(self):
        """Test CA detection when installed."""
        with mock.patch("shutil.which", return_value="/usr/local/bin/mkcert"):
            with mock.patch("subprocess.run") as mock_run:
                mock_run.return_value = mock.Mock(
                    returncode=0, stdout="/Users/test/.local/share/mkcert\n"
                )
                with mock.patch("pathlib.Path.exists", return_value=True):
                    assert mkcert.is_ca_installed() is True

    def test_is_ca_installed_false_no_mkcert(self):
        """Test CA detection when mkcert not installed."""
        with mock.patch("shutil.which", return_value=None):
            assert mkcert.is_ca_installed() is False


class TestCertificateGeneration:
    """Tests for certificate generation."""

    def test_certificates_exist_true(self):
        """Test certificate existence check when both files exist."""
        with mock.patch("pathlib.Path.exists", return_value=True):
            assert mkcert.certificates_exist() is True

    def test_certificates_exist_false(self):
        """Test certificate existence check when files don't exist."""
        with mock.patch("pathlib.Path.exists", return_value=False):
            assert mkcert.certificates_exist() is False

    def test_generate_certificates_no_mkcert(self):
        """Test certificate generation fails when mkcert not installed."""
        with mock.patch("shutil.which", return_value=None):
            result = mkcert.generate_certificates()
            assert result is False

    def test_generate_certificates_success(self):
        """Test successful certificate generation."""
        with mock.patch("shutil.which", return_value="/usr/local/bin/mkcert"):
            with mock.patch("pathlib.Path.exists", return_value=False):
                with mock.patch("pathlib.Path.mkdir"):
                    with mock.patch("subprocess.run") as mock_run:
                        mock_run.return_value = mock.Mock(returncode=0)
                        result = mkcert.generate_certificates()
                        assert result is True


class TestAutoGeneration:
    """Tests for automatic certificate generation."""

    def test_try_auto_generate_existing_certs(self):
        """Test auto-generation when certificates already exist."""
        with mock.patch("zebra_day.mkcert.certificates_exist", return_value=True):
            success, message, cert, key = mkcert.try_auto_generate_certificates()
            assert success is True
            assert "already exist" in message.lower()
            assert cert is not None
            assert key is not None

    def test_try_auto_generate_no_mkcert(self):
        """Test auto-generation when mkcert not installed."""
        with mock.patch("zebra_day.mkcert.certificates_exist", return_value=False):
            with mock.patch("zebra_day.mkcert.is_mkcert_installed", return_value=False):
                success, message, cert, key = mkcert.try_auto_generate_certificates()
                assert success is False
                assert "not installed" in message.lower()
                assert cert is None
                assert key is None

    def test_try_auto_generate_no_ca(self):
        """Test auto-generation when CA not installed."""
        with mock.patch("zebra_day.mkcert.certificates_exist", return_value=False):
            with mock.patch("zebra_day.mkcert.is_mkcert_installed", return_value=True):
                with mock.patch("zebra_day.mkcert.is_ca_installed", return_value=False):
                    success, message, cert, key = mkcert.try_auto_generate_certificates()
                    assert success is False
                    assert "mkcert -install" in message
                    assert cert is None
                    assert key is None

    def test_try_auto_generate_success(self):
        """Test successful auto-generation."""
        with mock.patch("zebra_day.mkcert.certificates_exist", return_value=False):
            with mock.patch("zebra_day.mkcert.is_mkcert_installed", return_value=True):
                with mock.patch("zebra_day.mkcert.is_ca_installed", return_value=True):
                    with mock.patch("zebra_day.mkcert.generate_certificates", return_value=True):
                        success, message, cert, key = mkcert.try_auto_generate_certificates()
                        assert success is True
                        assert "success" in message.lower()
                        assert cert is not None
                        assert key is not None
