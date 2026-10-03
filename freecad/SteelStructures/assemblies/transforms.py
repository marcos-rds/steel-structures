"""Orthogonal section transforms, applied before extrusion, never Placement.

Canonical insertion references are resolved BEFORE transforming/reordering paths.
Scalar dimension stations describe the canonical profile and are not propagated.
"""
from dataclasses import dataclass, replace
import math
from ..profiles.geometry import (Point2D, LineSegment2D, ArcSegment2D,
                                SectionPath2D, SectionBounds2D)
from ..profiles.insertion import section_insertion_references


@dataclass(frozen=True)
class SectionTransform:
    """R(angle) @ mirror-X. Reflection changes handedness explicitly."""
    rotation_degrees: float = 0.0
    reflect_x: bool = False

    def __post_init__(self):
        if (isinstance(self.rotation_degrees, bool)
                or not isinstance(self.rotation_degrees, (int, float))
                or not math.isfinite(self.rotation_degrees)
                or not isinstance(self.reflect_x, bool)):
            raise ValueError("Transformação de seção inválida.")
        object.__setattr__(self, "rotation_degrees", float(self.rotation_degrees) % 360.)

    @property
    def determinant(self):
        return -1 if self.reflect_x else 1

    @property
    def matrix(self):
        angle = math.radians(self.rotation_degrees)
        c, s = math.cos(angle), math.sin(angle)
        c, s = (0. if abs(x) < 1e-14 else x for x in (c, s))
        return ((c*self.determinant, -s), (s*self.determinant, c))

    def point(self, point):
        (a, b), (c, d) = self.matrix
        return Point2D(a*point.x+b*point.y, c*point.x+d*point.y)


def transform_path(path, transform):
    result = []
    for segment in path.segments:
        start, end = transform.point(segment.start), transform.point(segment.end)
        if isinstance(segment, ArcSegment2D):
            result.append(ArcSegment2D(start, end, transform.point(segment.center),
                                      segment.clockwise ^ transform.reflect_x))
        elif isinstance(segment, LineSegment2D):
            result.append(LineSegment2D(start, end))
        else:
            raise ValueError("Tipo de segmento não suportado.")
    if transform.reflect_x:
        result = [ArcSegment2D(s.end, s.start, s.center, not s.clockwise)
                  if isinstance(s, ArcSegment2D) else LineSegment2D(s.end, s.start)
                  for s in reversed(result)]
    return SectionPath2D(tuple(result), path.closed)


def _bounds(path):
    points = []
    for segment in path.segments:
        points.extend((segment.start, segment.end))
        if isinstance(segment, ArcSegment2D):
            for angle in (0., math.pi/2, math.pi, 3*math.pi/2):
                travel = ((segment.start_angle-angle) if segment.clockwise
                          else (angle-segment.start_angle)) % (2*math.pi)
                if travel <= abs(segment.sweep)+1e-12:
                    points.append(Point2D(segment.center.x+segment.radius*math.cos(angle),
                                          segment.center.y+segment.radius*math.sin(angle)))
    return SectionBounds2D(min(p.x for p in points), max(p.x for p in points),
                           min(p.y for p in points), max(p.y for p in points))


def transform_section(geometry, transform):
    """Return transformed geometry AND semantic insertion references together."""
    references = tuple(replace(r, point=transform.point(r.point))
                       for r in section_insertion_references(geometry))
    outer = transform_path(geometry.outer_path, transform)
    transformed = replace(geometry, outer_path=outer,
                          inner_paths=tuple(transform_path(p, transform) for p in geometry.inner_paths),
                          origin=transform.point(geometry.origin), bounds=_bounds(outer),
                          dimension_stations=())
    bounds = transformed.bounds
    references = tuple(replace(r, point=Point2D(
        (bounds.min_x+bounds.max_x)/2., (bounds.min_y+bounds.max_y)/2.))
        if r.id == "envelope_center" else r for r in references)
    return transformed, references
