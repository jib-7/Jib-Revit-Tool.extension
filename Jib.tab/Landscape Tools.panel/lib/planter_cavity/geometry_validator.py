# -*- coding: utf-8 -*-
"""Loop clean-up and validation (pure Python)."""
from __future__ import division
import math

from .models import (BoundaryLoop, LoopEdge, GeometryError, dist, point_seg_dist,
                     seg_intersects, signed_area)


def clean_loop(loop, cfg):
    """Remove tiny edges and merge collinear straight edges."""
    edges = [LoopEdge(e.a, e.b, e.arc, e.synthetic, e.top) for e in loop.edges]
    guard = 0
    changed = True
    while changed and len(edges) > 3 and guard < 10000:
        guard += 1
        changed = False
        n = len(edges)
        for i in range(n):
            e = edges[i]
            if dist(e.a, e.b) < cfg.min_seg:
                m = ((e.a[0] + e.b[0]) / 2.0, (e.a[1] + e.b[1]) / 2.0)
                prev = edges[i - 1]
                nxt = edges[(i + 1) % n]
                prev.b = m
                nxt.a = m
                del edges[i]
                changed = True
                break
        if changed:
            continue
        n = len(edges)
        for i in range(n):
            e = edges[i]
            nx = edges[(i + 1) % n]
            if e.arc is not None or nx.arc is not None:
                continue
            if e.synthetic != nx.synthetic or e.top != nx.top:
                continue
            d, _ = point_seg_dist(e.b, e.a, nx.b)
            dx1, dy1 = e.b[0] - e.a[0], e.b[1] - e.a[1]
            dx2, dy2 = nx.b[0] - nx.a[0], nx.b[1] - nx.a[1]
            if d <= cfg.snap_tol and dx1 * dx2 + dy1 * dy2 > 0:
                if i + 1 < n:
                    e.b = nx.b
                    del edges[i + 1]
                else:
                    nx.a = e.a
                    del edges[i]
                changed = True
                break
    out = BoundaryLoop(edges, list(loop.bridges))
    if signed_area(out.points) < 0:
        raise GeometryError("Detected loop has clockwise orientation (internal error).")
    return out


def self_intersections(points, closed, tol):
    n = len(points)
    segs = n if closed else n - 1
    bad = []
    for i in range(segs):
        a, b = points[i], points[(i + 1) % n]
        for j in range(i + 1, segs):
            if j == i + 1 or (closed and i == 0 and j == segs - 1):
                continue
            c, d = points[j], points[(j + 1) % n]
            if seg_intersects(a, b, c, d, tol):
                bad.append((i, j))
    return bad


def validate_loop(loop, cfg):
    """Return a list of error strings (empty = valid)."""
    errs = []
    pts = loop.points
    if len(pts) < 3:
        errs.append("Boundary has fewer than 3 edges.")
        return errs
    if loop.area < cfg.min_area:
        errs.append("Boundary area is too small.")
    for e in loop.edges:
        if dist(e.a, e.b) < cfg.min_seg:
            errs.append("Boundary contains an edge shorter than the minimum segment length.")
            break
    # closure continuity
    for i, e in enumerate(loop.edges):
        nxt = loop.edges[(i + 1) % len(loop.edges)]
        if dist(e.b, nxt.a) > 1e-9:
            errs.append("Boundary edges are not continuous.")
            break
    if self_intersections(pts, True, cfg.snap_tol * 0.5):
        errs.append("Boundary is self-intersecting or self-touching.")
    return errs
