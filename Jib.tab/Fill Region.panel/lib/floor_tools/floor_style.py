# -*- coding: utf-8 -*-
"""Floor appearance -> Filled Region Type.

A Floor has no fill pattern of its own: what is drawn comes from the materials
of its FloorType layers (Material > Surface/Cut Pattern, foreground and
background, each with a colour). This module reads those values from the
top-most layer that defines a pattern and copies them to a Filled Region Type
named after the Floor type. Existing types are reused, never modified.
"""
import re

from Autodesk.Revit import DB

from floor_tools import revit_compat as compat

_ILLEGAL_NAME_CHARS = re.compile(r'[\\:{}\[\]|;<>?`~]')   # characters Revit forbids in names


class FloorStyle(object):
    def __init__(self, name, fg_pattern_id=None, fg_color=None, bg_pattern_id=None,
                 bg_color=None, warnings=None):
        self.name = name
        self.fg_pattern_id = fg_pattern_id
        self.fg_color = fg_color
        self.bg_pattern_id = bg_pattern_id
        self.bg_color = bg_color
        self.warnings = warnings or []
        self.source_doc = None          # document the pattern ids belong to (may be a link)


def _valid_id(element_id):
    return element_id is not None and compat.element_id_value(element_id) != -1


def _valid_color(color):
    try:
        return color is not None and color.IsValid
    except Exception:
        return False


def sanitize_name(name):
    cleaned = _ILLEGAL_NAME_CHARS.sub("_", name or "").strip()
    return cleaned or "Floor"


def _layer_materials(doc, floor_type):
    """Materials of the type's layers, ordered top (finish) to bottom."""
    materials = []
    structure = floor_type.GetCompoundStructure()
    if structure is None:
        return materials
    for layer in structure.GetLayers():
        if _valid_id(layer.MaterialId):
            material = doc.GetElement(layer.MaterialId)
            if material is not None:
                materials.append(material)
    return materials


def read_floor_style(floor, source):
    """Appearance of the Floor's type. Never raises for missing materials."""
    doc = floor.Document
    floor_type = doc.GetElement(floor.GetTypeId())
    name = sanitize_name(compat.element_name(floor_type))
    warnings = []
    try:
        materials = _layer_materials(doc, floor_type)
    except Exception:
        materials = []
    if not materials:
        warnings.append("Floor type '{}' has no layer material; the selected base type's "
                        "appearance was used.".format(name))
        style = FloorStyle(name, warnings=warnings)
        style.source_doc = doc
        return style

    chosen = None
    for material in materials:                       # first layer that defines a pattern
        patterns = compat.get_material_patterns(material, source)
        if _valid_id(patterns[0]) or _valid_id(patterns[2]):
            chosen = patterns
            break
    if chosen is None:
        chosen = compat.get_material_patterns(materials[0], source)
        warnings.append("No layer material of '{}' defines a pattern for this source; only "
                        "colours were copied where available.".format(name))
    style = FloorStyle(name, chosen[0], chosen[1], chosen[2], chosen[3], warnings)
    style.source_doc = doc
    return style


def _host_pattern_id(host_doc, source_doc, pattern_id, warnings):
    """Fill pattern id valid in the HOST document.

    Pattern ElementIds are per document, so a pattern of a linked model is
    matched by name and target (Drafting/Model) in the host; if the host lacks
    it, the pattern definition is copied into the host.
    """
    if not _valid_id(pattern_id):
        return None
    if source_doc is None or not source_doc.IsLinked:
        return pattern_id
    try:
        element = source_doc.GetElement(pattern_id)
        pattern = element.GetFillPattern()
        if pattern.IsSolidFill:      # "Solid fill" is localized: match by property, not name
            for candidate in DB.FilteredElementCollector(host_doc).OfClass(DB.FillPatternElement):
                host_pattern = candidate.GetFillPattern()
                if host_pattern.IsSolidFill and host_pattern.Target == pattern.Target:
                    return candidate.Id
        existing = DB.FillPatternElement.GetFillPatternElementByName(
            host_doc, pattern.Target, pattern.Name)
        if existing is not None:
            return existing.Id
        return DB.FillPatternElement.Create(host_doc, pattern).Id
    except Exception as ex:
        warnings.append("Pattern of the linked Floor could not be brought into this project ({})."
                        .format(str(ex).splitlines()[0] if str(ex) else "rejected by Revit"))
        return None


def get_or_create_region_type(doc, base_type, style, types_by_name):
    """Return (type ElementId, created, warnings).

    Needs an open transaction. types_by_name ({name: FilledRegionType}) is
    updated in place so later floors of the same type reuse the new type.
    """
    existing = types_by_name.get(style.name)
    if existing is not None:
        return existing.Id, False, []

    warnings = []
    region_type = doc.GetElement(base_type.Duplicate(style.name).Id)

    def apply(prop, value):
        try:
            setattr(region_type, prop, value)
        except Exception as ex:                      # e.g. pattern not usable in regions
            warnings.append("Could not set {} on '{}' ({}).".format(
                prop, style.name, str(ex).splitlines()[0] if str(ex) else "rejected by Revit"))

    fg_pattern = _host_pattern_id(doc, style.source_doc, style.fg_pattern_id, warnings)
    bg_pattern = _host_pattern_id(doc, style.source_doc, style.bg_pattern_id, warnings)
    if fg_pattern is not None:
        apply("ForegroundPatternId", fg_pattern)
    if _valid_color(style.fg_color):
        apply("ForegroundPatternColor", style.fg_color)
    if bg_pattern is not None:
        apply("BackgroundPatternId", bg_pattern)
    if _valid_color(style.bg_color):
        apply("BackgroundPatternColor", style.bg_color)

    types_by_name[style.name] = region_type
    return region_type.Id, True, warnings
