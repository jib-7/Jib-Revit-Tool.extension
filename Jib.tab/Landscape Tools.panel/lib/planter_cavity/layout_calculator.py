# -*- coding: utf-8 -*-
"""Derives the 005 / 006 / 008 / 010 geometry from the 026 boundary loop.

The 026 Filled Region boundary is the single geometric master.  All results
are (u, v) coordinates in the active view plane, in internal units.
"""
from __future__ import division
import math

from .curve_offsetter import offset_path, simplify_polyline, check_polyline
from .models import GeometryError
from .point_in_polygon import point_in_polygon


class RegionMetrics(object):
    pass


class Layout(object):
    def __init__(self):
        self.metrics = None
        self.lines005 = []
        self.lines006 = []
        self.lines008 = []
        self.point010 = None
        self.warnings = []
        self.info = []


def _is_vertical(a, b, cfg):
    dx, dy = b[0] - a[0], b[1] - a[1]
    length = math.hypot(dx, dy)
    return length > 0 and abs(dx) <= length * math.sin(cfg.vert_tol)


def _is_horizontal(a, b, cfg):
    dx, dy = b[0] - a[0], b[1] - a[1]
    length = math.hypot(dx, dy)
    return length > 0 and abs(dy) <= length * math.sin(cfg.horiz_tol)


def _cyclic_runs(flags):
    n = len(flags)
    if all(flags):
        raise GeometryError("Cannot determine the top boundary of the region.")
    runs = []
    for s in range(n):
        if flags[s] and not flags[s - 1]:
            run = []
            i = s
            while flags[i % n]:
                run.append(i % n)
                i += 1
            runs.append(run)
    return runs


def analyze_region(loop, cfg):
    edges = loop.edges
    n = len(edges)
    m = RegionMetrics()
    m.u_min, m.v_min, m.u_max, m.v_max = loop.bbox()
    m.u_center = (m.u_min + m.u_max) / 2.0
    m.width = m.u_max - m.u_min
    m.height = m.v_max - m.v_min

    def elen(e):
        return math.hypot(e.b[0] - e.a[0], e.b[1] - e.a[1])

    # ---- top run -----------------------------------------------------
    flagged = [e.top for e in edges]
    if any(flagged):
        runs = _cyclic_runs(flagged)
        run = max(runs, key=lambda r: sum(elen(edges[i]) for i in r))
        v_ref = max(max(edges[i].a[1], edges[i].b[1]) for i in run)
        changed = True
        while changed:        # absorb adjacent horizontal edges at the same level
            changed = False
            for idx in (run[-1] + 1, run[0] - 1):
                j = idx % n
                if j in run:
                    continue
                e = edges[j]
                if (e.arc is None and _is_horizontal(e.a, e.b, cfg) and
                        min(e.a[1], e.b[1]) >= v_ref - cfg.level_tol):
                    if idx == run[-1] + 1:
                        run = run + [j]
                    else:
                        run = [j] + run
                    changed = True
                    break
    else:
        top_flags = [(edges[i].arc is None and _is_horizontal(edges[i].a, edges[i].b, cfg) and
                      min(edges[i].a[1], edges[i].b[1]) >= m.v_max - cfg.level_tol) for i in range(n)]
        if not any(top_flags):
            raise GeometryError(
                "The 026 boundary has no horizontal top edge. The top of a planter cavity must be "
                "horizontal (a closed gap at the top is created automatically).")
        runs = _cyclic_runs(top_flags)
        run = max(runs, key=lambda r: sum(elen(edges[i]) for i in r))
    m.top_run = run
    m.v_top = max(max(edges[i].a[1], edges[i].b[1]) for i in run)
    run_set = set(run)

    # ---- main inner walls ---------------------------------------------
    verts = []
    for i, e in enumerate(edges):
        if i in run_set or e.arc is not None:
            continue
        if _is_vertical(e.a, e.b, cfg):
            verts.append((i, (e.a[0] + e.b[0]) / 2.0, elen(e)))

    def main_wall(side_left):
        cand = [v for v in verts if (v[1] < m.u_center) == side_left]
        if not cand:
            return None
        cand.sort(key=lambda x: x[1])
        groups = [[cand[0]]]
        for c in cand[1:]:
            if abs(c[1] - groups[-1][-1][1]) <= cfg.level_tol:
                groups[-1].append(c)
            else:
                groups.append([c])
        best = max(groups, key=lambda g: sum(x[2] for x in g))
        tot = sum(x[2] for x in best)
        u = sum(x[1] * x[2] for x in best) / tot
        return {'u': u, 'edges': set(x[0] for x in best), 'length': tot}

    m.left = main_wall(True)
    m.right = main_wall(False)
    if m.left is None or m.right is None:
        raise GeometryError(
            "Could not find a vertical main inner wall on both sides of the 026 region "
            "(vertical tolerance %.1f deg)." % math.degrees(cfg.vert_tol))
    m.warnings = []

    # ---- bottom -------------------------------------------------------
    hz = [(min(e.a[1], e.b[1]) + max(e.a[1], e.b[1])) / 2.0 for i, e in enumerate(edges)
          if i not in run_set and e.arc is None and _is_horizontal(e.a, e.b, cfg)]
    if hz:
        m.v_bottom = min(hz)
    else:
        m.v_bottom = m.v_min
        m.warnings.append("No horizontal bottom edge found; the lowest point of 026 was used.")

    # ---- open path (all edges except the top run), CCW from top-left ---
    r1 = run[-1]
    order = [(r1 + 1 + k) % n for k in range(n - len(run))]
    m.path_edges = order
    m.path_points = [edges[order[0]].a] + [edges[i].b for i in order]
    return m


def compute_layout(loop, cfg):
    m = analyze_region(loop, cfg)
    lay = Layout()
    lay.metrics = m
    lay.warnings.extend(m.warnings)
    uL, uR = m.left['u'], m.right['u']
    vt = m.v_top

    # ---- 005 ----------------------------------------------------------
    uL5, uR5 = uL - cfg.d005_side, uR + cfg.d005_side
    vB5 = m.v_bottom - cfg.d005_bottom
    lay.lines005 = [((uL5, vt), (uL5, vB5)), ((uL5, vB5), (uR5, vB5)), ((uR5, vB5), (uR5, vt))]

    # ---- 006 ----------------------------------------------------------
    uL6, uR6 = uL - cfg.d006_side, uR + cfg.d006_side
    vB6 = vB5 + cfg.d006_gap
    lay.lines006 = [((uL6, vt), (uL6, vB6)), ((uL6, vB6), (uR6, vB6)), ((uR6, vB6), (uR6, vt))]

    # ---- 008 ----------------------------------------------------------
    edges = loop.edges
    order = m.path_edges
    overrides = {}
    first, last = order[0], order[-1]
    ef, el = edges[first], edges[last]
    if (ef.arc is None and _is_vertical(ef.a, ef.b, cfg) and first not in m.left['edges']
            and (ef.a[0] + ef.b[0]) / 2.0 < m.u_center):
        overrides[0] = uL6 + cfg.d008_top_inset
        lay.info.append("008: top short vertical portion on the left placed %.1f mm inside 006."
                        % (cfg.d008_top_inset * 304.8))
    else:
        lay.info.append("008: no distinct short vertical portion at the top-left; normal offset used.")
    if (el.arc is None and _is_vertical(el.a, el.b, cfg) and last not in m.right['edges']
            and (el.a[0] + el.b[0]) / 2.0 >= m.u_center):
        overrides[len(order) - 1] = uR6 - cfg.d008_top_inset
        lay.info.append("008: top short vertical portion on the right placed %.1f mm inside 006."
                        % (cfg.d008_top_inset * 304.8))
    else:
        lay.info.append("008: no distinct short vertical portion at the top-right; normal offset used.")
    raw = offset_path(m.path_points, cfg.d008_offset, vt, overrides, cfg.min_seg)
    pts = simplify_polyline(raw, cfg.min_seg, cfg.snap_tol)
    check_polyline(pts, cfg.snap_tol * 0.5)
    if len(pts) < 2:
        raise GeometryError("008 offset geometry is empty.")
    # all vertices except those of overridden edges must lie inside / on 026
    poly = loop.points
    skip = set()
    if 0 in overrides:
        skip.update([0, 1])
    if (len(order) - 1) in overrides:
        skip.update([len(raw) - 1, len(raw) - 2])
    raw_ok = []
    for i, p in enumerate(raw):
        if i in skip:
            continue
        if point_in_polygon(p, poly, cfg.snap_tol * 2.0) < 0:
            raise GeometryError("The 008 offset moved outside the 026 region; the cavity is too narrow "
                                "or has features smaller than the offset.")
        raw_ok.append(p)
    lay.lines008 = [(pts[i], pts[i + 1]) for i in range(len(pts) - 1)]

    # ---- 010 ----------------------------------------------------------
    lay.point010 = (m.u_center, m.v_bottom - cfg.d010_below)
    return lay
