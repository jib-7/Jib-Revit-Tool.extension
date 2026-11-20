# -*- coding: utf-8 -*-
"""Settings: defaults, optional user override file, internal-unit Config."""
from __future__ import division
import json
import math
import os

# Order matters: it is the order shown by the Shift+Click settings editor.
DEFAULTS = [
    ("region_type_token", "026"),
    ("line005_token", "005"),
    ("line006_token", "006"),
    ("line008_token", "008"),
    ("point010_token", "010"),
    ("line005_side_offset_mm", 32.5),
    ("line005_bottom_offset_mm", 95.0),
    ("line006_side_offset_mm", 22.5),
    ("line006_above_005_mm", 10.0),
    ("line008_offset_mm", 15.0),
    ("line008_top_inset_from_006_mm", 10.0),
    ("point010_below_mm", 80.0),
    ("snap_tolerance_mm", 0.5),
    ("max_gap_mm", 100.0),
    ("max_top_gap_mm", 3000.0),
    ("top_closure_max_angle_deg", 10.0),
    ("search_radius_mm", 6000.0),
    ("ambiguity_tolerance_mm", 5.0),
    ("vertical_tolerance_deg", 2.0),
    ("horizontal_tolerance_deg", 2.0),
    ("level_tolerance_mm", 1.0),
    ("arc_tessellation_tolerance_mm", 0.1),
    ("min_segment_mm", 1.0),
    ("exclude_output_families_from_boundary", True),
    ("write_tag_comments", True),
    ("inspect_families_deep", True),
    ("fail_on_halftone_error", True),
]


def default_settings():
    return dict(DEFAULTS)


def settings_path():
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    return os.path.join(base, "FillPlanterCavity", "settings.json")


def load_settings(path=None):
    s = default_settings()
    path = path or settings_path()
    try:
        if os.path.isfile(path):
            with open(path, "r") as fh:
                user = json.load(fh)
            for k, v in user.items():
                if k in s:
                    s[k] = v
    except Exception:
        pass   # corrupt user file -> silently use defaults
    return s


def save_settings(s, path=None):
    path = path or settings_path()
    folder = os.path.dirname(path)
    if not os.path.isdir(folder):
        os.makedirs(folder)
    with open(path, "w") as fh:
        json.dump(s, fh, indent=2, sort_keys=True)
    return path


class Config(object):
    """Settings converted to Revit internal units (feet) / radians."""

    def __init__(self, s, to_internal):
        c = to_internal
        self.raw = dict(s)
        self.snap_tol = c(s["snap_tolerance_mm"])
        self.max_gap = c(s["max_gap_mm"])
        self.max_top_gap = c(s["max_top_gap_mm"])
        self.top_angle = math.radians(s["top_closure_max_angle_deg"])
        self.search_radius = c(s["search_radius_mm"])
        self.ambiguity_tol = c(s["ambiguity_tolerance_mm"])
        self.vert_tol = math.radians(s["vertical_tolerance_deg"])
        self.horiz_tol = math.radians(s["horizontal_tolerance_deg"])
        self.level_tol = c(s["level_tolerance_mm"])
        self.arc_tol = c(s["arc_tessellation_tolerance_mm"])
        self.min_seg = c(s["min_segment_mm"])
        self.d005_side = c(s["line005_side_offset_mm"])
        self.d005_bottom = c(s["line005_bottom_offset_mm"])
        self.d006_side = c(s["line006_side_offset_mm"])
        self.d006_gap = c(s["line006_above_005_mm"])
        self.d008_offset = c(s["line008_offset_mm"])
        self.d008_top_inset = c(s["line008_top_inset_from_006_mm"])
        self.d010_below = c(s["point010_below_mm"])
        self.min_area = c(10.0) * c(10.0)
        self.max_visible_nodes = 90
