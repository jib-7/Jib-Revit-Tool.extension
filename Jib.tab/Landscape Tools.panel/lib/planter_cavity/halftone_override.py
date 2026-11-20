# -*- coding: utf-8 -*-
"""Per-instance Halftone override in the active view."""
from Autodesk.Revit.DB import OverrideGraphicSettings

from .models import PlanterError


def apply_halftone(view, element):
    """Apply Halftone to this single element in this view and verify it."""
    try:
        ogs = view.GetElementOverrides(element.Id)
    except Exception:
        ogs = OverrideGraphicSettings()
    ogs.SetHalftone(True)
    view.SetElementOverrides(element.Id, ogs)
    if not view.GetElementOverrides(element.Id).Halftone:
        raise PlanterError("The Halftone override did not stick (check view template / VG overrides control).")
    return True
