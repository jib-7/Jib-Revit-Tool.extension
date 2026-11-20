# FloorTools.extension — Floor → Fill Region

A pyRevit extension that creates **Filled Regions** in the active plan view from selected **Floors** — and (Revit 2024+) **Toposolids**, from the active model or from **linked Revit models** — preserving openings, without ever modifying the Floors.

Two buttons: **Floor / Toposolid → Fill Region** and **Linked Floor / Toposolid → Fill Region** (same dialog, same options, same result).

> **Status:** written against the Revit API for Revit 2021–2026 and syntax-checked. The pure-geometry helpers (`geometry2d.py`) are unit-tested; the Revit-facing code has **not** been run inside Revit yet. Run the test procedure in section 9 before using it on production models.

---

## 1. Revit API limitations (analysis)

| Topic | Limitation | Design consequence |
|---|---|---|
| `FilledRegion.Create` | Needs closed, planar, non-self-intersecting `CurveLoop`s parallel to the view; openings must be nested in the outline; curves shorter than `Application.ShortCurveTolerance` are rejected; full circles are not allowed | Loops are projected, validated and healed *before* the API call |
| Floor has no "footprint" API | A Floor is a 3D solid; there is no call returning its 2D outline | Boundary is read from the solid's top face |
| `SpatialElementGeometryCalculator`, `BoundarySegment` | Room/Space tools — they do not accept Floors | Deliberately **not** used (the brief listed them "where appropriate"; here they are not) |
| Floor sketch (`Sketch.Profile`) | Only the sketch the user drew: ignores cuts from Opening elements, joins and shape edits | Used only as a fallback |
| Sloped / shape-edited floors | Top face is tilted (one face) or split into many faces | Tilted faces are projected; split tops fall back to the sketch outline |
| Arcs on a tilted plane | Their true projection is an ellipse | Approximated by a fine polyline (reported as a warning) |
| Filled Region types | Editing a type changes **every** region using it | Types are never edited; new types are only created (duplicated) per Floor type, existing ones are reused as they are |
| Extensible Storage | `AccessLevel.Vendor` write is checked against the running add-in's manifest (pyRevit's, not ours) | Schema uses Public read/write |
| Views | No Filled Regions in 3D views, sheets, schedules, view templates; Sections/Elevations would flatten a floor to a line | Plan views only (`FloorPlan`, `CeilingPlan`, `EngineeringPlan`, `AreaPlan`), configurable in `settings.py` |
| Linked models | Elements live in another `Document` with their own coordinates, ElementIds, types, materials and fill patterns | Separate command: geometry is read in the link and moved with the link instance transform; patterns are mapped into the host (section 9) |

## 2. Installation

1. Copy the whole `FloorTools.extension` folder to a location of your choice, e.g. `C:\PyRevitExtensions\`.
2. In Revit: **pyRevit tab → Settings → Custom Extension Directories → Add Folder** → select `C:\PyRevitExtensions\` (the folder that *contains* `FloorTools.extension`).
3. **Save Settings and Reload.** A **FloorTools** tab appears with the **Floor → Fill Region** button.

(Alternatively copy the folder to `%APPDATA%\pyRevit\Extensions\` and reload.)

Requires pyRevit 4.8+ (5.x for Revit 2025/2026). No third-party packages. The code is written in a Python 2.7 / 3 compatible subset (no f-strings), so it runs on the IronPython 2.7, IronPython 3 and CPython engines.

## 3. Usage

1. Open a **plan view** (Floor / Ceiling / Engineering Plan).
2. Preselect Floors, or run the command and pick them (finish with **Finish**).
3. In the dialog choose the **Filled Region Type**, an optional **offset** (`0`, `25 mm`, `2"` …) and whether to **prevent duplicates**.
4. Read the summary. One **Undo** removes everything created by the run.

Remembered between runs: last type, offset, duplicate option, styling option and pattern source, log option (pyRevit config, section `FloorToFillRegion`).

## 4. Architecture

```
FloorTools.extension/
├── extension.json
├── README.md
├── FloorTools.tab/Floor Tools.panel/
│   ├── Floor to Fill Region.pushbutton/         script.py → command.execute(linked=False), bundle.yaml, icon.png
│   └── Linked Floor to Fill Region.pushbutton/  script.py → command.execute(linked=True),  bundle.yaml, icon.png
└── lib/floor_tools/     (namespaced package – see note)
    ├── revit_compat.py  ALL version / engine differences
    ├── settings.py      constants + remembered user settings
    ├── utils.py         logging, results, summary, friendly errors
    ├── geometry2d.py    pure-Python polygon maths (unit-tested, no Revit)
    ├── curve_loops.py   projection, grouping, offset, validation of CurveLoops
    ├── floor_geometry.py  Floor → footprint (LoopGroups)
    ├── floor_style.py   Floor type material → pattern/colour → Filled Region Type
    ├── fill_region.py   types, view validation, extensible storage, FilledRegion.Create
    ├── command.py       shared command flow: view check → selection → dialog → workflow → report
    ├── selection.py     host / linked Floor selection → FloorItem (floor + link transform)
    ├── workflow.py      transaction, per-floor isolation, progress
    └── ui.py            options dialog
```

**Note on `lib/`:** pyRevit puts the `lib` folder of *every* extension on `sys.path`. Generic top-level names such as `utils.py` or `settings.py` therefore collide with other extensions, so the requested modules live inside the `floor_tools` package. Import them as `from floor_tools import utils`.

To add a command: create another `.pushbutton` folder and reuse `floor_tools` modules.

## 5. How boundary extraction works

`floor_geometry.extract_footprint(floor)`:

1. **Top face** — `HostObjectUtils.GetTopFaces(floor)` → `PlanarFace`. If it returns exactly one face (flat or uniformly sloped floor), `face.GetEdgesAsCurveLoops()` yields every edge loop. If `GetTopFaces` fails, planar up-facing faces (`normal.Z ≥ 0.5`) are collected from the solid geometry instead.
2. **Split top** (several top faces): the outline comes from the Floor's `Sketch` profile (curves are chained and re-oriented into closed loops). A warning notes that openings created by Opening elements may be missing. If no sketch is found, each top face becomes its own boundary.
3. **Projection** (`curve_loops.project_loop`) — thickness, level and slope are irrelevant for a 2D region, so every loop is projected orthogonally onto the plane of the active view:
   * lines → projected end points;
   * arcs/splines parallel to the view → *translated* (stay exact arcs/splines);
   * curves on a tilted plane → fine polyline;
   * curves shorter than the short-curve tolerance are dropped; if that breaks continuity, the loop is rebuilt as a closed polyline (warning).
4. **Validation** (`validate_group`) — closed, planar, non-zero area, no self-intersection, openings inside and not crossing the outline, openings not overlapping.
5. **Offset** (optional) — `CurveLoop.CreateViaOffset` on each loop. Its sign convention depends on loop orientation, so both signs are tried and the one that grows the filled area is kept (outline moves out, openings shrink; negative values do the opposite). If the result is invalid, the original boundary is used and a warning is recorded.

## 6. How Floor openings are handled

Openings appear as *inner edge loops* of the top face — whether they come from the floor sketch, an Opening/Shaft element, or a cut. `group_loops` sorts all loops by **nesting depth**: even depth = filled outline, odd depth = opening, so islands inside openings also work. Each outline plus its openings is passed to a single `FilledRegion.Create` call, so a stair opening becomes an unfilled hole. Multiple openings and multiple separate outlines per Floor are supported.

## 7. Revit version compatibility

* Supported range and the "newer than tested" policy are configured in `settings.py` (`MIN_REVIT_VERSION`, `MAX_TESTED_REVIT_VERSION`, `ALLOW_UNTESTED_NEWER_VERSIONS`); `bundle.yaml` carries `min_revit_version`.
* `revit_compat.py` is the **only** module that branches on version or engine:

| Difference | Handling |
|---|---|
| `ElementId.IntegerValue` (≤2023) vs `.Value` (≥2024, Int64) | `element_id_value()`, `make_element_id()` |
| `UnitType`/`DisplayUnitType` vs `SpecTypeId`/`ForgeTypeId` | `_length_spec()`, `_length_display_unit()`; feature-detected with `hasattr`, not version numbers |
| Unit parsing/formatting | `parse_length()` uses Revit's `UnitFormatUtils.TryParse` (project units, `25 mm`, `2"`), with a small fallback parser |
| `Element.Name` on ElementTypes (IronPython) | `element_name()` |
| `ElementClassFilter` needs `System.Type` | `clr_type()` |

* Everything else uses APIs that are stable across 2021–2026 (`FilledRegion.Create`, `HostObjectUtils.GetTopFaces`, `Face.GetEdgesAsCurveLoops`, `CurveLoop.CreateViaOffset`, Extensible Storage).
* If Autodesk changes an API in a future release, the fix belongs in `revit_compat.py`; the algorithm modules stay untouched.

## 8. Floor appearance → Fill Region (patterns, colours, type name)

With **Copy each Floor's pattern and colours** on (default), the region does not use the selected type directly:

1. The Floor's *type* is read (`FloorType.GetCompoundStructure()`). Its layer materials are checked from the top layer down and the first material that defines a pattern is used.
2. From that material the **foreground pattern, foreground colour, background pattern and background colour** are taken — either the *Surface* pattern (what is drawn on the floor in plan views, default) or the *Cut* pattern (dialog option).
3. A Filled Region Type **named after the Floor type** is looked up. If it exists it is **reused unchanged**; otherwise the type selected in the dialog is duplicated under that name and the four values above are applied. All Floors of the same type share one Filled Region Type.
4. Characters Revit forbids in names (`\ : { } [ ] | ; < > ? ` ~`) are replaced by `_`.

Notes: a Floor *instance* has no name of its own, so "floor name" means the Floor **type** name. If Revit rejects a pattern for a region type (for example an unsupported pattern kind) the type keeps the base type's pattern and a warning is listed. New types are created inside the same transaction, so one Undo removes them as well. Switch the option off to use the selected type as-is.

## 9. Floors from linked models

Use **Linked Floor → Fill Region**, click Floors inside one or more loaded links, and press **Finish**. Everything else (options, offset, duplicates, styling, summary) works as for host Floors.

How it differs internally:

* **Selection:** `PickObjects(ObjectType.LinkedElement)` returns a reference to the *link instance* plus the id of the element inside the link. The Floor is fetched from `link_instance.GetLinkDocument()`. Elements that are not Floors are ignored and counted; **unloaded links** are skipped with a note.
* **Geometry:** the boundary is extracted in the link's own document (top face, sketch fallback — exactly as for host floors), then each loop is moved into host coordinates with `link_instance.GetTotalTransform()` (covers link position, rotation and shared coordinates) before it is projected onto the view plane. Rotated or moved links therefore land correctly.
* **Type and pattern:** the Filled Region Type is named after the *linked* Floor type. Fill patterns have per-document ElementIds, so each pattern is matched in the host by target (Drafting/Model) and name (solid fill is matched by property because its name is localized). If the host lacks the pattern, its definition is copied into the host (inside the same transaction). Colours are plain values and copy directly.
* **Duplicates:** the stored key is *link instance + Floor UniqueId*, so the same Floor in two link instances (or a Floor in the host and in a link) never blocks the other.
* **Report:** ElementIds of linked Floors are not host ids, so failures are listed as `Floor ID n (link 'name')` without a click-to-select link.

Not supported: nested links (a link inside a link) unless Revit lets you pick the element; the Fill Regions are 2D snapshots and do not follow later link updates.

## 10. Toposolids (Revit 2024+)

The `Toposolid` class only exists from Revit 2024. `revit_compat.py` detects it (`HAS_TOPOSOLID`), so on Revit 2021–2023 the tool silently works with Floors only, and on 2024+ Toposolids can be selected in both commands (host and linked).

* **Boundary:** the top surface of a Toposolid is a non-planar mesh, so the plan outline is taken from its **sketch** — outer boundary plus inner openings — which is then processed exactly like a Floor boundary (projection, validation, offset, nesting into holes). If no sketch is found, a flat **bottom face** is used with a warning.
* **Limitation:** the sketch is the outline the user drew, so cuts made in the Toposolid by other elements (e.g. building pads) are not reflected. Subdivisions are ignored.
* **Appearance:** the Toposolid *type* layer materials are read like Floor types; the Filled Region Type is named after the Toposolid type.
* Results are labelled `Toposolid ID n` in the summary.

## 11. Duplicate prevention

Each created region gets an Extensible Storage entity holding the source Floor's `UniqueId`. With **Prevent Duplicate Fill Regions** on, regions already in the **active view** are indexed once (single collector pass) and Floors that already have one are reported as *Already existed*. Regions created by other tools, or in other views, are not considered.

## 12. Testing procedure (Revit 2021 – 2026)

Use one test project per Revit version (or the same `.rvt` upgraded). Model these Floors on a level with a Floor Plan:

| # | Floor | Expected |
|---|---|---|
| T1 | Rectangle | Region matches outline |
| T2 | L-shape, U-shape | Concave corners exact |
| T3 | Curved edges (arcs) | Region contains true arcs |
| T4 | Rectangle with stair opening | Opening not filled |
| T5 | Two openings + one Opening element (shaft) | All holes present |
| T6 | Rotated floor (30°) | Matches |
| T7 | Sloped floor (slope arrow) | Plan outline matches; warning only if arcs |
| T8 | Shape-edited floor | Sketch-outline warning shown |
| T9 | Floor on another level / different thickness | Same result |
| T10 | Floor in a Ceiling Plan / Engineering Plan | Works |
| T12 | Linked model: rectangle, L-shape with opening, Floor of a link that is **moved/rotated** and uses shared coordinates | Regions sit exactly on the linked floors |
| T13 | Linked floor with a material pattern that does not exist in the host | Pattern is created in the host; type named after the linked Floor type |
| T14 | Unloaded link; same link loaded twice (two instances) | Note for unloaded link; both instances handled independently, no false duplicates |
| T15 | Revit 2024+: Toposolid with an opening, in host and in a link | Region follows the sketch outline; hole not filled; type named after the Toposolid type |
| T16 | Revit 2021–2023 | Toposolid option absent, Floors work as before |
| T11 | Two floors of the same type + one of another type | 2 new Filled Region Types named after the Floor types, patterns/colours match the materials |

Then check behaviour:

1. Run in a **3D view**, **section**, **sheet**, **view template** → clear message, nothing created.
2. Nothing selected → prompt; select a Wall only → "No Floors were selected" style message.
3. 20 Floors preselected → 20 regions, one Undo removes all.
4. Run again with duplicates ON → all *Already existed*; OFF → duplicates created.
5. Offset `+50 mm`, `-50 mm`, `0`; a huge negative offset on a small floor → warning, original boundary used.
6. Corrupt case: a tiny sliver floor → listed under *Failed* with its ID, others continue.
7. 100+ and 500+ floors → progress bar, cancel works, runtime acceptable.
8. Project in feet-inches and in millimetres: `25 mm` and bare `25` behave correctly.
9. Enable *detailed log* → output window shows the log; file written to `%TEMP%\FloorTools\floor_to_fill_region.log`.

Record per Revit version: pass/fail per row, pyRevit version, engine (IronPython/CPython).

## 13. Troubleshooting

| Symptom | Cause / fix |
|---|---|
| Button missing | Folder not registered under Custom Extension Directories, or no reload; extension folder must end in `.extension` |
| "Cannot be created from Floors in a '…' view" | Active view is not a plan; switch view |
| "No Filled Region Types" | Create one: Manage → Additional Settings → Filled Region |
| Failed: *Revit could not create the Filled Region* | Message contains Revit's reason; usually degenerate geometry — enable the detailed log |
| Warning: *curves approximated* | Very short curves or a sloped floor with arcs; the polyline is visually equivalent |
| Warning: *split into N faces* | Shape-edited floor; sketch outline used, Opening-element holes may be missing — add the hole to the floor sketch or check the result |
| Region looks like the base type, not the Floor | Floor type has no layer material / no pattern for the chosen source (try the other source), or a type with the Floor type's name already existed and was reused |
| Warning: *Offset ignored* | Offset collapses or self-intersects the boundary; use a smaller value |
| Linked command cannot click floors | The link must be loaded and its Floors visible in the active view (Visibility/Graphics → Revit Links; *By Linked View* settings can hide them) |
| Region misplaced for a linked floor | The region follows the link instance's current transform; check the link position / shared coordinates and re-run |
| Duplicates still created | Option off, region created in a different view, or region was made by another tool |
| Region slightly offset from floor | Regions sit at the view's plane; check crop/annotation scaling and that the view is not rotated by *Project North* expectations |
| `ImportError: floor_tools` | `lib/floor_tools` missing or extension not reloaded |
| Unexpected error dialog | Open `%TEMP%\FloorTools\floor_to_fill_region.log` |

## 14. Known limitations

* Floors inside linked models are not supported.
* Sloped/shape-edited floors: see sections 1 and 5.
* Fill Regions are 2D snapshots; they do not update when the Floor changes — delete and re-run (duplicate prevention will not block this once the old region is deleted).
* Pattern/colour are copied from the Floor type's materials at creation time; later material changes are not synced to existing Filled Region Types (reused by name). Delete the type and re-run to refresh.
