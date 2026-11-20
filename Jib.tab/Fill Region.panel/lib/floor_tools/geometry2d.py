# -*- coding: utf-8 -*-
"""Pure-Python 2D polygon helpers. No Revit dependency, so it is unit-testable.

Polygons are lists of (x, y) tuples, implicitly closed.
"""
from __future__ import division


def signed_area(points):
    """Shoelace area; positive for counter-clockwise polygons."""
    n = len(points)
    if n < 3:
        return 0.0
    total = 0.0
    for i in range(n):
        x1, y1 = points[i]
        x2, y2 = points[(i + 1) % n]
        total += x1 * y2 - x2 * y1
    return total / 2.0


def _orient(a, b, c):
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def segments_cross(a, b, c, d, eps=1e-10):
    """True only for a proper crossing (touching end points do not count)."""
    if (max(a[0], b[0]) < min(c[0], d[0]) or max(c[0], d[0]) < min(a[0], b[0]) or
            max(a[1], b[1]) < min(c[1], d[1]) or max(c[1], d[1]) < min(a[1], b[1])):
        return False
    o1, o2 = _orient(a, b, c), _orient(a, b, d)
    o3, o4 = _orient(c, d, a), _orient(c, d, b)
    return (((o1 > eps and o2 < -eps) or (o1 < -eps and o2 > eps)) and
            ((o3 > eps and o4 < -eps) or (o3 < -eps and o4 > eps)))


def polygon_self_intersects(points, eps=1e-10):
    n = len(points)
    for i in range(n):
        a, b = points[i], points[(i + 1) % n]
        for j in range(i + 2, n):
            if i == 0 and j == n - 1:
                continue  # neighbours through the closing edge
            if segments_cross(a, b, points[j], points[(j + 1) % n], eps):
                return True
    return False


def polygons_cross(poly_a, poly_b, eps=1e-10):
    na, nb = len(poly_a), len(poly_b)
    for i in range(na):
        a, b = poly_a[i], poly_a[(i + 1) % na]
        for j in range(nb):
            if segments_cross(a, b, poly_b[j], poly_b[(j + 1) % nb], eps):
                return True
    return False


def point_in_polygon(point, polygon):
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


def polygon_inside(inner, outer, max_samples=50):
    """True if (the majority of) the inner polygon's vertices lie inside outer.

    Callers rule out edge crossings separately, so a vertex vote is enough and
    tolerates vertices that sit exactly on the outer boundary.
    """
    n = len(inner)
    if n == 0:
        return False
    step = max(1, n // max_samples)
    samples = inner[::step]
    hits = sum(1 for p in samples if point_in_polygon(p, outer))
    return hits * 2 > len(samples)
