# -*- coding: utf-8 -*-
"""Filled Region Boundary Manager - pyRevit entry point."""
__title__ = 'Boundary\nManager'
__author__ = 'Jibin Issac'
__doc__ = ('Create, duplicate, preview and apply Line Styles to Filled Region boundaries; '
           'presets, batch replace and audit.')

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from pyrevit import forms, revit  # noqa: E402


def _main():
    uidoc = revit.uidoc
    if uidoc is None or uidoc.Document is None:
        forms.alert('Open a Revit project first.', title='Filled Region Boundary Manager')
        return
    from lib import utils
    from ui import main_window
    try:
        main_window.run(uidoc)
    except Exception as ex:
        try:
            utils.write_text(os.path.join(utils.config_dir(), 'last_error.log'), utils.trace())
        except Exception:
            pass
        forms.alert('Filled Region Boundary Manager hit an unexpected error and closed. '
                    'Revit and your model were not harmed.\n\n%s\n\nDetails: %%APPDATA%%\\pyRevit\\'
                    'FilledRegionBoundaryManager\\last_error.log' % ex,
                    title='Filled Region Boundary Manager', warn_icon=True)


_main()
