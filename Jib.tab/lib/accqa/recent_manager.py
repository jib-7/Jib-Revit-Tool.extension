# -*- coding: utf-8 -*-
"""Recently ACCESSED saved project links (not recently opened Revit models)."""
from accqa import config_manager as cfg
from accqa.folder_manager import find_project


def record_access(project_id, folder_id=None, folder_name=u""):
    """Move the project to the top of the recent list. Returns False if tracking is off."""
    def _op(data):
        settings = cfg.get_settings(data)
        if not settings["recent_tracking"]:
            return False
        recents = [r for r in data["recent_projects"] if r.get("project_id") != project_id]
        recents.insert(0, {
            "project_id": project_id,
            "last_accessed": cfg.now_iso(),
            "last_folder_id": folder_id or u"",
            "last_folder_name": folder_name or u"",
        })
        data["recent_projects"] = recents[: settings["max_recent_projects"]]
        return True
    return cfg.mutate(_op)


def get_recent(data=None):
    """Most recent first: [{'project', 'last_accessed', 'last_folder_id', 'last_folder_name'}]."""
    data = data or cfg.load()
    limit = cfg.get_settings(data)["max_recent_projects"]
    entries = []
    for item in data.get("recent_projects", []):
        project = find_project(data, item.get("project_id"))
        if project is None:
            continue  # project was deleted
        entries.append({
            "project": project,
            "last_accessed": item.get("last_accessed") or u"",
            "last_folder_id": item.get("last_folder_id") or u"",
            "last_folder_name": item.get("last_folder_name") or u"",
        })
    entries.sort(key=lambda e: e["last_accessed"], reverse=True)
    return entries[:limit]


def clear():
    def _op(data):
        data["recent_projects"] = []
        return True
    return cfg.mutate(_op)
