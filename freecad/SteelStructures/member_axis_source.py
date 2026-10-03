# SPDX-License-Identifier: LGPL-2.1-or-later
"""Resolve a Draft Line into the nominal global axis of a structural member."""

from __future__ import annotations

from dataclasses import dataclass


AXIS_TOLERANCE = 1e-7


@dataclass(frozen=True)
class AxisSourceGeometry:
    source: object
    subelement: str
    start: object
    end: object


def unpack_axis_source(value):
    """Normalize an object or LinkSub value to ``(DraftLine, 'Edge1')``."""
    if value is None:
        return None
    if isinstance(value, (tuple, list)):
        if len(value) < 2 or value[0] is None:
            return None
        source, subelements = value[0], value[1]
        if isinstance(subelements, str):
            subelements = (subelements,)
        if not isinstance(subelements, (tuple, list)) or len(subelements) != 1:
            return None
        subelement = str(subelements[0] or "Edge1")
    else:
        source, subelement = value, "Edge1"
    if subelement != "Edge1":
        return None
    return source, subelement


def is_draft_line(source) -> bool:
    """Return whether *source* is the one-segment Draft Wire used as a Line."""
    try:
        proxy = source.Proxy
        properties = set(source.PropertiesList)
        return (
            source.TypeId == "Part::FeaturePython"
            and proxy is not None
            and proxy.__class__.__name__ == "Wire"
            and proxy.__class__.__module__.startswith("draftobjects.")
            and {"Start", "End", "Shape"}.issubset(properties)
        )
    except (AttributeError, ReferenceError, RuntimeError, TypeError):
        return False


def _parent_placement(source):
    """Return accumulated parent placement, excluding the Draft object's own.

    Draft Wire bakes changes to its own Placement into Start/End.  Container
    placements are not baked, so only the parent transform belongs here.
    """
    global_placement = source.getGlobalPlacement()
    return global_placement.multiply(source.Placement.inverse())


def resolve_axis_source(value, tolerance=AXIS_TOLERANCE):
    """Return ordered global endpoints for one valid Draft Line, or ``None``."""
    unpacked = unpack_axis_source(value)
    if unpacked is None:
        return None
    source, subelement = unpacked
    if not is_draft_line(source):
        return None
    try:
        parent = _parent_placement(source)
        start = parent.multVec(source.Start)
        end = parent.multVec(source.End)
        if start.sub(end).Length <= float(tolerance):
            return None
        shape = source.Shape
        if shape is not None and not shape.isNull() and shape.isValid():
            if len(shape.Edges) != 1:
                return None
            edge = source.getSubObject(subelement)
            curve = edge.Curve
            if (edge is None or edge.ShapeType != "Edge" or edge.isNull()
                    or not edge.isValid() or len(edge.Vertexes) != 2):
                return None
            try:
                linear = curve.isDerivedFrom("Part::GeomLine")
            except (AttributeError, RuntimeError, TypeError):
                linear = getattr(curve, "TypeId", "") == "Part::GeomLine"
            if not linear:
                return None
        return AxisSourceGeometry(source, subelement, start, end)
    except (AttributeError, ReferenceError, RuntimeError, TypeError, ValueError):
        return None


def axis_source_from_selection(selection_ex):
    """Accept exactly one whole Draft Line or its natural Edge1 selection."""
    items = tuple(selection_ex or ())
    if len(items) != 1:
        return None
    item = items[0]
    source = getattr(item, "Object", None)
    names = tuple(getattr(item, "SubElementNames", ()) or ())
    if names not in ((), ("Edge1",)):
        return None
    link = (source, ["Edge1"])
    return link if resolve_axis_source(link) is not None else None


__all__ = [
    "AXIS_TOLERANCE", "AxisSourceGeometry", "axis_source_from_selection",
    "is_draft_line", "resolve_axis_source", "unpack_axis_source",
]
