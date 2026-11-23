# -*- coding: utf-8 -*-
"""Add / edit folder link dialog and the edit-project dialog."""
from accqa import acc_url_manager, folder_manager, ui_base as ub, ui_xaml, validation
from accqa import config_manager as cfg
from accqa import logging_manager as log
from accqa.revit_compat import to_text
from accqa.validation import CATEGORIES, ValidationError


class LinkDialog(object):
    """mode='add': project + folder (new or existing project). mode='edit': one existing folder."""

    def __init__(self, mode="add", project=None, folder=None, prefill=None, owner=None):
        self.mode = mode
        self.project = project
        self.folder = folder
        self.owner = owner
        self.prefill = prefill or {}
        self.result = None
        self.win, self.c = ub.load_window(ui_xaml.LINK_DIALOG)
        self.projects = folder_manager.sort_projects(cfg.load()["projects"])
        self._populate()
        self._wire()

    # -- setup --------------------------------------------------------------
    def _populate(self):
        c = self.c
        for category in CATEGORIES:
            c.cmbCategory.Items.Add(category)
        for project in self.projects:
            c.cmbProject.Items.Add(project["project_name"])
        if self.mode == "edit":
            ub.set_header(c, u"Edit Folder", u"Project: %s" % validation.project_label(self.project))
            c.cmbProject.Text = self.project["project_name"]
            c.txtNumber.Text = self.project["project_number"]
            c.cmbProject.IsEnabled = False
            c.txtNumber.IsEnabled = False
            c.txtFolder.Text = self.folder["folder_name"]
            c.cmbCategory.SelectedIndex = CATEGORIES.index(self.folder["category"])
            c.txtUrl.Text = self.folder["url"]
            c.txtDesc.Text = self.folder["description"]
        else:
            ub.set_header(c, u"Add ACC Link", u"Save a project folder address for one-click access")
            c.cmbProject.Text = to_text(self.prefill.get("project_name", u""))
            c.txtNumber.Text = to_text(self.prefill.get("project_number", u""))
            c.txtFolder.Text = to_text(self.prefill.get("folder_name", u""))
            category = self.prefill.get("category") or "Shared"
            c.cmbCategory.SelectedIndex = CATEGORIES.index(category) if category in CATEGORIES else 1
            c.txtUrl.Text = to_text(self.prefill.get("url", u""))

    def _wire(self):
        self.c.btnSave.Click += self._on_save
        self.c.btnTest.Click += self._on_test
        self.c.cmbProject.SelectionChanged += self._on_project_selected
        self.c.cmbProject.LostFocus += self._on_project_lost_focus

    # -- helpers ------------------------------------------------------------
    def _project_by_name(self, name):
        key = validation.normalize_name(name)
        for project in self.projects:
            if validation.normalize_name(project["project_name"]) == key:
                return project
        return None

    def _status(self, text, ok=False):
        self.c.lblError.Foreground = ub.brush("#2E7D32" if ok else "#B00020")
        self.c.lblError.Text = to_text(text)

    def _category(self):
        index = self.c.cmbCategory.SelectedIndex
        return CATEGORIES[index] if 0 <= index < len(CATEGORIES) else None

    # -- events -------------------------------------------------------------
    def _on_project_selected(self, sender, args):
        if self.mode != "add":
            return
        selected = self.c.cmbProject.SelectedItem
        if selected is None:
            return
        project = self._project_by_name(to_text(selected))
        if project is not None:
            self.c.txtNumber.Text = project["project_number"]

    def _on_project_lost_focus(self, sender, args):
        if self.mode != "add":
            return
        project = self._project_by_name(self.c.cmbProject.Text)
        if project is not None and not self.c.txtNumber.Text.strip():
            self.c.txtNumber.Text = project["project_number"]

    def _on_test(self, sender, args):
        try:
            url = validation.validate_url(self.c.txtUrl.Text)
        except ValidationError as ex:
            self._status(ex.message_text)
            return
        result = acc_url_manager.open_url(url, force_browser=True)
        self._status(result.message, ok=(result.status == "opened"))

    def _on_save(self, sender, args):
        c = self.c
        try:
            url = validation.validate_url(c.txtUrl.Text)
            category = self._category()
            if self.mode == "add":
                validation.require_text(c.cmbProject.Text, u"Project Name")
            validation.require_text(c.txtFolder.Text, u"Folder Name")
            if category is None:
                raise ValidationError(u"Please choose a folder category.")

            # Soft warnings (the user may still continue).
            if not validation.is_autodesk_url(url):
                if not ub.confirm(u"This address does not look like an Autodesk (ACC) link:\n\n%s\n\n"
                                  u"Save it anyway?" % ub.short_text(url, 120), self.win):
                    return
            exclude = self.project["project_id"] if self.mode == "edit" else None
            elsewhere = folder_manager.find_url_elsewhere(url, exclude)
            if elsewhere:
                if not ub.confirm(u"This exact URL is already saved under '%s' as '%s'.\n\nSave it again here?"
                                  % elsewhere, self.win):
                    return

            if self.mode == "add":
                project_id, folder_id = folder_manager.add_link(
                    c.cmbProject.Text, c.txtNumber.Text, c.txtFolder.Text, category, url, c.txtDesc.Text)
            else:
                folder_manager.update_folder(
                    self.project["project_id"], self.folder["folder_id"],
                    c.txtFolder.Text, category, url, c.txtDesc.Text)
                project_id, folder_id = self.project["project_id"], self.folder["folder_id"]
        except ValidationError as ex:
            self._status(ex.message_text)
            return
        except Exception as ex:
            log.log_exception("Saving a link failed")
            self._status(u"The link could not be saved: %s\nDetails were written to the log file." % to_text(ex))
            return
        self.result = {"project_id": project_id, "folder_id": folder_id}
        self.win.DialogResult = True

    def show(self):
        """Returns {'project_id', 'folder_id'} after a successful save, otherwise None."""
        ub.show_modal(self.win, self.owner)
        return self.result


class ProjectDialog(object):
    """Edit project name, number, cloud project GUID and remembered models."""

    def __init__(self, project, owner=None):
        self.project = project
        self.owner = owner
        self.saved = False
        self.models = list(project.get("models", []))
        self.win, self.c = ub.load_window(ui_xaml.PROJECT_DIALOG)
        ub.set_header(self.c, u"Edit Project", validation.project_label(project))
        self.c.txtName.Text = project["project_name"]
        self.c.txtNumber.Text = project["project_number"]
        self.c.txtGuid.Text = project["cloud_project_guid"]
        self._fill_models()
        self.c.btnSave.Click += self._on_save
        self.c.btnRemoveModel.Click += self._on_remove_model

    def _fill_models(self):
        self.c.lstModels.Items.Clear()
        for index, model in enumerate(self.models):
            label = model.get("title") or u"(untitled)"
            if model.get("model_guid"):
                label += u"   [%s]" % model["model_guid"]
            self.c.lstModels.Items.Add(ub.make_list_item(u"m|%d" % index, "Custom", label, bold_main=False))

    def _on_remove_model(self, sender, args):
        tag = ub.selected_tag(self.c.lstModels)
        if not tag:
            return
        index = int(tag.split(u"|")[1])
        if 0 <= index < len(self.models):
            del self.models[index]
            self._fill_models()

    def _on_save(self, sender, args):
        c = self.c
        try:
            folder_manager.update_project(
                self.project["project_id"], c.txtName.Text, c.txtNumber.Text, c.txtGuid.Text, self.models)
        except ValidationError as ex:
            c.lblError.Text = ex.message_text
            return
        except Exception as ex:
            log.log_exception("Saving a project failed")
            c.lblError.Text = u"The project could not be saved: %s" % to_text(ex)
            return
        self.saved = True
        self.win.DialogResult = True

    def show(self):
        ub.show_modal(self.win, self.owner)
        return self.saved
