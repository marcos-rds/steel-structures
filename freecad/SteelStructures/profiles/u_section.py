# SPDX-License-Identifier: LGPL-2.1-or-later
"""Simple cold-formed U: physical geometry, independent of published properties.

NBR 6355 nominal bw/bf are external dimensions. The free flange ends have no
lips. Coordinates start at the external rear web face, opening towards +X;
the shared cold-formed core subsequently translates to the physical centroid.
"""

from dataclasses import dataclass, replace

from .cold_formed import (
    ColdFormedPath2D, section_geometry_from_cold_formed, translated_path,
)
from .geometry import (
    ArcSegment2D, LineSegment2D, Point2D, SectionGeometryError, SectionPath2D,
    _finite,
)


@dataclass(frozen=True)
class SimpleUDerivedDimensions:
    a: float
    am: float
    b: float
    bm: float
    rm: float
    re: float


def simple_u_derived_dimensions(*, bw, bf, t, ri):
    """Validate physical dimensions; do not impose a catalog's ri/tn rule."""
    bw, bf, t, ri = (_finite(value, name) for name, value in
                     (("bw", bw), ("bf", bf), ("t", t), ("ri", ri)))
    if min(bw, bf, t, ri) <= 0.0:
        raise SectionGeometryError("bw, bf, t e ri do U simples devem ser positivos")
    re, rm = ri + t, ri + t / 2.0
    result = SimpleUDerivedDimensions(
        a=bw - 2.0 * re, am=bw - t, b=bf - re, bm=bf - t / 2.0,
        rm=rm, re=re,
    )
    if min(result.a, result.b) <= 0.0:
        raise SectionGeometryError("dimensões U simples não acomodam trechos planos e raios")
    return result


def build_simple_u_mean_path(*, bw, bf, t, ri):
    """Three tangent lines and two circular quarter bends, constant thickness."""
    dims = simple_u_derived_dimensions(bw=bw, bf=bf, t=t, ri=ri)
    # Use validated numeric values, including inputs accepted by _finite.
    bw, bf, t = float(bw), float(bf), float(t)
    half, re = t / 2.0, dims.re
    p0, p1 = Point2D(bf, bw - half), Point2D(re, bw - half)
    p2, p3 = Point2D(half, bw - re), Point2D(half, re)
    p4, p5 = Point2D(re, half), Point2D(bf, half)
    return ColdFormedPath2D(SectionPath2D((
        LineSegment2D(p0, p1),
        ArcSegment2D(p1, p2, Point2D(re, bw - re)),
        LineSegment2D(p2, p3),
        ArcSegment2D(p3, p4, Point2D(re, re)),
        LineSegment2D(p4, p5),
    ), False), t)


def build_simple_u_section(*, bw, bf, t, ri):
    """Physical contour and named stations in the same centroidal frame."""
    folded = build_simple_u_mean_path(bw=bw, bf=bf, t=t, ri=ri)
    geometry = section_geometry_from_cold_formed(
        folded, geometry_type="cold_formed_channel", geometry_variant="simple_u",
    )
    bf, t, ri = float(bf), folded.thickness, float(ri)
    bounds = geometry.bounds
    return replace(geometry, dimension_stations=(
        ("external_web_x", bounds.min_x),
        ("web_mean_x", bounds.min_x + t / 2.0),
        ("nominal_top_y", bounds.max_y),
        ("nominal_bottom_y", bounds.min_y),
        ("nominal_flange_tip_x", bounds.min_x + bf),
        ("upper_flange_mean_y", bounds.max_y - t / 2.0),
        ("lower_flange_mean_y", bounds.min_y + t / 2.0),
        ("flange_web_tangent_x", bounds.min_x + ri + t),
        ("thickness", t),
        ("internal_radius", ri),
    ))


def build_simplified_simple_u_section(*, bw, bf, t, ri):
    """Sharp representation retaining the detailed datum and insertion stations.

    Its BRep area intentionally differs. Published properties are not changed.
    """
    detailed = build_simple_u_section(bw=bw, bf=bf, t=t, ri=ri)
    bw, bf, t = float(bw), float(bf), float(t)
    points = (
        Point2D(bf, bw - t), Point2D(t, bw - t), Point2D(t, t),
        Point2D(bf, t), Point2D(bf, 0), Point2D(0, 0),
        Point2D(0, bw), Point2D(bf, bw),
    )
    path = SectionPath2D(tuple(
        LineSegment2D(point, points[(index + 1) % len(points)])
        for index, point in enumerate(points)
    ), True)
    return replace(detailed, outer_path=translated_path(
        path, detailed.bounds.min_x, detailed.bounds.min_y,
    ))


__all__ = [
    "SimpleUDerivedDimensions", "simple_u_derived_dimensions",
    "build_simple_u_mean_path", "build_simple_u_section",
    "build_simplified_simple_u_section",
]
