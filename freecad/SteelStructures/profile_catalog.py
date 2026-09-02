# SPDX-License-Identifier: LGPL-2.1-or-later
"""Temporary compatibility facade over the typed profile-catalog API."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List

from .paths import CATALOGS_DIR
from .profiles import (
    ProfileLibrary, ProfileRef, build_section_geometry,
    canonicalize_designation as canonical_designation, geometry_is_released,
    section_insertion_references,
)

# The folded-steel category is now supplied by its real normative catalog.
KNOWN_CATEGORIES = ["Aço Laminado"]

# Temporary application capability until geometry generators for the other
# catalog families are integrated and validated.
SUPPORTED_CREATION_SERIES = {
    "w", "hp", "i", "u", "t", "equal-angle-inch", "equal-angle-metric",
    "ue-nbr-6355",
    "shs", "rhs", "chs",
}


@dataclass(frozen=True)
class Profile:
    category: str
    series: str
    manufacturer: str
    family: str
    designation: str
    mass_per_m: float
    d: float
    bf: float
    tw: float
    tf: float
    area_cm2: float
    source: str
    definition: object | None = None


_LIBRARY = ProfileLibrary(CATALOGS_DIR)
_CACHE: Dict[str, Profile] | None = None


def is_creation_profile(definition) -> bool:
    """Central creation eligibility: supported family and released geometry."""
    return (
        definition.series_id in SUPPORTED_CREATION_SERIES
        and geometry_is_released(definition)
    )


def _legacy_source(definition) -> str:
    source = definition.catalog.source
    owner = definition.manufacturer or definition.catalog.issuer
    value = f"{owner.name} - {source.source_name}" if owner else source.source_name
    if source.source_revision:
        value += f", revisão {source.source_revision}"
    return value


def _adapt(definition, categories, series) -> Profile:
    physical = definition.physical_properties
    return Profile(
        category=categories[(definition.ref.catalog_id, definition.category_id)],
        series=series[(definition.ref.catalog_id, definition.series_id)],
        manufacturer=definition.manufacturer.name if definition.manufacturer else "",
        family=definition.family,
        designation=definition.designation,
        mass_per_m=float(physical.mass_per_length_kg_m),
        d=definition.geometry.get("d", 0.0),
        bf=definition.geometry.get("bf", 0.0),
        tw=definition.geometry.get("tw", 0.0),
        tf=definition.geometry.get("tf", 0.0),
        area_cm2=float(physical.area_mm2) / 100.0,
        source=_legacy_source(definition),
        definition=definition,
    )


def _load() -> Dict[str, Profile]:
    categories_by_id = {
        (item.catalog_id, item.id): item.name for item in _LIBRARY.list_categories()
    }
    series_by_id = {
        (item.catalog_id, item.id): item.name for item in _LIBRARY.list_series()
    }
    result = {}
    for definition in _LIBRARY.list_profiles():
        if not is_creation_profile(definition):
            continue
        # The legacy contract has no catalog namespace. Keep its historical
        # global-designation constraint while new consumers use ProfileRef.
        if definition.designation in result:
            raise ValueError(f"Designação duplicada: {definition.designation}")
        result[definition.designation] = _adapt(
            definition, categories_by_id, series_by_id
        )
    if not result:
        raise RuntimeError("Nenhum perfil foi encontrado no catálogo.")
    return result


def profiles() -> Dict[str, Profile]:
    global _CACHE
    if _CACHE is None:
        _CACHE = _load()
    return _CACHE


def categories() -> List[str]:
    found = list(KNOWN_CATEGORIES)
    for profile in profiles().values():
        if profile.category not in found:
            found.append(profile.category)
    return found


def series_for_category(category: str) -> List[str]:
    result = []
    for profile in profiles().values():
        if profile.category == category and profile.series not in result:
            result.append(profile.series)
    return result


def designations(category: str | None = None, series: str | None = None) -> List[str]:
    result = []
    for profile in profiles().values():
        if category is not None and profile.category != category:
            continue
        if series is not None and profile.series != series:
            continue
        result.append(profile.designation)
    return result


def property_designation(designation: str) -> str:
    """Return a PropertyEnumeration label that FreeCAD can serialize safely."""
    return canonical_designation(designation).replace('"', "″")


def property_designations(category: str | None = None, series: str | None = None) -> List[str]:
    return [property_designation(value) for value in designations(category, series)]


def get(designation: str) -> Profile:
    catalog = profiles()
    canonical = canonical_designation(designation)
    if canonical not in catalog:
        raise KeyError(f"Perfil não encontrado: {designation}")
    return catalog[canonical]


def insertion_options(profile: Profile):
    if profile.definition is None:
        return ()
    geometry = build_section_geometry(profile.definition)
    return tuple(item.label for item in section_insertion_references(geometry))


def ref_for_designation(designation: str) -> ProfileRef:
    """Return the stable typed identity behind a creation-profile designation."""
    designation = canonical_designation(designation)
    if designation not in profiles():
        raise KeyError(f"Perfil não encontrado: {designation}")
    for definition in _LIBRARY.list_profiles():
        if is_creation_profile(definition) and definition.designation == designation:
            return definition.ref
    raise KeyError(f"Perfil não encontrado: {designation}")


def selection_for_ref(ref: ProfileRef):
    """Bridge a typed identity to the current category/series/combo values."""
    definition = _LIBRARY.get(ref)
    if not is_creation_profile(definition):
        raise ValueError("A série do perfil ainda não possui geometria de criação.")
    category = next(
        item.name for item in _LIBRARY.list_categories()
        if item.catalog_id == ref.catalog_id and item.id == definition.category_id
    )
    series = next(
        item.name for item in _LIBRARY.list_series(definition.category_id)
        if item.catalog_id == ref.catalog_id and item.id == definition.series_id
    )
    return category, series, definition.designation


def reload():
    """Reload typed catalogs and invalidate the compatibility cache."""
    global _CACHE
    _LIBRARY.reload()
    _CACHE = None
