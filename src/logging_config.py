"""
Central Logging Configuration for NyayaSetu.

Configures root and application loggers based on the LOG_LEVEL environment variable
(defaulting to INFO). Can be imported early across CLI scripts and test suites.
"""

import logging
import os
import sys

DEFAULT_LOG_LEVEL = "INFO"


def setup_logging(level: str | int | None = None) -> logging.Logger:
    """
    Configures standard logging format and sets the log level.
    Precedence:
      1. Explicit argument `level` (if provided)
      2. Environment variable `LOG_LEVEL` (e.g. DEBUG, INFO, WARNING, ERROR)
      3. DEFAULT_LOG_LEVEL ("INFO")
    """
    if level is None:
        raw_level = os.environ.get("LOG_LEVEL", DEFAULT_LOG_LEVEL).strip().upper()
        level = getattr(logging, raw_level, logging.INFO)
    elif isinstance(level, str):
        level = getattr(logging, level.strip().upper(), logging.INFO)

    root_logger = logging.getLogger()
    if not root_logger.handlers:
        logging.basicConfig(
            level=level,
            format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
            stream=sys.stderr,
        )
    else:
        root_logger.setLevel(level)

    return root_logger


# Automatically configure logging on initial import
setup_logging()
