# -*- coding: utf-8 -*-
"""Filled Region creation, type lookup, view validation and duplicate tracking
via Extensible Storage (the source Floor's UniqueId is stored on each region)."""
import System
from Autodesk.Revit import DB
from Autodesk.Revit.DB.ExtensibleStorage import AccessLevel, Entity, Schema, SchemaBuilder

from floor_tools import settings
from floor_tools import revit_compat as compat
from floor_tools.utils import FloorToolsError, friendly_message


class FillRegionError(FloorToolsError):
    """Revit refused to create the Filled Region."""


# -------------------------------------------------------------------- views --
def validate_view(view):
    """(ok, message) - can this view receive plan Filled Regions from Floors?"""
    if view is None:
        return False, "There is no active view."
    if getattr(view, "IsTemplate", False):
        return False, "The active view is a view template. Open a plan view instead."
    view_type = str(view.ViewType)
    if view_type not in settings.SUPPORTED_VIEW_TYPE_NAMES:
        return False, ("Fill Regions cannot be created from Floors in a '{}' view.\n"
                       "Open a Floor Plan, Ceiling Plan or Engineering Plan and run the "
                       "command again.".format(view_type))
    return True, ""


# -------------------------------------------------------------------- types --
def collect_region_types(doc):
    """All Filled Region Types, sorted by name (collected once per run)."""
    types = list(DB.FilteredElementCollector(doc).OfClass(DB.FilledRegionType))
    types.sort(key=lambda t: compat.element_name(t).lower())
    return types


def find_type_index(types, unique_id, name):
    """Index of the remembered type (UniqueId first, then name), else 0."""
    for index, region_type in enumerate(types):
        if unique_id and region_type.UniqueId == unique_id:
            return index
    for index, region_type in enumerate(types):
        if name and compat.element_name(region_type) == name:
            return index
    return 0


# --------------------------------------------------------- extensible storage
def get_schema(create=True):
    """The schema holding the source-Floor link. Public read/write on purpose:
    Vendor-level write access would compare against pyRevit's own add-in
    manifest and reject writes from scripts."""
    guid = System.Guid(settings.ES_SCHEMA_GUID)
    schema = Schema.Lookup(guid)
    if schema is not None or not create:
        return schema
    builder = SchemaBuilder(guid)
    builder.SetSchemaName(settings.ES_SCHEMA_NAME)
    builder.SetDocumentation("UniqueId of the Floor a Filled Region was generated from.")
    builder.SetReadAccessLevel(AccessLevel.Public)
    builder.SetWriteAccessLevel(AccessLevel.Public)
    builder.SetVendorId(settings.ES_VENDOR_ID)
    builder.AddSimpleField(settings.ES_FIELD_SOURCE, System.String)
    return builder.Finish()


def tag_region(region, schema, floor_unique_id):
    """Store the source Floor's UniqueId on the region (needs an open transaction)."""
    entity = Entity(schema)
    entity.Set[System.String](settings.ES_FIELD_SOURCE, floor_unique_id)
    region.SetEntity(entity)


def _read_source_uid(region, schema):
    try:
        entity = region.GetEntity(schema)
        if entity is not None and entity.IsValid():
            return entity.Get[System.String](settings.ES_FIELD_SOURCE)
    except Exception:
        pass
    return None


def build_source_index(doc, view, schema):
    """{floor UniqueId: [region ElementIds]} for regions already in this view.
    One collector pass per run - never per floor."""
    index = {}
    if schema is None:
        return index
    for region in DB.FilteredElementCollector(doc, view.Id).OfClass(DB.FilledRegion):
        uid = _read_source_uid(region, schema)
        if uid:
            index.setdefault(uid, []).append(region.Id)
    return index


# ----------------------------------------------------------------- creation --
def create_region(doc, view, region_type_id, group):
    """Create one Filled Region from a LoopGroup (outer loop + openings)."""
    loops = compat.to_clr_list(group.loops(), DB.CurveLoop)
    try:
        # Revit validates that loops are closed, planar, parallel to the view,
        # non-self-intersecting and that openings are nested inside the outline.
        return DB.FilledRegion.Create(doc, region_type_id, view.Id, loops)
    except Exception as ex:
        raise FillRegionError("Revit could not create the Filled Region. {}".format(friendly_message(ex)))
