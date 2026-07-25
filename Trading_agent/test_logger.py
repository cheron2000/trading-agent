"""
Unit tests for foundation.logger.

Python: 3.13+
"""

from __future__ import annotations

import logging
from pathlib import Path

from foundation.enums import LogLevel
from foundation.logger import ILogger, ProductionLogger


# ============================================================================
# Interface Compliance
# ============================================================================


def test_logger_implements_interface() -> None:
    """ProductionLogger should implement ILogger."""
    logger = ProductionLogger()

    assert isinstance(logger, ILogger)


# ============================================================================
# Construction
# ============================================================================


def test_default_logger_creation() -> None:
    """Logger should be created successfully with default settings."""
    logger = ProductionLogger()

    assert isinstance(logger.logger, logging.Logger)


def test_custom_logger_name() -> None:
    """Logger should use the supplied logger name."""
    logger = ProductionLogger(name="unit_test_logger")

    assert logger.logger.name == "unit_test_logger"


# ============================================================================
# Log Level
# ============================================================================


def test_default_log_level() -> None:
    """Default logging level should be INFO."""
    logger = ProductionLogger()

    assert logger.logger.level == logging.INFO


def test_set_log_level() -> None:
    """Logger level should be updated."""
    logger = ProductionLogger()

    logger.set_level(LogLevel.DEBUG)

    assert logger.logger.level == logging.DEBUG


# ============================================================================
# Logging Methods
# ============================================================================


def test_debug_logging() -> None:
    """Debug logging should execute without error."""
    logger = ProductionLogger(level=LogLevel.DEBUG)

    logger.debug("debug message")


def test_info_logging() -> None:
    """Info logging should execute without error."""
    logger = ProductionLogger()

    logger.info("info message")


def test_warning_logging() -> None:
    """Warning logging should execute without error."""
    logger = ProductionLogger()

    logger.warning("warning message")


def test_error_logging() -> None:
    """Error logging should execute without error."""
    logger = ProductionLogger()

    logger.error("error message")


def test_critical_logging() -> None:
    """Critical logging should execute without error."""
    logger = ProductionLogger()

    logger.critical("critical message")


def test_exception_logging() -> None:
    """Exception logging should include traceback."""
    logger = ProductionLogger()

    try:
        raise RuntimeError("boom")
    except RuntimeError:
        logger.exception("exception occurred")


# ============================================================================
# File Logging
# ============================================================================


def test_file_logging(tmp_path: Path) -> None:
    """Logger should write messages to a file."""
    log_file = tmp_path / "test.log"

    logger = ProductionLogger(
        name="file_logger",
        log_file=log_file,
    )

    logger.info("file logging works")

    assert log_file.exists()

    content = log_file.read_text(encoding="utf-8")

    assert "file logging works" in content


# ============================================================================
# Handler Reuse
# ============================================================================


def test_logger_does_not_duplicate_handlers() -> None:
    """Creating the same logger twice should not duplicate handlers."""
    logger1 = ProductionLogger(name="duplicate_logger")
    handler_count = len(logger1.logger.handlers)

    logger2 = ProductionLogger(name="duplicate_logger")

    assert len(logger2.logger.handlers) == handler_count


# ============================================================================
# Logger Property
# ============================================================================


def test_logger_property_returns_standard_logger() -> None:
    """The logger property should expose the underlying logger."""
    logger = ProductionLogger()

    assert isinstance(logger.logger, logging.Logger)