"""Optional normative provenance without changing published section masses.

The small payload below is synthetic validation data, not a normative table.
"""

from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from freecad.SteelStructures.paths import CATALOGS_DIR
from freecad.SteelStructures.profiles.effective_properties import (
    calculate_hollow_profile_properties, calculate_solid_profile_properties,
    resolve_profile_mass,
)
from freecad.SteelStructures.profiles.validation import (
    CatalogValidationError, validate_catalog_payload,
)


def metadata_payload():
    return {
        "schema_version": 2,
        "catalog": {
            "id": "normative-metadata-test", "name": "Teste de metadados",
            "catalog_version": "test", "manufacturer": None,
            "issuer": {"id": "test-issuer", "name": "Emissor de teste"},
            "source": {
                "source_name": "Dados sintéticos para teste de metadados",
                "source_type": "normative", "density_kg_m3": 7850,
            },
            "region": "BR", "country": "Brazil", "catalog_pack": "brazil",
        },
        "units": {"length": "mm", "area": "mm2", "mass_per_length": "kg/m"},
        "categories": [{"id": "solid-steel", "name": "Aço Maciço"}],
        "series": [{
            "id": "round-bar", "category_id": "solid-steel",
            "name": "Barra Redonda", "family": "ROUND_BAR",
            "geometry_type": "solid_section", "geometry_variant": "circular",
        }],
        "profiles": [{
            "id": "round-bar-test", "series_id": "round-bar",
            "designation": "Barra de teste", "availability_status": "standard",
            "geometry_type": "solid_section", "geometry": {"d": 10},
            "physical_properties": {}, "section_properties": {}, "centroid": {},
            "source_metadata": {
                "source_page": 2, "source_pdf_page": 7, "source_table": "Tabela de teste",
                "source_row": 3, "mass_type": "published",
                "mass_basis": "normative_table", "source_mass_per_length_kg_m": 7.777,
            },
        }],
    }


class NormativeProfileMetadataTests(unittest.TestCase):
    def validate(self, payload):
        return validate_catalog_payload(payload, Path("metadata-test.json"))

    def test_region_and_source_locations_reach_typed_models(self):
        metadata, _, _, profiles = self.validate(metadata_payload())
        self.assertEqual((metadata.region, metadata.country, metadata.catalog_pack),
                         ("BR", "Brazil", "brazil"))
        self.assertEqual(metadata.source.density_kg_m3, 7850)
        source = profiles[0].source_metadata
        self.assertEqual((source.source_page, source.source_pdf_page, source.source_row),
                         (2, 7, 3))
        self.assertEqual(source.source_table, "Tabela de teste")
        self.assertEqual(source.mass_basis, "normative_table")

    def test_all_new_fields_can_be_absent_or_null(self):
        for explicit_null in (False, True):
            payload = metadata_payload()
            mappings = (
                (payload["catalog"], ("region", "country", "catalog_pack")),
                (payload["catalog"]["source"], ("density_kg_m3",)),
                (payload["profiles"][0]["source_metadata"],
                 ("source_table", "source_pdf_page", "source_row", "mass_basis")),
            )
            for mapping, keys in mappings:
                for key in keys:
                    if explicit_null:
                        mapping[key] = None
                    else:
                        mapping.pop(key)
            metadata, _, _, profiles = self.validate(payload)
            self.assertEqual((metadata.region, metadata.country, metadata.catalog_pack),
                             (None, None, None))
            self.assertIsNone(metadata.source.density_kg_m3)
            for name in ("source_table", "source_pdf_page", "source_row", "mass_basis"):
                self.assertIsNone(getattr(profiles[0].source_metadata, name))

    def test_normative_table_availability_is_distinct_from_commercial_supply(self):
        payload = metadata_payload()
        payload["profiles"][0]["availability_status"] = "normative_table"
        profile = self.validate(payload)[3][0]
        self.assertEqual(profile.availability_status, "normative_table")
        self.assertEqual(profile.catalog.source.source_type, "normative")

    def test_normative_table_availability_requires_normative_source(self):
        for source_type in (None, "commercial", "development_fixture"):
            payload = metadata_payload()
            payload["profiles"][0]["availability_status"] = "normative_table"
            # Isolate availability validation from the independent mass-basis rule.
            payload["profiles"][0]["source_metadata"].pop("mass_basis")
            payload["catalog"]["source"]["source_type"] = source_type
            with self.subTest(source_type=source_type), self.assertRaisesRegex(
                CatalogValidationError, "availability_status normative_table",
            ):
                self.validate(payload)

    def test_region_requires_two_uppercase_ascii_letters(self):
        for value in ("br", "BRA", "B", "BŔ", "12", "", True, 1):
            payload = metadata_payload()
            payload["catalog"]["region"] = value
            with self.subTest(value=value), self.assertRaises(CatalogValidationError):
                self.validate(payload)

    def test_country_and_pack_reject_invalid_values(self):
        cases = {
            "country": ("", "  ", False, 12),
            "catalog_pack": ("", "Brazil", "brazil_pack", "two words", False, 12),
        }
        for name, values in cases.items():
            for value in values:
                payload = metadata_payload()
                payload["catalog"][name] = value
                with self.subTest(name=name, value=value), self.assertRaises(CatalogValidationError):
                    self.validate(payload)

    def test_informative_density_requires_positive_finite_number(self):
        for value in (0, -1, True, "7850", float("nan"), float("inf")):
            payload = metadata_payload()
            payload["catalog"]["source"]["density_kg_m3"] = value
            with self.subTest(value=value), self.assertRaises(CatalogValidationError):
                self.validate(payload)

    def test_location_indices_are_one_based_positive_integers(self):
        for name in ("source_page", "source_pdf_page", "source_row"):
            for value in (0, -1, True, 1.5, "2"):
                payload = metadata_payload()
                payload["profiles"][0]["source_metadata"][name] = value
                with self.subTest(name=name, value=value), self.assertRaises(CatalogValidationError):
                    self.validate(payload)

    def test_source_table_is_optional_nonempty_text(self):
        for value in ("", "  ", True, 2):
            payload = metadata_payload()
            payload["profiles"][0]["source_metadata"]["source_table"] = value
            with self.subTest(value=value), self.assertRaises(CatalogValidationError):
                self.validate(payload)

    def test_normative_table_requires_normative_origin_and_published_mass(self):
        for location, key, value in (
            ("source", "source_type", "development_fixture"),
            ("metadata", "mass_type", "calculated_fixture"),
            ("metadata", "mass_type", "derived"),
            ("metadata", "source_mass_per_length_kg_m", None),
            ("metadata", "mass_basis", "unknown_basis"),
        ):
            payload = metadata_payload()
            mapping = (payload["catalog"]["source"] if location == "source"
                       else payload["profiles"][0]["source_metadata"])
            mapping[key] = value
            with self.subTest(key=key, value=value), self.assertRaises(CatalogValidationError):
                self.validate(payload)

    def test_published_physical_mass_can_carry_normative_basis(self):
        payload = metadata_payload()
        profile_raw = payload["profiles"][0]
        profile_raw["source_metadata"].pop("source_mass_per_length_kg_m")
        profile_raw["physical_properties"]["mass_per_length"] = 7.777
        profile = self.validate(payload)[3][0]
        resolved = resolve_profile_mass(profile)
        self.assertEqual(resolved.physical_properties.mass_per_length_kg_m, 7.777)
        self.assertEqual(resolved.source_metadata.mass_basis, "normative_table")

    def test_source_density_never_recalculates_published_mass(self):
        for density in (7850, 8000):
            payload = metadata_payload()
            payload["catalog"]["source"]["density_kg_m3"] = density
            profile = self.validate(payload)[3][0]
            resolved = calculate_solid_profile_properties(resolve_profile_mass(profile))
            self.assertEqual(resolved.physical_properties.mass_per_length_kg_m, 7.777)
            self.assertEqual(resolved.property_provenance["mass_per_length"].source_type, "published")
            self.assertIsNone(resolved.source_metadata.density_kg_m3)
            self.assertNotAlmostEqual(resolved.physical_properties.mass_per_length_kg_m,
                                      resolved.physical_properties.area_mm2 * density * 1e-6)

    def test_source_density_does_not_supply_missing_profile_mass(self):
        payload = metadata_payload()
        source = payload["profiles"][0]["source_metadata"]
        source.pop("source_mass_per_length_kg_m")
        source.pop("mass_basis")
        profile = self.validate(payload)[3][0]
        with self.assertRaisesRegex(ValueError, "massa publicada"):
            calculate_solid_profile_properties(resolve_profile_mass(profile))

    def test_tuper_metadata_and_p_over_six_remain_compatible(self):
        payload = json.loads((CATALOGS_DIR / "tuper_hollow_2024.json").read_text(encoding="utf-8"))
        payload["profiles"] = payload["profiles"][:1]
        metadata, _, _, profiles = self.validate(copy.deepcopy(payload))
        self.assertIsNone(metadata.region)
        self.assertIsNone(metadata.source.density_kg_m3)
        resolved = calculate_hollow_profile_properties(resolve_profile_mass(profiles[0]))
        self.assertEqual(resolved.physical_properties.mass_per_length_kg_m,
                         resolved.source_metadata.source_weight_p_kg_per_6m / 6)
        self.assertEqual(resolved.property_provenance["mass_per_length"].source_type, "derived")
        self.assertIsNone(resolved.source_metadata.mass_basis)
        self.assertIsNone(resolved.source_metadata.source_table)


if __name__ == "__main__":
    unittest.main()
