# SPDX-License-Identifier: LGPL-2.1-or-later
"""Frames for interactive plate creation and explicitly selected planar faces."""

from __future__ import annotations

from dataclasses import dataclass
import math
import re

import FreeCAD as App
import Part


_FACE_NAME = re.compile(r"(?:^|\.)Face[1-9][0-9]*$")
_PICK_COMPONENT = re.compile(r"(?:^|\.)(?:Face|Edge|Vertex)[1-9][0-9]*$")


@dataclass(frozen=True)
class PlateFaceReference:
    parent: object
    subelement: str


def _face_name(value):
    return isinstance(value, str) and _FACE_NAME.search(value) is not None


def placement_from_points(first, second, third):
    """Use the first edge as local X and its ordered cross product as +Z.

    Return None until the points define a nondegenerate plane. The frame does
    not depend on the camera, Work Plane, hover, or snap subelement type.
    """
    origin = App.Vector(first)
    x_axis = App.Vector(second).sub(origin)
    length = x_axis.Length
    if length <= 1e-7:
        return None
    normal = x_axis.cross(App.Vector(third).sub(origin))
    if normal.Length / length <= 1e-7:
        return None
    x_axis.normalize()
    normal.normalize()
    y_axis = normal.cross(x_axis)
    return App.Placement(origin, App.Rotation(x_axis, y_axis, normal, "ZXY"))


def selected_plane_face(selection, document):
    """Accept exactly one selected FaceN, including nested App::Part paths."""
    items = tuple(selection or ())
    if len(items) != 1:
        return None
    item = items[0]
    parent = getattr(item, "Object", None)
    names = tuple(getattr(item, "SubElementNames", ()) or ())
    subobjects = tuple(getattr(item, "SubObjects", ()) or ())
    if (parent is None or getattr(parent, "Document", None) is not document
            or len(names) != 1 or not _face_name(names[0])
            or (subobjects and (len(subobjects) != 1
                                or getattr(subobjects[0], "ShapeType", None) != "Face"))):
        return None
    return PlateFaceReference(parent, names[0])


def point_from_pick_info(info, document):
    """Return a native 3D hit only with a resolvable document subelement."""
    if (not isinstance(info, dict)
            or not isinstance(info.get("Component"), str)
            or _PICK_COMPONENT.search(info["Component"]) is None):
        return None
    parent = info.get("ParentObject")
    if parent is None:
        name = info.get("Object")
        parent = document.getObject(name) if isinstance(name, str) else None
    if parent is None or getattr(parent, "Document", None) is not document:
        return None
    try:
        coordinates = tuple(float(info[name]) for name in ("x", "y", "z"))
    except (KeyError, TypeError, ValueError):
        return None
    if not all(math.isfinite(value) for value in coordinates):
        return None
    return App.Vector(*coordinates)


def screen_coordinates(screen_position):
    """Read the Coin event's viewport pixels without Qt/Y/HiDPI conversion."""
    try:
        values = (screen_position.getValue()
                  if hasattr(screen_position, "getValue") else screen_position)
        coordinates = tuple(int(value) for value in values)
    except (AttributeError, TypeError, ValueError):
        return None
    return coordinates if len(coordinates) == 2 else None


def preselection_pick(selection, document):
    """Read FreeCAD's current hover entity and its world-space picked point.

    An empty SelectionObject raises on ``Object``; inspect its document/name
    before accessing that property.
    """
    try:
        if selection is None or selection.DocumentName != document.Name:
            return None, None
        names = tuple(selection.SubElementNames or ())
        if len(names) != 1 or _PICK_COMPONENT.search(names[0]) is None:
            return None, None
        parent = selection.Object
        if parent is None or parent.Document is not document:
            return None, None
        points = tuple(selection.PickedPoints or ())
        if len(points) != 1:
            return None, None
        point = App.Vector(points[0])
        if not all(math.isfinite(value) for value in (point.x, point.y, point.z)):
            return None, None
    except (AttributeError, ReferenceError, RuntimeError, TypeError, ValueError):
        return None, None
    info = {"Document": document.Name, "Object": parent.Name,
            "Component": names[0], "ParentObject": parent,
            "SubName": names[0], "x": point.x, "y": point.y, "z": point.z}
    return info, point


def view_pick(view, screen_position, document):
    """Use FreeCAD's frontmost native pick, as Draft's face-alignment tool does."""
    try:
        position = screen_coordinates(screen_position)
        if position is None:
            return None, None
        info = view.getObjectInfo(position)
    except (AttributeError, ReferenceError, RuntimeError, TypeError, ValueError):
        return None, None
    point = point_from_pick_info(info, document)
    return info, point


def placement_from_face(reference):
    """Return a world Placement with deterministic +Z face normal.

    Part.getShape returns geometry in ``parent`` coordinates. Its own
    Placement is already included, while ancestor App::Part placements are
    not; apply just those ancestors once before constructing the frame.
    """
    if reference is None or not _face_name(reference.subelement):
        raise ValueError("Selecione uma face plana válida.")
    try:
        face = Part.getShape(reference.parent, reference.subelement,
                             needSubElement=True, noElementMap=True)
        if (face.isNull() or face.ShapeType != "Face" or not face.isValid()
                or face.Area <= 1e-12):
            raise ValueError("A referência não contém uma face válida.")
        face = face.copy()
        parent = reference.parent
        ancestors = parent.getGlobalPlacement().multiply(parent.Placement.inverse())
        face.Placement = ancestors.multiply(face.Placement)
    except (AttributeError, ReferenceError, RuntimeError, TypeError, ValueError) as exc:
        raise ValueError("Não foi possível resolver a face selecionada.") from exc
    if not face.Surface.isDerivedFrom("Part::GeomPlane"):
        raise ValueError("A face selecionada deve ser plana.")

    normal = App.Vector(face.normalAt(0, 0))
    if normal.Length <= 1e-12:
        raise ValueError("A face não possui normal válida.")
    normal.normalize()
    origin = App.Vector(face.CenterOfMass)

    # Project global +X, then +Y if necessary. The axes and BRep face
    # orientation determine the result; the current Draft Work Plane does not.
    for axis in (App.Vector(1, 0, 0), App.Vector(0, 1, 0)):
        x_axis = axis.sub(App.Vector(normal).multiply(axis.dot(normal)))
        if x_axis.Length > 1e-8:
            x_axis.normalize()
            break
    y_axis = normal.cross(x_axis)
    rotation = App.Rotation(x_axis, y_axis, normal, "ZXY")
    return App.Placement(origin, rotation)


__all__ = ["PlateFaceReference", "selected_plane_face", "placement_from_points",
           "point_from_pick_info", "screen_coordinates", "preselection_pick",
           "view_pick", "placement_from_face"]
