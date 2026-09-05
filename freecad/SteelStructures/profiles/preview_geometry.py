# SPDX-License-Identifier: LGPL-2.1-or-later
"""Pure geometry helpers shared by section preview widgets."""

from __future__ import annotations

import math
from dataclasses import dataclass

from .geometry import ArcSegment2D, Point2D
from .insertion import InsertionReference, section_insertion_references


def background_needs_dark_outline_halo(red, green, blue):
    """Return whether a dark technical line needs separation from its background."""
    channels = []
    for value in (float(red), float(green), float(blue)):
        value = min(max(value, 0.0), 1.0)
        channels.append(
            value / 12.92
            if value <= 0.04045
            else ((value + 0.055) / 1.055) ** 2.4
        )
    luminance = 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]
    return luminance < 0.30


@dataclass(frozen=True)
class SchematicLine2D:
    start: Point2D
    end: Point2D


@dataclass(frozen=True)
class SchematicCubic2D:
    start: Point2D
    control1: Point2D
    control2: Point2D
    end: Point2D

    def sampled_points(self, count=12):
        points = []
        for index in range(1, count + 1):
            t = index / count
            inverse = 1.0 - t
            points.append(Point2D(
                inverse ** 3 * self.start.x
                + 3.0 * inverse ** 2 * t * self.control1.x
                + 3.0 * inverse * t ** 2 * self.control2.x
                + t ** 3 * self.end.x,
                inverse ** 3 * self.start.y
                + 3.0 * inverse ** 2 * t * self.control1.y
                + 3.0 * inverse * t ** 2 * self.control2.y
                + t ** 3 * self.end.y,
            ))
        return tuple(points)


@dataclass(frozen=True)
class SchematicSection2D:
    """Normalized family diagram, never a source of structural geometry."""

    typology_key: tuple[str, str]
    outline: tuple[Point2D, ...]
    references: tuple[InsertionReference, ...]
    segments: tuple[SchematicLine2D | SchematicCubic2D, ...] = ()
    center: Point2D = Point2D(0.0, 0.0)
    inner_segments: tuple[tuple[SchematicLine2D | SchematicCubic2D, ...], ...] = ()


def _line_segments(outline):
    return tuple(
        SchematicLine2D(point, outline[(index + 1) % len(outline)])
        for index, point in enumerate(outline)
    )


def preview_segments_for_path(path, scale=1.0):
    """Convert line/arc geometry to smooth line/cubic preview primitives."""
    result = []
    for segment in path.segments:
        if not isinstance(segment, ArcSegment2D):
            result.append(SchematicLine2D(
                Point2D(segment.start.x / scale, segment.start.y / scale),
                Point2D(segment.end.x / scale, segment.end.y / scale),
            ))
            continue
        count = max(1, int(math.ceil(abs(segment.sweep) / (math.pi / 2.0))))
        delta = segment.sweep / count
        previous_end = Point2D(segment.start.x / scale, segment.start.y / scale)
        for index in range(count):
            a0 = segment.start_angle + index * delta
            a1 = a0 + delta
            radius = segment.radius / scale
            center = Point2D(segment.center.x / scale, segment.center.y / scale)
            start = previous_end
            end = (Point2D(segment.end.x / scale, segment.end.y / scale)
                   if index == count - 1 else
                   Point2D(center.x + radius * math.cos(a1), center.y + radius * math.sin(a1)))
            k = 4.0 / 3.0 * math.tan(delta / 4.0)
            control1 = Point2D(start.x - k * radius * math.sin(a0), start.y + k * radius * math.cos(a0))
            control2 = Point2D(end.x + k * radius * math.sin(a1), end.y - k * radius * math.cos(a1))
            result.append(SchematicCubic2D(start, control1, control2, end))
            previous_end = end
    return tuple(result)


def _point(x, y):
    return Point2D(x, y)


def _schematic_outline(segments):
    points = [segments[0].start]
    for segment in segments:
        if isinstance(segment, SchematicCubic2D):
            points.extend(segment.sampled_points())
        else:
            points.append(segment.end)
    return tuple(points[:-1] if points[-1] == points[0] else points)


_I_OUTLINE = tuple(Point2D(*point) for point in (
    (-0.70, -1.00), (0.70, -1.00), (0.70, -0.74), (0.13, -0.74),
    (0.13, 0.74), (0.70, 0.74), (0.70, 1.00), (-0.70, 1.00),
    (-0.70, 0.74), (-0.13, 0.74), (-0.13, -0.74), (-0.70, -0.74),
))
_I_POINTS = {
    "centroid": (0.0, 0.0), "left": (-0.70, 0.0), "right": (0.70, 0.0),
    "top": (0.0, 1.0), "bottom": (0.0, -1.0),
    "top_left": (-0.70, 1.0), "top_right": (0.70, 1.0),
    "bottom_left": (-0.70, -1.0), "bottom_right": (0.70, -1.0),
}
_TAPERED_I_PATH = (
    SchematicLine2D(_point(-0.62, -1.00), _point(0.62, -1.00)),
    SchematicCubic2D(
        _point(0.62, -1.00), _point(0.67, -1.00),
        _point(0.70, -0.97), _point(0.70, -0.92),
    ),
    SchematicLine2D(_point(0.70, -0.92), _point(0.70, -0.84)),
    SchematicCubic2D(
        _point(0.70, -0.84), _point(0.70, -0.81),
        _point(0.67, -0.79), _point(0.64, -0.78),
    ),
    SchematicLine2D(_point(0.64, -0.78), _point(0.18, -0.66)),
    SchematicCubic2D(
        _point(0.18, -0.66), _point(0.13, -0.65),
        _point(0.13, -0.57), _point(0.13, -0.48),
    ),
    SchematicLine2D(_point(0.13, -0.48), _point(0.13, 0.48)),
    SchematicCubic2D(
        _point(0.13, 0.48), _point(0.13, 0.57),
        _point(0.13, 0.65), _point(0.18, 0.66),
    ),
    SchematicLine2D(_point(0.18, 0.66), _point(0.64, 0.78)),
    SchematicCubic2D(
        _point(0.64, 0.78), _point(0.67, 0.79),
        _point(0.70, 0.81), _point(0.70, 0.84),
    ),
    SchematicLine2D(_point(0.70, 0.84), _point(0.70, 0.92)),
    SchematicCubic2D(
        _point(0.70, 0.92), _point(0.70, 0.97),
        _point(0.67, 1.00), _point(0.62, 1.00),
    ),
    SchematicLine2D(_point(0.62, 1.00), _point(-0.62, 1.00)),
    SchematicCubic2D(
        _point(-0.62, 1.00), _point(-0.67, 1.00),
        _point(-0.70, 0.97), _point(-0.70, 0.92),
    ),
    SchematicLine2D(_point(-0.70, 0.92), _point(-0.70, 0.84)),
    SchematicCubic2D(
        _point(-0.70, 0.84), _point(-0.70, 0.81),
        _point(-0.67, 0.79), _point(-0.64, 0.78),
    ),
    SchematicLine2D(_point(-0.64, 0.78), _point(-0.18, 0.66)),
    SchematicCubic2D(
        _point(-0.18, 0.66), _point(-0.13, 0.65),
        _point(-0.13, 0.57), _point(-0.13, 0.48),
    ),
    SchematicLine2D(_point(-0.13, 0.48), _point(-0.13, -0.48)),
    SchematicCubic2D(
        _point(-0.13, -0.48), _point(-0.13, -0.57),
        _point(-0.13, -0.65), _point(-0.18, -0.66),
    ),
    SchematicLine2D(_point(-0.18, -0.66), _point(-0.64, -0.78)),
    SchematicCubic2D(
        _point(-0.64, -0.78), _point(-0.67, -0.79),
        _point(-0.70, -0.81), _point(-0.70, -0.84),
    ),
    SchematicLine2D(_point(-0.70, -0.84), _point(-0.70, -0.92)),
    SchematicCubic2D(
        _point(-0.70, -0.92), _point(-0.70, -0.97),
        _point(-0.67, -1.00), _point(-0.62, -1.00),
    ),
)
_TAPERED_I_OUTLINE = _schematic_outline(_TAPERED_I_PATH)
_U_PATH = (
    SchematicLine2D(_point(-0.65, -1.00), _point(0.56, -1.00)),
    SchematicCubic2D(
        _point(0.56, -1.00), _point(0.61, -1.00),
        _point(0.65, -0.96), _point(0.65, -0.91),
    ),
    SchematicLine2D(_point(0.65, -0.91), _point(0.65, -0.83)),
    SchematicCubic2D(
        _point(0.65, -0.83), _point(0.65, -0.77),
        _point(0.61, -0.73), _point(0.56, -0.72),
    ),
    SchematicLine2D(_point(0.56, -0.72), _point(-0.18, -0.52)),
    SchematicCubic2D(
        _point(-0.18, -0.52), _point(-0.29, -0.49),
        _point(-0.40, -0.44), _point(-0.40, -0.34),
    ),
    SchematicLine2D(_point(-0.40, -0.34), _point(-0.40, 0.34)),
    SchematicCubic2D(
        _point(-0.40, 0.34), _point(-0.40, 0.44),
        _point(-0.29, 0.49), _point(-0.18, 0.52),
    ),
    SchematicLine2D(_point(-0.18, 0.52), _point(0.56, 0.72)),
    SchematicCubic2D(
        _point(0.56, 0.72), _point(0.61, 0.73),
        _point(0.65, 0.77), _point(0.65, 0.83),
    ),
    SchematicLine2D(_point(0.65, 0.83), _point(0.65, 0.91)),
    SchematicCubic2D(
        _point(0.65, 0.91), _point(0.65, 0.96),
        _point(0.61, 1.00), _point(0.56, 1.00),
    ),
    SchematicLine2D(_point(0.56, 1.00), _point(-0.65, 1.00)),
    SchematicLine2D(_point(-0.65, 1.00), _point(-0.65, -1.00)),
)
_U_OUTLINE = _schematic_outline(_U_PATH)
_U_POINTS = {
    "centroid": (-0.12, 0.0), "web_center": (-0.52, 0.0),
    "web_back": (-0.65, 0.0), "rear_top": (-0.65, 1.0),
    "rear_bottom": (-0.65, -1.0), "flange_top_tip": (0.62, 0.98),
    "flange_bottom_tip": (0.62, -0.98),
}
_UE_PATH = (
    SchematicLine2D(_point(0.72, 0.52), _point(0.72, 0.78)),
    SchematicCubic2D(_point(0.72, 0.78), _point(0.72, 0.85), _point(0.67, 0.90), _point(0.60, 0.90)),
    SchematicLine2D(_point(0.60, 0.90), _point(-0.48, 0.90)),
    SchematicCubic2D(_point(-0.48, 0.90), _point(-0.56, 0.90), _point(-0.62, 0.84), _point(-0.62, 0.76)),
    SchematicLine2D(_point(-0.62, 0.76), _point(-0.62, -0.76)),
    SchematicCubic2D(_point(-0.62, -0.76), _point(-0.62, -0.84), _point(-0.56, -0.90), _point(-0.48, -0.90)),
    SchematicLine2D(_point(-0.48, -0.90), _point(0.60, -0.90)),
    SchematicCubic2D(_point(0.60, -0.90), _point(0.67, -0.90), _point(0.72, -0.85), _point(0.72, -0.78)),
    SchematicLine2D(_point(0.72, -0.78), _point(0.72, -0.52)),
    SchematicLine2D(_point(0.72, -0.52), _point(0.54, -0.52)),
    SchematicLine2D(_point(0.54, -0.52), _point(0.54, -0.70)),
    SchematicCubic2D(_point(0.54, -0.70), _point(0.54, -0.74), _point(0.50, -0.76), _point(0.46, -0.76)),
    SchematicLine2D(_point(0.46, -0.76), _point(-0.40, -0.76)),
    SchematicCubic2D(_point(-0.40, -0.76), _point(-0.42, -0.76), _point(-0.44, -0.74), _point(-0.44, -0.72)),
    SchematicLine2D(_point(-0.44, -0.72), _point(-0.44, 0.72)),
    SchematicCubic2D(_point(-0.44, 0.72), _point(-0.44, 0.74), _point(-0.42, 0.76), _point(-0.40, 0.76)),
    SchematicLine2D(_point(-0.40, 0.76), _point(0.46, 0.76)),
    SchematicCubic2D(_point(0.46, 0.76), _point(0.50, 0.76), _point(0.54, 0.74), _point(0.54, 0.70)),
    SchematicLine2D(_point(0.54, 0.70), _point(0.54, 0.52)),
    SchematicLine2D(_point(0.54, 0.52), _point(0.72, 0.52)),
)
_UE_OUTLINE = _schematic_outline(_UE_PATH)
_UE_POINTS = {
    "centroid": (-0.20, 0.0), "web_center": (-0.53, 0.0),
    "web_back": (-0.62, 0.0), "rear_top": (-0.62, 0.90),
    "rear_bottom": (-0.62, -0.90), "lip_top_tip": (0.63, 0.52),
    "lip_bottom_tip": (0.63, -0.52),
    "outer_top_mid": (0.06, 0.90),
    "outer_bottom_mid": (0.06, -0.90),
    "outer_lip_top_corner": (0.72, 0.90),
    "outer_lip_bottom_corner": (0.72, -0.90),
}
_L_OUTLINE = tuple(Point2D(*point) for point in (
    (-0.90, -0.90), (0.90, -0.90), (0.90, -0.56),
    (-0.56, -0.56), (-0.56, 0.90), (-0.90, 0.90),
))
_L_POINTS = {
    "centroid": (-0.34, -0.34), "outer_corner": (-0.90, -0.90),
    "top_tip": (-0.90, 0.90), "right_tip": (0.90, -0.90),
    "inner_corner": (-0.56, -0.56),
}
_T_OUTLINE = tuple(Point2D(*point) for point in (
    (-0.14, -1.00), (0.14, -1.00), (0.14, 0.34),
    (0.72, 0.34), (0.72, 0.65), (-0.72, 0.65),
    (-0.72, 0.34), (-0.14, 0.34),
))
_T_POINTS = {
    "centroid": (0.0, 0.0),
    "top": (0.0, 0.65),
    "bottom": (0.0, -1.00),
    "top_left": (-0.72, 0.65),
    "top_right": (0.72, 0.65),
}
_SCHEMATICS = {
    ("i_section", "parallel_flange"): (_I_OUTLINE, _I_POINTS, _line_segments(_I_OUTLINE)),
    ("i_section", "tapered_flange"): (
        _TAPERED_I_OUTLINE, _I_POINTS, _TAPERED_I_PATH,
    ),
    ("channel_section", "tapered_flange"): (_U_OUTLINE, _U_POINTS, _U_PATH),
    ("cold_formed_channel", "stiffened_u"): (_UE_OUTLINE, _UE_POINTS, _UE_PATH),
    ("equal_angle", "equal_leg"): (_L_OUTLINE, _L_POINTS, _line_segments(_L_OUTLINE)),
    ("tee_section", "standard_tee"): (_T_OUTLINE, _T_POINTS, _line_segments(_T_OUTLINE)),
}


def schematic_section_for_geometry(geometry):
    """Build a family diagram while retaining real insertion ids and labels."""
    key = (geometry.geometry_type, geometry.geometry_variant)
    definition = _SCHEMATICS.get(key)
    if key[0] in ("hollow_section", "solid_section"):
        scale = max(geometry.bounds.width, geometry.bounds.height) / 2.0
        def normalized_path(path):
            return preview_segments_for_path(path, scale)
        outer_segments = normalized_path(geometry.outer_path)
        inner_segments = tuple(normalized_path(path) for path in geometry.inner_paths)
        real_references = section_insertion_references(geometry)
        references = tuple(InsertionReference(
            reference.id, reference.label,
            Point2D(reference.point.x / scale, reference.point.y / scale),
        ) for reference in real_references)
        outline = tuple(segment.start for segment in outer_segments)
        return SchematicSection2D(
            key, outline, references, outer_segments, Point2D(0.0, 0.0), inner_segments,
        )
    if definition is None:
        return None
    outline, positions, segments = definition
    real_references = section_insertion_references(geometry)
    if any(reference.id not in positions for reference in real_references):
        return None
    references = tuple(
        InsertionReference(reference.id, reference.label, Point2D(*positions[reference.id]))
        for reference in real_references
    )
    return SchematicSection2D(key, outline, references, segments)


def section_path_points(path):
    """Return one canonical path as points, sampling only curved segments."""
    points = [path.segments[0].start]
    for segment in path.segments:
        if isinstance(segment, ArcSegment2D):
            points.extend(segment.sampled_points())
        else:
            points.append(segment.end)
    return tuple(points)


def section_outline_points(geometry):
    return section_path_points(geometry.outer_path)


def section_contour_points(geometry):
    """Return outer and inner contours for fill-rule-aware preview renderers."""
    return (section_path_points(geometry.outer_path),) + tuple(
        section_path_points(path) for path in geometry.inner_paths
    )


def transform_preview_point(point, insertion_point, rotation_degrees):
    """Translate to the insertion axis, then rotate around that fixed axis."""
    x = point.x - insertion_point.x
    y = point.y - insertion_point.y
    angle = math.radians(float(rotation_degrees))
    cosine, sine = math.cos(angle), math.sin(angle)
    return Point2D(x * cosine - y * sine, x * sine + y * cosine)


def outline_presentation_reference(outline):
    """Return the stable bounding-box center used only for 2D presentation."""
    minimum_x = min(point.x for point in outline)
    maximum_x = max(point.x for point in outline)
    minimum_y = min(point.y for point in outline)
    maximum_y = max(point.y for point in outline)
    return Point2D(
        (minimum_x + maximum_x) / 2.0,
        (minimum_y + maximum_y) / 2.0,
    )


def profile_presentation_radius(outline, presentation_reference):
    """Envelope the contour around a stable profile presentation reference."""
    radius = max(
        math.hypot(
            point.x - presentation_reference.x,
            point.y - presentation_reference.y,
        )
        for point in outline
    )
    return max(radius, 1e-9)


def preview_screen_point(point, insertion_point, rotation_degrees,
                         target_x, target_y, scale):
    """Map model +Y upward to a Qt screen whose +Y points downward."""
    transformed = transform_preview_point(point, insertion_point, rotation_degrees)
    return target_x + transformed.x * scale, target_y - transformed.y * scale


def nearest_reference(references, insertion_point, rotation_degrees,
                      target_x, target_y, scale, cursor_x, cursor_y,
                      hit_radius_pixels):
    """Return the visually closest reference inside a device-pixel hit radius."""
    candidates = []
    for reference in references:
        x, y = preview_screen_point(
            reference.point, insertion_point, rotation_degrees,
            target_x, target_y, scale,
        )
        distance = math.hypot(cursor_x - x, cursor_y - y)
        if distance <= hit_radius_pixels:
            candidates.append((distance, reference))
    return min(candidates, key=lambda item: item[0])[1] if candidates else None


__all__ = [
    "background_needs_dark_outline_halo", "nearest_reference",
    "outline_presentation_reference", "preview_segments_for_path",
    "preview_screen_point", "profile_presentation_radius",
    "schematic_section_for_geometry", "section_contour_points", "section_outline_points",
    "section_path_points",
    "SchematicCubic2D", "SchematicLine2D", "SchematicSection2D",
    "transform_preview_point",
]
