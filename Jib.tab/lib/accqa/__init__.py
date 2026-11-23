# -*- coding: utf-8 -*-
"""ACC Quick Access - shared library package for the pyRevit extension.

All modules live inside this package (instead of loose files in lib/) so their
names cannot collide with modules from other pyRevit extensions that also add
their own lib folder to sys.path.
"""

__version__ = "1.0.2"
APP_NAME = "ACC Quick Access"

# Schema version written to config.json
CONFIG_SCHEMA_VERSION = "1.0"
