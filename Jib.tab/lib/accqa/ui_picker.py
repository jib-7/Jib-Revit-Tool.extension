# -*- coding: utf-8 -*-
"""Generic searchable list picker (used to choose a project or a folder)."""
from accqa import ui_base as ub, ui_xaml
from accqa.revit_compat import to_text
from accqa.validation import normalize_name


def pick_item(title, prompt, items, remember_text=None, owner=None):
    """items: [(tag, category, main_text, sub_text)]. Returns (tag, remember_flag) or None."""
    win, c = ub.load_window(ui_xaml.PICKER_WINDOW)
    ub.set_header(c, title)
    c.lblPrompt.Text = to_text(prompt)
    if remember_text:
        c.chkRemember.Content = to_text(remember_text)
    else:
        from System.Windows import Visibility
        c.chkRemember.Visibility = Visibility.Collapsed
    state = {"result": None}

    def refill(sender=None, args=None):
        needle = normalize_name(c.txtSearch.Text)
        c.lstItems.Items.Clear()
        first = None
        for tag, category, main_text, sub_text in items:
            if needle and needle not in normalize_name(main_text) and needle not in normalize_name(sub_text or u""):
                continue
            item = ub.make_list_item(tag, category, main_text, sub_text)
            c.lstItems.Items.Add(item)
            if first is None:
                first = item
        if first is not None:
            first.IsSelected = True

    def accept(sender=None, args=None):
        tag = ub.selected_tag(c.lstItems)
        if tag is None:
            ub.info(u"Please select an item first.", win)
            return
        state["result"] = (tag, bool(c.chkRemember.IsChecked))
        win.DialogResult = True

    c.txtSearch.TextChanged += refill
    c.btnOK.Click += accept
    c.lstItems.MouseDoubleClick += lambda s, a: accept() if c.lstItems.SelectedItem is not None else None
    refill()
    ub.show_modal(win, owner)
    return state["result"]


def pick_project(projects, owner=None, allow_remember=False, prompt=None):
    """Returns (project_id, remember) or None."""
    from accqa import folder_manager
    from accqa.validation import project_label
    items = []
    for project in folder_manager.sort_projects(projects):
        count = len(project["folders"])
        items.append((project["project_id"], "Project Root", project_label(project),
                      u"%d folder%s" % (count, u"" if count == 1 else u"s")))
    remember = u"Remember this Revit model for the selected project" if allow_remember else None
    return pick_item(u"Select Project", prompt or u"Choose the project:", items, remember, owner)


def pick_folder(project, folders, owner=None, prompt=None):
    """Returns the chosen folder_id or None."""
    from accqa.validation import project_label
    items = [(f["folder_id"], f["category"], f["folder_name"], f.get("description") or u"") for f in folders]
    result = pick_item(u"Select Folder", prompt or (u"%s - choose a folder to open:" % project_label(project)),
                       items, None, owner)
    return result[0] if result else None
