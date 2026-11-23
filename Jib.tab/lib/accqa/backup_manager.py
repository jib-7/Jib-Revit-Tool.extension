# -*- coding: utf-8 -*-
"""Export / import of the configuration (merge or replace, with preview)."""
import copy
import os

from accqa import config_manager as cfg
from accqa import logging_manager as log
from accqa.revit_compat import to_text
from accqa.validation import (
    ValidationError, make_id, normalize_name, normalize_title, urls_equal, validate_url)


def export_backup(dest_path):
    """Write the full configuration to dest_path. Returns (projects, folders)."""
    data = cfg.load()
    payload = copy.deepcopy(data)
    payload["exported_at"] = cfg.now_iso()
    cfg.write_json_atomic(dest_path, payload)
    return len(data["projects"]), sum(len(p["folders"]) for p in data["projects"])


def read_backup(path):
    """Read and validate a backup file. Returns (normalized_data, issues).

    Folders whose URL is not a valid http/https URL are skipped and listed in issues.
    Raises ValidationError with a friendly message if the file is unusable.
    """
    try:
        raw = cfg.read_json_file(path)
    except Exception as ex:
        raise ValidationError(u"The file could not be read as JSON: %s" % to_text(ex))
    if not isinstance(raw, dict) or not isinstance(raw.get("projects"), list):
        raise ValidationError(u"This is not an ACC Quick Access backup (no 'projects' list found).")
    try:
        data = cfg.normalize_config(raw)
    except Exception as ex:
        raise ValidationError(u"The backup structure is invalid: %s" % to_text(ex))
    issues = []
    for project in data["projects"]:
        valid = []
        for folder in project["folders"]:
            try:
                validate_url(folder["url"])
                valid.append(folder)
            except ValidationError as ex:
                issues.append(u"Skipped folder '%s' in '%s': %s" % (
                    folder["folder_name"], project["project_name"], ex.message_text))
        project["folders"] = valid
    return data, issues


def _find_match(projects, incoming):
    for project in projects:
        if project["project_id"] == incoming["project_id"]:
            return project
    number = normalize_name(incoming.get("project_number"))
    if number:
        for project in projects:
            if normalize_name(project["project_number"]) == number:
                return project
    name = normalize_name(incoming.get("project_name"))
    for project in projects:
        if normalize_name(project["project_name"]) == name:
            return project
    return None


def _merge_projects(target_projects, incoming_projects):
    """Merge incoming into target (modifies target). Returns a statistics dict."""
    stats = {"new_projects": 0, "merged_projects": 0, "new_folders": 0, "duplicate_folders": 0,
             "new_models": 0}
    for incoming in copy.deepcopy(incoming_projects):
        existing = _find_match(target_projects, incoming)
        if existing is None:
            used_ids = set(p["project_id"] for p in target_projects)
            if incoming["project_id"] in used_ids:
                incoming["project_id"] = make_id("p")
            target_projects.append(incoming)
            stats["new_projects"] += 1
            stats["new_folders"] += len(incoming["folders"])
            continue
        stats["merged_projects"] += 1
        if not existing["project_number"] and incoming.get("project_number"):
            existing["project_number"] = incoming["project_number"]
        if not existing["cloud_project_guid"] and incoming.get("cloud_project_guid"):
            existing["cloud_project_guid"] = incoming["cloud_project_guid"]
        for folder in incoming["folders"]:
            duplicate = any(
                urls_equal(f["url"], folder["url"])
                or normalize_name(f["folder_name"]) == normalize_name(folder["folder_name"])
                for f in existing["folders"])
            if duplicate:
                stats["duplicate_folders"] += 1
                continue
            if any(f["folder_id"] == folder["folder_id"] for f in existing["folders"]):
                folder["folder_id"] = make_id("f")
            existing["folders"].append(folder)
            stats["new_folders"] += 1
        for model in incoming.get("models", []):
            known = any(
                (model.get("model_guid") and m.get("model_guid") == model.get("model_guid"))
                or (not model.get("model_guid") and normalize_title(m.get("title")) == normalize_title(model.get("title")))
                for m in existing["models"])
            if not known:
                existing["models"].append(model)
                stats["new_models"] += 1
    return stats


def build_preview(current, incoming, mode, issues=None):
    """Return preview text lines for the confirmation window. Does not change anything."""
    issues = issues or []
    cur_p = len(current["projects"])
    cur_f = sum(len(p["folders"]) for p in current["projects"])
    inc_p = len(incoming["projects"])
    inc_f = sum(len(p["folders"]) for p in incoming["projects"])
    lines = [
        u"Current configuration : %d projects, %d folders" % (cur_p, cur_f),
        u"Backup file           : %d projects, %d folders" % (inc_p, inc_f),
        u"",
    ]
    if mode == "replace":
        lines.append(u"REPLACE: all current projects and folders will be replaced by the backup contents.")
    else:
        stats = _merge_projects(copy.deepcopy(current["projects"]), incoming["projects"])
        lines += [
            u"MERGE: current data is kept; the backup is added to it.",
            u"  New projects to add        : %d" % stats["new_projects"],
            u"  Existing projects merged   : %d" % stats["merged_projects"],
            u"  New folders to add         : %d" % stats["new_folders"],
            u"  Duplicate folders skipped  : %d" % stats["duplicate_folders"],
        ]
    lines += [u"", u"Projects in the backup:"]
    for project in incoming["projects"]:
        number = project["project_number"]
        lines.append(u"  - %s%s (%d folders)" % (
            (number + u" - ") if number else u"", project["project_name"], len(project["folders"])))
    if issues:
        lines += [u"", u"Problems found (these items are not imported):"] + [u"  ! " + i for i in issues]
    lines += [u"", u"A safety copy of your current configuration is saved automatically before importing."]
    return lines


def apply_import(incoming, mode, import_settings=False):
    """Apply the import after a timestamped safety backup. Returns a summary string."""
    safety = cfg.make_timestamped_backup("before-import")

    def _op(data):
        if mode == "replace":
            data["projects"] = copy.deepcopy(incoming["projects"])
            ids = set(p["project_id"] for p in data["projects"])
            data["recent_projects"] = [r for r in data["recent_projects"] if r.get("project_id") in ids]
            summary = u"Replaced configuration: %d projects imported." % len(data["projects"])
        else:
            stats = _merge_projects(data["projects"], incoming["projects"])
            summary = (u"Merged: %(new_projects)d new projects, %(merged_projects)d merged, "
                       u"%(new_folders)d folders added, %(duplicate_folders)d duplicate folders skipped." % stats)
        if import_settings:
            data["settings"] = dict(data.get("settings") or {})
            data["settings"].update(cfg.get_settings(incoming))
        return summary
    summary = cfg.mutate(_op)
    log.info(u"Import applied (%s). Safety backup: %s" % (mode, safety))
    if safety:
        summary += u"\nSafety copy: %s" % os.path.basename(safety)
    return summary
