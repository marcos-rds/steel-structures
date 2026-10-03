# SPDX-License-Identifier: LGPL-2.1-or-later
"""Schema-v2 validation and canonical unit conversion."""

from __future__ import annotations

import math
import re
from decimal import Decimal
from pathlib import Path

from .models import (
    CatalogMetadata,
    CatalogSource,
    CategoryDefinition,
    ManufacturerDefinition,
    IssuerDefinition,
    PhysicalProperties,
    ProfileDefinition,
    ProfileRef,
    ProfileSourceMetadata,
    SectionPropertyOverride,
    SeriesDefinition,
    SupplyConditionDefinition,
    immutable_mapping,
)

ID_PATTERN = re.compile(r"^[a-z0-9]+(?:[.-][a-z0-9]+)*$")
UNIT_FACTORS = {
    "length": {"mm": 1.0},
    "centroid": {"mm": 1.0, "cm": 10.0},
    "radius_of_gyration": {"mm": 1.0, "cm": 10.0},
    "area": {"mm2": 1.0, "cm2": 100.0},
    "mass_per_length": {"kg/m": 1.0},
    "section_modulus": {"mm3": 1.0, "cm3": 1_000.0},
    "second_moment_of_area": {"mm4": 1.0, "cm4": 10_000.0},
    "warping_constant": {"mm6": 1.0, "cm6": 1_000_000.0},
    "surface_area_per_length": {"m2/m": 1.0},
    "dimensionless": {"1": 1.0},
}
SECTION_PROPERTY_QUANTITIES = {
    "ix": "second_moment_of_area",
    "iy": "second_moment_of_area",
    "j": "second_moment_of_area",
    "it": "second_moment_of_area",
    "wx": "section_modulus",
    "wy": "section_modulus",
    "zx": "section_modulus",
    "zy": "section_modulus",
    "rx": "radius_of_gyration",
    "ry": "radius_of_gyration",
    "rt": "radius_of_gyration",
    "rz_min": "radius_of_gyration",
    "r0": "radius_of_gyration",
    "x0": "centroid",
    "cw": "warping_constant",
    "slenderness_flange": "dimensionless",
    "slenderness_web": "dimensionless",
}

AVAILABILITY_STATUSES = {
    "standard", "made_to_order", "consultation", "development_fixture",
    "normative_table",
}


class CatalogError(Exception):
    """Base error for the typed profile-catalog API."""


class CatalogValidationError(CatalogError):
    """Raised when a catalog does not satisfy schema v2."""


class ProfileNotFoundError(CatalogError):
    """Raised when a ProfileRef is not present in the library."""


def _error(path: Path, catalog_id: str, message: str) -> CatalogValidationError:
    return CatalogValidationError(f"{path.name} [{catalog_id}]: {message}")


def _mapping(value, path, catalog_id, field):
    if not isinstance(value, dict):
        raise _error(path, catalog_id, f"{field} deve ser um objeto")
    return value


def _list(value, path, catalog_id, field):
    if not isinstance(value, list):
        raise _error(path, catalog_id, f"{field} deve ser uma lista")
    return value


def _string(value, path, catalog_id, field, optional=False):
    if optional and value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise _error(path, catalog_id, f"{field} deve ser uma string não vazia")
    return value.strip()


def _id(value, path, catalog_id, field):
    value = _string(value, path, catalog_id, field)
    if not value.isascii() or not ID_PATTERN.fullmatch(value):
        raise _error(path, catalog_id, f"{field} possui ID inválido: {value!r}")
    return value


def _number(value, path, catalog_id, field, positive=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise _error(path, catalog_id, f"{field} deve ser numérico")
    result = float(value)
    if not math.isfinite(result):
        raise _error(path, catalog_id, f"{field} não pode ser NaN ou infinito")
    if positive and result <= 0.0:
        raise _error(path, catalog_id, f"{field} deve ser positivo")
    return result


def _optional_positive_integer(value, path, catalog_id, field):
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise _error(path, catalog_id, f"{field} deve ser inteiro positivo")
    return value


def convert_to_canonical(value, quantity: str, unit: str) -> float:
    """Convert a finite value to the canonical mm-based internal system."""
    if quantity not in UNIT_FACTORS or unit not in UNIT_FACTORS[quantity]:
        raise CatalogValidationError(
            f"unidade desconhecida para {quantity}: {unit!r}"
        )
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise CatalogValidationError(f"valor não numérico para {quantity}")
    result = float(value)
    if not math.isfinite(result):
        raise CatalogValidationError(f"valor não finito para {quantity}")
    return float(Decimal(str(value)) * Decimal(str(UNIT_FACTORS[quantity][unit])))


def _validate_units(raw, path, catalog_id):
    raw = _mapping(raw, path, catalog_id, "units")
    required = ("length", "mass_per_length", "area")
    units = {}
    for quantity in required:
        unit = _string(raw.get(quantity), path, catalog_id, f"units.{quantity}")
        if unit not in UNIT_FACTORS[quantity]:
            raise _error(
                path, catalog_id,
                f"units.{quantity} possui unidade desconhecida: {unit!r}",
            )
        units[quantity] = unit
    for quantity, unit in raw.items():
        if quantity not in UNIT_FACTORS:
            raise _error(path, catalog_id, f"grupo de unidade desconhecido: {quantity!r}")
        if unit not in UNIT_FACTORS[quantity]:
            raise _error(path, catalog_id, f"units.{quantity} possui unidade desconhecida: {unit!r}")
        units[quantity] = unit
    return immutable_mapping(units)


def validate_catalog_payload(payload, path: Path):
    """Validate one schema-v2 payload and build immutable domain objects."""
    path = Path(path)
    if not isinstance(payload, dict):
        raise _error(path, "unknown", "a raiz deve ser um objeto")
    if payload.get("schema_version") != 2:
        raise _error(path, "unknown", "schema_version deve ser 2")

    raw_catalog = _mapping(payload.get("catalog"), path, "unknown", "catalog")
    catalog_id = _id(raw_catalog.get("id"), path, "unknown", "catalog.id")
    manufacturer_raw = raw_catalog.get("manufacturer")
    manufacturer = None
    if manufacturer_raw is not None:
        manufacturer_raw = _mapping(
            manufacturer_raw, path, catalog_id, "catalog.manufacturer"
        )
        manufacturer = ManufacturerDefinition(
            id=_id(manufacturer_raw.get("id"), path, catalog_id, "manufacturer.id"),
            name=_string(manufacturer_raw.get("name"), path, catalog_id, "manufacturer.name"),
        )
    issuer_raw = raw_catalog.get("issuer")
    issuer = None
    if issuer_raw is not None:
        issuer_raw = _mapping(issuer_raw, path, catalog_id, "catalog.issuer")
        issuer = IssuerDefinition(
            id=_id(issuer_raw.get("id"), path, catalog_id, "issuer.id"),
            name=_string(issuer_raw.get("name"), path, catalog_id, "issuer.name"),
        )
    if manufacturer is None and issuer is None:
        raise _error(path, catalog_id, "catálogo requer manufacturer ou issuer")
    region = _string(raw_catalog.get("region"), path, catalog_id, "catalog.region", True)
    if region is not None and re.fullmatch(r"[A-Z]{2}", region) is None:
        raise _error(path, catalog_id, "catalog.region deve conter duas letras ASCII maiúsculas")
    catalog_pack = raw_catalog.get("catalog_pack")
    if catalog_pack is not None:
        catalog_pack = _id(catalog_pack, path, catalog_id, "catalog.catalog_pack")
    source_raw = _mapping(raw_catalog.get("source"), path, catalog_id, "catalog.source")
    source_density = source_raw.get("density_kg_m3")
    if source_density is not None:
        source_density = _number(
            source_density, path, catalog_id, "source.density_kg_m3", True,
        )
    source = CatalogSource(
        source_name=_string(source_raw.get("source_name"), path, catalog_id, "source.source_name"),
        source_revision=_string(source_raw.get("source_revision"), path, catalog_id, "source.source_revision", True),
        source_url=_string(source_raw.get("source_url"), path, catalog_id, "source.source_url", True),
        source_date=_string(source_raw.get("source_date"), path, catalog_id, "source.source_date", True),
        notes=_string(source_raw.get("notes"), path, catalog_id, "source.notes", True),
        source_type=_string(source_raw.get("source_type"), path, catalog_id, "source.source_type", True),
        density_kg_m3=source_density,
    )
    units = _validate_units(payload.get("units"), path, catalog_id)
    supply_conditions = []
    supply_codes = set()
    for index, value in enumerate(_list(
        raw_catalog.get("supply_condition_definitions", []), path, catalog_id,
        "catalog.supply_condition_definitions",
    )):
        value = _mapping(
            value, path, catalog_id,
            f"catalog.supply_condition_definitions[{index}]",
        )
        code = _string(value.get("code"), path, catalog_id, f"supply condition {index}.code")
        if code in supply_codes:
            raise _error(path, catalog_id, f"código de condição de fornecimento duplicado: {code}")
        supply_codes.add(code)
        availability = _string(
            value.get("availability"), path, catalog_id,
            f"supply condition {code}.availability",
        )
        if availability not in {"normal", "special_consultation"}:
            raise _error(path, catalog_id, f"condição de fornecimento {code}: disponibilidade inválida")
        source_page = value.get("source_page")
        if isinstance(source_page, bool) or not isinstance(source_page, int) or source_page <= 0:
            raise _error(path, catalog_id, f"condição de fornecimento {code}: source_page inválida")
        supply_conditions.append(SupplyConditionDefinition(
            code=code,
            description=_string(
                value.get("description"), path, catalog_id,
                f"supply condition {code}.description",
            ),
            availability=availability,
            source_page=source_page,
        ))
    metadata = CatalogMetadata(
        id=catalog_id,
        name=_string(raw_catalog.get("name"), path, catalog_id, "catalog.name"),
        catalog_version=_string(raw_catalog.get("catalog_version"), path, catalog_id, "catalog.catalog_version"),
        manufacturer=manufacturer,
        source=source,
        units=units,
        standard_references=tuple(
            _string(value, path, catalog_id, "catalog.standard_references")
            for value in _list(raw_catalog.get("standard_references", []), path, catalog_id, "catalog.standard_references")
        ),
        material_notes=_string(raw_catalog.get("material_notes"), path, catalog_id, "catalog.material_notes", True),
        issuer=issuer,
        supply_condition_definitions=tuple(supply_conditions),
        region=region,
        country=_string(raw_catalog.get("country"), path, catalog_id, "catalog.country", True),
        catalog_pack=catalog_pack,
    )

    categories = []
    category_ids = set()
    for index, raw in enumerate(_list(payload.get("categories"), path, catalog_id, "categories")):
        raw = _mapping(raw, path, catalog_id, f"categories[{index}]")
        category_id = _id(raw.get("id"), path, catalog_id, f"categories[{index}].id")
        if category_id in category_ids:
            raise _error(path, catalog_id, f"categoria duplicada: {category_id}")
        category_ids.add(category_id)
        categories.append(CategoryDefinition(catalog_id, category_id, _string(raw.get("name"), path, catalog_id, f"categories[{index}].name")))

    series = []
    series_by_id = {}
    for index, raw in enumerate(_list(payload.get("series"), path, catalog_id, "series")):
        raw = _mapping(raw, path, catalog_id, f"series[{index}]")
        series_id = _id(raw.get("id"), path, catalog_id, f"series[{index}].id")
        if series_id in series_by_id:
            raise _error(path, catalog_id, f"série duplicada: {series_id}")
        category_id = _id(raw.get("category_id"), path, catalog_id, f"series[{index}].category_id")
        if category_id not in category_ids:
            raise _error(path, catalog_id, f"série {series_id} referencia categoria inexistente: {category_id}")
        definition = SeriesDefinition(
            catalog_id, series_id, category_id,
            _string(raw.get("name"), path, catalog_id, f"series[{index}].name"),
            _string(raw.get("family"), path, catalog_id, f"series[{index}].family"),
            _string(raw.get("geometry_type"), path, catalog_id, f"series[{index}].geometry_type"),
            _string(raw.get("geometry_variant"), path, catalog_id, f"series[{index}].geometry_variant", True),
            _string(raw.get("geometry_notes"), path, catalog_id, f"series[{index}].geometry_notes", True),
        )
        series_by_id[series_id] = definition
        series.append(definition)

    profiles = []
    profile_ids = set()
    designations_by_series = set()
    canonical_rhs_dimensions = set()
    for index, raw in enumerate(_list(payload.get("profiles"), path, catalog_id, "profiles")):
        raw = _mapping(raw, path, catalog_id, f"profiles[{index}]")
        profile_id = _id(raw.get("id"), path, catalog_id, f"profiles[{index}].id")
        if profile_id in profile_ids:
            raise _error(path, catalog_id, f"perfil duplicado: {profile_id}")
        profile_ids.add(profile_id)
        series_id = _id(raw.get("series_id"), path, catalog_id, f"profiles[{index}].series_id")
        if series_id not in series_by_id:
            raise _error(path, catalog_id, f"perfil {profile_id} referencia série inexistente: {series_id}")
        series_definition = series_by_id[series_id]
        designation = _string(raw.get("designation"), path, catalog_id, f"profiles[{index}].designation")
        designation_key = (series_id, designation)
        if designation_key in designations_by_series:
            raise _error(path, catalog_id, f"designação duplicada na série {series_id}: {designation!r}")
        designations_by_series.add(designation_key)
        geometry_type = _string(raw.get("geometry_type"), path, catalog_id, f"profiles[{index}].geometry_type")
        if geometry_type != series_definition.geometry_type:
            raise _error(path, catalog_id, f"perfil {profile_id}: geometry_type diverge da série")
        geometry_raw = _mapping(raw.get("geometry"), path, catalog_id, f"profiles[{index}].geometry")
        geometry = {}
        if geometry_type in {"i_section", "channel_section", "tee_section"}:
            for parameter in ("d", "bf", "tw", "tf"):
                geometry[parameter] = convert_to_canonical(
                    _number(geometry_raw.get(parameter), path, catalog_id, f"profiles[{index}].geometry.{parameter}", True),
                    "length", units["length"],
                )
            for parameter in ("h", "d_prime"):
                if parameter in geometry_raw:
                    geometry[parameter] = convert_to_canonical(
                        _number(geometry_raw.get(parameter), path, catalog_id, f"profiles[{index}].geometry.{parameter}", True),
                        "length", units["length"],
                    )
            if geometry["tw"] >= geometry["bf"]:
                raise _error(path, catalog_id, f"perfil {profile_id}: tw deve ser menor que bf")
            if geometry_type in {"i_section", "channel_section"} and 2.0 * geometry["tf"] >= geometry["d"]:
                raise _error(path, catalog_id, f"perfil {profile_id}: 2*tf deve ser menor que d")
            if geometry_type == "tee_section" and geometry["tf"] >= geometry["d"]:
                raise _error(path, catalog_id, f"perfil {profile_id}: tf deve ser menor que d")
            if geometry_type == "channel_section" and series_definition.geometry_variant == "tapered_flange":
                for parameter in ("r1", "r2"):
                    geometry[parameter] = convert_to_canonical(
                        _number(geometry_raw.get(parameter), path, catalog_id,
                                f"profiles[{index}].geometry.{parameter}", True),
                        "length", units["length"],
                    )
                geometry["flange_angle"] = _number(
                    geometry_raw.get("flange_angle"), path, catalog_id,
                    f"profiles[{index}].geometry.flange_angle", True,
                )
                if not 0.0 < geometry["flange_angle"] < 45.0:
                    raise _error(path, catalog_id, f"perfil {profile_id}: flange_angle deve estar entre 0 e 45 graus")
            if geometry_type == "i_section" and series_definition.geometry_variant == "tapered_flange":
                for parameter in ("r1", "r2", "tl"):
                    geometry[parameter] = convert_to_canonical(
                        _number(geometry_raw.get(parameter), path, catalog_id,
                                f"profiles[{index}].geometry.{parameter}", True),
                        "length", units["length"],
                    )
                geometry["flange_angle"] = _number(
                    geometry_raw.get("flange_angle"), path, catalog_id,
                    f"profiles[{index}].geometry.flange_angle", True,
                )
                if not 0.0 < geometry["flange_angle"] < 45.0:
                    raise _error(path, catalog_id, f"perfil {profile_id}: flange_angle deve estar entre 0 e 45 graus")
                if geometry["tl"] >= (geometry["bf"] - geometry["tw"]) / 2.0:
                    raise _error(path, catalog_id, f"perfil {profile_id}: TL deve ficar antes da alma")
        elif geometry_type == "cold_formed_channel":
            if series_definition.geometry_variant != "stiffened_u":
                raise _error(path, catalog_id, "variante cold-formed ainda não suportada")
            for parameter in ("bw", "bf", "D", "tn", "t", "ri"):
                geometry[parameter] = convert_to_canonical(
                    _number(geometry_raw.get(parameter), path, catalog_id,
                            f"profiles[{index}].geometry.{parameter}", True),
                    "length", units["length"],
                )
            from .ue_section import nbr_6355_expected_internal_radius, ue_derived_dimensions
            try:
                ue_derived_dimensions(**{
                    key: geometry[key] for key in ("bw", "bf", "D", "t", "ri")
                })
            except ValueError as exc:
                raise _error(path, catalog_id, f"perfil {profile_id}: {exc}") from exc
            is_nbr_6355_a3_uncoated = (
                catalog_id == "abnt-nbr-6355-2012-a3"
                and series_id == "ue-nbr-6355"
            )
            if (is_nbr_6355_a3_uncoated
                    and not math.isclose(geometry["t"], geometry["tn"],
                                         rel_tol=1.0e-12, abs_tol=1.0e-9)):
                raise _error(
                    path, catalog_id,
                    f"perfil {profile_id}: Tabela A.3, aço sem revestimento, exige t = tn",
                )
            expected_ri = nbr_6355_expected_internal_radius(geometry["tn"])
            if not math.isclose(geometry["ri"], expected_ri, abs_tol=1.0e-9):
                raise _error(path, catalog_id,
                             f"perfil {profile_id}: ri diverge da regra da Tabela A.3")
        elif geometry_type == "equal_angle":
            for parameter in ("b", "t"):
                geometry[parameter] = convert_to_canonical(
                    _number(geometry_raw.get(parameter), path, catalog_id, f"profiles[{index}].geometry.{parameter}", True),
                    "length", units["length"],
                )
            if geometry["t"] >= geometry["b"]:
                raise _error(path, catalog_id, f"perfil {profile_id}: t deve ser menor que b")
        elif geometry_type == "solid_section":
            from .solid_sections import (
                SOLID_SECTION_FAMILIES, SOLID_SECTION_PARAMETERS, solid_section_dimensions,
            )
            variant = series_definition.geometry_variant
            if (variant not in SOLID_SECTION_FAMILIES
                    or series_definition.family != SOLID_SECTION_FAMILIES[variant]):
                raise _error(path, catalog_id, f"perfil {profile_id}: família/variante maciça incompatível")
            keys = SOLID_SECTION_PARAMETERS[variant]
            if set(geometry_raw) != set(keys):
                raise _error(path, catalog_id, f"perfil {profile_id}: dimensões esperadas: {', '.join(keys)}")
            geometry = {name: _number(geometry_raw[name], path, catalog_id,
                                     f"geometry.{name}", True) for name in keys}
            try:
                solid_section_dimensions(variant, geometry)
            except ValueError as exc:
                raise _error(path, catalog_id, f"perfil {profile_id}: {exc}") from exc
        elif geometry_type == "hollow_section":
            variant = series_definition.geometry_variant
            expected_family = {"square": "SHS", "rectangular": "RHS", "circular": "CHS"}
            if variant not in expected_family or series_definition.family.upper() != expected_family[variant]:
                raise _error(path, catalog_id, f"perfil {profile_id}: família/variante tubular incompatível")
            keys = ("d", "t") if variant == "circular" else (("b", "t") if variant == "square" else ("h", "b", "t"))
            if set(geometry_raw) != set(keys):
                raise _error(path, catalog_id, f"perfil {profile_id}: dimensões esperadas: {', '.join(keys)}")
            for parameter in keys:
                geometry[parameter] = convert_to_canonical(
                    _number(geometry_raw.get(parameter), path, catalog_id,
                            f"profiles[{index}].geometry.{parameter}", True),
                    "length", units["length"],
                )
            t = geometry["t"]
            if variant == "circular" and geometry["d"] <= 2.0 * t:
                raise _error(path, catalog_id, f"perfil {profile_id}: CHS exige d > 2*t")
            if variant == "square" and geometry["b"] <= 4.0 * t:
                raise _error(path, catalog_id, f"perfil {profile_id}: SHS exige b > 4*t")
            if variant == "rectangular":
                h, b = geometry["h"], geometry["b"]
                key = (max(h, b), min(h, b), t)
                if key in canonical_rhs_dimensions:
                    raise _error(path, catalog_id, f"perfil {profile_id}: dimensões RHS duplicadas após normalização")
                canonical_rhs_dimensions.add(key)
                if h <= b:
                    raise _error(path, catalog_id, f"perfil {profile_id}: RHS exige H > B")
                if b <= 4.0 * t:
                    raise _error(path, catalog_id, f"perfil {profile_id}: RHS exige B > 4*t")
        else:
            raise _error(path, catalog_id, f"geometry_type não suportado: {geometry_type!r}")

        physical_raw = _mapping(raw.get("physical_properties", {}), path, catalog_id, f"profiles[{index}].physical_properties")
        mass = physical_raw.get("mass_per_length")
        area = physical_raw.get("area")
        surface = physical_raw.get("surface_area_per_length")
        physical = PhysicalProperties(
            mass_per_length_kg_m=None if mass is None else convert_to_canonical(
                _number(mass, path, catalog_id, f"profiles[{index}].physical_properties.mass_per_length", True),
                "mass_per_length", units["mass_per_length"],
            ),
            area_mm2=None if area is None else convert_to_canonical(
                _number(area, path, catalog_id, f"profiles[{index}].physical_properties.area", True),
                "area", units["area"],
            ),
            surface_area_per_length_m2_m=None if surface is None else convert_to_canonical(
                _number(surface, path, catalog_id, f"profiles[{index}].physical_properties.surface_area_per_length", True),
                "surface_area_per_length", units["surface_area_per_length"],
            ),
        )
        section_raw = _mapping(raw.get("section_properties", {}), path, catalog_id, f"profiles[{index}].section_properties")
        section = {}
        for key, value in section_raw.items():
            quantity = SECTION_PROPERTY_QUANTITIES.get(key.casefold())
            if quantity is None:
                raise _error(path, catalog_id, f"propriedade de seção desconhecida: {key!r}")
            if quantity not in units:
                raise _error(path, catalog_id, f"units.{quantity} é necessária para {key}")
            section[key] = convert_to_canonical(
                _number(value, path, catalog_id, f"profiles[{index}].section_properties.{key}", True),
                quantity, units[quantity],
            )
        override_raw = raw.get("section_property_override")
        override = None
        if override_raw is not None:
            override_raw = _mapping(
                override_raw, path, catalog_id,
                f"profiles[{index}].section_property_override",
            )
            basis = _string(
                override_raw.get("basis"), path, catalog_id,
                f"profiles[{index}].section_property_override.basis",
            )
            if basis != "nominal_revit_geometry":
                raise _error(path, catalog_id, f"perfil {profile_id}: base efetiva não suportada")
            names_raw = _list(
                override_raw.get("properties"), path, catalog_id,
                f"profiles[{index}].section_property_override.properties",
            )
            names = tuple(_string(
                value, path, catalog_id,
                f"profiles[{index}].section_property_override.properties",
            ) for value in names_raw)
            if not names or len(names) != len(set(names)) or set(names) != {"iy", "wy", "ry"}:
                raise _error(path, catalog_id, f"perfil {profile_id}: override deve abranger iy, wy e ry")
            if any(name not in section for name in names):
                raise _error(path, catalog_id, f"perfil {profile_id}: propriedade publicada ausente")
            if (geometry_type, series_definition.geometry_variant) != ("i_section", "tapered_flange"):
                raise _error(path, catalog_id, f"perfil {profile_id}: override geométrico incompatível")
            override = SectionPropertyOverride(
                basis=basis,
                properties=names,
                note=_string(
                    override_raw.get("note"), path, catalog_id,
                    f"profiles[{index}].section_property_override.note",
                ),
            )
        centroid_raw = _mapping(raw.get("centroid", {}), path, catalog_id, f"profiles[{index}].centroid")
        centroid = {}
        centroid_from_top_flange_face = None
        for key, value in centroid_raw.items():
            if key != "x":
                raise _error(path, catalog_id, f"coordenada de centroide desconhecida: {key!r}")
            converted_centroid = convert_to_canonical(
                _number(value, path, catalog_id, f"profiles[{index}].centroid.{key}", True),
                "centroid", units.get("centroid", units["length"]),
            )
            if geometry_type == "tee_section":
                centroid_from_top_flange_face = converted_centroid
            else:
                centroid[key] = converted_centroid
        aliases_raw = _list(raw.get("aliases", []), path, catalog_id, f"profiles[{index}].aliases")
        aliases = tuple(_string(value, path, catalog_id, f"profiles[{index}].aliases") for value in aliases_raw)
        markers_raw = _list(raw.get("catalog_markers", []), path, catalog_id, f"profiles[{index}].catalog_markers")
        markers = tuple(_string(value, path, catalog_id, f"profiles[{index}].catalog_markers") for value in markers_raw)
        if len(markers) != len(set(markers)):
            raise _error(path, catalog_id, f"perfil {profile_id}: catalog_markers duplicados")
        availability = _string(raw.get("availability_status"), path, catalog_id, f"profiles[{index}].availability_status")
        if availability not in AVAILABILITY_STATUSES:
            raise _error(path, catalog_id, f"perfil {profile_id}: availability_status inválido: {availability!r}")
        if availability == "normative_table" and source.source_type != "normative":
            raise _error(path, catalog_id,
                         f"perfil {profile_id}: availability_status normative_table exige origem normativa")
        geometry_status = _string(
            raw.get("geometry_status", "released"), path, catalog_id,
            f"profiles[{index}].geometry_status",
        )
        if geometry_status not in {"released", "pending_technical_review"}:
            raise _error(path, catalog_id, f"perfil {profile_id}: geometry_status inválido: {geometry_status!r}")
        source_metadata_raw = raw.get("source_metadata")
        source_metadata = None
        if source_metadata_raw is not None:
            source_metadata_raw = _mapping(
                source_metadata_raw, path, catalog_id,
                f"profiles[{index}].source_metadata",
            )
            source_dimensions_raw = _mapping(
                source_metadata_raw.get("source_dimensions", {}), path, catalog_id,
                f"profiles[{index}].source_metadata.source_dimensions",
            )
            source_dimensions = {
                _string(name, path, catalog_id, "source dimension name"):
                _number(value, path, catalog_id, f"source_dimensions.{name}", True)
                for name, value in source_dimensions_raw.items()
            }
            source_locations = {
                name: _optional_positive_integer(
                    source_metadata_raw.get(name), path, catalog_id,
                    f"perfil {profile_id}: {name}",
                ) for name in ("source_page", "source_pdf_page", "source_row")
            }
            def optional_number(name):
                value = source_metadata_raw.get(name)
                return None if value is None else _number(
                    value, path, catalog_id, f"source_metadata.{name}", True,
                )
            weight = optional_number("source_weight_p_kg_per_6m")
            basis = optional_number("source_weight_basis_mm")
            published_mass = optional_number("source_mass_per_length_kg_m")
            density = optional_number("density_kg_m3")
            mass_type = _string(source_metadata_raw.get("mass_type"), path, catalog_id,
                                "source_metadata.mass_type", True)
            if mass_type not in {None, "published", "derived", "calculated_fixture"}:
                raise _error(path, catalog_id, f"perfil {profile_id}: mass_type inválido")
            mass_basis = _string(
                source_metadata_raw.get("mass_basis"), path, catalog_id,
                "source_metadata.mass_basis", True,
            )
            if mass_basis not in {None, "normative_table"}:
                raise _error(path, catalog_id, f"perfil {profile_id}: mass_basis inválido")
            if mass_basis == "normative_table" and (
                source.source_type != "normative"
                or mass_type not in {None, "published"}
                or (published_mass is None and (
                    mass_type != "published" or physical.mass_per_length_kg_m is None
                ))
            ):
                raise _error(path, catalog_id,
                             f"perfil {profile_id}: normative_table exige origem normativa e massa publicada")
            if (weight is None) != (basis is None) or (basis is not None and basis != 6000):
                raise _error(path, catalog_id, f"perfil {profile_id}: peso por 6 m requer peso e base 6000 mm")
            if weight is not None:
                if mass_type not in {None, "derived"} or published_mass is not None:
                    raise _error(path, catalog_id, f"perfil {profile_id}: origens de massa incompatíveis")
                if physical.mass_per_length_kg_m is None or not math.isclose(
                    physical.mass_per_length_kg_m, weight / 6.0, rel_tol=1e-12,
                ):
                    raise _error(path, catalog_id, f"perfil {profile_id}: massa deve ser p/6")
            if mass_type == "derived" and weight is None:
                raise _error(path, catalog_id, f"perfil {profile_id}: massa derivada requer peso de origem")
            if published_mass is not None and (
                mass_type not in {None, "published"}
                or (physical.mass_per_length_kg_m is not None and not math.isclose(
                    published_mass, physical.mass_per_length_kg_m, rel_tol=1e-12))
            ):
                raise _error(path, catalog_id, f"perfil {profile_id}: massa publicada conflitante")
            if mass_type == "calculated_fixture":
                if (source.source_type != "development_fixture"
                        or availability != "development_fixture" or density is None
                        or published_mass is not None or weight is not None
                        or geometry_type != "solid_section"):
                    raise _error(path, catalog_id, f"perfil {profile_id}: massa de fixture exige origem dev, seção maciça e densidade")
            elif density is not None:
                raise _error(path, catalog_id, f"perfil {profile_id}: densidade de cálculo exige calculated_fixture")
            source_metadata = ProfileSourceMetadata(
                source_page=source_locations["source_page"],
                source_pdf_page=source_locations["source_pdf_page"],
                source_row=source_locations["source_row"],
                source_table=_string(
                    source_metadata_raw.get("source_table"), path, catalog_id,
                    "source_metadata.source_table", True,
                ),
                mass_basis=mass_basis,
                source_weight_p_kg_per_6m=weight,
                source_weight_basis_mm=basis,
                mass_type=mass_type,
                source_mass_per_length_kg_m=published_mass,
                density_kg_m3=density,
                source_designation=_string(
                    source_metadata_raw.get("source_designation"), path, catalog_id,
                    f"profiles[{index}].source_metadata.source_designation", True,
                ),
                source_inches=_string(
                    source_metadata_raw.get("source_inches"), path, catalog_id,
                    f"profiles[{index}].source_metadata.source_inches", True,
                ),
                source_dimensions=immutable_mapping(source_dimensions),
                availability_note=_string(
                    source_metadata_raw.get("availability_note"), path, catalog_id,
                    f"profiles[{index}].source_metadata.availability_note", True,
                ),
            )
        profiles.append(ProfileDefinition(
            ref=ProfileRef(catalog_id, profile_id),
            designation=designation,
            equivalent_designation=_string(raw.get("equivalent_designation"), path, catalog_id, f"profiles[{index}].equivalent_designation", True),
            aliases=aliases,
            catalog_markers=markers,
            availability_status=availability,
            geometry_status=geometry_status,
            series_id=series_id,
            category_id=series_definition.category_id,
            manufacturer=manufacturer,
            family=series_definition.family,
            geometry_type=geometry_type,
            geometry_variant=series_definition.geometry_variant,
            geometry_notes=series_definition.geometry_notes,
            geometry=immutable_mapping(geometry),
            physical_properties=physical,
            section_properties=immutable_mapping(section),
            reported_section_properties=immutable_mapping(section),
            section_property_override=override,
            centroid_from_top_flange_face=centroid_from_top_flange_face,
            centroid=immutable_mapping(centroid),
            catalog=metadata,
            source_metadata=source_metadata,
        ))
    return metadata, tuple(categories), tuple(series), tuple(profiles)
