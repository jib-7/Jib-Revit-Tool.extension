# -*- coding: utf-8 -*-
"""Find every Filled Region in the active document whose TYPE has Type Comments = Planting."""
from Autodesk.Revit.DB import FilteredElementCollector, FilledRegion

from planting_tools import config, parameters


class PlantingItem(object):
    """One qualifying Filled Region."""
    def __init__(self, element, type_name, type_comments):
        self.element = element
        self.type_name = type_name
        self.type_comments = type_comments


class ScanResult(object):
    def __init__(self):
        self.total = 0                 # all Filled Regions in the document
        self.items = []                # qualifying PlantingItem objects
        self.excluded_other = 0        # Type Comments has another value
        self.excluded_empty = 0        # Type Comments is empty
        self.excluded_no_param = 0     # type has no Type Comments parameter


def _classify_type(doc, type_id):
    """Return (category, type_name, raw_comments) for one Filled Region type."""
    type_element = doc.GetElement(type_id)
    type_name = parameters.get_type_name(type_element)
    found, comments = parameters.read_type_comments(type_element)
    if not found:
        return "no_param", type_name, ""
    cleaned = comments.strip().lower()
    if not cleaned:
        return "empty", type_name, comments
    if cleaned == config.TYPE_COMMENTS_EXPECTED:
        return "planting", type_name, comments
    return "other", type_name, comments


def collect_planting_regions(doc):
    """Scan the whole document (linked models are not included by FilteredElementCollector)."""
    result = ScanResult()
    regions = FilteredElementCollector(doc).OfClass(FilledRegion).ToElements()
    cache = {}                         # one lookup per type, not per element
    for region in regions:
        result.total += 1
        type_id = region.GetTypeId()
        key = parameters.eid_value(type_id)
        if key not in cache:
            cache[key] = _classify_type(doc, type_id)
        category, type_name, comments = cache[key]
        if category == "planting":
            result.items.append(PlantingItem(region, type_name, comments))
        elif category == "other":
            result.excluded_other += 1
        elif category == "empty":
            result.excluded_empty += 1
        else:
            result.excluded_no_param += 1
    return result
