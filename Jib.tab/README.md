# ACC Quick Access (pyRevit extension) v1.0

One-click access to your Autodesk Construction Cloud (ACC) project folders from a dedicated
Revit ribbon tab. You save folder URLs once (through the UI); they are stored in a JSON file and
survive Revit restarts.

> **Honest status:** this package was built and tested *outside* Revit (Linux, desktop Python 3).
> The data layer, validation, detection logic, backup/restore and URL handling have automated tests.
> The WPF windows, the ribbon and the real Revit/ACC behaviour have **not** been executed by the
> author. Read `docs/TEST_CHECKLIST.md` and run the "needs Revit" part once on your machine.

## Install

1. Install pyRevit (4.8.x or newer) if you do not have it.
2. Unzip `ACCQuickAccess_v1.0.zip`. You get one folder: `ACCQuickAccess.extension`.
3. Put that folder into a pyRevit extensions directory, for example
   `%APPDATA%\pyRevit\Extensions\` (create it if missing).
   Alternative: keep it anywhere and add its *parent* folder in
   pyRevit tab > Settings > *Custom Extension Directories*, then save.
