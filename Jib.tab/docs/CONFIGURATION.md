# Configuration

## Files (all in `%APPDATA%\pyRevit\ACCQuickAccess\`)

| File | Purpose |
|---|---|
| `config.json` | Your projects, folders, recent list, settings (UTF-8; non-Latin text is stored as `\uXXXX` escapes and read back intact) |
| `config.json.bak` | Copy of the previous version, refreshed on every save |
| `backups/config_<reason>_<time>.json` | Safety copies made before import, reset and migration (newest 25 kept) |
| `config.corrupt-<time>.json` | A damaged config is never deleted; it is kept under this name |
| `logs/accqa.log` | Technical errors (rotates at about 1 MB) |

Everything is created automatically. The folder is per Windows user. For testing only, the
environment variable `ACCQA_DATA_DIR` redirects the data folder.

## Schema (version "1.0")

```json
{
  "version": "1.0",
  "projects": [
    {
      "project_id": "p_1a2b3c4d",          // internal unique id (generated)
      "project_number": "3929",
      "project_name": "EMAAR Dubai Hills Estate",
      "cloud_project_guid": "",            // optional; used by automatic detection
      "models": [                          // Revit models remembered for this project
        {"title": "3929-ARC-Model", "model_guid": "", "project_guid": "", "added": "2026-11-23T10:00:00"}
      ],
      "folders": [
        {"folder_id": "f_5e6f7a8b", "folder_name": "Shared", "category": "Shared",
         "url": "<your ACC folder URL>", "description": ""}
      ]
    }
  ],
  "recent_projects": [
    {"project_id": "p_1a2b3c4d", "last_accessed": "2026-11-23T10:05:00",
     "last_folder_id": "f_5e6f7a8b", "last_folder_name": "Shared"}
  ],
  "settings": {
    "auto_detect_project": true, "recent_tracking": true, "max_recent_projects": 10,
    "open_in_default_browser": true, "confirm_delete": true
  }
}
```
Categories: `Project Root`, `Shared`, `WIP`, `Published`, `Custom`.
The example schema in the original brief used `project_id` as the project number; such files load fine
(the id is copied into `project_number`). Unknown keys written by future versions are preserved.

## Settings

| Setting | Effect |
|---|---|
| Automatic current project detection | Off = buttons ask you to pick the project manually |
| Recent project tracking | Off = nothing is recorded |
| Maximum recent projects | 1-10 (default 10) |
| Open links in default browser | Off = the URL is copied to the clipboard instead of opened |
| Confirm before deleting | Applies to single folders. Deleting a whole project always asks |

*Reset Settings* restores the defaults and does **not** touch projects. *Delete All Saved Data...* is a
separate, double-confirmed action that first writes a backup copy.

## Rules the data layer enforces

* Project name, folder name and URL are required; URL must be `http://` or `https://`.
* URLs are saved exactly as pasted (surrounding whitespace removed, nothing else) and opened unchanged,
  including `?` parameters, `&` and folder identifiers.
* Duplicates: same folder name or same URL inside one project is refused; a project number that belongs to
  another project name (or vice versa) is refused instead of merging silently.
* Every change is saved immediately and re-reads the file first, so two Revit sessions do not overwrite each other.

## Updating the extension

Replace the `ACCQuickAccess.extension` folder. Your data lives outside it and is not touched.
Schema changes are handled by `config_manager.migrate()` (a timestamped backup is taken first).
