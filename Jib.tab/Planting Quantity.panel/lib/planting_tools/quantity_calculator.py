# -*- coding: utf-8 -*-
"""Pure Python quantity maths (no Revit API). Easy to extend with new layouts."""
from __future__ import division
import math

# Floating point noise guard
_DECIMALS = 6


def _density(area_m2, density):
    """Simple density calculation: plants = area × plants_per_m²."""
    return area_m2 * density


# Keep the same key so the rest of the code does not break
ARRANGEMENTS = {
    "square": _density,          # now used as density
}


def calculate_quantity(area_m2, density, arrangement="square"):
    """Return the whole number of plants, always rounded UP.

    area_m2  -- enclosed area in square metres (> 0)
    density  -- plants per square metre (> 0)
    """
    if area_m2 is None or area_m2 <= 0:
        raise ValueError("Area must be greater than zero")
    if density is None or density <= 0:
        raise ValueError("Density must be greater than zero")
    function = ARRANGEMENTS.get(arrangement)
    if function is None:
        raise ValueError("Unsupported planting arrangement: {}".format(arrangement))
    raw = function(float(area_m2), float(density))
    return int(math.ceil(round(raw, _DECIMALS)))