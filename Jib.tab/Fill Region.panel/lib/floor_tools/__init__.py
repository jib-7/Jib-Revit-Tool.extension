# -*- coding: utf-8 -*-
"""Floor Tools shared library (imported by the pushbutton scripts).

The package is deliberately namespaced (``floor_tools``) instead of putting
generic module names such as ``utils`` or ``settings`` directly in ``lib/``:
pyRevit adds the ``lib`` folder of *every* loaded extension to ``sys.path``,
so un-namespaced names easily collide with other extensions.
"""
