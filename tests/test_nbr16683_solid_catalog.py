"""Normative solid catalog: source-bound data, public UI and legacy resolution."""

from collections import Counter
import copy
from dataclasses import replace
import json
import math
from pathlib import Path
import tempfile
import unittest

from freecad.SteelStructures import profile_catalog
from freecad.SteelStructures.paths import CATALOGS_DIR
from freecad.SteelStructures.profiles import (
    ProfileLibrary, build_section_geometry, solid_section_properties,
)
from freecad.SteelStructures.profiles.presentation import profile_property_groups, profile_source_groups
from scripts import generate_nbr16683_solid_catalog as generator
from tests.test_profile_browser import _load_browser_runtime_module


class NBR16683CatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.snapshot = json.loads(generator.SNAPSHOT.read_text(encoding="utf-8"))
        cls.library = ProfileLibrary(CATALOGS_DIR)
        cls.profiles = cls.library.list_profiles(category_id="solid-steel")
        cls.by_id = {p.ref.profile_id: p for p in cls.profiles}

    def test_counts_and_source_table_locations(self):
        self.assertEqual(Counter(p.series_id for p in self.profiles), generator.EXPECTED_COUNTS)
        self.assertEqual(len(self.profiles), 164)
        self.assertEqual(Counter(p.source_metadata.source_page for p in self.profiles), generator.PAGE_COUNTS)
        for p in self.profiles:
            self.assertEqual(p.source_metadata.source_table, generator.FAMILIES[p.series_id][3])
            self.assertEqual(p.source_metadata.source_pdf_page, p.source_metadata.source_page + 6)
            self.assertGreater(p.source_metadata.source_row, 0)

    def test_primary_source_identity_and_corrected_edition(self):
        source = self.snapshot["source"]
        self.assertEqual(source["sha256"], generator.PDF_SHA256)
        self.assertEqual(source["edition_date"], "2018-11-29")
        self.assertEqual(source["corrected_date"], "2020-04-23")
        self.assertEqual(source["errata"], [{"number": 1, "date": "2020-04-23", "reference": "Prefácio, p. v"}])
        self.assertFalse(source["current_status_verified"])
        self.assertEqual(self.snapshot["audit"]["source_corrections_applied"], [])

    def test_every_catalog_cell_matches_its_raw_nominal_columns_and_mass(self):
        raw = {(r["page"], r["row"]): r for r in self.snapshot["records"]}
        self.assertEqual(len(raw), len(self.profiles))
        for p in self.profiles:
            metadata = p.source_metadata
            record = raw[(metadata.source_page, metadata.source_row)]
            self.assertEqual(dict(p.geometry), {k: float(v.replace(",", ".")) for k, v in record["dimensions"].items()})
            self.assertEqual(p.physical_properties.mass_per_length_kg_m, float(record["mass_kg_m"].replace(",", ".")))
            self.assertEqual(metadata.source_designation, record["source_reference"])
            self.assertEqual(metadata.source_inches, record["source_inches"])

    def test_independent_small_medium_large_samples_from_pdf(self):
        # Numeric cells checked against rendered printed pp. 6-12, not formulas.
        for profile_id, dimensions, mass in (
            ("round-bar-6-35", {"d": 6.35}, .249),
            ("round-bar-52-38", {"d": 52.38}, 16.916),
            ("round-bar-103-19", {"d": 103.19}, 65.650),
            ("square-bar-6-35", {"b": 6.35}, .310),
            ("square-bar-38-1", {"b": 38.1}, 11.150),
            ("square-bar-52-39", {"b": 52.39}, 21.550),
            ("flat-bar-9-53x3-18", {"b": 9.53, "t": 3.18}, .238),
            ("flat-bar-44-45x6-35", {"b": 44.45, "t": 6.35}, 1.966),
            ("flat-bar-152-4x25-4", {"b": 152.4, "t": 25.4}, 30.387),
        ):
            p = self.by_id[profile_id]
            self.assertEqual(dict(p.geometry), dimensions)
            self.assertEqual(p.physical_properties.mass_per_length_kg_m, mass)

    def test_conflicting_reference_does_not_override_explicit_thickness(self):
        p = self.by_id["flat-bar-76-2x50-8"]
        self.assertEqual(p.geometry["t"], 50.8)
        self.assertEqual(p.source_metadata.source_designation, "76,20 × 49,80")
        self.assertIn("49,80", p.source_metadata.availability_note)
        self.assertEqual(p.physical_properties.mass_per_length_kg_m, 30.390)

    def test_no_cartesian_expansion_or_fixture_dimensions(self):
        flats = [p for p in self.profiles if p.series_id == "flat-bar"]
        self.assertEqual(len({p.geometry["b"] for p in flats}), 17)
        self.assertNotIn("flat-bar-88-9x9-53", self.by_id)
        self.assertIn("flat-bar-88-9x9-52", self.by_id)
        for profile_id in ("round-bar-20", "round-bar-50", "square-bar-20", "square-bar-50",
                           "flat-bar-50x6-35", "flat-bar-100x10"):
            self.assertNotIn(profile_id, self.by_id)

    def test_numeric_order_is_diameter_side_then_width_thickness(self):
        for family, data in generator.FAMILIES.items():
            values = [tuple(p.geometry[k] for k in data[4]) for p in self.profiles if p.series_id == family]
            self.assertEqual(values, sorted(values))
        flat_ids = [p.ref.profile_id for p in self.profiles if p.series_id == "flat-bar"]
        self.assertLess(flat_ids.index("flat-bar-130x10"), flat_ids.index("flat-bar-152-4x6-35"))

    def test_region_origin_and_mass_contract_reaches_every_profile(self):
        for p in self.profiles:
            self.assertEqual((p.catalog.region, p.catalog.country, p.catalog.catalog_pack), ("BR", "Brazil", "brazil"))
            self.assertIsNone(p.manufacturer)
            self.assertEqual(p.catalog.issuer.id, "abnt")
            self.assertEqual(p.catalog.source.source_type, "normative")
            self.assertEqual(p.catalog.source.density_kg_m3, 7850)
            self.assertEqual(p.source_metadata.mass_basis, "normative_table")
            self.assertEqual(p.property_provenance["mass_per_length"].source_type, "published")
            self.assertEqual(p.availability_status, "normative_table")

    def test_technical_properties_remain_calculated_and_do_not_follow_mass(self):
        for p in self.profiles:
            expected = solid_section_properties(variant=p.geometry_variant, **p.geometry)
            self.assertEqual(p.physical_properties.area_mm2, expected.area)
            self.assertAlmostEqual(profile_catalog.get(p.designation).area_cm2 * 100, expected.area)
            for key in ("ix", "iy", "wx", "wy", "rx", "ry"):
                self.assertEqual(p.section_properties[key], getattr(expected, key))
                self.assertEqual(p.property_provenance[key].source_type, "calculated")
            if p.geometry_variant == "rectangular":
                self.assertGreater(expected.iy, expected.ix)
            else:
                self.assertEqual((expected.ix, expected.wx, expected.rx), (expected.iy, expected.wy, expected.ry))
        square = self.by_id["square-bar-38-1"]
        self.assertNotAlmostEqual(square.physical_properties.mass_per_length_kg_m,
                                  square.physical_properties.area_mm2 * .00785, places=2)

    def test_no_radii_or_inner_paths_and_modes_stay_equivalent(self):
        for p in self.profiles:
            detailed = build_section_geometry(p, "Detailed")
            self.assertEqual(detailed, build_section_geometry(p, "Simplified"))
            self.assertEqual(detailed.inner_paths, ())

    def test_approved_searches_and_absent_nominal_examples(self):
        ids = lambda text: {p.ref.profile_id for p in self.library.search(text, category_id="solid-steel")}
        self.assertEqual(ids("Barra Redonda 20"), {"round-bar-20-64"})
        self.assertEqual(ids("Ø20"), {"round-bar-20-64"})
        self.assertTrue(ids("20"))
        for query in ("Barra Quadrada 20x20", "20x20", "Barra Chata 50x6,35", "50x6.35", "50x6,35"):
            self.assertEqual(ids(query), set())
        self.assertEqual(ids("50,8x6,35"), ids("50.8x6.35"))
        self.assertEqual(ids("50.8x6.35"), {"flat-bar-50-8x6-35"})

    def test_inches_aliases_only_exist_for_actual_inch_rows(self):
        for p in self.profiles:
            if p.source_metadata.source_inches is None:
                self.assertFalse(any('"' in value for value in p.aliases))
        p = self.by_id["square-bar-20-64"]
        self.assertEqual(p.source_metadata.source_inches, "13/16’")
        self.assertIn(p, self.library.search('13/16"', series_id="square-bar"))

    def test_browser_source_and_properties_have_normative_mass_and_calculated_area(self):
        browser = _load_browser_runtime_module()
        p = self.by_id["flat-bar-44-45x6-35"]
        self.assertEqual(browser._profile_subtitle(p, "Barra Chata"), "Barra Chata — ABNT NBR 16683:2018")
        rows = {r.label: r.value for g in profile_source_groups(p) for r in g.rows}
        self.assertEqual(rows["Tabela"], "A.1")
        self.assertEqual(rows["Página da fonte"], "7")
        self.assertEqual(rows["Região"], "Brasil")
        self.assertIn("publicada", rows["Massa linear"])
        props = {r.label: r for g in profile_property_groups(p) for r in g.rows}
        self.assertEqual(props["Massa linear"].value, "1,966 kg/m")
        self.assertIn("publicada", props["Massa linear"].tooltip)

    def test_public_lists_hide_dev_but_legacy_lookup_preserves_mass(self):
        for library in (self.library, ProfileLibrary(CATALOGS_DIR).reload()):
            self.assertFalse(any(p.availability_status == "development_fixture" for p in library.list_profiles()))
        legacy = profile_catalog.get("Barra Redonda Ø20")
        self.assertEqual(legacy.definition.ref.catalog_id, "steelstructures-solid-sections-validation")
        self.assertAlmostEqual(legacy.mass_per_m, math.pi * 100 * .00785)
        self.assertNotIn(legacy.designation, profile_catalog.designations())
        self.assertNotIn(legacy.designation, profile_catalog.property_designations())

    def test_normative_source_renderer_tolerates_optional_metadata_and_issuer(self):
        profile = self.by_id["round-bar-6-35"]
        profile = replace(profile, source_metadata=None, catalog=replace(profile.catalog, issuer=None))
        rows = {row.label: row.value for group in profile_source_groups(profile) for row in group.rows}
        self.assertEqual(rows["Norma"], "ABNT NBR 16683:2018")
        for missing in ("Tabela", "Página da fonte", "Organismo", "Massa linear"):
            self.assertNotIn(missing, rows)

    def test_only_current_legacy_profile_is_retained_for_restore(self):
        current = "Barra Redonda Ø20"
        choices = profile_catalog.property_designations("Aço Maciço", "Barra Redonda", current)
        self.assertIn(current, choices)
        self.assertNotIn("Barra Redonda Ø50", choices)
        self.assertNotIn(current, profile_catalog.property_designations("Aço Maciço", "Barra Quadrada", current))
        self.assertEqual(len(choices), 54)

    def test_deterministic_bytes_match_committed_catalog(self):
        first = generator.render_catalog(self.snapshot)
        second = generator.render_catalog(copy.deepcopy(self.snapshot))
        self.assertEqual(first, second)
        self.assertEqual(first, generator.OUTPUT.read_bytes())
        with tempfile.TemporaryDirectory() as directory:
            a, b = Path(directory) / "a.json", Path(directory) / "b.json"
            a.write_bytes(first)
            b.write_bytes(second)
            self.assertEqual(a.read_bytes(), b.read_bytes())

    def test_generator_rejects_changed_mass_even_if_embedded_hash_is_recomputed(self):
        snapshot = copy.deepcopy(self.snapshot)
        snapshot["records"][0]["mass_kg_m"] = "0,239"
        snapshot["audit"]["raw_records_sha256"] = generator.fingerprint(snapshot["records"])
        with self.assertRaisesRegex(ValueError, "auditadas"):
            generator.build_catalog(snapshot)

    def test_generator_rejects_missing_rows_wrong_edition_or_unapproved_correction(self):
        for mutation in (
            lambda s: s["records"].pop(),
            lambda s: s["source"].update(corrected_date="2018-11-29"),
            lambda s: s["audit"].update(source_corrections_applied=["replace_mass"]),
        ):
            snapshot = copy.deepcopy(self.snapshot)
            mutation(snapshot)
            with self.assertRaises(ValueError):
                generator.build_catalog(snapshot)

    def test_mass_discrepancies_are_audit_only_not_source_corrections(self):
        payload = generator.build_catalog(self.snapshot)
        audit = payload["generation_audit"]
        flags = [row for row in audit["mass_comparison"] if row["exceeds_0_5_percent"]]
        self.assertEqual(len(flags), 12)
        self.assertEqual(sum(r["profile_id"].startswith("flat-bar") for r in flags), 10)
        self.assertEqual(sum(r["profile_id"].startswith("square-bar") for r in flags), 2)
        self.assertFalse(any(r["profile_id"].startswith("round-bar") for r in flags))
        self.assertEqual(audit["source_corrections_applied"], [])


if __name__ == "__main__":
    unittest.main()
