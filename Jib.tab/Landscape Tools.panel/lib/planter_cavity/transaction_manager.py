# -*- coding: utf-8 -*-
"""All-or-nothing transaction wrapper."""
from Autodesk.Revit.DB import Transaction, TransactionStatus

from .models import PlanterError


class SafeTransaction(object):
    """Context manager: commits on success, rolls back on ANY exception."""

    def __init__(self, doc, name):
        self.doc = doc
        self.name = name
        self.tx = None

    def __enter__(self):
        self.tx = Transaction(self.doc, self.name)
        status = self.tx.Start()
        if status != TransactionStatus.Started:
            raise PlanterError("Could not start the Revit transaction.")
        return self

    def __exit__(self, exc_type, exc, tb):
        if exc_type is not None:
            try:
                if self.tx.HasStarted():
                    self.tx.RollBack()
            except Exception:
                pass
            return False
        status = self.tx.Commit()
        if status != TransactionStatus.Committed:
            try:
                if self.tx.HasStarted():
                    self.tx.RollBack()
            except Exception:
                pass
            raise PlanterError("Revit refused to commit the changes (%s). Nothing was created." % status)
        return False
