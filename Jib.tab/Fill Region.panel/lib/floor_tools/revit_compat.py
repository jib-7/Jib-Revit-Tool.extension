# -*- coding: utf-8 -*-
"""Revit API compatibility layer.

EVERYTHING that differs between Revit versions (or between the IronPython and
CPython engines) lives here, so the geometry and workflow modules stay
version-independent.

Known differences handled in this module:

* ElementId: ``IntegerValue`` (<= 2023, int) vs ``Value`` (>= 2024, Int64).
* Units: ``UnitType`` / ``DisplayUnitType`` (<= 2021) vs ``SpecTypeId`` /
  ``ForgeTypeId`` (>= 2021/2022; the old enums were removed in 2022).
* ``Element.Name`` property lookup problems on some ElementTypes in IronPython.
* ``ElementClassFilter`` needs a System.Type (``clr.GetClrType`` in IronPython).
"""
from __future__ import division

import re

import System
from System.Collections.Generic import List
from Autodesk.Revit import DB

try:
    import clr
except ImportError:  # pragma: no cover
    clr = None

from floor_tools import settings


# --------------------------------------------------------------- version ----
def get_revit_version():
    """Major Revit version as int (e.g. 2024); 0 if it cannot be determined."""
    try:
        from pyrevit import HOST_APP
        return int(HOST_APP.version)
    except Exception:
        return 0


REVIT_VERSION = get_revit_version()
USES_INT64_ELEMENT_IDS = REVIT_VERSION >= 2024
HAS_FORGE_UNIT_API = hasattr(DB, "SpecTypeId")
HAS_TOPOSOLID = hasattr(DB, "Toposolid")          # class introduced in Revit 2024


def check_version():
    """Return (ok, message). ok=False blocks the command; message may be a note."""
    if REVIT_VERSION and REVIT_VERSION < settings.MIN_REVIT_VERSION:
        return False, ("Revit {} is older than the minimum supported version ({})."
                       .format(REVIT_VERSION, settings.MIN_REVIT_VERSION))
    if REVIT_VERSION > settings.MAX_TESTED_REVIT_VERSION:
        note = ("Revit {} is newer than the latest tested version ({}). "
                "The tool will run, but please verify the results.".format(
                    REVIT_VERSION, settings.MAX_TESTED_REVIT_VERSION))
        return settings.ALLOW_UNTESTED_NEWER_VERSIONS, note
    return True, ""


# ----------------------------------------------------------- generic helpers -
def clr_type(cls):
    """System.Type for a Revit API class (IronPython needs clr.GetClrType)."""
    if clr is not None and hasattr(clr, "GetClrType"):
        return clr.GetClrType(cls)
    return cls


def to_clr_list(items, cls):
    """Python iterable -> System.Collections.Generic.List[cls]."""
    result = List[cls]()
    for item in items:
        result.Add(item)
    return result


def element_id_value(element_id):
    """Numeric ElementId value on every Revit version."""
    try:
        return int(element_id.Value)          # Revit 2024+ (Int64)
    except AttributeError:
        return int(element_id.IntegerValue)   # Revit <= 2023


def make_element_id(value):
    """Build an ElementId from a number on every Revit version."""
    if USES_INT64_ELEMENT_IDS:
        return DB.ElementId(System.Int64(value))
    return DB.ElementId(int(value))


def element_name(element):
    """Element.Name that also works for ElementTypes under IronPython."""
    try:
        return element.Name
    except Exception:
        pass
    try:
        return DB.Element.Name.GetValue(element)      # IronPython
    except Exception:
        pass
    try:
        return DB.Element.Name.__get__(element)       # pythonnet / CPython
    except Exception:
        return "<unnamed>"


def supported_element_classes():
    """Element classes the tool converts: Floors, plus Toposolids on Revit 2024+."""
    if HAS_TOPOSOLID:
        return (DB.Floor, DB.Toposolid)
    return (DB.Floor,)


def is_supported_element(element):
    return isinstance(element, supported_element_classes())


def is_toposolid(element):
    return HAS_TOPOSOLID and isinstance(element, DB.Toposolid)


def element_kind(element):
    return "Toposolid" if is_toposolid(element) else "Floor"


def short_curve_tolerance(application):
    """Shortest curve length Revit accepts (feet)."""
    return application.ShortCurveTolerance


def get_view_plane(view):
    """(origin, unit normal) of the plane a Filled Region in this view lives on."""
    return view.Origin, view.ViewDirection.Normalize()


def get_link_transform(link_instance):
    """Transform from a linked model's coordinates to the host model's."""
    try:
        return link_instance.GetTotalTransform()      # includes shared-coordinate placement
    except Exception:
        return link_instance.GetTransform()


def get_sketch_ids(floor):
    """ElementIds of the Sketch(es) the Floor depends on (version independent)."""
    try:
        return list(floor.GetDependentElements(DB.ElementClassFilter(clr_type(DB.Sketch))))
    except Exception:
        return []


def get_material_patterns(material, source):
    """(fg pattern id, fg colour, bg pattern id, bg colour) of a Material.

    source is settings.PATTERN_SOURCE_SURFACE or PATTERN_SOURCE_CUT. The
    foreground/background split exists since Revit 2019, so it is available on
    every supported version; missing members yield None instead of raising.
    """
    prefix = "Cut" if source == settings.PATTERN_SOURCE_CUT else "Surface"

    def read(suffix):
        try:
            return getattr(material, prefix + suffix)
        except Exception:
            return None

    return (read("ForegroundPatternId"), read("ForegroundPatternColor"),
            read("BackgroundPatternId"), read("BackgroundPatternColor"))


# ----------------------------------------------------------------- units ----
def _length_spec():
    if HAS_FORGE_UNIT_API:
        return DB.SpecTypeId.Length
    return DB.UnitType.UT_Length


def _length_display_unit(doc):
    """The project's length unit (ForgeTypeId >= 2021/22, DisplayUnitType before)."""
    options = doc.GetUnits().GetFormatOptions(_length_spec())
    if hasattr(options, "GetUnitTypeId"):
        return options.GetUnitTypeId()
    return options.DisplayUnits


def length_unit_label(doc):
    """Human readable project length unit, '' if unavailable."""
    try:
        unit = _length_display_unit(doc)
        if hasattr(DB.LabelUtils, "GetLabelForUnit"):
            return DB.LabelUtils.GetLabelForUnit(unit)
        return DB.LabelUtils.GetLabelFor(unit)
    except Exception:
        return ""


def format_length(doc, feet):
    """Format an internal length (feet) using the project's units."""
    try:
        return DB.UnitFormatUtils.Format(doc.GetUnits(), _length_spec(), feet, False)
    except Exception:
        return "{:.4f} ft".format(feet)


def _unpack_try(result):
    if isinstance(result, tuple):
        return bool(result[0]), result[1]
    return bool(result), None


_TOKEN_TO_METERS = {"mm": 0.001, "cm": 0.01, "m": 1.0, "ft": 0.3048, "'": 0.3048,
                    "in": 0.0254, '"': 0.0254}
_METERS_PER_FOOT = 0.3048


def _fallback_parse(doc, text):
    """Very small parser used only if Revit's own parser rejects the text."""
    match = re.match(r"^\s*([-+]?\d+(?:[.,]\d+)?)\s*([a-zA-Z'\"]*)\s*$", text)
    if not match:
        return None
    number = float(match.group(1).replace(",", "."))
    token = match.group(2).lower()
    if not token:  # bare number = project unit
        try:
            return DB.UnitUtils.ConvertToInternalUnits(number, _length_display_unit(doc))
        except Exception:
            return None
    if token not in _TOKEN_TO_METERS:
        return None
    return number * _TOKEN_TO_METERS[token] / _METERS_PER_FOOT


def parse_length(doc, text):
    """User text -> internal feet, honouring project units. None if invalid.

    A bare number is interpreted in the project length unit; text such as
    '25 mm' or '1 1/2"' is understood by Revit's own unit parser.
    """
    text = (text or "").strip()
    if not text:
        return 0.0
    try:
        ok, value = _unpack_try(DB.UnitFormatUtils.TryParse(doc.GetUnits(), _length_spec(), text))
        if ok:
            return float(value)
    except Exception:
        pass
    return _fallback_parse(doc, text)
