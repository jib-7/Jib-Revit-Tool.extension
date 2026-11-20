# -*- coding: utf-8 -*-
"""Inward offsetting of an open path with mitre joins (pure Python)."""
from __future__ import division
import math

from .geometry_validator import self_intersections
from .models import GeometryError, dist, point_seg_dist, v_sub, v_cross, v_dot


def _intersect(l1, l2, prev_len):
    (p, d), (q, e) = l1, l2
    den = v_cross(d, e)
    if abs(den) < 1e-9:
        if v_dot(d, e) > 0:
            return (p[0] + d[0] * prev_len, p[1] + d[1] * prev_len)
        raise GeometryError("Boundary contains a 180-degree reversal; cannot offset it.")
    t = v_cross(v_sub(q, p), e) / den
    return (p[0] + d[0] * t, p[1] + d[1] * t)


def offset_path(points, distance, v_top, overrides, tol, miter_limit=8.0):
    """Offset an open polyline to its left side (inward for a CCW loop).

    points     : [(u, v), ...] open path in counter-clockwise loop direction
    distance   : offset distance
    v_top      : first and last vertex are placed exactly on v = v_top
    overrides  : {edge_index: u} forces that (near-vertical) edge onto u = value
    """
    n = len(points) - 1
    if n < 1:
        raise GeometryError("Boundary path is too short to offset.")
    lines, lens, dirs = [], [], []
    for i in range(n):
        a, b = points[i], points[i + 1]
        d = v_sub(b, a)
        length = math.hypot(d[0], d[1])
        if length < tol:
            raise GeometryError("Boundary path contains a zero-length edge.")
        u = (d[0] / length, d[1] / length)
        if i in overrides:
            p0 = (overrides[i], a[1])
        else:
            p0 = (a[0] + (-u[1]) * distance, a[1] + u[0] * distance)
        lines.append((p0, u))
        lens.append(length)
        dirs.append(u)

    def at_top(line):
        p, d = line
        if abs(d[1]) < 1e-9:
            raise GeometryError("First/last boundary edge is horizontal; cannot start at the top.")
        t = (v_top - p[1]) / d[1]
        return (p[0] + d[0] * t, v_top)

    out = [at_top(lines[0])]
    for i in range(1, n):
        out.append(_intersect(lines[i - 1], lines[i], lens[i - 1]))
    out.append(at_top(lines[-1]))
    for i in range(n):
        seg = v_sub(out[i + 1], out[i])
        if v_dot(seg, dirs[i]) <= tol:
            raise GeometryError(
                "The %.1f-unit offset collapses boundary edge %d (feature too small)." % (distance, i + 1))
    for i in range(1, n):
        if (i in overrides) or ((i - 1) in overrides):
            continue
        if dist(out[i], points[i]) > miter_limit * abs(distance):
            raise GeometryError("Sharp corner at vertex %d makes the offset unreliable." % i)
    return out


def simplify_polyline(points, min_seg, collinear_tol):
    """Drop duplicate vertices and merge collinear segments (keeps end points)."""
    pts = [points[0]]
    for p in points[1:]:
        if dist(p, pts[-1]) >= min_seg:
            pts.append(p)
    if len(pts) >= 2 and dist(pts[-1], points[-1]) > 0:
        pts[-1] = points[-1]
    changed = True
    while changed and len(pts) > 2:
        changed = False
        for i in range(1, len(pts) - 1):
            d, _ = point_seg_dist(pts[i], pts[i - 1], pts[i + 1])
            if d <= collinear_tol:
                del pts[i]
                changed = True
                break
    return pts


def check_polyline(points, tol):
    if self_intersections(points, False, tol):
        raise GeometryError("Offset geometry is self-intersecting.")
