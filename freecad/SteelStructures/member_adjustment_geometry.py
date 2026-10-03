# SPDX-License-Identifier: LGPL-2.1-or-later
"""Pure longitudinal geometry for structural-member end adjustments."""

from __future__ import annotations

from dataclasses import dataclass
from math import sqrt
from typing import Sequence


DEFAULT_TOLERANCE = 1e-7


@dataclass(frozen=True)
class AxisGeometry:
    start: tuple[float, float, float]
    end: tuple[float, float, float]
    direction: tuple[float, float, float]
    length: float


@dataclass(frozen=True)
class PhysicalExtents:
    start: tuple[float, float, float]
    end: tuple[float, float, float]
    length: float
    valid: bool


def _point(value: Sequence[float]) -> tuple[float, float, float]:
    return (float(value[0]), float(value[1]), float(value[2]))


def _add(a, b):
    return tuple(x + y for x, y in zip(a, b))


def _sub(a, b):
    return tuple(x - y for x, y in zip(a, b))


def _scale(vector, scalar):
    return tuple(value * scalar for value in vector)


def _dot(a, b):
    return sum(x * y for x, y in zip(a, b))


def axis_geometry(start, end, tolerance: float = DEFAULT_TOLERANCE) -> AxisGeometry | None:
    """Return the normalized nominal axis, or ``None`` for a null axis."""
    start_point, end_point = _point(start), _point(end)
    delta = _sub(end_point, start_point)
    length = sqrt(_dot(delta, delta))
    if length <= tolerance:
        return None
    return AxisGeometry(start_point, end_point, _scale(delta, 1.0 / length), length)


def nominal_length(start, end) -> float:
    delta = _sub(_point(end), _point(start))
    return sqrt(_dot(delta, delta))


def intersect_infinite_axis_with_plane(
    start, end, plane_point, plane_normal, tolerance: float = DEFAULT_TOLERANCE
):
    """Intersect an infinite member axis with a plane.

    Returns ``None`` when the axis is null or parallel to the plane. Reversing
    the plane normal produces the same point.
    """
    axis = axis_geometry(start, end, tolerance)
    if axis is None:
        return None
    normal = _point(plane_normal)
    normal_length = sqrt(_dot(normal, normal))
    if normal_length == 0.0:
        return None
    denominator = _dot(normal, axis.direction)
    if abs(denominator) <= tolerance * normal_length:
        return None
    parameter = _dot(normal, _sub(_point(plane_point), axis.start)) / denominator
    return _add(axis.start, _scale(axis.direction, parameter))


def closest_point_on_member_axis(
    start, end, line_point, line_direction, tolerance: float = DEFAULT_TOLERANCE
):
    """Return the member-axis point closest to an infinite reference line."""
    axis = axis_geometry(start, end, tolerance)
    if axis is None:
        return None
    reference_direction = _point(line_direction)
    reference_length = sqrt(_dot(reference_direction, reference_direction))
    if reference_length <= tolerance:
        return None
    reference_direction = _scale(reference_direction, 1.0 / reference_length)
    cosine = _dot(axis.direction, reference_direction)
    denominator = 1.0 - cosine * cosine
    if denominator <= tolerance * tolerance:
        return None
    offset = _sub(axis.start, _point(line_point))
    axis_projection = _dot(axis.direction, offset)
    reference_projection = _dot(reference_direction, offset)
    parameter = (cosine * reference_projection - axis_projection) / denominator
    return _add(axis.start, _scale(axis.direction, parameter))


def plane_axial_span(cut_station, normal, x_bounds, y_bounds,
                     tolerance: float = DEFAULT_TOLERANCE):
    """Return min/max local Z where a plane crosses an XY bounding box."""
    nx, ny, nz = _point(normal)
    normal_length = sqrt(nx * nx + ny * ny + nz * nz)
    if normal_length <= tolerance or abs(nz) <= tolerance * normal_length:
        return None
    heights = [
        float(cut_station) - (nx * x + ny * y) / nz
        for x in (float(x_bounds[0]), float(x_bounds[1]))
        for y in (float(y_bounds[0]), float(y_bounds[1]))
    ]
    return min(heights), max(heights)


def normalized_vector(vector, tolerance: float = DEFAULT_TOLERANCE):
    values = _point(vector)
    length = sqrt(_dot(values, values))
    if length <= tolerance:
        return None
    return _scale(values, 1.0 / length)


def apply_gap(reference_point, direction, adjusted_end: str, gap: float):
    """Move a zero-gap reference inward for a positive gap."""
    sign = 1.0 if adjusted_end == "Start" else -1.0 if adjusted_end == "End" else None
    if sign is None:
        raise ValueError("adjusted_end must be 'Start' or 'End'")
    return _add(_point(reference_point), _scale(_point(direction), sign * float(gap)))


def fixed_reference_point(start, end, adjusted_end: str, reference_offset: float,
                          tolerance: float = DEFAULT_TOLERANCE):
    axis = axis_geometry(start, end, tolerance)
    if axis is None:
        return None
    if adjusted_end == "Start":
        return _add(axis.start, _scale(axis.direction, float(reference_offset)))
    if adjusted_end == "End":
        return _sub(axis.end, _scale(axis.direction, float(reference_offset)))
    raise ValueError("adjusted_end must be 'Start' or 'End'")


def physical_extents(
    start,
    end,
    *,
    mode: str = "None",
    adjusted_end: str = "Start",
    reference_offset: float = 0.0,
    gap: float = 0.0,
    start_extension: float = 0.0,
    end_extension: float = 0.0,
    reference_point=None,
    tolerance: float = DEFAULT_TOLERANCE,
) -> PhysicalExtents:
    """Calculate final physical endpoints, including valid extensions.

    Associative mode consumes an explicit zero-gap reference point already
    obtained from the axis/plane intersection.
    """
    start_point, end_point = _point(start), _point(end)
    axis = axis_geometry(start_point, end_point, tolerance)
    if axis is None:
        return PhysicalExtents(start_point, end_point, 0.0, False)

    start_parameter = -max(0.0, float(start_extension))
    end_parameter = axis.length + max(0.0, float(end_extension))
    if mode == "Fixed" and adjusted_end == "Start":
        start_parameter = float(reference_offset) + float(gap)
    elif mode == "Fixed" and adjusted_end == "End":
        end_parameter = axis.length - float(reference_offset) - float(gap)
    elif mode == "Associative" and reference_point is not None:
        reference_parameter = _dot(_sub(_point(reference_point), axis.start), axis.direction)
        if adjusted_end == "Start":
            start_parameter = reference_parameter + float(gap)
        elif adjusted_end == "End":
            end_parameter = reference_parameter - float(gap)

    length = end_parameter - start_parameter
    effective_start = _add(axis.start, _scale(axis.direction, start_parameter))
    effective_end = _add(axis.start, _scale(axis.direction, end_parameter))
    if length <= tolerance:
        return PhysicalExtents(effective_start, effective_end, 0.0, False)
    return PhysicalExtents(effective_start, effective_end, length, True)
