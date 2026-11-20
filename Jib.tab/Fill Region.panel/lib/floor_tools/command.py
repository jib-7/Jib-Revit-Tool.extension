# -*- coding: utf-8 -*-
"""Shared command flow for 'Floor -> Fill Region' (host floors) and
'Linked Floor -> Fill Region' (floors of linked Revit models).

Pushbutton scripts only call execute(); everything else lives here so new
commands can reuse the same building blocks."""
from pyrevit import revit

from floor_tools import fill_region, selection, settings, ui, utils, workflow
from floor_tools import revit_compat as compat


def _run(log, linked):
    ok, message = compat.check_version()
    if not ok:
        utils.warn(message)
        return
    if message:
        log.warning(message)
    log.info("Revit version detected: {}; source: {}".format(
        compat.REVIT_VERSION or "unknown", "linked models" if linked else "active model"))

    doc, uidoc = revit.doc, revit.uidoc
    view = doc.ActiveView

    # 1. Validate the view BEFORE asking for anything: nothing is created in an invalid view.
    ok, message = fill_region.validate_view(view)
    if not ok:
        utils.warn(message)
        return

    # 2. Floors (host: preselection, otherwise prompt; linked: prompt).
    picked = selection.get_floor_items(uidoc, linked)
    if picked is None:
        return                                   # user pressed Esc
    if not picked.items:
        if linked:
            utils.warn("No Floors or Toposolids from linked models were selected.",
                       sub_msg="; ".join(picked.notes) or
                       "Click Floors or Toposolids inside a loaded Revit link and finish the selection.")
        else:
            utils.warn("No Floors or Toposolids were selected.",
                       sub_msg="Select one or more Floors (or Toposolids in Revit 2024+) and run the command again.")
        return

    # 3. Options.
    region_types = fill_region.collect_region_types(doc)
    if not region_types:
        utils.warn("This project has no Filled Region Types.",
                   sub_msg="Create one in Manage > Additional Settings > Filled Region.")
        return
    user_settings = settings.load()
    type_index = fill_region.find_type_index(
        region_types, user_settings.region_type_uid, user_settings.region_type_name)
    title = u"Linked Floor / Toposolid \u2192 Fill Region" if linked else u"Floor / Toposolid \u2192 Fill Region"
    link_count = len(set(i.link_key for i in picked.items))
    note = " (from {} link{})".format(link_count, "" if link_count == 1 else "s") if linked else ""
    choice = ui.ask_options(doc, view, region_types, len(picked.items), type_index, user_settings,
                            title=title, source_note=note)
    if choice is None:
        return
    log.echo = choice.verbose

    user_settings.region_type_uid = choice.region_type.UniqueId
    user_settings.region_type_name = compat.element_name(choice.region_type)
    user_settings.offset_text = choice.offset_text
    user_settings.prevent_duplicates = choice.prevent_duplicates
    user_settings.verbose_log = choice.verbose
    user_settings.use_floor_style = choice.use_floor_style
    user_settings.pattern_source = choice.pattern_source
    settings.save(user_settings)

    # 4. Do the work and report.
    options = workflow.RunOptions(choice.region_type.Id, choice.offset_ft, choice.prevent_duplicates,
                                  choice.use_floor_style, choice.pattern_source)
    summary = workflow.run(doc, view, picked.items, options, log)
    summary.ignored_non_floors = picked.ignored
    summary.notes.extend(picked.notes)
    utils.show_summary(summary, log)


def execute(linked=False):
    """Entry point used by the pushbutton scripts."""
    log = utils.DetailLog()
    try:
        _run(log, linked)
    except Exception as ex:                      # never show a stack trace to the user
        log.add_traceback()
        utils.report_unexpected(ex, log)
    finally:
        log.flush()
