# -*- coding: utf-8 -*-
"""Options dialog (WPF, defined inline so the extension has no extra files)."""
from pyrevit import forms

from floor_tools import revit_compat as compat
from floor_tools import settings

_XAML = u"""
<Window xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
        xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml"
        Title="Floor / Toposolid &#8594; Fill Region" Width="470" SizeToContent="Height"
        ResizeMode="NoResize" WindowStartupLocation="CenterScreen"
        ShowInTaskbar="False" Topmost="True" FontSize="12">
  <StackPanel Margin="18">
    <TextBlock Text="Create Fill Region from selected Floor(s) / Toposolid(s)" FontSize="15" FontWeight="SemiBold"/>
    <TextBlock x:Name="txt_summary" Margin="0,4,0,14" Foreground="#555555" TextWrapping="Wrap"/>

    <CheckBox x:Name="chk_style" Margin="0,0,0,4" Checked="on_style_changed" Unchecked="on_style_changed"
              Content="Copy each Floor's pattern and colours (Fill Region Type named after the Floor / Toposolid type)"/>
    <TextBlock Text="Pattern source" Margin="20,2,0,0" FontSize="11"/>
    <ComboBox x:Name="cmb_source" Margin="20,2,0,12"/>

    <TextBlock x:Name="lbl_type" Text="Fill Region Type" FontWeight="SemiBold"/>
    <ComboBox x:Name="cmb_type" Margin="0,4,0,4" SelectionChanged="on_type_changed"/>
    <TextBlock x:Name="txt_type_info" Foreground="#555555" FontSize="11"
               TextWrapping="Wrap" Margin="0,0,0,12"/>

    <TextBlock Text="Boundary offset" FontWeight="SemiBold"/>
    <TextBox x:Name="txt_offset" Margin="0,4,0,2" Padding="3"/>
    <TextBlock x:Name="txt_offset_hint" Foreground="#555555" FontSize="11"
               TextWrapping="Wrap" Margin="0,0,0,12"/>

    <CheckBox x:Name="chk_dup" Content="Prevent Duplicate Fill Regions" Margin="0,0,0,6"/>
    <CheckBox x:Name="chk_log" Content="Show detailed log in the output window"/>

    <StackPanel Orientation="Horizontal" HorizontalAlignment="Right" Margin="0,18,0,0">
      <Button Content="Create" Width="90" Height="28" IsDefault="True" Click="on_ok" Margin="0,0,8,0"/>
      <Button Content="Cancel" Width="90" Height="28" IsCancel="True" Click="on_cancel"/>
    </StackPanel>
  </StackPanel>
</Window>
"""


class DialogResult(object):
    def __init__(self, region_type, offset_ft, offset_text, prevent_duplicates, verbose,
                 use_floor_style, pattern_source):
        self.use_floor_style = use_floor_style
        self.pattern_source = pattern_source
        self.region_type = region_type
        self.offset_ft = offset_ft
        self.offset_text = offset_text
        self.prevent_duplicates = prevent_duplicates
        self.verbose = verbose


def _pattern_text(doc, pattern_id, color):
    name = "none"
    try:
        element = doc.GetElement(pattern_id)
        if element is not None:
            name = compat.element_name(element)
    except Exception:
        pass
    if color is not None:
        try:
            return "{} (RGB {}, {}, {})".format(name, color.Red, color.Green, color.Blue)
        except Exception:
            pass
    return name


def describe_type(doc, region_type):
    """Read-only summary of a type's patterns and colours (types are never modified)."""
    try:
        foreground = _pattern_text(doc, region_type.ForegroundPatternId,
                                   getattr(region_type, "ForegroundPatternColor", None))
        background = _pattern_text(doc, region_type.BackgroundPatternId,
                                   getattr(region_type, "BackgroundPatternColor", None))
        return "Foreground: {}   |   Background: {}".format(foreground, background)
    except Exception:
        return ""


class OptionsDialog(forms.WPFWindow):
    def __init__(self, doc, view, region_types, floor_count, defaults, title, source_note):
        forms.WPFWindow.__init__(self, _XAML, literal_string=True)
        self.Title = title
        self._doc = doc
        self._types = region_types
        self.result = None

        self.txt_summary.Text = "{} Floor/Toposolid element(s) selected{}  |  Active view: {}".format(
            floor_count, source_note, view.Name)
        for region_type in region_types:
            self.cmb_type.Items.Add(compat.element_name(region_type))
        self.cmb_type.SelectedIndex = defaults.type_index
        self.txt_offset.Text = defaults.offset_text
        unit = compat.length_unit_label(doc)
        self.txt_offset_hint.Text = (
            "Positive values grow the region outward, negative values shrink it. "
            "Examples: 0, 10 mm, 2\". A plain number uses the project unit{}."
            .format(" ({})".format(unit) if unit else ""))
        self.chk_dup.IsChecked = defaults.prevent_duplicates
        self.chk_log.IsChecked = defaults.verbose_log
        self.cmb_source.Items.Add("Surface pattern (as drawn on the floor in plan views)")
        self.cmb_source.Items.Add("Cut pattern")
        self.cmb_source.SelectedIndex = 1 if defaults.pattern_source == settings.PATTERN_SOURCE_CUT else 0
        self.chk_style.IsChecked = defaults.use_floor_style
        self.on_style_changed(None, None)

    def on_type_changed(self, sender, args):
        index = self.cmb_type.SelectedIndex
        if 0 <= index < len(self._types):
            self.txt_type_info.Text = describe_type(self._doc, self._types[index])

    def on_style_changed(self, sender, args):
        styled = bool(self.chk_style.IsChecked)
        self.cmb_source.IsEnabled = styled
        self.lbl_type.Text = ("Base Fill Region Type (duplicated for new types)" if styled
                              else "Fill Region Type")

    def on_ok(self, sender, args):
        text = self.txt_offset.Text
        offset = compat.parse_length(self._doc, text)
        if offset is None:
            forms.alert("The offset is not a valid length.\nExamples: 0, 25 mm, 2\"",
                        title=settings.COMMAND_TITLE)
            return
        self.result = DialogResult(self._types[self.cmb_type.SelectedIndex], offset,
                                   text.strip() or "0", bool(self.chk_dup.IsChecked),
                                   bool(self.chk_log.IsChecked), bool(self.chk_style.IsChecked),
                                   settings.PATTERN_SOURCE_CUT if self.cmb_source.SelectedIndex == 1
                                   else settings.PATTERN_SOURCE_SURFACE)
        self.DialogResult = True

    def on_cancel(self, sender, args):
        self.DialogResult = False


class _Defaults(object):
    def __init__(self, type_index, user_settings):
        self.type_index = type_index
        self.offset_text = user_settings.offset_text
        self.prevent_duplicates = user_settings.prevent_duplicates
        self.verbose_log = user_settings.verbose_log
        self.use_floor_style = user_settings.use_floor_style
        self.pattern_source = user_settings.pattern_source


def ask_options(doc, view, region_types, floor_count, type_index, user_settings,
                title=u"Floor / Toposolid \u2192 Fill Region", source_note=""):
    """Show the dialog. Returns DialogResult or None when cancelled."""
    dialog = OptionsDialog(doc, view, region_types, floor_count, _Defaults(type_index, user_settings),
                           title, source_note)
    dialog.show_dialog()
    return dialog.result
