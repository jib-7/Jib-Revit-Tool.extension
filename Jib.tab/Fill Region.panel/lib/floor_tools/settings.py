# -*- coding: utf-8 -*-
"""Static configuration constants and persisted per-user settings."""
from pyrevit import script

COMMAND_TITLE = "Floor to Fill Region"
TRANSACTION_NAME = "Floor to Fill Region"

# ---------------------------------------------------------------- versions --
# Versions the extension is designed for. Newer versions are allowed to run
# (with a note in the log) because the compat layer avoids removed APIs.
MIN_REVIT_VERSION = 2021
MAX_TESTED_REVIT_VERSION = 2026
ALLOW_UNTESTED_NEWER_VERSIONS = True

# ------------------------------------------------------------------- views --
# ViewType names (as strings, so no enum members are needed at import time).
SUPPORTED_VIEW_TYPE_NAMES = ("FloorPlan", "CeilingPlan", "EngineeringPlan", "AreaPlan")

# ------------------------------------------------------------ performance ---
PROGRESS_BAR_THRESHOLD = 25          # show a progress bar from this many floors

# ---------------------------------------------------------------- geometry --
# All lengths are Revit internal units (feet).
TOP_FACE_MIN_NORMAL_Z = 0.5          # fallback top-face detection
FLAT_TOLERANCE_FT = 1.0e-5           # "curve is parallel to the view plane"
CHAIN_TOLERANCE_FT = 5.0e-4          # joining unordered sketch curves
ARC_SEGMENT_LENGTH_FT = 0.25         # sampling density for area / tilted arcs
MIN_CURVE_SEGMENTS = 8
MAX_CURVE_SEGMENTS = 256
MIN_LOOP_AREA_SQFT = 1.0e-6
MAX_INTERSECTION_TEST_POINTS = 1500  # skip O(n^2) tests above this size

# --------------------------------------------------------- extensible storage
ES_SCHEMA_GUID = "b3a1f6c2-5d4e-4a8b-9c7d-2e1f0a9b8c7d"
ES_SCHEMA_NAME = "FloorToFillRegionSource"
ES_VENDOR_ID = "FloorTools"
ES_FIELD_SOURCE = "SourceFloorUniqueId"

# ---------------------------------------------------------- persisted config -
CONFIG_SECTION = "FloorToFillRegion"

# Which material pattern of the Floor is copied to the Filled Region Type.
PATTERN_SOURCE_SURFACE = "surface"   # what is drawn on the floor top in plan views
PATTERN_SOURCE_CUT = "cut"           # pattern used when the floor is cut


class UserSettings(object):
    """Values remembered between runs (stored in pyRevit's config file)."""

    def __init__(self):
        self.region_type_uid = ""
        self.region_type_name = ""
        self.offset_text = "0"
        self.prevent_duplicates = True
        self.verbose_log = False
        self.use_floor_style = True
        self.pattern_source = PATTERN_SOURCE_SURFACE


def _to_bool(value, default):
    if value is None:
        return default
    return str(value).strip().lower() in ("true", "1", "yes")


def load():
    """Read the remembered settings; never raises."""
    settings = UserSettings()
    try:
        cfg = script.get_config(CONFIG_SECTION)
        settings.region_type_uid = str(cfg.get_option("region_type_uid", ""))
        settings.region_type_name = str(cfg.get_option("region_type_name", ""))
        settings.offset_text = str(cfg.get_option("offset_text", "0"))
        settings.prevent_duplicates = _to_bool(cfg.get_option("prevent_duplicates", "True"), True)
        settings.verbose_log = _to_bool(cfg.get_option("verbose_log", "False"), False)
        settings.use_floor_style = _to_bool(cfg.get_option("use_floor_style", "True"), True)
        source = str(cfg.get_option("pattern_source", PATTERN_SOURCE_SURFACE))
        settings.pattern_source = source if source in (PATTERN_SOURCE_SURFACE, PATTERN_SOURCE_CUT) else PATTERN_SOURCE_SURFACE
    except Exception:
        pass  # fall back to defaults - remembering settings is a convenience only
    return settings


def save(settings):
    """Persist the settings; never raises."""
    try:
        cfg = script.get_config(CONFIG_SECTION)
        cfg.set_option("region_type_uid", settings.region_type_uid)
        cfg.set_option("region_type_name", settings.region_type_name)
        cfg.set_option("offset_text", settings.offset_text)
        cfg.set_option("prevent_duplicates", str(bool(settings.prevent_duplicates)))
        cfg.set_option("verbose_log", str(bool(settings.verbose_log)))
        cfg.set_option("use_floor_style", str(bool(settings.use_floor_style)))
        cfg.set_option("pattern_source", settings.pattern_source)
        script.save_config()
    except Exception:
        pass
