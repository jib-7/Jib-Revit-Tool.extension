# -*- coding: utf-8 -*-
"""Orchestration: one Transaction, one SubTransaction per Floor, progress bar,
per-floor error isolation. Contains no UI code besides the progress bar."""
from Autodesk.Revit import DB
from pyrevit import forms

from floor_tools import curve_loops, fill_region, floor_geometry, floor_style, settings, utils
from floor_tools import revit_compat as compat


class RunOptions(object):
    def __init__(self, region_type_id, offset_ft=0.0, prevent_duplicates=True,
                 use_floor_style=False, pattern_source=settings.PATTERN_SOURCE_SURFACE):
        self.region_type_id = region_type_id          # selected type (base type when styling)
        self.offset_ft = offset_ft
        self.prevent_duplicates = prevent_duplicates
        self.use_floor_style = use_floor_style        # type per Floor type, named after it
        self.pattern_source = pattern_source


class _Context(object):
    """Everything computed once per run and shared by all floors."""

    def __init__(self, doc, view, options, log):
        self.doc, self.view, self.options, self.log = doc, view, options, log
        origin, normal = compat.get_view_plane(view)
        self.basis = curve_loops.PlaneBasis(origin, normal)
        self.min_len = compat.short_curve_tolerance(doc.Application) * 1.05
        self.schema = None
        self.index = {}
        self.base_type = doc.GetElement(options.region_type_id)
        self.types_by_name = {}       # existing + newly created Filled Region Types
        self.style_cache = {}         # Floor type id -> FloorStyle (read once per type)
        self.new_type_names = []      # created while processing the current floor
        self.summary_types = []       # all types created in this run


class _NoProgress(object):
    cancelled = False

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def update_progress(self, *args, **kwargs):
        pass


def _progress(total):
    if total >= settings.PROGRESS_BAR_THRESHOLD:
        return forms.ProgressBar(title="Floor to Fill Region... ({value} of {max_value})",
                                 cancellable=True)
    return _NoProgress()


def _resolve_region_type(item, ctx):
    """Filled Region Type for this floor. Returns (type id, warnings)."""
    if not ctx.options.use_floor_style:
        return ctx.options.region_type_id, []
    floor = item.floor
    key = (item.link_key, compat.element_id_value(floor.GetTypeId()))   # type ids are per document
    style = ctx.style_cache.get(key)
    if style is None:
        style = floor_style.read_floor_style(floor, ctx.options.pattern_source)
        ctx.style_cache[key] = style
    type_id, created, warnings = floor_style.get_or_create_region_type(
        ctx.doc, ctx.base_type, style, ctx.types_by_name)
    if created:
        ctx.new_type_names.append(style.name)
        ctx.log.info("Created Filled Region Type '{}'.".format(style.name))
        return type_id, list(style.warnings) + warnings
    return type_id, []


def _create_for_floor(item, ctx):
    """Extract, project, (offset), validate and create. Returns (regions, warnings)."""
    # For linked floors the boundary is moved into host coordinates first (item.transform).
    footprint = floor_geometry.extract_footprint(item.floor, ctx.min_len, item.transform)
    ctx.log.info("Boundary via {} ({} group(s)).".format(footprint.method, len(footprint.groups)),
                 item.log_id)
    warnings = list(footprint.warnings)
    type_id, type_warnings = _resolve_region_type(item, ctx)
    warnings.extend(type_warnings)
    regions = []
    for raw_group in footprint.groups:
        # 3D face loops -> planar loops in the view plane (floor thickness,
        # elevation and slope are irrelevant for a 2D annotation).
        group, approximated = curve_loops.project_group(raw_group, ctx.basis, ctx.min_len)
        if approximated:
            warnings.append("Some curves were approximated by straight segments.")
        if abs(ctx.options.offset_ft) > 0.0:
            try:
                shifted = curve_loops.offset_group(group, ctx.options.offset_ft, ctx.basis)
                problems = curve_loops.validate_group(shifted, ctx.basis)
                if problems:
                    raise curve_loops.GeometryError(" ".join(problems))
                group = shifted
            except Exception as ex:
                warnings.append("Offset ignored, original boundary used ({}).".format(
                    utils.friendly_message(ex)))
        problems = curve_loops.validate_group(group, ctx.basis)
        if problems:
            raise curve_loops.GeometryError(" ".join(problems))
        region = fill_region.create_region(ctx.doc, ctx.view, type_id, group)
        if ctx.schema is not None:
            fill_region.tag_region(region, ctx.schema, item.source_key)
        regions.append(region)
    return regions, warnings


def _process_floor(item, ctx):
    floor_id = item.floor.Id
    numeric_id = item.log_id
    uid = item.source_key
    linkable = not item.is_linked
    if ctx.options.prevent_duplicates and uid in ctx.index:
        ctx.log.info("Skipped: a Fill Region for this Floor already exists in the view.", numeric_id)
        return utils.FloorResult(floor_id, utils.STATUS_EXISTING, label=item.label, linkable=linkable)

    sub = DB.SubTransaction(ctx.doc)      # isolates a failing floor from the rest
    sub.Start()
    ctx.new_type_names = []
    try:
        regions, warnings = _create_for_floor(item, ctx)
        sub.Commit()
    except Exception as ex:
        try:
            sub.RollBack()
        except Exception:
            pass
        for name in ctx.new_type_names:   # types created by this floor were rolled back too
            ctx.types_by_name.pop(name, None)
        ctx.new_type_names = []
        ctx.log.error(utils.friendly_message(ex), numeric_id)
        ctx.log.add_traceback(numeric_id)
        return utils.FloorResult(floor_id, utils.STATUS_FAILED, utils.friendly_message(ex),
                                 label=item.label, linkable=linkable)

    ctx.index[uid] = [r.Id for r in regions]
    ctx.summary_types.extend(ctx.new_type_names)
    for warning in warnings:
        ctx.log.warning(warning, numeric_id)
    return utils.FloorResult(floor_id, utils.STATUS_CREATED, regions=len(regions), warnings=warnings,
                             label=item.label, linkable=linkable)


def run(doc, view, floors, options, log):
    """Process all FloorItems inside ONE undoable transaction; returns a RunSummary."""
    summary = utils.RunSummary(len(floors))
    ctx = _Context(doc, view, options, log)

    try:
        ctx.schema = fill_region.get_schema(create=True)
    except Exception as ex:
        ctx.schema = None
        note = ("Duplicate tracking is unavailable ({}); Fill Regions were created without a "
                "link to their Floors.".format(utils.friendly_message(ex)))
        summary.notes.append(note)
        log.warning(note)
    if options.prevent_duplicates and ctx.schema is not None:
        ctx.index = fill_region.build_source_index(doc, view, ctx.schema)   # single pass

    if options.use_floor_style:
        for region_type in fill_region.collect_region_types(doc):   # single pass
            ctx.types_by_name[compat.element_name(region_type)] = region_type

    transaction = DB.Transaction(doc, settings.TRANSACTION_NAME)
    transaction.Start()
    try:
        with _progress(len(floors)) as bar:
            for position, floor in enumerate(floors):
                if bar.cancelled:
                    summary.cancelled = True
                    for rest in floors[position:]:
                        summary.add(utils.FloorResult(rest.floor.Id, utils.STATUS_NOT_PROCESSED,
                                                      label=rest.label, linkable=not rest.is_linked))
                    break
                bar.update_progress(position + 1, len(floors))
                summary.add(_process_floor(floor, ctx))
    except Exception:
        transaction.RollBack()
        raise

    summary.types_created = list(ctx.summary_types)
    if summary.regions_created == 0:
        transaction.RollBack()            # keep the undo stack clean
    else:
        status = transaction.Commit()
        if status != DB.TransactionStatus.Committed:
            raise utils.FloorToolsError(
                "Revit could not commit the changes ({}). Nothing was created.".format(status))
    return summary
