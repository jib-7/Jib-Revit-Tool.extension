# -*- coding: utf-8 -*-
"""Finds the 026 Filled Region Type and the 005/006/008/010 families."""
from Autodesk.Revit.DB import (BuiltInCategory, FamilyPlacementType, FamilySymbol,
                               FilledRegionType, FilteredElementCollector)

from .revit_utils import get_name, name_matches


class Resolved(object):
    def __init__(self):
        self.region_type = None
        self.symbols = {}      # role -> FamilySymbol
        self.errors = []
        self.warnings = []


def _symbol_label(sym):
    return "%s : %s" % (get_name(sym.Family), get_name(sym))


def find_region_types(doc, token):
    return [t for t in FilteredElementCollector(doc).OfClass(FilledRegionType)
            if name_matches(get_name(t), token)]


def find_detail_symbols(doc, token):
    out = []
    col = FilteredElementCollector(doc).OfClass(FamilySymbol).OfCategory(BuiltInCategory.OST_DetailComponents)
    for sym in col:
        if name_matches(get_name(sym.Family), token) or name_matches(get_name(sym), token):
            out.append(sym)
    return out


def _choose(options, labels, title, chooser, warnings, what):
    if len(options) == 1:
        return options[0]
    if chooser is not None:
        idx = chooser(labels, title)
        if idx is None:
            return None
        return options[idx]
    warnings.append("Several %s match; using '%s'." % (what, labels[0]))
    return options[0]


def resolve_all(doc, settings, chooser=None):
    """chooser(labels, title) -> index or None (cancel)."""
    res = Resolved()
    tok = settings["region_type_token"]
    types = find_region_types(doc, tok)
    if not types:
        res.errors.append("Missing Filled Region Type: no type whose name contains '%s'." % tok)
    else:
        labels = [get_name(t) for t in types]
        res.region_type = _choose(types, labels, "Select the '%s' Filled Region Type" % tok,
                                  chooser, res.warnings, "Filled Region Types")
        if res.region_type is None:
            res.errors.append("Selection of the '%s' Filled Region Type was cancelled." % tok)

    roles = [("005", settings["line005_token"], FamilyPlacementType.CurveBasedDetail, "line-based"),
             ("006", settings["line006_token"], FamilyPlacementType.CurveBasedDetail, "line-based"),
             ("008", settings["line008_token"], FamilyPlacementType.CurveBasedDetail, "line-based"),
             ("010", settings["point010_token"], FamilyPlacementType.ViewBased, "point-based")]
    for role, token, placement, kind in roles:
        syms = find_detail_symbols(doc, token)
        if not syms:
            res.errors.append("Missing %s Detail Item family: no Detail Item family or type contains '%s'."
                              % (kind, token))
            continue
        good = [s for s in syms if s.Family.FamilyPlacementType == placement]
        if not good:
            found = ", ".join("%s (%s)" % (_symbol_label(s), s.Family.FamilyPlacementType) for s in syms[:5])
            res.errors.append("'%s' families were found but none is %s: %s" % (token, kind, found))
            continue
        labels = [_symbol_label(s) for s in good]
        sym = _choose(good, labels, "Select the '%s' %s Detail Item type" % (token, kind),
                      chooser, res.warnings, "'%s' types" % token)
        if sym is None:
            res.errors.append("Selection of the '%s' type was cancelled." % token)
            continue
        res.symbols[role] = sym
    return res
