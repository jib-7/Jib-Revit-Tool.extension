# -*- coding: utf-8 -*-
"""Small Revit API helpers shared by the Revit-facing modules."""
import re

from Autodesk.Revit.DB import BuiltInParameter, Element, XYZ

from .models import ViewFrame


def get_name(elem):
    """Element name that works in IronPython 2/3 and CPython engines."""
    try:
        return elem.Name
    except Exception:
        pass
    try:
        return Element.Name.GetValue(elem)
    except Exception:
        pass
    try:
        return Element.Name.__get__(elem)
    except Exception:
        return ""


def token_regex(token):
    return re.compile(r"(?<!\d)" + re.escape(token) + r"(?!\d)")


def name_matches(name, token):
    return bool(name) and token_regex(token).search(name) is not None


def xyz_t(p):
    return (p.X, p.Y, p.Z)


def frame_from_view(view):
    return ViewFrame(xyz_t(view.Origin), xyz_t(view.RightDirection),
                     xyz_t(view.UpDirection), xyz_t(view.ViewDirection))


def to_xyz(frame, uv):
    t = frame.to_xyz(uv)
    return XYZ(t[0], t[1], t[2])


def set_comment(elem, text):
    try:
        prm = elem.get_Parameter(BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS)
        if prm is not None and not prm.IsReadOnly:
            prm.Set(text)
            return True
    except Exception:
        pass
    return False


def get_comment(elem):
    try:
        prm = elem.get_Parameter(BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS)
        if prm is not None and prm.HasValue:
            return prm.AsString() or ""
    except Exception:
        pass
    return ""


def id_value(elem_or_id):
    eid = getattr(elem_or_id, "Id", elem_or_id)
    try:
        return eid.Value          # Revit 2024+
    except Exception:
        return eid.IntegerValue   # older
