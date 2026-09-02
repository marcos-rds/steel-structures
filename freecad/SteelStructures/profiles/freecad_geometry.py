# SPDX-License-Identifier: LGPL-2.1-or-later
"""FreeCAD boundary adapter for pure two-dimensional section geometry."""

from __future__ import annotations

import FreeCAD as App
import Part

from .geometry import ArcSegment2D, LineSegment2D, Point2D, SectionGeometry2D, SectionPath2D


class FreeCADSectionGeometryError(RuntimeError):
    """Raised when pure section geometry cannot be converted to Part shapes."""


def point_to_vector(point: Point2D):
    """Map a millimetre Point2D directly into the local FreeCAD XY plane."""
    if not isinstance(point, Point2D):
        raise FreeCADSectionGeometryError("point deve ser Point2D")
    return App.Vector(point.x, point.y, 0.0)


def section_path_to_wire(path: SectionPath2D):
    """Convert one closed line path to a Part.Wire, preserving segment order."""
    if not isinstance(path, SectionPath2D):
        raise FreeCADSectionGeometryError("path deve ser SectionPath2D")
    if not path.closed:
        raise FreeCADSectionGeometryError("somente caminhos fechados podem formar Wire")

    edges = []
    for segment in path.segments:
        if not isinstance(segment, (LineSegment2D, ArcSegment2D)):
            raise FreeCADSectionGeometryError(
                f"segmento ainda não suportado pelo adaptador: {type(segment).__name__}"
            )
        try:
            if isinstance(segment, LineSegment2D):
                edge = Part.makeLine(
                    point_to_vector(segment.start), point_to_vector(segment.end)
                )
            else:
                edge = Part.Arc(
                    point_to_vector(segment.start), point_to_vector(segment.mid),
                    point_to_vector(segment.end),
                ).toShape()
            edges.append(edge)
        except Exception as exc:
            raise FreeCADSectionGeometryError(
                f"não foi possível converter segmento em aresta: {exc}"
            ) from exc
    try:
        wire = Part.Wire(edges)
    except Exception as exc:
        raise FreeCADSectionGeometryError(f"não foi possível criar Wire: {exc}") from exc
    is_closed = getattr(wire, "isClosed", None)
    if callable(is_closed) and not is_closed():
        raise FreeCADSectionGeometryError("Part.Wire resultante não está fechado")
    return wire


def section_geometry_to_face(geometry: SectionGeometry2D):
    """Convert a pure section into one planar Part.Face in local Z=0."""
    if not isinstance(geometry, SectionGeometry2D):
        raise FreeCADSectionGeometryError("geometry deve ser SectionGeometry2D")
    wires = [section_path_to_wire(geometry.outer_path)]
    for path in geometry.inner_paths:
        inner_wire = section_path_to_wire(path)
        reverse = getattr(inner_wire, "reverse", None)
        if (path.signed_area * geometry.outer_path.signed_area > 0.0
                and callable(reverse)):
            reverse()
        wires.append(inner_wire)
    try:
        face = Part.Face(wires[0] if len(wires) == 1 else wires)
    except Exception as exc:
        raise FreeCADSectionGeometryError(f"não foi possível criar Face: {exc}") from exc
    is_null = getattr(face, "isNull", None)
    if callable(is_null) and is_null():
        raise FreeCADSectionGeometryError("Part.Face resultante é nula")
    is_valid = getattr(face, "isValid", None)
    if callable(is_valid) and not is_valid():
        raise FreeCADSectionGeometryError("Part.Face resultante é inválida")
    area = getattr(face, "Area", None)
    if area is not None and float(area) <= 1e-9:
        raise FreeCADSectionGeometryError("Part.Face resultante deve possuir área positiva")
    return face


__all__ = [
    "FreeCADSectionGeometryError", "point_to_vector",
    "section_geometry_to_face", "section_path_to_wire",
]
