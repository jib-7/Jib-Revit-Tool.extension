# -*- coding: utf-8 -*-
"""Read-only audit of Filled Region boundary graphics, plus style usage scan."""
from Autodesk.Revit.DB import CurveElement, BuiltInCategory
from lib import revit_compat as rc, filled_region_manager as frm, boundary_manager as bm
from lib import batch_replace as br, colour_manager as cm
from lib import line_weight_manager as lwm


def run_audit(doc, scope, view, selected_ids, pat_idx, unwanted_names=None):
    """One row per (region, boundary style)."""
    unwanted = set(n.strip().lower() for n in (unwanted_names or []) if n.strip())
    rows = []
    cache = {}
    for r in br.regions_for_scope(doc, scope, selected_ids, view):
        tname = frm.type_name(doc, r)
        groups = {}
        for s in bm.get_segments(doc, r):
            info = bm.segment_style_info(doc, s, pat_idx, cache)
            g = groups.setdefault(info['gs_idv'], [info, 0])
            g[1] += 1
        if not groups:
            rows.append({'region': rc.eid_value(r.Id), 'type': tname, 'style': '(no boundary found)',
                         'weight': '', 'mm': '', 'hex': '', 'pattern': '', 'segments': 0,
                         'flag': ''})
        for info, n in groups.values():
            flag = 'UNWANTED' if info['name'].lower() in unwanted else ''
            rows.append({'region': rc.eid_value(r.Id), 'type': tname, 'style': info['name'],
                         'weight': info['weight'] if info['weight'] is not None else '',
                         'mm': lwm.mm_for(info['weight']) if info['weight'] else '',
                         'hex': info['hex'], 'pattern': info['pattern_name'],
                         'segments': n, 'flag': flag})
    rows.sort(key=lambda x: (x['style'].lower(), x['region']))
    return rows


def usage_scan(doc, gs_idv):
    """Who uses a style? Returns dict: fr (list of (region, seg)), other (list of
    curve ids that are NOT filled-region boundaries), regions (set)."""
    fr_pairs, fr_seg_ids, regions = [], set(), set()
    for r in frm.regions_in_project(doc):
        for s in bm.get_segments(doc, r):
            try:
                if rc.eid_value(s.LineStyle.Id) == gs_idv:
                    fr_pairs.append((rc.eid_value(r.Id), rc.eid_value(s.Id)))
                    fr_seg_ids.add(rc.eid_value(s.Id))
                    regions.add(rc.eid_value(r.Id))
            except Exception:
                continue
    other = []
    try:
        col = rc.collector(doc).OfClass(rc.clr_type(CurveElement)).WhereElementIsNotElementType()
    except Exception:
        col = rc.collector(doc).OfCategory(BuiltInCategory.OST_Lines).WhereElementIsNotElementType()
    for e in col:
        try:
            idv = rc.eid_value(e.Id)
            if idv in fr_seg_ids:
                continue
            if rc.eid_value(e.LineStyle.Id) == gs_idv:
                other.append(idv)
        except Exception:
            continue
    return {'fr': fr_pairs, 'other': other, 'regions': regions}
