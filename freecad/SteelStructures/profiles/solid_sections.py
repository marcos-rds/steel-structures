# SPDX-License-Identifier: LGPL-2.1-or-later
"""Exact nominal solid bars in local XY, independent from FreeCAD and Qt."""

from .geometry import (
    Point2D, SectionBounds2D, SectionGeometry2D, SectionGeometryError,
    SectionGeometryMode, _finite, normalize_section_geometry_mode,
)
from .section_paths import circle_path, rectangle_path


SOLID_SECTION_PARAMETERS = {
    "circular": ("d",), "square": ("b",), "rectangular": ("b", "t"),
}
SOLID_SECTION_FAMILIES = {
    "circular": "ROUND_BAR", "square": "SQUARE_BAR", "rectangular": "FLAT_BAR",
}


def solid_section_dimensions(variant, dimensions):
    """Validate exact parameters and return width X / height Y without swaps."""
    expected = SOLID_SECTION_PARAMETERS.get(variant)
    if expected is None or set(dimensions) != set(expected):
        raise SectionGeometryError("variante ou parâmetros de seção maciça inválidos")
    values = {name: _finite(value, name) for name, value in dimensions.items()}
    if any(value <= 0 for value in values.values()):
        raise SectionGeometryError("dimensões maciças devem ser positivas")
    if variant == "circular":
        return values["d"], values["d"]
    if variant == "square":
        return values["b"], values["b"]
    if values["b"] <= values["t"]:
        raise SectionGeometryError("barra chata exige B > t > 0")
    return values["b"], values["t"]


def _build(variant, dimensions, mode):
    normalize_section_geometry_mode(mode)  # Both modes have the same nominal contour.
    width, height = solid_section_dimensions(variant, dimensions)
    circular = variant == "circular"
    stations = (("diameter", width),) if circular else (
        ("width", width), ("height", height),
    )
    if variant == "rectangular":
        stations += (("thickness", height),)
    return SectionGeometry2D(
        geometry_type="solid_section", geometry_variant=variant,
        outer_path=circle_path(width / 2) if circular else rectangle_path(width, height),
        inner_paths=(), origin=Point2D(0, 0),
        bounds=SectionBounds2D(-width / 2, width / 2, -height / 2, height / 2),
        dimension_stations=stations,
    )


def build_round_bar(*, d, mode=SectionGeometryMode.DETAILED):
    return _build("circular", {"d": d}, mode)


def build_square_bar(*, b, mode=SectionGeometryMode.DETAILED):
    return _build("square", {"b": b}, mode)


def build_flat_bar(*, b, t, mode=SectionGeometryMode.DETAILED):
    return _build("rectangular", {"b": b, "t": t}, mode)
