# -*- coding: utf-8 -*-
"""Orchestrates boundary detection around a clicked point (pure Python)."""
from __future__ import division

from .curve_graph import build_graph
from .gap_closer import find_closures
from .geometry_validator import clean_loop, validate_loop
from .loop_detector import find_loops, loops_containing
from .models import dist


class DetectionResult(object):
    def __init__(self):
        self.status = 'fail'        # 'ok' | 'ambiguous' | 'fail'
        self.candidates = []        # list of BoundaryLoop
        self.messages = []
        self.stats = {}


def _in_window(prim, center, radius, cfg):
    pts = prim.bbox_points(cfg.arc_tol)
    for p in pts:
        if dist(p, center) <= radius:
            return True
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return (min(xs) - radius <= center[0] <= max(xs) + radius and
            min(ys) - radius <= center[1] <= max(ys) + radius)


def detect(primitives, pick_uv, cfg):
    res = DetectionResult()
    window = max(cfg.search_radius, cfg.max_top_gap) * 1.5
    prims = [p for p in primitives if _in_window(p, pick_uv, window, cfg)]
    res.stats['primitives_total'] = len(primitives)
    res.stats['primitives_in_window'] = len(prims)
    if not prims:
        res.messages.append("No detail lines or detail-component curves were found near the clicked point.")
        return res
    graph = build_graph(prims, cfg.snap_tol, cfg.arc_tol)
    res.stats['nodes'] = len(graph.nodes)
    res.stats['edges'] = len(graph.edges)
    res.stats['dangling_ends'] = len(graph.dangling_nodes())
    hits = loops_containing(find_loops(graph, cfg.min_area), pick_uv, 0.0)
    raw = []
    if hits:
        res.stats['mode'] = 'closed loop (no gaps closed)'
        raw = [hits[0]]
    else:
        res.stats['mode'] = 'gap closure'
        sols = find_closures(graph, pick_uv, cfg)
        raw = [s.loop for s in sols]
        if not sols:
            res.messages.append(
                "The clicked point is not enclosed and no gap closure within the configured "
                "limits (max gap %.0f mm, max top gap %.0f mm) could enclose it. "
                "Check that you clicked inside the soil area or increase the gap limits."
                % (cfg.raw['max_gap_mm'], cfg.raw['max_top_gap_mm']))
            return res
    cleaned = []
    for lp in raw:
        try:
            c = clean_loop(lp, cfg)
        except Exception as ex:   # pragma: no cover
            res.messages.append("Rejected a candidate loop: %s" % ex)
            continue
        errs = validate_loop(c, cfg)
        if errs:
            res.messages.append("Rejected a candidate loop: " + "; ".join(errs))
            continue
        cleaned.append(c)
    if not cleaned:
        res.messages.append("The detected boundary is not a valid closed loop.")
        return res
    res.candidates = cleaned
    res.status = 'ok' if len(cleaned) == 1 else 'ambiguous'
    return res
