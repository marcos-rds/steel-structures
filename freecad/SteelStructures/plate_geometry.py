# SPDX-License-Identifier: LGPL-2.1-or-later
"""Pure local XY geometry for a structural plate's outer contour.

The canonical ring contains an arbitrary number of vertices in millimetres.
Its last edge returns implicitly to the first vertex.  Placement, thickness,
FreeCAD shapes, and the source used to draw the contour belong elsewhere.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from numbers import Real
from typing import Iterable


Point2D = tuple[float, float]
CONTOUR_FORMAT_VERSION = 1
_LINEAR_TOLERANCE = 1e-7  # millimetres; close to FreeCAD's modelling tolerance


class PlateGeometryError(ValueError):
    """An invalid or unsupported plate contour."""


def _point(value: object, index: int) -> Point2D:
    if isinstance(value, (str, bytes)):
        raise PlateGeometryError(f"O vértice {index} deve conter duas coordenadas.")
    try:
        coordinates = tuple(value)
    except TypeError as exc:
        raise PlateGeometryError(f"O vértice {index} deve conter duas coordenadas.") from exc
    if len(coordinates) != 2:
        raise PlateGeometryError(f"O vértice {index} deve conter duas coordenadas.")
    result = []
    for coordinate in coordinates:
        if isinstance(coordinate, bool) or not isinstance(coordinate, Real):
            raise PlateGeometryError(f"As coordenadas do vértice {index} devem ser numéricas.")
        number = float(coordinate)
        if not math.isfinite(number):
            raise PlateGeometryError(f"As coordenadas do vértice {index} devem ser finitas.")
        result.append(0.0 if number == 0.0 else number)
    return result[0], result[1]


def _distance(first: Point2D, second: Point2D) -> float:
    return math.hypot(first[0] - second[0], first[1] - second[1])


def _cross(first: Point2D, second: Point2D, third: Point2D) -> float:
    return ((second[0] - first[0]) * (third[1] - first[1])
            - (second[1] - first[1]) * (third[0] - first[0]))


def _orientation(first: Point2D, second: Point2D, third: Point2D) -> int:
    cross = _cross(first, second, third)
    tolerance = _LINEAR_TOLERANCE * _distance(first, second)
    return 1 if cross > tolerance else -1 if cross < -tolerance else 0


def _on_segment(first: Point2D, point: Point2D, second: Point2D) -> bool:
    return (_orientation(first, second, point) == 0
            and min(first[0], second[0]) - _LINEAR_TOLERANCE <= point[0]
            <= max(first[0], second[0]) + _LINEAR_TOLERANCE
            and min(first[1], second[1]) - _LINEAR_TOLERANCE <= point[1]
            <= max(first[1], second[1]) + _LINEAR_TOLERANCE)


def _intersect(a: Point2D, b: Point2D, c: Point2D, d: Point2D) -> bool:
    ab_c = _orientation(a, b, c)
    ab_d = _orientation(a, b, d)
    cd_a = _orientation(c, d, a)
    cd_b = _orientation(c, d, b)
    if ab_c * ab_d < 0 and cd_a * cd_b < 0:
        return True
    return (ab_c == 0 and _on_segment(a, c, b)
            or ab_d == 0 and _on_segment(a, d, b)
            or cd_a == 0 and _on_segment(c, a, d)
            or cd_b == 0 and _on_segment(c, b, d))


@dataclass(frozen=True)
class PlateContour2D:
    """Immutable simple polygon, with an implicit closing edge and no holes."""

    vertices: tuple[Point2D, ...]

    def __post_init__(self) -> None:
        if isinstance(self.vertices, (str, bytes)):
            raise PlateGeometryError("Os vértices do contorno devem formar uma sequência de pontos.")
        try:
            vertices = tuple(_point(value, index) for index, value in enumerate(self.vertices))
        except TypeError as exc:
            raise PlateGeometryError("Os vértices do contorno devem formar uma sequência de pontos.") from exc
        object.__setattr__(self, "vertices", vertices)
        if len(vertices) < 3:
            raise PlateGeometryError("Um contorno fechado precisa de pelo menos três vértices.")
        for index, first in enumerate(vertices):
            second = vertices[(index + 1) % len(vertices)]
            if _distance(first, second) <= _LINEAR_TOLERANCE:
                raise PlateGeometryError("Vértices consecutivos do contorno coincidem.")

        origin = vertices[0]
        twice_area = math.fsum(
            (first[0] - origin[0]) * (second[1] - origin[1])
            - (second[0] - origin[0]) * (first[1] - origin[1])
            for first, second in self.edges
        )
        width = max(point[0] for point in vertices) - min(point[0] for point in vertices)
        height = max(point[1] for point in vertices) - min(point[1] for point in vertices)
        if not math.isfinite(twice_area) or abs(twice_area) <= max(
            _LINEAR_TOLERANCE ** 2, width * height * 1e-12
        ):
            raise PlateGeometryError("A área do contorno deve ser positiva e não degenerada.")

        count = len(vertices)
        for index in range(count):
            before, current, after = (
                vertices[(index - 1) % count], vertices[index], vertices[(index + 1) % count]
            )
            if _orientation(before, current, after) == 0:
                incoming = (before[0] - current[0], before[1] - current[1])
                outgoing = (after[0] - current[0], after[1] - current[1])
                if incoming[0] * outgoing[0] + incoming[1] * outgoing[1] > 0:
                    raise PlateGeometryError("Arestas adjacentes do contorno se sobrepõem.")
            for other in range(index + 1, count):
                if other in ((index + 1) % count, (index - 1) % count):
                    continue
                if _intersect(vertices[index], vertices[(index + 1) % count],
                              vertices[other], vertices[(other + 1) % count]):
                    raise PlateGeometryError("O contorno possui autointerseção.")

    @classmethod
    def from_points(cls, points: Iterable[object], *, closed: bool = True) -> PlateContour2D:
        """Build a ring; a repeated closing endpoint is accepted and removed.

        Source adapters must explicitly pass ``closed=False`` for an open
        Draft wire.  A vertex list alone does not convey whether its source
        was closed, while a canonical polygon is always closed.
        """
        if not closed:
            raise PlateGeometryError("O contorno de origem está aberto.")
        if isinstance(points, (str, bytes)):
            raise PlateGeometryError("Os vértices do contorno devem formar uma sequência de pontos.")
        try:
            vertices = tuple(_point(value, index) for index, value in enumerate(points))
        except TypeError as exc:
            raise PlateGeometryError("Os vértices do contorno devem formar uma sequência de pontos.") from exc
        if len(vertices) >= 2 and _distance(vertices[0], vertices[-1]) <= _LINEAR_TOLERANCE:
            vertices = vertices[:-1]
        return cls(vertices)

    @property
    def edges(self) -> tuple[tuple[Point2D, Point2D], ...]:
        return tuple((point, self.vertices[(index + 1) % len(self.vertices)])
                     for index, point in enumerate(self.vertices))

    @property
    def signed_area(self) -> float:
        origin = self.vertices[0]
        return 0.5 * math.fsum(
            (first[0] - origin[0]) * (second[1] - origin[1])
            - (second[0] - origin[0]) * (first[1] - origin[1])
            for first, second in self.edges
        )

    @property
    def area(self) -> float:
        return abs(self.signed_area)

    @property
    def orientation(self) -> str:
        return "CCW" if self.signed_area > 0 else "CW"

    def to_data(self) -> str:
        """Serialize version 1 as deterministic JSON with typed segments.

        The envelope reserves inner rings and segment types for later versions.
        Version 1 readers deliberately reject holes and curved segments.
        """
        data = {
            "version": CONTOUR_FORMAT_VERSION,
            "units": "mm",
            "outer": {
                "segments": [
                    {"type": "line", "start": list(first), "end": list(second)}
                    for first, second in self.edges
                ]
            },
            "holes": [],
        }
        return json.dumps(data, sort_keys=True, separators=(",", ":"), allow_nan=False)

    @classmethod
    def from_data(cls, data: str) -> PlateContour2D:
        if not isinstance(data, str):
            raise PlateGeometryError("ContourData deve ser um texto JSON.")
        try:
            payload = json.loads(data)
        except (TypeError, ValueError) as exc:
            raise PlateGeometryError("ContourData contém JSON inválido.") from exc
        if (not isinstance(payload, dict)
                or type(payload.get("version")) is not int
                or payload["version"] != CONTOUR_FORMAT_VERSION):
            raise PlateGeometryError("A versão de ContourData não é suportada.")
        if payload.get("units") != "mm":
            raise PlateGeometryError("As unidades de ContourData devem ser milímetros.")
        if payload.get("holes") != []:
            raise PlateGeometryError("Contornos internos não são suportados na versão 1 de ContourData.")
        outer = payload.get("outer")
        segments = outer.get("segments") if isinstance(outer, dict) else None
        if not isinstance(segments, list) or len(segments) < 3:
            raise PlateGeometryError("ContourData precisa de um contorno externo fechado.")
        edges = []
        for index, segment in enumerate(segments):
            if not isinstance(segment, dict) or segment.get("type") != "line":
                raise PlateGeometryError("O tipo de segmento em ContourData não é suportado.")
            edges.append((_point(segment.get("start"), index),
                          _point(segment.get("end"), index)))
        for index, (_, end) in enumerate(edges):
            if end != edges[(index + 1) % len(edges)][0]:
                raise PlateGeometryError("O contorno externo de ContourData está aberto ou descontínuo.")
        return cls(tuple(start for start, _ in edges))


def serialize_contour(contour: PlateContour2D) -> str:
    return contour.to_data()


def parse_contour(data: str) -> PlateContour2D:
    return PlateContour2D.from_data(data)
