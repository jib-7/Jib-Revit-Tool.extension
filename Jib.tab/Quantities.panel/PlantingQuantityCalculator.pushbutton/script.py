# -*- coding: utf-8 -*-
"""Planting Quantity Calculator (Revit 2026, pyRevit)

For every Fill Region in the ACTIVE document (links are ignored):
  1. Measures the true geometric area (square metres).
  2. Rounds it half-up to a whole m2 and writes it to 'Net Area'.
  3. Reads 'Planting Density' from the Fill Region TYPE (never modified).
  4. Writes 'Planting Quantity' = Net Area x Planting Density.
"""
__title__ = "Planting Quantity\nCalculator"
__author__ = "Your Name"

import math

from pyrevit import revit, DB, forms, script

# ----------------------------------------------------------------------
# Settings
# ----------------------------------------------------------------------
P_NET_AREA = "Net Area"
P_DENSITY = "Planting Density"
P_QUANTITY = "Planting Quantity"
ROUND_EPSILON = 1e-6   # protects 5.4999999999 (float noise) from rounding down

doc = revit.doc
output = script.get_output()


# ----------------------------------------------------------------------
# Small helpers
# ----------------------------------------------------------------------
def id_value(element_id):
    """ElementId number. Revit 2024+ uses .Value, older uses .IntegerValue."""
    try:
        return element_id.Value
    except AttributeError:
        return element_id.IntegerValue


def id_link(element_id):
    try:
        return output.linkify(element_id, title=str(id_value(element_id)))
    except Exception:
        return str(id_value(element_id))


def round_half_up(value):
    """Standard rounding: x.49 -> down, x.50 -> up (NOT Python's banker's round)."""
    return int(math.floor(value + 0.5 + ROUND_EPSILON))


def sqft_to_sqm(value):
    return DB.UnitUtils.ConvertFromInternalUnits(value, DB.UnitTypeId.SquareMeters)


def sqm_to_sqft(value):
    return DB.UnitUtils.ConvertToInternalUnits(value, DB.UnitTypeId.SquareMeters)


def fmt(value, digits=2):
    return "-" if value is None else "{0:.{1}f}".format(value, digits)


# ----------------------------------------------------------------------
# Area calculation
# ----------------------------------------------------------------------
def _polygon_points(loop):
    pts = []
    for curve in loop:
        tess = curve.Tessellate()
        for i in range(len(tess) - 1):
            pts.append(tess[i])
    return pts


def _shoelace(points, normal):
    """Unsigned polygon area in the plane with the given normal."""
    total = DB.XYZ(0, 0, 0)
    n = len(points)
    for i in range(n):
        total = total + points[i].CrossProduct(points[(i + 1) % n])
    return abs(total.DotProduct(normal)) / 2.0


def _point_in_polygon(pt, points, normal):
    # project onto 2 axes of the plane
    ax = normal.CrossProduct(DB.XYZ.BasisZ)
    if ax.GetLength() < 1e-9:
        ax = DB.XYZ.BasisX
    ax = ax.Normalize()
    ay = normal.CrossProduct(ax).Normalize()
    px, py = pt.DotProduct(ax), pt.DotProduct(ay)
    inside = False
    n = len(points)
    j = n - 1
    for i in range(n):
        xi, yi = points[i].DotProduct(ax), points[i].DotProduct(ay)
        xj, yj = points[j].DotProduct(ax), points[j].DotProduct(ay)
        if (yi > py) != (yj > py) and px < (xj - xi) * (py - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


def area_by_extrusion(loops, normal):
    """Exact area (ft2): extrude the loops into a thin solid and read a planar face.
    Holes (loops inside loops) are handled automatically by Revit."""
    solid = DB.GeometryCreationUtilities.CreateExtrusionGeometry(loops, normal, 1.0)
    best = None
    for face in solid.Faces:
        if isinstance(face, DB.PlanarFace):
            if abs(face.FaceNormal.DotProduct(normal)) > 0.999:
                best = face.Area
                break
    if best is None:
        raise Exception("No planar face found on temporary solid")
    return best


def area_by_polygons(loops, normal):
    """Fallback (ft2): tessellated polygons, nested loops alternate add/subtract."""
    polys = [_polygon_points(l) for l in loops]
    total = 0.0
    for i, poly in enumerate(polys):
        depth = 0
        for j, other in enumerate(polys):
            if i != j and _point_in_polygon(poly[0], other, normal):
                depth += 1
        a = _shoelace(poly, normal)
        total += a if depth % 2 == 0 else -a
    return total


def get_area_sqft(fill_region):
    """Returns (area_sqft, method). Raises if the region has no usable boundary."""
    loops = fill_region.GetBoundaries()
    if loops is None or loops.Count == 0:
        raise Exception("Fill Region has no boundary loops")
    normal = None
    for loop in loops:
        try:
            normal = loop.GetPlane().Normal
            break
        except Exception:
            continue
    if normal is None:
        raise Exception("Could not determine the sketch plane of the boundary")
    try:
        return area_by_extrusion(loops, normal), "exact"
    except Exception:
        return area_by_polygons(loops, normal), "tessellated"


# ----------------------------------------------------------------------
# Parameter helpers
# ----------------------------------------------------------------------
def get_param(element, name):
    """Parameter by name on the given element (instance or type element)."""
    if element is None:
        return None
    return element.LookupParameter(name)


def get_region_type(region):
    return doc.GetElement(region.GetTypeId())


def check_param_writable(p, name, kind):
    """kind: 'area' or 'number'. Returns an error string or None."""
    if p is None:
        return "Parameter '{0}' is missing or not bound to this element's category".format(name)
    if p.IsReadOnly:
        return "Parameter '{0}' is read-only".format(name)
    dt = p.Definition.GetDataType()
    if kind == "area":
        if dt != DB.SpecTypeId.Area or p.StorageType != DB.StorageType.Double:
            return "Parameter '{0}' must be of type Area (found {1})".format(
                name, DB.LabelUtils.GetLabelForSpec(dt))
    else:
        ok_double = dt == DB.SpecTypeId.Number and p.StorageType == DB.StorageType.Double
        ok_int = dt == DB.SpecTypeId.Int.Integer and p.StorageType == DB.StorageType.Integer
        if not (ok_double or ok_int):
            return "Parameter '{0}' must be Number or Integer (found {1}, storage {2})".format(
                name, DB.LabelUtils.GetLabelForSpec(dt), p.StorageType)
    return None


def read_density(p):
    """Returns (value, error)."""
    if p is None:
        return None, "Type parameter '{0}' is missing or not bound as a Type parameter".format(P_DENSITY)
    if p.StorageType not in (DB.StorageType.Double, DB.StorageType.Integer):
        return None, "Parameter '{0}' has an incompatible storage type ({1})".format(
            P_DENSITY, p.StorageType)
    if not p.HasValue:
        return None, "Planting Density is empty on the Fill Region type"
    if p.StorageType == DB.StorageType.Integer:
        value = float(p.AsInteger())
    else:
        value = p.AsDouble()
    if math.isnan(value) or math.isinf(value):
        return None, "Planting Density is invalid"
    if value < 0:
        return None, "Planting Density is negative ({0})".format(value)
    if value == 0:
        return None, "Planting Density is 0 (enter a value greater than 0)"
    return value, None


def write_number(p, value):
    """Writes a whole number into a Number (double) or Integer parameter."""
    if p.StorageType == DB.StorageType.Integer:
        ok = p.Set(int(value))
    else:
        ok = p.Set(float(value))
    if not ok:
        raise Exception("Revit refused to set parameter '{0}'".format(p.Definition.Name))


# ----------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------
def main():
    if doc is None or doc.IsFamilyDocument:
        forms.alert("Open a Revit project (not a family) first.", exitscript=True)

    regions = list(DB.FilteredElementCollector(doc)
                   .OfClass(DB.FilledRegion)
                   .WhereElementIsNotElementType()
                   .ToElements())

    if not regions:
        forms.alert("No Fill Regions were found in the active document.", exitscript=True)

    # ---- Pre-flight: abort before touching anything if a parameter is
    # missing on EVERY Fill Region (i.e. a project-wide setup problem).
    for name, is_type in ((P_NET_AREA, False), (P_DENSITY, True), (P_QUANTITY, False)):
        if is_type:
            found = any(get_param(get_region_type(r), name) is not None for r in regions)
        else:
            found = any(get_param(r, name) is not None for r in regions)
        if not found:
            forms.alert(
                "Parameter '{0}' was not found on any Fill Region{1}.\n\n"
                "Check that the shared parameter is loaded in the project and bound "
                "as a {2} parameter to the category of Fill Regions.\n\n"
                "Nothing was changed.".format(
                    name, " type" if is_type else "",
                    "TYPE" if is_type else "INSTANCE"), exitscript=True)

    rows = []
    n_ok = n_skip = n_err = 0
    updates = []   # (region, net_area_m2, quantity) validated and ready to write

    # ---- Phase 1: calculate and validate (read-only)
    for r in regions:
        rtype = get_region_type(r)
        info = {"id": r.Id, "type": rtype.Name if rtype else "-", "area": None, "net": None, "dens": None, "qty": None,
                "status": "", "kind": ""}
        rows.append(info)
        try:
            p_net = get_param(r, P_NET_AREA)
            p_den = get_param(rtype, P_DENSITY)   # TYPE parameter
            p_qty = get_param(r, P_QUANTITY)

            err = (check_param_writable(p_net, P_NET_AREA, "area")
                   or check_param_writable(p_qty, P_QUANTITY, "number"))
            if err:
                info["status"], info["kind"] = err, "skip"
                continue

            area_sqft, method = get_area_sqft(r)
            area_m2 = sqft_to_sqm(area_sqft)
            info["area"] = area_m2
            if math.isnan(area_m2) or area_m2 <= 0:
                info["status"], info["kind"] = "Zero or invalid area", "skip"
                continue

            net = round_half_up(area_m2)
            info["net"] = net
            if net <= 0:
                info["status"] = "Area rounds to 0 m2 (too small)"
                info["kind"] = "skip"
                continue

            dens, derr = read_density(p_den)
            if derr:
                info["status"], info["kind"] = derr, "skip"
                continue
            info["dens"] = dens

            qty = round_half_up(net * dens)
            info["qty"] = qty
            if method != "exact":
                info["status"] = "Updated (area from tessellated fallback)"
            updates.append((r, net, qty, info))
        except Exception as ex:
            info["status"], info["kind"] = "Error: {0}".format(ex), "error"

    # ---- Phase 2: write (single transaction, one sub-transaction per element)
    if updates:
        with revit.Transaction("Planting Quantity Calculator"):
            for r, net, qty, info in updates:
                st = DB.SubTransaction(doc)
                st.Start()
                try:
                    get_param(r, P_NET_AREA).Set(sqm_to_sqft(net))
                    write_number(get_param(r, P_QUANTITY), qty)
                    st.Commit()
                    info["kind"] = "ok"
                    if not info["status"]:
                        info["status"] = "Updated"
                except Exception as ex:
                    st.RollBack()
                    info["status"] = "Update failed: {0}".format(ex)
                    info["kind"] = "error"

    for info in rows:
        if info["kind"] == "ok":
            n_ok += 1
        elif info["kind"] == "skip":
            n_skip += 1
        else:
            n_err += 1

    # ---- Report
    output.print_md("# Planting Quantity Calculator")
    output.print_md("**Total Fill Regions checked:** {0}  \n"
                    "**Updated successfully:** {1}  \n"
                    "**Skipped:** {2}  \n"
                    "**Errors:** {3}".format(len(rows), n_ok, n_skip, n_err))

    table = []
    for info in rows:
        table.append([
            id_link(info["id"]),
            info["type"],
            fmt(info["area"]),
            "-" if info["net"] is None else info["net"],
            "-" if info["dens"] is None else fmt(info["dens"], 0 if float(info["dens"]).is_integer() else 2),
            "-" if info["qty"] is None or info["kind"] != "ok" else info["qty"],
            info["status"],
        ])
    output.print_table(
        table_data=table,
        title="Details",
        columns=["Element ID", "Fill Region Type", "Actual Area (m2)", "Net Area (m2)",
                 "Planting Density", "Planting Quantity", "Status"])


main()
