# -*- coding: utf-8 -*-
"""Places line-based and point-based detail items in the active view."""
from Autodesk.Revit.DB import FamilyPlacementType, Line

from .models import FamilyError, GeometryError, dist
from .revit_utils import get_name, to_xyz


def ensure_active(doc, symbol):
    if not symbol.IsActive:
        symbol.Activate()
        doc.Regenerate()


def check_placement(symbol, expected):
    actual = symbol.Family.FamilyPlacementType
    if actual != expected:
        raise FamilyError("Family '%s' has placement type %s, expected %s."
                          % (get_name(symbol.Family), actual, expected))


def place_line(doc, view, symbol, frame, p_uv, q_uv, min_len):
    """One line-based family instance along p -> q (a single straight reference line)."""
    check_placement(symbol, FamilyPlacementType.CurveBasedDetail)
    if dist(p_uv, q_uv) < min_len:
        raise GeometryError("A %s line is shorter than the minimum curve length." % get_name(symbol.Family))
    line = Line.CreateBound(to_xyz(frame, p_uv), to_xyz(frame, q_uv))
    inst = doc.Create.NewFamilyInstance(line, symbol, view)
    if inst is None:
        raise FamilyError("Revit did not place '%s'." % get_name(symbol.Family))
    return inst


def place_polyline(doc, view, symbol, frame, segments, min_len):
    """A connected polyline = one line-based instance per straight segment."""
    return [place_line(doc, view, symbol, frame, a, b, min_len) for (a, b) in segments]


def place_point(doc, view, symbol, frame, uv):
    check_placement(symbol, FamilyPlacementType.ViewBased)
    inst = doc.Create.NewFamilyInstance(to_xyz(frame, uv), symbol, view)
    if inst is None:
        raise FamilyError("Revit did not place '%s'." % get_name(symbol.Family))
    return inst


def inspect_family(doc, family):
    """Best-effort look inside a line-based family. Returns a dict (never raises)."""
    info = {'placement': str(family.FamilyPlacementType), 'ok': True, 'notes': []}
    fam_doc = None
    try:
        from Autodesk.Revit.DB import (CurveElement, FilteredElementCollector, FilledRegion,
                                       ReferencePlane)
        fam_doc = doc.EditFamily(family)
        curves = list(FilteredElementCollector(fam_doc).OfClass(CurveElement))
        ref_lines = 0
        for c in curves:
            try:
                if c.IsReferenceLine:
                    ref_lines += 1
            except Exception:
                pass
        info['reference_lines'] = ref_lines
        info['curve_elements'] = len(curves)
        info['filled_regions'] = len(list(FilteredElementCollector(fam_doc).OfClass(FilledRegion)))
        info['reference_planes'] = len(list(FilteredElementCollector(fam_doc).OfClass(ReferencePlane)))
    except Exception as ex:
        info['notes'].append("Family contents could not be inspected (%s)." % ex)
    finally:
        try:
            if fam_doc is not None:
                fam_doc.Close(False)
        except Exception:
            pass
    return info
