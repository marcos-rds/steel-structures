# SPDX-License-Identifier: LGPL-2.1-or-later
"""ABNT NBR 6355 Ue mean-line, physical contour and normative controls."""

from __future__ import annotations

import math
from dataclasses import dataclass, replace

from .cold_formed import (
    ColdFormedPath2D, section_geometry_from_cold_formed, translated_path,
)
from .geometry import (
    ArcSegment2D, LineSegment2D, Point2D,
    SectionGeometry2D, SectionGeometryError, SectionPath2D,
)


@dataclass(frozen=True)
class UeDerivedDimensions:
    a: float
    am: float
    b: float
    bm: float
    c: float
    cm: float
    rm: float
    re: float
    u1: float


@dataclass(frozen=True)
class UeNormativeProperties:
    area_mm2: float
    xg_mm: float
    ix_mm4: float
    iy_mm4: float


def ue_derived_dimensions(*, bw, bf, D, t, ri):
    values = {name: float(value) for name, value in
              (("bw", bw), ("bf", bf), ("D", D), ("t", t), ("ri", ri))}
    if any(not math.isfinite(value) for value in values.values()):
        raise SectionGeometryError("dimensões Ue devem ser finitas")
    if min(values["bw"], values["bf"], values["D"], values["t"]) <= 0.0:
        raise SectionGeometryError("bw, bf, D e t devem ser positivos")
    if values["ri"] < 0.0:
        raise SectionGeometryError("ri não pode ser negativo")
    bw, bf, D, t, ri = (values[name] for name in ("bw", "bf", "D", "t", "ri"))
    rm, re = ri + 0.5 * t, ri + t
    result = UeDerivedDimensions(
        a=bw - 2.0 * re, am=bw - t,
        b=bf - 2.0 * re, bm=bf - t,
        c=D - re, cm=D - 0.5 * t,
        rm=rm, re=re, u1=1.571 * rm,
    )
    if min(result.a, result.b, result.c) < 0.0:
        raise SectionGeometryError("dimensões Ue não acomodam espessura e raios")
    if result.rm <= 0.0 or result.re <= result.rm:
        raise SectionGeometryError("raios Ue inválidos")
    return result


def _build_ue_mean_path_and_points(*, bw, bf, D, t, ri):
    dims = ue_derived_dimensions(bw=bw, bf=bf, D=D, t=t, ri=ri)
    half_t, rm, re = t / 2.0, dims.rm, dims.re
    # From the upper free lip to the lower free lip. External web face x=0,
    # external section limits y=0..bw, opening toward +X.
    p0 = Point2D(bf - half_t, bw - D)
    p1 = Point2D(bf - half_t, bw - re)
    p2 = Point2D(bf - re, bw - half_t)
    p3 = Point2D(re, bw - half_t)
    p4 = Point2D(half_t, bw - re)
    p5 = Point2D(half_t, re)
    p6 = Point2D(re, half_t)
    p7 = Point2D(bf - re, half_t)
    p8 = Point2D(bf - half_t, re)
    p9 = Point2D(bf - half_t, D)
    segments = (
        LineSegment2D(p0, p1),
        ArcSegment2D(p1, p2, Point2D(bf - re, bw - re), False),
        LineSegment2D(p2, p3),
        ArcSegment2D(p3, p4, Point2D(re, bw - re), False),
        LineSegment2D(p4, p5),
        ArcSegment2D(p5, p6, Point2D(re, re), False),
        LineSegment2D(p6, p7),
        ArcSegment2D(p7, p8, Point2D(bf - re, re), False),
        LineSegment2D(p8, p9),
    )
    return ColdFormedPath2D(SectionPath2D(segments, False), t), {
        "flange_top_lip_tangent": p2,
        "flange_top_web_tangent": p3,
    }


def build_ue_mean_path(*, bw, bf, D, t, ri):
    folded, _points = _build_ue_mean_path_and_points(
        bw=bw, bf=bf, D=D, t=t, ri=ri
    )
    return folded


def build_ue_section(*, bw, bf, D, t, ri):
    folded, mean_points = _build_ue_mean_path_and_points(
        bw=bw, bf=bf, D=D, t=t, ri=ri
    )
    geometry = section_geometry_from_cold_formed(
        folded,
        geometry_type="cold_formed_channel",
        geometry_variant="stiffened_u",
    )
    bounds = geometry.bounds
    # These stations come from the named straight portions of the physical
    # mean line, then receive the same nominal-to-centroidal translation as
    # the generated section. They deliberately do not depend on outer_path.
    translation_x = bounds.min_x
    flange_web_tangent_x = (
        mean_points["flange_top_web_tangent"].x + translation_x
    )
    flange_lip_tangent_x = (
        mean_points["flange_top_lip_tangent"].x + translation_x
    )
    # Presentation/reference stations are derived from the approved physical
    # contour after centroidal translation. Nominal rounded-corner references
    # use the intersections of the external dimension planes.
    return replace(geometry, dimension_stations=(
        ("external_web_x", bounds.min_x),
        ("web_mean_x", bounds.min_x + 0.5 * t),
        ("nominal_top_y", bounds.max_y),
        ("nominal_bottom_y", bounds.min_y),
        ("nominal_flange_tip_x", bounds.min_x + bf),
        ("upper_lip_tip_y", bounds.max_y - D),
        ("lower_lip_tip_y", bounds.min_y + D),
        ("flange_web_tangent_x", flange_web_tangent_x),
        ("flange_lip_tangent_x", flange_lip_tangent_x),
        ("thickness", t),
        ("internal_radius", ri),
    ))


def build_simplified_ue_section(*, bw, bf, D, t, ri):
    """Build the same nominal Ue with sharp bends and unchanged technical data."""
    # Validate the catalog contract, including ri, without applying ri to BRep.
    ue_derived_dimensions(bw=bw, bf=bf, D=D, t=t, ri=ri)
    detailed = build_ue_section(bw=bw, bf=bf, D=D, t=t, ri=ri)
    detailed_stations = dict(detailed.dimension_stations)
    # Nominal external datum: rear web x=0, height 0..bw, opening toward +X.
    points = (
        Point2D(bf - t, bw - D), Point2D(bf - t, bw - t),
        Point2D(t, bw - t), Point2D(t, t),
        Point2D(bf - t, t), Point2D(bf - t, D),
        Point2D(bf, D), Point2D(bf, 0.0), Point2D(0.0, 0.0),
        Point2D(0.0, bw), Point2D(bf, bw), Point2D(bf, bw - D),
    )
    raw = SectionPath2D(tuple(
        LineSegment2D(point, points[(index + 1) % len(points)])
        for index, point in enumerate(points)
    ), True)
    # Preserve the detailed nominal centroid as the member-axis datum.
    detailed_external_web = detailed_stations["external_web_x"]
    detailed_centroid_x = -detailed_external_web
    centered = translated_path(raw, -detailed_centroid_x, -bw / 2.0)
    bounds = detailed.bounds
    stations = tuple((name, value) for name, value in detailed.dimension_stations)
    return SectionGeometry2D(
        "cold_formed_channel", "stiffened_u", centered, (), bounds,
        Point2D(0.0, 0.0), stations,
    )


def ue_normative_properties(*, bw, bf, D, t, ri):
    """Calculate Ue A, Xg, Ix and Iy with the Annex A item 11 formulas.

    Inputs and results use the NBR formula units: millimetres, square
    millimetres and fourth-power millimetres. Decimal coefficients are kept
    exactly as printed and deliberately are not replaced by pi-based values.
    """
    dims = ue_derived_dimensions(
        bw=bw, bf=bf, D=D, t=t, ri=ri
    )
    a, b, c, rm, u1 = dims.a, dims.b, dims.c, dims.rm, dims.u1
    area = t * (a + 2.0 * b + 2.0 * c + 4.0 * u1)
    xg = (
        (2.0 * t / area)
        * (b * (0.5 * b + rm) + (u1 + c) * (b + 2.0 * rm))
        + 0.5 * t
    )
    ix = 2.0 * t * (
        0.042 * a ** 3
        + b * (0.5 * a + rm) ** 2
        + 2.0 * u1 * (0.5 * a + 0.637 * rm) ** 2
        + 0.298 * rm ** 3
        + 0.083 * c ** 3
        + 0.25 * c * (a - c) ** 2
    )
    iy = (
        2.0 * t * (
            b * (0.5 * b + rm) ** 2
            + 0.083 * b ** 3
            + 0.505 * rm ** 3
            + c * (b + 2.0 * rm) ** 2
            + u1 * (b + 1.637 * rm) ** 2
        )
        - area * (xg - 0.5 * t) ** 2
    )
    return UeNormativeProperties(
        area_mm2=area,
        xg_mm=xg,
        ix_mm4=ix,
        iy_mm4=iy,
    )


def nbr_6355_expected_internal_radius(tn):
    tn = float(tn)
    if not math.isfinite(tn) or tn <= 0.0:
        raise ValueError("tn deve ser positivo e finito")
    return tn if tn <= 6.3 else 1.5 * tn


__all__ = [
    "UeDerivedDimensions", "UeNormativeProperties", "build_ue_mean_path",
    "build_simplified_ue_section",
    "build_ue_section", "nbr_6355_expected_internal_radius",
    "ue_derived_dimensions", "ue_normative_properties",
]
