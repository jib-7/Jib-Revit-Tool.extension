# -*- coding: utf-8 -*-
"""Line Styles = subcategories of the built-in Lines category (OST_Lines).

Creating a style therefore creates a genuine Revit document subcategory
(Categories.NewSubcategory), which is stored in the .rvt file.
"""
import os
from Autodesk.Revit.DB import (BuiltInCategory, GraphicsStyleType, Transaction,
                               TransactionStatus)
from lib import utils, revit_compat as rc, colour_manager as cm
from lib import line_pattern_manager as lpm, line_weight_manager as lwm


class StyleError(Exception):
    pass


def lines_category(doc):
    return doc.Settings.Categories.get_Item(BuiltInCategory.OST_Lines)


def _weight(cat):
    try:
        w = cat.GetLineWeight(GraphicsStyleType.Projection)
        return None if w is None else int(w)
    except Exception:
        return None


def info_from_category(doc, cat, pat_idx):
    pid = None
    try:
        pid = cat.GetLinePatternId(GraphicsStyleType.Projection)
    except Exception:
        pass
    pidv = rc.eid_value(pid) if pid is not None else -1
    pat = pat_idx.get(pidv)
    gs = None
    try:
        gs = cat.GetGraphicsStyle(GraphicsStyleType.Projection)
    except Exception:
        pass
    w = _weight(cat)
    rgb = cm.from_revit_color(cat.LineColor)
    cat_idv = rc.eid_value(cat.Id)
    return {
        'name': cat.Name, 'weight': w, 'mm': lwm.mm_for(w) if w else None,
        'rgb': rgb, 'hex': cm.rgb_to_hex(rgb),
        'pattern_name': pat['name'] if pat else ('Solid' if pidv == -1 else '(unknown)'),
        'pattern_idv': pidv, 'segments': pat['segments'] if pat else [],
        'gs_id': gs.Id if gs is not None else None,
        'gs_idv': rc.eid_value(gs.Id) if gs is not None else -1,
        'cat_id': cat.Id, 'cat_idv': cat_idv, 'builtin': cat_idv < 0,
        'cut_weight': 'n/a',
    }


def unknown_info(label='<none>'):
    return {'name': label, 'weight': None, 'mm': None, 'rgb': (0, 0, 0),
            'hex': '#000000', 'pattern_name': '?', 'pattern_idv': -1,
            'segments': [], 'gs_id': None, 'gs_idv': -1, 'cat_id': None,
            'cat_idv': 0, 'builtin': True, 'cut_weight': 'n/a'}


def info_from_graphics_style(doc, gs, pat_idx, cache=None):
    if gs is None:
        return unknown_info()
    key = rc.eid_value(gs.Id)
    if cache is not None and key in cache:
        return cache[key]
    try:
        cat = gs.GraphicsStyleCategory
        info = info_from_category(doc, cat, pat_idx) if cat is not None else unknown_info(rc.el_name(gs))
        info['gs_id'] = gs.Id
        info['gs_idv'] = key
    except Exception:
        info = unknown_info(rc.el_name(gs))
    if cache is not None:
        cache[key] = info
    return info


def list_styles(doc, pat_idx):
    out = []
    parent = lines_category(doc)
    for sub in parent.SubCategories:
        try:
            out.append(info_from_category(doc, sub, pat_idx))
        except Exception:
            continue
    out.sort(key=lambda i: i['name'].lower())
    return out


def get_by_name(styles, name):
    n = (name or '').lower()
    for s in styles:
        if s['name'].lower() == n:
            return s
    return None


def get_by_gs_idv(styles, idv):
    for s in styles:
        if s['gs_idv'] == idv:
            return s
    return None


def _category_by_name(doc, name):
    for sub in lines_category(doc).SubCategories:
        if sub.Name.lower() == name.lower():
            return sub
    return None


def validate_name(doc, name, ignore_name=None):
    ok, msg = utils.validate_name_syntax(name)
    if not ok:
        return False, msg
    existing = set(sub.Name.lower() for sub in lines_category(doc).SubCategories)
    if name.lower() in existing and name.lower() != (ignore_name or '').lower():
        return False, 'A Line Style named "%s" already exists. Enter a different name.' % name
    return True, ''


def unique_name(doc, base, suffix=' - Custom'):
    existing = set(sub.Name.lower() for sub in lines_category(doc).SubCategories)
    cand = base + suffix
    n = 2
    while cand.lower() in existing:
        cand = '%s%s %d' % (base, suffix, n)
        n += 1
    return cand


def _apply_props(cat, weight, rgb, pattern_id):
    cat.SetLineWeight(lwm.clamp(weight), GraphicsStyleType.Projection)
    cat.LineColor = cm.to_revit_color(rgb)
    if rc.is_valid_id(pattern_id):
        cat.SetLinePatternId(pattern_id, GraphicsStyleType.Projection)


def _commit(t):
    st = t.Commit()
    if st != TransactionStatus.Committed:
        raise StyleError('Transaction did not commit (%s).' % st)


def create_line_style(doc, name, weight, rgb, pattern_id, origin=None):
    """Create a NEW Line Style (own transaction). Never overwrites."""
    if doc.IsReadOnly:
        raise StyleError('The document is read-only.')
    ok, msg = validate_name(doc, name)
    if not ok:
        raise StyleError(msg)
    t = Transaction(doc, 'Create Line Style - ' + name)
    t.Start()
    try:
        cat = doc.Settings.Categories.NewSubcategory(lines_category(doc), name)
        _apply_props(cat, weight, rgb, pattern_id)
        if cat.GetGraphicsStyle(GraphicsStyleType.Projection) is None:
            raise StyleError('Revit did not create a graphics style for "%s".' % name)
        _commit(t)
    except Exception:
        if t.HasStarted() and not t.HasEnded():
            t.RollBack()
        raise
    if origin:
        save_origin(doc, name, origin)
    pats = lpm.list_patterns(doc)
    return get_by_name(list_styles(doc, lpm.index_by_idv(pats)), name)


def update_line_style(doc, name, weight, rgb, pattern_id):
    """Edit an EXISTING style in place (affects every element using it)."""
    cat = _category_by_name(doc, name)
    if cat is None:
        raise StyleError('Line Style "%s" no longer exists.' % name)
    t = Transaction(doc, 'Edit Line Style - ' + name)
    t.Start()
    try:
        _apply_props(cat, weight, rgb, pattern_id)
        _commit(t)
    except Exception:
        if t.HasStarted() and not t.HasEnded():
            t.RollBack()
        raise


def rename_line_style(doc, old, new):
    ok, msg = validate_name(doc, new, ignore_name=old)
    if not ok:
        raise StyleError(msg)
    cat = _category_by_name(doc, old)
    if cat is None:
        raise StyleError('Line Style "%s" no longer exists.' % old)
    if rc.eid_value(cat.Id) < 0:
        raise StyleError('Built-in Revit line styles cannot be renamed.')
    t = Transaction(doc, 'Rename Line Style')
    t.Start()
    try:
        cat.Name = new
        _commit(t)
    except Exception:
        if t.HasStarted() and not t.HasEnded():
            t.RollBack()
        raise
    origins = _load_origins(doc)
    if old in origins:
        origins[new] = origins.pop(old)
    for k, v in list(origins.items()):
        if v == old:
            origins[k] = new
    _save_origins(doc, origins)


def delete_line_style(doc, name):
    cat = _category_by_name(doc, name)
    if cat is None:
        raise StyleError('Line Style "%s" no longer exists.' % name)
    if rc.eid_value(cat.Id) < 0:
        raise StyleError('Built-in Revit line styles cannot be deleted.')
    t = Transaction(doc, 'Delete Line Style - ' + name)
    t.Start()
    try:
        doc.Delete(cat.Id)
        _commit(t)
    except Exception:
        if t.HasStarted() and not t.HasEnded():
            t.RollBack()
        raise


# -- origin tracking for duplicated styles (stored outside the model) -------
def _origin_key(doc):
    try:
        return doc.ProjectInformation.UniqueId
    except Exception:
        return doc.Title


def _origins_path():
    return os.path.join(utils.config_dir(), 'style_origins.json')


def _load_origins(doc):
    data = utils.read_json(_origins_path(), {}) or {}
    return data.get(_origin_key(doc), {})


def _save_origins(doc, origins):
    data = utils.read_json(_origins_path(), {}) or {}
    data[_origin_key(doc)] = origins
    try:
        utils.write_json(_origins_path(), data)
    except Exception:
        pass


def save_origin(doc, new_name, original_name):
    o = _load_origins(doc)
    o[new_name] = original_name
    _save_origins(doc, o)


def origin_of(doc, name):
    return _load_origins(doc).get(name, '')
