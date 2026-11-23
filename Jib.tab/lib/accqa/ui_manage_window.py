# -*- coding: utf-8 -*-
"""Manage Links: project list + folder editor (add, edit, rename, re-categorise, test, delete)."""
from accqa import acc_url_manager, folder_manager, ui_base as ub, ui_xaml
from accqa import config_manager as cfg
from accqa.ui_link_dialog import LinkDialog, ProjectDialog
from accqa.validation import normalize_name, project_label


class ManageWindow(object):
    def __init__(self, owner=None):
        self.owner = owner
        self.win, self.c = ub.load_window(ui_xaml.MANAGE_WINDOW)
        self.project_id = None
        self._suppress = False  # blocks SelectionChanged while the list is rebuilt
        c = self.c
        c.txtSearch.TextChanged += lambda s, a: self._fill_projects()
        c.lstProjects.SelectionChanged += self._on_project_changed
        c.btnAddProject.Click += lambda s, a: self._add_project()
        c.btnEditProject.Click += lambda s, a: self._edit_project()
        c.btnDeleteProject.Click += lambda s, a: self._delete_project()
        c.btnAddFolder.Click += lambda s, a: self._add_folder()
        c.btnEditFolder.Click += lambda s, a: self._edit_folder()
        c.btnTestUrl.Click += lambda s, a: self._test_url()
        c.btnOpen.Click += lambda s, a: self._open()
        c.btnDeleteFolder.Click += lambda s, a: self._delete_folder()
        c.lstFolders.MouseDoubleClick += lambda s, a: self._edit_folder()
        self._fill_projects()

    # -- data ---------------------------------------------------------------
    def _project(self):
        if not self.project_id:
            return None
        return folder_manager.find_project(cfg.load(), self.project_id)

    def _selected_folder(self):
        project = self._project()
        tag = ub.selected_tag(self.c.lstFolders)
        if project is None or not tag:
            return project, None
        return project, folder_manager.find_folder(project, tag)

    # -- lists --------------------------------------------------------------
    def _fill_projects(self, select_id=None):
        c = self.c
        data = cfg.load()
        needle = normalize_name(c.txtSearch.Text)
        wanted = select_id or self.project_id
        self._suppress = True
        c.lstProjects.Items.Clear()
        chosen = None
        for project in folder_manager.sort_projects(data["projects"]):
            label = project_label(project)
            if needle and needle not in normalize_name(label):
                continue
            count = len(project["folders"])
            item = ub.make_list_item(project["project_id"], "Project Root", label,
                                     u"%d folder%s" % (count, u"" if count == 1 else u"s"))
            c.lstProjects.Items.Add(item)
            if project["project_id"] == wanted:
                chosen = item
        if chosen is None and c.lstProjects.Items.Count > 0:
            chosen = c.lstProjects.Items[0]
        if chosen is not None:
            chosen.IsSelected = True
            self.project_id = ub.selected_tag(c.lstProjects)
        else:
            self.project_id = None
        self._suppress = False
        self._fill_folders()

    def _on_project_changed(self, sender, args):
        if self._suppress:
            return
        tag = ub.selected_tag(self.c.lstProjects)
        if tag:
            self.project_id = tag
            self._fill_folders()

    def _fill_folders(self):
        c = self.c
        project = self._project()
        c.lstFolders.Items.Clear()
        if project is None:
            c.lblProjName.Text = u"Select a project"
            c.lblProjInfo.Text = u""
            return
        c.lblProjName.Text = project_label(project)
        guid = project["cloud_project_guid"] or u"not set"
        c.lblProjInfo.Text = u"Cloud project GUID: %s   |   Remembered Revit models: %d" % (
            guid, len(project["models"]))
        for category, label, folders in folder_manager.group_by_category(project):
            for folder in folders:
                sub = u"%s  -  %s" % (label, ub.short_text(folder["url"], 70))
                c.lstFolders.Items.Add(ub.make_list_item(
                    folder["folder_id"], category, folder["folder_name"], sub, tooltip=folder["url"]))

    # -- actions ------------------------------------------------------------
    def _add_project(self):
        result = LinkDialog("add", owner=self.win).show()
        if result:
            self._fill_projects(select_id=result["project_id"])

    def _edit_project(self):
        project = self._project()
        if project is None:
            ub.info(u"Select a project first.", self.win)
            return
        if ProjectDialog(project, self.win).show():
            self._fill_projects(select_id=project["project_id"])

    def _delete_project(self):
        project = self._project()
        if project is None:
            ub.info(u"Select a project first.", self.win)
            return
        if not ub.confirm(
                u"Delete the project '%s' and all %d saved folder link(s)?\n\nThis only removes the saved links. "
                u"Nothing is deleted in ACC." % (project_label(project), len(project["folders"])),
                self.win, warning=True):
            return
        folder_manager.delete_project(project["project_id"])
        self.project_id = None
        self._fill_projects()

    def _add_folder(self):
        project = self._project()
        if project is None:
            ub.info(u"Select a project first.", self.win)
            return
        prefill = {"project_name": project["project_name"], "project_number": project["project_number"]}
        if LinkDialog("add", prefill=prefill, owner=self.win).show():
            self._fill_projects(select_id=project["project_id"])

    def _edit_folder(self):
        project, folder = self._selected_folder()
        if folder is None:
            ub.info(u"Select a folder first.", self.win)
            return
        if LinkDialog("edit", project, folder, owner=self.win).show():
            self._fill_projects(select_id=project["project_id"])

    def _test_url(self):
        project, folder = self._selected_folder()
        if folder is None:
            ub.info(u"Select a folder first.", self.win)
            return
        # Testing does not count as 'recently accessed', so it does not use open_folder().
        result = acc_url_manager.open_url(folder["url"], force_browser=True)
        if result.status == "error":
            ub.error(result.message, self.win)
        else:
            ub.info(result.message, self.win)

    def _open(self):
        project, folder = self._selected_folder()
        if folder is None:
            ub.info(u"Select a folder first.", self.win)
            return
        ub.report_open_result(acc_url_manager.open_folder(project, folder), self.win)

    def _delete_folder(self):
        project, folder = self._selected_folder()
        if folder is None:
            ub.info(u"Select a folder first.", self.win)
            return
        settings = cfg.get_settings(cfg.load())
        if settings["confirm_delete"] and not ub.confirm(
                u"Delete the folder '%s' from '%s'?\n\nThis only removes the saved link. Nothing is deleted in ACC."
                % (folder["folder_name"], project["project_name"]), self.win, warning=True):
            return
        folder_manager.delete_folder(project["project_id"], folder["folder_id"])
        self._fill_projects(select_id=project["project_id"])

    def show(self):
        ub.show_modal(self.win, self.owner)
