# -*- coding: utf-8 -*-
"""Filled Region boundary segments.

API facts used here:
* FilledRegion.GetBoundaries() returns CurveLoops (geometry only, NO line style).
* The boundary segments exist as dependent CurveElements of the region
  (FilledRegion.GetDependentElements). Each one carries a GraphicsStyle
  (CurveElement.LineStyle). Changing that style does not touch geometry,
  so SetBoundaries() (which rebuilds the sketch) is deliberately NOT used.
* Every segment is addressed by its own ElementId, which makes individual
  segment editing reliable.
"""
from Autodesk.Revit.DB import (CurveElement, ElementClassFilter, BuiltInCategory,
                               ElementCategoryFilter, SubTransaction, BuiltInParameter)
from lib import revit_compat as rc, line_style_manager as lsm
from lib.utils import MM_PER_FOOT


def get_segments(doc, region):
    ids = None
    for flt in (None, 'class', 'cat'):
        try:
            if flt is None:
                ids = region.GetDependentElements(None)
            elif flt == 'class':
                ids = region.GetDependentElements(ElementClassFilter(rc.clr_type(CurveElement)))
            else:
                ids = region.GetDependentElements(ElementCategoryFilter(BuiltInCategory.OST_Lines))
            break
        except Exception:
            ids = None
    segs = []
    if ids is None:
        return segs
    for i in ids:
        try:
            e = doc.GetElement(i)
            if isinstance(e, CurveElement):
                segs.append(e)
        except Exception:
            continue
    segs.sort(key=lambda s: rc.eid_value(s.Id))
    return segs


def segment_style_info(doc, seg, pat_idx, cache=None):
    try:
        gs = seg.LineStyle
    except Exception:
        gs = None
    return lsm.info_from_graphics_style(doc, gs, pat_idx, cache)


def describe_geometry(seg):
    try:
        c = seg.GeometryCurve
        return c.GetType().Name, c.Length * MM_PER_FOOT
    except Exception:
        return '?', 0.0


def set_segment_style(seg, gs):
    """Returns (ok, message). Verifies the result."""
    err = ''
    try:
        seg.LineStyle = gs
        if rc.eid_value(seg.LineStyle.Id) == rc.eid_value(gs.Id):
            return True, ''
        err = 'LineStyle did not change.'
    except Exception as ex:
        err = str(ex)
    try:
        p = seg.get_Parameter(BuiltInParameter.BUILDING_CURVE_GSTYLE)
        if p is not None and not p.IsReadOnly:
            p.Set(gs.Id)
            if rc.eid_value(seg.LineStyle.Id) == rc.eid_value(gs.Id):
                return True, ''
    except Exception as ex:
        err = err + ' / ' + str(ex)
    return False, err or 'Unsupported boundary curve.'


def apply_style_to_targets(doc, targets, gs, pat_idx):
    """Must be called inside an open Transaction.

    targets: list of (region_idv, [segment_idv, ...] or None for all).
    One SubTransaction per region: a failure rolls back that whole region so
    no region is ever left half-changed.
    """
    res = {'regions': 0, 'segments': 0, 'updated': 0, 'failed': 0, 'skipped': 0,
           'failures': [], 'originals': {}, 'updated_regions': 0}
    new_idv = rc.eid_value(gs.Id)
    cache = {}
    for region_idv, seg_ids in targets:
        region = doc.GetElement(rc.make_eid(region_idv))
        if region is None:
            res['failed'] += len(seg_ids or [])
            res['failures'].append((region_idv, 0, 'Filled Region not found.'))
            continue
        all_segs = get_segments(doc, region)
        if seg_ids is not None:
            wanted = set(seg_ids)
            segs = [s for s in all_segs if rc.eid_value(s.Id) in wanted]
        else:
            segs = all_segs
        res['regions'] += 1
        res['segments'] += len(segs)
        todo = []
        for s in segs:
            info = segment_style_info(doc, s, pat_idx, cache)
            ent = res['originals'].setdefault(info['gs_idv'], {'info': info, 'count': 0})
            ent['count'] += 1
            if info['gs_idv'] == new_idv:
                res['skipped'] += 1
            else:
                todo.append(s)
        if not todo:
            continue
        sub = SubTransaction(doc)
        sub.Start()
        bad = None
        try:
            for s in todo:
                ok, msg = set_segment_style(s, gs)
                if not ok:
                    bad = (rc.eid_value(s.Id), msg)
                    break
        except Exception as ex:
            bad = (0, str(ex))
        if bad is None:
            sub.Commit()
            res['updated'] += len(todo)
            res['updated_regions'] += 1
        else:
            sub.RollBack()
            res['failed'] += len(todo)
            res['failures'].append((region_idv, bad[0], bad[1]))
    return res
