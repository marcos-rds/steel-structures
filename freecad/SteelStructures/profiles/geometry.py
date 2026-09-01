# SPDX-License-Identifier: LGPL-2.1-or-later
"""Pure two-dimensional geometry for structural profile sections.

Coordinates use millimetres in the local section plane: X is the flange-width
direction, Y is the web-height direction, and a future local Z axis is the
member longitudinal axis.  This module deliberately has no 3D placement,
rotation, insertion-point, FreeCAD, Part or UI concerns.

The sharp-cornered parallel-flange I contour preserves the historical member
approximation, while catalog-backed tapered I and U sections retain their
nominal circular transitions. Equal-leg angles use one six-segment L contour
located about the published centroid.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from typing import Protocol, runtime_checkable

from .models import ProfileDefinition


class SectionGeometryMode(str, Enum):
    """Physical representation strategy, independent from catalog data."""

    DETAILED = "Detailed"
    SIMPLIFIED = "Simplified"


def normalize_section_geometry_mode(value) -> SectionGeometryMode:
    if isinstance(value, SectionGeometryMode):
        return value
    try:
        return SectionGeometryMode(str(value))
    except ValueError as exc:
        raise SectionGeometryError(f"modo geométrico de seção inválido: {value!r}") from exc


def section_geometry_mode_has_effect(profile: ProfileDefinition) -> bool:
    """Whether this typed profile has removable manufacturing radii."""
    return (profile.geometry_type, profile.geometry_variant) in {
        ("i_section", "tapered_flange"),
        ("channel_section", "tapered_flange"),
        ("cold_formed_channel", "stiffened_u"),
    }


class SectionGeometryError(ValueError):
    """Raised when section dimensions or path topology are invalid."""


class UnsupportedSectionGeometryError(SectionGeometryError):
    """Raised when a profile's geometry type/variant has no builder yet."""


class GeometryTemporarilyUnavailableError(UnsupportedSectionGeometryError):
    """Raised when catalog traceability explicitly blocks geometric use."""


def geometry_is_released(profile: ProfileDefinition) -> bool:
    """Return the single catalog-backed geometric release decision."""
    return getattr(profile, "geometry_status", "released") == "released"


def _finite(value: float, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise SectionGeometryError(f"{name} deve ser numérico")
    result = float(value)
    if not math.isfinite(result):
        raise SectionGeometryError(f"{name} deve ser finito")
    return result


@dataclass(frozen=True)
class Point2D:
    """A finite point in the local section plane, expressed in millimetres."""

    x: float
    y: float

    def __post_init__(self) -> None:
        object.__setattr__(self, "x", _finite(self.x, "x"))
        object.__setattr__(self, "y", _finite(self.y, "y"))


@runtime_checkable
class PathSegment2D(Protocol):
    """Minimal interface shared by straight and future curved path segments."""

    @property
    def start(self) -> Point2D: ...

    @property
    def end(self) -> Point2D: ...


@dataclass(frozen=True)
class LineSegment2D:
    """A non-zero straight segment between two finite points."""

    start: Point2D
    end: Point2D

    def __post_init__(self) -> None:
        if not isinstance(self.start, Point2D) or not isinstance(self.end, Point2D):
            raise SectionGeometryError("segmentos devem usar Point2D")
        if self.start == self.end:
            raise SectionGeometryError("segmento não pode possuir comprimento zero")

    @property
    def length(self) -> float:
        return math.hypot(self.end.x - self.start.x, self.end.y - self.start.y)


@dataclass(frozen=True)
class ArcSegment2D:
    """Circular arc with an explicit centre and sweep direction."""

    start: Point2D
    end: Point2D
    center: Point2D
    clockwise: bool = False

    def __post_init__(self) -> None:
        radii = (
            math.hypot(self.start.x - self.center.x, self.start.y - self.center.y),
            math.hypot(self.end.x - self.center.x, self.end.y - self.center.y),
        )
        if min(radii) <= 0.0 or not math.isclose(*radii, rel_tol=1e-9, abs_tol=1e-7):
            raise SectionGeometryError("arco deve possuir raio positivo e extremidades concêntricas")

    @property
    def radius(self) -> float:
        return math.hypot(self.start.x - self.center.x, self.start.y - self.center.y)

    @property
    def start_angle(self) -> float:
        return math.atan2(self.start.y - self.center.y, self.start.x - self.center.x)

    @property
    def sweep(self) -> float:
        delta = math.atan2(self.end.y - self.center.y, self.end.x - self.center.x) - self.start_angle
        if self.clockwise:
            return delta - 2.0 * math.pi if delta >= 0.0 else delta
        return delta + 2.0 * math.pi if delta <= 0.0 else delta

    @property
    def mid(self) -> Point2D:
        angle = self.start_angle + self.sweep / 2.0
        return Point2D(
            self.center.x + self.radius * math.cos(angle),
            self.center.y + self.radius * math.sin(angle),
        )

    @property
    def length(self) -> float:
        return abs(self.sweep) * self.radius

    def sampled_points(self, count: int = 12) -> tuple[Point2D, ...]:
        return tuple(
            Point2D(
                self.center.x + self.radius * math.cos(self.start_angle + self.sweep * index / count),
                self.center.y + self.radius * math.sin(self.start_angle + self.sweep * index / count),
            )
            for index in range(1, count + 1)
        )


@dataclass(frozen=True)
class SectionPath2D:
    """An ordered, continuous path with explicit closure state."""

    segments: tuple[PathSegment2D, ...]
    closed: bool

    def __post_init__(self) -> None:
        segments = tuple(self.segments)
        object.__setattr__(self, "segments", segments)
        if not segments:
            raise SectionGeometryError("caminho deve possuir ao menos um segmento")
        for index, segment in enumerate(segments):
            if not isinstance(segment, PathSegment2D):
                raise SectionGeometryError("segmento não implementa PathSegment2D")
            if index and segments[index - 1].end != segment.start:
                raise SectionGeometryError("caminho possui descontinuidade")
        if self.closed and segments[-1].end != segments[0].start:
            raise SectionGeometryError("caminho fechado não retorna ao ponto inicial")
        if not self.closed and segments[-1].end == segments[0].start:
            raise SectionGeometryError("caminho geometricamente fechado deve declarar closed=True")

    @property
    def signed_area(self) -> float:
        """Return shoelace signed area; CCW closed paths are positive."""
        if not self.closed:
            raise SectionGeometryError("área requer caminho fechado")
        total = 0.0
        for segment in self.segments:
            if isinstance(segment, ArcSegment2D):
                theta1 = segment.start_angle
                theta2 = theta1 + segment.sweep
                radius = segment.radius
                total += 0.5 * (
                    radius * segment.center.x * (math.sin(theta2) - math.sin(theta1))
                    - radius * segment.center.y * (math.cos(theta2) - math.cos(theta1))
                    + radius * radius * segment.sweep
                )
            else:
                total += 0.5 * (
                    segment.start.x * segment.end.y - segment.end.x * segment.start.y
                )
        return total

    @property
    def area(self) -> float:
        return abs(self.signed_area)


@dataclass(frozen=True)
class SectionBounds2D:
    """Axis-aligned bounds in the local section plane, in millimetres."""

    min_x: float
    max_x: float
    min_y: float
    max_y: float

    def __post_init__(self) -> None:
        for name in ("min_x", "max_x", "min_y", "max_y"):
            object.__setattr__(self, name, _finite(getattr(self, name), name))
        if self.min_x >= self.max_x or self.min_y >= self.max_y:
            raise SectionGeometryError("bounds devem possuir largura e altura positivas")

    @property
    def width(self) -> float:
        return self.max_x - self.min_x

    @property
    def height(self) -> float:
        return self.max_y - self.min_y


@dataclass(frozen=True)
class SectionGeometry2D:
    """Deterministic mathematical section geometry, not a CAD shape."""

    geometry_type: str
    geometry_variant: str
    outer_path: SectionPath2D
    inner_paths: tuple[SectionPath2D, ...]
    bounds: SectionBounds2D
    origin: Point2D
    dimension_stations: tuple[tuple[str, float], ...] = ()

    def __post_init__(self) -> None:
        if not self.geometry_type or not self.geometry_variant:
            raise SectionGeometryError("tipo e variante geométrica são obrigatórios")
        if not isinstance(self.outer_path, SectionPath2D) or not self.outer_path.closed:
            raise SectionGeometryError("contorno externo deve ser um SectionPath2D fechado")
        inner_paths = tuple(self.inner_paths)
        object.__setattr__(self, "inner_paths", inner_paths)
        if any(not isinstance(path, SectionPath2D) or not path.closed for path in inner_paths):
            raise SectionGeometryError("contornos internos devem ser caminhos fechados")
        if not isinstance(self.bounds, SectionBounds2D):
            raise SectionGeometryError("bounds deve ser SectionBounds2D")
        if not isinstance(self.origin, Point2D):
            raise SectionGeometryError("origin deve ser Point2D")
        stations = tuple((str(name), _finite(value, name))
                         for name, value in self.dimension_stations)
        if len({name for name, _value in stations}) != len(stations):
            raise SectionGeometryError("estações de dimensão devem possuir nomes únicos")
        object.__setattr__(self, "dimension_stations", stations)

    @property
    def signed_area(self) -> float:
        return self.outer_path.signed_area - sum(path.area for path in self.inner_paths)

    @property
    def area(self) -> float:
        return abs(self.signed_area)


def _closed_polygon(points: tuple[Point2D, ...]) -> SectionPath2D:
    if len(points) < 3:
        raise SectionGeometryError("polígono requer ao menos três pontos")
    segments = tuple(
        LineSegment2D(point, points[(index + 1) % len(points)])
        for index, point in enumerate(points)
    )
    return SectionPath2D(segments=segments, closed=True)


def build_parallel_flange_i_section(
    *, d: float, bf: float, tw: float, tf: float
) -> SectionGeometry2D:
    """Build one sharp-cornered, doubly symmetric parallel-flange I section."""
    d = _finite(d, "d")
    bf = _finite(bf, "bf")
    tw = _finite(tw, "tw")
    tf = _finite(tf, "tf")
    if min(d, bf, tw, tf) <= 0.0:
        raise SectionGeometryError("d, bf, tw e tf devem ser positivos")
    if tw >= bf:
        raise SectionGeometryError("tw deve ser menor que bf")
    if 2.0 * tf >= d:
        raise SectionGeometryError("2*tf deve ser menor que d")

    half_b = bf / 2.0
    half_d = d / 2.0
    half_tw = tw / 2.0
    inner_y = half_d - tf
    # Historical member order: lower-left start, then counter-clockwise.
    points = (
        Point2D(-half_b, -half_d),
        Point2D(half_b, -half_d),
        Point2D(half_b, -inner_y),
        Point2D(half_tw, -inner_y),
        Point2D(half_tw, inner_y),
        Point2D(half_b, inner_y),
        Point2D(half_b, half_d),
        Point2D(-half_b, half_d),
        Point2D(-half_b, inner_y),
        Point2D(-half_tw, inner_y),
        Point2D(-half_tw, -inner_y),
        Point2D(-half_b, -inner_y),
    )
    outer_path = _closed_polygon(points)
    return SectionGeometry2D(
        geometry_type="i_section",
        geometry_variant="parallel_flange",
        outer_path=outer_path,
        inner_paths=(),
        bounds=SectionBounds2D(-half_b, half_b, -half_d, half_d),
        origin=Point2D(0.0, 0.0),
    )


def build_tapered_flange_i_section(
    *, d: float, bf: float, tw: float, tf: float, flange_angle: float,
    r1: float, r2: float, tl: float,
) -> SectionGeometry2D:
    """Build Gerdau's nominal Revit tapered-flange I section.

    The section is doubly symmetric about its centroid. ``tf`` is the vertical
    thickness at the explicit BIM station ``tl`` measured inward from either
    flange tip; it is deliberately not interpreted as a normal distance.
    """
    values = {
        name: _finite(value, name) for name, value in (
            ("d", d), ("bf", bf), ("tw", tw), ("tf", tf),
            ("flange_angle", flange_angle), ("r1", r1), ("r2", r2),
            ("tl", tl),
        )
    }
    d, bf, tw, tf = (values[name] for name in ("d", "bf", "tw", "tf"))
    flange_angle, r1, r2, tl = (
        values[name] for name in ("flange_angle", "r1", "r2", "tl")
    )
    if min(d, bf, tw, tf, r1, r2, tl) <= 0.0:
        raise SectionGeometryError("dimensões, raios e TL do perfil I devem ser positivos")
    if tw >= bf or 2.0 * tf >= d or not 0.0 < flange_angle < 45.0:
        raise SectionGeometryError("proporções inválidas para perfil I de mesas inclinadas")
    if tl >= (bf - tw) / 2.0:
        raise SectionGeometryError("TL deve ficar entre a ponta da mesa e a alma")

    angle = math.radians(flange_angle)
    slope = math.tan(angle)
    sine, cosine = math.sin(angle), math.cos(angle)
    half_b, half_d, half_tw = bf / 2.0, d / 2.0, tw / 2.0
    x_tf = half_b - tl
    intercept = half_d - tf - slope * x_tf

    root_line_x = half_tw + r1 - r1 * sine
    root_center_x = half_tw + r1
    root_line_y = slope * root_line_x + intercept
    root_center_y = root_line_y - r1 * cosine
    toe_line_x = half_b - r2 + r2 * sine
    toe_center_x = half_b - r2
    toe_line_y = slope * toe_line_x + intercept
    toe_center_y = toe_line_y + r2 * cosine
    if not half_tw < root_line_x < toe_line_x < half_b:
        raise SectionGeometryError("raios do perfil I não cabem entre alma e extremidade")
    if not 0.0 < root_center_y < toe_center_y < half_d:
        raise SectionGeometryError("faces internas do perfil I excedem os limites externos")

    left_bottom = Point2D(-half_b, -half_d)
    right_bottom = Point2D(half_b, -half_d)
    bottom_toe = Point2D(half_b, -toe_center_y)
    bottom_toe_line = Point2D(toe_line_x, -toe_line_y)
    bottom_root_line = Point2D(root_line_x, -root_line_y)
    bottom_web = Point2D(half_tw, -root_center_y)
    top_web = Point2D(half_tw, root_center_y)
    top_root_line = Point2D(root_line_x, root_line_y)
    top_toe_line = Point2D(toe_line_x, toe_line_y)
    top_toe = Point2D(half_b, toe_center_y)
    right_top = Point2D(half_b, half_d)
    first_half = (
        LineSegment2D(left_bottom, right_bottom),
        LineSegment2D(right_bottom, bottom_toe),
        ArcSegment2D(bottom_toe, bottom_toe_line,
                     Point2D(toe_center_x, -toe_center_y)),
        LineSegment2D(bottom_toe_line, bottom_root_line),
        ArcSegment2D(bottom_root_line, bottom_web,
                     Point2D(root_center_x, -root_center_y), True),
        LineSegment2D(bottom_web, top_web),
        ArcSegment2D(top_web, top_root_line,
                     Point2D(root_center_x, root_center_y), True),
        LineSegment2D(top_root_line, top_toe_line),
        ArcSegment2D(top_toe_line, top_toe,
                     Point2D(toe_center_x, toe_center_y)),
        LineSegment2D(top_toe, right_top),
    )

    def rotate(point):
        return Point2D(-point.x, -point.y)

    def rotate_segment(segment):
        if isinstance(segment, ArcSegment2D):
            return ArcSegment2D(
                rotate(segment.start), rotate(segment.end),
                rotate(segment.center), segment.clockwise,
            )
        return LineSegment2D(rotate(segment.start), rotate(segment.end))

    segments = first_half + tuple(rotate_segment(segment) for segment in first_half)
    return SectionGeometry2D(
        geometry_type="i_section",
        geometry_variant="tapered_flange",
        outer_path=SectionPath2D(segments, True),
        inner_paths=(),
        bounds=SectionBounds2D(-half_b, half_b, -half_d, half_d),
        origin=Point2D(0.0, 0.0),
        dimension_stations=(("tf_left", -x_tf), ("tf_right", x_tf)),
    )


def build_simplified_tapered_flange_i_section(
    *, d: float, bf: float, tw: float, tf: float, flange_angle: float,
    tl: float,
) -> SectionGeometry2D:
    """Build the approved tapered I datum with sharp manufacturing corners."""
    values = {name: _finite(value, name) for name, value in (
        ("d", d), ("bf", bf), ("tw", tw), ("tf", tf),
        ("flange_angle", flange_angle), ("tl", tl),
    )}
    d, bf, tw, tf = (values[name] for name in ("d", "bf", "tw", "tf"))
    flange_angle, tl = values["flange_angle"], values["tl"]
    if min(d, bf, tw, tf, tl) <= 0.0 or tw >= bf or 2.0 * tf >= d:
        raise SectionGeometryError("proporções inválidas para perfil I de mesas inclinadas")
    if not 0.0 < flange_angle < 45.0 or tl >= (bf - tw) / 2.0:
        raise SectionGeometryError("inclinação ou TL inválido para perfil I")
    half_b, half_d, half_tw = bf / 2.0, d / 2.0, tw / 2.0
    x_tf = half_b - tl
    slope = math.tan(math.radians(flange_angle))
    intercept = half_d - tf - slope * x_tf
    inner_web = slope * half_tw + intercept
    inner_tip = slope * half_b + intercept
    points = (
        Point2D(-half_b, -half_d), Point2D(half_b, -half_d),
        Point2D(half_b, -inner_tip), Point2D(half_tw, -inner_web),
        Point2D(half_tw, inner_web), Point2D(half_b, inner_tip),
        Point2D(half_b, half_d), Point2D(-half_b, half_d),
        Point2D(-half_b, inner_tip), Point2D(-half_tw, inner_web),
        Point2D(-half_tw, -inner_web), Point2D(-half_b, -inner_tip),
    )
    return SectionGeometry2D(
        "i_section", "tapered_flange", _closed_polygon(points), (),
        SectionBounds2D(-half_b, half_b, -half_d, half_d), Point2D(0.0, 0.0),
        (("tf_left", -x_tf), ("tf_right", x_tf)),
    )


def build_equal_angle_section(
    *, b: float, t: float, centroid_x: float
) -> SectionGeometry2D:
    """Build one sharp-cornered equal-leg angle about its catalog centroid."""
    b = _finite(b, "b")
    t = _finite(t, "t")
    centroid_x = _finite(centroid_x, "centroid_x")
    if b <= 0.0 or t <= 0.0:
        raise SectionGeometryError("b e t devem ser positivos")
    if t >= b:
        raise SectionGeometryError("t deve ser menor que b")
    if centroid_x <= 0.0 or centroid_x >= b:
        raise SectionGeometryError("centroid_x deve estar no interior das abas")

    x_bar = centroid_x
    points = (
        Point2D(-x_bar, -x_bar),
        Point2D(b - x_bar, -x_bar),
        Point2D(b - x_bar, t - x_bar),
        Point2D(t - x_bar, t - x_bar),
        Point2D(t - x_bar, b - x_bar),
        Point2D(-x_bar, b - x_bar),
    )
    return SectionGeometry2D(
        geometry_type="equal_angle",
        geometry_variant="equal_leg",
        outer_path=_closed_polygon(points),
        inner_paths=(),
        bounds=SectionBounds2D(-x_bar, b - x_bar, -x_bar, b - x_bar),
        origin=Point2D(0.0, 0.0),
    )


def build_standard_tee_section(
    *, d: float, bf: float, tw: float, tf: float
) -> SectionGeometry2D:
    """Build one sharp-cornered nominal T section about its own centroid."""
    d, bf, tw, tf = (
        _finite(value, name)
        for name, value in (("d", d), ("bf", bf), ("tw", tw), ("tf", tf))
    )
    if min(d, bf, tw, tf) <= 0.0:
        raise SectionGeometryError("d, bf, tw e tf devem ser positivos")
    if tw >= bf:
        raise SectionGeometryError("tw deve ser menor que bf")
    if tf >= d:
        raise SectionGeometryError("tf deve ser menor que d")

    web_height = d - tf
    web_area = tw * web_height
    flange_area = bf * tf
    area = web_area + flange_area
    centroid_y = (
        web_area * web_height / 2.0
        + flange_area * (web_height + tf / 2.0)
    ) / area
    half_tw, half_b = tw / 2.0, bf / 2.0

    def point(x, y):
        return Point2D(x, y - centroid_y)

    points = (
        point(-half_tw, 0.0),
        point(half_tw, 0.0),
        point(half_tw, web_height),
        point(half_b, web_height),
        point(half_b, d),
        point(-half_b, d),
        point(-half_b, web_height),
        point(-half_tw, web_height),
    )
    return SectionGeometry2D(
        geometry_type="tee_section",
        geometry_variant="standard_tee",
        outer_path=_closed_polygon(points),
        inner_paths=(),
        bounds=SectionBounds2D(-half_b, half_b, -centroid_y, d - centroid_y),
        origin=Point2D(0.0, 0.0),
        dimension_stations=(("centroid_from_top", d - centroid_y),),
    )


def build_tapered_flange_channel_section(
    *, d: float, bf: float, tw: float, tf: float, flange_angle: float,
    r1: float, r2: float, centroid_x: float,
) -> SectionGeometry2D:
    """Build Gerdau's nominal tapered-flange U section about its centroid.

    ``tf`` is imposed at TL=(bf-tw)/2 from the flange tip.  The physical
    datum x=0 is the external rear web face and the opening points toward +X.
    """
    values = {
        name: _finite(value, name) for name, value in (
            ("d", d), ("bf", bf), ("tw", tw), ("tf", tf),
            ("flange_angle", flange_angle), ("r1", r1), ("r2", r2),
            ("centroid_x", centroid_x),
        )
    }
    d, bf, tw, tf = (values[name] for name in ("d", "bf", "tw", "tf"))
    flange_angle, r1, r2, centroid_x = (
        values[name] for name in ("flange_angle", "r1", "r2", "centroid_x")
    )
    if min(d, bf, tw, tf, r1, r2, centroid_x) <= 0.0:
        raise SectionGeometryError("dimensões, raios e centroide do perfil U devem ser positivos")
    if tw >= bf or 2.0 * tf >= d or not 0.0 < flange_angle < 45.0:
        raise SectionGeometryError("proporções inválidas para perfil U de mesas inclinadas")
    if centroid_x >= bf:
        raise SectionGeometryError("centroid_x deve estar entre a alma traseira e a abertura")

    angle = math.radians(flange_angle)
    slope = math.tan(angle)
    cosine = math.cos(angle)
    sine = math.sin(angle)
    half_d = d / 2.0
    tl = (bf - tw) / 2.0
    x_tf = bf - tl
    intercept = half_d - tf - slope * x_tf

    root_line_x = tw + r1 - r1 * sine
    root_center_x = tw + r1
    root_line_y = slope * root_line_x + intercept
    root_center_y = root_line_y - r1 * cosine
    toe_line_x = bf - r2 + r2 * sine
    toe_center_x = bf - r2
    toe_line_y = slope * toe_line_x + intercept
    toe_center_y = toe_line_y + r2 * cosine
    if not tw < root_line_x < toe_line_x < bf:
        raise SectionGeometryError("raios do perfil U não cabem entre alma e extremidade")
    if not 0.0 < root_center_y < toe_center_y < half_d:
        raise SectionGeometryError("faces internas do perfil U excedem os limites externos")

    def point(x, y):
        return Point2D(x - centroid_x, y)

    rear_bottom = point(0.0, -half_d)
    outer_bottom_tip = point(bf, -half_d)
    bottom_toe = point(bf, -toe_center_y)
    bottom_toe_line = point(toe_line_x, -toe_line_y)
    bottom_root_line = point(root_line_x, -root_line_y)
    bottom_root = point(tw, -root_center_y)
    top_root = point(tw, root_center_y)
    top_root_line = point(root_line_x, root_line_y)
    top_toe_line = point(toe_line_x, toe_line_y)
    top_toe = point(bf, toe_center_y)
    outer_top_tip = point(bf, half_d)
    rear_top = point(0.0, half_d)

    segments = (
        LineSegment2D(rear_bottom, outer_bottom_tip),
        LineSegment2D(outer_bottom_tip, bottom_toe),
        ArcSegment2D(bottom_toe, bottom_toe_line, point(toe_center_x, -toe_center_y)),
        LineSegment2D(bottom_toe_line, bottom_root_line),
        ArcSegment2D(bottom_root_line, bottom_root, point(root_center_x, -root_center_y), True),
        LineSegment2D(bottom_root, top_root),
        ArcSegment2D(top_root, top_root_line, point(root_center_x, root_center_y), True),
        LineSegment2D(top_root_line, top_toe_line),
        ArcSegment2D(top_toe_line, top_toe, point(toe_center_x, toe_center_y)),
        LineSegment2D(top_toe, outer_top_tip),
        LineSegment2D(outer_top_tip, rear_top),
        LineSegment2D(rear_top, rear_bottom),
    )
    return SectionGeometry2D(
        geometry_type="channel_section",
        geometry_variant="tapered_flange",
        outer_path=SectionPath2D(segments, True),
        inner_paths=(),
        bounds=SectionBounds2D(-centroid_x, bf - centroid_x, -half_d, half_d),
        origin=Point2D(0.0, 0.0),
        dimension_stations=(("web_back_x", -centroid_x),
                            ("web_inner_x", tw - centroid_x),
                            ("flange_tip_x", bf - centroid_x)),
    )


def build_simplified_tapered_flange_channel_section(
    *, d: float, bf: float, tw: float, tf: float, flange_angle: float,
    centroid_x: float,
) -> SectionGeometry2D:
    """Build a sharp-corner U while retaining its approved flange taper."""
    values = {name: _finite(value, name) for name, value in (
        ("d", d), ("bf", bf), ("tw", tw), ("tf", tf),
        ("flange_angle", flange_angle), ("centroid_x", centroid_x),
    )}
    d, bf, tw, tf = (values[name] for name in ("d", "bf", "tw", "tf"))
    flange_angle, centroid_x = values["flange_angle"], values["centroid_x"]
    if min(d, bf, tw, tf, centroid_x) <= 0.0 or tw >= bf or 2.0 * tf >= d:
        raise SectionGeometryError("proporções inválidas para perfil U de mesas inclinadas")
    if not 0.0 < flange_angle < 45.0 or centroid_x >= bf:
        raise SectionGeometryError("inclinação ou centroide inválido para perfil U")
    half_d = d / 2.0
    tl = (bf - tw) / 2.0
    x_tf = bf - tl
    slope = math.tan(math.radians(flange_angle))
    intercept = half_d - tf - slope * x_tf
    inner_root = slope * tw + intercept
    inner_tip = slope * bf + intercept
    point = lambda x, y: Point2D(x - centroid_x, y)
    points = (
        point(0.0, -half_d), point(bf, -half_d), point(bf, -inner_tip),
        point(tw, -inner_root), point(tw, inner_root), point(bf, inner_tip),
        point(bf, half_d), point(0.0, half_d),
    )
    return SectionGeometry2D(
        "channel_section", "tapered_flange", _closed_polygon(points), (),
        SectionBounds2D(-centroid_x, bf - centroid_x, -half_d, half_d),
        Point2D(0.0, 0.0),
        (("web_back_x", -centroid_x), ("web_inner_x", tw - centroid_x),
         ("flange_tip_x", bf - centroid_x)),
    )


def build_section_geometry(
    profile: ProfileDefinition, mode: SectionGeometryMode | str = SectionGeometryMode.DETAILED,
) -> SectionGeometry2D:
    """Dispatch a typed profile by geometry type and variant."""
    if getattr(profile, "geometry_status", "released") == "pending_technical_review":
        raise GeometryTemporarilyUnavailableError(
            "geometria temporariamente indisponível: inconsistência entre fontes técnicas Gerdau"
        )
    mode = normalize_section_geometry_mode(mode)
    key = (profile.geometry_type, profile.geometry_variant)
    if key == ("i_section", "parallel_flange"):
        names = ("d", "bf", "tw", "tf")
        builder = build_parallel_flange_i_section
    elif key == ("i_section", "tapered_flange"):
        if mode is SectionGeometryMode.SIMPLIFIED:
            names = ("d", "bf", "tw", "tf", "flange_angle", "tl")
            builder = build_simplified_tapered_flange_i_section
        else:
            names = ("d", "bf", "tw", "tf", "flange_angle", "r1", "r2", "tl")
            builder = build_tapered_flange_i_section
    elif key == ("equal_angle", "equal_leg"):
        names = ("b", "t")
        builder = build_equal_angle_section
    elif key == ("tee_section", "standard_tee"):
        names = ("d", "bf", "tw", "tf")
        builder = build_standard_tee_section
    elif key == ("channel_section", "tapered_flange"):
        if mode is SectionGeometryMode.SIMPLIFIED:
            names = ("d", "bf", "tw", "tf", "flange_angle")
            builder = build_simplified_tapered_flange_channel_section
        else:
            names = ("d", "bf", "tw", "tf", "flange_angle", "r1", "r2")
            builder = build_tapered_flange_channel_section
    elif key == ("cold_formed_channel", "stiffened_u"):
        from .ue_section import build_simplified_ue_section, build_ue_section
        names = ("bw", "bf", "D", "t", "ri")
        builder = (build_simplified_ue_section
                   if mode is SectionGeometryMode.SIMPLIFIED else build_ue_section)
    else:
        raise UnsupportedSectionGeometryError(
            f"geometria de seção ainda não suportada: {key[0]!r} / {key[1]!r}"
        )
    try:
        dimensions = {name: profile.geometry[name] for name in names}
        if key == ("equal_angle", "equal_leg"):
            dimensions["centroid_x"] = profile.centroid["x"]
        elif key == ("channel_section", "tapered_flange"):
            dimensions["centroid_x"] = profile.centroid["x"]
    except KeyError as exc:
        raise SectionGeometryError(f"dimensão ausente: {exc.args[0]}") from exc
    return builder(**dimensions)


__all__ = [
    "LineSegment2D", "PathSegment2D", "Point2D", "SectionBounds2D",
    "SectionGeometry2D", "SectionGeometryError", "SectionPath2D",
    "GeometryTemporarilyUnavailableError", "geometry_is_released",
    "SectionGeometryMode", "normalize_section_geometry_mode",
    "section_geometry_mode_has_effect",
    "UnsupportedSectionGeometryError", "ArcSegment2D", "build_equal_angle_section",
    "build_standard_tee_section",
    "build_tapered_flange_i_section",
    "build_simplified_tapered_flange_i_section",
    "build_tapered_flange_channel_section",
    "build_simplified_tapered_flange_channel_section",
    "build_parallel_flange_i_section", "build_section_geometry",
]
