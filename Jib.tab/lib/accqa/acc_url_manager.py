# -*- coding: utf-8 -*-
"""Opening saved URLs. The stored URL is passed to Windows exactly as saved.

The URL is launched with ShellExecute semantics (Process.Start with UseShellExecute=True,
falling back to os.startfile / webbrowser). We deliberately do NOT use `cmd /c start`,
which would cut a URL at the first '&'. Autodesk sign-in and folder permissions stay
entirely under Autodesk's control: a successful launch only means Windows accepted the
request - it says nothing about whether the folder exists or you may open it.
"""
import os

from accqa import config_manager as cfg
from accqa import logging_manager as log
from accqa import recent_manager
from accqa.revit_compat import to_text
from accqa.validation import ValidationError, validate_url


class OpenResult(object):
    """status: 'opened' | 'copied' | 'error'"""

    def __init__(self, status, message=u""):
        self.status = status
        self.message = message

    @property
    def ok(self):
        return self.status in ("opened", "copied")


def _launch(url):
    """Hand the URL to the default browser. Returns None or raises RuntimeError."""
    errors = []
    try:
        try:
            import clr
            clr.AddReference("System.Diagnostics.Process")  # separate assembly on .NET 8
        except Exception:
            pass
        from System.Diagnostics import Process, ProcessStartInfo
        info = ProcessStartInfo(url)
        info.UseShellExecute = True  # required on .NET (Revit 2025+) to use the default browser
        Process.Start(info)
        return
    except Exception as ex:
        errors.append(u"Process.Start: %s" % to_text(ex))
    try:
        os.startfile(url)  # Windows only
        return
    except Exception as ex:
        errors.append(u"os.startfile: %s" % to_text(ex))
    try:
        import webbrowser
        if webbrowser.open(url):
            return
        errors.append(u"webbrowser.open returned False")
    except Exception as ex:
        errors.append(u"webbrowser: %s" % to_text(ex))
    raise RuntimeError(u"; ".join(errors))


def copy_to_clipboard(text):
    try:
        from System.Windows import Clipboard
        Clipboard.SetText(text)
        return True
    except Exception:
        log.log_exception("Clipboard copy failed")
        return False


def open_url(url, force_browser=False):
    """Validate and open a URL. force_browser ignores the 'open in browser' setting (Test URL)."""
    try:
        checked = validate_url(url)
    except ValidationError as ex:
        return OpenResult("error", ex.message_text)

    if not force_browser:
        try:
            if not cfg.get_settings(cfg.load())["open_in_default_browser"]:
                if copy_to_clipboard(checked):
                    return OpenResult("copied", u"Opening links in the browser is switched off in Settings, "
                                                u"so the URL was copied to the clipboard instead.")
                return OpenResult("error", u"Opening links in the browser is switched off in Settings and the "
                                           u"URL could not be copied to the clipboard.")
        except Exception:
            log.log_exception("Could not read the open-in-browser setting; continuing with the browser")

    try:
        _launch(checked)
    except Exception as ex:
        log.log_exception("Browser launch failed for URL (see message)")
        log.error(u"Browser launch error: %s" % to_text(ex))
        return OpenResult("error", u"The URL could not be opened in your default browser.\n\n%s" % to_text(ex))
    log.info(u"Opened URL: %s" % checked)
    return OpenResult("opened", u"The URL was sent to your default browser. Autodesk controls sign-in and "
                                u"folder permissions, so the folder may still show an Autodesk error page if it "
                                u"was moved, deleted or you do not have access.")


def open_folder(project, folder):
    """Open a saved folder and (if the launch succeeded) record it in the recent list."""
    result = open_url(folder.get("url"))
    if result.status == "error" and not folder.get("url"):
        result.message = u"The folder '%s' has no URL saved." % folder.get("folder_name")
    if result.status == "opened":
        try:
            recent_manager.record_access(project["project_id"], folder["folder_id"], folder["folder_name"])
        except Exception:
            log.log_exception("Could not update the recent list")
    return result
