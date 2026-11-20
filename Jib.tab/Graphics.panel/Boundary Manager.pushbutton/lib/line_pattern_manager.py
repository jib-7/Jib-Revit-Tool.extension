# -*- coding: utf-8 -*-
"""Line patterns are read dynamically from the active document."""
from Autodesk.Revit.DB import FilteredElementCollector, LinePatternElement
from lib import revit_compat as rc
from lib.utils import MM_PER_FOOT


def _segments(lpe):
    out = []
    try:
        for s in lpe.GetLinePattern().GetSegments():
            out.append((str(s.Type), float(s.Length) * MM_PER_FOOT))
    except Exception:
        pass
    return out


def list_patterns(doc):
    sid = rc.solid_pattern_id(doc)
    first = {'name': 'Solid', 'id': sid, 'idv': rc.eid_value(sid), 'segments': []}
    seen = set([first['idv']])
    items = []
    try:
        col = FilteredElementCollector(doc).OfClass(rc.clr_type(LinePatternElement))
        for lpe in col:
            idv = rc.eid_value(lpe.Id)
            if idv in seen:
                continue
            seen.add(idv)
            items.append({'name': rc.el_name(lpe), 'id': lpe.Id, 'idv': idv,
                          'segments': _segments(lpe)})
    except Exception:
        pass
    items.sort(key=lambda p: p['name'].lower())
    return [first] + items


def index_by_idv(patterns):
    return dict((p['idv'], p) for p in patterns)


def find_by_name(patterns, name):
    n = (name or '').strip().lower()
    for p in patterns:
        if p['name'].lower() == n:
            return p
    return None


def find_by_idv(patterns, idv):
    for p in patterns:
        if p['idv'] == idv:
            return p
    return None
