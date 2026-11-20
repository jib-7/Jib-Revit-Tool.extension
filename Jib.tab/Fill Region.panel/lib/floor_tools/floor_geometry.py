# -*- coding: utf-8 -*-
"""Floor footprint extraction (read-only; the Floor is never modified).

Strategy, most reliable first:

1. TOP FACE   - HostObjectUtils.GetTopFaces(floor). A flat or uniformly sloped
                floor has exactly one planar top face whose edge loops are the
                real boundary INCLUDING openings, cut-outs and joins.
2. SKETCH     - if the top is split into several faces (shape editing, split
                face) one outline is taken from the Floor's Sketch profile.
3. FACES      - last resort: every top face becomes its own boundary.

SpatialElementGeometryCalculator / BoundarySegment are Room/Space tools and do
not accept Floors, so they are intentionally not used.
"""
from Autodesk.Revit import DB

from floor_tools import curve_loops, settings
from floor_tools import revit_compat as compat
from floor_tools.utils import FloorToolsError

METHOD_TOP_FACE = "top face"
METHOD_SKETCH = "floor sketch"
METHOD_FACES = "individual top faces"
METHOD_TOPO_SKETCH = "toposolid sketch"
METHOD_TOPO_BOTTOM = "toposolid bottom face"


class FootprintError(FloorToolsError):
    """The Floor's boundary could not be extracted."""


class Footprint(object):
    """Result of the extraction: LoopGroups in model coordinates."""

    def __init__(self, groups, method, warnings=None):
        self.groups = groups
        self.method = method
        self.warnings = warnings or []


# ---------------------------------------------------------------- top faces --
def _iter_solids(geometry):
    for obj in geometry:
        if isinstance(obj, DB.Solid):
            if obj.Volume > 0 and obj.Faces.Size > 0:
                yield obj
        elif isinstance(obj, DB.GeometryInstance):
            for solid in _iter_solids(obj.GetInstanceGeometry()):
                yield solid


def _planar_faces_from_geometry(floor, upward=True):
    """Planar faces looking up (top) or down (bottom), read from the solid geometry."""
    options = DB.Options()
    options.ComputeReferences = False
    options.DetailLevel = DB.ViewDetailLevel.Fine
    geometry = floor.get_Geometry(options)
    faces = []
    if geometry is None:
        return faces
    for solid in _iter_solids(geometry):
        for face in solid.Faces:
            if not isinstance(face, DB.PlanarFace):
                continue
            normal_z = face.FaceNormal.Z
            if (upward and normal_z >= settings.TOP_FACE_MIN_NORMAL_Z) or \
                    ((not upward) and normal_z <= -settings.TOP_FACE_MIN_NORMAL_Z):
                faces.append(face)
    return faces


def _find_top_faces(floor):
    faces = []
    try:
        for reference in DB.HostObjectUtils.GetTopFaces(floor):
            face = floor.GetGeometryObjectFromReference(reference)
            if isinstance(face, DB.PlanarFace):
                faces.append(face)
    except Exception:
        faces = []
    return faces or _planar_faces_from_geometry(floor, True)


def _groups_from_faces(faces):
    groups = []
    for face in faces:
        loops = list(face.GetEdgesAsCurveLoops())
        if not loops:
            continue
        basis = curve_loops.PlaneBasis(face.Origin, face.FaceNormal)
        groups.extend(curve_loops.group_loops(loops, basis))
    return groups


# ------------------------------------------------------------------- sketch --
def _groups_from_sketch(floor, min_len):
    doc = floor.Document
    loops = []
    try:
        for sketch_id in compat.get_sketch_ids(floor):
            sketch = doc.GetElement(sketch_id)
            profile = getattr(sketch, "Profile", None)
            if profile is None:
                continue
            for curve_array in profile:
                curves = [c for c in curve_array]
                if curves:
                    loops.append(curve_loops.assemble_unordered(curves, min_len))
    except FloorToolsError:
        return []
    if not loops:
        return []
    first_point = curve_loops.loop_points(loops[0])[0]
    basis = curve_loops.PlaneBasis(first_point, DB.XYZ.BasisZ)
    return curve_loops.group_loops(loops, basis)


def _apply_transform(groups, transform):
    if transform is not None and not transform.IsIdentity:
        return [curve_loops.transform_group(g, transform) for g in groups]
    return groups


def _extract_toposolid(element, min_len, transform):
    """Toposolid: the top surface is a non-planar mesh, so the plan outline comes
    from the sketch (outer boundary + inner openings). Fallback: a flat bottom face."""
    warnings = []
    groups = _groups_from_sketch(element, min_len)
    method = METHOD_TOPO_SKETCH
    if not groups:
        faces = _planar_faces_from_geometry(element, upward=False)
        if faces:
            groups = _groups_from_faces(faces)
            method = METHOD_TOPO_BOTTOM
            warnings.append("No sketch found; the flat bottom face of the Toposolid was used.")
    if not groups:
        raise FootprintError("The Toposolid outline could not be read (no sketch and no flat bottom face).")
    return Footprint(_apply_transform(groups, transform), method, warnings)


# ---------------------------------------------------------------- public API -
def extract_footprint(floor, min_len, transform=None):
    """Return the Footprint of a Floor or raise FootprintError.

    transform: optional link -> host transform for Floors of linked models. The
    boundary is extracted in the Floor's own document and moved afterwards.
    """
    if compat.is_toposolid(floor):
        return _extract_toposolid(floor, min_len, transform)

    faces = _find_top_faces(floor)
    if not faces:
        raise FootprintError("The Floor has no planar top face (empty or unsupported geometry).")

    warnings = []
    if len(faces) == 1:
        groups, method = _groups_from_faces(faces), METHOD_TOP_FACE
    else:
        groups = _groups_from_sketch(floor, min_len)
        method = METHOD_SKETCH
        if groups:
            warnings.append("The Floor top is split into {} faces (shape edits / split face); "
                            "the sketch outline was used, so openings made by Opening elements "
                            "may be missing.".format(len(faces)))
        else:
            groups, method = _groups_from_faces(faces), METHOD_FACES
            warnings.append("The Floor top is split into {} faces; one Fill Region per face "
                            "was created.".format(len(faces)))
    if not groups:
        raise FootprintError("No boundary loops could be read from the Floor.")
    return Footprint(_apply_transform(groups, transform), method, warnings)
