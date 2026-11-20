# -*- coding: utf-8 -*-
"""Execution report: build, display, copy, export TXT / CSV."""
import clr
clr.AddReference('PresentationFramework')
clr.AddReference('PresentationCore')
import datetime
from System.Windows import Clipboard
from System.Windows.Markup import XamlReader
from Microsoft.Win32 import SaveFileDialog
from lib import utils, colour_manager as cm, line_weight_manager as lwm

_XAML = u'''<Window xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
 xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml"
 Title="Execution Report" Width="640" Height="560" WindowStartupLocation="CenterOwner"
 FontFamily="Segoe UI" FontSize="12">
 <DockPanel Margin="10">
  <StackPanel DockPanel.Dock="Bottom" Orientation="Horizontal" HorizontalAlignment="Right" Margin="0,8,0,0">
   <Button x:Name="BtnCopy" Content="Copy" Padding="14,4" Margin="3"/>
   <Button x:Name="BtnTxt" Content="Export TXT" Padding="14,4" Margin="3"/>
   <Button x:Name="BtnCsv" Content="Export CSV" Padding="14,4" Margin="3"/>
   <Button x:Name="BtnClose" Content="Close" Padding="14,4" Margin="3" IsDefault="True"/>
  </StackPanel>
  <TextBox x:Name="ReportText" IsReadOnly="True" FontFamily="Consolas" FontSize="12"
   VerticalScrollBarVisibility="Auto" HorizontalScrollBarVisibility="Auto" TextWrapping="NoWrap"/>
 </DockPanel></Window>'''


def _desc(i):
    w = i.get('weight')
    return {'name': i['name'], 'weight': w if w is not None else '?',
            'mm': utils.fmt_mm(lwm.mm_for(w)) if w else '?',
            'colour': cm.rgb_to_hex(i['rgb']), 'pattern': i['pattern_name']}


def build_report(doc, title, res, new_info, n_regions_selected):
    originals = []
    for ent in res.get('originals', {}).values():
        d = _desc(ent['info'])
        d['count'] = ent['count']
        originals.append(d)
    return {
        'title': title,
        'timestamp': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'document': doc.Title,
        'regions_selected': n_regions_selected,
        'regions_processed': res.get('regions', 0),
        'boundaries_processed': res.get('segments', 0),
        'updated': res.get('updated', 0), 'failed': res.get('failed', 0),
        'skipped': res.get('skipped', 0),
        'original': originals, 'new': _desc(new_info) if new_info else None,
        'failures': res.get('failures', []),
        'notes': res.get('notes', []),
    }


def to_text(r):
    L = []
    L.append('FILLED REGION BOUNDARY MANAGER - EXECUTION REPORT')
    L.append('=' * 52)
    L.append('Operation : %s' % r['title'])
    L.append('Time      : %s' % r['timestamp'])
    L.append('Document  : %s' % r['document'])
    L.append('')
    L.append('Total Filled Regions selected : %s' % r['regions_selected'])
    L.append('Filled Regions processed      : %s' % r['regions_processed'])
    L.append('Total boundaries processed    : %s' % r['boundaries_processed'])
    L.append('Successfully updated          : %s' % r['updated'])
    L.append('Failed                        : %s' % r['failed'])
    L.append('Skipped (already that style)  : %s' % r['skipped'])
    L.append('')
    L.append('ORIGINAL STYLE(S)')
    for o in r['original']:
        L.append('  %s | weight %s (approx. %s mm) | %s | %s | %s boundaries' % (
            o['name'], o['weight'], o['mm'], o['colour'], o['pattern'], o['count']))
    if not r['original']:
        L.append('  -')
    L.append('NEW STYLE')
    n = r['new']
    if n:
        L.append('  %s | weight %s (approx. %s mm) | %s | %s' % (
            n['name'], n['weight'], n['mm'], n['colour'], n['pattern']))
    if r['failures']:
        L.append('')
        L.append('FAILURES')
        for reg, seg, msg in r['failures']:
            L.append('  Region %s / segment %s : %s' % (reg, seg, msg))
    for note in r['notes']:
        L.append('')
        L.append(note)
    L.append('')
    L.append('Weights in mm are reference values (the Revit API does not expose the project line-weight table).')
    return u'\r\n'.join(utils.to_text(x) for x in L)


def to_csv(r):
    headers = ['Item', 'Name', 'Weight', 'Approx mm', 'Colour', 'Pattern', 'Count']
    rows = []
    for o in r['original']:
        rows.append(['Original', o['name'], o['weight'], o['mm'], o['colour'], o['pattern'], o['count']])
    if r['new']:
        n = r['new']
        rows.append(['New', n['name'], n['weight'], n['mm'], n['colour'], n['pattern'], r['updated']])
    rows.append(['Summary', 'Regions selected', r['regions_selected'], '', '', '', ''])
    rows.append(['Summary', 'Boundaries processed', r['boundaries_processed'], '', '', '', ''])
    rows.append(['Summary', 'Updated', r['updated'], '', '', '', ''])
    rows.append(['Summary', 'Failed', r['failed'], '', '', '', ''])
    rows.append(['Summary', 'Skipped', r['skipped'], '', '', '', ''])
    for reg, seg, msg in r['failures']:
        rows.append(['Failure', 'Region %s / segment %s' % (reg, seg), '', '', '', msg, ''])
    return utils.rows_to_csv(headers, rows)


def save_dialog(title, flt, default):
    dlg = SaveFileDialog()
    dlg.Title = title
    dlg.Filter = flt
    dlg.FileName = default
    if dlg.ShowDialog():
        return dlg.FileName
    return None


def show_report(report, owner=None):
    text = to_text(report)
    win = XamlReader.Parse(_XAML)
    if owner is not None:
        try:
            win.Owner = owner
        except Exception:
            pass
    win.FindName('ReportText').Text = text

    def do_copy(s, a):
        Clipboard.SetText(text)

    def do_txt(s, a):
        p = save_dialog('Export report', 'Text (*.txt)|*.txt', 'BoundaryReport.txt')
        if p:
            utils.write_text(p, text)

    def do_csv(s, a):
        p = save_dialog('Export report', 'CSV (*.csv)|*.csv', 'BoundaryReport.csv')
        if p:
            utils.write_text(p, to_csv(report), bom=True)

    def do_close(s, a):
        win.Close()

    win.FindName('BtnCopy').Click += do_copy
    win.FindName('BtnTxt').Click += do_txt
    win.FindName('BtnCsv').Click += do_csv
    win.FindName('BtnClose').Click += do_close
    win.ShowDialog()
