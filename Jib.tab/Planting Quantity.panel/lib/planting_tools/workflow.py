# -*- coding: utf-8 -*-
"""Coordinates scan -> preview -> confirmation -> update -> summary."""
from __future__ import division
from Autodesk.Revit.DB import Transaction, SubTransaction, TransactionStatus
from pyrevit import forms, HOST_APP

from planting_tools import (area_calculator, config, parameters,
                            quantity_calculator, reporting, selection)

OPT_UPDATE = "Update Parameters"
OPT_REFRESH = "Calculate / Refresh"
OPT_EXPORT = "Export Excel"
OPT_CANCEL = "Cancel"
TITLE = "Planting Quantity Calculator"


class Row(object):
    """Calculation result for one qualifying Filled Region."""
    def __init__(self, item):
        self.element = item.element
        self.element_id = parameters.eid_value(item.element.Id)
        self.type_name = item.type_name
        self.type_comments = item.type_comments
        self.area_m2 = None
        self.spacing_m = None
        self.spacing_text = ""
        self.current_value = None
        self.current_text = ""
        self.quantity = None
        self.status = ""
        self.reason = ""


def build_row(item):
    """Read area, spacing and current quantity; calculate the result. Never raises."""
    row = Row(item)
    problems = []

    try:
        row.area_m2, error = area_calculator.get_area_m2(item.element)
    except Exception as ex:
        row.area_m2, error = None, "Unexpected error while calculating area: {}".format(ex)
    if error:
        problems.append(error)

    row.spacing_m, row.spacing_text, error = parameters.read_spacing_m(item.element)
    if error:
        problems.append(error)

    quantity_param, error = parameters.check_quantity_param(item.element)
    row.current_value, row.current_text = parameters.current_quantity(quantity_param)
    if error:
        problems.append(error)

    if problems:
        row.status = config.STATUS_SKIPPED
        row.reason = "; ".join(problems)
        return row

    row.quantity = quantity_calculator.calculate_quantity(
        row.area_m2, row.spacing_m, config.DEFAULT_ARRANGEMENT)
    if row.current_value is not None and abs(row.current_value - row.quantity) < 1e-9:
        row.status = config.STATUS_UP_TO_DATE
    else:
        row.status = config.STATUS_READY
    return row


def _same_document(doc):
    try:
        active = HOST_APP.uiapp.ActiveUIDocument.Document
        return active.Title == doc.Title and active.PathName == doc.PathName
    except Exception:
        return False


def _update_parameters(doc, rows):
    """Write results inside ONE transaction; each element gets its own sub-transaction."""
    targets = [r for r in rows if r.status == config.STATUS_READY]
    if not targets:
        return

    transaction = Transaction(doc, "Update Planting Quantities")
    try:
        transaction.Start()
    except Exception as ex:
        for r in targets:
            r.status, r.reason = config.STATUS_FAILED, "Could not start transaction: {}".format(ex)
        return

    try:
        for r in targets:
            sub = SubTransaction(doc)
            try:
                sub.Start()
                param, error = parameters.check_quantity_param(r.element)
                if error:
                    raise RuntimeError(error)
                parameters.write_quantity(param, r.quantity)
                sub.Commit()
                r.status, r.reason = config.STATUS_UPDATED, ""
            except Exception as ex:
                try:
                    sub.RollBack()
                except Exception:
                    pass
                r.status, r.reason = config.STATUS_FAILED, str(ex)

        if transaction.Commit() != TransactionStatus.Committed:
            raise RuntimeError("Revit did not commit the transaction")
    except Exception as ex:
        try:
            if transaction.HasStarted():
                transaction.RollBack()
        except Exception:
            pass
        for r in targets:
            if r.status == config.STATUS_UPDATED:
                r.status = config.STATUS_FAILED
                r.reason = "Transaction rolled back: {}".format(ex)


def run():
    uidoc = HOST_APP.uiapp.ActiveUIDocument
    doc = uidoc.Document if uidoc is not None else None
    if doc is None:
        forms.alert("Open a Revit project first.", title=TITLE)
        return
    if doc.IsFamilyDocument:
        forms.alert("This tool works in project documents only, not in the Family Editor.",
                    title=TITLE)
        return

    scan = None
    rows = []
    run_number = 0
    need_calculation = True

    while True:
        if need_calculation:
            scan = selection.collect_planting_regions(doc)
            reporting.show_scan(scan)
            if not scan.items:
                forms.alert("No Filled Regions were found whose type has "
                            "Type Comments = Planting.\n\nNothing was changed.", title=TITLE)
                return
            rows = sorted((build_row(i) for i in scan.items),
                          key=lambda r: (r.type_name, r.element_id))
            run_number += 1
            reporting.show_preview(rows, run_number)
            need_calculation = False

        c = reporting.count_rows(rows)
        message = ("Found {} Filled Region(s) with Type Comments = Planting.\n\n"
                   "Ready to update: {}\nAlready up to date: {}\nSkipped (see preview): {}\n\n"
                   "Review the preview table in the pyRevit output window.".format(
                       len(rows), c["ready"], c["up_to_date"], c["skipped"]))
        options = ([OPT_UPDATE] if c["ready"] else []) + [OPT_REFRESH, OPT_EXPORT, OPT_CANCEL]
        choice = forms.alert(message, title=TITLE, options=options)

        if choice == OPT_REFRESH:
            need_calculation = True
            continue
        if choice == OPT_EXPORT:
            reporting.export_excel(rows)
            continue
        if choice != OPT_UPDATE:
            reporting.show_cancelled()
            return

        confirmed = forms.alert(
            "Write Planting Quantity on {} Filled Region(s)?\n\n"
            "Only Filled Regions whose type has Type Comments = Planting are changed. "
            "You can undo this with Ctrl+Z.".format(c["ready"]),
            title=TITLE, yes=True, no=True)
        if not confirmed:
            continue
        if not _same_document(doc):
            forms.alert("The active document has changed. Nothing was updated. "
                        "Please run the tool again.", title=TITLE)
            return
        if doc.IsReadOnly:
            forms.alert("The document is read-only. Nothing was updated.", title=TITLE)
            return

        _update_parameters(doc, rows)
        reporting.show_summary(scan, rows)
        if forms.alert("Export the results to Excel for BOQ / take-off?",
                       title=TITLE, yes=True, no=True):
            reporting.export_excel(rows)
        return
