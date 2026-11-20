# -*- coding: utf-8 -*-
"""Logging, result bookkeeping and user-facing messages (no geometry here)."""
import codecs
import os
import tempfile
import time
import traceback

from pyrevit import forms, script

from floor_tools import settings

try:
    text_type = unicode  # noqa: F821  (IronPython 2 / Python 2)
except NameError:
    text_type = str

output_logger = script.get_logger()

STATUS_CREATED = "created"
STATUS_EXISTING = "existing"
STATUS_FAILED = "failed"
STATUS_NOT_PROCESSED = "not_processed"


def to_text(value):
    """Best-effort conversion of anything (incl. .NET exceptions) to text."""
    if isinstance(value, bytes):
        try:
            return value.decode("utf-8")
        except UnicodeDecodeError:
            return value.decode("latin-1")
    try:
        return text_type(value)
    except Exception:
        return repr(value)


class FloorToolsError(Exception):
    """An expected, explainable failure. The message is shown to the user as is."""


def friendly_message(ex):
    """One readable line for an exception - never a stack trace."""
    if isinstance(ex, FloorToolsError):
        return to_text(ex)
    lines = [l for l in to_text(ex).strip().splitlines() if l.strip()]
    text = lines[0] if lines else ex.__class__.__name__
    return "Revit reported: {}".format(text)


# --------------------------------------------------------------------- log --
class DetailLog(object):
    """Collects diagnostic lines; written to a temp file (and optionally echoed)."""

    def __init__(self):
        self._lines = []
        self.echo = False
        self.path = os.path.join(tempfile.gettempdir(), "FloorTools", "floor_to_fill_region.log")

    def add(self, level, message, floor_id=None):
        prefix = "[{}]".format(level)
        if floor_id is not None:
            prefix += " Floor {}".format(floor_id)
        self._lines.append(to_text("{} {}".format(prefix, to_text(message))))

    def info(self, message, floor_id=None):
        self.add("INFO", message, floor_id)

    def warning(self, message, floor_id=None):
        self.add("WARN", message, floor_id)

    def error(self, message, floor_id=None):
        self.add("ERROR", message, floor_id)

    def add_traceback(self, floor_id=None):
        self.add("TRACE", traceback.format_exc(), floor_id)

    def flush(self):
        """Write the log file; echo to the pyRevit output window if requested."""
        header = "Floor to Fill Region log - {}".format(time.strftime("%Y-%m-%d %H:%M:%S"))
        body = [header] + self._lines
        try:
            folder = os.path.dirname(self.path)
            if not os.path.isdir(folder):
                os.makedirs(folder)
            with codecs.open(self.path, "w", "utf-8") as handle:
                handle.write(u"\n".join(body))
        except Exception:
            pass  # logging must never break the command
        if self.echo:
            for line in body:
                print(line)


# ----------------------------------------------------------------- results --
class FloorResult(object):
    def __init__(self, floor_id, status, message="", regions=0, warnings=None,
                 label=None, linkable=True):
        self.floor_id = floor_id          # DB.ElementId (in the Floor's own document)
        self.label = label                # e.g. "Floor ID 123 (link 'Arch.rvt')"
        self.linkable = linkable          # False for linked floors: ids are not host ids
        self.status = status
        self.message = message
        self.regions = regions
        self.warnings = warnings or []


class RunSummary(object):
    def __init__(self, selected):
        self.selected = selected
        self.results = []
        self.notes = []
        self.ignored_non_floors = 0
        self.cancelled = False
        self.types_created = []      # names of Filled Region Types created

    def add(self, result):
        self.results.append(result)

    def _with_status(self, status):
        return [r for r in self.results if r.status == status]

    @property
    def created(self):
        return self._with_status(STATUS_CREATED)

    @property
    def existing(self):
        return self._with_status(STATUS_EXISTING)

    @property
    def failed(self):
        return self._with_status(STATUS_FAILED)

    @property
    def not_processed(self):
        return self._with_status(STATUS_NOT_PROCESSED)

    @property
    def regions_created(self):
        return sum(r.regions for r in self.created)

    @property
    def with_warnings(self):
        return [r for r in self.results if r.warnings]

    def text(self):
        lines = ["Floors / Toposolids selected: {}".format(self.selected),
                 "Fill Regions created: {}".format(self.regions_created)]
        if len(self.created) != self.regions_created:
            lines[-1] += " (from {} Floors)".format(len(self.created))
        if self.types_created:
            lines.append("Fill Region Types created: {}".format(len(self.types_created)))
        lines.append("Already existed (skipped): {}".format(len(self.existing)))
        lines.append("Failed: {}".format(len(self.failed)))
        if self.not_processed:
            lines.append("Not processed (cancelled): {}".format(len(self.not_processed)))
        if self.with_warnings:
            lines.append("Created with warnings: {}".format(len(self.with_warnings)))
        if self.ignored_non_floors:
            lines.append("Ignored other elements: {}".format(self.ignored_non_floors))
        for note in self.notes:
            lines.append("")
            lines.append(note)
        return "\n".join(lines)


# ---------------------------------------------------------------- messages --
def warn(message, sub_msg=None):
    forms.alert(message, title=settings.COMMAND_TITLE, sub_msg=sub_msg)


def result_label(result):
    return result.label or "Floor ID {}".format(_id_text(result.floor_id))


def _id_text(element_id):
    from floor_tools import revit_compat as compat
    return str(compat.element_id_value(element_id))


def show_summary(summary, log):
    """Final report: dialog for everybody, output-window links for failures."""
    expanded = None
    if summary.failed:
        expanded = "Failed elements:\n" + "\n".join(
            "  {} - {}".format(result_label(r), r.message) for r in summary.failed)
    if summary.types_created:
        expanded = (expanded + "\n\n" if expanded else "") + "New Fill Region Types:\n" + "\n".join(
            "  " + name for name in summary.types_created)
    if summary.with_warnings:
        expanded = (expanded + "\n\n" if expanded else "") + "Warnings:\n" + "\n".join(
            "  {} - {}".format(result_label(r), "; ".join(r.warnings))
            for r in summary.with_warnings)
    forms.alert(summary.text(), title=settings.COMMAND_TITLE + " - complete",
                expanded=expanded, warn_icon=bool(summary.failed))
    if summary.failed:
        output = script.get_output()
        print("Failed elements (click to select in Revit):")
        for r in summary.failed:
            shown = output.linkify(r.floor_id, result_label(r)) if r.linkable else result_label(r)
            print("{} - {}".format(shown, r.message))
        print("Detailed log: {}".format(log.path))


def report_unexpected(ex, log):
    """Unexpected error: short dialog for the user, trace goes to the log only."""
    forms.alert("Floor to Fill Region stopped because of an unexpected problem.",
                title=settings.COMMAND_TITLE,
                sub_msg=friendly_message(ex),
                expanded="Nothing was changed if the problem happened before the final commit.\n"
                         "Technical details were written to:\n{}".format(log.path))
