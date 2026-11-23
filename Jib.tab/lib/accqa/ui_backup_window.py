# -*- coding: utf-8 -*-
"""Backup / Restore window and import preview."""
import time

import clr
clr.AddReference("PresentationFramework")
from Microsoft.Win32 import OpenFileDialog, SaveFileDialog

from accqa import backup_manager, ui_base as ub, ui_xaml
from accqa import config_manager as cfg
from accqa import logging_manager as log
from accqa.revit_compat import to_text
from accqa.validation import ValidationError

FILE_FILTER = "JSON files (*.json)|*.json|All files (*.*)|*.*"


class ImportPreviewWindow(object):
    def __init__(self, current, incoming, issues, owner=None):
        self.owner = owner
        self.current = current
        self.incoming = incoming
        self.issues = issues
        self.result = None
        self.win, self.c = ub.load_window(ui_xaml.IMPORT_PREVIEW)
        self.c.rbMerge.Checked += lambda s, a: self._refresh()
        self.c.rbReplace.Checked += lambda s, a: self._refresh()
        self.c.btnImport.Click += lambda s, a: self._accept()
        self._refresh()

    def _mode(self):
        return "replace" if self.c.rbReplace.IsChecked else "merge"

    def _refresh(self):
        lines = backup_manager.build_preview(self.current, self.incoming, self._mode(), self.issues)
        self.c.txtPreview.Text = u"\n".join(lines)

    def _accept(self):
        mode = self._mode()
        if mode == "replace" and not ub.confirm(
                u"Replace your current projects and folders with the backup contents?", self.win, warning=True):
            return
        self.result = (mode, bool(self.c.chkSettings.IsChecked))
        self.win.DialogResult = True

    def show(self):
        ub.show_modal(self.win, self.owner)
        return self.result


class BackupWindow(object):
    def __init__(self, owner=None):
        self.owner = owner
        self.win, self.c = ub.load_window(ui_xaml.BACKUP_WINDOW)
        self.c.btnExport.Click += lambda s, a: self._export()
        self.c.btnImport.Click += lambda s, a: self._import()
        self._summary()

    def _summary(self):
        data = cfg.load()
        folders = sum(len(p["folders"]) for p in data["projects"])
        self.c.lblSummary.Text = u"Currently saved: %d project(s), %d folder link(s)." % (len(data["projects"]), folders)

    def _status(self, text, ok=True):
        self.c.lblStatus.Foreground = ub.brush("#2E7D32" if ok else "#B00020")
        self.c.lblStatus.Text = to_text(text)

    def _export(self):
        dialog = SaveFileDialog()
        dialog.Title = "Export ACC Quick Access backup"
        dialog.Filter = FILE_FILTER
        dialog.DefaultExt = ".json"
        dialog.AddExtension = True
        dialog.OverwritePrompt = True
        dialog.FileName = "ACCQuickAccess_backup_%s.json" % time.strftime("%Y%m%d_%H%M")
        if not dialog.ShowDialog(self.win):
            return
        try:
            projects, folders = backup_manager.export_backup(dialog.FileName)
        except Exception as ex:
            log.log_exception("Export failed")
            self._status(u"The backup could not be written: %s" % to_text(ex), ok=False)
            return
        self._status(u"Exported %d project(s) and %d folder link(s) to:\n%s" % (projects, folders, dialog.FileName))

    def _import(self):
        dialog = OpenFileDialog()
        dialog.Title = "Select an ACC Quick Access backup"
        dialog.Filter = FILE_FILTER
        dialog.CheckFileExists = True
        if not dialog.ShowDialog(self.win):
            return
        try:
            incoming, issues = backup_manager.read_backup(dialog.FileName)
        except ValidationError as ex:
            self._status(ex.message_text, ok=False)
            return
        except Exception as ex:
            log.log_exception("Reading the backup failed")
            self._status(u"The backup could not be read: %s" % to_text(ex), ok=False)
            return
        choice = ImportPreviewWindow(cfg.load(), incoming, issues, self.win).show()
        if not choice:
            self._status(u"Import cancelled. Nothing was changed.", ok=True)
            return
        mode, import_settings = choice
        try:
            summary = backup_manager.apply_import(incoming, mode, import_settings)
        except Exception as ex:
            log.log_exception("Import failed")
            self._status(u"The import failed and nothing was changed: %s" % to_text(ex), ok=False)
            return
        self._summary()
        self._status(summary)

    def show(self):
        ub.show_modal(self.win, self.owner)
