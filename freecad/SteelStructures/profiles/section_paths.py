# SPDX-License-Identifier: LGPL-2.1-or-later
# Shared exact centered paths for solid and hollow sections.

from .geometry import (
    ArcSegment2D, LineSegment2D, Point2D, SectionGeometryError, SectionPath2D,
)


def rectangle_path(width: float, height: float, radius: float = 0.0) -> SectionPath2D:
    hw, hh, r = width / 2.0, height / 2.0, float(radius)
    if r < 0.0 or r > min(hw, hh):
        raise SectionGeometryError("raio retangular incompatível com as dimensões")
    if r == 0.0:
        points = (
            Point2D(-hw, -hh), Point2D(hw, -hh),
            Point2D(hw, hh), Point2D(-hw, hh),
        )
        return SectionPath2D(tuple(
            LineSegment2D(point, points[(index + 1) % 4])
            for index, point in enumerate(points)
        ), True)
    points = (
        Point2D(-hw + r, -hh), Point2D(hw - r, -hh),
        Point2D(hw, -hh + r), Point2D(hw, hh - r),
        Point2D(hw - r, hh), Point2D(-hw + r, hh),
        Point2D(-hw, hh - r), Point2D(-hw, -hh + r),
    )
    centers = (
        Point2D(hw - r, -hh + r), Point2D(hw - r, hh - r),
        Point2D(-hw + r, hh - r), Point2D(-hw + r, -hh + r),
    )
    candidates = (
        (LineSegment2D, points[0], points[1], None),
        (ArcSegment2D, points[1], points[2], centers[0]),
        (LineSegment2D, points[2], points[3], None),
        (ArcSegment2D, points[3], points[4], centers[1]),
        (LineSegment2D, points[4], points[5], None),
        (ArcSegment2D, points[5], points[6], centers[2]),
        (LineSegment2D, points[6], points[7], None),
        (ArcSegment2D, points[7], points[0], centers[3]),
    )
    segments = tuple(
        segment_type(start, end) if center is None else segment_type(start, end, center)
        for segment_type, start, end, center in candidates
        if start != end
    )
    return SectionPath2D(segments, True)


def circle_path(radius: float) -> SectionPath2D:
    if radius <= 0.0:
        raise SectionGeometryError("raio circular deve ser positivo")
    center = Point2D(0.0, 0.0)
    right, left = Point2D(radius, 0.0), Point2D(-radius, 0.0)
    return SectionPath2D((
        ArcSegment2D(right, left, center), ArcSegment2D(left, right, center),
    ), True)
