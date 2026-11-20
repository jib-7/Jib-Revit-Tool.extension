# -*- coding: utf-8 -*-
"""Point-in-polygon tests (pure Python)."""
from __future__ import division
from .models import point_seg_dist, signed_area  # noqa: F401


def point_in_polygon(pt, poly, tol=0.0):
    """Return 1 if inside, 0 if on the boundary (within tol), -1 if outside."""
    n = len(poly)
    if n < 3:
        return -1
    x, y = pt
    for i in range(n):
        if point_seg_dist(pt, poly[i], poly[(i + 1) % n])[0] <= tol:
            return 0
    inside = False
    j = n - 1
    for i in range(n):
        xi, yi = poly[i]
        xj, yj = poly[j]
        if (yi > y) != (yj > y):
            xint = (xj - xi) * (y - yi) / (yj - yi) + xi
            if x < xint:
                inside = not inside
        j = i
    return 1 if inside else -1
