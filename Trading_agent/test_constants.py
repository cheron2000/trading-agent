"""
Unit tests for foundation.constants.

Python: 3.13+
"""

from foundation import constants


def test_system_name() -> None:
    """SYSTEM_NAME should be defined."""
    assert constants.SYSTEM_NAME == "AI Trading Operating System"


def test_system_short_name() -> None:
    """SYSTEM_SHORT_NAME should be defined."""
    assert constants.SYSTEM_SHORT_NAME == "AITOS"


def test_api_version() -> None:
    """API version should be a non-empty string."""
    assert isinstance(constants.API_VERSION, str)
    assert constants.API_VERSION


def test_event_schema_version() -> None:
    """Event schema version should be defined."""
    assert isinstance(constants.EVENT_SCHEMA_VERSION, str)
    assert constants.EVENT_SCHEMA_VERSION


def test_default_encoding() -> None:
    """UTF-8 should be the default encoding."""
    assert constants.DEFAULT_TEXT_ENCODING == "utf-8"


def test_default_timezone() -> None:
    """UTC should be the default timezone."""
    assert constants.DEFAULT_TIMEZONE == "UTC"


def test_default_logger_name() -> None:
    """Logger name should not be empty."""
    assert constants.DEFAULT_LOGGER_NAME


def test_default_log_format() -> None:
    """Log format should contain required placeholders."""
    log_format = constants.DEFAULT_LOG_FORMAT

    assert "%(asctime)s" in log_format
    assert "%(levelname)s" in log_format
    assert "%(message)s" in log_format


def test_default_date_format() -> None:
    """Date format should not be empty."""
    assert constants.DEFAULT_DATE_FORMAT


def test_plugin_directory_name() -> None:
    """Plugin directory should be defined."""
    assert constants.PLUGIN_DIRECTORY_NAME == "plugins"


def test_default_config_filename() -> None:
    """Configuration filename should end with .yaml."""
    assert constants.DEFAULT_CONFIG_FILENAME.endswith(".yaml")


def test_min_uuid_length() -> None:
    """UUID string length should match canonical UUID format."""
    assert constants.MIN_UUID_LENGTH == 36


def test_json_extension() -> None:
    """JSON extension should be correct."""
    assert constants.JSON_EXTENSION == ".json"


def test_yaml_extension() -> None:
    """YAML extension should be correct."""
    assert constants.YAML_EXTENSION == ".yaml"


def test_yml_extension() -> None:
    """YML extension should be correct."""
    assert constants.YML_EXTENSION == ".yml"


def test_log_extension() -> None:
    """Log extension should be correct."""
    assert constants.LOG_EXTENSION == ".log"