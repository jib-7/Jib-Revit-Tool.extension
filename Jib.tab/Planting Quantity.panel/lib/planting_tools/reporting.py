# -*- coding: utf-8 -*-
"""Everything the user sees in the pyRevit output window, plus the Excel export."""
from __future__ import division
from collections import defaultdict

from pyrevit import forms, script

from planting_tools import config


def _output():
    return script.get_output()


def status_text(row):
    if row.reason:
        return u"{}: {}".format(row.status, row.reason)
    return row.status


def _area_text(row):
    return "{:.3f}".format(row.area_m2) if row.area_m2 is not None else "-"


def _quantity_text(row):
    return str(row.quantity) if row.quantity is not None else "-"


def show_scan(scan):
    out = _output()
    out.print_md("## Planting Quantity Calculator")
    out.print_md(
        "* Filled Regions scanned: **{}**\n"
        "* With type `Type Comments = Planting`: **{}**\n"
        "* Excluded (other Type Comments value): {}\n"
        "* Excluded (Type Comments empty): {}\n"
        "* Excluded (type has no Type Comments parameter): {}".format(
            scan.total, len(scan.items), scan.excluded_other,
            scan.excluded_empty, scan.excluded_no_param))


def show_preview(rows, run_number):
    out = _output()
    columns = ["Element ID", "Filled Region type", "Type Comments",
               u"Area ({})".format(config.SQM), "Planting spacing",
               "Current Planting Quantity", "Calculated Planting Quantity", "Status"]
    data = [[str(r.element_id), r.type_name, r.type_comments.strip(), _area_text(r),
             r.spacing_text or "-", r.current_text, _quantity_text(r), status_text(r)]
            for r in rows]
    out.print_table(table_data=data, title="Preview (calculation #{})".format(run_number),
                    columns=columns)


def show_type_summary(rows):
    """Group by Filled Region type and show total quantity per type."""
    out = _output()

    # Only rows that have a calculated quantity
    valid_rows = [r for r in rows if r.quantity is not None]

    if not valid_rows:
        out.print_md("### Summary by Filled Region Type\n\nNo valid quantities to summarise.")
        return

    # Group: type_name -> total quantity
    totals = defaultdict(int)
    for r in valid_rows:
        totals[r.type_name] += r.quantity

    # Sort by type name
    sorted_types = sorted(totals.items(), key=lambda x: x[0])

    columns = ["Filled Region type", "Total Quantity"]
    data = [[type_name, str(qty)] for type_name, qty in sorted_types]

    out.print_table(
        table_data=data,
        title="Final Result – Total Quantity by Filled Region Type",
        columns=columns
    )

    # Grand total
    grand_total = sum(totals.values())
    out.print_md("**Grand Total plants: {}**".format(grand_total))


def count_rows(rows):
    counts = {"valid": 0, "ready": 0, "up_to_date": 0, "updated": 0,
              "skipped": 0, "failed": 0, "total_plants": 0}
    for r in rows:
        if r.area_m2 is not None and r.spacing_m is not None:
            counts["valid"] += 1
        if r.status == config.STATUS_READY:
            counts["ready"] += 1
        elif r.status == config.STATUS_UP_TO_DATE:
            counts["up_to_date"] += 1
        elif r.status == config.STATUS_UPDATED:
            counts["updated"] += 1
        elif r.status == config.STATUS_SKIPPED:
            counts["skipped"] += 1
        elif r.status == config.STATUS_FAILED:
            counts["failed"] += 1
        if r.quantity is not None and r.status != config.STATUS_SKIPPED:
            counts["total_plants"] += r.quantity
    return counts


def show_summary(scan, rows):
    out = _output()
    c = count_rows(rows)
    out.print_md("## Final summary")
    out.print_md(
        "* Total Filled Regions scanned: **{}**\n"
        "* Filled Regions with `Type Comments = Planting`: **{}**\n"
        "* With valid area and spacing: **{}**\n"
        "* Quantities successfully updated: **{}**\n"
        "* Already up to date (not rewritten): {}\n"
        "* Skipped (missing or invalid parameters): **{}**\n"
        "* Failed updates: **{}**\n"
        "* Total plants in processed regions: **{}**".format(
            scan.total, len(scan.items), c["valid"], c["updated"],
            c["up_to_date"], c["skipped"], c["failed"], c["total_plants"]))

    # Show the grouped type summary
    show_type_summary(rows)

    problems = [r for r in rows if r.status in (config.STATUS_SKIPPED, config.STATUS_FAILED)]
    if problems:
        out.print_table(
            table_data=[[str(r.element_id), r.status, r.reason] for r in problems],
            title="Planting Filled Regions that could not be processed",
            columns=["Element ID", "Result", "Exact reason"])
    else:
        out.print_md("All qualifying Filled Regions were processed without problems.")


def show_cancelled():
    _output().print_md("Cancelled. **No parameters were changed.**")


def export_excel(rows):
    """Export results to a real .xlsx file using Excel COM."""
    try:
        import clr
        clr.AddReference("Microsoft.Office.Interop.Excel")
        from Microsoft.Office.Interop import Excel
    except Exception:
        forms.alert(
            "Microsoft Excel is not available on this computer.\n\n"
            "Please make sure Excel is installed, then try again.",
            title="Excel Export"
        )
        return None

    # Ask user for save location
    path = forms.save_file(file_ext="xlsx", default_name="Planting_Quantities")
    if not path:
        return None

    # Force .xlsx extension
    if not path.lower().endswith(".xlsx"):
        path = path + ".xlsx"

    excel = None
    workbook = None
    try:
        excel = Excel.ApplicationClass()
        excel.Visible = False
        excel.DisplayAlerts = False
        excel.ScreenUpdating = False

        workbook = excel.Workbooks.Add()

        # ---------- Sheet 1 : Detailed Results ----------
        ws1 = workbook.Worksheets[1]
        ws1.Name = "Detailed Results"

        header = [
            "Element ID",
            "Filled Region type",
            "Type Comments",
            "Area (m2)",
            "Planting spacing (Density)",
            "Current Planting Quantity",
            "Calculated Planting Quantity",
            "Status",
            "Reason"
        ]

        # Header
        for col, title in enumerate(header, 1):
            cell = ws1.Cells[1, col]
            cell.Value2 = title
            cell.Font.Bold = True
            cell.Font.Color = 0xFFFFFF
            cell.Interior.Color = 0x2F5496
            cell.HorizontalAlignment = -4108  # xlCenter

        # Data rows
        for row_idx, r in enumerate(rows, 2):
            values = [
                r.element_id,
                r.type_name or "",
                (r.type_comments or "").strip(),
                round(r.area_m2, 4) if r.area_m2 is not None else "",
                r.spacing_text or "",
                r.current_text if r.current_text not in ("n/a", "(empty)") else "",
                r.quantity if r.quantity is not None else "",
                r.status or "",
                r.reason or ""
            ]
            for col, value in enumerate(values, 1):
                ws1.Cells[row_idx, col].Value2 = value

        ws1.Columns.AutoFit()

        # ---------- Sheet 2 : Summary by Type ----------
        ws2 = workbook.Worksheets.Add(After=ws1)
        ws2.Name = "Summary by Type"

        totals = defaultdict(int)
        for r in rows:
            if r.quantity is not None:
                totals[r.type_name] += r.quantity

        sorted_types = sorted(totals.items(), key=lambda x: x[0])

        # Header
        ws2.Cells[1, 1].Value2 = "Filled Region type"
        ws2.Cells[1, 2].Value2 = "Total Quantity"
        for col in range(1, 3):
            cell = ws2.Cells[1, col]
            cell.Font.Bold = True
            cell.Font.Color = 0xFFFFFF
            cell.Interior.Color = 0x2F5496

        # Data
        for idx, (type_name, qty) in enumerate(sorted_types, 2):
            ws2.Cells[idx, 1].Value2 = type_name
            ws2.Cells[idx, 2].Value2 = qty

        # Grand Total
        last_row = len(sorted_types) + 2
        ws2.Cells[last_row, 1].Value2 = "GRAND TOTAL"
        ws2.Cells[last_row, 2].Value2 = sum(totals.values())
        ws2.Cells[last_row, 1].Font.Bold = True
        ws2.Cells[last_row, 2].Font.Bold = True

        ws2.Columns.AutoFit()

        # ---------- Save as real XLSX ----------
        # 51 = xlOpenXMLWorkbook (.xlsx)
        workbook.SaveAs(path, FileFormat=51)

        _output().print_md("**Excel file saved:** `{}`".format(path))
        return path

    except Exception as ex:
        forms.alert(
            "Failed to create Excel file:\n\n{}".format(str(ex)),
            title="Excel Export Error"
        )
        return None

    finally:
        try:
            if workbook is not None:
                workbook.Close(SaveChanges=False)
        except:
            pass
        try:
            if excel is not None:
                excel.Quit()
        except:
            pass
        # Clean up COM objects
        try:
            del workbook
            del excel
        except:
            pass