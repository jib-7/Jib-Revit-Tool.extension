# -*- coding: utf-8 -*-
"""Collects progress/diagnostic messages and renders the final report."""


class Report(object):
    def __init__(self):
        self.lines = []
        self.warnings = []
        self.errors = []
        self.results = {}

    def info(self, text):
        self.lines.append(text)

    def warn(self, text):
        self.warnings.append(text)

    def error(self, text):
        self.errors.append(text)

    def render_result(self):
        r = self.results

        def flag(key, label):
            return "- %s: %s" % (label, r.get(key, "Not created"))
        out = ["Fill Planter Cavity \u2013 Result", ""]
        out.append(flag("026", "026 Filled Region"))
        out.append(flag("005", "005 Detail Item"))
        out.append(flag("006", "006 Detail Item"))
        out.append(flag("008", "008 Detail Item"))
        out.append(flag("010", "010 Detail Component"))
        out.append(flag("halftone", "Halftone Override").replace("Not created", "Not applied"))
        return "\n".join(out)
