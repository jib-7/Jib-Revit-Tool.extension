# -*- coding: utf-8 -*-
"""Floor selection (host model or linked models) as FloorItem objects.

A FloorItem couples a Floor with the information needed to use it in the ACTIVE
document: for linked floors that is the link instance and its transform, which
moves link coordinates into host coordinates.
"""
from Autodesk.Revit import DB
from Autodesk.Revit.Exceptions import OperationCanceledException
from Autodesk.Revit.UI.Selection import ISelectionFilter, ObjectType

from floor_tools import revit_compat as compat


class FloorItem(object):
    def __init__(self, floor, link_instance=None, transform=None):
        self.floor = floor
        self.link_instance = link_instance
        self.transform = transform          # None for floors of the active document
        numeric = compat.element_id_value(floor.Id)
        if link_instance is None:
            self.link_key = ""
            self.log_id = str(numeric)
            self.label = "{} ID {}".format(compat.element_kind(floor), numeric)
        else:
            name = compat.element_name(link_instance)
            self.link_key = link_instance.UniqueId
            self.log_id = "{} (link '{}')".format(numeric, name)
            self.label = "{} ID {} (link '{}')".format(compat.element_kind(floor), numeric, name)

    @property
    def is_linked(self):
        return self.link_instance is not None

    @property
    def source_key(self):
        """Unique per Floor AND link instance (a link can be loaded twice)."""
        if self.link_instance is None:
            return self.floor.UniqueId
        return "{}|{}".format(self.link_key, self.floor.UniqueId)


class SelectionResult(object):
    def __init__(self, items, ignored=0, notes=None):
        self.items = items
        self.ignored = ignored
        self.notes = notes or []


# ------------------------------------------------------------------ filters --
class FloorSelectionFilter(ISelectionFilter):
    """Host model: only Floors (incl. structural slabs) and Toposolids can be clicked."""

    def AllowElement(self, element):
        return compat.is_supported_element(element)

    def AllowReference(self, reference, position):
        return False


class LinkedFloorSelectionFilter(ISelectionFilter):
    """Linked models: link instances may be hovered; the referenced element is
    checked when Revit asks (if it cannot be checked it is allowed and filtered
    after the pick)."""

    def __init__(self, doc):
        self._doc = doc

    def AllowElement(self, element):
        return isinstance(element, DB.RevitLinkInstance)

    def AllowReference(self, reference, position):
        try:
            link = self._doc.GetElement(reference.ElementId)
            element = link.GetLinkDocument().GetElement(reference.LinkedElementId)
            return compat.is_supported_element(element)
        except Exception:
            return True


# ---------------------------------------------------------------- host pick --
def _host_items(doc, element_ids):
    items, ignored, seen = [], 0, set()
    for element_id in element_ids:
        element = doc.GetElement(element_id)
        if compat.is_supported_element(element):
            if element.UniqueId not in seen:
                seen.add(element.UniqueId)
                items.append(FloorItem(element))
        else:
            ignored += 1
    return items, ignored


def _pick_host(uidoc):
    doc = uidoc.Document
    items, ignored = _host_items(doc, uidoc.Selection.GetElementIds())   # preselection first
    if items:
        return SelectionResult(items, ignored)
    try:
        references = uidoc.Selection.PickObjects(
            ObjectType.Element, FloorSelectionFilter(),
            "Select Floors and/or Toposolids, then click Finish")
    except OperationCanceledException:
        return None
    items, _ = _host_items(doc, [r.ElementId for r in references])
    return SelectionResult(items, ignored)


# -------------------------------------------------------------- linked pick --
def _pick_linked(uidoc):
    doc = uidoc.Document
    try:
        references = uidoc.Selection.PickObjects(
            ObjectType.LinkedElement, LinkedFloorSelectionFilter(doc),
            "Select Floors and/or Toposolids in linked models, then click Finish")
    except OperationCanceledException:
        return None

    items, seen, ignored, unloaded = [], set(), 0, set()
    for reference in references:
        link = doc.GetElement(reference.ElementId)
        if not isinstance(link, DB.RevitLinkInstance):
            ignored += 1
            continue
        link_doc = link.GetLinkDocument()
        if link_doc is None:
            unloaded.add(compat.element_name(link))     # link is unloaded / not accessible
            continue
        element = link_doc.GetElement(reference.LinkedElementId)
        if not compat.is_supported_element(element):
            ignored += 1
            continue
        item = FloorItem(element, link, compat.get_link_transform(link))
        if item.source_key not in seen:
            seen.add(item.source_key)
            items.append(item)
    notes = []
    if unloaded:
        notes.append("Skipped elements of unloaded link(s): {}. Load the link and run again."
                     .format(", ".join(sorted(unloaded))))
    return SelectionResult(items, ignored, notes)


def get_floor_items(uidoc, linked):
    """SelectionResult, or None when the user cancelled."""
    return _pick_linked(uidoc) if linked else _pick_host(uidoc)
