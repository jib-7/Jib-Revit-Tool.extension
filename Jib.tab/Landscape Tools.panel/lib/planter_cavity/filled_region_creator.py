# -*- coding: utf-8 -*-
"""Creates the 026 Filled Region from the detected boundary."""
from System.Collections.Generic import List
from Autodesk.Revit.DB import Arc, CurveLoop, FilledRegion, Line

from .models import GeometryError, loop_to_curve_specs
from .revit_utils import to_xyz


def build_curve_loop(frame, loop, min_len):
    cl = CurveLoop()
    for spec in loop_to_curve_specs(loop, min_len):
        if spec[0] == 'line':
            cl.Append(Line.CreateBound(to_xyz(frame, spec[1]), to_xyz(frame, spec[2])))
        else:
            cl.Append(Arc.Create(to_xyz(frame, spec[1]), to_xyz(frame, spec[3]), to_xyz(frame, spec[2])))
    if not cl.IsOpen() and cl.HasPlane():
        return cl
    raise GeometryError("The detected boundary could not be converted to a closed planar curve loop.")


def create_filled_region(doc, view, frame, region_type, loop, min_len):
    cl = build_curve_loop(frame, loop, min_len)
    loops = List[CurveLoop]()
    loops.Add(cl)
    region = FilledRegion.Create(doc, region_type.Id, view.Id, loops)
    if region is None:
        raise GeometryError("Revit did not create the Filled Region.")
    return region
