# -*- coding: utf-8 -*-
"""Fill Planter Cavity (026)

Click inside the soil area of a planter section/detail view. The tool detects the
closed cavity boundary (closing small gaps), creates the 026 Filled Region and
derives the 005 / 006 / 008 line-based Detail Items and the 010 Detail Component
from the actual 026 geometry. Everything is created in ONE transaction.

Shift+Click the button to edit settings.
"""
__title__ = "Fill Planter\nCavity (026)"
__author__ = "BIM Automation"
__min_revit_ver__ = 2022

import traceback

from Autodesk.Revit.DB import ViewType
from Autodesk.Revit.Exceptions import OperationCanceledException
from pyrevit import forms, revit, script

from planter_cavity import (boundary_detector, detail_item_placer, duplicate_checker,
                            family_finder, filled_region_creator, geometry_collector,
                            halftone_override, layout_calculator, models, report,
                            revit_utils, settings)
from planter_cavity.models import PlanterError, internal_to_mm, mm_to_internal
from planter_cavity.transaction_manager import SafeTransaction

TITLE = "Fill Planter Cavity (026)"
ALLOWED_VIEWS = (ViewType.Section, ViewType.Detail, ViewType.DraftingView, ViewType.Elevation,
                 ViewType.FloorPlan, ViewType.CeilingPlan, ViewType.EngineeringPlan)

out = script.get_output()


def say(text):
    out.print_md(text)


def choose_from(labels, title):
    sel = forms.SelectFromList.show(labels, title=title, button_name="Select", multiselect=False)
    if sel is None:
        return None
    return labels.index(sel)


def describe_candidate(i, loop):
    x0, y0, x1, y1 = loop.bbox()
    area_m2 = loop.area * (internal_to_mm(1.0) / 1000.0) ** 2
    bridges = ", ".join("%.0f mm%s" % (internal_to_mm(b['length']), " (top)" if b['top'] else "")
                        for b in loop.bridges) or "none"
    return "Option %d - area %.3f m2, %.0f x %.0f mm, closed gaps: %s" % (
        i + 1, area_m2, internal_to_mm(x1 - x0), internal_to_mm(y1 - y0), bridges)


def run():
    doc, uidoc = revit.doc, revit.uidoc
    view = doc.ActiveView
    rep = report.Report()

    if view.IsTemplate or view.ViewType not in ALLOWED_VIEWS:
        forms.alert("Open a planter section, detail or drafting view first.\n\n"
                    "Active view type '%s' is not supported." % view.ViewType, title=TITLE)
        return

    s = settings.load_settings()
    cfg = settings.Config(s, mm_to_internal)
    frame = revit_utils.frame_from_view(view)

    # ---- 1. families --------------------------------------------------
    say("**Fill Planter Cavity (026)**  \n1/6 Checking Filled Region Type and families...")
    res = family_finder.resolve_all(doc, s, choose_from)
    for w in res.warnings:
        rep.warn(w)
    if res.errors:
        forms.alert("Cannot continue - missing or unsuitable families:\n\n- " + "\n- ".join(res.errors) +
                    "\n\nLoad the families into the project (or check their names/placement type) and run again.",
                    title=TITLE, warn_icon=True)
        for e in res.errors:
            say("- :x: " + e)
        return
    for role in ("005", "006", "008"):
        info = None
        if s.get("inspect_families_deep", True):
            info = detail_item_placer.inspect_family(doc, res.symbols[role].Family)
        if info:
            say("Family %s: placement=%s, reference lines=%s, detail curves=%s, filled regions=%s. "
                "A line-based instance is ONE straight line, so the U-shape is built from several instances."
                % (role, info.get('placement'), info.get('reference_lines', '?'),
                   info.get('curve_elements', '?'), info.get('filled_regions', '?')))
            for n in info.get('notes', []):
                rep.warn("%s: %s" % (role, n))

    # ---- 2. pick point ------------------------------------------------
    say("2/6 Waiting for a click inside the planter soil area...")
    try:
        pt = uidoc.Selection.PickPoint("Click INSIDE the planter soil area (Esc to cancel)")
    except OperationCanceledException:
        return
    except Exception as ex:
        forms.alert("Could not pick a point in this view:\n%s\n\nUse a section, detail or drafting view."
                    % ex, title=TITLE, warn_icon=True)
        return
    pick_uv = frame.to_uv(revit_utils.xyz_t(pt))

    # ---- 3. geometry + detection ---------------------------------------
    say("3/6 Collecting Detail Lines and Detail Components...")
    exclude = []
    if s.get("exclude_output_families_from_boundary", True):
        exclude = [s["line005_token"], s["line006_token"], s["line008_token"], s["point010_token"]]
    prims, stats = geometry_collector.collect_primitives(doc, view, frame, cfg, exclude)
    say("   %d detail lines, %d detail components, %d curves collected (%d output-family items ignored)."
        % (stats.detail_curves, stats.components, stats.curves, stats.excluded_output))
    for e in stats.errors[:5]:
        rep.warn(e)
    say("4/6 Detecting the closed boundary around the click...")
    det = boundary_detector.detect(prims, pick_uv, cfg)
    if det.status == 'fail':
        forms.alert("Geometry error - no closed boundary:\n\n" + "\n".join(det.messages) +
                    "\n\nTips: click inside the soil area, make sure the walls are Detail Lines / Detail "
                    "Components (not model elements), and check max gap settings (Shift+Click).",
                    title=TITLE, warn_icon=True)
        return
    loop = det.candidates[0]
    if det.status == 'ambiguous':
        labels = [describe_candidate(i, c) for i, c in enumerate(det.candidates)]
        idx = choose_from(labels, "Ambiguous boundary - choose the cavity outline")
        if idx is None:
            return
        loop = det.candidates[idx]
        rep.warn("Ambiguous boundary: option %d chosen by the user." % (idx + 1))
    for b in loop.bridges:
        say("   closed a %.0f mm gap%s." % (internal_to_mm(b['length']), " at the open top" if b['top'] else ""))

    # ---- 5. layout -----------------------------------------------------
    say("5/6 Calculating 005 / 006 / 008 / 010 geometry from the 026 region...")
    try:
        lay = layout_calculator.compute_layout(loop, cfg)
    except PlanterError as ex:
        forms.alert("Geometry error:\n\n%s" % ex, title=TITLE, warn_icon=True)
        return
    for t in lay.info:
        say("   " + t)
    rep.warnings.extend(lay.warnings)

    sig = duplicate_checker.loop_signature(loop)
    dups = duplicate_checker.find_duplicates(doc, view, frame, loop, pick_uv, s["region_type_token"],
                                             sig, cfg.snap_tol)
    if dups:
        forms.alert("Duplicate prevention - nothing was created.\n\n- " + "\n- ".join(dups) +
                    "\n\nDelete the existing elements first if you want to regenerate them.",
                    title=TITLE, warn_icon=True)
        return

    # ---- 6. create ------------------------------------------------------
    say("6/6 Creating elements (single transaction)...")
    tag = s.get("write_tag_comments", True)
    try:
        with SafeTransaction(doc, TITLE):
            for role in ("005", "006", "008", "010"):
                detail_item_placer.ensure_active(doc, res.symbols[role])
            region = filled_region_creator.create_filled_region(doc, view, frame, res.region_type,
                                                                loop, cfg.min_seg)
            e005 = detail_item_placer.place_polyline(doc, view, res.symbols["005"], frame,
                                                     lay.lines005, cfg.min_seg)
            e006 = detail_item_placer.place_polyline(doc, view, res.symbols["006"], frame,
                                                     lay.lines006, cfg.min_seg)
            e008 = detail_item_placer.place_polyline(doc, view, res.symbols["008"], frame,
                                                     lay.lines008, cfg.min_seg)
            e010 = detail_item_placer.place_point(doc, view, res.symbols["010"], frame, lay.point010)
            halftone_state = "Applied"
            try:
                halftone_override.apply_halftone(view, e010)
            except Exception as ex:
                if s.get("fail_on_halftone_error", True):
                    raise PlanterError("Halftone override failed: %s" % ex)
                halftone_state = "Not applied (%s)" % ex
                rep.warn("Halftone override failed: %s" % ex)
            if tag:
                revit_utils.set_comment(region, duplicate_checker.make_tag(sig, "026"))
                for role, els in (("005", e005), ("006", e006), ("008", e008), ("010", [e010])):
                    for el in els:
                        revit_utils.set_comment(el, duplicate_checker.make_tag(sig, role))
    except PlanterError as ex:
        forms.alert("Nothing was created (transaction rolled back).\n\n%s" % ex, title=TITLE, warn_icon=True)
        return
    except Exception as ex:
        say("```\n%s\n```" % traceback.format_exc())
        forms.alert("Unexpected error - the transaction was rolled back, nothing was created.\n\n%s" % ex,
                    title=TITLE, warn_icon=True)
        return

    rep.results = {
        "026": "Created",
        "005": "Created (%d line-based instances)" % len(e005),
        "006": "Created (%d line-based instances)" % len(e006),
        "008": "Created (%d line-based instances)" % len(e008),
        "010": "Created",
        "halftone": halftone_state,
    }
    text = rep.render_result()
    say("```\n%s\n```" % text)
    for w in rep.warnings:
        say("- :warning: " + w)
    forms.alert(text + ("\n\nNotes:\n- " + "\n- ".join(rep.warnings) if rep.warnings else ""), title=TITLE)


try:
    run()
except Exception as _ex:
    say("```\n%s\n```" % traceback.format_exc())
    forms.alert("Unexpected error: %s" % _ex, title=TITLE, warn_icon=True)
