# -*- coding: utf-8 -*-
"""CurveLoop processing: projection onto the view plane, grouping, offsetting
and validation. Works only on geometry - it never touches the document."""
from __future__ import division

import math

from Autodesk.Revit import DB

from floor_tools import geometry2d, settings
from floor_tools.utils import FloorToolsError


class GeometryError(FloorToolsError):
    """Geometry cannot be turned into a valid Filled Region boundary."""


# ------------------------------------------------------------- data types ---
class PlaneBasis(object):
    """Orthonormal frame of a plane; converts 3D points to plane (u, v)."""

    def __init__(self, origin, normal):
        self.origin = origin
        self.normal = normal.Normalize()
        plane = DB.Plane.CreateByNormalAndOrigin(self.normal, origin)
        self.u = plane.XVec
        self.v = plane.YVec

    def signed_distance(self, point):
        return point.Subtract(self.origin).DotProduct(self.normal)

    def project(self, point):
        return point.Subtract(self.normal.Multiply(self.signed_distance(point)))

    def to_uv(self, point):
        rel = point.Subtract(self.origin)
        return (rel.DotProduct(self.u), rel.DotProduct(self.v))


class LoopGroup(object):
    """One outer boundary plus its openings (all CurveLoops in one plane)."""

    def __init__(self, outer, holes=None):
        self.outer = outer
        self.holes = list(holes or [])

    def loops(self):
        return [self.outer] + self.holes


# --------------------------------------------------------------- sampling ---
def sample_curve(curve, min_segments=None):
    """Points along a curve (start and end included), density from settings."""
    p0, p1 = curve.GetEndPoint(0), curve.GetEndPoint(1)
    if isinstance(curve, DB.Line):
        return [p0, p1]
    minimum = min_segments or settings.MIN_CURVE_SEGMENTS
    count = int(math.ceil(curve.ApproximateLength / settings.ARC_SEGMENT_LENGTH_FT))
    count = max(minimum, min(settings.MAX_CURVE_SEGMENTS, count))
    points = [p0]
    for i in range(1, count):
        points.append(curve.Evaluate(float(i) / count, True))  # normalized parameter
    points.append(p1)
    return points


def loop_points(loop):
    """Closed polygon (no repeated first point) approximating the loop."""
    points = []
    for curve in loop:
        points.extend(sample_curve(curve)[:-1])
    return points


def loop_uv(loop, basis):
    return [basis.to_uv(p) for p in loop_points(loop)]


def loop_area(loop, basis):
    return geometry2d.signed_area(loop_uv(loop, basis))


# ------------------------------------------------------- loop construction ---
def _dedupe_points(points, min_len):
    """Drop points closer than min_len to the previous one; keep the last exact."""
    if not points:
        return []
    kept = []
    for p in points[:-1]:
        if not kept or kept[-1].DistanceTo(p) >= min_len:
            kept.append(p)
    last = points[-1]
    if kept and kept[-1].DistanceTo(last) < min_len:
        if len(kept) == 1:
            return []            # the whole curve is shorter than min_len
        kept[-1] = last
    else:
        kept.append(last)
    return kept


def _lines_through(points, min_len):
    pts = _dedupe_points(points, min_len)
    return [DB.Line.CreateBound(pts[i], pts[i + 1]) for i in range(len(pts) - 1)]


def _assemble(curves):
    loop = DB.CurveLoop()
    for curve in curves:
        loop.Append(curve)          # raises if a curve is not contiguous
    if loop.IsOpen():
        raise GeometryError("Boundary curves do not form a closed loop.")
    return loop


def _polygonize(curves, min_len):
    """Last resort: replace every curve by straight segments and close the loop."""
    if not curves:
        raise GeometryError("Boundary has no usable curves.")
    gap = curves[-1].GetEndPoint(1).DistanceTo(curves[0].GetEndPoint(0))
    if gap > 10.0 * min_len:
        raise GeometryError("Boundary is not closed (gap of {:.4f} ft).".format(gap))
    points = []
    for curve in curves:
        points.extend(sample_curve(curve, 16)[:-1])
    points = _dedupe_points(points, min_len)
    if len(points) > 1 and points[0].DistanceTo(points[-1]) < min_len:
        points.pop()
    if len(points) < 3:
        raise GeometryError("Boundary collapses to fewer than three points.")
    loop = DB.CurveLoop()
    for i in range(len(points)):
        loop.Append(DB.Line.CreateBound(points[i], points[(i + 1) % len(points)]))
    return loop


def build_loop(curves, min_len):
    """Curves in loop order -> (CurveLoop, approximated). Approximated means some
    curves were replaced by line segments to obtain a valid loop."""
    try:
        return _assemble(curves), False
    except Exception:
        return _polygonize(curves, min_len), True


def assemble_unordered(curves, min_len, tolerance=None):
    """Chain unordered / inconsistently oriented curves (e.g. a sketch profile)."""
    tol = tolerance or settings.CHAIN_TOLERANCE_FT
    remaining = list(curves)
    ordered = [remaining.pop(0)]
    end = ordered[0].GetEndPoint(1)
    while remaining:
        chosen = None
        for index, curve in enumerate(remaining):
            if curve.GetEndPoint(0).DistanceTo(end) <= tol:
                chosen = (index, curve)
                break
            if curve.GetEndPoint(1).DistanceTo(end) <= tol:
                chosen = (index, curve.CreateReversed())
                break
        if chosen is None:
            raise GeometryError("Sketch profile is not a closed, continuous loop.")
        remaining.pop(chosen[0])
        ordered.append(chosen[1])
        end = chosen[1].GetEndPoint(1)
    if ordered[0].GetEndPoint(0).DistanceTo(end) > tol:
        raise GeometryError("Sketch profile is not closed.")
    return build_loop(ordered, min_len)[0]


# ---------------------------------------------------------------- grouping ---
def group_loops(loops, basis):
    """Sort loops into outer boundaries and their openings by nesting depth.

    Even depth (0, 2, ...) = filled outline, odd depth = opening, so islands
    inside openings are handled as well.
    """
    polys = [loop_uv(l, basis) for l in loops]
    areas = [abs(geometry2d.signed_area(p)) for p in polys]
    order = sorted(range(len(loops)), key=lambda i: -areas[i])
    containers = {}
    for pos, i in enumerate(order):
        containers[i] = [j for j in order[:pos] if geometry2d.polygon_inside(polys[i], polys[j])]
    groups = {}
    result = []
    for i in order:
        if len(containers[i]) % 2 == 0:
            groups[i] = LoopGroup(loops[i])
            result.append(groups[i])
        else:
            groups[containers[i][-1]].holes.append(loops[i])   # smallest container
    return result


def transform_group(group, transform):
    """Move a LoopGroup with a rigid transform (e.g. link -> host coordinates)."""
    outer = DB.CurveLoop.CreateViaTransform(group.outer, transform)
    holes = [DB.CurveLoop.CreateViaTransform(h, transform) for h in group.holes]
    return LoopGroup(outer, holes)


# -------------------------------------------------------------- projection ---
def _project_curve(curve, basis, min_len):
    """Curve -> list of curves lying exactly in the view plane."""
    if isinstance(curve, DB.Line):
        p0 = basis.project(curve.GetEndPoint(0))
        p1 = basis.project(curve.GetEndPoint(1))
        return [] if p0.DistanceTo(p1) < min_len else [DB.Line.CreateBound(p0, p1)]
    distances = [basis.signed_distance(p) for p in sample_curve(curve)]
    if max(distances) - min(distances) <= settings.FLAT_TOLERANCE_FT:
        # Parallel to the view plane: a pure translation keeps arcs/splines exact.
        shift = basis.normal.Multiply(-distances[0])
        return [curve.CreateTransformed(DB.Transform.CreateTranslation(shift))]
    # Tilted (sloped floor): the true projection of an arc is an ellipse, which
    # cannot be represented safely, so approximate with a fine polyline.
    points = [basis.project(p) for p in sample_curve(curve, 16)]
    return _lines_through(points, min_len)


def project_loop(loop, basis, min_len):
    """Project a 3D loop onto the plane. Returns (CurveLoop, approximated)."""
    curves = []
    for curve in loop:
        curves.extend(_project_curve(curve, basis, min_len))
    curves = [c for c in curves if c.Length >= min_len]
    if len(curves) < 2:
        raise GeometryError("Boundary loop collapses when projected into the view.")
    return build_loop(curves, min_len)


def project_group(group, basis, min_len):
    """Project a whole LoopGroup. Returns (LoopGroup, approximated)."""
    outer, approx = project_loop(group.outer, basis, min_len)
    holes = []
    for hole in group.holes:
        projected, hole_approx = project_loop(hole, basis, min_len)
        holes.append(projected)
        approx = approx or hole_approx
    return LoopGroup(outer, holes), approx


# ------------------------------------------------------------------ offset ---
def _offset_loop(loop, distance, basis, grow):
    """Offset one loop so its enclosed area grows (grow=True) or shrinks.

    CreateViaOffset's sign convention depends on loop orientation, so both
    signs are tried and the one moving the boundary the wanted way is kept.
    """
    base_area = abs(loop_area(loop, basis))
    want_larger = grow if distance > 0 else (not grow)
    for sign in (1.0, -1.0):
        try:
            candidate = DB.CurveLoop.CreateViaOffset(loop, sign * abs(distance), basis.normal)
        except Exception:
            continue
        area = abs(loop_area(candidate, basis))
        if (want_larger and area > base_area) or ((not want_larger) and area < base_area):
            return candidate
    raise GeometryError("Boundary cannot be offset by the requested distance.")


def offset_group(group, distance, basis):
    """Positive distance = filled area grows: outline moves out, openings shrink."""
    outer = _offset_loop(group.outer, distance, basis, True)
    holes = [_offset_loop(h, distance, basis, False) for h in group.holes]
    return LoopGroup(outer, holes)


# -------------------------------------------------------------- validation ---
def validate_group(group, basis):
    """Return a list of problems (empty list = safe to pass to FilledRegion.Create)."""
    problems = []
    polys = []
    total_points = 0
    for index, loop in enumerate(group.loops()):
        label = "outer boundary" if index == 0 else "opening {}".format(index)
        if loop.IsOpen():
            problems.append("The {} is not closed.".format(label))
            polys.append(None)
            continue
        try:
            if not loop.HasPlane():
                problems.append("The {} is not planar.".format(label))
        except Exception:
            pass
        poly = loop_uv(loop, basis)
        polys.append(poly)
        total_points += len(poly)
        if abs(geometry2d.signed_area(poly)) < settings.MIN_LOOP_AREA_SQFT:
            problems.append("The {} has almost zero area.".format(label))

    if problems or total_points > settings.MAX_INTERSECTION_TEST_POINTS:
        return problems     # too large for the O(n^2) checks: rely on Revit's validation

    for index, poly in enumerate(polys):
        if geometry2d.polygon_self_intersects(poly):
            problems.append("The {} intersects itself.".format(
                "outer boundary" if index == 0 else "opening {}".format(index)))
    outer = polys[0]
    for index in range(1, len(polys)):
        if geometry2d.polygons_cross(outer, polys[index]):
            problems.append("Opening {} crosses the outer boundary.".format(index))
        elif not geometry2d.polygon_inside(polys[index], outer):
            problems.append("Opening {} lies outside the outer boundary.".format(index))
        for other in range(index + 1, len(polys)):
            if geometry2d.polygons_cross(polys[index], polys[other]):
                problems.append("Openings {} and {} overlap.".format(index, other))
    return problems
