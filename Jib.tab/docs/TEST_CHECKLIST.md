# Test checklist

Legend: **EXECUTED** = run by the author in a Linux sandbox with desktop Python 3 (`python tests/run_tests.py`,
44 tests, all passing at packaging time). **NOT EXECUTED** = needs Revit/pyRevit/Windows and/or a real ACC account;
nothing in that column has been verified. Tick them yourself after installing.

## Executed offline (data layer and static checks)

| Item | How |
|---|---|
| URL validation (http/https only, empty, spaces, file:, javascript:) | unit tests |
| Required fields; multiple projects; multiple folders per project | unit tests |
| Duplicate project / folder / URL prevention | unit tests |
| Exact URL preserved (query parameters, `&`, `%3A`) and passed unchanged to the launcher | unit tests (launcher mocked) |
| Edit, rename, re-categorise, change number, delete folder/project | unit tests |
| Search by project name, number and folder name | unit tests |
| Recent list: order, limit 10, clear, deleted projects, tracking off, failed launch not recorded | unit tests |
| Config: auto-create, UTF-8 round trip, .bak, corrupted file + restore, no-backup fallback, unknown keys kept, spec example schema, settings reset keeps projects | unit tests |
| Backup/restore: export, preview, merge (no duplicates, idempotent), replace, invalid file, invalid URLs skipped, safety backup | unit tests |
| Detection tiers, ambiguity, "similar names never match", family/no document, setting off | unit tests with fake model data |
| Cloud info extraction against fake Revit document objects (incl. missing API members) | unit tests |
| All Python compiles; ASCII only; no Python 3-only syntax; XAML well-formed; every `c.<control>` used in code exists in XAML; every button has script + icon | static checks |

## NOT EXECUTED - needs Revit (please verify)

- [ ] Extension loads in pyRevit without errors; tab **ACC Quick Access** appears after Reload
- [ ] All 11 buttons are visible with their icons and open their window / action (no traceback)
- [ ] Add ACC Link: dialog layout, project drop-down fills number, Test URL opens browser, Save works
- [ ] Validation messages appear in the dialog; duplicate warning dialogs behave
- [ ] All Projects: tree expand/collapse, double-click opens URL, add/edit/delete, search, folder icons render
- [ ] Manage Links: edit project, rename/re-categorise folder, test URL, delete with confirmation
- [ ] Current Project with: (a) an ACC cloud model, (b) a local model, (c) no document, (d) a family
- [ ] Detection details panel shows sensible GUIDs and the user-visible path for your Revit version
- [ ] Manual selection + "Remember this model" makes the next detection automatic
- [ ] Shared / WIP / Published / Custom Folders buttons: 0, 1 and several folders per category
- [ ] Recent Projects after opening several folders; Clear History
- [ ] Settings save; Reset Settings keeps projects; Delete All Saved Data (double confirm + backup file)
- [ ] Backup export/import dialogs (Windows file dialogs), preview window, merge and replace
- [ ] Config survives closing Revit / restarting Windows
- [ ] Revit 2024, 2025 and 2026 each tested
- [ ] pyRevit engine variants (IronPython 2.7 / 3.4 / CPython) tested if you switch engines

## NOT EXECUTED - needs a real ACC account

- [ ] A pasted ACC folder URL opens the exact folder after Autodesk sign-in
- [ ] Behaviour for a folder deleted/moved in ACC and for a user without permission (Autodesk's page is shown; the extension cannot detect this)
- [ ] Whether your cloud model's project GUID equals the GUID inside your saved ACC folder URLs (detection tier 3). If not, use Edit Project to paste the GUID shown in *Detection details*, or remember the model.
