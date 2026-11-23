# -*- coding: utf-8 -*-
"""Project and folder CRUD with duplicate prevention. Every change is saved immediately."""
from accqa import config_manager as cfg
from accqa.validation import (
    CATEGORIES, CATEGORY_LABELS, ValidationError, clean, make_id, normalize_name,
    require_text, validate_category, validate_url, urls_equal)

DISPLAY_ORDER_CURRENT = ["Shared", "WIP", "Published", "Project Root", "Custom"]


# ---------------------------------------------------------------------------
# Read helpers (pure functions on loaded data)
# ---------------------------------------------------------------------------
def _sort_key(project):
    number = clean(project.get("project_number"))
    name = normalize_name(project.get("project_name"))
    if number.isdigit():
        return (0, -int(number), name)  # numbered projects first, newest (highest) number first
    return (1, 0, name)


def sort_projects(projects):
    return sorted(projects, key=_sort_key)


def find_project(data, project_id):
    for project in data.get("projects", []):
        if project.get("project_id") == project_id:
            return project
    return None


def find_folder(project, folder_id):
    if project is None:
        return None
    for folder in project.get("folders", []):
        if folder.get("folder_id") == folder_id:
            return folder
    return None


def group_by_category(project, order=None):
    """[(category, label, [folders])] for non-empty categories, in display order."""
    order = order or CATEGORIES
    groups = []
    for category in order:
        items = [f for f in project.get("folders", []) if f.get("category") == category]
        if items:
            groups.append((category, CATEGORY_LABELS.get(category, category), items))
    return groups


def folders_in_category(project, category):
    return [f for f in project.get("folders", []) if f.get("category") == category]


def search_projects(projects, query):
    """Return [(project, folders_to_show, force_expand)].

    A match on project name/number shows all folders of that project; a match on a
    folder name shows only the matching folders of the project.
    """
    needle = normalize_name(query)
    results = []
    for project in sort_projects(projects):
        if not needle:
            results.append((project, list(project["folders"]), False))
            continue
        if (needle in normalize_name(project.get("project_name"))
                or needle in normalize_name(project.get("project_number"))):
            results.append((project, list(project["folders"]), True))
            continue
        hits = [f for f in project["folders"] if needle in normalize_name(f.get("folder_name"))]
        if hits:
            results.append((project, hits, True))
    return results


def count_folders(data):
    return sum(len(p.get("folders", [])) for p in data.get("projects", []))


def find_url_elsewhere(url, exclude_project_id=None):
    """Return (project_name, folder_name) if the exact URL is saved in another project."""
    data = cfg.load()
    for project in data["projects"]:
        if project["project_id"] == exclude_project_id:
            continue
        for folder in project["folders"]:
            if urls_equal(folder.get("url"), url):
                return (project["project_name"], folder["folder_name"])
    return None


# ---------------------------------------------------------------------------
# Duplicate rules
# ---------------------------------------------------------------------------
def _check_folder_duplicates(project, folder_name, url, exclude_folder_id=None):
    for folder in project["folders"]:
        if folder["folder_id"] == exclude_folder_id:
            continue
        if normalize_name(folder["folder_name"]) == normalize_name(folder_name):
            raise ValidationError(u"A folder named '%s' already exists in this project." % folder["folder_name"])
        if urls_equal(folder["url"], url):
            raise ValidationError(u"This URL is already saved in this project as '%s'." % folder["folder_name"])


def _resolve_project(data, name, number):
    """Find the project for (name, number) or create it. Never merges conflicting projects."""
    by_number = None
    by_name = None
    for project in data["projects"]:
        if number and normalize_name(project["project_number"]) == normalize_name(number):
            by_number = project
        if normalize_name(project["project_name"]) == normalize_name(name):
            by_name = project
    if by_number is not None and by_name is not None and by_number is not by_name:
        raise ValidationError(
            u"Project number %s belongs to '%s' but a different project is named '%s'. "
            u"Check the project name and number." % (number, by_number["project_name"], by_name["project_name"]))
    existing = by_number or by_name
    if existing is None:
        project = {
            "project_id": make_id("p"),
            "project_number": number,
            "project_name": name,
            "cloud_project_guid": u"",
            "models": [],
            "folders": [],
        }
        data["projects"].append(project)
        return project
    if by_number is not None and normalize_name(by_number["project_name"]) != normalize_name(name):
        raise ValidationError(
            u"Project number %s is already registered as '%s'. Use that project name, "
            u"or choose a different project number." % (number, by_number["project_name"]))
    if number and existing["project_number"] and normalize_name(existing["project_number"]) != normalize_name(number):
        raise ValidationError(
            u"The project '%s' is already registered with number %s. Use that number or leave it unchanged."
            % (existing["project_name"], existing["project_number"]))
    if number and not existing["project_number"]:
        existing["project_number"] = number
    return existing


# ---------------------------------------------------------------------------
# Mutations
# ---------------------------------------------------------------------------
def add_link(project_name, project_number, folder_name, category, url, description=u""):
    """Add a folder (and the project if it is new). Returns (project_id, folder_id)."""
    name = require_text(project_name, u"Project Name")
    number = clean(project_number)
    fname = require_text(folder_name, u"Folder Name")
    cat = validate_category(category)
    clean_url = validate_url(url)
    desc = clean(description)

    def _op(data):
        project = _resolve_project(data, name, number)
        _check_folder_duplicates(project, fname, clean_url)
        folder = {
            "folder_id": make_id("f"),
            "folder_name": fname,
            "category": cat,
            "url": clean_url,
            "description": desc,
        }
        project["folders"].append(folder)
        return (project["project_id"], folder["folder_id"])
    return cfg.mutate(_op)


def update_folder(project_id, folder_id, folder_name, category, url, description=u""):
    fname = require_text(folder_name, u"Folder Name")
    cat = validate_category(category)
    clean_url = validate_url(url)
    desc = clean(description)

    def _op(data):
        project = find_project(data, project_id)
        folder = find_folder(project, folder_id)
        if folder is None:
            raise ValidationError(u"This folder no longer exists. Close the window and reopen it.")
        _check_folder_duplicates(project, fname, clean_url, exclude_folder_id=folder_id)
        folder["folder_name"] = fname
        folder["category"] = cat
        folder["url"] = clean_url
        folder["description"] = desc
        return True
    return cfg.mutate(_op)


def delete_folder(project_id, folder_id):
    def _op(data):
        project = find_project(data, project_id)
        if project is None:
            return False
        before = len(project["folders"])
        project["folders"] = [f for f in project["folders"] if f["folder_id"] != folder_id]
        return len(project["folders"]) != before
    return cfg.mutate(_op)


def delete_project(project_id):
    def _op(data):
        before = len(data["projects"])
        data["projects"] = [p for p in data["projects"] if p["project_id"] != project_id]
        data["recent_projects"] = [r for r in data["recent_projects"] if r.get("project_id") != project_id]
        return len(data["projects"]) != before
    return cfg.mutate(_op)


def update_project(project_id, project_name, project_number, cloud_project_guid=u"", models=None):
    name = require_text(project_name, u"Project Name")
    number = clean(project_number)
    guid = clean(cloud_project_guid).lower()

    def _op(data):
        project = find_project(data, project_id)
        if project is None:
            raise ValidationError(u"This project no longer exists. Close the window and reopen it.")
        for other in data["projects"]:
            if other is project:
                continue
            if normalize_name(other["project_name"]) == normalize_name(name):
                raise ValidationError(u"Another project is already named '%s'." % other["project_name"])
            if number and normalize_name(other["project_number"]) == normalize_name(number):
                raise ValidationError(u"Project number %s is already used by '%s'." % (number, other["project_name"]))
        project["project_name"] = name
        project["project_number"] = number
        project["cloud_project_guid"] = guid
        if models is not None:
            project["models"] = [cfg.normalize_model(m) for m in models if cfg.normalize_model(m)]
        return True
    return cfg.mutate(_op)


def link_model(project_id, title, model_guid=None, project_guid=None):
    """Remember that this Revit model belongs to a saved project (used by auto-detection)."""
    title = clean(title)
    model_guid = clean(model_guid).lower()
    project_guid = clean(project_guid).lower()
    if not title and not model_guid:
        return False

    def _op(data):
        project = find_project(data, project_id)
        if project is None:
            return False
        for model in project["models"]:
            same_guid = model_guid and model.get("model_guid") == model_guid
            same_title = (not model_guid) and normalize_name(model.get("title")) == normalize_name(title)
            if same_guid or same_title:
                return True
        project["models"].append({
            "title": title, "model_guid": model_guid, "project_guid": project_guid,
            "added": cfg.now_iso()})
        if project_guid and not project["cloud_project_guid"]:
            project["cloud_project_guid"] = project_guid
        return True
    return cfg.mutate(_op)
