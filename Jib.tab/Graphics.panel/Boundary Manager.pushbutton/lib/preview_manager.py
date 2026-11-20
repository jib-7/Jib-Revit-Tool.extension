# -*- coding: utf-8 -*-
"""BEFORE / AFTER preview. Pure WPF drawing - never touches the Revit document."""
import clr
clr.AddReference('PresentationFramework')
clr.AddReference('PresentationCore')
from System.IO import FileStream, FileMode, FileAccess
from System.Windows.Markup import XamlReader
from System.Windows.Media import DoubleCollection, PenLineCap
from lib import colour_manager as cm, utils

PX_PER_MM = 4.0


def dash_array(segments, thickness):
    """Convert Revit pattern segments (type, mm) to a WPF StrokeDashArray
    (units of stroke thickness). Returns None for solid."""
    if not segments:
        return None
    seq = []  # list of (is_on, length_px)
    for typ, mm in segments:
        on = typ.lower() != 'space'
        ln = max(mm * PX_PER_MM, 0.6 if on else 0.8)
        if seq and seq[-1][0] == on:
            seq[-1] = (on, seq[-1][1] + ln)
        else:
            seq.append((on, ln))
    if not seq or all(not o for o, _ in seq):
        return None
    if not seq[0][0]:
        seq.insert(0, (True, 0.01))
    if len(seq) % 2 == 1:
        seq.append((False, 2.0))
    dc = DoubleCollection()
    t = max(thickness, 0.5)
    for _, ln in seq:
        dc.Add(ln / t)
    return dc


class PreviewPanel(object):
    def __init__(self, xaml_path):
        fs = FileStream(xaml_path, FileMode.Open, FileAccess.Read)
        try:
            self.root = XamlReader.Load(fs)
        finally:
            fs.Close()

    def _side(self, prefix, d):
        name = self.root.FindName(prefix + 'Name')
        info = self.root.FindName(prefix + 'Info')
        rect = self.root.FindName(prefix + 'Rect')
        sw = self.root.FindName(prefix + 'Swatch')
        if d is None:
            name.Text = '(none)'
            info.Text = ''
            rect.Stroke = cm.to_wpf_brush((200, 200, 200))
            rect.StrokeThickness = 1
            rect.StrokeDashArray = None
            sw.Background = cm.to_wpf_brush((255, 255, 255))
            return
        mm = d.get('mm')
        thick = min(14.0, max(1.0, (mm or 0.25) * PX_PER_MM))
        name.Text = d.get('name') or ''
        info.Text = 'Weight %s (approx. %s mm)\nColour %s\nPattern %s' % (
            d.get('weight'), utils.fmt_mm(mm), cm.rgb_to_hex(d['rgb']), d.get('pattern_name'))
        rect.Stroke = cm.to_wpf_brush(d['rgb'])
        rect.StrokeThickness = thick
        rect.StrokeDashArray = dash_array(d.get('segments'), thick)
        rect.StrokeDashCap = PenLineCap.Flat
        sw.Background = cm.to_wpf_brush(d['rgb'])

    def update(self, before, after):
        self._side('Before', before)
        self._side('After', after)
