"""
Tests for the zebra_day paths module (XDG Base Directory).
"""

from pathlib import Path

from zebra_day import paths as xdg


class TestXDGPaths:
    """Tests for XDG path functions."""

    def test_get_config_dir_returns_path(self):
        """Test get_config_dir returns a Path object."""
        result = xdg.get_config_dir()
        assert isinstance(result, Path)

    def test_get_data_dir_returns_path(self):
        """Test get_data_dir returns a Path object."""
        result = xdg.get_data_dir()
        assert isinstance(result, Path)

    def test_get_logs_dir_returns_path(self):
        """Test get_logs_dir returns a Path object."""
        result = xdg.get_logs_dir()
        assert isinstance(result, Path)

    def test_get_cache_dir_returns_path(self):
        """Test get_cache_dir returns a Path object."""
        result = xdg.get_cache_dir()
        assert isinstance(result, Path)

    def test_get_state_dir_returns_path(self):
        """Test get_state_dir returns a Path object."""
        result = xdg.get_state_dir()
        assert isinstance(result, Path)

    def test_get_printer_config_path_returns_path(self):
        """Test get_printer_config_path returns a Path object (now YAML)."""
        result = xdg.get_printer_config_path()
        assert isinstance(result, Path)
        # Since 2.2.0, this now returns the YAML config path
        assert result.name == "zebra-day-config.yaml"

    def test_get_config_file_path_returns_yaml_path(self):
        """Test get_config_file_path returns YAML path."""
        result = xdg.get_config_file_path()
        assert isinstance(result, Path)
        assert result.name == "zebra-day-config.yaml"

    def test_get_legacy_json_config_path_returns_json_path(self):
        """Test get_legacy_json_config_path returns JSON path."""
        result = xdg.get_legacy_json_config_path()
        assert isinstance(result, Path)
        assert result.name == "printer_config.json"

    def test_get_generated_files_dir_returns_path(self):
        """Test get_generated_files_dir returns a Path object."""
        result = xdg.get_generated_files_dir()
        assert isinstance(result, Path)


class TestXDGPathConsistency:
    """Tests for XDG path consistency."""

    def test_config_dir_ends_with_zebra_day(self):
        """Test config dir path ends with zebra_day."""
        result = xdg.get_config_dir()
        assert "zebra_day" in str(result)

    def test_data_dir_ends_with_zebra_day(self):
        """Test data dir path ends with zebra_day."""
        result = xdg.get_data_dir()
        assert "zebra_day" in str(result)
