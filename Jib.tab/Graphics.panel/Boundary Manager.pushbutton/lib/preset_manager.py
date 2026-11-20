# -*- coding: utf-8 -*-
"""External preset library (JSON in the pyRevit config folder).
Presets hold graphics values only - never ElementIds - and are NOT Revit styles."""
import os
from lib import utils, line_weight_manager as lwm

_HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_FILE = os.path.join(os.path.dirname(_HERE), 'presets', 'default_presets.json')


def user_file():
    return os.path.join(utils.config_dir(), 'presets.json')


def normalize(p):
    rgb = p.get('rgb') or [0, 0, 0]
    rgb = [max(0, min(255, int(v))) for v in (list(rgb) + [0, 0, 0])[:3]]
    return {'name': utils.to_text(p.get('name', '')).strip(),
            'weight': lwm.clamp(p.get('weight', 1)),
            'rgb': rgb, 'pattern': utils.to_text(p.get('pattern', 'Solid') or 'Solid'),
            'notes': utils.to_text(p.get('notes', ''))}


def load_all():
    data = utils.read_json(user_file(), None)
    if data is None:
        data = utils.read_json(DEFAULT_FILE, {'presets': []}) or {'presets': []}
        try:
            utils.write_json(user_file(), data)
        except Exception:
            pass
    out = []
    for p in data.get('presets', []):
        try:
            n = normalize(p)
            if n['name']:
                out.append(n)
        except Exception:
            continue
    return out


def save_all(presets):
    utils.write_json(user_file(), {'version': 1, 'presets': presets})


def find(presets, name):
    for p in presets:
        if p['name'].lower() == (name or '').lower():
            return p
    return None


def save(preset, overwrite=False):
    """Returns (ok, message). Never silently overwrites."""
    ok, msg = utils.validate_name_syntax(preset['name'])
    if not ok:
        return False, msg
    presets = load_all()
    ex = find(presets, preset['name'])
    if ex is not None and not overwrite:
        return False, 'A preset named "%s" already exists.' % preset['name']
    presets = [p for p in presets if p is not ex]
    presets.append(normalize(preset))
    presets.sort(key=lambda p: p['name'].lower())
    save_all(presets)
    return True, ''


def rename(old, new):
    ok, msg = utils.validate_name_syntax(new)
    if not ok:
        return False, msg
    presets = load_all()
    if find(presets, new) is not None and old.lower() != new.lower():
        return False, 'A preset named "%s" already exists.' % new
    p = find(presets, old)
    if p is None:
        return False, 'Preset not found.'
    p['name'] = new
    save_all(presets)
    return True, ''


def unique_preset_name(presets, base):
    n, cand = 2, base + ' - Copy'
    while find(presets, cand) is not None:
        cand = '%s - Copy %d' % (base, n)
        n += 1
    return cand


def duplicate(name):
    presets = load_all()
    p = find(presets, name)
    if p is None:
        return None
    c = dict(p)
    c['name'] = unique_preset_name(presets, name)
    presets.append(c)
    save_all(presets)
    return c['name']


def delete(name):
    presets = load_all()
    p = find(presets, name)
    if p is None:
        return False
    presets.remove(p)
    save_all(presets)
    return True


def export_file(path, names=None):
    presets = load_all()
    if names:
        presets = [p for p in presets if p['name'] in names]
    utils.write_json(path, {'version': 1, 'presets': presets})
    return len(presets)


def import_file(path):
    """Returns (added_count, warnings). Name clashes are renamed, never overwritten."""
    data = utils.read_json(path, None)
    if not data or 'presets' not in data:
        return 0, ['The file is not a valid preset file.']
    presets = load_all()
    warnings, added = [], 0
    for raw in data['presets']:
        try:
            p = normalize(raw)
        except Exception:
            warnings.append('Skipped an invalid entry.')
            continue
        if not p['name']:
            continue
        if find(presets, p['name']) is not None:
            new = unique_preset_name(presets, p['name'])
            warnings.append('"%s" already exists - imported as "%s".' % (p['name'], new))
            p['name'] = new
        presets.append(p)
        added += 1
    presets.sort(key=lambda p: p['name'].lower())
    save_all(presets)
    return added, warnings


def check_against_project(preset, patterns, style_names_lower):
    """Warnings when a preset is used in the current project."""
    from lib import line_pattern_manager as lpm
    warns = []
    pat = lpm.find_by_name(patterns, preset['pattern'])
    if pat is None:
        warns.append('Line Pattern "%s" does not exist in this project - Solid will be used.' % preset['pattern'])
    if preset['name'].lower() in style_names_lower:
        warns.append('A Line Style named "%s" already exists in this project - choose another name.' % preset['name'])
    return pat, warns
