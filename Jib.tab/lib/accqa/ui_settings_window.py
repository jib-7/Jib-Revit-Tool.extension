# -*- coding: utf-8 -*-
"""Settings window."""
from accqa import config_manager as cfg
from accqa import logging_manager as log
from accqa import paths, ui_base as ub, ui_xaml


class SettingsWindow(object):
    def __init__(self, owner=None):
        self.owner = owner
        self.win, self.c = ub.load_window(ui_xaml.SETTINGS_WINDOW)
        c = self.c
        ub.set_header(c, u"Settings", u"Preferences are stored in the configuration file")
        for number in range(1, cfg.MAX_RECENT_LIMIT + 1):
            c.cmbMaxRecent.Items.Add(str(number))
        c.txtConfigPath.Text = cfg.config_path()
        c.txtLogPath.Text = log.get_log_path()
        c.lblInfo.Text = (u"'Reset Settings' only restores the options above. "
                          u"'Delete All Saved Data...' removes every project and folder (a backup copy is made first).")
        c.btnSave.Click += lambda s, a: self._save()
        c.btnResetSettings.Click += lambda s, a: self._reset_settings()
        c.btnDeleteAll.Click += lambda s, a: self._delete_all()
        c.btnOpenFolder.Click += lambda s, a: self._open_folder()
        c.btnCopyPath.Click += lambda s, a: ub.copy_text(cfg.config_path())
        self._load_values()

    def _load_values(self):
        c = self.c
        settings = cfg.get_settings(cfg.load())
        c.chkAutoDetect.IsChecked = settings["auto_detect_project"]
        c.chkRecent.IsChecked = settings["recent_tracking"]
        c.chkBrowser.IsChecked = settings["open_in_default_browser"]
        c.chkConfirm.IsChecked = settings["confirm_delete"]
        c.cmbMaxRecent.SelectedIndex = settings["max_recent_projects"] - 1

    def _save(self):
        c = self.c
        index = c.cmbMaxRecent.SelectedIndex
        values = {
            "auto_detect_project": bool(c.chkAutoDetect.IsChecked),
            "recent_tracking": bool(c.chkRecent.IsChecked),
            "open_in_default_browser": bool(c.chkBrowser.IsChecked),
            "confirm_delete": bool(c.chkConfirm.IsChecked),
            "max_recent_projects": (index + 1) if index >= 0 else 10,
        }
        try:
            cfg.update_settings(values)
        except Exception:
            log.log_exception("Saving settings failed")
            ub.error(u"The settings could not be saved. Details were written to the log file.", self.win)
            return
        self.win.DialogResult = True

    def _reset_settings(self):
        if ub.confirm(u"Restore all settings to their defaults?\n\nYour saved projects and folders are NOT changed.",
                      self.win):
            cfg.reset_settings()
            self._load_values()

    def _delete_all(self):
        if not ub.confirm(u"Delete ALL saved projects, folders and recent history?\n\n"
                          u"This cannot be undone from inside Revit (a backup copy is saved automatically).",
                          self.win, warning=True):
            return
        if not ub.confirm(u"Are you absolutely sure? Every saved ACC link will be removed.", self.win, warning=True):
            return
        backup = cfg.reset_all_data()
        self._load_values()
        ub.info(u"All saved data was deleted." + (u"\n\nBackup copy: %s" % backup if backup else u""), self.win)

    def _open_folder(self):
        try:
            ub.open_path(paths.ensure_dir(paths.get_data_dir()))
        except Exception:
            log.log_exception("Could not open the data folder")
            ub.error(u"The data folder could not be opened:\n%s" % paths.get_data_dir(), self.win)

    def show(self):
        ub.show_modal(self.win, self.owner)
