# -*- coding: utf-8 -*-
__title__ = "Settings"
__doc__ = "Detection, recent history, browser and deletion options."
__author__ = "ACC Quick Access"

import os
import sys
import time
import traceback


def _startup_log(text):
    """Independent of the accqa package, so it still works if importing the package fails."""
    try:
        folder = os.path.join(os.environ.get("APPDATA") or "", "pyRevit", "ACCQuickAccess", "logs")
        if not os.path.isdir(folder):
            os.makedirs(folder)
        handle = open(os.path.join(folder, "startup.log"), "a")
        handle.write("%s %s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), text))
        handle.close()
    except Exception:
        pass


_startup_log("START Settings | python %s | platform %s" % (sys.version.split()[0], sys.platform))
try:
    from accqa import ui_manager
    ui_manager.run_safe(ui_manager.show_settings)
    _startup_log("END Settings (no exception reached the button script)")
except Exception:
    _details = traceback.format_exc()
    _startup_log("FAILED Settings\n" + _details)
    print("ACC Quick Access failed to start:")
    print(_details)
