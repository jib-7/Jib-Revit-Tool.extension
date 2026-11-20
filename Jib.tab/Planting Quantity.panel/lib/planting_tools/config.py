# -*- coding: utf-8 -*-
"""All fixed names and constants live here, so they are easy to change."""

# Value that the associated type's "Type Comments" must have (compared in lower case, stripped).
TYPE_COMMENTS_EXPECTED = "planting"

# Parameter names on the Filled Region instance.
SPACING_PARAM_NAME = "Planting spacing"
QUANTITY_PARAM_NAME = "Planting Quantity"

# Revit stores lengths in decimal feet. 1 foot = 0.3048 m exactly (by definition).
FEET_TO_METRES = 0.3048
SQFEET_TO_SQMETRES = FEET_TO_METRES * FEET_TO_METRES

# Planting arrangement used by the quantity calculator (see quantity_calculator.ARRANGEMENTS).
DEFAULT_ARRANGEMENT = "square"

# Row status values (shared by workflow.py and reporting.py).
STATUS_READY = "Ready"
STATUS_UP_TO_DATE = "Up to date"
STATUS_SKIPPED = "Skipped"
STATUS_UPDATED = "Updated"
STATUS_FAILED = "Failed"

SQM = u"m\u00b2"
