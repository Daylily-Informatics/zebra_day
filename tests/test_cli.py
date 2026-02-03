"""
Tests for the zebra_day CLI commands.
"""

from typer.testing import CliRunner

from zebra_day.cli import _get_version, app

runner = CliRunner()


class TestCLIVersion:
    """Tests for the version command."""

    def test_get_version_returns_string(self):
        """Test _get_version returns a string."""
        version = _get_version()
        assert isinstance(version, str)
        assert len(version) > 0

    def test_version_command(self):
        """Test version command outputs version."""
        result = runner.invoke(app, ["version"])
        assert result.exit_code == 0
        assert "zebra_day" in result.output


class TestCLIInfo:
    """Tests for the info command."""

    def test_info_command(self):
        """Test info command runs and shows table."""
        result = runner.invoke(app, ["info"])
        assert result.exit_code == 0
        assert "Version" in result.output
        assert "Config Dir" in result.output


class TestCLIStatus:
    """Tests for the status command."""

    def test_status_command(self):
        """Test status command runs."""
        result = runner.invoke(app, ["status"])
        assert result.exit_code == 0
        # Status shows printer counts
        assert "Labs" in result.output or "Printer" in result.output


class TestCLITemplateList:
    """Tests for template list command."""

    def test_template_list_command(self):
        """Test template list command runs."""
        result = runner.invoke(app, ["template", "list"])
        assert result.exit_code == 0
        # Should show templates or empty list
        assert "Template" in result.output or "Stable" in result.output or result.exit_code == 0


class TestCLIPrinterList:
    """Tests for printer list command."""

    def test_printer_list_command(self):
        """Test printer list command runs."""
        result = runner.invoke(app, ["printer", "list"])
        assert result.exit_code == 0


class TestCLIHelp:
    """Tests for CLI help output."""

    def test_main_help(self):
        """Test main help shows subcommands."""
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "gui" in result.output
        assert "printer" in result.output
        assert "template" in result.output

    def test_gui_help(self):
        """Test gui subcommand help."""
        result = runner.invoke(app, ["gui", "--help"])
        assert result.exit_code == 0
        assert "start" in result.output
        assert "stop" in result.output

    def test_printer_help(self):
        """Test printer subcommand help."""
        result = runner.invoke(app, ["printer", "--help"])
        assert result.exit_code == 0
        assert "list" in result.output

    def test_template_help(self):
        """Test template subcommand help."""
        result = runner.invoke(app, ["template", "--help"])
        assert result.exit_code == 0
        assert "list" in result.output


class TestCLIGuiStatus:
    """Tests for GUI status command."""

    def test_gui_status_command(self):
        """Test gui status command runs."""
        result = runner.invoke(app, ["gui", "status"])
        # exit_code 0 = running, exit_code 1 = not running (both valid)
        assert result.exit_code in (0, 1)
