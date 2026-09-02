# SPDX-License-Identifier: LGPL-2.1-or-later
"""Pure shared geometry builders for square, rectangular and circular tubes."""

from __future__ import annotations

import math
from dataclasses import dataclass, replace

from .geometry import (
    ArcSegment2D, LineSegment2D, Point2D, SectionBounds2D,
    SectionGeometry2D, SectionGeometryError, SectionGeometryMode, SectionPath2D,
    normalize_section_geometry_mode,
)
from .models import ProfileDefinition, immutable_mapping


@dataclass(frozen=True)
class HollowSectionRadii:
    """Radii used exclusively by the CAD representation."""

    cad_outer_corner_radius: float
    cad_inner_corner_radius: float


@dataclass(frozen=True)
class HollowSectionRadiusMetadata:
    """Non-CAD radius provenance, kept outside the BRep convention."""

    manufacturer_corner_radius: float | None = None
    calculation_corner_radius: float | None = None
    calculation_basis: str | None = None


@dataclass(frozen=True)
class HollowSectionDefinition:
    """Small common definition used by all hollow-section builders."""

    family: str
    width: float
    height: float
    thickness: float
    cad_radii: HollowSectionRadii | None = None
    radius_metadata: HollowSectionRadiusMetadata = HollowSectionRadiusMetadata()


def normalize_rhs_dimensions(h: float, b: float, t: float) -> tuple[float, float, float]:
    """Return the public RHS convention H x B x t, with H >= B."""
    h, b, t = float(h), float(b), float(t)
    if not all(math.isfinite(value) for value in (h, b, t)):
        raise SectionGeometryError("dimensões RHS devem ser finitas")
    return max(h, b), min(h, b), t


def canonical_rhs_key(h: float, b: float, t: float) -> tuple[float, float, float]:
    """Stable dimension key for deduplication after public H/B normalization."""
    return normalize_rhs_dimensions(h, b, t)


def normalize_hollow_profile_definition(profile: ProfileDefinition) -> ProfileDefinition:
    """Normalize typed RHS geometry at the public domain boundary.

    Source-order dimensions can remain in provenance metadata; consumers of the
    public profile contract always see H >= B, with H vertical and B horizontal.
    """
    if (profile.geometry_type, profile.geometry_variant) != (
        "hollow_section", "rectangular"
    ):
        return profile
    try:
        h, b, t = canonical_rhs_key(
            profile.geometry["h"], profile.geometry["b"], profile.geometry["t"]
        )
    except KeyError as exc:
        raise SectionGeometryError(f"dimensão ausente: {exc.args[0]}") from exc
    if (h, b, t) == (
        profile.geometry["h"], profile.geometry["b"], profile.geometry["t"]
    ):
        return profile
    geometry = dict(profile.geometry)
    geometry.update(h=h, b=b, t=t)
    return replace(profile, geometry=immutable_mapping(geometry))


def nominal_hollow_section_radii(thickness: float, minimum_dimension: float) -> HollowSectionRadii:
    """Return the Stage-A CAD convention ``ro=2t`` and ``ri=t``.

    This is only a visual BRep convention, informed by common HSS practice. It
    is neither a manufacturer radius nor the radius used by future section-
    property calculations.  An unrealizable section is rejected, never clamped.
    """
    t = float(thickness)
    side = float(minimum_dimension)
    if not math.isfinite(t) or not math.isfinite(side) or t <= 0.0 or 2.0 * t >= side:
        raise SectionGeometryError("t deve ser positivo e 2*t menor que a dimensão externa")
    outer_shape, inner_shape = 2.0 * t, t
    if outer_shape >= side / 2.0:
        raise SectionGeometryError(
            "convenção CAD ro=2*t não é realizável nas dimensões externas"
        )
    return HollowSectionRadii(outer_shape, inner_shape)


def _rectangle_path(width: float, height: float, radius: float = 0.0) -> SectionPath2D:
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


def _circle_path(radius: float) -> SectionPath2D:
    if radius <= 0.0:
        raise SectionGeometryError("raio circular deve ser positivo")
    center = Point2D(0.0, 0.0)
    right, left = Point2D(radius, 0.0), Point2D(-radius, 0.0)
    return SectionPath2D((
        ArcSegment2D(right, left, center), ArcSegment2D(left, right, center),
    ), True)


def build_rectangular_hollow_section(
    *, width: float, height: float, t: float,
    mode: SectionGeometryMode | str = SectionGeometryMode.DETAILED,
    family: str = "RHS",
) -> SectionGeometry2D:
    """Build SHS/RHS through one shared rectangular hollow-section pipeline."""
    width, height, t = float(width), float(height), float(t)
    if not all(math.isfinite(value) for value in (width, height, t)):
        raise SectionGeometryError("dimensões tubulares devem ser finitas")
    if min(width, height, t) <= 0.0 or 2.0 * t >= min(width, height):
        raise SectionGeometryError("dimensões tubulares inválidas")
    family = str(family).upper()
    if family not in ("SHS", "RHS"):
        raise SectionGeometryError("family deve ser SHS ou RHS")
    if family == "SHS" and not math.isclose(width, height, abs_tol=1e-9):
        raise SectionGeometryError("SHS deve possuir lados externos iguais")
    if family == "RHS" and math.isclose(width, height, abs_tol=1e-9):
        raise SectionGeometryError("RHS deve possuir lados externos diferentes")
    mode = normalize_section_geometry_mode(mode)
    radii = nominal_hollow_section_radii(t, min(width, height))
    detailed = mode is SectionGeometryMode.DETAILED
    outer_radius = radii.cad_outer_corner_radius if detailed else 0.0
    inner_radius = radii.cad_inner_corner_radius if detailed else 0.0
    inner_width, inner_height = width - 2.0 * t, height - 2.0 * t
    variant = "square" if family == "SHS" else "rectangular"
    stations = (
        ("width", width), ("height", height), ("thickness", t),
        ("cad_outer_corner_radius", outer_radius),
        ("cad_inner_corner_radius", inner_radius),
    )
    return SectionGeometry2D(
        geometry_type="hollow_section", geometry_variant=variant,
        outer_path=_rectangle_path(width, height, outer_radius),
        inner_paths=(_rectangle_path(inner_width, inner_height, inner_radius),),
        bounds=SectionBounds2D(-width / 2.0, width / 2.0, -height / 2.0, height / 2.0),
        origin=Point2D(0.0, 0.0), dimension_stations=stations,
    )


def build_square_hollow_section(
    *, b: float, t: float,
    mode: SectionGeometryMode | str = SectionGeometryMode.DETAILED,
) -> SectionGeometry2D:
    return build_rectangular_hollow_section(width=b, height=b, t=t, mode=mode, family="SHS")


def build_rhs_hollow_section(
    *, h: float, b: float, t: float,
    mode: SectionGeometryMode | str = SectionGeometryMode.DETAILED,
) -> SectionGeometry2D:
    """Build RHS with H on local Y and B on local X, normalizing H >= B."""
    h, b, t = normalize_rhs_dimensions(h, b, t)
    return build_rectangular_hollow_section(
        width=b, height=h, t=t, mode=mode, family="RHS"
    )


def build_circular_hollow_section(*, d: float, t: float) -> SectionGeometry2D:
    """Build CHS; its circular curvature is fundamental and has no LOD toggle."""
    d, t = float(d), float(t)
    if not math.isfinite(d) or not math.isfinite(t) or t <= 0.0 or 2.0 * t >= d:
        raise SectionGeometryError("CHS requer d > 2*t > 0")
    outer_radius, inner_radius = d / 2.0, d / 2.0 - t
    return SectionGeometry2D(
        geometry_type="hollow_section", geometry_variant="circular",
        outer_path=_circle_path(outer_radius), inner_paths=(_circle_path(inner_radius),),
        bounds=SectionBounds2D(-outer_radius, outer_radius, -outer_radius, outer_radius),
        origin=Point2D(0.0, 0.0),
        dimension_stations=(("diameter", d), ("inner_diameter", d - 2.0 * t), ("thickness", t)),
    )


__all__ = [
    "HollowSectionDefinition", "HollowSectionRadii", "HollowSectionRadiusMetadata",
    "build_circular_hollow_section", "canonical_rhs_key",
    "build_rectangular_hollow_section", "build_rhs_hollow_section",
    "build_square_hollow_section", "nominal_hollow_section_radii",
    "normalize_hollow_profile_definition", "normalize_rhs_dimensions",
]
