# SPDX-License-Identifier: LGPL-2.1-or-later
"""Immutable domain models for structural profile catalogs."""

from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Mapping


def immutable_mapping(values: Mapping[str, Any] | None = None) -> Mapping[str, Any]:
    """Return a detached, read-only mapping suitable for frozen models."""
    return MappingProxyType(dict(values or {}))


@dataclass(frozen=True)
class ProfileRef:
    catalog_id: str
    profile_id: str


@dataclass(frozen=True)
class CatalogSource:
    source_name: str
    source_revision: str | None = None
    source_url: str | None = None
    source_date: str | None = None
    notes: str | None = None
    source_type: str | None = None


@dataclass(frozen=True)
class ManufacturerDefinition:
    id: str
    name: str


@dataclass(frozen=True)
class IssuerDefinition:
    """Organization responsible for a normative catalog source."""

    id: str
    name: str


@dataclass(frozen=True)
class SupplyConditionDefinition:
    """Catalog-level glossary entry; never an inferred per-profile attribute."""

    code: str
    description: str
    availability: str
    source_page: int | None = None


@dataclass(frozen=True)
class CatalogMetadata:
    id: str
    name: str
    catalog_version: str
    manufacturer: ManufacturerDefinition | None
    source: CatalogSource
    units: Mapping[str, str]
    standard_references: tuple[str, ...] = ()
    material_notes: str | None = None
    issuer: IssuerDefinition | None = None
    supply_condition_definitions: tuple[SupplyConditionDefinition, ...] = ()


@dataclass(frozen=True)
class CategoryDefinition:
    catalog_id: str
    id: str
    name: str


@dataclass(frozen=True)
class SeriesDefinition:
    catalog_id: str
    id: str
    category_id: str
    name: str
    family: str
    geometry_type: str
    geometry_variant: str | None = None
    geometry_notes: str | None = None


@dataclass(frozen=True)
class PhysicalProperties:
    mass_per_length_kg_m: float | None = None
    area_mm2: float | None = None
    surface_area_per_length_m2_m: float | None = None


@dataclass(frozen=True)
class SectionPropertyOverride:
    """Catalog-backed decision to replace selected reported properties."""

    basis: str
    properties: tuple[str, ...]
    note: str


@dataclass(frozen=True)
class PropertyProvenance:
    """Origin of one effective property, independent of catalog provenance."""

    source_type: str
    calculation_convention: str | None = None
    note: str | None = None


@dataclass(frozen=True)
class ProfileSourceMetadata:
    """Traceable source fields that are not technical section properties."""

    source_page: int | None = None
    source_weight_p_kg_per_6m: float | None = None
    source_weight_basis_mm: float | None = None
    source_designation: str | None = None
    source_inches: str | None = None
    source_dimensions: Mapping[str, float] = field(default_factory=immutable_mapping)
    availability_note: str | None = None
    mass_type: str | None = None
    source_mass_per_length_kg_m: float | None = None
    density_kg_m3: float | None = None


@dataclass(frozen=True)
class ProfileDefinition:
    ref: ProfileRef
    designation: str
    equivalent_designation: str | None
    aliases: tuple[str, ...]
    catalog_markers: tuple[str, ...]
    availability_status: str
    geometry_status: str
    series_id: str
    category_id: str
    manufacturer: ManufacturerDefinition | None
    family: str
    geometry_type: str
    geometry_variant: str | None
    geometry_notes: str | None
    geometry: Mapping[str, float]
    physical_properties: PhysicalProperties
    section_properties: Mapping[str, float]
    reported_section_properties: Mapping[str, float]
    section_property_override: SectionPropertyOverride | None
    # T sections publish a vertical distance from the external top flange face,
    # not a horizontal centroid coordinate.
    centroid_from_top_flange_face: float | None
    # Section coordinate in the publication's geometric convention; it is not
    # a StructuralMember placement offset or a bounding-box center.
    centroid: Mapping[str, float]
    catalog: CatalogMetadata
    property_provenance: Mapping[str, PropertyProvenance] = field(
        default_factory=immutable_mapping
    )
    source_metadata: ProfileSourceMetadata | None = None
