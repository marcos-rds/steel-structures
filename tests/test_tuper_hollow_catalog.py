"""Integrity and runtime integration tests for the static Tuper catalog."""

from __future__ import annotations

import importlib.util
import copy
import hashlib
import json
import tempfile
import unittest
from collections import Counter
from pathlib import Path

from freecad.SteelStructures import profile_catalog
from freecad.SteelStructures.profiles import ProfileLibrary, ProfileRef
from freecad.SteelStructures.profiles.presentation import profile_source_groups


ROOT = Path(__file__).resolve().parents[1]
CATALOGS = ROOT / "freecad" / "SteelStructures" / "catalogs"
CATALOG_PATH = CATALOGS / "tuper_hollow_2024.json"
SNAPSHOT_PATH = (
    ROOT / "freecad" / "SteelStructures" / "catalog_sources"
    / "tuper_hollow_2024_extracted.json"
)
GENERATOR_PATH = ROOT / "scripts" / "generate_tuper_hollow_catalog.py"
CATALOG_ID = "arcelormittal-tuper-hollow-2024"


def load_generator():
    spec = importlib.util.spec_from_file_location("tuper_catalog_generator", GENERATOR_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TuperHollowGenerationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
        cls.snapshot = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
        cls.generator = load_generator()

    def test_audited_counts_and_explicit_source_errata(self):
        self.generator.validate_snapshot(self.snapshot)
        self.assertEqual(self.raw["generation_audit"]["raw_counts"], {
            "chs": 1239, "rhs": 1190, "shs": 678,
        })
        self.assertEqual(self.raw["generation_audit"]["final_counts"], {
            "chs": 1131, "rhs": 1190, "shs": 678,
        })
        self.assertEqual(self.raw["generation_audit"]["duplicate_key_count"], 0)
        self.assertEqual(
            self.raw["generation_audit"]["duplicate_resolution"],
            "explicit_source_errata_then_conflict_audit",
        )
        self.assertEqual(self.snapshot["source_corrections_applied"], [
            {"id": "chs-printed-page-30-stale-weight-body", "matched_records": 108},
            {"id": "shs-printed-page-58-first-header-dimension", "matched_records": 10},
        ])

    def test_generator_is_byte_deterministic(self):
        generated = self.generator.build_catalog(self.snapshot)
        expected = json.dumps(generated, ensure_ascii=False, indent=2) + "\n"
        self.assertEqual(expected, CATALOG_PATH.read_text(encoding="utf-8"))

    def test_static_catalog_has_exact_family_counts_and_numeric_order(self):
        profiles = self.raw["profiles"]
        self.assertEqual(Counter(item["series_id"] for item in profiles), {
            "chs": 1131, "rhs": 1190, "shs": 678,
        })
        for family in ("shs", "rhs", "chs"):
            records = [item for item in profiles if item["series_id"] == family]
            dimensions = [(
                item["geometry"].get("h", item["geometry"].get("d", item["geometry"].get("b"))),
                item["geometry"].get("b", 0.0), item["geometry"]["t"],
            ) for item in records]
            self.assertEqual(dimensions, sorted(dimensions))

    def test_public_designation_precision_and_source_text_are_clean(self):
        designations = {item["designation"] for item in self.raw["profiles"]}
        self.assertIn("CHS 88,90x3", designations)
        self.assertIn("CHS 273x10", designations)
        self.assertIn("RHS 150x100x4,75", designations)
        # The audit log names the repaired byte patterns intentionally; inspect
        # the extracted payload itself separately from that documentation.
        extracted = {key: value for key, value in self.snapshot.items() if key != "audit"}
        serialized = json.dumps(extracted, ensure_ascii=False)
        self.assertNotIn("�", serialized)
        self.assertNotIn("Ã", serialized)
        self.assertNotIn("”", serialized)
        self.assertEqual(self.snapshot["audit"]["text_normalization"], [
            "mojibake Ã˜ -> Ø",
            "mojibake TÃ©cnica -> Técnica",
            "curly closing inch quote U+201D -> ASCII quote",
            "replacement character U+FFFD removed from source labels",
        ])
        self.assertIn("explicit source errata", self.snapshot["audit"]["extraction_rule"])

    def test_known_errata_preserve_raw_and_correct_normalized_records(self):
        raw = self.snapshot["raw_records"]
        self.assertEqual(len([r for r in raw if r["family"] == "chs" and r["page"] == 30]), 108)
        records = {(r["family"], r.get("d_mm"), r.get("h_mm"), r["t_mm"]): r
                   for r in self.snapshot["records"]}
        self.assertEqual(records[("chs", 21.3, None, 0.75)]["source_weight_p_kg_per_6m"], 2.281)
        self.assertEqual(records[("chs", 26.0, None, 0.75)]["source_weight_p_kg_per_6m"], 2.802)
        self.assertEqual(records[("shs", None, 75.0, 2.0)]["source_weight_p_kg_per_6m"], 27.345)
        corrected = records[("shs", None, 76.2, 2.0)]
        self.assertEqual(corrected["source_weight_p_kg_per_6m"], 27.797)
        self.assertEqual(corrected["source_correction_id"],
                         "shs-printed-page-58-first-header-dimension")
        series_75 = [r["source_weight_p_kg_per_6m"] for r in self.snapshot["records"]
                     if r["family"] == "shs" and r["h_mm"] == 75.0]
        series_762 = [r["source_weight_p_kg_per_6m"] for r in self.snapshot["records"]
                      if r["family"] == "shs" and r["h_mm"] == 76.2]
        self.assertEqual(series_75, [
            27.345, 30.634, 35.838, 40.331, 44.767,
            49.77, 55.919, 61.955, 71.952, 79.937,
        ])
        self.assertEqual(series_762, [
            27.797, 31.143, 36.437, 41.009, 45.525,
            50.617, 56.88, 63.028, 73.218, 81.361,
        ])

    def test_unknown_material_duplicate_still_raises(self):
        first = {"family": "chs", "d_mm": 50.0, "t_mm": 2.0, "page": 1,
                 "source_weight_p_kg_per_6m": 10.0, "availability": "standard"}
        second = dict(first, page=2, source_weight_p_kg_per_6m=11.0)
        with self.assertRaisesRegex(self.generator.DuplicateCommercialConflict,
                                    "family=chs.*page=1.*page=2"):
            self.generator.reconcile_duplicates([first, second])

    def test_compatible_duplicate_merges_alias_and_source_pages(self):
        first = {"family": "chs", "d_mm": 88.9, "t_mm": 3.0, "page": 1,
                 "source_weight_p_kg_per_6m": 38.0, "availability": "standard",
                 "source_inches": '3 1/2"', "source_designation": "Ø 88,90",
                 "source_notes": "condição A"}
        second = dict(first, page=2, source_inches='3.1/2"',
                      source_designation="88,90 mm", source_notes="condição B")
        merged = next(iter(self.generator.reconcile_duplicates([first, second]).values()))
        self.assertEqual(merged["source_inches_aliases"], ['3 1/2"', '3.1/2"'])
        self.assertEqual(merged["source_pages"], [1, 2])
        self.assertEqual(merged["source_designations"], ["88,90 mm", "Ø 88,90"])
        self.assertEqual(merged["source_conditions"], ["condição A", "condição B"])

    def test_snapshot_validation_recomputes_raw_records_hash(self):
        altered = copy.deepcopy(self.snapshot)
        altered["raw_records"][0]["source_weight_p_kg_per_6m"] += 0.001
        with self.assertRaisesRegex(ValueError, "raw_records_sha256"):
            self.generator.validate_snapshot(altered)
        expected = hashlib.sha256(json.dumps(
            self.snapshot["raw_records"], ensure_ascii=False, separators=(",", ":"),
        ).encode("utf-8")).hexdigest()
        self.assertEqual(self.snapshot["audit"]["raw_records_sha256"], expected)

    def test_source_correction_rejects_changed_matching_context(self):
        altered = copy.deepcopy(self.snapshot["raw_records"])
        target = next(record for record in altered
                      if record["family"] == "chs" and record["page"] == 30)
        target["source_weight_p_kg_per_6m"] += 0.001
        with self.assertRaisesRegex(ValueError, "contexto divergente"):
            self.generator.apply_source_corrections(altered)

    def test_mass_is_exactly_p_over_six_and_source_fields_are_preserved(self):
        for item in self.raw["profiles"]:
            source = item["source_metadata"]
            self.assertEqual(source["source_weight_basis_mm"], 6000.0)
            self.assertNotIn("supply_conditions", item)
            self.assertAlmostEqual(
                item["physical_properties"]["mass_per_length"],
                source["source_weight_p_kg_per_6m"] / 6.0,
            )
            self.assertGreater(source["source_page"], 0)
            self.assertTrue(source["source_designation"])
        extreme = next(item for item in self.raw["profiles"]
                       if item["id"] == "rhs-203-2x76-2x16")
        self.assertEqual(extreme["geometry"], {"h": 203.2, "b": 76.2, "t": 16.0})
        self.assertEqual(extreme["source_metadata"]["source_dimensions"], {
            "l1": 76.2, "l2": 203.2,
        })
        self.assertEqual(extreme["availability_status"], "consultation")

    def test_supply_conditions_are_catalog_glossary_only(self):
        conditions = self.raw["catalog"]["supply_condition_definitions"]
        self.assertEqual(conditions, [
            {"code": "RA", "description": "Rebarba Interna Alta, Sem Remoção",
             "availability": "normal", "source_page": 17},
            {"code": "RIR", "description": "Rebarba Interna Removida",
             "availability": "special_consultation", "source_page": 17},
            {"code": "RIC", "description": "Rebarba Interna Controlada",
             "availability": "special_consultation", "source_page": 17},
        ])


class TuperHollowRuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.library = ProfileLibrary(CATALOGS).reload()

    def test_library_has_one_tubular_category_and_three_series(self):
        categories = [item for item in self.library.list_categories() if item.id == "tubular"]
        self.assertEqual([(item.catalog_id, item.name) for item in categories], [
            (CATALOG_ID, "Aço Tubular"),
        ])
        series = [item.id for item in self.library.list_series("tubular")]
        self.assertEqual(series, ["shs", "rhs", "chs"])

    def test_profiles_have_calculated_properties_and_traceable_source(self):
        for profile_id in (
            "shs-100x100x4-25", "rhs-150x100x4-75",
            "rhs-203-2x76-2x16", "chs-88-9x3",
        ):
            profile = self.library.get(ProfileRef(CATALOG_ID, profile_id))
            self.assertEqual(set(profile.section_properties), {
                "ix", "iy", "wx", "wy", "rx", "ry",
            })
            self.assertGreater(profile.physical_properties.area_mm2, 0.0)
            self.assertEqual(profile.property_provenance["area"].source_type, "calculated")
            self.assertIsNotNone(profile.source_metadata.source_weight_p_kg_per_6m)
            self.assertEqual(profile.source_metadata.source_weight_basis_mm, 6000.0)
            self.assertEqual(
                profile.property_provenance["mass_per_length"].source_type, "derived"
            )
            self.assertAlmostEqual(
                profile.physical_properties.mass_per_length_kg_m,
                profile.source_metadata.source_weight_p_kg_per_6m / 6.0,
            )
            self.assertEqual(
                [item.code for item in profile.catalog.supply_condition_definitions],
                ["RA", "RIR", "RIC"],
            )

    def test_search_supports_public_source_and_inch_designations(self):
        public = self.library.search("RHS 150x100x4,75", series_id="rhs")
        source = self.library.search("100 x 150", series_id="rhs")
        inches = self.library.search('3.1/2"', series_id="chs")
        self.assertIn("rhs-150x100x4-75", {item.ref.profile_id for item in public})
        self.assertIn("rhs-150x100x4-75", {item.ref.profile_id for item in source})
        self.assertIn("chs-88-9x3", {item.ref.profile_id for item in inches})

    def test_source_presentation_labels_catalog_conditions_as_general(self):
        profile = self.library.get(ProfileRef(CATALOG_ID, "rhs-150x100x4-75"))
        rows = {row.label: row for group in profile_source_groups(profile)
                for row in group.rows}
        self.assertIn("Condição geral RA", rows)
        self.assertIn("condição normal", rows["Condição geral RA"].value)
        self.assertIn("condição especial sob consulta", rows["Condição geral RIR"].value)
        self.assertIn("não atribuído automaticamente", rows["Condição geral RIC"].tooltip)

    def test_legacy_creation_facade_exposes_all_commercial_hollows(self):
        profile_catalog.reload()
        profiles = profile_catalog.profiles()
        counts = Counter(item.family for item in profiles.values()
                         if item.category == "Aço Tubular")
        self.assertEqual(counts, {"SHS": 678, "RHS": 1190, "CHS": 1131})
        self.assertIn("Aço Tubular", profile_catalog.categories())
        self.assertEqual(profile_catalog.series_for_category("Aço Tubular"), [
            "SHS — Tubo quadrado", "RHS — Tubo retangular", "CHS — Tubo redondo",
        ])


if __name__ == "__main__":
    unittest.main()
