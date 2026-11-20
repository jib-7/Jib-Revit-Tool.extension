# -*- coding: utf-8 -*-
"""Line weight helpers.

IMPORTANT API LIMITATION: the Revit API exposes the line weight NUMBER (1-16)
of a Lines subcategory, but NOT the project's Additional Settings > Line
Weights table (the plotted millimetre value per weight, which also depends on
view scale). The mm values below are therefore REFERENCE values, flagged with
'approx.' in the UI. To match your own template, create the file
line_weights.json in the plug-in config folder, e.g. {"1": 0.18, "2": 0.25}.
"""
import os
from lib import utils

MIN_WEIGHT = 1
MAX_WEIGHT = 16

_DEFAULT_MM = {1: 0.18, 2: 0.25, 3: 0.35, 4: 0.50, 5: 0.70, 6: 1.00, 7: 1.40,
               8: 2.00, 9: 2.80, 10: 4.00, 11: 5.00, 12: 6.00, 13: 7.00,
               14: 8.00, 15: 9.00, 16: 10.00}
_table = None


def table():
    global _table
    if _table is None:
        t = dict(_DEFAULT_MM)
        data = utils.read_json(os.path.join(utils.config_dir(), 'line_weights.json'), {})
        for k, v in (data or {}).items():
            try:
                t[int(k)] = float(v)
            except Exception:
                pass
        _table = t
    return _table


def reload_table():
    global _table
    _table = None


def weights():
    return list(range(MIN_WEIGHT, MAX_WEIGHT + 1))


def mm_for(weight):
    return table().get(weight)


def label(weight):
    return '%d  (approx. %s mm)' % (weight, utils.fmt_mm(mm_for(weight)))


def clamp(w):
    try:
        w = int(w)
    except Exception:
        w = MIN_WEIGHT
    return max(MIN_WEIGHT, min(MAX_WEIGHT, w))


def nearest_weight(mm):
    t = table()
    return min(t.keys(), key=lambda k: abs(t[k] - mm))
