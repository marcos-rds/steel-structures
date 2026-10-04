# SPDX-License-Identifier: LGPL-2.1-or-later
"""Normalize supported Draft outlines into a local StructuralPlate contour."""

from __future__ import annotations

from dataclasses import dataclass
import math

import FreeCAD as App

from .plate_geometry import PlateContour2D


TOLERANCE = 1e-7


@dataclass(frozen=True)
class ResolvedPlateSource:
    contour: PlateContour2D
    placement: object
    containers: tuple[object, ...] = ()


def _number(value):
    return float(getattr(value, "Value", value))


def _proxy_is(source, name):
    try:
        proxy_type = type(source.Proxy)
        return (proxy_type.__name__ == name
                and proxy_type.__module__.startswith("draftobjects.")
                and source.TypeId in ("Part::FeaturePython", "Part::Part2DObjectPython"))
    except (AttributeError, ReferenceError, RuntimeError, TypeError):
        return False


def is_draft_rectangle(source):
    return (_proxy_is(source, "Rectangle")
            and all(hasattr(source, name) for name in ("Length", "Height", "Shape", "Placement")))


def is_draft_wire(source):
    return (_proxy_is(source, "Wire")
            and all(hasattr(source, name) for name in ("Closed", "Shape", "Placement")))


def reference_containers(source):
    """Return parent placement dependencies that Draft child edits do not touch."""
    result = []
    current = source
    while callable(getattr(current, "getParentGeoFeatureGroup", None)):
        current = current.getParentGeoFeatureGroup()
        if current is None:
            break
        if current in result:
            raise ValueError("Ciclo nos contêineres da origem.")
        result.append(current)
    return tuple(result)


def _valid_shape(source):
    shape = source.Shape
    if shape is None or shape.isNull() or not shape.isValid():
        raise ValueError("A origem Draft não possui Shape válida; recompute a origem.")
    return shape


def _linear_edges(shape):
    edges = shape.Edges
    if not edges:
        raise ValueError("A origem Draft não possui arestas.")
    for edge in edges:
        try:
            linear = edge.Curve.isDerivedFrom("Part::GeomLine")
        except (AttributeError, RuntimeError, TypeError):
            linear = getattr(edge.Curve, "TypeId", "") == "Part::GeomLine"
        if not linear or len(edge.Vertexes) != 2:
            raise ValueError("A origem Draft contém curva; somente segmentos retos são aceitos.")
    return edges


def _global_wire_vertices(source, shape):
    wires = shape.Wires
    if len(wires) != 1 or len(shape.Edges) != len(wires[0].Edges):
        raise ValueError("A Wire deve possuir exatamente um contorno externo fechado.")
    wire = wires[0]
    if not wire.isClosed():
        raise ValueError("A Wire Draft deve estar fechada.")
    vertices = wire.OrderedVertexes
    if len(vertices) < 3:
        raise ValueError("A Wire Draft exige ao menos três vértices.")
    # Draft Wire bakes its own Placement into Shape. App::Part placement is not
    # baked, so apply only the accumulated parent transformation here.
    parent = source.getGlobalPlacement().multiply(source.Placement.inverse())
    return tuple(parent.multVec(vertex.Point) for vertex in vertices)


def _frame_from_points(points, preferred_normal=None):
    origin = points[0]
    x_axis = points[1].sub(origin)
    if x_axis.Length <= TOLERANCE:
        raise ValueError("Segmento inicial da origem degenerado.")
    x_axis.normalize()
    derived = None
    for point in points[2:]:
        candidate = x_axis.cross(point.sub(origin))
        if candidate.Length > TOLERANCE:
            candidate.normalize()
            derived = candidate
            break
    if derived is None:
        raise ValueError("O contorno Draft não define um plano com área positiva.")
    normal = derived
    if preferred_normal is not None:
        preferred = App.Vector(preferred_normal)
        if preferred.Length > TOLERANCE:
            preferred.normalize()
            if abs(preferred.dot(derived)) >= 1.0 - 1e-7:
                normal = preferred
    y_axis = normal.cross(x_axis)
    rotation = App.Rotation(x_axis, y_axis, normal, "ZXY")
    placement = App.Placement(origin, rotation)
    inverse = placement.inverse()
    local = []
    for point in points:
        value = inverse.multVec(point)
        if abs(value.z) > max(TOLERANCE, 1e-8 * point.sub(origin).Length):
            raise ValueError("A Wire Draft não é coplanar.")
        local.append((float(value.x), float(value.y)))
    return PlateContour2D.from_points(local), placement


def _rectangle(source):
    if not is_draft_rectangle(source):
        raise ValueError("Selecione um Retângulo Draft válido.")
    length, height = _number(source.Length), _number(source.Height)
    if not all(math.isfinite(value) and value > TOLERANCE for value in (length, height)):
        raise ValueError("O Retângulo Draft possui comprimento ou altura inválidos.")
    for property_name in ("FilletRadius", "ChamferSize"):
        if _number(getattr(source, property_name, 0.0)) != 0.0:
            raise ValueError("Retângulos Draft com arredondamento ou chanfro ainda não são aceitos.")
    if any(_number(getattr(source, name, 1)) != 1 for name in ("Rows", "Columns")):
        raise ValueError("Retângulos Draft subdivididos ainda não são aceitos.")
    shape = _valid_shape(source)
    if len(_linear_edges(shape)) != 4 or len(shape.Wires) != 1:
        raise ValueError("O Retângulo Draft deve conter quatro segmentos retos.")
    placement = source.getGlobalPlacement()
    contour = PlateContour2D(((0.0, 0.0), (length, 0.0),
                              (length, height), (0.0, height)))
    # Catch a stale source Shape before silently using edited properties.
    parent = placement.multiply(source.Placement.inverse())
    actual = [parent.multVec(v.Point) for v in shape.Vertexes]
    expected = [placement.multVec(App.Vector(x, y, 0)) for x, y in contour.vertices]
    if len(actual) != 4 or any(not any(point.sub(item).Length <= 1e-6 for item in actual)
                                   for point in expected):
        raise ValueError("Shape do Retângulo Draft não corresponde às dimensões; recompute a origem.")
    return ResolvedPlateSource(contour, placement, reference_containers(source))


def _wire(source):
    if not is_draft_wire(source):
        raise ValueError("Selecione uma Wire/Polyline Draft válida.")
    if not bool(source.Closed):
        raise ValueError("A Wire/Polyline Draft deve estar fechada.")
    shape = _valid_shape(source)
    _linear_edges(shape)
    points = _global_wire_vertices(source, shape)
    normal = source.getGlobalPlacement().Rotation.multVec(App.Vector(0, 0, 1))
    contour, placement = _frame_from_points(points, normal)
    return ResolvedPlateSource(contour, placement, reference_containers(source))


def resolve_plate_source(source, mode):
    """Return one contour/plane regardless of the supported Draft source type."""
    if mode == "DraftRectangle":
        return _rectangle(source)
    if mode == "DraftWire":
        return _wire(source)
    raise ValueError("Modo de origem da chapa ainda não suportado.")


__all__ = ["ResolvedPlateSource", "is_draft_rectangle", "is_draft_wire",
           "reference_containers", "resolve_plate_source"]
