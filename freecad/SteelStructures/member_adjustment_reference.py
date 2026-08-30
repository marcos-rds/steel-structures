# SPDX-License-Identifier: LGPL-2.1-or-later
"""FreeCAD-facing helpers for associative member end references."""

from __future__ import annotations

from dataclasses import dataclass
import re


_SUBELEMENT_NAME = re.compile(r"^(?:Face|Edge)[1-9][0-9]*$")


@dataclass(frozen=True)
class PlaneReference:
    point_global: tuple[float, float, float]
    normal_global: tuple[float, float, float]


@dataclass(frozen=True)
class LinearReference:
    point_global: tuple[float, float, float]
    direction_global: tuple[float, float, float]


def unpack_link_sub(value):
    """Return ``(object, 'FaceN')`` only for one explicit face reference."""
    if not value or not isinstance(value, (tuple, list)) or len(value) < 2:
        return None
    reference = value[0]
    subelements = value[1]
    if isinstance(subelements, str):
        subelements = (subelements,)
    if reference is None or not isinstance(subelements, (tuple, list)) or len(subelements) != 1:
        return None
    subelement = str(subelements[0])
    if not _SUBELEMENT_NAME.fullmatch(subelement):
        return None
    return reference, subelement


def _is_planar(face) -> bool:
    surface = getattr(face, "Surface", None)
    if surface is None:
        return False
    try:
        if surface.isDerivedFrom("Part::GeomPlane"):
            return True
    except (AttributeError, RuntimeError, TypeError):
        pass
    return getattr(surface, "TypeId", "") == "Part::GeomPlane"


def plane_reference_from_link(value) -> PlaneReference | None:
    """Resolve a LinkSub face into one global plane.

    ``DocumentObject.getSubObject()`` is deliberately the single coordinate
    path used here: FreeCAD returns the selected subshape with the object's
    accumulated placement already applied. The returned face is therefore
    sampled directly and no Placement is multiplied a second time.
    """
    unpacked = unpack_link_sub(value)
    if unpacked is None:
        return None
    reference, subelement = unpacked
    if not subelement.startswith("Face"):
        return None
    try:
        shape = reference.Shape
        if (shape is None or (hasattr(shape, "isNull") and shape.isNull())
                or (hasattr(shape, "isValid") and not shape.isValid())):
            return None
        face = reference.getSubObject(subelement)
        if (face is None or getattr(face, "ShapeType", "") != "Face"
                or (hasattr(face, "isNull") and face.isNull())
                or (hasattr(face, "isValid") and not face.isValid())
                or not _is_planar(face)):
            return None
        parameters = tuple(float(value) for value in face.ParameterRange)
        if len(parameters) != 4:
            return None
        u = (parameters[0] + parameters[1]) * 0.5
        v = (parameters[2] + parameters[3]) * 0.5
        point = face.valueAt(u, v)
        normal = face.normalAt(u, v)
        if float(normal.Length) == 0.0:
            return None
        return PlaneReference(
            (float(point.x), float(point.y), float(point.z)),
            (float(normal.x), float(normal.y), float(normal.z)),
        )
    except (AttributeError, IndexError, ReferenceError, RuntimeError, TypeError, ValueError):
        return None


def _is_linear(edge) -> bool:
    curve = getattr(edge, "Curve", None)
    if curve is None:
        return False
    try:
        if curve.isDerivedFrom("Part::GeomLine"):
            return True
    except (AttributeError, RuntimeError, TypeError):
        pass
    return getattr(curve, "TypeId", "") == "Part::GeomLine"


def linear_reference_from_link(value, tolerance: float = 1e-7) -> LinearReference | None:
    """Resolve one explicit straight EdgeN as its infinite global line."""
    unpacked = unpack_link_sub(value)
    if unpacked is None:
        return None
    reference, subelement = unpacked
    if not subelement.startswith("Edge"):
        return None
    try:
        shape = reference.Shape
        if (shape is None or (hasattr(shape, "isNull") and shape.isNull())
                or (hasattr(shape, "isValid") and not shape.isValid())):
            return None
        edge = reference.getSubObject(subelement)
        if (edge is None or getattr(edge, "ShapeType", "") != "Edge"
                or (hasattr(edge, "isNull") and edge.isNull())
                or (hasattr(edge, "isValid") and not edge.isValid())
                or not _is_linear(edge)):
            return None
        first = float(edge.FirstParameter)
        last = float(edge.LastParameter)
        start = edge.valueAt(first)
        end = edge.valueAt(last)
        direction = (
            float(end.x) - float(start.x),
            float(end.y) - float(start.y),
            float(end.z) - float(start.z),
        )
        length = sum(value * value for value in direction) ** 0.5
        if length <= tolerance:
            return None
        return LinearReference(
            (float(start.x), float(start.y), float(start.z)),
            tuple(value / length for value in direction),
        )
    except (AttributeError, ReferenceError, RuntimeError, TypeError, ValueError):
        return None


def _dependencies(obj):
    try:
        return tuple(obj.OutList)
    except (AttributeError, RuntimeError, TypeError):
        return ()


def would_create_adjustment_cycle(target, reference) -> bool:
    """Return whether adding ``target -> reference`` would create a cycle."""
    if target is None or reference is None:
        return False
    if target is reference:
        return True
    visited = set()
    pending = [reference]
    while pending:
        current = pending.pop()
        marker = id(current)
        if marker in visited:
            continue
        visited.add(marker)
        if current is target:
            return True
        pending.extend(_dependencies(current))
    return False
