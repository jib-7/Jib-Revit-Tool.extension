# -*- coding: utf-8 -*-
"""Shared WPF helpers: window loading, message boxes, list/tree item builders."""
import time

import clr
# "System.Diagnostics.Process" is a separate assembly on .NET 8 (Revit 2025+); without the
# reference "from System.Diagnostics import Process" fails with "Cannot import name Process".
for _assembly in ("PresentationFramework", "PresentationCore", "WindowsBase", "System.Xaml",
                  "System.Diagnostics.Process", "System.ComponentModel.Primitives"):
    try:
        clr.AddReference(_assembly)
    except Exception:
        pass

try:
    from System.Diagnostics import Process, ProcessStartInfo
except Exception:  # never let a missing optional type stop the windows from loading
    Process = None
    ProcessStartInfo = None
from System.Windows import (
    Clipboard, MessageBox, MessageBoxButton, MessageBoxImage, MessageBoxResult, Thickness,
    VerticalAlignment, TextWrapping)
from System.Windows.Controls import ListBoxItem, Orientation, StackPanel, TextBlock, TreeViewItem
from System.Windows.Interop import WindowInteropHelper
from System.Windows.Markup import XamlReader
from System.Windows.Media import BrushConverter, FontFamily

from accqa import logging_manager as log
from accqa import ui_xaml
from accqa.revit_compat import to_text

TITLE = "ACC Quick Access"
GLYPH_FOLDER = u"\uE8B7"   # Segoe MDL2 Assets 'Folder'
CATEGORY_COLORS = {
    "Project Root": "#5B6770",
    "Shared": "#1F6FB2",
    "WIP": "#E08A00",
    "Published": "#2E9D4E",
    "Custom": "#8A55B8",
}
_brushes = BrushConverter()


# ---------------------------------------------------------------------------
# Windows
# ---------------------------------------------------------------------------
class Controls(object):
    """Attribute access to every x:Name element of a parsed window."""

    def __init__(self, window, names):
        for name in names:
            element = window.FindName(name)
            if element is None:
                raise RuntimeError("UI element '%s' was not found in the window definition." % name)
            setattr(self, name, element)


def load_window(xaml):
    """Create a Window from a XAML string and return (window, controls)."""
    window = XamlReader.Parse(xaml)
    return window, Controls(window, ui_xaml.names(xaml))


def _main_window_handle():
    """Handle of the Revit main window (UIApplication.MainWindowHandle, else the process window)."""
    try:
        from pyrevit import HOST_APP
        return HOST_APP.uiapp.MainWindowHandle
    except Exception:
        pass
    if Process is not None:
        return Process.GetCurrentProcess().MainWindowHandle
    return None


def show_modal(window, owner=None):
    """Show a window modally, owned by another WPF window or by the Revit main window."""
    try:
        if owner is not None:
            window.Owner = owner
        else:
            handle = _main_window_handle()
            if handle is not None:
                WindowInteropHelper(window).Owner = handle
    except Exception:
        log.log_exception("Could not set the owner of a window")
    return window.ShowDialog()


def set_header(controls, title, sub=None):
    controls.HeaderTitle.Text = title
    if sub is not None:
        controls.HeaderSub.Text = sub


# ---------------------------------------------------------------------------
# Message boxes
# ---------------------------------------------------------------------------
def _box(text, title, buttons, image, owner=None, default=None):
    text = to_text(text)
    if owner is not None:
        if default is not None:
            return MessageBox.Show(owner, text, title, buttons, image, default)
        return MessageBox.Show(owner, text, title, buttons, image)
    if default is not None:
        return MessageBox.Show(text, title, buttons, image, default)
    return MessageBox.Show(text, title, buttons, image)


def info(text, owner=None, title=TITLE):
    _box(text, title, MessageBoxButton.OK, MessageBoxImage.Information, owner)


def warn(text, owner=None, title=TITLE):
    _box(text, title, MessageBoxButton.OK, MessageBoxImage.Warning, owner)


def error(text, owner=None, title=TITLE):
    _box(text, title, MessageBoxButton.OK, MessageBoxImage.Error, owner)


def confirm(text, owner=None, title=TITLE, warning=False):
    """Yes/No question; 'No' is the default button."""
    image = MessageBoxImage.Warning if warning else MessageBoxImage.Question
    result = _box(text, title, MessageBoxButton.YesNo, image, owner, MessageBoxResult.No)
    return result == MessageBoxResult.Yes


# ---------------------------------------------------------------------------
# Item builders (no data binding: works on IronPython and CPython engines)
# ---------------------------------------------------------------------------
def brush(hex_color):
    return _brushes.ConvertFromString(hex_color)


def icon_block(category, size=17):
    block = TextBlock()
    block.FontFamily = FontFamily("Segoe MDL2 Assets")
    block.Text = GLYPH_FOLDER
    block.FontSize = size
    block.Foreground = brush(CATEGORY_COLORS.get(category, "#5B6770"))
    block.Margin = Thickness(0, 0, 8, 0)
    block.VerticalAlignment = VerticalAlignment.Center
    return block


def text_block(text, bold=False, color=None, size=None, wrap=False):
    block = TextBlock()
    block.Text = to_text(text)
    if bold:
        from System.Windows import FontWeights
        block.FontWeight = FontWeights.SemiBold
    if color:
        block.Foreground = brush(color)
    if size:
        block.FontSize = size
    if wrap:
        block.TextWrapping = TextWrapping.Wrap
    return block


def row_panel(category, main_text, sub_text=None, bold_main=True):
    """Horizontal panel: folder icon + main text (+ grey second line)."""
    panel = StackPanel()
    panel.Orientation = Orientation.Horizontal
    panel.Margin = Thickness(2, 3, 2, 3)
    panel.Children.Add(icon_block(category))
    inner = StackPanel()
    inner.Children.Add(text_block(main_text, bold=bold_main))
    if sub_text:
        inner.Children.Add(text_block(sub_text, color="#667788", size=11))
    panel.Children.Add(inner)
    return panel


def make_list_item(tag, category, main_text, sub_text=None, tooltip=None, bold_main=True):
    item = ListBoxItem()
    item.Content = row_panel(category, main_text, sub_text, bold_main)
    item.Tag = tag
    if tooltip:
        item.ToolTip = to_text(tooltip)
    return item


def make_tree_item(tag, category, main_text, sub_text=None, tooltip=None, bold_main=False):
    item = TreeViewItem()
    item.Header = row_panel(category, main_text, sub_text, bold_main)
    item.Tag = tag
    if tooltip:
        item.ToolTip = to_text(tooltip)
    return item


def selected_tag(list_control):
    """Tag (string) of the selected ListBox/TreeView item, or None."""
    item = list_control.SelectedItem
    if item is None:
        return None
    try:
        return to_text(item.Tag)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Misc
# ---------------------------------------------------------------------------
def format_when(iso_text):
    """'2026-11-20T14:05:00' -> '20 Nov 2026, 14:05'."""
    try:
        return to_text(time.strftime("%d %b %Y, %H:%M", time.strptime(to_text(iso_text), "%Y-%m-%dT%H:%M:%S")))
    except Exception:
        return to_text(iso_text)


def short_text(text, limit=80):
    text = to_text(text)
    return text if len(text) <= limit else text[: limit - 3] + u"..."


def copy_text(text):
    try:
        Clipboard.SetText(to_text(text))
        return True
    except Exception:
        log.log_exception("Clipboard copy failed")
        return False


def open_path(path):
    """Open a file or folder with Windows Explorer / the default app."""
    if Process is None:
        import os
        os.startfile(to_text(path))
        return
    info_obj = ProcessStartInfo(to_text(path))
    info_obj.UseShellExecute = True
    Process.Start(info_obj)


def report_open_result(result, owner=None):
    """Show a message only when something needs the user's attention."""
    if result.status == "error":
        error(result.message + u"\n\nIf the address is wrong, edit the folder in Manage Links.", owner)
    elif result.status == "copied":
        info(result.message, owner)
