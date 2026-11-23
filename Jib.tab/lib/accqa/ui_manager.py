# -*- coding: utf-8 -*-
"""Entry points called by the ribbon buttons. Every entry point is wrapped by run_safe()."""
from accqa import config_manager as cfg
from accqa import logging_manager as log
from accqa.revit_compat import to_text


def run_safe(func, *args, **kwargs):
    """Run a command; show a friendly message (never a traceback) if something unexpected fails."""
    try:
        from accqa import ui_base as ub
    except Exception:
        log.log_exception("WPF could not be loaded")
        raise
    try:
        notice = None
        try:
            cfg.load()
            notice = cfg.take_notice()
        except Exception:
            log.log_exception("Configuration could not be loaded")
            ub.error(u"The ACC Quick Access configuration could not be loaded or created.\n\n"
                     u"Details were written to:\n%s" % log.get_log_path())
            return
        if notice:
            ub.warn(notice)
        return func(*args, **kwargs)
    except Exception as ex:
        log.log_exception("Unexpected error in %s" % getattr(func, "__name__", "command"))
        try:
            import traceback
            print(traceback.format_exc())  # also visible in the pyRevit output window
        except Exception:
            pass
        ub.error(u"Something went wrong: %s\n\nTechnical details were written to the log file:\n%s"
                 % (to_text(ex), log.get_log_path()))


# ---------------------------------------------------------------------------
# Project access
# ---------------------------------------------------------------------------
def show_current_project():
    from accqa.ui_current_window import CurrentProjectWindow
    CurrentProjectWindow().show()


def show_all_projects():
    from accqa.ui_projects_window import ProjectsWindow
    ProjectsWindow().show()


def show_recent_projects():
    from accqa.ui_recent_window import RecentWindow
    RecentWindow().show()


# ---------------------------------------------------------------------------
# Folder access (Shared / WIP / Published / Custom Folders)
# ---------------------------------------------------------------------------
def quick_open_category(category):
    """Open a folder of the given category for the current (or manually chosen) project."""
    from accqa import acc_url_manager, folder_manager, project_detector, ui_base as ub
    from accqa.ui_current_window import link_model_to_project
    from accqa.ui_link_dialog import LinkDialog
    from accqa.ui_picker import pick_folder, pick_project
    from accqa.validation import CATEGORY_LABELS, project_label

    label = CATEGORY_LABELS.get(category, category)
    data = cfg.load()
    if not data["projects"]:
        ub.info(u"No ACC links are saved yet.\n\nUse the 'Add ACC Link' button to save your first project folder.")
        return

    detection = project_detector.detect_current_project(data)
    project = detection.project
    if project is None:
        if detection.ambiguous:
            question = u"More than one saved project matches this model. Choose the project manually?"
        elif detection.has_project_document:
            question = u"The current Revit project could not be identified automatically. Choose the project manually?"
        else:
            question = u"No Revit project is open. Choose a project manually?"
        if not ub.confirm(question):
            return
        picked = pick_project(data["projects"], allow_remember=detection.has_project_document)
        if not picked:
            return
        project = folder_manager.find_project(cfg.load(), picked[0])
        if picked[1]:
            link_model_to_project(detection, picked[0])
    if project is None:
        return

    folders = folder_manager.folders_in_category(project, category)
    if not folders:
        if ub.confirm(u"No '%s' folder is saved for %s.\n\nWould you like to add one now?" % (label, project_label(project))):
            LinkDialog("add", prefill={"project_name": project["project_name"],
                                       "project_number": project["project_number"],
                                       "category": category}).show()
        return
    folder = folders[0]
    if len(folders) > 1:
        chosen = pick_folder(project, folders, prompt=u"%s - several '%s' folders are saved. Choose one:"
                             % (project_label(project), label))
        if not chosen:
            return
        folder = folder_manager.find_folder(project, chosen)
    ub.report_open_result(acc_url_manager.open_folder(project, folder))


# ---------------------------------------------------------------------------
# Management
# ---------------------------------------------------------------------------
def show_add_link():
    from accqa import project_detector
    from accqa.ui_current_window import link_model_to_project, suggest_prefill
    from accqa.ui_link_dialog import LinkDialog

    prefill = {}
    detection = None
    try:
        detection = project_detector.detect_current_project()
        if detection.project is not None:
            prefill = {"project_name": detection.project["project_name"],
                       "project_number": detection.project["project_number"]}
        elif detection.has_project_document and not detection.ambiguous:
            prefill = suggest_prefill(detection)
    except Exception:
        log.log_exception("Could not pre-fill the Add ACC Link dialog")
    result = LinkDialog("add", prefill=prefill).show()
    if result and detection is not None and detection.project is None and detection.has_project_document:
        # The user registered a folder for the project of the open model: remember that model.
        link_model_to_project(detection, result["project_id"])


def show_manage_links():
    from accqa.ui_manage_window import ManageWindow
    ManageWindow().show()


def show_settings():
    from accqa.ui_settings_window import SettingsWindow
    SettingsWindow().show()


def show_backup_restore():
    from accqa.ui_backup_window import BackupWindow
    BackupWindow().show()
