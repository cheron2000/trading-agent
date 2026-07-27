"""
Production logging interfaces and implementation.

This module defines the logging abstraction for the Foundation Layer.
All framework components should depend on the ILogger interface rather
than the standard logging module directly.

Python: 3.13+
"""

from __future__ import annotations

import logging
import sys
from abc import ABC, abstractmethod
from pathlib import Path
from typing import ClassVar

from foundation.constants import (
    DEFAULT_DATE_FORMAT,
    DEFAULT_LOG_FORMAT,
    DEFAULT_LOGGER_NAME,
)
from foundation.enums import LogLevel


class ILogger(ABC):
    """Abstract logging interface."""

    @abstractmethod
    def debug(self, message: str, *args: object) -> None:
        """Log a debug message."""

    @abstractmethod
    def info(self, message: str, *args: object) -> None:
        """Log an informational message."""

    @abstractmethod
    def warning(self, message: str, *args: object) -> None:
        """Log a warning message."""

    @abstractmethod
    def error(self, message: str, *args: object) -> None:
        """Log an error message."""

    @abstractmethod
    def critical(self, message: str, *args: object) -> None:
        """Log a critical message."""

    @abstractmethod
    def exception(self, message: str, *args: object) -> None:
        """Log an exception with traceback."""


class ProductionLogger(ILogger):
    """Production-ready logger implementation."""

    _LEVEL_MAP: ClassVar[dict[LogLevel, int]] = {
        LogLevel.DEBUG: logging.DEBUG,
        LogLevel.INFO: logging.INFO,
        LogLevel.WARNING: logging.WARNING,
        LogLevel.ERROR: logging.ERROR,
        LogLevel.CRITICAL: logging.CRITICAL,
    }

    def __init__(
        self,
        *,
        name: str = DEFAULT_LOGGER_NAME,
        level: LogLevel = LogLevel.INFO,
        log_file: str | Path | None = None,
    ) -> None:
        """
        Initialize the logger.

        Args:
            name: Logger name.
            level: Minimum logging level.
            log_file: Optional log file path. If omitted, logs are written
                to stdout only.
        """
        self._logger = logging.getLogger(name)
        self._logger.setLevel(self._LEVEL_MAP[level])
        self._logger.propagate = False

        if self._logger.handlers:
            return

        formatter = logging.Formatter(
            fmt=DEFAULT_LOG_FORMAT,
            datefmt=DEFAULT_DATE_FORMAT,
        )

        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(formatter)
        self._logger.addHandler(console_handler)

        if log_file is not None:
            safe_log_path = Path(log_file).resolve()
            file_handler = logging.FileHandler(
                filename=safe_log_path,
                encoding="utf-8",
            )
            file_handler.setFormatter(formatter)
            self._logger.addHandler(file_handler)

    @property
    def logger(self) -> logging.Logger:
        """Return the underlying standard logger."""
        return self._logger

    def set_level(self, level: LogLevel) -> None:
        """
        Update the active logging level.

        Args:
            level: New minimum logging level.
        """
        self._logger.setLevel(self._LEVEL_MAP[level])

    def debug(self, message: str, *args: object) -> None:
        """Log a debug message."""
        self._logger.debug(message, *args)

    def info(self, message: str, *args: object) -> None:
        """Log an informational message."""
        self._logger.info(message, *args)

    def warning(self, message: str, *args: object) -> None:
        """Log a warning message."""
        self._logger.warning(message, *args)

    def error(self, message: str, *args: object) -> None:
        """Log an error message."""
        self._logger.error(message, *args)

    def critical(self, message: str, *args: object) -> None:
        """Log a critical message."""
        self._logger.critical(message, *args)

    def exception(self, message: str, *args: object) -> None:
        """Log an exception with traceback."""
        self._logger.exception(message, *args)
