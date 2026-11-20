# -*- coding: utf-8 -*-
from Autodesk.Revit.UI.Selection import ObjectType, ISelectionFilter
from Autodesk.Revit.DB import FilledRegion, ElementId
from Autodesk.Revit.Exceptions import OperationCanceledException
from lib import revit_compat as rc


class FilledRegionFilter(ISelectionFilter):
    def AllowElement(self, elem):
        return isinstance(elem, FilledRegion)

    def AllowReference(self, reference, position):
        return False


def pick_regions(uidoc, prompt='Select Filled Regions, then click Finish'):
    """Returns list of element id values (active-document elements only)."""
    try:
        refs = uidoc.Selection.PickObjects(ObjectType.Element, FilledRegionFilter(), prompt)
    except OperationCanceledException:
        return []
    ids = []
    for r in refs:
        try:
            if r.LinkedElementId != ElementId.InvalidElementId:
                continue  # never touch Revit Links
        except Exception:
            pass
        ids.append(rc.eid_value(r.ElementId))
    return ids


def from_revit_selection(uidoc):
    doc = uidoc.Document
    out = []
    for eid in uidoc.Selection.GetElementIds():
        el = doc.GetElement(eid)
        if isinstance(el, FilledRegion):
            out.append(rc.eid_value(eid))
    return out
