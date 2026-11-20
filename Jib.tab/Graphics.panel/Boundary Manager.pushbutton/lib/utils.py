# -*- coding: utf-8 -*-
"""Generic helpers (IronPython 2.7 / 3.x compatible, no f-strings)."""
import os
import io
import json
import tempfile
import traceback

APP_NAME = 'FilledRegionBoundaryManager'
APP_TITLE = 'Filled Region Boundary Manager'
# Characters Revit does not allow in names
INVALID_CHARS = '\\:{}[]|;<>?`~'
MM_PER_FOOT = 304.8


def to_text(s):
    try:
        unicode_t = unicode  # noqa  (IronPython 2.7)
    except NameError:
        return s if isinstance(s, str) else str(s)
    if isinstance(s, unicode_t):
        return s
    if isinstance(s, str):
        return s.decode('utf-8', 'replace')
    return unicode_t(s)


def config_dir():
    base = os.environ.get('APPDATA') or os.path.expanduser('~')
    path = os.path.join(base, 'pyRevit', APP_NAME)
    try:
        if not os.path.isdir(path):
            os.makedirs(path)
        return path
    except Exception:
        path = os.path.join(tempfile.gettempdir(), APP_NAME)
        if not os.path.isdir(path):
            os.makedirs(path)
        return path


def read_json(path, default=None):
    try:
        if os.path.isfile(path):
            with open(path, 'r') as f:
                return json.load(f)
    except Exception:
        pass
    return default


def write_json(path, data):
    with open(path, 'w') as f:
        json.dump(data, f, indent=2, sort_keys=True)


def write_text(path, text, bom=False):
    enc = 'utf-8-sig' if bom else 'utf-8'
    with io.open(path, 'w', encoding=enc, newline='') as f:
        f.write(to_text(text))


def validate_name_syntax(name):
    """Return (ok, message) for a Revit style name (syntax only)."""
    if name is None or not name.strip():
        return False, 'The name is empty.'
    if name != name.strip():
        return False, 'The name cannot start or end with a space.'
    bad = sorted(set(c for c in name if c in INVALID_CHARS))
    if bad:
        return False, 'Invalid character(s): ' + ' '.join(bad)
    if len(name) > 200:
        return False, 'The name is too long (max 200 characters).'
    return True, ''


def safe_int(s, default=None):
    try:
        return int(str(s).strip())
    except Exception:
        return default


def safe_float(s, default=None):
    try:
        return float(str(s).strip().replace(',', '.'))
    except Exception:
        return default


def csv_cell(v):
    t = to_text(v if v is not None else '')
    if any(c in t for c in u',"\r\n'):
        t = u'"' + t.replace(u'"', u'""') + u'"'
    return t


def rows_to_csv(headers, rows):
    lines = [u','.join(csv_cell(h) for h in headers)]
    for r in rows:
        lines.append(u','.join(csv_cell(c) for c in r))
    return u'\r\n'.join(lines) + u'\r\n'


def trace():
    return traceback.format_exc()


def fmt_mm(mm):
    if mm is None:
        return '?'
    return ('%.2f' % mm).rstrip('0').rstrip('.')
