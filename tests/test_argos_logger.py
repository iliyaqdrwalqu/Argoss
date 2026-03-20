"""Tests for src/argos_logger.py"""
import logging
import os
import pytest


def test_get_logger_returns_logger():
    from src.argos_logger import get_logger
    logger = get_logger("test.module")
    assert isinstance(logger, logging.Logger)


def test_get_logger_has_handler():
    from src.argos_logger import get_logger
    logger = get_logger("test.handler")
    assert len(logger.handlers) > 0


def test_get_logger_name():
    from src.argos_logger import get_logger
    logger = get_logger("test.name")
    assert logger.name == "test.name"


def test_get_logger_default_level_info():
    from src.argos_logger import get_logger
    logger = get_logger("test.level")
    assert logger.level == logging.INFO


def test_get_logger_custom_level_via_env(monkeypatch):
    monkeypatch.setenv("ARGOS_LOG_LEVEL", "DEBUG")
    from src.argos_logger import get_logger
    logger = get_logger("test.debug_level")
    assert logger.level == logging.DEBUG


def test_get_logger_idempotent():
    from src.argos_logger import get_logger
    logger1 = get_logger("test.idempotent")
    logger2 = get_logger("test.idempotent")
    assert logger1 is logger2
