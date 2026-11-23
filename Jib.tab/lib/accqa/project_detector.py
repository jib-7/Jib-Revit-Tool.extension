# -*- coding: utf-8 -*-
"""Identify which saved project the active Revit model belongs to.

Matching order (first tier that finds anything wins; more than one hit in a tier
means "ambiguous" and NO project is auto-selected):
  1. Saved cloud project GUID equals the model's cloud project GUID      (high)
  2. A remembered model entry has the same cloud model GUID              (high)
  3. The cloud project GUID appears inside one of the saved folder URLs  (high)
  4. ACC project name (cloud path / Desktop Connector path) equals the
     saved project name (exact, case-insensitive)                        (medium)
  5. A remembered model entry has the same title (exact)                 (medium)
  6. The saved project number is a whole token of the model title        (low)
Similar-looking names are never matched: every comparison is exact after
normalising case, spaces and dashes. No private Autodesk API is used.
"""
import re

from accqa import config_manager as cfg
from accqa import logging_manager as log
from accqa import revit_compat as rc
from accqa.revit_compat import to_text
from accqa.validation import clean, normalize_name, normalize_title, project_label

METHOD_LABELS = {
    "cloud_project_guid": u"cloud project GUID",
    "saved_model_guid": u"remembered cloud model GUID",
    "url_project_guid": u"project GUID found in a saved folder URL",
    "acc_project_name": u"ACC project name",
    "saved_model_title": u"remembered model title",
    "title_project_number": u"project number in the model title",
    "manual": u"selected manually",
    "none": u"not identified",
}
CONFIDENCE = {
    "cloud_project_guid": "high", "saved_model_guid": "high", "url_project_guid": "high",
    "acc_project_name": "medium", "saved_model_title": "medium",
    "title_project_number": "low", "manual": "manual", "none": "none",
}


class DetectionResult(object):
    def __init__(self, info):
        self.info = info
        self.project = None
        self.method = "none"
        self.candidates = []   # filled when several projects match one tier
        self.notes = []

    @property
    def confidence(self):
        return CONFIDENCE.get(self.method, "none")

    @property
    def method_label(self):
        return METHOD_LABELS.get(self.method, u"")

    @property
    def ambiguous(self):
        return self.project is None and len(self.candidates) > 1

    @property
    def has_document(self):
        return bool(self.info.get("has_document"))

    @property
    def has_project_document(self):
        return bool(self.info.get("has_document")) and not self.info.get("is_family")

    def diagnostics_text(self):
        i = self.info
        lines = [
            u"Python engine: %s" % i.get("engine", u""),
            u"Revit version: %s" % i.get("revit_version", u""),
            u"Document title: %s" % i.get("title", u""),
            u"Document path: %s" % (i.get("path") or u"(none)"),
            u"Cloud model: %s" % {True: u"yes", False: u"no", None: u"unknown"}.get(i.get("is_cloud")),
            u"Cloud project GUID: %s" % (i.get("project_guid") or u"(not available)"),
            u"Cloud model GUID: %s" % (i.get("model_guid") or u"(not available)"),
            u"Region: %s" % (i.get("region") or u"(not available)"),
            u"User-visible path: %s" % (i.get("user_visible_path") or u"(not available)"),
            u"ACC project name used for matching: %s" % (i.get("acc_project_name") or u"(none)"),
            u"Result: %s (%s)" % (self.method_label, self.confidence),
        ]
        if self.candidates:
            lines.append(u"Candidates: %s" % u"; ".join(project_label(p) for p in self.candidates))
        for note in list(i.get("notes", [])) + list(self.notes):
            lines.append(u"Note: %s" % note)
        return u"\n".join(lines)


def gather_model_info(doc):
    """Collect identifiers from a Revit Document (None-safe)."""
    info = {
        "has_document": doc is not None,
        "is_family": False,
        "title": u"",
        "path": u"",
        "is_cloud": None,
        "project_guid": None,
        "model_guid": None,
        "region": None,
        "user_visible_path": None,
        "acc_project_name": None,
        "notes": [],
        "engine": rc.engine_description(),
        "revit_version": rc.get_revit_version(),
    }
    if doc is None:
        return info
    info["is_family"] = not rc.is_project_document(doc)
    info["title"] = rc.get_model_title(doc)
    info["path"] = to_text(rc.safe_attr(doc, "PathName", u""))
    if info["is_family"]:
        return info
    cloud = rc.get_cloud_info(doc)
    for key in ("is_cloud", "project_guid", "model_guid", "region", "user_visible_path", "acc_project_name"):
        info[key] = cloud.get(key)
    info["notes"].extend(cloud.get("notes", []))
    if not info["acc_project_name"]:
        local = rc.project_name_from_local_path(info["path"])
        if local:
            info["acc_project_name"] = local
            info["notes"].append(u"ACC project name taken from a Desktop Connector (ACCDocs) path.")
    return info


def _number_tokens(value):
    return [t for t in re.split(r"[^0-9A-Za-z]+", to_text(value).upper()) if t]


def _contains_sequence(tokens, wanted):
    if not wanted or len(wanted) > len(tokens):
        return False
    for start in range(len(tokens) - len(wanted) + 1):
        if tokens[start:start + len(wanted)] == wanted:
            return True
    return False


def _tier_matches(projects, info):
    """Yield (method, [matching projects]) in priority order."""
    project_guid = (info.get("project_guid") or u"").lower()
    model_guid = (info.get("model_guid") or u"").lower()
    acc_name = normalize_name(info.get("acc_project_name") or u"")
    title_key = normalize_title(info.get("title") or u"")

    yield "cloud_project_guid", [p for p in projects
                                 if project_guid and p.get("cloud_project_guid", u"").lower() == project_guid]
    yield "saved_model_guid", [p for p in projects if model_guid and any(
        m.get("model_guid") == model_guid for m in p.get("models", []))]
    yield "url_project_guid", [p for p in projects if project_guid and any(
        project_guid in (f.get("url") or u"").lower() for f in p.get("folders", []))]

    def _acc_name_hit(p):
        name = normalize_name(p.get("project_name"))
        number = normalize_name(p.get("project_number"))
        keys = set([name])
        if number:
            keys.add(normalize_name(u"%s - %s" % (number, p.get("project_name"))))
            keys.add(normalize_name(u"%s %s" % (number, p.get("project_name"))))
        return acc_name in keys
    yield "acc_project_name", [p for p in projects if acc_name and _acc_name_hit(p)]

    yield "saved_model_title", [p for p in projects if title_key and any(
        normalize_title(m.get("title")) == title_key for m in p.get("models", []))]

    title_tokens = _number_tokens(info.get("title") or u"")
    hits = []
    for p in projects:
        wanted = _number_tokens(p.get("project_number"))
        if len(u"".join(wanted)) >= 3 and _contains_sequence(title_tokens, wanted):
            hits.append(p)
    yield "title_project_number", hits


def match_project(data, info):
    """Pure matching function (no Revit needed) - used by detect_current_project and tests."""
    result = DetectionResult(info)
    if not info.get("has_document"):
        result.notes.append(u"No active Revit document.")
        return result
    if info.get("is_family"):
        result.notes.append(u"The active document is a family, not a project.")
        return result
    projects = data.get("projects", [])
    for method, matches in _tier_matches(projects, info):
        if len(matches) == 1:
            result.project = matches[0]
            result.method = method
            return result
        if len(matches) > 1:
            result.candidates = matches
            result.method = "none"
            result.notes.append(u"More than one saved project matches by %s; not choosing automatically."
                                % METHOD_LABELS[method])
            return result
    return result


def detect_current_project(data=None, doc=None):
    """Detect the project of the active (or supplied) document; honours the settings."""
    data = data or cfg.load()
    if doc is None:
        doc = rc.get_active_document()
    info = gather_model_info(doc)
    if not cfg.get_settings(data)["auto_detect_project"]:
        result = DetectionResult(info)
        result.notes.append(u"Automatic detection is switched off in Settings.")
        return result
    try:
        return match_project(data, info)
    except Exception:
        log.log_exception("Project detection failed")
        result = DetectionResult(info)
        result.notes.append(u"Detection failed; see the log file.")
        return result
