# -*- coding: utf-8 -*-
"""Filesystem locations used by ACC Quick Access.

Default data folder:  %APPDATA%\\pyRevit\\ACCQuickAccess
For automated testing only, the environment variable ACCQA_DATA_DIR overrides it.
"""
import os

APP_FOLDER = "ACCQuickAccess"


def get_data_dir():
    override = os.environ.get("ACCQA_DATA_DIR")
    if override:
        return override
    base = os.environ.get("APPDATA")
    if not base:
        base = os.path.join(os.path.expanduser("~"), "AppData", "Roaming")
    return os.path.join(base, "pyRevit", APP_FOLDER)


def ensure_dir(path):
    """Create a directory (and parents) if it does not exist yet."""
    if os.path.isdir(path):
        return path
    try:
        os.makedirs(path)
    except OSError:
        # Another process may have created it in the meantime.
        if not os.path.isdir(path):
            raise
    return path


def get_config_path():
    return os.path.join(get_data_dir(), "config.json")


def get_backup_dir():
    return os.path.join(get_data_dir(), "backups")


def get_log_dir():
    return os.path.join(get_data_dir(), "logs")


def get_log_path():
    return os.path.join(get_log_dir(), "accqa.log")
