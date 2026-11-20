# -*- coding: utf-8 -*-
"""Enclosed area of a Filled Region, calculated from its boundary curve loops.

The Revit API gives the boundary through FilledRegion.GetBoundaries(), which
returns a list of CurveLoop objects (outer loop plus one loop per hole).
Each loop is flattened into its own plane, converted into simple 2D "segments",
and the area is calculated with Green's theorem (exact for lines and arcs).

Part 1 below is pure Python maths (testable outside Revit).
Part 2 converts Revit curves into those segments.
"""
from __future__ import division
import math

from planting_tools import config

TWO_PI = 2.0 * math.pi
CLOSURE_TOLERANCE_FT = 0.002      # max gap between consecutive curves (about 0.6 mm)
MAX_ARC_STEP = math.pi / 36.0     # 5 degrees, only used to build polygons for hole detection

# Segment formats (2D, feet):
#   ("line", (x0, y0), (x1, y1))
#   ("arc",  (cx, cy), radius, start_angle, signed_sweep)   sweep > 0 = counter-clockwise
#   ("poly", [(x, y), ...])   open polyline, used for splines/ellipses (tessellated)


# ----------------------------------------------------------------------------
# Part 1 - pure maths
# ----------------------------------------------------------------------------
def segment_start(seg):
    kind = seg[0]
    if kind == "line":
        return seg[1]
    if kind == "arc":
        _, c, r, a0, sweep = seg
        return (c[0] + r * math.cos(a0), c[1] + r * math.sin(a0))
    return seg[1][0]


def segment_end(seg):
    kind = seg[0]
    if kind == "line":
        return seg[2]
    if kind == "arc":
        _, c, r, a0, sweep = seg
        a1 = a0 + sweep
        return (c[0] + r * math.cos(a1), c[1] + r * math.sin(a1))
    return seg[1][-1]


def segment_green_term(seg):
    """Contribution of one segment to the signed area: 0.5 * integral(x dy - y dx)."""
    kind = seg[0]
    if kind == "line":
        (x0, y0), (x1, y1) = seg[1], seg[2]
        return 0.5 * (x0 * y1 - x1 * y0)
    if kind == "arc":
        _, c, r, a0, sweep = seg
        a1 = a0 + sweep
        return 0.5 * (r * c[0] * (math.sin(a1) - math.sin(a0))
                      - r * c[1] * (math.cos(a1) - math.cos(a0))
                      + r * r * sweep)
    pts = seg[1]
    total = 0.0
    for i in range(len(pts) - 1):
        total += 0.5 * (pts[i][0] * pts[i + 1][1] - pts[i + 1][0] * pts[i][1])
    return total


def segment_points(seg):
    """Points along a segment (start included, end excluded) for the hole-detection polygon."""
    kind = seg[0]
    if kind == "line":
        return [seg[1]]
    if kind == "arc":
        _, c, r, a0, sweep = seg
        steps = max(2, int(math.ceil(abs(sweep) / MAX_ARC_STEP)))
        return [(c[0] + r * math.cos(a0 + sweep * k / steps),
                 c[1] + r * math.sin(a0 + sweep * k / steps)) for k in range(steps)]
    return list(seg[1][:-1])


def loop_signed_area(segments):
    return sum(segment_green_term(s) for s in segments)


def loop_polygon(segments):
    polygon = []
    for seg in segments:
        polygon.extend(segment_points(seg))
    return polygon


def loop_is_closed(segments, tolerance=CLOSURE_TOLERANCE_FT):
    """True when every curve ends where the next one starts (and the last meets the first)."""
    count = len(segments)
    if count < 2:
        return False
    for i in range(count):
        e = segment_end(segments[i])
        s = segment_start(segments[(i + 1) % count])
        if math.hypot(e[0] - s[0], e[1] - s[1]) > tolerance:
            return False
    return True


def point_in_polygon(point, polygon):
    """Ray casting test."""
    x, y = point
    inside = False
    n = len(polygon)
    j = n - 1
    for i in range(n):
        xi, yi = polygon[i]
        xj, yj = polygon[j]
        if (yi > y) != (yj > y):
            x_cross = (xj - xi) * (y - yi) / (yj - yi) + xi
            if x < x_cross:
                inside = not inside
        j = i
    return inside


def enclosed_area(loops):
    """Area enclosed by several loops, holes subtracted.

    A loop nested inside an even number of other loops is solid material (added);
    inside an odd number it is a hole (subtracted). This also handles an island
    inside a hole, and does not depend on the loops' drawing direction.
    """
    infos = []
    for segments in loops:
        infos.append((abs(loop_signed_area(segments)), loop_polygon(segments)))
    total = 0.0
    for i, (area, polygon) in enumerate(infos):
        test_point = polygon[0]
        depth = 0
        for j, (_, other) in enumerate(infos):
            if j != i and point_in_polygon(test_point, other):
                depth += 1
        total += area if depth % 2 == 0 else -area
    return total


# ----------------------------------------------------------------------------
# Part 2 - Revit curves -> segments
# ----------------------------------------------------------------------------
def _curve_to_segment(curve, to_2d):
    from Autodesk.Revit.DB import Line, Arc   # imported here so Part 1 works outside Revit

    if isinstance(curve, Line):
        return ("line", to_2d(curve.GetEndPoint(0)), to_2d(curve.GetEndPoint(1)))

    if isinstance(curve, Arc):
        start = to_2d(curve.GetEndPoint(0))
        end = to_2d(curve.GetEndPoint(1))
        mid = to_2d(curve.Evaluate(0.5, True))
        centre = to_2d(curve.Center)
        radius = math.hypot(start[0] - centre[0], start[1] - centre[1])
        a0 = math.atan2(start[1] - centre[1], start[0] - centre[0])
        a1 = math.atan2(end[1] - centre[1], end[0] - centre[0])
        am = math.atan2(mid[1] - centre[1], mid[0] - centre[0])
        ccw_sweep = (a1 - a0) % TWO_PI
        mid_offset = (am - a0) % TWO_PI
        sweep = ccw_sweep if mid_offset <= ccw_sweep else ccw_sweep - TWO_PI
        return ("arc", centre, radius, a0, sweep)

    # Splines, ellipses, etc.: approximated by Revit's own tessellation.
    return ("poly", [to_2d(p) for p in curve.Tessellate()])


def _loop_to_segments(loop):
    if not loop.HasPlane():
        return None, "a boundary loop is not planar"
    plane = loop.GetPlane()
    o, xv, yv = plane.Origin, plane.XVec, plane.YVec

    def to_2d(p):
        dx, dy, dz = p.X - o.X, p.Y - o.Y, p.Z - o.Z
        return (dx * xv.X + dy * xv.Y + dz * xv.Z,
                dx * yv.X + dy * yv.Y + dz * yv.Z)

    segments = [_curve_to_segment(curve, to_2d) for curve in loop]
    if not loop_is_closed(segments):
        return None, "a boundary loop is not closed or its curves are not continuous"
    return segments, None


def get_area_m2(filled_region):
    """Return (area_in_square_metres, error_text). Exactly one of them is None."""
    try:
        loops = list(filled_region.GetBoundaries())
    except Exception as ex:
        return None, "Could not read the boundary: {}".format(ex)
    if not loops:
        return None, "Filled Region has no boundary loops"

    all_segments = []
    for loop in loops:
        try:
            segments, error = _loop_to_segments(loop)
        except Exception as ex:
            return None, "Could not read boundary curves: {}".format(ex)
        if error:
            return None, "Area cannot be calculated reliably: " + error
        all_segments.append(segments)

    area_ft2 = enclosed_area(all_segments)
    if area_ft2 <= 1e-9:
        return None, "Calculated area is zero or negative"
    return area_ft2 * config.SQFEET_TO_SQMETRES, None
