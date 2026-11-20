# -*- coding: utf-8 -*-
"""Colour conversions (RGB tuples <-> HEX <-> Revit Color <-> WPF brush)."""
import re
from Autodesk.Revit.DB import Color

_HEX = re.compile(r'^#?([0-9a-fA-F]{6}|[0-9a-fA-F]{3})$')


def clamp(v):
    try:
        v = int(v)
    except Exception:
        v = 0
    return max(0, min(255, v))


def rgb_to_hex(rgb):
    return '#%02X%02X%02X' % (clamp(rgb[0]), clamp(rgb[1]), clamp(rgb[2]))


def hex_to_rgb(text):
    m = _HEX.match((text or '').strip())
    if not m:
        return None
    h = m.group(1)
    if len(h) == 3:
        h = ''.join(c * 2 for c in h)
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def parse_rgb(r, g, b):
    try:
        vals = [int(str(x).strip()) for x in (r, g, b)]
    except Exception:
        return None
    if any(v < 0 or v > 255 for v in vals):
        return None
    return tuple(vals)


def to_revit_color(rgb):
    return Color(clamp(rgb[0]), clamp(rgb[1]), clamp(rgb[2]))


def from_revit_color(color):
    try:
        if color is None or not color.IsValid:
            return (0, 0, 0)
        return (int(color.Red), int(color.Green), int(color.Blue))
    except Exception:
        return (0, 0, 0)


def to_wpf_brush(rgb):
    from System.Windows.Media import SolidColorBrush
    from System.Windows.Media import Color as WColor
    return SolidColorBrush(WColor.FromRgb(clamp(rgb[0]), clamp(rgb[1]), clamp(rgb[2])))


def describe(rgb):
    return 'RGB(%d, %d, %d) %s' % (rgb[0], rgb[1], rgb[2], rgb_to_hex(rgb))
