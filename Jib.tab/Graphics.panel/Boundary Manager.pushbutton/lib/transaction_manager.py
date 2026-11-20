# -*- coding: utf-8 -*-
"""Transaction orchestration: TransactionGroup > Transaction > SubTransaction."""
from Autodesk.Revit.DB import (Transaction, TransactionGroup, TransactionStatus)
from lib import revit_compat as rc, boundary_manager as bm, line_style_manager as lsm
from lib import line_pattern_manager as lpm


class TxError(Exception):
    pass


def check_writable(doc):
    if doc.IsReadOnly:
        raise TxError('The document is read-only; no changes can be made.')
    if doc.IsModifiable:
        raise TxError('Another transaction is already open in Revit.')


def _gs(doc, info):
    gs = doc.GetElement(info['gs_id']) if info.get('gs_id') is not None else None
    if gs is None:
        raise TxError('The Line Style "%s" has no valid Graphics Style.' % info['name'])
    return gs


def _run_apply(doc, targets, gs, pat_idx, name):
    t = Transaction(doc, name)
    t.Start()
    try:
        res = bm.apply_style_to_targets(doc, targets, gs, pat_idx)
        if res['updated'] == 0 and res['failed'] > 0:
            t.RollBack()
        else:
            if t.Commit() != TransactionStatus.Committed:
                raise TxError('Transaction did not commit.')
        return res
    except Exception:
        if t.HasStarted() and not t.HasEnded():
            t.RollBack()
        raise


def apply_style(doc, targets, style_info, name='Apply Boundary Line Style'):
    check_writable(doc)
    pat_idx = lpm.index_by_idv(lpm.list_patterns(doc))
    group = TransactionGroup(doc, name)
    group.Start()
    try:
        res = _run_apply(doc, targets, _gs(doc, style_info), pat_idx, name)
        if res['updated'] > 0:
            group.Assimilate()
        else:
            group.RollBack()
        return res
    except Exception:
        if group.HasStarted() and not group.HasEnded():
            group.RollBack()
        raise


def save_and_apply(doc, name, weight, rgb, pattern_id, targets, origin=None):
    """Create the Line Style and apply it as ONE undo step.
    If nothing could be applied because of failures, the creation is rolled
    back too (no partial changes)."""
    check_writable(doc)
    pat_idx = lpm.index_by_idv(lpm.list_patterns(doc))
    group = TransactionGroup(doc, 'Create + Apply Line Style - ' + name)
    group.Start()
    try:
        info = lsm.create_line_style(doc, name, weight, rgb, pattern_id)
        res = _run_apply(doc, targets, _gs(doc, info), pat_idx, 'Apply Line Style')
        if res['updated'] == 0 and res['failed'] > 0:
            group.RollBack()
            res['style_created'] = False
            return None, res
        group.Assimilate()
        res['style_created'] = True
    except Exception:
        if group.HasStarted() and not group.HasEnded():
            group.RollBack()
        raise
    if origin:
        lsm.save_origin(doc, name, origin)
    pats = lpm.list_patterns(doc)
    info = lsm.get_by_name(lsm.list_styles(doc, lpm.index_by_idv(pats)), name)
    return info, res


def reassign_and_delete(doc, old_info, new_info, curve_ids):
    """Move every curve element in curve_ids (ElementId values) from the old
    style to the new one, then delete the old Line Style. One undo step."""
    check_writable(doc)
    new_gs = _gs(doc, new_info)
    group = TransactionGroup(doc, 'Reassign and delete Line Style')
    group.Start()
    try:
        t = Transaction(doc, 'Reassign curves')
        t.Start()
        failed = 0
        for idv in curve_ids:
            el = doc.GetElement(rc.make_eid(idv))
            ok = False
            if el is not None:
                ok, _ = bm.set_segment_style(el, new_gs)
            if not ok:
                failed += 1
        if failed:
            t.RollBack()
            group.RollBack()
            raise TxError('%d element(s) could not be reassigned. Nothing was changed.' % failed)
        if t.Commit() != TransactionStatus.Committed:
            raise TxError('Transaction did not commit.')
        lsm.delete_line_style(doc, old_info['name'])
        group.Assimilate()
    except Exception:
        if group.HasStarted() and not group.HasEnded():
            group.RollBack()
        raise
