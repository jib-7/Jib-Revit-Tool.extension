# -*- coding: utf-8 -*-
"""Reading and validating the parameters used by the calculator."""
from __future__ import division
from Autodesk.Revit.DB import BuiltInParameter, StorageType, SpecTypeId
from planting_tools import config


def eid_value(element_id):
    """Integer value of an ElementId (ElementId.Value in 2024+, IntegerValue before)."""
    try:
        return element_id.Value
    except AttributeError:
        return element_id.IntegerValue


def get_type_name(type_element):
    if type_element is None:
        return "(no type)"
    try:
        p = type_element.get_Parameter(BuiltInParameter.SYMBOL_NAME_PARAM)
        if p is not None and p.AsString():
            return p.AsString()
    except Exception:
        pass
    try:
        return type_element.Name
    except Exception:
        return "(unnamed type)"


def read_type_comments(type_element):
    """Return (parameter_found, text) for the TYPE parameter 'Type Comments'.
    The built-in parameter is tried first because it works in every Revit language;
    the name lookup is only a fallback.
    """
    if type_element is None:
        return False, ""
    p = type_element.get_Parameter(BuiltInParameter.ALL_MODEL_TYPE_COMMENTS)
    if p is None:
        p = type_element.LookupParameter("Type Comments")
    if p is None or p.StorageType != StorageType.String:
        return False, ""
    return True, (p.AsString() or "")


def _data_type(parameter):
    try:
        return parameter.Definition.GetDataType()
    except Exception:
        return None


def _type_label(data_type):
    try:
        return data_type.TypeId
    except Exception:
        return str(data_type)


def read_spacing_m(element):
    """Return (density, display_text, error_text) for 'Planting spacing'.

    The parameter is treated as density (plants per m²).
    Accepts Integer or Number (unitless).
    """
    name = config.SPACING_PARAM_NAME
    p = element.LookupParameter(name)              # instance parameter first
    if p is None:                                  # then the Filled Region TYPE
        try:
            type_element = element.Document.GetElement(element.GetTypeId())
            if type_element is not None:
                p = type_element.LookupParameter(name)
        except Exception:
            p = None

    if p is None:
        return None, "", "Parameter '{}' not found on the Filled Region or its type".format(name)

    if p.IsReadOnly:
        return None, "", "Parameter '{}' is read-only".format(name)

    storage = p.StorageType
    data_type = _data_type(p)

    # Accept Integer or Number only
    if storage == StorageType.Integer:
        # reject Yes/No
        if data_type is not None and data_type == SpecTypeId.Boolean.YesNo:
            return None, "", "Parameter '{}' is Yes/No, not a whole number".format(name)
    elif storage == StorageType.Double:
        # only pure Number (unitless) is allowed
        if data_type is not None and data_type != SpecTypeId.Number:
            return None, "", "Parameter '{}' must be Integer or Number (found {})".format(
                name, _type_label(data_type))
    else:
        return None, "", "Parameter '{}' has an incompatible storage type ({})".format(name, storage)

    if not p.HasValue:
        return None, "", "Parameter '{}' is empty".format(name)

    # Read the value (treated as density = plants per m²)
    try:
        if storage == StorageType.Integer:
            value = float(p.AsInteger())
            text = str(p.AsInteger())
        else:  # Double / Number
            value = p.AsDouble()
            text = p.AsValueString() or "{:g}".format(value)
    except Exception:
        return None, "", "Could not read value of '{}'".format(name)

    if value <= 0:
        return None, text, "Parameter '{}' is zero or negative".format(name)

    return value, text, None


def check_quantity_param(element):
    """Return (parameter_or_None, error_text) for 'Planting Quantity'.
    The parameter object is returned even when there is an error (if it exists),
    so the current value can still be shown in the preview.
    """
    name = config.QUANTITY_PARAM_NAME
    p = element.LookupParameter(name)
    if p is None:
        return None, "Parameter '{}' not found".format(name)
    if p.IsReadOnly:
        return p, "Parameter '{}' is read-only".format(name)
    storage = p.StorageType
    data_type = _data_type(p)
    if storage == StorageType.Integer:
        if data_type is not None and data_type == SpecTypeId.Boolean.YesNo:
            return p, "Parameter '{}' is Yes/No, not a whole number".format(name)
        return p, None
    if storage == StorageType.Double:
        if data_type is not None and data_type != SpecTypeId.Number:
            return p, "Parameter '{}' must be Integer or Number (found {})".format(
                name, _type_label(data_type))
        return p, None
    return p, "Parameter '{}' has an incompatible storage type ({})".format(name, storage)


def current_quantity(parameter):
    """Return (numeric_value_or_None, display_text) of the current Planting Quantity."""
    if parameter is None:
        return None, "n/a"
    try:
        if not parameter.HasValue:
            return None, "(empty)"
        if parameter.StorageType == StorageType.Integer:
            value = parameter.AsInteger()
            return value, str(value)
        if parameter.StorageType == StorageType.Double:
            value = parameter.AsDouble()
            return value, "{:g}".format(value)
    except Exception:
        pass
    return None, "n/a"


def write_quantity(parameter, quantity):
    """Write the whole number. Raises RuntimeError if Revit refuses it."""
    if parameter.StorageType == StorageType.Integer:
        ok = parameter.Set(int(quantity))
    elif parameter.StorageType == StorageType.Double:
        ok = parameter.Set(float(quantity))
    else:
        raise RuntimeError("Incompatible parameter storage type")
    if not ok:
        raise RuntimeError("Revit refused to set the value "
                           "(element may be owned by another user or locked)")