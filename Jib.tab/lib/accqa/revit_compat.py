# -*- coding: utf-8 -*-
"""Compatibility layer: Python engines (IronPython 2.7 / 3.4, CPython 3) and Revit 2024-2026.

Design rules used in the whole package:
  * No f-strings, no nonlocal, no type annotations (must parse on IronPython 2.7).
  * All Revit API access is defensive: every property/method that is not guaranteed
    to exist in every supported Revit version is read through try/except and any
    failure is recorded as a diagnostic note instead of crashing.
"""
import re
import sys

try:
    text_type = unicode  # IronPython 2.7 / Python 2
except NameError:
    text_type = str

try:
    from urllib.parse import urlparse
except ImportError:  # IronPython 2.7
    from urlparse import urlparse


def to_text(value):
    """Return value as a text (unicode) string on every supported engine."""
    if value is None:
        return u""
    if isinstance(value, text_type):
        return value
    try:
        if isinstance(value, bytes):
            return value.decode("utf-8")
    except Exception:
        pass
    try:
        return text_type(value)
    except Exception:
        return u"%s" % (repr(value),)


def safe_attr(obj, name, default=None):
    """getattr that never raises (Revit properties can throw for unusual documents)."""
    try:
        return getattr(obj, name)
    except Exception:
        return default


def engine_description():
    impl = getattr(sys, "implementation", None)
    if impl is not None:
        name = impl.name
    elif sys.platform == "cli":
        name = "IronPython"
    else:
        name = "Python"
    return u"%s %s" % (name, sys.version.split()[0])


# ---------------------------------------------------------------------------
# Revit session helpers
# ---------------------------------------------------------------------------
def get_revit_version():
    """Return the Revit major version as text (e.g. '2026') or 'unknown'."""
    try:
        from pyrevit import HOST_APP
        return to_text(HOST_APP.version)
    except Exception:
        pass
    return u"unknown"


def get_active_document():
    """Return the active Revit Document or None (no document open / not in Revit)."""
    try:
        from pyrevit import HOST_APP
        uidoc = HOST_APP.uidoc
        if uidoc is not None:
            return uidoc.Document
    except Exception:
        pass
    return None


def is_project_document(doc):
    """True for a normal project document; False for family documents."""
    if doc is None:
        return False
    return not bool(safe_attr(doc, "IsFamilyDocument", False))


def get_model_title(doc):
    """Document title without the workshared '_<username>' suffix (when present)."""
    title = to_text(safe_attr(doc, "Title", u""))
    try:
        if safe_attr(doc, "IsWorkshared", False):
            user = to_text(doc.Application.Username)
            suffix = u"_" + user
            if user and title.lower().endswith(suffix.lower()):
                title = title[: -len(suffix)]
    except Exception:
        pass
    return title


# ---------------------------------------------------------------------------
# Cloud / ACC identification
# ---------------------------------------------------------------------------
def _user_visible_path(model_path):
    """ModelPathUtils.ConvertModelPathToUserVisiblePath (documented Revit API)."""
    from Autodesk.Revit.DB import ModelPathUtils
    return to_text(ModelPathUtils.ConvertModelPathToUserVisiblePath(model_path))


def parse_visible_path(visible):
    """Split a user-visible path such as 'Provider://Project/Model.rvt'.

    Returns (provider, project_name, file_name); unknown parts are None.
    The result is only ever used for EXACT (case-insensitive) comparisons.
    """
    value = to_text(visible).strip()
    provider = None
    rest = value
    if u"://" in value:
        provider, rest = value.split(u"://", 1)
    parts = [p for p in re.split(r"[\\/]+", rest) if p]
    if len(parts) >= 2:
        return provider, parts[0], parts[-1]
    if len(parts) == 1:
        return provider, None, parts[0]
    return provider, None, None


def project_name_from_local_path(path):
    """Desktop Connector keeps ACC files under ...\\ACCDocs\\<Project>\\...  (best effort)."""
    parts = [p for p in re.split(r"[\\/]+", to_text(path)) if p]
    for index, part in enumerate(parts[:-1]):
        if part.lower() == u"accdocs" and index + 1 < len(parts) - 1:
            return parts[index + 1]
    return None


def get_cloud_info(doc):
    """Collect everything the supported API can tell us about a cloud-hosted model.

    Uses only documented members and guards each one:
      Document.IsModelInCloud, Document.GetCloudModelPath(),
      Document.GetWorksharingCentralModelPath(), ModelPath.CloudPath,
      ModelPath.GetProjectGUID(), ModelPath.GetModelGUID(), ModelPath.Region,
      ModelPathUtils.ConvertModelPathToUserVisiblePath().
    Missing members are recorded in info['notes'] so they show up in the
    'Detection details' panel and in the log.
    """
    info = {
        "is_cloud": None,
        "project_guid": None,
        "model_guid": None,
        "region": None,
        "user_visible_path": None,
        "provider": None,
        "acc_project_name": None,
        "file_name": None,
        "notes": [],
    }
    notes = info["notes"]
    if doc is None:
        return info

    try:
        info["is_cloud"] = bool(doc.IsModelInCloud)
    except Exception as ex:
        notes.append(u"Document.IsModelInCloud not available: %s" % to_text(ex))

    model_path = None
    if info["is_cloud"] is not False:
        try:
            model_path = doc.GetCloudModelPath()
        except Exception as ex:
            notes.append(u"Document.GetCloudModelPath() failed: %s" % to_text(ex))
        if model_path is None and safe_attr(doc, "IsWorkshared", False):
            try:
                model_path = doc.GetWorksharingCentralModelPath()
            except Exception as ex:
                notes.append(u"GetWorksharingCentralModelPath() failed: %s" % to_text(ex))

    if model_path is not None:
        cloud_flag = safe_attr(model_path, "CloudPath", None)
        if cloud_flag is False:
            notes.append(u"The model path is not a cloud path.")
            info["is_cloud"] = False
            model_path = None
        elif cloud_flag is True:
            info["is_cloud"] = True

    if model_path is not None and info["is_cloud"]:
        for key, method in (("project_guid", "GetProjectGUID"), ("model_guid", "GetModelGUID")):
            func = getattr(model_path, method, None)
            if func is None:
                notes.append(u"ModelPath.%s() is not available in this Revit version." % method)
                continue
            try:
                info[key] = to_text(func()).strip().lower() or None
            except Exception as ex:
                notes.append(u"ModelPath.%s() failed: %s" % (method, to_text(ex)))
        region = safe_attr(model_path, "Region", None)
        if region is not None:
            info["region"] = to_text(region)
        try:
            visible = _user_visible_path(model_path)
            info["user_visible_path"] = visible
            provider, project_name, file_name = parse_visible_path(visible)
            info["provider"] = provider
            info["acc_project_name"] = project_name
            info["file_name"] = file_name
        except Exception as ex:
            notes.append(u"User-visible cloud path not available: %s" % to_text(ex))

    return info
