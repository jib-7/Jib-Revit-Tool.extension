# -*- coding: utf-8 -*-
"""Duplicate prevention and output tagging."""
import hashlib

from Autodesk.Revit.DB import FilledRegion, FilteredElementCollector

from .models import dist
from .point_in_polygon import point_in_polygon
from .revit_utils import get_comment, get_name, id_value, name_matches, xyz_t

TAG_PREFIX = "FPC026|"


def loop_signature(loop, mm_per_unit=304.8):
    pts = sorted((round(p[0] * mm_per_unit, 1), round(p[1] * mm_per_unit, 1)) for p in loop.points)
    return hashlib.md5(repr(pts).encode("utf-8")).hexdigest()[:10]


def make_tag(signature, role):
    return "%s%s|%s" % (TAG_PREFIX, signature, role)


def _region_uv_points(region, frame):
    pts = []
    for cl in region.GetBoundaries():
        loop_pts = []
        for c in cl:
            loop_pts.append(frame.to_uv(xyz_t(c.GetEndPoint(0))))
        pts.append(loop_pts)
    return pts


def find_duplicates(doc, view, frame, loop, pick_uv, region_token, signature, tol):
    """Return a list of human-readable descriptions of conflicting elements."""
    found = []
    new_pts = loop.points
    for el in FilteredElementCollector(doc, view.Id).WhereElementIsNotElementType():
        tag = get_comment(el)
        if tag.startswith(TAG_PREFIX + signature):
            found.append("%s (id %s) already created by this tool for the same boundary"
                         % (tag.split("|")[-1], id_value(el)))
    for el in FilteredElementCollector(doc, view.Id).OfClass(FilledRegion):
        try:
            rtype = doc.GetElement(el.GetTypeId())
            if not name_matches(get_name(rtype), region_token):
                continue
            for pts in _region_uv_points(el, frame):
                if not pts:
                    continue
                matched = sum(1 for p in new_pts if any(dist(p, q) <= tol * 2 for q in pts))
                if matched >= 0.9 * len(new_pts) and len(pts) >= 3 and abs(len(pts) - len(new_pts)) <= 2:
                    found.append("026 Filled Region (id %s) with the same boundary" % id_value(el))
                elif point_in_polygon(pick_uv, pts, 0.0) >= 0:
                    found.append("026 Filled Region (id %s) already covers the clicked point" % id_value(el))
        except Exception:
            continue
    return list(dict.fromkeys(found)) if hasattr(dict, "fromkeys") else found
