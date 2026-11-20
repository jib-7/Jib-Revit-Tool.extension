# -*- coding: utf-8 -*-
"""Replace one boundary Line Style by another on Filled Region boundaries only.
Detail Lines / Model Lines that are not Filled Region boundaries are never touched."""
from lib import revit_compat as rc, filled_region_manager as frm, boundary_manager as bm

SCOPE_SELECTION, SCOPE_VIEW, SCOPE_PROJECT = 'selection', 'view', 'project'


def regions_for_scope(doc, scope, selected_ids, view):
    if scope == SCOPE_SELECTION:
        out = []
        for i in selected_ids:
            r = frm.get_region(doc, i)
            if r is not None:
                out.append(r)
        return out
    if scope == SCOPE_VIEW:
        return frm.regions_in_view(doc, view)
    return frm.regions_in_project(doc)


def find_targets(doc, from_gs_idv, scope, selected_ids, view):
    """Returns (targets, n_regions_scanned, n_regions_affected, n_boundaries)."""
    regions = regions_for_scope(doc, scope, selected_ids, view)
    targets = []
    nb = 0
    for r in regions:
        ids = []
        for s in bm.get_segments(doc, r):
            try:
                if rc.eid_value(s.LineStyle.Id) == from_gs_idv:
                    ids.append(rc.eid_value(s.Id))
            except Exception:
                continue
        if ids:
            targets.append((rc.eid_value(r.Id), ids))
            nb += len(ids)
    return targets, len(regions), len(targets), nb
