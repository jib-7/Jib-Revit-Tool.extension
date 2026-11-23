# -*- coding: utf-8 -*-
"""File logging. Technical details go to the log, users see friendly messages."""
import os
import logging
import traceback

from accqa import paths
from accqa.revit_compat import to_text

_LOGGER_NAME = "accqa"
_MAX_BYTES = 1024 * 1024


def _rotate_if_large(path):
    """Very small, lock-tolerant rotation done once when the logger is created."""
    try:
        if os.path.exists(path) and os.path.getsize(path) > _MAX_BYTES:
            old = path + ".old"
            if os.path.exists(old):
                os.remove(old)
            os.rename(path, old)
    except Exception:
        pass  # Another Revit session may hold the file; never fail because of logging.


def get_logger():
    logger = logging.getLogger(_LOGGER_NAME)
    if getattr(logger, "_accqa_ready", False):
        return logger
    logger.setLevel(logging.DEBUG)
    logger.propagate = False
    try:
        paths.ensure_dir(paths.get_log_dir())
        log_path = paths.get_log_path()
        _rotate_if_large(log_path)
        handler = logging.FileHandler(log_path, mode="a", encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
        logger.addHandler(handler)
    except Exception:
        logger.addHandler(logging.NullHandler())
    logger._accqa_ready = True
    return logger


def _safe(message):
    try:
        return to_text(message)
    except Exception:
        return u"<unprintable message>"


def info(message):
    try:
        get_logger().info(_safe(message))
    except Exception:
        pass


def warning(message):
    try:
        get_logger().warning(_safe(message))
    except Exception:
        pass


def error(message):
    try:
        get_logger().error(_safe(message))
    except Exception:
        pass


def log_exception(context):
    """Write the current exception with traceback to the log file."""
    try:
        get_logger().error(_safe(context) + u"\n" + _safe(traceback.format_exc()))
    except Exception:
        pass


def get_log_path():
    return paths.get_log_path()
