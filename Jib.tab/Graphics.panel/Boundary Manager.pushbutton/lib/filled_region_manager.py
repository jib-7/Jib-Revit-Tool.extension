# -*- coding: utf-8 -*-
"""Native Filled Regions of the active document only (never links)."""
from Autodesk.Revit.DB import FilledRegion, FilledRegionType
from lib import revit_compat as rc, boundary_manager as bm


def is_filled_region(el):
    return isinstance(el, FilledRegion)


def get_region(doc, idv):
    try:
        el = doc.GetElement(rc.make_eid(idv))
    except Exception:
        return None
    return el if isinstance(el, FilledRegion) else None


def type_name(doc, region):
    try:
        return rc.el_name(doc.GetElement(region.GetTypeId()))
    except Exception:
        return '?'


def regions_in_view(doc, view):
    try:
        return list(rc.collector(doc, view).OfClass(rc.clr_type(FilledRegion)).WhereElementIsNotElementType())
    except Exception:
        return []


def regions_in_project(doc):
    return list(rc.collector(doc).OfClass(rc.clr_type(FilledRegion)).WhereElementIsNotElementType())


def region_types(doc):
    out = []
    for t in rc.collector(doc).OfClass(rc.clr_type(FilledRegionType)):
        out.append((rc.el_name(t), rc.eid_value(t.Id)))
    out.sort(key=lambda x: x[0].lower())
    return out


def filter_by_type(doc, regions, tname):
    return [r for r in regions if type_name(doc, r) == tname]


def summarize(doc, region, pat_idx, cache):
    segs = []
    for s in bm.get_segments(doc, region):
        gtype, length = bm.describe_geometry(s)
        segs.append({'seg_idv': rc.eid_value(s.Id), 'geom': gtype, 'len_mm': length,
                     'style': bm.segment_style_info(doc, s, pat_idx, cache)})
    names = []
    for sg in segs:
        n = sg['style']['name']
        if n not in names:
            names.append(n)
    return {'id': rc.eid_value(region.Id), 'type': type_name(doc, region),
            'segments': segs, 'style_names': names}
