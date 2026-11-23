# -*- coding: utf-8 -*-
"""Reading, validating, migrating and safely writing config.json.

Safety rules implemented here:
  * Directory is created automatically.
  * Writes go to a temp file, are read back and verified, then swapped in.
  * The previous file is copied to config.json.bak before every overwrite.
  * A corrupted file is never deleted: it is kept as config.corrupt-<stamp>.json and
    the newest valid backup is restored (or a fresh empty config is created).
  * Unknown keys written by newer versions are preserved.
  * No passwords, tokens or credentials are ever stored.
"""
import copy
import json
import os
import shutil
import time

from accqa import CONFIG_SCHEMA_VERSION, paths
from accqa import logging_manager as log
from accqa.revit_compat import to_text
from accqa.validation import canonical_category, clean, make_id

DEFAULT_SETTINGS = {
    "auto_detect_project": True,
    "recent_tracking": True,
    "max_recent_projects": 10,
    "open_in_default_browser": True,
    "confirm_delete": True,
}
MAX_RECENT_LIMIT = 10
BACKUP_KEEP = 25

# Notice produced when load() had to repair something; the UI shows it once.
_pending_notice = [None]


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------
def now_iso():
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def now_stamp():
    return time.strftime("%Y%m%d-%H%M%S")


def config_path():
    return paths.get_config_path()


def default_config():
    return {
        "version": CONFIG_SCHEMA_VERSION,
        "projects": [],
        "recent_projects": [],
        "settings": copy.deepcopy(DEFAULT_SETTINGS),
    }


def take_notice():
    """Return (and clear) the pending repair notice, or None."""
    notice = _pending_notice[0]
    _pending_notice[0] = None
    return notice


def _set_notice(text):
    _pending_notice[0] = text
    log.warning(text)


# ---------------------------------------------------------------------------
# Low level file access
# ---------------------------------------------------------------------------
def read_json_file(path):
    """Read a UTF-8 (with or without BOM) JSON file. Raises ValueError/IOError."""
    handle = open(path, "rb")
    try:
        raw = handle.read()
    finally:
        handle.close()
    text = raw.decode("utf-8")
    if text.startswith(u"\ufeff"):
        text = text[1:]
    return json.loads(text)


def _encode_json(data):
    # ensure_ascii=True keeps the file pure ASCII (valid UTF-8) and avoids str/unicode
    # pitfalls on IronPython 2.7. Non-Latin names are stored as \uXXXX and read back intact.
    text = json.dumps(data, indent=2, ensure_ascii=True, separators=(",", ": "))
    return text.encode("utf-8")


def _replace(src, dst):
    replace = getattr(os, "replace", None)
    if replace is not None:
        replace(src, dst)
        return
    if os.path.exists(dst):  # IronPython 2.7 has no os.replace
        os.remove(dst)
    os.rename(src, dst)


def write_json_atomic(path, data):
    """Write data to path via temp file + verification (does not touch the .bak)."""
    paths.ensure_dir(os.path.dirname(path))
    tmp = path + ".tmp"
    payload = _encode_json(data)
    handle = open(tmp, "wb")
    try:
        handle.write(payload)
        handle.flush()
        try:
            os.fsync(handle.fileno())
        except Exception:
            pass
    finally:
        handle.close()
    read_json_file(tmp)  # verification: raises if what we wrote cannot be parsed
    _replace(tmp, path)


def make_timestamped_backup(tag):
    """Copy the current config into backups/ (if it exists). Returns the new path or None."""
    src = config_path()
    if not os.path.exists(src):
        return None
    folder = paths.ensure_dir(paths.get_backup_dir())
    dest = os.path.join(folder, "config_%s_%s.json" % (tag, now_stamp()))
    try:
        shutil.copy2(src, dest)
    except Exception:
        log.log_exception("Could not create timestamped backup")
        return None
    _prune_backups(folder)
    return dest


def _prune_backups(folder):
    try:
        names = sorted(n for n in os.listdir(folder) if n.startswith("config_") and n.endswith(".json"))
        for name in names[:-BACKUP_KEEP]:
            os.remove(os.path.join(folder, name))
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Normalisation / migration
# ---------------------------------------------------------------------------
def _txt(value):
    return clean(value) if value is not None else u""


def normalize_model(model):
    if not isinstance(model, dict):
        return None
    out = dict(model)
    out["title"] = _txt(model.get("title"))
    out["model_guid"] = _txt(model.get("model_guid")).lower()
    out["project_guid"] = _txt(model.get("project_guid")).lower()
    out["added"] = _txt(model.get("added"))
    if not out["title"] and not out["model_guid"]:
        return None
    return out


def normalize_folder(folder):
    if not isinstance(folder, dict):
        return None
    out = dict(folder)
    out["folder_id"] = _txt(folder.get("folder_id")) or make_id("f")
    out["folder_name"] = _txt(folder.get("folder_name")) or u"Untitled folder"
    out["category"] = canonical_category(folder.get("category"))
    out["url"] = _txt(folder.get("url"))
    out["description"] = _txt(folder.get("description"))
    return out


def normalize_project(project):
    if not isinstance(project, dict):
        return None
    out = dict(project)
    out["project_id"] = _txt(project.get("project_id")) or make_id("p")
    number = project.get("project_number")
    if number is None:
        # Schema example in the specification used project_id as the project number.
        legacy = _txt(project.get("project_id"))
        number = legacy if legacy.isdigit() else u""
    out["project_number"] = _txt(number)
    out["project_name"] = _txt(project.get("project_name")) or u"Unnamed project"
    out["cloud_project_guid"] = _txt(project.get("cloud_project_guid")).lower()
    models = project.get("models")
    out["models"] = [m for m in (normalize_model(x) for x in (models if isinstance(models, list) else [])) if m]
    folders = project.get("folders")
    out["folders"] = [f for f in (normalize_folder(x) for x in (folders if isinstance(folders, list) else [])) if f]
    seen = set()
    for folder in out["folders"]:
        if folder["folder_id"] in seen:
            folder["folder_id"] = make_id("f")
        seen.add(folder["folder_id"])
    return out


def get_settings(data):
    """Return settings merged with defaults and clamped to valid values."""
    stored = data.get("settings") if isinstance(data, dict) else None
    settings = copy.deepcopy(DEFAULT_SETTINGS)
    if isinstance(stored, dict):
        for key in DEFAULT_SETTINGS:
            if key in stored:
                settings[key] = stored[key]
    for key in ("auto_detect_project", "recent_tracking", "open_in_default_browser", "confirm_delete"):
        settings[key] = bool(settings[key])
    try:
        limit = int(settings["max_recent_projects"])
    except Exception:
        limit = DEFAULT_SETTINGS["max_recent_projects"]
    settings["max_recent_projects"] = max(1, min(MAX_RECENT_LIMIT, limit))
    return settings


def normalize_config(data):
    """Return a normalised copy of data. Raises ValueError if the root is not an object."""
    if not isinstance(data, dict):
        raise ValueError("The configuration root must be a JSON object.")
    out = dict(data)
    version = _txt(out.get("version")) or CONFIG_SCHEMA_VERSION
    out["version"] = version
    projects = out.get("projects")
    normalized = []
    seen = set()
    for item in (projects if isinstance(projects, list) else []):
        project = normalize_project(item)
        if project is None:
            log.warning("Ignored a project entry that was not a JSON object.")
            continue
        if project["project_id"] in seen:
            project["project_id"] = make_id("p")
        seen.add(project["project_id"])
        normalized.append(project)
    out["projects"] = normalized
    recent = out.get("recent_projects")
    out["recent_projects"] = [r for r in (recent if isinstance(recent, list) else []) if isinstance(r, dict)]
    merged = dict(out.get("settings") if isinstance(out.get("settings"), dict) else {})
    merged.update(get_settings(out))
    out["settings"] = merged
    return out


# Add one function per schema step here when the schema version changes, e.g.
# _MIGRATIONS["1.0"] = _migrate_1_0_to_1_1.  Version 1.0 is the first schema, so
# there is nothing to migrate yet; older/unversioned files are handled by
# normalize_config() (missing keys filled in, legacy project_id -> project_number).
_MIGRATIONS = {}


def migrate(data):
    """Apply schema migrations. Returns (data, changed)."""
    changed = False
    guard = 0
    while data.get("version") in _MIGRATIONS and guard < 20:
        data = _MIGRATIONS[data["version"]](data)
        changed = True
        guard += 1
    if data.get("version") != CONFIG_SCHEMA_VERSION and data.get("version") not in _MIGRATIONS:
        try:
            newer = float(data.get("version")) > float(CONFIG_SCHEMA_VERSION)
        except Exception:
            newer = False
        if newer:
            _set_notice(u"The configuration was written by a newer version of ACC Quick Access "
                        u"(schema %s). It is kept unchanged, but some fields may be ignored." % data.get("version"))
    return data, changed


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def load():
    """Load configuration from disk, repairing problems without losing data."""
    path = config_path()
    paths.ensure_dir(os.path.dirname(path))

    if not os.path.exists(path):
        data = default_config()
        try:
            write_json_atomic(path, data)
        except Exception:
            log.log_exception("Could not create the initial configuration file")
        return data

    try:
        raw = read_json_file(path)
        data = normalize_config(raw)
    except Exception as ex:
        log.log_exception("config.json could not be read")
        corrupt = os.path.join(os.path.dirname(path), "config.corrupt-%s.json" % now_stamp())
        try:
            shutil.copy2(path, corrupt)
        except Exception:
            corrupt = None
        data = None
        restored = False
        bak = path + ".bak"
        if os.path.exists(bak):
            try:
                data = normalize_config(read_json_file(bak))
                restored = True
            except Exception:
                data = None
        if data is None:
            data = default_config()
        try:
            write_json_atomic(path, data)  # does not overwrite the .bak
        except Exception:
            log.log_exception("Could not write the repaired configuration")
        _set_notice(
            u"The saved configuration file could not be read (%s).\n\n"
            u"%s\n\nThe damaged file was kept%s." % (
                to_text(ex),
                u"Your most recent automatic backup was restored." if restored
                else u"No usable backup was found, so an empty configuration was created.",
                (u" as: " + to_text(corrupt)) if corrupt else u""))
        return data

    data, changed = migrate(data)
    if changed:
        make_timestamped_backup("premigration")
        save(data)
    return data


def save(data, make_backup=True):
    """Write data to disk (previous version is kept as config.json.bak)."""
    path = config_path()
    if make_backup and os.path.exists(path):
        try:
            shutil.copy2(path, path + ".bak")
        except Exception:
            log.log_exception("Could not refresh config.json.bak")
    write_json_atomic(path, data)


def mutate(func):
    """Load fresh data, let func modify it, save, and return func's result.

    Always re-reading first means two Revit sessions never overwrite each other's
    changes with stale in-memory copies.
    """
    data = load()
    result = func(data)
    save(data)
    return result


def update_settings(new_values):
    def _op(data):
        settings = get_settings(data)
        for key in DEFAULT_SETTINGS:
            if key in new_values:
                settings[key] = new_values[key]
        data["settings"] = dict(data.get("settings") or {})
        data["settings"].update(get_settings({"settings": settings}))
        return data["settings"]
    return mutate(_op)


def reset_settings():
    """Restore default settings. Projects and folders are NOT touched."""
    def _op(data):
        data["settings"] = copy.deepcopy(DEFAULT_SETTINGS)
        return True
    return mutate(_op)


def reset_all_data():
    """Delete every saved project, recent entry and setting (a backup is made first)."""
    backup = make_timestamped_backup("before-reset")
    save(default_config())
    return backup
