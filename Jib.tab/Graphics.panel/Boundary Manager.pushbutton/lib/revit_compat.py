# -*- coding: utf-8 -*-
"""Revit 2024 / 2025 / 2026 compatibility helpers."""
import clr
from System import Int64
from Autodesk.Revit.DB import (ElementId, Element, FilteredElementCollector,
                               LinePatternElement)


def eid_value(eid):
    """Integer value of an ElementId (2024+ has .Value, older .IntegerValue)."""
    if eid is None:
        return -1
    try:
        return int(eid.Value)
    except AttributeError:
        return int(eid.IntegerValue)


def make_eid(v):
    try:
        return ElementId(Int64(int(v)))
    except Exception:
        return ElementId(int(v))


def is_valid_id(eid):
    return eid is not None and eid_value(eid) != -1


def el_name(el):
    if el is None:
        return ''
    try:
        return Element.Name.GetValue(el)
    except Exception:
        pass
    try:
        return el.Name
    except Exception:
        return ''


def revit_version(doc):
    try:
        return int(doc.Application.VersionNumber)
    except Exception:
        return 0


def clr_type(cls):
    try:
        return clr.GetClrType(cls)
    except Exception:
        return cls


def collector(doc, view=None):
    if view is not None:
        return FilteredElementCollector(doc, view.Id)
    return FilteredElementCollector(doc)


def solid_pattern_id(doc=None):
    try:
        return LinePatternElement.GetSolidPatternId()
    except Exception:
        pass
    if doc is not None:
        try:
            for lpe in FilteredElementCollector(doc).OfClass(clr_type(LinePatternElement)):
                if el_name(lpe).lower() == 'solid':
                    return lpe.Id
        except Exception:
            pass
    return ElementId.InvalidElementId
