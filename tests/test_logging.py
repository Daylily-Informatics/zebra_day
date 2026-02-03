"""
Tests for the zebra_day logging_config module.
"""
import logging
import tempfile
from pathlib import Path

from zebra_day import logging_config


class TestGetLogger:
    """Tests for get_logger function."""

    def test_get_logger_returns_logger(self):
        """Test get_logger returns a Logger instance."""
        logger = logging_config.get_logger("test_module")
        assert isinstance(logger, logging.Logger)

    def test_get_logger_with_zebra_day_prefix(self):
        """Test get_logger with zebra_day prefix."""
        logger = logging_config.get_logger("zebra_day.web.app")
        assert logger.name == "zebra_day.web.app"

    def test_get_logger_adds_prefix(self):
        """Test get_logger adds zebra_day prefix."""
        logger = logging_config.get_logger("my_module")
        assert logger.name == "zebra_day.my_module"


class TestConfigureLogging:
    """Tests for configure_logging function."""

    def test_configure_logging_sets_level(self):
        """Test configure_logging sets the logging level."""
        logging_config.configure_logging(level=logging.DEBUG)
        logger = logging.getLogger("zebra_day")
        assert logger.level == logging.DEBUG

    def test_configure_logging_info_level(self):
        """Test configure_logging with INFO level."""
        logging_config.configure_logging(level=logging.INFO)
        logger = logging.getLogger("zebra_day")
        assert logger.level == logging.INFO

    def test_configure_logging_creates_file_handler(self):
        """Test configure_logging creates file handler when log_file provided."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = Path(tmpdir) / "logs" / "test.log"
            logging_config.configure_logging(level=logging.INFO, log_file=log_path)

            # Log something
            logger = logging.getLogger("zebra_day")
            logger.info("Test log message")

            # Check file was created
            assert log_path.exists()

    def test_configure_logging_custom_format(self):
        """Test configure_logging accepts custom format."""
        custom_format = "%(levelname)s - %(message)s"
        logging_config.configure_logging(level=logging.INFO, format_string=custom_format)

        logger = logging.getLogger("zebra_day")
        assert len(logger.handlers) > 0

