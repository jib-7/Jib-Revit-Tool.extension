# -*- coding: utf-8 -*-
"""All Projects window: project > category > folder tree with search and management."""
from accqa import acc_url_manager, folder_manager, ui_base as ub, ui_xaml
from accqa import config_manager as cfg
from accqa import logging_manager as log
from accqa.revit_compat import to_text
from accqa.ui_link_dialog import LinkDialog, ProjectDialog
from accqa.validation import CATEGORY_LABELS, EN_DASH, project_label

SEP = u"|"


class ProjectsWindow(object):
    def __init__(self, owner=None):
        self.owner = owner
        self.win, self.c = ub.load_window(ui_xaml.PROJECTS_WINDOW)
        self.expanded = set()
        self.first_load = True
        self.selected = None
        c = self.c
        c.txtSearch.TextChanged += lambda s, a: self.refresh()
        c.btnClearSearch.Click += lambda s, a: self._clear_search()
        c.tree.MouseDoubleClick += self._on_double_click
        c.tree.KeyDown += self._on_key
        c.btnOpen.Click += lambda s, a: self._open_selected()
        c.btnAddProject.Click += lambda s, a: self._add_project()
        c.btnAddFolder.Click += lambda s, a: self._add_folder()
        c.btnEdit.Click += lambda s, a: self._edit()
        c.btnDelete.Click += lambda s, a: self._delete()
        c.btnExpand.Click += lambda s, a: self._set_all(True)
        c.btnCollapse.Click += lambda s, a: self._set_all(False)
        self.refresh()

    # -- tree ---------------------------------------------------------------
    def _walk(self, items):
        for item in items:
            yield item
            for child in self._walk(item.Items):
                yield child

    def _collect_state(self):
        self.selected = ub.selected_tag(self.c.tree) or self.selected
        for item in self._walk(self.c.tree.Items):
            tag = to_text(item.Tag)
            if item.IsExpanded:
                self.expanded.add(tag)
            else:
                self.expanded.discard(tag)

    def refresh(self):
        c = self.c
        if not self.first_load:
            self._collect_state()
        data = cfg.load()
        query = c.txtSearch.Text
        results = folder_manager.search_projects(data["projects"], query)
        total_folders = folder_manager.count_folders(data)
        expand_all_first = self.first_load and total_folders <= 40
        c.tree.Items.Clear()
        for project, folders, force in results:
            pid = project["project_id"]
            ptag = u"project" + SEP + pid
            pitem = ub.make_tree_item(
                ptag, "Project Root", project_label(project),
                u"%d folder%s" % (len(project["folders"]), u"" if len(project["folders"]) == 1 else u"s"),
                bold_main=True)
            groups = folder_manager.group_by_category({"folders": folders})
            for category, label, flist in groups:
                ctag = SEP.join([u"cat", pid, category])
                citem = ub.make_tree_item(ctag, category, label, u"(%d)" % len(flist), bold_main=True)
                for folder in flist:
                    ftag = SEP.join([u"folder", pid, folder["folder_id"]])
                    tip = folder["url"] + ((u"\n" + folder["description"]) if folder["description"] else u"")
                    fitem = ub.make_tree_item(ftag, category, folder["folder_name"], None, tooltip=tip)
                    fitem.IsSelected = (ftag == self.selected)
                    citem.Items.Add(fitem)
                citem.IsExpanded = bool(force or expand_all_first or ctag in self.expanded)
                citem.IsSelected = (ctag == self.selected)
                pitem.Items.Add(citem)
            pitem.IsExpanded = bool(force or expand_all_first or ptag in self.expanded)
            pitem.IsSelected = (ptag == self.selected)
            c.tree.Items.Add(pitem)
        self.first_load = False
        shown = len(results)
        c.lblStatus.Text = u"%d of %d project%s shown, %d folder%s saved in total" % (
            shown, len(data["projects"]), u"" if len(data["projects"]) == 1 else u"s",
            total_folders, u"" if total_folders == 1 else u"s")
        if not data["projects"]:
            c.lblStatus.Text = u"No projects saved yet. Click 'Add Project' to register your first ACC folder."

    def _set_all(self, expanded):
        for item in self._walk(self.c.tree.Items):
            item.IsExpanded = expanded

    def _clear_search(self):
        self.c.txtSearch.Text = u""

    # -- selection helpers ----------------------------------------------------
    def _selection(self):
        tag = ub.selected_tag(self.c.tree)
        if not tag:
            return None, None, None
        parts = tag.split(SEP)
        kind = parts[0]
        pid = parts[1] if len(parts) > 1 else None
        extra = parts[2] if len(parts) > 2 else None
        return kind, pid, extra

    def _load(self, pid, fid=None):
        data = cfg.load()
        project = folder_manager.find_project(data, pid)
        folder = folder_manager.find_folder(project, fid) if fid else None
        return project, folder

    # -- actions --------------------------------------------------------------
    def _on_double_click(self, sender, args):
        kind, pid, extra = self._selection()
        if kind == "folder":
            self._open_folder(pid, extra)

    def _on_key(self, sender, args):
        from System.Windows.Input import Key
        if args.Key == Key.Enter:
            self._open_selected()
            args.Handled = True

    def _open_selected(self):
        kind, pid, extra = self._selection()
        if kind != "folder":
            ub.info(u"Select a folder (or double-click it) to open it.", self.win)
            return
        self._open_folder(pid, extra)

    def _open_folder(self, pid, fid):
        project, folder = self._load(pid, fid)
        if folder is None:
            ub.warn(u"That folder no longer exists.", self.win)
            self.refresh()
            return
        ub.report_open_result(acc_url_manager.open_folder(project, folder), self.win)

    def _add_project(self):
        result = LinkDialog("add", owner=self.win).show()
        if result:
            self.selected = SEP.join([u"folder", result["project_id"], result["folder_id"]])
            self.refresh()

    def _add_folder(self):
        kind, pid, extra = self._selection()
        if pid is None:
            ub.info(u"Select a project first, then click Add Folder.", self.win)
            return
        project, _ = self._load(pid)
        if project is None:
            return
        prefill = {"project_name": project["project_name"], "project_number": project["project_number"]}
        if kind == "cat":
            prefill["category"] = extra
        result = LinkDialog("add", prefill=prefill, owner=self.win).show()
        if result:
            self.selected = SEP.join([u"folder", result["project_id"], result["folder_id"]])
            self.expanded.add(u"project" + SEP + result["project_id"])
            self.refresh()

    def _edit(self):
        kind, pid, extra = self._selection()
        if kind == "project":
            project, _ = self._load(pid)
            if project is not None and ProjectDialog(project, self.win).show():
                self.refresh()
        elif kind == "folder":
            project, folder = self._load(pid, extra)
            if folder is not None and LinkDialog("edit", project, folder, owner=self.win).show():
                self.refresh()
        else:
            ub.info(u"Select a project or a folder to edit.", self.win)

    def _delete(self):
        kind, pid, extra = self._selection()
        if kind == "folder":
            project, folder = self._load(pid, extra)
            if folder is None:
                return
            settings = cfg.get_settings(cfg.load())
            if settings["confirm_delete"] and not ub.confirm(
                    u"Delete the folder '%s' from '%s'?\n\nThis only removes the saved link. Nothing is "
                    u"deleted in ACC." % (folder["folder_name"], project["project_name"]), self.win, warning=True):
                return
            folder_manager.delete_folder(pid, extra)
            self.selected = None
            self.refresh()
        elif kind == "project":
            project, _ = self._load(pid)
            if project is None:
                return
            if not ub.confirm(
                    u"Delete the project '%s' and all %d saved folder link(s)?\n\nThis only removes the saved "
                    u"links. Nothing is deleted in ACC. Use Backup / Restore first if you may need them again."
                    % (project_label(project), len(project["folders"])), self.win, warning=True):
                return
            folder_manager.delete_project(pid)
            self.selected = None
            self.refresh()
        else:
            ub.info(u"Select a project or a folder to delete.", self.win)

    def show(self):
        ub.show_modal(self.win, self.owner)
