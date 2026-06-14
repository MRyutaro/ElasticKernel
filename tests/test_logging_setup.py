"""Tests for the consolidated logger setup (D-7).

Logger names, log filenames, and the format string must stay identical to the
previous per-module setup; this also guards against handler duplication on
re-initialization.
"""

import logging
from logging.handlers import RotatingFileHandler

from elastic_notebook.core.common.logging_setup import (
    DATE_FORMAT,
    LOG_FORMAT,
    JSTFormatter,
    setup_logger,
)


def _rotating_handlers(logger):
    return [h for h in logger.handlers if isinstance(h, RotatingFileHandler)]


def test_setup_logger_adds_single_jst_handler(tmp_path):
    name = "TestLogger_single"
    logging.getLogger(name).handlers.clear()
    try:
        logger = setup_logger(name, str(tmp_path / "Test.log"))
        handlers = _rotating_handlers(logger)
        assert len(handlers) == 1
        assert isinstance(handlers[0].formatter, JSTFormatter)
        assert handlers[0].formatter._fmt == LOG_FORMAT
        assert handlers[0].formatter.datefmt == DATE_FORMAT
    finally:
        logging.getLogger(name).handlers.clear()


def test_setup_logger_no_duplicate_handler_on_reinit(tmp_path):
    name = "TestLogger_dup"
    logging.getLogger(name).handlers.clear()
    try:
        log_path = str(tmp_path / "Test.log")
        setup_logger(name, log_path)
        logger = setup_logger(name, log_path)  # second call must not duplicate
        assert len(_rotating_handlers(logger)) == 1
    finally:
        logging.getLogger(name).handlers.clear()


def test_setup_logger_respects_level_env(tmp_path, monkeypatch):
    name = "TestLogger_level"
    logging.getLogger(name).handlers.clear()
    try:
        monkeypatch.setenv("ELASTIC_KERNEL_LOG_LEVEL", "DEBUG")
        logger = setup_logger(name, str(tmp_path / "Test.log"))
        assert logger.level == logging.DEBUG
    finally:
        logging.getLogger(name).handlers.clear()
