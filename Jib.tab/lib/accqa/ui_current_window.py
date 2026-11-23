# -*- coding: utf-8 -*-
"""Current Project window: detect the project of the active model and list its folders."""
from System.Windows import Visibility

from accqa import acc_url_manager, folder_manager, project_detector, ui_base as ub, ui_xaml
from accqa import config_manager as cfg
from accqa import logging_manager as log
from accqa.revit_compat import to_text
from accqa.ui_link_dialog import LinkDialog
from accqa.ui_picker import pick_project
from accqa.validation import project_label, EN_DASH
import re

NOT_REGISTERED = u"No saved ACC links found for this project. Would you like to register it?"


def link_model_to_project(detection, project_id):
    """Remember the active model for a project (used after a manual choice / registration)."""
    info = detection.info
    if not info.get("has_document") or info.get("is_family"):
        return False
    return folder_manager.link_model(project_id, info.get("title"), info.get("model_guid"), info.get("project_guid"))


def suggest_prefill(detection):
    """Pre-fill the Add dialog from the model. These are suggestions the user can change."""
    info = detection.info
    prefill = {}
    if info.get("acc_project_name"):
        prefill["project_name"] = info["acc_project_name"]
    match = re.match(r"^\s*(\d{3,})[\s_\-]", to_text(info.get("title")))
    if match:
        prefill["project_number"] = match.group(1)
    return prefill


class CurrentProjectWindow(object):
    def __init__(self, owner=None):
        self.owner = owner
        self.win, self.c = ub.load_window(ui_xaml.CURRENT_WINDOW)
        self.detection = project_detector.detect_current_project()
        self.project_id = self.detection.project["project_id"] if self.detection.project else None
        self.manual = False
        c = self.c
        c.btnOpen.Click += lambda s, a: self._open_selected()
        c.lstFolders.MouseDoubleClick += lambda s, a: self._open_selected()
        c.btnAddFolder.Click += lambda s, a: self._add_folder()
        c.btnRegister.Click += lambda s, a: self._register()
        c.btnChange.Click += lambda s, a: self._change()
        self.refresh()

    def _project(self):
        if not self.project_id:
            return None
        return folder_manager.find_project(cfg.load(), self.project_id)

    def refresh(self):
        c = self.c
        d = self.detection
        info = d.info
        project = self._project()
        ub.set_header(c, u"Current Project", u"")
        if not info.get("has_document"):
            c.lblModel.Text = u"No Revit project is open."
        elif info.get("is_family"):
            c.lblModel.Text = u"The active document is a family (%s), not a project." % info.get("title")
        else:
            kind = {True: u"ACC / cloud model", False: u"not a cloud model", None: u"cloud status unknown"}[info.get("is_cloud")]
            c.lblModel.Text = u"Revit model: %s  (%s)" % (info.get("title"), kind)
        c.txtDiag.Text = d.diagnostics_text()
        c.lblMessage.Text = u""
        c.lstFolders.Items.Clear()
        if project is not None:
            c.lblProject.Text = u"Current Project: %s" % project_label(project)
            if self.manual:
                c.lblMatch.Text = u"Selected manually."
            else:
                c.lblMatch.Text = u"Identified by %s (%s confidence)." % (d.method_label, d.confidence)
                if d.confidence == "low":
                    c.lblMatch.Text += u" Please check this is the right project - use 'Select Project...' to change it."
            c.btnRegister.Visibility = Visibility.Collapsed
            c.btnAddFolder.Visibility = Visibility.Visible
            for category, label, folders in folder_manager.group_by_category(
                    project, folder_manager.DISPLAY_ORDER_CURRENT):
                for folder in folders:
                    sub = label + ((u"  -  " + folder["description"]) if folder["description"] else u"")
                    c.lstFolders.Items.Add(ub.make_list_item(
                        folder["folder_id"], category, folder["folder_name"], sub, tooltip=folder["url"]))
            if c.lstFolders.Items.Count == 0:
                c.lblMessage.Text = u"This project has no saved folders yet. Click 'Add Folder...'."
            else:
                c.lstFolders.Items[0].IsSelected = True
        else:
            c.lblProject.Text = u"Current Project: not identified"
            c.lblMatch.Text = u""
            c.btnAddFolder.Visibility = Visibility.Collapsed
            c.btnRegister.Visibility = Visibility.Visible if d.has_project_document else Visibility.Collapsed
            if d.ambiguous:
                names = u"; ".join(project_label(p) for p in d.candidates)
                c.lblMessage.Text = (u"More than one saved project matches this model (%s). "
                                     u"Please choose the correct one with 'Select Project...'." % names)
            elif d.has_project_document:
                c.lblMessage.Text = NOT_REGISTERED
            else:
                c.lblMessage.Text = u"You can still pick a project manually with 'Select Project...'."

    def _open_selected(self):
        project = self._project()
        tag = ub.selected_tag(self.c.lstFolders)
        if project is None or not tag:
            ub.info(u"Select a folder first.", self.win)
            return
        folder = folder_manager.find_folder(project, tag)
        if folder is None:
            return
        ub.report_open_result(acc_url_manager.open_folder(project, folder), self.win)

    def _add_folder(self):
        project = self._project()
        if project is None:
            return
        prefill = {"project_name": project["project_name"], "project_number": project["project_number"]}
        if LinkDialog("add", prefill=prefill, owner=self.win).show():
            self.refresh()

    def _register(self):
        result = LinkDialog("add", prefill=suggest_prefill(self.detection), owner=self.win).show()
        if result:
            # The user registered this project from this model: remember the association.
            link_model_to_project(self.detection, result["project_id"])
            self.project_id = result["project_id"]
            self.manual = True
            self.refresh()

    def _change(self):
        data = cfg.load()
        if not data["projects"]:
            ub.info(u"No projects are saved yet. Use 'Add Project...' or the Add ACC Link button first.", self.win)
            return
        picked = pick_project(data["projects"], self.win, allow_remember=self.detection.has_project_document)
        if not picked:
            return
        self.project_id, remember = picked
        self.manual = True
        if remember:
            link_model_to_project(self.detection, self.project_id)
        self.refresh()

    def show(self):
        ub.show_modal(self.win, self.owner)
