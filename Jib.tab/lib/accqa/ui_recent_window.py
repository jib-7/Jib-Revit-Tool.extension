# -*- coding: utf-8 -*-
"""Recent Projects window (recently ACCESSED saved links, newest first)."""
from accqa import acc_url_manager, folder_manager, recent_manager, ui_base as ub, ui_xaml
from accqa import config_manager as cfg
from accqa.validation import project_label


class RecentWindow(object):
    def __init__(self, owner=None):
        self.owner = owner
        self.win, self.c = ub.load_window(ui_xaml.RECENT_WINDOW)
        self._suppress = False
        c = self.c
        c.lstRecent.SelectionChanged += self._on_project_changed
        c.lstFolders.MouseDoubleClick += lambda s, a: self._open()
        c.btnOpen.Click += lambda s, a: self._open()
        c.btnClear.Click += lambda s, a: self._clear()
        self._fill()

    def _fill(self):
        c = self.c
        data = cfg.load()
        if not cfg.get_settings(data)["recent_tracking"]:
            c.lblNote.Text = u"Tracking is switched off in Settings."
        else:
            c.lblNote.Text = u""
        self._suppress = True
        c.lstRecent.Items.Clear()
        for entry in recent_manager.get_recent(data):
            project = entry["project"]
            sub = u"Last opened: %s" % ub.format_when(entry["last_accessed"])
            if entry["last_folder_name"]:
                sub += u"  -  %s" % entry["last_folder_name"]
            c.lstRecent.Items.Add(ub.make_list_item(project["project_id"], "Project Root", project_label(project), sub))
        self._suppress = False
        if c.lstRecent.Items.Count > 0:
            c.lstRecent.Items[0].IsSelected = True
        self._fill_folders()
        if c.lstRecent.Items.Count == 0:
            c.lstFolders.Items.Clear()
            c.lstFolders.Items.Add(ub.make_list_item(u"none", "Custom", u"Nothing here yet",
                                                    u"Folders you open from this extension will appear here.", bold_main=False))

    def _on_project_changed(self, sender, args):
        if not self._suppress:
            self._fill_folders()

    def _fill_folders(self):
        c = self.c
        c.lstFolders.Items.Clear()
        pid = ub.selected_tag(c.lstRecent)
        if not pid:
            return
        project = folder_manager.find_project(cfg.load(), pid)
        if project is None:
            return
        for category, label, folders in folder_manager.group_by_category(project, folder_manager.DISPLAY_ORDER_CURRENT):
            for folder in folders:
                c.lstFolders.Items.Add(ub.make_list_item(folder["folder_id"], category, folder["folder_name"],
                                                         label, tooltip=folder["url"]))

    def _open(self):
        c = self.c
        pid = ub.selected_tag(c.lstRecent)
        fid = ub.selected_tag(c.lstFolders)
        project = folder_manager.find_project(cfg.load(), pid) if pid else None
        folder = folder_manager.find_folder(project, fid) if (project and fid) else None
        if folder is None:
            ub.info(u"Select a project and a folder first.", self.win)
            return
        ub.report_open_result(acc_url_manager.open_folder(project, folder), self.win)
        self._fill()

    def _clear(self):
        if ub.confirm(u"Clear the recent project history?\n\nYour saved projects and folders are not affected.",
                      self.win):
            recent_manager.clear()
            self._fill()

    def show(self):
        ub.show_modal(self.win, self.owner)
