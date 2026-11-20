# -*- coding: utf-8 -*-
"""Collects Detail Lines and Detail Component geometry of the active view."""
from Autodesk.Revit.DB import (Arc, BuiltInCategory, Curve, CurveElement, CurveElementType,
                               FamilyInstance, FilteredElementCollector, GeometryInstance,
                               Line, Options, PolyLine, Solid, Transform)

from .models import ArcInfo, Primitive, dist
from .revit_utils import name_matches, xyz_t


class CollectStats(object):
    def __init__(self):
        self.detail_curves = 0
        self.components = 0
        self.excluded_output = 0
        self.curves = 0
        self.skipped = 0
        self.errors = []


def _uv(frame, xyz):
    return frame.to_uv(xyz_t(xyz))


def _curve_to_primitive(curve, frame, min_len):
    try:
        if isinstance(curve, Line):
            a, b = _uv(frame, curve.GetEndPoint(0)), _uv(frame, curve.GetEndPoint(1))
            if dist(a, b) <= min_len:
                return None
            return Primitive('line', [a, b])
        if isinstance(curve, Arc) and curve.IsBound:
            normal = xyz_t(curve.Normal)
            d = frame.direction
            if abs(normal[0] * d[0] + normal[1] * d[1] + normal[2] * d[2]) > 0.9999:
                s = _uv(frame, curve.GetEndPoint(0))
                e = _uv(frame, curve.GetEndPoint(1))
                m = _uv(frame, curve.Evaluate(0.5, True))
                info = ArcInfo.from_three_points(s, m, e)
                if info is not None:
                    return Primitive('arc', arc=info)
        pts = [_uv(frame, p) for p in curve.Tessellate()]
        if len(pts) >= 2:
            return Primitive('poly', pts)
    except Exception:
        return None
    return None


def _walk_geometry(geom, transform, out):
    for obj in geom:
        if isinstance(obj, GeometryInstance):
            sub = obj.GetSymbolGeometry()
            if sub is not None:
                _walk_geometry(sub, transform.Multiply(obj.Transform), out)
        elif isinstance(obj, Curve):
            out.append(obj.CreateTransformed(transform))
        elif isinstance(obj, PolyLine):
            pts = list(obj.GetCoordinates())
            for i in range(len(pts) - 1):
                p0, p1 = transform.OfPoint(pts[i]), transform.OfPoint(pts[i + 1])
                out.append(Line.CreateBound(p0, p1))
        elif isinstance(obj, Solid):
            try:
                for edge in obj.Edges:
                    out.append(edge.AsCurve().CreateTransformed(transform))
            except Exception:
                pass


def _component_curves(inst, view):
    opts = Options()
    opts.View = view
    opts.ComputeReferences = False
    opts.IncludeNonVisibleObjects = False
    geom = inst.get_Geometry(opts)
    out = []
    if geom is None:
        return out
    try:
        _walk_geometry(geom, Transform.Identity, out)
    except Exception:
        out = []
        for obj in geom:      # fallback: let Revit flatten the instance geometry
            if isinstance(obj, GeometryInstance):
                for sub in obj.GetInstanceGeometry():
                    if isinstance(sub, Curve):
                        out.append(sub)
    return out


def _is_hidden(elem, view):
    try:
        return elem.IsHidden(view)
    except Exception:
        return False


def collect_primitives(doc, view, frame, cfg, exclude_tokens):
    """Return (list[Primitive], CollectStats). Everything is in view (u, v)."""
    stats = CollectStats()
    prims = []
    seen = set()

    for el in FilteredElementCollector(doc, view.Id).OfClass(CurveElement).WhereElementIsNotElementType():
        try:
            if el.CurveElementType != CurveElementType.DetailCurve or _is_hidden(el, view):
                continue
            pr = _curve_to_primitive(el.GeometryCurve, frame, cfg.snap_tol)
        except Exception as ex:
            stats.errors.append("Detail curve: %s" % ex)
            continue
        stats.detail_curves += 1
        if pr is not None:
            prims.append(pr)
            stats.curves += 1
        else:
            stats.skipped += 1

    col = (FilteredElementCollector(doc, view.Id)
           .OfCategory(BuiltInCategory.OST_DetailComponents).WhereElementIsNotElementType())
    for el in col:
        if not isinstance(el, FamilyInstance) or _is_hidden(el, view):
            continue
        try:
            sym = el.Symbol
            fam_name = sym.Family.Name
            if exclude_tokens and any(name_matches(fam_name, t) for t in exclude_tokens):
                stats.excluded_output += 1
                continue
            curves = _component_curves(el, view)
        except Exception as ex:
            stats.errors.append("Detail component: %s" % ex)
            continue
        stats.components += 1
        for c in curves:
            pr = _curve_to_primitive(c, frame, cfg.snap_tol)
            if pr is not None:
                prims.append(pr)
                stats.curves += 1
            else:
                stats.skipped += 1
    return prims, stats
