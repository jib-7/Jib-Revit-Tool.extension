# -*- coding: utf-8 -*-
"""Pure-Python data models and 2D vector helpers (no Revit dependency).

All lengths are in Revit internal units (decimal feet) unless stated otherwise.
Coordinates (u, v) are expressed in the active view plane:
u = along view.RightDirection, v = along view.UpDirection.
"""
from __future__ import division
import math

MM_PER_FOOT = 304.8

try:  # inside Revit / pyRevit
    from Autodesk.Revit.DB import UnitUtils, UnitTypeId

    def mm_to_internal(value_mm):
        return UnitUtils.ConvertToInternalUnits(float(value_mm), UnitTypeId.Millimeters)

    def internal_to_mm(value):
        return UnitUtils.ConvertFromInternalUnits(float(value), UnitTypeId.Millimeters)
    REVIT_UNITS = True
except Exception:  # unit tests outside Revit
    def mm_to_internal(value_mm):
        return float(value_mm) / MM_PER_FOOT

    def internal_to_mm(value):
        return float(value) * MM_PER_FOOT
    REVIT_UNITS = False


class PlanterError(Exception):
    """Base class for user-facing errors."""


class GeometryError(PlanterError):
    pass


class FamilyError(PlanterError):
    pass


# ----------------------------------------------------------------- vectors
def v_sub(a, b):
    return (a[0] - b[0], a[1] - b[1])


def v_add(a, b):
    return (a[0] + b[0], a[1] + b[1])


def v_scale(a, s):
    return (a[0] * s, a[1] * s)


def v_dot(a, b):
    return a[0] * b[0] + a[1] * b[1]


def v_cross(a, b):
    return a[0] * b[1] - a[1] * b[0]


def v_len(a):
    return math.hypot(a[0], a[1])


def dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def point_seg_dist(p, a, b):
    """Return (distance, t) of point p to segment a-b, t clamped to [0, 1]."""
    dx = b[0] - a[0]
    dy = b[1] - a[1]
    l2 = dx * dx + dy * dy
    if l2 <= 0.0:
        return dist(p, a), 0.0
    t = ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / l2
    t = 0.0 if t < 0.0 else (1.0 if t > 1.0 else t)
    return math.hypot(p[0] - (a[0] + t * dx), p[1] - (a[1] + t * dy)), t


def seg_intersects(p1, p2, q1, q2, tol):
    """True if two segments cross properly or touch within tol."""
    if (max(p1[0], p2[0]) < min(q1[0], q2[0]) - tol or
            max(q1[0], q2[0]) < min(p1[0], p2[0]) - tol or
            max(p1[1], p2[1]) < min(q1[1], q2[1]) - tol or
            max(q1[1], q2[1]) < min(p1[1], p2[1]) - tol):
        return False
    if (point_seg_dist(q1, p1, p2)[0] <= tol or point_seg_dist(q2, p1, p2)[0] <= tol or
            point_seg_dist(p1, q1, q2)[0] <= tol or point_seg_dist(p2, q1, q2)[0] <= tol):
        return True
    r = v_sub(p2, p1)
    s = v_sub(q2, q1)
    den = v_cross(r, s)
    if abs(den) < 1e-18:
        return False
    qp = v_sub(q1, p1)
    t = v_cross(qp, s) / den
    u = v_cross(qp, r) / den
    return 0.0 < t < 1.0 and 0.0 < u < 1.0


def signed_area(points):
    a = 0.0
    n = len(points)
    for i in range(n):
        x1, y1 = points[i]
        x2, y2 = points[(i + 1) % n]
        a += x1 * y2 - x2 * y1
    return a / 2.0


# --------------------------------------------------------------- view frame
class ViewFrame(object):
    """Maps between 3D model coordinates and (u, v) in the view plane."""

    def __init__(self, origin, right, up, direction):
        self.origin = tuple(origin)
        self.right = tuple(right)
        self.up = tuple(up)
        self.direction = tuple(direction)

    @staticmethod
    def _dot3(a, b):
        return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]

    def to_uv(self, xyz):
        d = (xyz[0] - self.origin[0], xyz[1] - self.origin[1], xyz[2] - self.origin[2])
        return (self._dot3(d, self.right), self._dot3(d, self.up))

    def depth(self, xyz):
        d = (xyz[0] - self.origin[0], xyz[1] - self.origin[1], xyz[2] - self.origin[2])
        return self._dot3(d, self.direction)

    def to_xyz(self, uv):
        u, v = uv
        return tuple(self.origin[i] + u * self.right[i] + v * self.up[i] for i in range(3))


# -------------------------------------------------------------------- arcs
class ArcInfo(object):
    """Circular arc in (u, v) space, defined by centre/radius and 3 points."""

    def __init__(self, center, radius, start, mid, end, ccw):
        self.center = center
        self.radius = radius
        self.start = start
        self.mid = mid
        self.end = end
        self.ccw = ccw

    @staticmethod
    def from_three_points(start, mid, end):
        ax, ay = 0.0, 0.0
        bx, by = mid[0] - start[0], mid[1] - start[1]
        cx, cy = end[0] - start[0], end[1] - start[1]
        d = 2.0 * (ax * (by - cy) + bx * (cy - ay) + cx * (ay - by))
        if abs(d) < 1e-14:
            return None
        b2 = bx * bx + by * by
        c2 = cx * cx + cy * cy
        ux = (cy * b2 - by * c2) / d
        uy = (bx * c2 - cx * b2) / d
        r = math.hypot(ux, uy)
        if r < 1e-12:
            return None
        center = (ux + start[0], uy + start[1])
        cross = bx * (cy - by) - by * (cx - bx)
        return ArcInfo(center, r, start, mid, end, cross > 0)

    def sweep(self):
        a0 = math.atan2(self.start[1] - self.center[1], self.start[0] - self.center[0])
        a1 = math.atan2(self.end[1] - self.center[1], self.end[0] - self.center[0])
        if self.ccw:
            return a0, (a1 - a0) % (2 * math.pi)
        return a0, -((a0 - a1) % (2 * math.pi))

    def tessellate(self, tol):
        a0, sw = self.sweep()
        r = self.radius
        if tol >= r:
            step = math.pi / 2.0
        else:
            step = 2.0 * math.acos(max(-1.0, 1.0 - tol / r))
        n = int(math.ceil(abs(sw) / max(step, 1e-6)))
        n = max(2, min(n, 720))
        pts = [self.start]
        for i in range(1, n):
            a = a0 + sw * i / n
            pts.append((self.center[0] + r * math.cos(a), self.center[1] + r * math.sin(a)))
        pts.append(self.end)
        return pts


def arc_run_midpoint(arc, a, b, ccw_traversal):
    """Return (mid_point, abs_sweep) of arc portion from a to b."""
    c = arc.center
    a0 = math.atan2(a[1] - c[1], a[0] - c[0])
    a1 = math.atan2(b[1] - c[1], b[0] - c[0])
    if ccw_traversal:
        sw = (a1 - a0) % (2 * math.pi)
    else:
        sw = -((a0 - a1) % (2 * math.pi))
    am = a0 + sw / 2.0
    return (c[0] + arc.radius * math.cos(am), c[1] + arc.radius * math.sin(am)), abs(sw)


class Primitive(object):
    """Input curve in uv space. kind: 'line' | 'poly' | 'arc'."""

    def __init__(self, kind, points=None, arc=None, source=None):
        self.kind = kind
        self.points = points
        self.arc = arc
        self.source = source

    def pieces(self, arc_tol):
        """Yield straight pieces (p0, p1, arc_or_None)."""
        if self.kind == 'line':
            yield (self.points[0], self.points[1], None)
        elif self.kind == 'poly':
            for i in range(len(self.points) - 1):
                yield (self.points[i], self.points[i + 1], None)
        elif self.kind == 'arc':
            pts = self.arc.tessellate(arc_tol)
            for i in range(len(pts) - 1):
                yield (pts[i], pts[i + 1], self.arc)

    def bbox_points(self, arc_tol):
        if self.kind == 'arc':
            return self.arc.tessellate(max(arc_tol, self.arc.radius / 20.0))
        return self.points


# ------------------------------------------------------------------- loops
class LoopEdge(object):
    __slots__ = ('a', 'b', 'arc', 'synthetic', 'top')

    def __init__(self, a, b, arc=None, synthetic=False, top=False):
        self.a = a
        self.b = b
        self.arc = arc
        self.synthetic = synthetic
        self.top = top

    def length(self):
        return dist(self.a, self.b)


class BoundaryLoop(object):
    """Closed counter-clockwise loop of straight/arc-piece edges."""

    def __init__(self, edges, bridges=None):
        self.edges = edges
        self.bridges = bridges or []   # list of dicts: length, top

    @property
    def points(self):
        return [e.a for e in self.edges]

    @property
    def area(self):
        return signed_area(self.points)

    def bbox(self):
        pts = self.points
        us = [p[0] for p in pts]
        vs = [p[1] for p in pts]
        return min(us), min(vs), max(us), max(vs)

    def signature(self, ndigits=5):
        pts = sorted((round(p[0], ndigits), round(p[1], ndigits)) for p in self.points)
        return tuple(pts)


def loop_to_curve_specs(loop, min_len=0.0):
    """Convert loop edges into ('line', a, b) / ('arc', a, mid, b) specs.

    Consecutive pieces that came from the same original arc are merged back
    into a single arc.
    """
    edges = loop.edges
    n = len(edges)
    start = None
    for i in range(n):
        prev = edges[i - 1]
        cur = edges[i]
        if not (cur.arc is not None and prev.arc is cur.arc and not cur.synthetic):
            start = i
            break
    if start is None:   # a full circle: fall back to straight pieces
        return [('line', e.a, e.b) for e in edges]
    specs = []
    i = 0
    while i < n:
        e = edges[(start + i) % n]
        if e.arc is None or e.synthetic:
            specs.append(('line', e.a, e.b))
            i += 1
            continue
        j = i
        while (j + 1 < n and edges[(start + j + 1) % n].arc is e.arc and
               not edges[(start + j + 1) % n].synthetic):
            j += 1
        first = edges[(start + i) % n]
        last = edges[(start + j) % n]
        c = e.arc.center
        ccw_trav = v_cross(v_sub(first.a, c), v_sub(first.b, c)) > 0
        mid, sw = arc_run_midpoint(e.arc, first.a, last.b, ccw_trav)
        if sw < 1e-6 or sw > 2 * math.pi - 1e-3 or dist(first.a, last.b) < max(min_len, 1e-9):
            for k in range(i, j + 1):
                pe = edges[(start + k) % n]
                specs.append(('line', pe.a, pe.b))
        else:
            specs.append(('arc', first.a, mid, last.b))
        i = j + 1
    return specs
