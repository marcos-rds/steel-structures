# SPDX-License-Identifier: LGPL-2.1-or-later
"""Typed structural-profile catalog domain API."""

from .catalog import ProfileLibrary, canonicalize_designation, normalize_search_text
from .geometry import (
    ArcSegment2D,
    GeometryTemporarilyUnavailableError,
    LineSegment2D,
    PathSegment2D,
    Point2D,
    SectionBounds2D,
    SectionGeometry2D,
    SectionGeometryMode,
    SectionGeometryError,
    SectionPath2D,
    UnsupportedSectionGeometryError,
    build_equal_angle_section,
    build_parallel_flange_i_section,
    build_standard_tee_section,
    build_tapered_flange_i_section,
    build_tapered_flange_channel_section,
    build_section_geometry,
    normalize_section_geometry_mode, section_geometry_mode_has_effect,
    geometry_is_released,
)
from .insertion import (
    InsertionReference, insertion_reference, insertion_translation,
    section_insertion_references,
)
from .effective_properties import (
    GeometricSectionProperties, resolve_effective_section_properties,
    section_geometric_properties,
)
from .cold_formed import (
    ColdFormedPath2D, PhysicalSectionProperties2D, SegmentIntersections2D,
    angle_on_arc, arc_arc_intersections, path_self_intersections,
    physical_section_properties, section_geometry_from_cold_formed,
    segment_arc_intersections, segment_segment_intersections,
)
from .ue_section import (
    UeDerivedDimensions, UeNormativeProperties, build_ue_mean_path,
    build_simplified_ue_section, build_ue_section, nbr_6355_expected_internal_radius,
    ue_derived_dimensions, ue_normative_properties,
)
from .models import (
    CatalogMetadata,
    CatalogSource,
    CategoryDefinition,
    ManufacturerDefinition,
    IssuerDefinition,
    PhysicalProperties,
    ProfileDefinition,
    ProfileRef,
    SectionPropertyOverride,
    SeriesDefinition,
)
from .validation import (
    CatalogError,
    CatalogValidationError,
    ProfileNotFoundError,
    convert_to_canonical,
)

__all__ = [
    "CatalogError", "CatalogMetadata", "CatalogSource",
    "CatalogValidationError", "CategoryDefinition", "ArcSegment2D", "LineSegment2D",
    "ManufacturerDefinition", "IssuerDefinition", "PathSegment2D", "Point2D",
    "GeometryTemporarilyUnavailableError", "geometry_is_released",
    "PhysicalProperties", "ProfileDefinition", "ProfileLibrary",
    "ProfileNotFoundError", "ProfileRef", "SectionBounds2D",
    "SectionPropertyOverride",
    "SectionGeometry2D", "SectionGeometryError", "SectionGeometryMode", "SectionPath2D",
    "SeriesDefinition", "UnsupportedSectionGeometryError",
    "build_equal_angle_section", "build_parallel_flange_i_section",
    "build_standard_tee_section",
    "build_tapered_flange_i_section",
    "build_tapered_flange_channel_section",
    "build_section_geometry",
    "InsertionReference", "insertion_reference", "insertion_translation",
    "section_insertion_references",
    "canonicalize_designation", "convert_to_canonical", "normalize_search_text",
    "GeometricSectionProperties", "resolve_effective_section_properties",
    "section_geometric_properties",
    "ColdFormedPath2D", "PhysicalSectionProperties2D",
    "SegmentIntersections2D", "angle_on_arc", "arc_arc_intersections",
    "path_self_intersections", "segment_arc_intersections",
    "segment_segment_intersections",
    "physical_section_properties", "section_geometry_from_cold_formed",
    "UeDerivedDimensions", "UeNormativeProperties", "build_ue_mean_path",
    "build_simplified_ue_section", "build_ue_section", "nbr_6355_expected_internal_radius",
    "normalize_section_geometry_mode", "section_geometry_mode_has_effect",
    "ue_derived_dimensions", "ue_normative_properties",
]
