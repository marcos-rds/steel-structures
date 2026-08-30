# SPDX-License-Identifier: LGPL-2.1-or-later
"""Controlled finite OCC clipping for structural-member end planes."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite, sqrt

from .member_adjustment_geometry import normalized_vector, plane_axial_span


@dataclass(frozen=True)
class PlaneCutResult:
    shape: object
    section_area: float
    pre_start: float
    pre_end: float


@dataclass(frozen=True)
class FiniteClipPlan:
    point: tuple[float, float, float]
    normal: tuple[float, float, float]
    e1: tuple[float, float, float]
    e2: tuple[float, float, float]
    e1_min: float
    e1_max: float
    e2_min: float
    e2_max: float
    depth: float
    margin: float


@dataclass(frozen=True)
class FiniteClipResult:
    shape: object
    keep_solid: object
    clipping_face: object
    plan: FiniteClipPlan


def _dot(a, b):
    return sum(float(x) * float(y) for x, y in zip(a, b))


def _sub(a, b):
    return tuple(float(x) - float(y) for x, y in zip(a, b))


def _cross(a, b):
    return (
        float(a[1]) * float(b[2]) - float(a[2]) * float(b[1]),
        float(a[2]) * float(b[0]) - float(a[0]) * float(b[2]),
        float(a[0]) * float(b[1]) - float(a[1]) * float(b[0]),
    )


def orthonormal_plane_basis(normal, tolerance: float = 1e-7):
    """Return deterministic unit vectors ``(e1, e2, n)`` for one plane."""
    unit = normalized_vector(normal, tolerance)
    if unit is None:
        return None
    seed = (0.0, 0.0, 1.0) if abs(unit[2]) < 0.9 else (1.0, 0.0, 0.0)
    e1 = normalized_vector(_cross(seed, unit), tolerance)
    if e1 is None:
        return None
    e2 = normalized_vector(_cross(unit, e1), tolerance)
    if e2 is None:
        return None
    return e1, e2, unit


def bounding_box_corners(bounds):
    """Return the eight corners of a FreeCAD-like axis-aligned BoundBox."""
    return tuple(
        (float(x), float(y), float(z))
        for x in (bounds.XMin, bounds.XMax)
        for y in (bounds.YMin, bounds.YMax)
        for z in (bounds.ZMin, bounds.ZMax)
    )


def finite_clip_plan(bounds, plane_point, plane_normal, keep_point,
                     tolerance: float = 1e-7) -> FiniteClipPlan | None:
    """Dimension a finite solid that covers the retained side of ``bounds``."""
    basis = orthonormal_plane_basis(plane_normal, tolerance)
    if basis is None:
        return None
    e1, e2, normal = basis
    point = tuple(float(value) for value in plane_point)
    keep = tuple(float(value) for value in keep_point)
    if _dot(_sub(keep, point), normal) < 0.0:
        normal = tuple(-value for value in normal)
        e2 = tuple(-value for value in e2)

    relative = [_sub(corner, point) for corner in bounding_box_corners(bounds)]
    e1_values = [_dot(value, e1) for value in relative]
    e2_values = [_dot(value, e2) for value in relative]
    normal_values = [_dot(value, normal) for value in relative]
    diagonal = sqrt(
        float(bounds.XLength) ** 2
        + float(bounds.YLength) ** 2
        + float(bounds.ZLength) ** 2
    )
    margin = max(tolerance * 100.0, diagonal * 1e-6, 1e-6)
    depth = max(normal_values) + margin
    if depth <= tolerance:
        return None
    return FiniteClipPlan(
        point, normal, e1, e2,
        min(e1_values) - margin, max(e1_values) + margin,
        min(e2_values) - margin, max(e2_values) + margin,
        depth, margin,
    )


def clip_prism_by_plane_finite(part_module, vector_type, prism, plane_point,
                               plane_normal, keep_point,
                               tolerance: float = 1e-7) -> FiniteClipResult | None:
    """Clip with a bounded, well-conditioned solid."""
    plan = finite_clip_plan(
        prism.BoundBox, plane_point, plane_normal, keep_point, tolerance
    )
    if plan is None:
        return None

    def vertex(a, b):
        return vector_type(
            plan.point[0] + a * plan.e1[0] + b * plan.e2[0],
            plan.point[1] + a * plan.e1[1] + b * plan.e2[1],
            plan.point[2] + a * plan.e1[2] + b * plan.e2[2],
        )

    corners = [
        vertex(plan.e1_min, plan.e2_min),
        vertex(plan.e1_max, plan.e2_min),
        vertex(plan.e1_max, plan.e2_max),
        vertex(plan.e1_min, plan.e2_max),
    ]
    wire = part_module.makePolygon(corners + [corners[0]])
    clipping_face = part_module.Face(wire)
    keep_solid = clipping_face.extrude(vector_type(
        plan.normal[0] * plan.depth,
        plan.normal[1] * plan.depth,
        plan.normal[2] * plan.depth,
    ))
    if ((hasattr(keep_solid, "isNull") and keep_solid.isNull())
            or (hasattr(keep_solid, "isValid") and not keep_solid.isValid())
            or not isfinite(float(keep_solid.Volume))
            or float(keep_solid.Volume) <= tolerance):
        return None
    clipped = prism.common(keep_solid)
    if ((hasattr(clipped, "isNull") and clipped.isNull())
            or (hasattr(clipped, "isValid") and not clipped.isValid())
            or not isfinite(float(clipped.Volume)) or float(clipped.Volume) <= tolerance):
        return None
    return FiniteClipResult(clipped, keep_solid, clipping_face, plan)


def global_plane_to_member_local(placement, vector_type, point_global, normal_global,
                                 tolerance: float = 1e-7):
    """Transform a global plane into the local frame driven by ``placement``.

    A point receives the complete inverse Placement.  A normal receives only
    its inverse rotation, represented as the difference of two transformed
    points so this also works with the FreeCAD Placement API and test doubles.
    """
    inverse = placement.inverse()
    point = inverse.multVec(vector_type(*point_global))
    tip = inverse.multVec(vector_type(
        float(point_global[0]) + float(normal_global[0]),
        float(point_global[1]) + float(normal_global[1]),
        float(point_global[2]) + float(normal_global[2]),
    ))
    normal = normalized_vector(
        (tip.x - point.x, tip.y - point.y, tip.z - point.z), tolerance
    )
    if normal is None:
        return None
    return (float(point.x), float(point.y), float(point.z)), normal


def plane_point_at_axis_station(point_local, normal_local, cut_station: float,
                                tolerance: float = 1e-7):
    """Translate a local plane along +Z so it crosses the axis at a station."""
    normal = normalized_vector(normal_local, tolerance)
    if normal is None or abs(normal[2]) <= tolerance:
        return None
    px, py, pz = (float(value) for value in point_local)
    axis_station = pz + (normal[0] * px + normal[1] * py) / normal[2]
    return px, py, pz + float(cut_station) - axis_station


def is_orthogonal_plane(normal_local, angular_tolerance: float = 1e-7) -> bool:
    normal = normalized_vector(normal_local, angular_tolerance)
    return normal is not None and abs(normal[2]) >= 1.0 - angular_tolerance


def _build_plane_cut(part_module, vector_type, section_face, axial_length: float,
                     cut_station: float, normal_local, adjusted_end: str,
                     tolerance: float = 1e-7, point_local=None) -> PlaneCutResult | None:
    """Clip a local-Z prism with a finite solid bounded by the requested plane."""
    normal = normalized_vector(normal_local, tolerance)
    if normal is None or adjusted_end not in ("Start", "End"):
        return None
    bounds = section_face.BoundBox
    span = plane_axial_span(
        cut_station, normal, (bounds.XMin, bounds.XMax), (bounds.YMin, bounds.YMax), tolerance
    )
    if span is None:
        return None
    section_scale = max(float(bounds.XLength), float(bounds.YLength), 1.0)
    overbuild = max(tolerance * 100.0, section_scale * 1e-6)
    # Do not let the oblique cutting plane merely touch the auxiliary prism at
    # a cap extremum: that tangency is numerically fragile in OCC common().
    pre_start = min(0.0, span[0] - overbuild) if adjusted_end == "Start" else 0.0
    pre_end = (max(float(axial_length), span[1] + overbuild)
               if adjusted_end == "End" else float(axial_length))
    if pre_end - pre_start <= tolerance:
        return None

    face = section_face.copy()
    if abs(pre_start) > tolerance:
        face.translate(vector_type(0.0, 0.0, pre_start))
    prism = face.extrude(vector_type(0.0, 0.0, pre_end - pre_start))

    if point_local is None:
        point_local = (0.0, 0.0, float(cut_station))
    point_local = plane_point_at_axis_station(point_local, normal, cut_station, tolerance)
    if point_local is None:
        return None
    point = vector_type(*point_local)

    # The retained side is selected from the nominal opposite end, never from
    # the arbitrary orientation of the reference Face normal.
    keep_z = float(axial_length) if adjusted_end == "Start" else 0.0
    if abs(keep_z - float(cut_station)) <= tolerance:
        keep_z += (1.0 if adjusted_end == "Start" else -1.0) * max(tolerance * 10.0, 1e-6)
    finite = clip_prism_by_plane_finite(
        part_module, vector_type, prism, point_local, normal,
        (0.0, 0.0, keep_z), tolerance,
    )
    if (finite is None or not isfinite(float(section_face.Area))
            or float(section_face.Area) <= tolerance):
        return None
    return PlaneCutResult(finite.shape, float(section_face.Area), pre_start, pre_end)


def build_plane_cut(part_module, vector_type, section_face, axial_length: float,
                    cut_station: float, normal_local, adjusted_end: str,
                    tolerance: float = 1e-7, point_local=None) -> PlaneCutResult | None:
    """Defensively execute the OCC clipping operation during recompute."""
    try:
        return _build_plane_cut(
            part_module, vector_type, section_face, axial_length, cut_station,
            normal_local, adjusted_end, tolerance, point_local,
        )
    except Exception:
        return None
