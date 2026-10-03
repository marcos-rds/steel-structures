# SPDX-License-Identifier: LGPL-2.1-or-later
"""Pure mathematical contract for a parametric structural grid.

All coordinates are local ``(x, y, z)`` tuples in the XY plane.  The X axis
*family* is located at constant X coordinates and its lines run parallel to
geometric Y.  Conversely, the Y axis family is located at constant Y
coordinates and its lines run parallel to geometric X.

Intersections are stored in deterministic X-major order: every Y position for
the first X position, followed by every Y position for the next X position.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from numbers import Real
from typing import Iterable, Sequence


Point3D = tuple[float, float, float]


@dataclass(frozen=True)
class GridAxis:
    """One grid axis, distinguishing its named family from line direction."""

    family: str
    index: int
    identifier: str
    start: Point3D
    end: Point3D

    @property
    def geometric_direction(self) -> str:
        """Return the local geometric direction of the line."""
        return "Y" if self.family == "X" else "X"


@dataclass(frozen=True)
class GridIntersection:
    """Intersection between one member of each grid-axis family."""

    x_index: int
    y_index: int
    point: Point3D


@dataclass(frozen=True)
class GridLabelAnchor:
    """Render-independent axis identification anchored in local coordinates."""

    text: str
    family: str
    axis_index: int
    side: str
    anchor_point_local: Point3D


@dataclass(frozen=True)
class GridGeometry:
    """Immutable result of a structural-grid calculation."""

    x_positions: tuple[float, ...]
    y_positions: tuple[float, ...]
    x_axes: tuple[GridAxis, ...]
    y_axes: tuple[GridAxis, ...]
    intersections: tuple[GridIntersection, ...]
    overall_length_x: float
    overall_length_y: float
    displayed_length_x: float
    displayed_length_y: float


def grid_label_anchors(
    geometry: GridGeometry,
    label_position: str,
    label_offset: Real,
) -> tuple[GridLabelAnchor, ...]:
    """Return semantic label anchors at axis ends, independent of rendering."""
    if label_position not in ("Start", "End", "Both"):
        raise ValueError("Label position must be Start, End or Both.")
    offset = validate_extension(label_offset, "Label offset")
    anchors = []
    for axis in geometry.x_axes:
        if label_position in ("Start", "Both"):
            anchors.append(GridLabelAnchor(
                axis.identifier, axis.family, axis.index, "bottom",
                (axis.start[0], axis.start[1] - offset, axis.start[2]),
            ))
        if label_position in ("End", "Both"):
            anchors.append(GridLabelAnchor(
                axis.identifier, axis.family, axis.index, "top",
                (axis.end[0], axis.end[1] + offset, axis.end[2]),
            ))
    for axis in geometry.y_axes:
        if label_position in ("Start", "Both"):
            anchors.append(GridLabelAnchor(
                axis.identifier, axis.family, axis.index, "left",
                (axis.start[0] - offset, axis.start[1], axis.start[2]),
            ))
        if label_position in ("End", "Both"):
            anchors.append(GridLabelAnchor(
                axis.identifier, axis.family, axis.index, "right",
                (axis.end[0] + offset, axis.end[1], axis.end[2]),
            ))
    return tuple(anchors)


def _finite_number(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise TypeError(f"{name} must be a numeric value, not {type(value).__name__}.")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{name} must be finite.")
    return result


def validate_spacings(values: Iterable[Real], axis_name: str) -> tuple[float, ...]:
    """Validate and copy an ordered spacing iterable into an immutable tuple."""
    if isinstance(values, (str, bytes)):
        raise TypeError(f"{axis_name} spacings must be an iterable of numbers.")
    try:
        supplied = tuple(values)
    except TypeError as exc:
        raise TypeError(f"{axis_name} spacings must be an iterable of numbers.") from exc

    validated = []
    for index, value in enumerate(supplied):
        spacing = _finite_number(value, f"{axis_name} spacing at index {index}")
        if spacing <= 0.0:
            raise ValueError(
                f"{axis_name} spacing at index {index} must be greater than zero."
            )
        validated.append(spacing)
    return tuple(validated)


def validate_extension(value: Real, name: str) -> float:
    """Return a finite, non-negative extension as a float."""
    extension = _finite_number(value, name)
    if extension < 0.0:
        raise ValueError(f"{name} must be greater than or equal to zero.")
    return extension


def accumulated_positions(spacings: Iterable[Real]) -> tuple[float, ...]:
    """Return ordered cumulative positions, always beginning at zero."""
    values = validate_spacings(spacings, "Axis")
    positions = [0.0]
    total = 0.0
    for index, spacing in enumerate(values):
        total += spacing
        if not math.isfinite(total):
            raise ValueError(
                f"Accumulated position overflow at spacing index {index}; "
                "the running total must remain finite."
            )
        positions.append(total)
    return tuple(positions)


def _validate_index(index: object) -> int:
    if isinstance(index, bool) or not isinstance(index, int):
        raise TypeError("Axis index must be an integer.")
    if index < 0:
        raise ValueError("Axis index must be greater than or equal to zero.")
    return index


def numeric_axis_identifier(index: int) -> str:
    """Convert a zero-based axis index to a one-based numeric identifier."""
    return str(_validate_index(index) + 1)


def alphabetic_axis_identifier(index: int) -> str:
    """Convert a zero-based index to spreadsheet-style letters (A, ..., AA)."""
    value = _validate_index(index) + 1
    characters = []
    while value:
        value, remainder = divmod(value - 1, 26)
        characters.append(chr(ord("A") + remainder))
    return "".join(reversed(characters))


def _validate_count(count: object) -> int:
    if isinstance(count, bool) or not isinstance(count, int):
        raise TypeError("Identifier count must be an integer.")
    if count < 0:
        raise ValueError("Identifier count must be greater than or equal to zero.")
    return count


def normalize_identifiers(
    explicit: Sequence[str] | None,
    count: int,
    scheme: str,
) -> tuple[str, ...]:
    """Generate or validate immutable identifiers for one axis family."""
    count = _validate_count(count)
    if scheme == "numeric":
        return tuple(numeric_axis_identifier(index) for index in range(count))
    if scheme == "alphabetic":
        return tuple(alphabetic_axis_identifier(index) for index in range(count))
    if scheme != "custom":
        raise ValueError(
            f"Unknown identifier scheme {scheme!r}; expected numeric, alphabetic, or custom."
        )
    if explicit is None or isinstance(explicit, (str, bytes)):
        raise ValueError("Custom identifiers must contain exactly the requested count.")
    identifiers = tuple(explicit)
    if len(identifiers) != count:
        raise ValueError(
            f"Custom identifiers must contain exactly {count} values; got {len(identifiers)}."
        )
    normalized = []
    for index, identifier in enumerate(identifiers):
        if not isinstance(identifier, str):
            raise TypeError(f"Custom identifier at index {index} must be text.")
        value = identifier.strip()
        if not value:
            raise ValueError(f"Custom identifier at index {index} cannot be empty.")
        normalized.append(value)
    if len(set(normalized)) != len(normalized):
        raise ValueError("Custom identifiers cannot contain duplicates.")
    return tuple(normalized)


def build_grid_geometry(
    x_spacings: Iterable[Real],
    y_spacings: Iterable[Real],
    x_start_extension: Real = 0.0,
    x_end_extension: Real = 0.0,
    y_start_extension: Real = 0.0,
    y_end_extension: Real = 0.0,
    x_identifier_scheme: str = "numeric",
    y_identifier_scheme: str = "alphabetic",
    x_identifiers: Sequence[str] | None = None,
    y_identifiers: Sequence[str] | None = None,
) -> GridGeometry:
    """Build an immutable grid in local XY coordinates.

    Axis-family naming follows spacing coordinates, not geometric line
    direction: X-family axes have constant X and run along Y; Y-family axes
    have constant Y and run along X.
    """
    x_values = validate_spacings(x_spacings, "X")
    y_values = validate_spacings(y_spacings, "Y")
    x_start = validate_extension(x_start_extension, "X start extension")
    x_end = validate_extension(x_end_extension, "X end extension")
    y_start = validate_extension(y_start_extension, "Y start extension")
    y_end = validate_extension(y_end_extension, "Y end extension")

    x_positions = accumulated_positions(x_values)
    y_positions = accumulated_positions(y_values)
    overall_x = x_positions[-1]
    overall_y = y_positions[-1]
    displayed_x = overall_x + x_start
    if not math.isfinite(displayed_x):
        raise ValueError("Displayed X length overflow; length and extensions must remain finite.")
    displayed_x += x_end
    if not math.isfinite(displayed_x):
        raise ValueError("Displayed X length overflow; length and extensions must remain finite.")
    displayed_y = overall_y + y_start
    if not math.isfinite(displayed_y):
        raise ValueError("Displayed Y length overflow; length and extensions must remain finite.")
    displayed_y += y_end
    if not math.isfinite(displayed_y):
        raise ValueError("Displayed Y length overflow; length and extensions must remain finite.")
    x_labels = normalize_identifiers(
        x_identifiers, len(x_positions), x_identifier_scheme
    )
    y_labels = normalize_identifiers(
        y_identifiers, len(y_positions), y_identifier_scheme
    )

    x_axes = tuple(
        GridAxis(
            family="X",
            index=index,
            identifier=x_labels[index],
            start=(position, -y_start, 0.0),
            end=(position, overall_y + y_end, 0.0),
        )
        for index, position in enumerate(x_positions)
    )
    y_axes = tuple(
        GridAxis(
            family="Y",
            index=index,
            identifier=y_labels[index],
            start=(-x_start, position, 0.0),
            end=(overall_x + x_end, position, 0.0),
        )
        for index, position in enumerate(y_positions)
    )
    intersections = tuple(
        GridIntersection(x_index, y_index, (x, y, 0.0))
        for x_index, x in enumerate(x_positions)
        for y_index, y in enumerate(y_positions)
    )
    return GridGeometry(
        x_positions=x_positions,
        y_positions=y_positions,
        x_axes=x_axes,
        y_axes=y_axes,
        intersections=intersections,
        overall_length_x=overall_x,
        overall_length_y=overall_y,
        displayed_length_x=displayed_x,
        displayed_length_y=displayed_y,
    )


def _validate_point(point: Sequence[Real]) -> Point3D:
    if isinstance(point, (str, bytes)):
        raise TypeError("Point must contain exactly three numeric coordinates.")
    try:
        coordinates = tuple(point)
    except TypeError as exc:
        raise TypeError("Point must contain exactly three numeric coordinates.") from exc
    if len(coordinates) != 3:
        raise ValueError("Point must contain exactly three coordinates.")
    return tuple(
        _finite_number(value, f"Point coordinate {index}")
        for index, value in enumerate(coordinates)
    )  # type: ignore[return-value]


def nearest_intersection(
    point: Sequence[Real],
    intersections: Iterable[GridIntersection],
    tolerance: Real,
) -> GridIntersection | None:
    """Return the first nearest intersection inside an inclusive tolerance."""
    target = _validate_point(point)
    limit = validate_extension(tolerance, "Tolerance")
    nearest = None
    nearest_distance = math.inf
    for intersection in intersections:
        candidate = _validate_point(intersection.point)
        distance = math.dist(candidate, target)
        if distance <= limit and distance < nearest_distance:
            nearest = intersection
            nearest_distance = distance
    return nearest


__all__ = [
    "GridAxis",
    "GridGeometry",
    "GridIntersection",
    "GridLabelAnchor",
    "accumulated_positions",
    "alphabetic_axis_identifier",
    "build_grid_geometry",
    "grid_label_anchors",
    "nearest_intersection",
    "normalize_identifiers",
    "numeric_axis_identifier",
    "validate_extension",
    "validate_spacings",
]
