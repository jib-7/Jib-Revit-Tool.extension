# -*- coding: utf-8 -*-
"""Main WPF window. Compatible with IronPython 2.7 / 3.4 (no f-strings)."""
import os
import clr
clr.AddReference('PresentationFramework')
clr.AddReference('PresentationCore')
clr.AddReference('WindowsBase')
import functools
from System.Collections.Generic import Dictionary, List
from System.Windows.Controls import Button
from System.Windows.Media import Brushes
from Microsoft.Win32 import OpenFileDialog, SaveFileDialog
from Autodesk.Revit.DB import ElementId
from pyrevit import forms

from lib import utils, revit_compat as rc, colour_manager as cm
from lib import line_weight_manager as lwm, line_pattern_manager as lpm, line_style_manager as lsm
from lib import filled_region_manager as frm, boundary_manager as bm, selection
from lib import transaction_manager as tm, batch_replace as br, project_audit as pa
from lib import preset_manager as pm, preview_manager, report_manager as rpt

UI_DIR = os.path.dirname(os.path.abspath(__file__))
TITLE = utils.APP_TITLE
MODES = {'existing': 'RbExisting', 'duplicate': 'RbDuplicate', 'new': 'RbNew', 'edit': 'RbEdit'}


def row(**kw):
    d = Dictionary[str, object]()
    for k, v in kw.items():
        d[k] = v
    return d


def to_list(rows):
    lst = List[object]()
    for r in rows:
        lst.Add(r)
    return lst


def safe(fn):
    @functools.wraps(fn)
    def wrapper(self, *args):
        try:
            return fn(self, *args)
        except Exception as ex:
            self._error(ex)
    return wrapper


class AppState(object):
    """Survives re-creation of the window (needed while picking in Revit)."""
    def __init__(self):
        self.regions = []
        self.pending = None
        self.tab = 0
        self.mode = 'new'
        self.source = None
        self.name = ''
        self.weight = 3
        self.rgb = (0, 0, 0)
        self.pattern_name = 'Solid'
        self.apply_scope = 'selected'
        self.apply_type = None
        self.type_project = False
        self.sel_type = None


STATE = AppState()


class ColourPickerDialog(forms.WPFWindow):
    _ready = False

    def __init__(self, xaml, rgb, owner=None):
        forms.WPFWindow.__init__(self, xaml)
        if owner is not None:
            try:
                self.Owner = owner
            except Exception:
                pass
        self.result = None
        palette = [(0, 0, 0), (255, 255, 255), (255, 0, 0), (0, 160, 0), (0, 0, 255), (255, 255, 0),
                   (255, 0, 255), (0, 255, 255), (128, 128, 128), (192, 192, 192), (255, 128, 0),
                   (0, 100, 0), (128, 64, 0), (128, 0, 128), (0, 128, 128), (0, 0, 128)]
        for c in palette:
            b = Button()
            b.Width = 26
            b.Height = 26
            b.Margin = System_Thickness(2)
            b.Background = cm.to_wpf_brush(c)
            b.ToolTip = cm.rgb_to_hex(c)

            def handler(s, a, col=c):
                self._set(col)
            b.Click += handler
            self.Palette.Children.Add(b)
        self._ready = True
        self._set(rgb)

    def _set(self, rgb):
        self._ready = False
        self.SliderR.Value, self.SliderG.Value, self.SliderB.Value = rgb[0], rgb[1], rgb[2]
        self._ready = True
        self._sync(rgb, from_hex=False)

    def _sync(self, rgb, from_hex):
        self._rgb = tuple(int(v) for v in rgb)
        self.ValR.Text, self.ValG.Text, self.ValB.Text = str(rgb[0]), str(rgb[1]), str(rgb[2])
        self.Swatch.Background = cm.to_wpf_brush(rgb)
        if not from_hex:
            self._ready = False
            self.HexBox.Text = cm.rgb_to_hex(rgb)
            self._ready = True

    def slider_changed(self, sender, args):
        if not self._ready:
            return
        self._sync((int(self.SliderR.Value), int(self.SliderG.Value), int(self.SliderB.Value)), False)

    def hex_changed(self, sender, args):
        if not self._ready:
            return
        rgb = cm.hex_to_rgb(self.HexBox.Text)
        if rgb is None:
            return
        self._ready = False
        self.SliderR.Value, self.SliderG.Value, self.SliderB.Value = rgb[0], rgb[1], rgb[2]
        self._ready = True
        self._sync(rgb, True)

    def ok_click(self, sender, args):
        self.result = self._rgb
        self.Close()

    def cancel_click(self, sender, args):
        self.result = None
        self.Close()


def System_Thickness(v):
    from System.Windows import Thickness
    return Thickness(v)


class MainWindow(forms.WPFWindow):
    _ready = False
    _loading = False

    # ------------------------------------------------------------------ init
    def __init__(self, xaml, uidoc, state):
        forms.WPFWindow.__init__(self, xaml)
        self.uidoc = uidoc
        self.doc = uidoc.Document
        self.S = state
        self.cur = {'weight': 3, 'rgb': (0, 0, 0), 'pattern': None}
        self.orig = None
        self._seg_rows_all = []
        self.seg_cache = {}
        self._audit_rows = []
        self._style_view = []
        self._pat_view = []
        self.preview = preview_manager.PreviewPanel(os.path.join(UI_DIR, 'preview_control.xaml'))
        self.PreviewHost.Content = self.preview.root
        self._load_data()
        self._loading = True
        try:
            for w in lwm.weights():
                self.WeightCombo.Items.Add(lwm.label(w))
            self.type_names = [n for n, _ in frm.region_types(self.doc)]
            for n in self.type_names:
                self.TypeCombo.Items.Add(n)
                self.ApplyTypeCombo.Items.Add(n)
            self.RbScopeSel.IsChecked = True
            self.RbAuditView.IsChecked = True
            self.AuditUnwanted.Text = '<Medium Lines>, <Thin Lines>, <Wide Lines>'
        finally:
            self._loading = False
        self._restore_state()
        self._ready = True
        self.refresh_regions()
        self.ms_refresh()
        self._refresh_presets()
        self._fill_replace_combos()
        self._enter_mode(keep_values=True)
        self._status('Ready. Active document: %s (Revit %s). Select Filled Regions in tab 1, or build a Line Style in tab 2.'
                     % (self.doc.Title, rc.revit_version(self.doc)))

    # ------------------------------------------------------------- utilities
    def _load_data(self):
        self.patterns = lpm.list_patterns(self.doc)
        self.pat_idx = lpm.index_by_idv(self.patterns)
        self.styles = lsm.list_styles(self.doc, self.pat_idx)
        self.info_cache = {}

    def _status(self, msg, error=False):
        self.StatusText.Text = msg
        self.StatusText.Foreground = Brushes.Firebrick if error else Brushes.Black

    def _error(self, ex):
        try:
            path = os.path.join(utils.config_dir(), 'last_error.log')
            utils.write_text(path, utils.trace())
        except Exception:
            pass
        self._status('Error: %s' % ex, True)
        forms.alert('The operation could not be completed. No partial changes were kept.\n\n%s' % ex,
                    title=TITLE, warn_icon=True)

    def _info(self, msg, warn=False):
        forms.alert(msg, title=TITLE, warn_icon=warn)

    def _confirm(self, msg, ok_label='Apply Changes'):
        r = forms.alert(msg, title=TITLE, options=[ok_label, 'Cancel'])
        return r == ok_label

    def _fill_combo(self, combo, items):
        combo.Items.Clear()
        for it in items:
            combo.Items.Add(it)

    # ---------------------------------------------------------------- state
    def _save_state(self):
        S = self.S
        S.tab = self.MainTabs.SelectedIndex
        S.name = self.NameBox.Text
        S.weight = self.cur['weight']
        S.rgb = self.cur['rgb']
        S.pattern_name = self.cur['pattern']['name'] if self.cur['pattern'] else 'Solid'
        S.apply_scope = self._apply_scope()
        S.apply_type = self.ApplyTypeCombo.SelectedItem
        S.type_project = bool(self.ChkTypeProject.IsChecked)
        S.sel_type = self.TypeCombo.SelectedItem

    def _restore_state(self):
        S = self.S
        self._loading = True
        try:
            getattr(self, MODES[S.mode]).IsChecked = True
            scope_rb = {'selected': 'RbApplySelected', 'segments': 'RbApplySegments',
                        'view': 'RbApplyView', 'type': 'RbApplyType'}[S.apply_scope]
            getattr(self, scope_rb).IsChecked = True
            self.ChkTypeProject.IsChecked = S.type_project
            if S.apply_type in self.type_names:
                self.ApplyTypeCombo.SelectedItem = S.apply_type
            if S.sel_type in self.type_names:
                self.TypeCombo.SelectedItem = S.sel_type
            self.MainTabs.SelectedIndex = S.tab
        finally:
            self._loading = False
        self._fill_style_combo('', S.source)
        pat = lpm.find_by_name(self.patterns, S.pattern_name) or self.patterns[0]
        self._set_cur(S.weight, S.rgb, pat)
        self._loading = True
        self.NameBox.Text = S.name
        self._loading = False

    # ------------------------------------------------------- combos: styles
    def _style_label(self, s):
        return '%s   [w%s | %s | %s]' % (s['name'], s['weight'], s['hex'], s['pattern_name'])

    def _fill_style_combo(self, flt='', select_name=None):
        flt = (flt or '').lower()
        self._style_view = [s for s in self.styles if flt in s['name'].lower()]
        was = self._loading
        self._loading = True
        try:
            self._fill_combo(self.StyleCombo, [self._style_label(s) for s in self._style_view])
            for i, s in enumerate(self._style_view):
                if select_name and s['name'].lower() == select_name.lower():
                    self.StyleCombo.SelectedIndex = i
                    break
        finally:
            self._loading = was

    def _fill_pattern_combo(self, flt='', select=None):
        flt = (flt or '').lower()
        self._pat_view = [p for p in self.patterns if flt in p['name'].lower()]
        was = self._loading
        self._loading = True
        try:
            self._fill_combo(self.PatternCombo, [p['name'] for p in self._pat_view])
            if select is not None:
                for i, p in enumerate(self._pat_view):
                    if p['idv'] == select['idv']:
                        self.PatternCombo.SelectedIndex = i
                        break
        finally:
            self._loading = was

    def _current_source(self):
        if not self.S.source:
            return None
        return lsm.get_by_name(self.styles, self.S.source)

    @safe
    def style_search_changed(self, sender, args):
        if not self._ready or self._loading:
            return
        self._fill_style_combo(self.StyleSearch.Text, self.S.source)

    @safe
    def style_selected(self, sender, args):
        if not self._ready or self._loading:
            return
        i = self.StyleCombo.SelectedIndex
        if i < 0 or i >= len(self._style_view):
            return
        self.S.source = self._style_view[i]['name']
        self._load_source_into_form()

    @safe
    def pattern_search_changed(self, sender, args):
        if not self._ready or self._loading:
            return
        self._fill_pattern_combo(self.PatternSearch.Text, self.cur['pattern'])

    @safe
    def pattern_changed(self, sender, args):
        if not self._ready or self._loading:
            return
        i = self.PatternCombo.SelectedIndex
        if 0 <= i < len(self._pat_view):
            self.cur['pattern'] = self._pat_view[i]
            self.update_preview()

    # ------------------------------------------------------------ form model
    def _set_rgb_controls(self, rgb):
        self.RBox.Text, self.GBox.Text, self.BBox.Text = str(rgb[0]), str(rgb[1]), str(rgb[2])
        self.HexBox.Text = cm.rgb_to_hex(rgb)
        self.ColourSwatch.Background = cm.to_wpf_brush(rgb)

    def _set_cur(self, weight, rgb, pat):
        was = self._loading
        self._loading = True
        try:
            w = lwm.clamp(weight or 1)
            self.cur['weight'] = w
            self.cur['rgb'] = tuple(rgb)
            self.cur['pattern'] = pat
            self.WeightCombo.SelectedIndex = w - 1
            self.MmBox.Text = utils.fmt_mm(lwm.mm_for(w))
            self._set_rgb_controls(rgb)
            self.PatternSearch.Text = ''
            self._fill_pattern_combo('', pat)
        finally:
            self._loading = was
        if self._ready:
            self.update_preview()

    def _collect_form(self):
        pat = self.cur['pattern'] or self.patterns[0]
        return {'name': self.NameBox.Text.strip(), 'weight': self.cur['weight'],
                'rgb': self.cur['rgb'], 'pattern': pat}

    @safe
    def weight_changed(self, sender, args):
        if not self._ready or self._loading:
            return
        i = self.WeightCombo.SelectedIndex
        if i < 0:
            return
        self.cur['weight'] = i + 1
        self._loading = True
        self.MmBox.Text = utils.fmt_mm(lwm.mm_for(i + 1))
        self._loading = False
        self.update_preview()

    @safe
    def mm_snap(self, sender, args):
        mm = utils.safe_float(self.MmBox.Text)
        if mm is None or mm <= 0:
            self._status('Enter a thickness in mm greater than 0.', True)
            return
        w = lwm.nearest_weight(mm)
        self.WeightCombo.SelectedIndex = w - 1
        self._status('Nearest available Revit weight: %d (approx. %s mm).' % (w, utils.fmt_mm(lwm.mm_for(w))))

    @safe
    def rgb_changed(self, sender, args):
        if not self._ready or self._loading:
            return
        rgb = cm.parse_rgb(self.RBox.Text, self.GBox.Text, self.BBox.Text)
        if rgb is None:
            return
        self.cur['rgb'] = rgb
        self._loading = True
        self.HexBox.Text = cm.rgb_to_hex(rgb)
        self._loading = False
        self.ColourSwatch.Background = cm.to_wpf_brush(rgb)
        self.update_preview()

    @safe
    def hex_changed(self, sender, args):
        if not self._ready or self._loading:
            return
        rgb = cm.hex_to_rgb(self.HexBox.Text)
        if rgb is None:
            return
        self.cur['rgb'] = rgb
        self._loading = True
        self.RBox.Text, self.GBox.Text, self.BBox.Text = str(rgb[0]), str(rgb[1]), str(rgb[2])
        self._loading = False
        self.ColourSwatch.Background = cm.to_wpf_brush(rgb)
        self.update_preview()

    @safe
    def pick_colour(self, sender, args):
        dlg = ColourPickerDialog(os.path.join(UI_DIR, 'colour_picker.xaml'), self.cur['rgb'], self)
        dlg.ShowDialog()
        if dlg.result is not None:
            self.cur['rgb'] = dlg.result
            self._set_rgb_controls(dlg.result)
            self.update_preview()

    @safe
    def reset_colour(self, sender, args):
        if self.orig:
            self.cur['rgb'] = self.orig['rgb']
            self._loading = True
            self._set_rgb_controls(self.orig['rgb'])
            self._loading = False
            self.update_preview()

    @safe
    def reset_pattern(self, sender, args):
        if self.orig:
            pat = self.pat_idx.get(self.orig['pattern_idv']) or self.patterns[0]
            self.cur['pattern'] = pat
            self._fill_pattern_combo('', pat)
            self.update_preview()

    @safe
    def reset_all(self, sender, args):
        if self.orig:
            pat = self.pat_idx.get(self.orig['pattern_idv']) or self.patterns[0]
            self._set_cur(self.orig['weight'], self.orig['rgb'], pat)

    @safe
    def name_changed(self, sender, args):
        if not self._ready or self._loading:
            return
        self._validate_name_live()
        self.update_preview()

    def _validate_name_live(self):
        m = self.S.mode
        if m in ('duplicate', 'new'):
            ok, msg = lsm.validate_name(self.doc, self.NameBox.Text.strip())
            self.NameStatus.Text = 'Name is available.' if ok else msg
            self.NameStatus.Foreground = Brushes.DarkGreen if ok else Brushes.Firebrick
        elif m == 'edit':
            self.NameStatus.Text = 'WARNING: editing a shared style changes every element that uses it. Use Rename in tab 3 to rename.'
            self.NameStatus.Foreground = Brushes.DarkOrange
        else:
            self.NameStatus.Text = 'Existing style - read only. Choose B or C to create your own style.'
            self.NameStatus.Foreground = Brushes.Gray

    # ----------------------------------------------------------------- modes
    def _mode_from_radios(self):
        for m, rb in MODES.items():
            if getattr(self, rb).IsChecked:
                return m
        return 'new'

    def _set_mode(self, mode):
        self.S.mode = mode
        self._loading = True
        getattr(self, MODES[mode]).IsChecked = True
        self._loading = False
        self._enter_mode()

    @safe
    def mode_changed(self, sender, args):
        if not self._ready or self._loading:
            return
        self.S.mode = self._mode_from_radios()
        self._enter_mode()

    def _enter_mode(self, keep_values=False):
        m = self.S.mode
        if m == 'new':
            self.StyleHint.Text = 'A brand-new Revit Line Style will be created from the values below.'
            if not keep_values:
                self.orig = None
                self._set_cur(3, (0, 0, 0), self.patterns[0])
                self._loading = True
                self.NameBox.Text = ''
                self._loading = False
        else:
            if self._current_source() is None and self._style_view:
                self.S.source = self._style_view[0]['name']
                self._fill_style_combo(self.StyleSearch.Text, self.S.source)
            if not keep_values:
                self._load_source_into_form()
            else:
                src = self._current_source()
                if src:
                    self.orig = {'weight': src['weight'], 'rgb': src['rgb'], 'pattern_idv': src['pattern_idv']}
        self._apply_mode_ui()
        self._validate_name_live()
        self.update_preview()

    def _apply_mode_ui(self):
        m = self.S.mode
        editable = m in ('duplicate', 'new', 'edit')
        self.NameBox.IsEnabled = m in ('duplicate', 'new')
        self.StyleCombo.IsEnabled = m != 'new'
        self.StyleSearch.IsEnabled = m != 'new'
        for c in (self.WeightCombo, self.MmBox, self.RBox, self.GBox, self.BBox, self.HexBox,
                  self.PatternCombo, self.PatternSearch):
            c.IsEnabled = editable
        self.BtnSave.IsEnabled = m != 'existing'
        self.BtnSaveApply.IsEnabled = editable
        self.BtnApplyExisting.IsEnabled = m == 'existing'

    def _load_source_into_form(self):
        src = self._current_source()
        if src is None:
            return
        m = self.S.mode
        self.orig = {'weight': src['weight'], 'rgb': src['rgb'], 'pattern_idv': src['pattern_idv']}
        pat = self.pat_idx.get(src['pattern_idv']) or self.patterns[0]
        self._set_cur(src['weight'] or 1, src['rgb'], pat)
        self._loading = True
        if m == 'duplicate':
            self.NameBox.Text = lsm.unique_name(self.doc, src['name'])
        else:
            self.NameBox.Text = src['name']
        self._loading = False
        hint = 'Built-in Revit style.' if src['builtin'] else 'Custom style stored in this project.'
        hint += ' Graphics Style ID %s.' % src['gs_idv']
        if m == 'edit' and src['builtin']:
            hint = 'Built-in Revit styles cannot be edited here. Choose a custom style.'
        self.StyleHint.Text = hint
        self._validate_name_live()
        self.update_preview()

    # --------------------------------------------------------------- preview
    def _selection_styles(self):
        counts = {}
        for ridv, summ in self.seg_cache.items():
            for sg in summ['segments']:
                st = sg['style']
                e = counts.setdefault(st['gs_idv'], [st, 0])
                e[1] += 1
        return [v[0] for v in sorted(counts.values(), key=lambda x: -x[1])]

    def _form_preview(self):
        pat = self.cur['pattern'] or self.patterns[0]
        w = self.cur['weight']
        return {'name': self.NameBox.Text.strip() or '(unnamed)', 'weight': w, 'mm': lwm.mm_for(w),
                'rgb': self.cur['rgb'], 'pattern_name': pat['name'], 'segments': pat['segments']}

    def update_preview(self):
        if not self._ready:
            return
        m = self.S.mode
        sel = self._selection_styles()
        src = self._current_source()
        if m == 'existing':
            before = sel[0] if sel else None
            after = src
        elif m in ('duplicate', 'edit'):
            before = src
            after = self._form_preview()
        else:
            before = sel[0] if sel else None
            after = self._form_preview()
        self.preview.update(before, after)

    # ------------------------------------------------------------- selection
    def _status_sel(self):
        self.TotalText.Text = 'Selected Filled Regions: %d' % len(self.S.regions)

    def _go_pick(self, action):
        self._save_state()
        self.S.pending = action
        self.Close()

    @safe
    def pick_replace(self, sender, args):
        self._go_pick('pick_replace')

    @safe
    def pick_add(self, sender, args):
        self._go_pick('pick_add')

    @safe
    def use_revit_selection(self, sender, args):
        ids = selection.from_revit_selection(self.uidoc)
        if not ids:
            self._status('No Filled Regions are selected in Revit.', True)
            return
        self._merge(ids)
        self._status('%d Filled Region(s) taken from the Revit selection.' % len(ids))

    @safe
    def select_all_view(self, sender, args):
        regs = frm.regions_in_view(self.doc, self.doc.ActiveView)
        if not regs:
            self._status('The active view contains no Filled Regions.', True)
            return
        self.S.regions = [rc.eid_value(r.Id) for r in regs]
        self.refresh_regions()
        self._status('%d Filled Region(s) selected from the active view.' % len(regs))

    @safe
    def select_by_type(self, sender, args):
        t = self.TypeCombo.SelectedItem
        if not t:
            self._status('Choose a Filled Region Type first.', True)
            return
        base = frm.regions_in_project(self.doc) if self.ChkSelTypeProject.IsChecked \
            else frm.regions_in_view(self.doc, self.doc.ActiveView)
        regs = frm.filter_by_type(self.doc, base, t)
        if not regs:
            self._status('No Filled Regions of type "%s" found in that scope.' % t, True)
            return
        self._merge([rc.eid_value(r.Id) for r in regs])
        self._status('%d Filled Region(s) of type "%s" added.' % (len(regs), t))

    def _merge(self, ids):
        cur = list(self.S.regions)
        for i in ids:
            if i not in cur:
                cur.append(i)
        self.S.regions = cur
        self.refresh_regions()

    def _selected_region_idvs(self):
        return [int(i['Id']) for i in self.RegionsGrid.SelectedItems]

    @safe
    def remove_selected(self, sender, args):
        rem = set(self._selected_region_idvs())
        if not rem:
            self._status('Highlight rows in the Filled Regions table to remove them.', True)
            return
        self.S.regions = [i for i in self.S.regions if i not in rem]
        self.refresh_regions()

    @safe
    def clear_selection(self, sender, args):
        self.S.regions = []
        self.refresh_regions()

    @safe
    def regions_selection_changed(self, sender, args):
        if not self._ready:
            return
        self.refresh_segments()

    def refresh_regions(self):
        live, rows, seg_rows = [], [], []
        self.seg_cache = {}
        for idv in self.S.regions:
            r = frm.get_region(self.doc, idv)
            if r is None:
                continue
            live.append(idv)
            summ = frm.summarize(self.doc, r, self.pat_idx, self.info_cache)
            self.seg_cache[idv] = summ
            rows.append(row(Id=str(idv), Type=summ['type'], Segs=str(len(summ['segments'])),
                            Styles=', '.join(summ['style_names']) or '(no boundary found)'))
            for sg in summ['segments']:
                st = sg['style']
                seg_rows.append(row(Sel=False, Region=str(idv), Seg=str(sg['seg_idv']), Geom=sg['geom'],
                                    Len=utils.fmt_mm(sg['len_mm']), Style=st['name'],
                                    Weight=str(st['weight']), Hex=st['hex'], Pattern=st['pattern_name'],
                                    GsId=str(st['gs_idv'])))
        self.S.regions = live
        self._seg_rows_all = seg_rows
        self.RegionsGrid.ItemsSource = to_list(rows)
        self._status_sel()
        self.refresh_segments()
        self._refresh_existing_info()
        self.update_preview()

    def refresh_segments(self):
        sel = set(self._selected_region_idvs())
        rows = [r for r in self._seg_rows_all if (not sel or int(r['Region']) in sel)]
        self.SegmentsGrid.ItemsSource = to_list(rows[:3000])

    def _refresh_existing_info(self):
        counts = {}
        for summ in self.seg_cache.values():
            for sg in summ['segments']:
                st = sg['style']
                e = counts.setdefault(st['gs_idv'], [st, 0])
                e[1] += 1
        if not counts:
            self.ExistingInfo.Text = 'No Filled Regions selected.'
            return
        lines = []
        for st, n in sorted(counts.values(), key=lambda x: -x[1]):
            lines.append('%s | weight %s (approx. %s mm) | %s | %s | GraphicsStyle ID %s | %d segment(s)' % (
                st['name'], st['weight'], utils.fmt_mm(st['mm']), st['hex'], st['pattern_name'], st['gs_idv'], n))
        self.ExistingInfo.Text = '\n'.join(lines)

    @safe
    def seg_check_all(self, sender, args):
        for r in self.SegmentsGrid.ItemsSource:
            r['Sel'] = True
        self.refresh_segments()

    @safe
    def seg_uncheck_all(self, sender, args):
        for r in self._seg_rows_all:
            r['Sel'] = False
        self.refresh_segments()

    @safe
    def show_in_revit(self, sender, args):
        ids = self._selected_region_idvs()
        if not ids:
            self._status('Highlight a Filled Region in the table first.', True)
            return
        eids = List[ElementId]()
        eids.Add(rc.make_eid(ids[0]))
        self.uidoc.Selection.SetElementIds(eids)
        self.uidoc.ShowElements(eids)
        self._status('Region %d selected in Revit (visible after you close this window).' % ids[0])

    @safe
    def tab_changed(self, sender, args):
        try:
            if args.OriginalSource.GetType().Name != 'TabControl':
                return
        except Exception:
            return
        if not self._ready:
            return
        i = self.MainTabs.SelectedIndex
        if i == 1:
            self.update_preview()
        elif i == 2:
            self.ms_refresh()
        elif i == 3:
            self._refresh_presets()

    # ------------------------------------------------------------ apply flow
    def _apply_scope(self):
        if self.RbApplySegments.IsChecked:
            return 'segments'
        if self.RbApplyView.IsChecked:
            return 'view'
        if self.RbApplyType.IsChecked:
            return 'type'
        return 'selected'

    def _resolve_targets(self):
        scope = self._apply_scope()
        doc = self.doc
        targets = []
        if scope == 'selected':
            targets = [(i, None) for i in self.S.regions if frm.get_region(doc, i) is not None]
        elif scope == 'segments':
            d = {}
            for r in self._seg_rows_all:
                if r['Sel']:
                    d.setdefault(int(r['Region']), []).append(int(r['Seg']))
            targets = list(d.items())
        elif scope == 'view':
            targets = [(rc.eid_value(r.Id), None) for r in frm.regions_in_view(doc, doc.ActiveView)]
        elif scope == 'type':
            t = self.ApplyTypeCombo.SelectedItem
            if not t:
                self._info('Choose a Filled Region Type first.', True)
                return None
            base = frm.regions_in_project(doc) if self.ChkTypeProject.IsChecked \
                else frm.regions_in_view(doc, doc.ActiveView)
            targets = [(rc.eid_value(r.Id), None) for r in frm.filter_by_type(doc, base, t)]
        if not targets:
            self._info('Nothing to apply to. No Filled Regions / boundary segments match the chosen scope.', True)
            return None
        return targets

    def _describe_targets(self, targets):
        nb, orig, cache = 0, {}, {}
        for ridv, segids in targets:
            r = frm.get_region(self.doc, ridv)
            if r is None:
                continue
            segs = bm.get_segments(self.doc, r)
            if segids is not None:
                wanted = set(segids)
                segs = [s for s in segs if rc.eid_value(s.Id) in wanted]
            nb += len(segs)
            for s in segs:
                n = bm.segment_style_info(self.doc, s, self.pat_idx, cache)['name']
                orig[n] = orig.get(n, 0) + 1
        return len(targets), nb, orig

    def _summary_text(self, targets, new_name, weight, rgb, pattern_name):
        nr, nb, orig = self._describe_targets(targets)
        if nb == 0:
            return None
        o = ', '.join('%s (%d)' % (k, v) for k, v in sorted(orig.items())) or '-'
        return ('Total Filled Regions: %d\nTotal Boundaries: %d\nOriginal Style: %s\nNew Style: %s\n'
                'Weight: %s (approx. %s mm)\nColour: %s\nPattern: %s\n\nOnly the boundary Line Style changes; '
                'geometry and region properties are preserved. Undo (Ctrl+Z) reverts it in one step.'
                % (nr, nb, o, new_name, weight, utils.fmt_mm(lwm.mm_for(weight)), cm.describe(rgb), pattern_name))

    def _finish(self, title, res, style_info, n_selected):
        report = rpt.build_report(self.doc, title, res, style_info, n_selected)
        self._load_data()
        self._fill_style_combo(self.StyleSearch.Text, self.S.source)
        self.refresh_regions()
        self.ms_refresh()
        self._fill_replace_combos()
        self._status('%s: %d updated, %d failed, %d skipped.' % (title, res['updated'], res['failed'], res['skipped']),
                     res['failed'] > 0)
        rpt.show_report(report, self)

    @safe
    def apply_existing(self, sender, args):
        src = self._current_source()
        if src is None or src.get('gs_id') is None:
            self._info('Select an existing Line Style first.', True)
            return
        targets = self._resolve_targets()
        if targets is None:
            return
        pat = src['pattern_name']
        txt = self._summary_text(targets, src['name'], src['weight'], src['rgb'], pat)
        if txt is None:
            self._info('The chosen scope contains no boundary segments.', True)
            return
        if not self._confirm(txt):
            return
        res = tm.apply_style(self.doc, targets, src)
        self._finish('Apply existing Line Style', res, src, len(targets))

    @safe
    def save_style(self, sender, args):
        m = self.S.mode
        if m == 'existing':
            self._info('Mode A uses an existing style. Choose B (duplicate) or C (new) to save a Line Style, '
                       'or use "APPLY STYLE".')
            return
        f = self._collect_form()
        if m == 'edit':
            src = self._current_source()
            if src is None or src['builtin']:
                self._info('Select a custom (non built-in) Line Style to edit.', True)
                return
            if not self._confirm('"%s" is a SHARED style. Changing it affects every element that uses it '
                                 '(Filled Region boundaries, detail lines, ...).\n\nSave the changes?' % src['name'],
                                 'Save changes'):
                return
            lsm.update_line_style(self.doc, src['name'], f['weight'], f['rgb'], f['pattern']['id'])
            self._status('Line Style "%s" updated.' % src['name'])
            name = src['name']
        else:
            ok, msg = lsm.validate_name(self.doc, f['name'])
            if not ok:
                self._info(msg, True)
                return
            origin = self.S.source if m == 'duplicate' else None
            info = lsm.create_line_style(self.doc, f['name'], f['weight'], f['rgb'], f['pattern']['id'], origin)
            name = info['name']
            self._status('Line Style "%s" saved in the project. No Filled Region was modified.' % name)
            self._info('Line Style "%s" was created in this project.\n\nIt is now available in Revit '
                       '(Manage > Object Styles > Lines) and was NOT applied to any element.' % name)
        self._load_data()
        self.S.source = name
        self._fill_style_combo(self.StyleSearch.Text, name)
        self.ms_refresh()
        self._fill_replace_combos()
        if m != 'edit':
            self._set_mode('existing')
        self.refresh_regions()

    @safe
    def save_and_apply(self, sender, args):
        m = self.S.mode
        if m == 'existing':
            self.apply_existing(sender, args)
            return
        f = self._collect_form()
        if m == 'edit':
            src = self._current_source()
            if src is None or src['builtin']:
                self._info('Select a custom (non built-in) Line Style to edit.', True)
                return
            targets = self._resolve_targets()
            if targets is None:
                return
            txt = self._summary_text(targets, src['name'], f['weight'], f['rgb'], f['pattern']['name'])
            if txt is None:
                self._info('The chosen scope contains no boundary segments.', True)
                return
            if not self._confirm('SHARED STYLE - this also changes every other element using "%s".\n\n%s'
                                 % (src['name'], txt), 'Save & Apply'):
                return
            lsm.update_line_style(self.doc, src['name'], f['weight'], f['rgb'], f['pattern']['id'])
            self._load_data()
            info = lsm.get_by_name(self.styles, src['name'])
            res = tm.apply_style(self.doc, targets, info)
            self._finish('Edit + apply Line Style', res, info, len(targets))
            return
        ok, msg = lsm.validate_name(self.doc, f['name'])
        if not ok:
            self._info(msg, True)
            return
        targets = self._resolve_targets()
        if targets is None:
            return
        txt = self._summary_text(targets, f['name'], f['weight'], f['rgb'], f['pattern']['name'])
        if txt is None:
            self._info('The chosen scope contains no boundary segments.', True)
            return
        if not self._confirm(txt, 'Save & Apply'):
            return
        origin = self.S.source if m == 'duplicate' else None
        info, res = tm.save_and_apply(self.doc, f['name'], f['weight'], f['rgb'], f['pattern']['id'],
                                      targets, origin)
        if info is None:
            res['notes'] = ['Nothing could be applied, so the new Line Style was NOT created (all changes rolled back).']
            new = {'name': f['name'], 'weight': f['weight'], 'rgb': f['rgb'], 'pattern_name': f['pattern']['name']}
            self._finish('Save & Apply (rolled back)', res, new, len(targets))
            return
        self.S.source = info['name']
        self._finish('Save & Apply Line Style', res, info, len(targets))
        self._set_mode('existing')

    # --------------------------------------------------------- my line styles
    def _ms_selected(self):
        it = self.MyStylesGrid.SelectedItem
        if it is None:
            self._status('Select a Line Style in the table first.', True)
            return None
        return lsm.get_by_name(self.styles, it['Name'])

    @safe
    def ms_refresh(self, sender=None, args=None):
        if not self._ready:
            return
        show_all = bool(self.ChkShowBuiltIn.IsChecked)
        rows = []
        for s in self.styles:
            if s['builtin'] and not show_all:
                continue
            rows.append(row(Name=s['name'], Weight=str(s['weight']), Mm=utils.fmt_mm(s['mm']), Hex=s['hex'],
                            Pattern=s['pattern_name'], Origin=lsm.origin_of(self.doc, s['name'])))
        self.MyStylesGrid.ItemsSource = to_list(rows)

    @safe
    def ms_create_new(self, sender, args):
        self._set_mode('new')
        self.MainTabs.SelectedIndex = 1

    @safe
    def ms_duplicate(self, sender, args):
        st = self._ms_selected()
        if st is None:
            return
        self.S.source = st['name']
        self._fill_style_combo('', st['name'])
        self._set_mode('duplicate')
        self.MainTabs.SelectedIndex = 1

    @safe
    def ms_edit(self, sender, args):
        st = self._ms_selected()
        if st is None:
            return
        if st['builtin']:
            self._info('Built-in Revit styles cannot be edited here. Duplicate it instead.', True)
            return
        self.S.source = st['name']
        self._fill_style_combo('', st['name'])
        self._set_mode('edit')
        self.MainTabs.SelectedIndex = 1

    @safe
    def ms_rename(self, sender, args):
        st = self._ms_selected()
        if st is None:
            return
        if st['builtin']:
            self._info('Built-in Revit styles cannot be renamed.', True)
            return
        new = forms.ask_for_string(default=st['name'], prompt='New name for the Line Style:', title=TITLE)
        if not new or new == st['name']:
            return
        lsm.rename_line_style(self.doc, st['name'], new.strip())
        if self.S.source == st['name']:
            self.S.source = new.strip()
        self._load_data()
        self._fill_style_combo(self.StyleSearch.Text, self.S.source)
        self.ms_refresh()
        self._fill_replace_combos()
        self.refresh_regions()
        self._status('Renamed to "%s". Elements using the style keep using it.' % new.strip())

    @safe
    def ms_apply(self, sender, args):
        st = self._ms_selected()
        if st is None:
            return
        self.S.source = st['name']
        self._fill_style_combo('', st['name'])
        self._set_mode('existing')
        self.apply_existing(sender, args)

    @safe
    def ms_usage(self, sender, args):
        st = self._ms_selected()
        if st is None:
            return
        u = pa.usage_scan(self.doc, st['gs_idv'])
        self._info('"%s" is used by:\n  %d Filled Region boundary segment(s) in %d Filled Region(s)\n  %d other line element(s) (detail / model lines)'
                   % (st['name'], len(u['fr']), len(u['regions']), len(u['other'])))

    @safe
    def ms_delete(self, sender, args):
        st = self._ms_selected()
        if st is None:
            return
        if st['builtin']:
            self._info('Built-in Revit styles cannot be deleted.', True)
            return
        u = pa.usage_scan(self.doc, st['gs_idv'])
        nfr, nother, nreg = len(u['fr']), len(u['other']), len(u['regions'])
        if nfr + nother == 0:
            if not self._confirm('Delete the Line Style "%s"? It is not used by any element.' % st['name'], 'Delete'):
                return
            lsm.delete_line_style(self.doc, st['name'])
        else:
            names = [s['name'] for s in self.styles if s['name'] != st['name'] and s.get('gs_id') is not None]
            pick = forms.SelectFromList.show(
                names, title='"%s" is in use - choose a replacement style' % st['name'],
                button_name='Reassign & Delete', multiselect=False)
            if not pick:
                return
            msg = ('"%s" is used by:\n  %d boundary segment(s) in %d Filled Region(s)\n  %d other line element(s)\n\n'
                   'All of them will be reassigned to "%s", then the style is deleted (one undo step).'
                   % (st['name'], nfr, nreg, nother, pick))
            if nother:
                msg += '\n\nNOTE: %d ordinary detail/model line(s) will ALSO change.' % nother
            if not self._confirm(msg, 'Reassign & Delete'):
                return
            new = lsm.get_by_name(self.styles, pick)
            ids = [s for _, s in u['fr']] + list(u['other'])
            tm.reassign_and_delete(self.doc, st, new, ids)
        if self.S.source == st['name']:
            self.S.source = None
        self._load_data()
        self._fill_style_combo(self.StyleSearch.Text, self.S.source)
        self.ms_refresh()
        self._fill_replace_combos()
        self.refresh_regions()
        self._status('Line Style "%s" deleted.' % st['name'])

    # ---------------------------------------------------------------- presets
    def _refresh_presets(self):
        names = set(s['name'].lower() for s in self.styles)
        rows = []
        for p in pm.load_all():
            avail = []
            if lpm.find_by_name(self.patterns, p['pattern']) is None:
                avail.append('pattern missing')
            if p['name'].lower() in names:
                avail.append('style name exists')
            rows.append(row(Name=p['name'], Weight=str(p['weight']), Hex=cm.rgb_to_hex(p['rgb']),
                            Pattern=p['pattern'], Avail='; '.join(avail) or 'OK'))
        self.PresetGrid.ItemsSource = to_list(rows)
        self.PresetPath.Text = 'Preset library file: ' + pm.user_file()

    def _preset_selected(self):
        it = self.PresetGrid.SelectedItem
        if it is None:
            self._status('Select a preset first.', True)
            return None
        return pm.find(pm.load_all(), it['Name'])

    @safe
    def pr_save(self, sender, args):
        f = self._collect_form()
        name = forms.ask_for_string(default=f['name'] or 'New Preset', prompt='Preset name:', title=TITLE)
        if not name:
            return
        p = {'name': name.strip(), 'weight': f['weight'], 'rgb': list(f['rgb']),
             'pattern': f['pattern']['name'], 'notes': ''}
        ok, msg = pm.save(p, overwrite=False)
        if not ok and 'already exists' in msg:
            if self._confirm('A preset named "%s" already exists. Overwrite it?' % p['name'], 'Overwrite'):
                ok, msg = pm.save(p, overwrite=True)
        if not ok:
            self._info(msg, True)
            return
        self._refresh_presets()
        self._status('Preset "%s" saved to the preset library (external file, not a Revit style).' % p['name'])

    @safe
    def save_preset_from_builder(self, sender, args):
        self.pr_save(sender, args)

    @safe
    def pr_load(self, sender, args):
        p = self._preset_selected()
        if p is None:
            return
        pat, warns = pm.check_against_project(p, self.patterns, set(s['name'].lower() for s in self.styles))
        self._set_mode('new')
        self._set_cur(p['weight'], p['rgb'], pat or self.patterns[0])
        nm = p['name']
        if lsm.validate_name(self.doc, nm)[0] is False:
            nm = lsm.unique_name(self.doc, p['name'], ' - Copy')
        self._loading = True
        self.NameBox.Text = nm
        self._loading = False
        self._validate_name_live()
        self.update_preview()
        self.MainTabs.SelectedIndex = 1
        if warns:
            self._info('Preset loaded with warnings:\n\n' + '\n'.join(warns), True)

    @safe
    def pr_create_style(self, sender, args):
        p = self._preset_selected()
        if p is None:
            return
        pat, warns = pm.check_against_project(p, self.patterns, set(s['name'].lower() for s in self.styles))
        name = p['name']
        while not lsm.validate_name(self.doc, name)[0]:
            msg = lsm.validate_name(self.doc, name)[1]
            name = forms.ask_for_string(default=lsm.unique_name(self.doc, p['name'], ' - Copy'),
                                        prompt=msg + '\nEnter a different Line Style name:', title=TITLE)
            if not name:
                return
            name = name.strip()
        notes = [w for w in warns if 'Pattern' in w]
        if notes and not self._confirm('\n'.join(notes), 'Continue'):
            return
        info = lsm.create_line_style(self.doc, name, p['weight'], tuple(p['rgb']), (pat or self.patterns[0])['id'])
        self._load_data()
        self._fill_style_combo(self.StyleSearch.Text, self.S.source)
        self.ms_refresh()
        self._fill_replace_combos()
        self._refresh_presets()
        self._status('Revit Line Style "%s" created from the preset. It has not been applied.' % info['name'])

    @safe
    def pr_rename(self, sender, args):
        p = self._preset_selected()
        if p is None:
            return
        new = forms.ask_for_string(default=p['name'], prompt='New preset name:', title=TITLE)
        if not new:
            return
        ok, msg = pm.rename(p['name'], new.strip())
        if not ok:
            self._info(msg, True)
        self._refresh_presets()

    @safe
    def pr_duplicate(self, sender, args):
        p = self._preset_selected()
        if p is None:
            return
        pm.duplicate(p['name'])
        self._refresh_presets()

    @safe
    def pr_delete(self, sender, args):
        p = self._preset_selected()
        if p is None:
            return
        if self._confirm('Delete preset "%s"? (Revit Line Styles are not affected.)' % p['name'], 'Delete'):
            pm.delete(p['name'])
            self._refresh_presets()

    @safe
    def pr_import(self, sender, args):
        dlg = OpenFileDialog()
        dlg.Filter = 'Preset files (*.json)|*.json'
        if not dlg.ShowDialog():
            return
        n, warns = pm.import_file(dlg.FileName)
        self._refresh_presets()
        self._info('%d preset(s) imported.%s' % (n, ('\n\n' + '\n'.join(warns)) if warns else ''), bool(warns))

    @safe
    def pr_export(self, sender, args):
        dlg = SaveFileDialog()
        dlg.Filter = 'Preset files (*.json)|*.json'
        dlg.FileName = 'BoundaryPresets.json'
        if not dlg.ShowDialog():
            return
        it = self.PresetGrid.SelectedItem
        n = pm.export_file(dlg.FileName, [it['Name']] if it is not None else None)
        self._status('%d preset(s) exported to %s' % (n, dlg.FileName))

    # ------------------------------------------------------------ batch replace
    def _fill_replace_combos(self):
        names = [s['name'] for s in self.styles]
        for combo in (self.ReplaceFromCombo, self.ReplaceToCombo):
            keep = combo.SelectedItem
            self._fill_combo(combo, names)
            if keep in names:
                combo.SelectedItem = keep

    def _replace_args(self):
        a, b = self.ReplaceFromCombo.SelectedItem, self.ReplaceToCombo.SelectedItem
        if not a or not b:
            self._info('Choose both the style to find and the style to replace it with.', True)
            return None
        if a == b:
            self._info('The two styles are the same.', True)
            return None
        s_from, s_to = lsm.get_by_name(self.styles, a), lsm.get_by_name(self.styles, b)
        if s_from is None or s_to is None or s_to.get('gs_id') is None:
            self._info('One of the styles is no longer available. Refresh and try again.', True)
            return None
        scope = br.SCOPE_VIEW if self.RbScopeView.IsChecked else (
            br.SCOPE_PROJECT if self.RbScopeProj.IsChecked else br.SCOPE_SELECTION)
        return s_from, s_to, scope

    @safe
    def br_scan(self, sender, args):
        a = self._replace_args()
        if a is None:
            return
        s_from, s_to, scope = a
        targets, nscan, naff, nb = br.find_targets(self.doc, s_from['gs_idv'], scope, self.S.regions, self.doc.ActiveView)
        self.ReplaceInfo.Text = ('Filled Regions scanned : %d\nFilled Regions affected: %d\nBoundaries affected    : %d'
                                 % (nscan, naff, nb))

    @safe
    def br_replace(self, sender, args):
        a = self._replace_args()
        if a is None:
            return
        s_from, s_to, scope = a
        targets, nscan, naff, nb = br.find_targets(self.doc, s_from['gs_idv'], scope, self.S.regions, self.doc.ActiveView)
        if not targets:
            self._info('No Filled Region boundary uses "%s" in that scope.' % s_from['name'])
            return
        msg = ('Total Filled Regions: %d\nTotal Boundaries: %d\nOriginal Style: %s\nNew Style: %s\n'
               'Weight: %s (approx. %s mm)\nColour: %s\nPattern: %s\n\nOrdinary Detail/Model Lines are not modified.'
               % (naff, nb, s_from['name'], s_to['name'], s_to['weight'], utils.fmt_mm(s_to['mm']),
                  cm.describe(s_to['rgb']), s_to['pattern_name']))
        if not self._confirm(msg, 'Replace'):
            return
        res = tm.apply_style(self.doc, targets, s_to, 'Batch replace boundary Line Style')
        self.ReplaceInfo.Text = ''
        self._finish('Batch Line Style replacement', res, s_to, naff)

    # ------------------------------------------------------------------- audit
    @safe
    def audit_run(self, sender, args):
        if self.RbAuditProj.IsChecked:
            scope = br.SCOPE_PROJECT
        elif self.RbAuditSel.IsChecked:
            scope = br.SCOPE_SELECTION
        else:
            scope = br.SCOPE_VIEW
        unwanted = [x for x in self.AuditUnwanted.Text.split(',')]
        self._audit_rows = pa.run_audit(self.doc, scope, self.doc.ActiveView, self.S.regions, self.pat_idx, unwanted)
        self._show_audit()

    def _filtered_audit(self):
        f = (self.AuditFilter.Text or '').strip().lower()
        out = []
        for r in self._audit_rows:
            blob = ' '.join([r['style'], r['type'], str(r['region']), r['flag']]).lower()
            if not f or f in blob:
                out.append(r)
        return out

    def _show_audit(self):
        rows = self._filtered_audit()
        self.AuditGrid.ItemsSource = to_list([
            row(Region=str(r['region']), Type=r['type'], Style=r['style'], Weight=str(r['weight']),
                Mm=utils.fmt_mm(r['mm']) if r['mm'] != '' else '', Hex=r['hex'], Pattern=r['pattern'],
                Segments=str(r['segments']), Flag=r['flag']) for r in rows])
        flagged = len(set(r['region'] for r in rows if r['flag']))
        self.AuditSummary.Text = '%d row(s), %d region(s) flagged' % (len(rows), flagged)

    @safe
    def audit_filter_changed(self, sender, args):
        if self._ready:
            self._show_audit()

    @safe
    def audit_export(self, sender, args):
        rows = self._filtered_audit()
        if not rows:
            self._status('Run the audit first.', True)
            return
        p = rpt.save_dialog('Export audit', 'CSV (*.csv)|*.csv', 'FilledRegionAudit.csv')
        if not p:
            return
        hdr = ['Region ID', 'Filled Region Type', 'Boundary Line Style', 'Weight', 'Approx mm', 'Colour', 'Pattern',
               'Segments', 'Flag']
        data = [[r['region'], r['type'], r['style'], r['weight'], r['mm'], r['hex'], r['pattern'], r['segments'],
                 r['flag']] for r in rows]
        utils.write_text(p, utils.rows_to_csv(hdr, data), bom=True)
        self._status('Audit exported to %s' % p)

    @safe
    def audit_select_flagged(self, sender, args):
        ids = sorted(set(r['region'] for r in self._filtered_audit() if r['flag']))
        if not ids:
            self._status('No flagged regions in the current audit.', True)
            return
        eids = List[ElementId]()
        for i in ids:
            eids.Add(rc.make_eid(i))
        self.uidoc.Selection.SetElementIds(eids)
        self._merge(ids)
        self._status('%d flagged region(s) selected in Revit and added to the tool selection.' % len(ids))


def run(uidoc):
    xaml = os.path.join(UI_DIR, 'main_window.xaml')
    for _ in range(500):
        win = MainWindow(xaml, uidoc, STATE)
        win.ShowDialog()
        action, STATE.pending = STATE.pending, None
        if action in ('pick_replace', 'pick_add'):
            ids = selection.pick_regions(uidoc)
            if ids:
                if action == 'pick_replace':
                    STATE.regions = ids
                else:
                    STATE.regions = list(STATE.regions) + [i for i in ids if i not in STATE.regions]
            STATE.tab = 0
            continue
        break
