# Filled Region Boundary Manager  (pyRevit extension)

Manage the boundary Line Styles of Filled Regions: select, create / duplicate / edit real Revit Line Styles,
preview before/after, save without applying, apply (all boundaries, ticked segments, active view, by type),
batch-replace, audit, presets, execution report.

Targets Revit 2024 / 2025 / 2026 with pyRevit (IronPython engine, the pyRevit default).

## Install
1. Extract this ZIP.
2. Copy the folder `FilledRegionBoundaryManager.extension` into your pyRevit extensions folder, or add its parent
   folder via pyRevit > Settings > Custom Extension Directories.
3. pyRevit > Reload.
4. Ribbon: **FilledRegionBoundaryManager > Graphics > Boundary Manager**.

## Workflow
SELECT (tab 1) -> CREATE / DUPLICATE (tab 2) -> CUSTOMISE -> NAME -> PREVIEW -> **SAVE LINE STYLE** -> **APPLY**.
* SAVE LINE STYLE creates a genuine Revit subcategory under *Lines* (visible in Manage > Object Styles > Lines and
  stored in the .rvt). It never touches Filled Regions and works with nothing selected.
* SAVE & APPLY creates the style and applies it as ONE undo step. If nothing could be applied because of failures,
  the creation is rolled back too.
* SAVE AS PRESET writes the values (weight, RGB, pattern *name*) to an external JSON library - not a Revit style.
* Names are validated (empty / invalid characters / duplicates). Existing styles are never overwritten.
* Tab 3 manages custom styles (rename, duplicate, edit, delete with usage count and reassignment). Tab 4 = presets
  (import/export; pattern availability and name clashes are checked). Tab 5 = batch replace. Tab 6 = read-only audit.

## How boundaries are modified (API notes)
* `FilledRegion.GetBoundaries()` returns only geometry (CurveLoops) - no line style - so it cannot be used to read
  or change styles. The boundary segments are exposed as dependent `CurveElement`s of the region
  (`GetDependentElements`), each with its own `LineStyle`. The tool changes that property per segment.
* `SetBoundaries()` is deliberately **not** used: it rebuilds the sketch and could alter geometry/loops/direction.
  Geometry, loops, type, fill patterns and location are therefore untouched by construction.
* Each region is processed in its own SubTransaction (all-or-nothing per region), inside a Transaction inside a
  TransactionGroup, so failures never leave a region half-changed and Undo works as one step.
* "Selected segments only" is supported through the segment table in tab 1 (each segment is identified by its own
  ElementId). Revit does not let you click an individual boundary line in the model outside sketch mode.
* Revit Links are never touched (only native elements of the active document are selected/processed).

## Known limitations (please read)
1. **NOT TESTED INSIDE REVIT.** No Revit installation was available while this was written. It was checked with
   syntax compilation, XAML well-formedness, handler/control name cross-checks, an import check of every module and
   logic tests (names, colours, presets, reports) against stubbed Revit modules. Real-Revit behaviour (especially
   items 2-3) must be verified by you with the acceptance tests below. Check Revit/pyRevit error output if
   something fails; details are written to `%APPDATA%\pyRevit\FilledRegionBoundaryManager\last_error.log`.
2. Setting `CurveElement.LineStyle` on Filled Region boundary segments is the documented/known technique, but if a
   particular Revit build refuses it, the tool reports the segment as FAILED, rolls that region back and tells you -
   it never fakes success.
3. The set of boundary segments is read with `GetDependentElements`; if a Revit version returned none for a region,
   it shows "(no boundary found)".
4. **Line weights in mm are reference values.** The Revit API exposes the weight number (1-16) but not the project's
   *Additional Settings > Line Weights* table, so the mm column is approximate. To match your template create
   `%APPDATA%\pyRevit\FilledRegionBoundaryManager\line_weights.json`, e.g. `{"1": 0.18, "2": 0.25, "3": 0.35}`.
5. **Cut line weight is not applicable** to Line Styles (they only have a projection weight), so it is not set.
6. A line style cannot have an arbitrary custom thickness; "Snap to nearest weight" picks the closest of 1-16.
7. Which styles are "original" for duplicates is remembered in `style_origins.json` (outside the model).
8. Built-in styles cannot be renamed, edited or deleted from this tool; duplicate them instead.
9. If you edit sources, use pyRevit > Reload (the IronPython engine caches modules). The CPython engine is not
   supported; keep the default IronPython engine.

## Acceptance tests to run in Revit (A-H)
A. Select 5 regions, apply an existing style -> only their boundaries change.
B. Duplicate "Landscape Boundary" as "Landscape Boundary - Custom", change weight/colour/pattern -> original unchanged.
C. New style "Planting Boundary - Custom", SAVE with nothing selected -> appears in Manage > Object Styles > Lines.
D. Create style + SAVE & APPLY on selected regions -> only those boundaries change; one Ctrl+Z reverts both.
E. Save a preset, close and reopen the tool, load it -> values remain.
F. Unrelated elements using the original style are unchanged.
G. Save, close, reopen the project -> custom styles still exist.
H. Try empty/invalid/duplicate names, a missing pattern (import a preset), a read-only/workshared-locked region.

## Folder contents
BoundaryManager.pushbutton: script.py, bundle.yaml, icon.png, ui/ (main_window.xaml/.py, colour_picker.xaml,
preview_control.xaml), lib/ (selection, filled_region_manager, boundary_manager, line_style_manager,
line_weight_manager, line_pattern_manager, colour_manager, preview_manager, preset_manager, transaction_manager,
batch_replace, project_audit, report_manager, revit_compat, utils), presets/default_presets.json.
Preset library (editable): `%APPDATA%\pyRevit\FilledRegionBoundaryManager\presets.json`.
