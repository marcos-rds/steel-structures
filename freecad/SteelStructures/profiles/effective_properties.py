# SPDX-License-Identifier: LGPL-2.1-or-later
"""Pure calculated section properties and catalog-backed effective values."""

from __future__ import annotations

import math
from dataclasses import dataclass, replace

from .geometry import ArcSegment2D, LineSegment2D, build_section_geometry
from .models import ProfileDefinition, PropertyProvenance, immutable_mapping


HOLLOW_CALCULATION_CONVENTION = "EN 10219-2:2019 Annex A dimensional convention"


@dataclass(frozen=True)
class GeometricSectionProperties:
    area: float
    centroid_x: float
    centroid_y: float
    ix: float
    iy: float


@dataclass(frozen=True)
class CalculatedSectionProperties:
    """Mode-independent dimensional section properties in mm units.

    X-X is horizontal and Y-Y vertical. ``basis`` records the mathematical
    convention without making a product-certification claim.
    """

    area: float
    ix: float
    iy: float
    wx: float
    wy: float
    rx: float
    ry: float
    centroid_x: float = 0.0
    centroid_y: float = 0.0
    basis: str = "Steel Structures calculation convention"


def rectangular_hollow_calculation_radii(t):
    """Return nominal calculation radii from EN 10219-2:2019 Annex A.

    These radii belong to the technical-section model, not the CAD BRep.
    """
    t = float(t)
    if not math.isfinite(t) or t <= 0.0:
        raise ValueError("espessura deve ser finita e positiva")
    factor = 2.0 if t <= 6.0 else (2.5 if t <= 10.0 else 3.0)
    outer = factor * t
    return outer, outer - t


def hollow_section_properties(*, family, h=None, b=None, d=None, t):
    """Calculate hollow-section properties from dimensions, never from a BRep.

    SHS/RHS use the nominal calculation-radius convention documented by
    EN 10219-2:2019 Annex A. CHS uses exact annulus expressions.
    Commercial mass remains wholly independent.
    """
    family, t = str(family).upper(), float(t)
    if family not in {"SHS", "RHS", "CHS"}:
        raise ValueError("family deve ser SHS, RHS ou CHS")
    if not math.isfinite(t):
        raise ValueError("espessura deve ser finita")
    if family == "CHS":
        d = float(d)
        if not math.isfinite(d) or t <= 0.0 or d <= 2.0 * t:
            raise ValueError("CHS requer D > 2*t > 0")
        inner = d - 2.0 * t
        area = math.pi * (d ** 2 - inner ** 2) / 4.0
        ix = iy = math.pi * (d ** 4 - inner ** 4) / 64.0
        wx = wy = ix / (d / 2.0)
    elif family in {"SHS", "RHS"}:
        h, b = float(h), float(b)
        if not math.isfinite(h) or not math.isfinite(b):
            raise ValueError("H e B devem ser finitos")
        if family == "RHS":
            h, b = max(h, b), min(h, b)
        if t <= 0.0 or min(h, b) <= 2.0 * t:
            raise ValueError("SHS/RHS requerem H e B maiores que 2*t")
        hi, bi = h - 2.0 * t, b - 2.0 * t
        ro, ri = rectangular_hollow_calculation_radii(t)
        # EN 10219-2 Annex A expresses the corner contribution algebraically.
        # It is not constructed as (and must not be constrained like) the CAD
        # rounded-rectangle BRep; this matters for thick, narrow RHS sections.
        # For example, RHS 203.2x76.2x16 has ro_calc=48 > B/2.  The expression
        # remains a mathematical calculation convention: it does not describe
        # a realizable rounded-rectangle contour, CAD radius or manufacturing
        # radius.
        c = (10.0 - 3.0 * math.pi) / (12.0 - 3.0 * math.pi)
        q = 1.0 / 3.0 - math.pi / 16.0 - 1.0 / (3.0 * (12.0 - 3.0 * math.pi))
        ag, axi = (1.0 - math.pi / 4.0) * ro ** 2, (1.0 - math.pi / 4.0) * ri ** 2
        ig, ixi = q * ro ** 4, q * ri ** 4
        area = 2.0 * t * (b + h - 2.0 * t) - (4.0 - math.pi) * (ro ** 2 - ri ** 2)
        ix = (
            b * h ** 3 / 12.0 - bi * hi ** 3 / 12.0
            - 4.0 * (ig + ag * (h / 2.0 - c * ro) ** 2)
            + 4.0 * (ixi + axi * (hi / 2.0 - c * ri) ** 2)
        )
        iy = (
            h * b ** 3 / 12.0 - hi * bi ** 3 / 12.0
            - 4.0 * (ig + ag * (b / 2.0 - c * ro) ** 2)
            + 4.0 * (ixi + axi * (bi / 2.0 - c * ri) ** 2)
        )
        wx, wy = ix / (h / 2.0), iy / (b / 2.0)
    values = (area, ix, iy, wx, wy)
    if not all(math.isfinite(value) and value > 0.0 for value in values):
        raise ValueError("propriedades tubulares calculadas devem ser finitas e positivas")
    return CalculatedSectionProperties(
        area, ix, iy, wx, wy, math.sqrt(ix / area), math.sqrt(iy / area),
        basis=(HOLLOW_CALCULATION_CONVENTION +
               "; calculation convention only, not product certification"
               if family != "CHS" else
               "Steel Structures exact circular annulus expressions"),
    )


def resolve_profile_mass(profile: ProfileDefinition):
    """Resolve explicit published kg/m for any family, retaining provenance."""
    source = profile.source_metadata
    if source is None:
        return profile
    mass = source.source_mass_per_length_kg_m
    if mass is None:
        mass = profile.physical_properties.mass_per_length_kg_m
    if mass is None or (source.mass_type != "published"
                        and source.source_mass_per_length_kg_m is None):
        return profile
    basis = None
    note = "Massa linear publicada em kg/m."
    if source.mass_basis == "normative_table":
        basis = f"{profile.catalog.source.source_name}, tabela {source.source_table}, p. {source.source_page}"
        note = "Massa nominal orientativa publicada na norma; preservada sem recalcular pela geometria CAD."
    return replace(
        profile, physical_properties=replace(profile.physical_properties, mass_per_length_kg_m=mass),
        property_provenance=immutable_mapping({
            **profile.property_provenance,
            "mass_per_length": PropertyProvenance("published", basis, note),
        }),
    )


def calculate_hollow_profile_properties(profile: ProfileDefinition):
    """Replace hollow fixture/catalog technical values at the library boundary."""
    if profile.geometry_type != "hollow_section":
        return profile
    dimensions = profile.geometry
    family = profile.family.upper()
    if family not in {"SHS", "RHS", "CHS"}:
        family = {"square": "SHS", "rectangular": "RHS", "circular": "CHS"}.get(
            profile.geometry_variant, family
        )
    kwargs = {"family": family, "t": dimensions["t"]}
    if family == "CHS":
        kwargs["d"] = dimensions["d"]
    elif family == "SHS":
        kwargs.update(h=dimensions["b"], b=dimensions["b"])
    else:
        kwargs.update(h=dimensions["h"], b=dimensions["b"])
    calculated = hollow_section_properties(**kwargs)
    names = ("ix", "iy", "wx", "wy", "rx", "ry")
    properties = immutable_mapping({name: getattr(calculated, name) for name in names})
    provenance = immutable_mapping({**profile.property_provenance, **{
        name: PropertyProvenance(
            "calculated", calculated.basis,
            "Calculated by Steel Structures; not a manufacturer-published value.",
        )
        for name in ("area",) + names
    }})
    if (
        profile.source_metadata is not None
        and profile.source_metadata.source_weight_p_kg_per_6m is not None
        and profile.physical_properties.mass_per_length_kg_m is not None
    ):
        provenance = immutable_mapping({
            **provenance,
            "mass_per_length": PropertyProvenance(
                "derived", "published weight p divided by 6 m",
                "p is manufacturer-published; mass per metre is calculated as p/6.",
            ),
        })
    physical = replace(profile.physical_properties, area_mm2=calculated.area)
    return replace(
        profile, physical_properties=physical, section_properties=properties,
        centroid=immutable_mapping({"x": calculated.centroid_x, "y": calculated.centroid_y}),
        property_provenance=provenance,
    )


def solid_section_properties(*, variant, **dimensions):
    """Exact ideal solid-section properties in local mm axes (X horizontal)."""
    from .solid_sections import solid_section_dimensions
    width, height = solid_section_dimensions(variant, dimensions)
    if variant == "circular":
        area = math.pi * width ** 2 / 4.0
        ix = iy = math.pi * width ** 4 / 64.0
    else:
        area = width * height
        ix, iy = width * height ** 3 / 12.0, height * width ** 3 / 12.0
    wx, wy = 2.0 * ix / height, 2.0 * iy / width
    values = (area, ix, iy, wx, wy)
    if not all(math.isfinite(value) and value > 0 for value in values):
        raise ValueError("propriedades maciças devem ser finitas e positivas")
    return CalculatedSectionProperties(
        area, ix, iy, wx, wy, math.sqrt(ix / area), math.sqrt(iy / area),
        basis="Steel Structures exact nominal solid-section expressions; local X horizontal, Y vertical",
    )


def calculate_solid_profile_properties(profile: ProfileDefinition):
    """Resolve technical area/properties and explicitly synthetic fixture mass."""
    if profile.geometry_type != "solid_section":
        return profile
    calculated = solid_section_properties(variant=profile.geometry_variant, **profile.geometry)
    names = ("ix", "iy", "wx", "wy", "rx", "ry")
    provenance = dict(profile.property_provenance)
    provenance.update({name: PropertyProvenance(
        "calculated", calculated.basis, "Geometria nominal ideal; calculada pela Steel Structures.",
    ) for name in ("area",) + names})
    mass = profile.physical_properties.mass_per_length_kg_m
    source = profile.source_metadata
    if source is not None and source.mass_type == "calculated_fixture":
        if (profile.catalog.source.source_type != "development_fixture"
                or profile.availability_status != "development_fixture"
                or source.density_kg_m3 is None):
            raise ValueError("massa de fixture requer origem de desenvolvimento e densidade explícita")
        expected_mass = calculated.area * source.density_kg_m3 * 1e-6
        if mass is not None and not math.isclose(mass, expected_mass, rel_tol=1e-12):
            raise ValueError("massa de fixture diverge de área nominal × densidade")
        mass = expected_mass
        provenance["mass_per_length"] = PropertyProvenance(
            "calculated_fixture", f"A * {source.density_kg_m3:g} kg/m³ * 1e-6",
            "Massa sintética de desenvolvimento; não é dado comercial.",
        )
    if mass is None or not math.isfinite(mass) or mass <= 0:
        raise ValueError("seção maciça requer massa publicada ou massa de fixture explícita")
    return replace(
        profile,
        physical_properties=replace(profile.physical_properties, area_mm2=calculated.area,
                                    mass_per_length_kg_m=mass),
        section_properties=immutable_mapping({name: getattr(calculated, name) for name in names}),
        centroid=immutable_mapping({"x": 0.0, "y": 0.0}),
        property_provenance=immutable_mapping(provenance),
    )


def _segment_state(segment, parameter):
    if isinstance(segment, LineSegment2D):
        dx = segment.end.x - segment.start.x
        dy = segment.end.y - segment.start.y
        return segment.start.x + dx * parameter, segment.start.y + dy * parameter, dx, dy
    if isinstance(segment, ArcSegment2D):
        angle = segment.start_angle + segment.sweep * parameter
        cosine, sine = math.cos(angle), math.sin(angle)
        rate = segment.sweep
        return (
            segment.center.x + segment.radius * cosine,
            segment.center.y + segment.radius * sine,
            -segment.radius * sine * rate,
            segment.radius * cosine * rate,
        )
    raise TypeError(f"segmento não suportado: {type(segment).__name__}")


def _adaptive_simpson(function, depth=18):
    start, end, middle = 0.0, 1.0, 0.5
    f_start, f_middle, f_end = function(start), function(middle), function(end)
    whole = (f_start + 4.0 * f_middle + f_end) / 6.0
    tolerance = max(1e-10, abs(whole) * 1e-12)

    def refine(left, right, f_left, f_mid, f_right, estimate, tol, remaining):
        center = (left + right) / 2.0
        left_mid, right_mid = (left + center) / 2.0, (center + right) / 2.0
        f_left_mid, f_right_mid = function(left_mid), function(right_mid)
        left_value = (center - left) * (f_left + 4.0 * f_left_mid + f_mid) / 6.0
        right_value = (right - center) * (f_mid + 4.0 * f_right_mid + f_right) / 6.0
        combined = left_value + right_value
        if remaining <= 0 or abs(combined - estimate) <= 15.0 * tol:
            return combined + (combined - estimate) / 15.0
        return (
            refine(left, center, f_left, f_left_mid, f_mid,
                   left_value, tol / 2.0, remaining - 1)
            + refine(center, right, f_mid, f_right_mid, f_right,
                     right_value, tol / 2.0, remaining - 1)
        )

    return refine(start, end, f_start, f_middle, f_end, whole, tolerance, depth)


def _path_integrals(path):
    totals = [0.0] * 5
    for segment in path.segments:
        def integrate(index):
            def value(parameter):
                x, y, dx, dy = _segment_state(segment, parameter)
                return (
                    0.5 * (x * dy - y * dx),
                    0.5 * x * x * dy,
                    -0.5 * y * y * dx,
                    -(y ** 3) * dx / 3.0,
                    (x ** 3) * dy / 3.0,
                )[index]
            # Semicircle moment integrands can alias at Simpson's initial
            # samples and falsely appear converged. Seed angular intervals
            # before adapting; straight segments retain the existing path.
            parts = (max(1, math.ceil(abs(segment.sweep) / (math.pi / 4)))
                     if isinstance(segment, ArcSegment2D) else 1)
            return sum(_adaptive_simpson(
                lambda parameter, offset=offset: value((offset + parameter) / parts) / parts
            ) for offset in range(parts))
        for index in range(5):
            totals[index] += integrate(index)
    return tuple(totals)


def section_geometric_properties(geometry):
    """Return centroidal area moments from the exact line/arc contour."""
    paths = ((geometry.outer_path, 1.0),) + tuple(
        (path, -1.0) for path in geometry.inner_paths
    )
    totals = [0.0] * 5
    for path, desired_sign in paths:
        values = _path_integrals(path)
        factor = desired_sign * (1.0 if values[0] >= 0.0 else -1.0)
        for index, value in enumerate(values):
            totals[index] += factor * value
    area, first_x, first_y, ix_origin, iy_origin = totals
    if area <= 0.0:
        raise ValueError("geometria deve possuir área positiva")
    centroid_x, centroid_y = first_x / area, first_y / area
    return GeometricSectionProperties(
        area, centroid_x, centroid_y,
        ix_origin - area * centroid_y ** 2,
        iy_origin - area * centroid_x ** 2,
    )


def resolve_effective_section_properties(profile: ProfileDefinition):
    """Apply one centralized, catalog-declared calculated-property decision."""
    override = profile.section_property_override
    if override is None:
        return profile
    if override.basis != "nominal_revit_geometry":
        raise ValueError(f"base de propriedade efetiva não suportada: {override.basis}")
    geometry = build_section_geometry(profile)
    calculated = section_geometric_properties(geometry)
    half_width = max(
        abs(geometry.bounds.min_x - calculated.centroid_x),
        abs(geometry.bounds.max_x - calculated.centroid_x),
    )
    values = {
        "iy": calculated.iy,
        "wy": calculated.iy / half_width,
        "ry": math.sqrt(calculated.iy / calculated.area),
    }
    effective = dict(profile.section_properties)
    for name in override.properties:
        effective[name] = values[name]
    return replace(profile, section_properties=immutable_mapping(effective))


__all__ = [
    "solid_section_properties", "calculate_solid_profile_properties",
    "CalculatedSectionProperties", "GeometricSectionProperties",
    "HOLLOW_CALCULATION_CONVENTION", "calculate_hollow_profile_properties",
    "hollow_section_properties", "rectangular_hollow_calculation_radii",
    "resolve_effective_section_properties",
    "section_geometric_properties",
]
