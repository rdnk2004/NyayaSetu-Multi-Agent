"""
Unit tests for NyayaSetu Logging Configuration (src/logging_config.py).
"""

import logging
import os
import sys
from pathlib import Path

# Ensure src is in sys.path
src_dir = Path(__file__).resolve().parent.parent / "src"
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))

from logging_config import setup_logging, DEFAULT_LOG_LEVEL
import qa_agent
import orchestrator


def test_default_logging_setup():
    logger = setup_logging()
    assert logger.level in (logging.INFO, logging.DEBUG)


def test_explicit_level_setup():
    logger = setup_logging(level="DEBUG")
    assert logger.level == logging.DEBUG
    setup_logging(level="INFO")
    assert logger.level == logging.INFO


def test_env_var_level_setup():
    orig = os.environ.get("LOG_LEVEL")
    try:
        os.environ["LOG_LEVEL"] = "WARNING"
        logger = setup_logging()
        assert logger.level == logging.WARNING
    finally:
        if orig is not None:
            os.environ["LOG_LEVEL"] = orig
        else:
            os.environ.pop("LOG_LEVEL", None)
        setup_logging(level="INFO")


def test_logger_instances_in_pipeline_modules():
    assert isinstance(qa_agent.logger, logging.Logger)
    assert isinstance(orchestrator.logger, logging.Logger)
    assert qa_agent.logger.name == "qa_agent"
    assert orchestrator.logger.name == "orchestrator"
