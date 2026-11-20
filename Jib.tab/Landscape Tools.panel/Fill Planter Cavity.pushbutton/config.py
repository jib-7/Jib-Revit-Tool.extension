# -*- coding: utf-8 -*-
"""Shift+Click: edit Fill Planter Cavity settings (stored per user)."""
__title__ = "Fill Planter Cavity settings"

from pyrevit import forms

from planter_cavity import settings

s = settings.load_settings()
while True:
    labels = ["%s = %s" % (k, s[k]) for k, _ in settings.DEFAULTS]
    labels.append("[ Reset all to defaults ]")
    sel = forms.SelectFromList.show(labels, title="Settings (user file: %s)" % settings.settings_path(),
                                    button_name="Edit selected", multiselect=False)
    if sel is None:
        break
    if sel.startswith("[ Reset"):
        s = settings.default_settings()
        settings.save_settings(s)
        continue
    key = sel.split(" = ")[0]
    old = s[key]
    new = forms.ask_for_string(default=str(old), prompt="New value for '%s'" % key, title="Edit setting")
    if new is None:
        continue
    try:
        if isinstance(old, bool):
            s[key] = new.strip().lower() in ("1", "true", "yes", "y")
        elif isinstance(old, float):
            s[key] = float(new)
        else:
            s[key] = new.strip()
        settings.save_settings(s)
    except Exception as ex:
        forms.alert("Invalid value: %s" % ex)
