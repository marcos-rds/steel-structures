"""Regression tests for the additional Gerdau profile families."""

from __future__ import annotations

import copy
import json
import math
import unittest
from pathlib import Path

from freecad.SteelStructures import profile_catalog
from freecad.SteelStructures.paths import CATALOGS_DIR
from freecad.SteelStructures.profiles import (
    CatalogValidationError, ProfileLibrary, ProfileRef, build_section_geometry,
    section_geometric_properties,
)
from freecad.SteelStructures.profiles.validation import validate_catalog_payload


CATALOG_ID = "gerdau-construcao-metalica-2023-01"
CATALOG_PATH = CATALOGS_DIR / "gerdau_construcao_metalica_2023_01.json"


class Stage2BCatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
        cls.library = ProfileLibrary(CATALOGS_DIR)
        cls.profiles = tuple(
            item for item in cls.library.list_profiles()
            if item.ref.catalog_id == CATALOG_ID
        )
        cls.by_id = {item.ref.profile_id: item for item in cls.profiles}

    def test_exact_global_and_series_counts_and_unique_refs(self):
        expected = {"w": 100, "hp": 8, "i": 8, "u": 12, "t": 10,
                    "equal-angle-inch": 50, "equal-angle-metric": 30}
        catalog_counts = {
            catalog.id: len(tuple(
                item for item in self.library.list_profiles()
                if item.ref.catalog_id == catalog.id
            ))
            for catalog in self.library.list_catalogs()
        }
        self.assertEqual(catalog_counts, {
            "abnt-nbr-6355-2012-a3": 85,
            "gerdau-construcao-metalica-2023-01": 218,
            "steel-structures-hollow-validation": 4,
        })
        all_profiles = self.library.list_profiles()
        self.assertEqual(len(all_profiles), 307)
        self.assertEqual(len({item.ref for item in all_profiles}), 307)
        self.assertEqual(len(tuple(item for item in self.library.list_categories()
                                   if item.catalog_id == CATALOG_ID)), 1)
        self.assertEqual(len(tuple(item for item in self.library.list_series()
                                   if item.catalog_id == CATALOG_ID)), 7)
        self.assertEqual(len(self.profiles), 218)
        self.assertEqual(len({item.ref for item in self.profiles}), 218)
        self.assertEqual({sid: len(self.library.list_profiles(series_id=sid)) for sid in expected}, expected)
        tubular = tuple(
            item for item in all_profiles
            if item.ref.catalog_id == "steel-structures-hollow-validation"
        )
        self.assertEqual(
            {item.designation for item in tubular},
            {"SHS 100x100x4,00", "RHS 150x100x4,75",
             "RHS 203,20x76,20x16", "CHS 88,90x3,00"},
        )

    def test_creation_combo_bridge_round_trips_all_constructible_profile_refs(self):
        for designation, expected_series in (
            ("W 150 x 13,0", "Perfis W"),
            ("HP 310 x 132,0", "Perfis HP"),
            ('I 3" x 8,48', "Perfis I"),
            ('U 6" x 12,20', "Perfis U"),
            ('T 2" x 1/4"', "Perfis T"),
            ('L 1/2" x 1/8"', "Cantoneiras - Polegadas"),
            ("L 40 x 3", "Cantoneiras - Métricas"),
        ):
            ref = profile_catalog.ref_for_designation(designation)
            category, series, restored = profile_catalog.selection_for_ref(ref)
            self.assertEqual(category, "Aço Laminado")
            self.assertEqual(series, expected_series)
            self.assertEqual(restored, designation)

    def test_creation_combo_bridge_rejects_non_constructible_profile(self):
        for profile_id in (
            "u-3x7.44", "u-10x30.80", "u-12x29.76",
        ):
            with self.subTest(profile_id=profile_id), self.assertRaises(ValueError):
                profile_catalog.selection_for_ref(ProfileRef(CATALOG_ID, profile_id))

    def test_creation_policy_has_one_catalog_backed_predicate(self):
        released = self.by_id["u-6x12.20"]
        pending = self.by_id["u-3x7.44"]
        self.assertTrue(profile_catalog.is_creation_profile(released))
        self.assertFalse(profile_catalog.is_creation_profile(pending))
        self.assertNotIn(pending.designation, profile_catalog.profiles())

    def test_series_geometry_types_variants_and_notes(self):
        expected = {
            "w": ("i_section", "parallel_flange"), "hp": ("i_section", "parallel_flange"),
            "i": ("i_section", "tapered_flange"), "u": ("channel_section", "tapered_flange"),
            "t": ("tee_section", "standard_tee"),
            "equal-angle-inch": ("equal_angle", "equal_leg"),
            "equal-angle-metric": ("equal_angle", "equal_leg"),
        }
        series = {item.id: item for item in self.library.list_series()}
        self.assertEqual({sid: (series[sid].geometry_type, series[sid].geometry_variant) for sid in expected}, expected)
        self.assertTrue(all(series[sid].geometry_notes for sid in expected))
        u_notes = series["u"].geometry_notes
        for evidence in ("Gerdau 2015", "Gerdau 2023", "BIM atual", "29,76", "30,80",
                         "sem troca silenciosa", "U 3 x 7,44", "U 10 x 30,80", "U 12 x 29,76"):
            self.assertIn(evidence, u_notes)
        i_notes = series["i"].geometry_notes
        for evidence in (
            "Perfil-I-Revit_1.zip", "Viga I Gerdau", "9,46", "r1 = 7 mm",
            "r2 = 3 mm", "TL explícito", "AutoCAD", "I 3 x 9,68",
            "inconsistência interna", "valores efetivos calculados",
        ):
            self.assertIn(evidence, i_notes)
        t_notes = series["t"].geometry_notes
        for evidence in (
            "Geometria nominal retangular", "face externa da mesa", "T 7/8 x 1/8",
            "0,33 cm4", "0,296 cm4", "sem override", "esclarecimento oficial",
        ):
            self.assertIn(evidence, t_notes)

    def assert_profile(self, profile_id, geometry, mass, area, section, centroid=None):
        item = self.by_id[profile_id]
        self.assertEqual(dict(item.geometry), geometry)
        self.assertEqual(item.physical_properties.mass_per_length_kg_m, mass)
        self.assertEqual(item.physical_properties.area_mm2, area * 100.0)
        self.assertEqual(dict(item.section_properties), section)
        if centroid is None:
            self.assertEqual(dict(item.centroid), {})
        else:
            if item.geometry_type == "tee_section":
                self.assertEqual(dict(item.centroid), {})
                self.assertAlmostEqual(item.centroid_from_top_flange_face, centroid * 10.0)
            else:
                self.assertEqual(set(item.centroid), {"x"})
                self.assertAlmostEqual(item.centroid["x"], centroid * 10.0)
        self.assertIsNone(item.physical_properties.surface_area_per_length_m2_m)

    def test_complete_i_boundary_samples(self):
        self.assert_profile("i-3x8.48", {"d":76.2,"tw":4.32,"bf":59.18,"tf":6.6,
                            "tl":13.715,"flange_angle":9.46,"r1":7.0,"r2":3.0}, 8.48, 10.8,
                            {"ix":1051000.0,"wx":27600.0,"rx":31.2,"iy":189000.0,"wy":6400.0,"ry":13.3,"rt":14.5})
        self.assert_profile("i-6x22.00", {"d":152.4,"tw":8.71,"bf":87.5,"tf":9.12,
                            "tl":19.6975,"flange_angle":9.46,"r1":7.0,"r2":3.0}, 22.0, 27.97,
                            {"ix":10030000.0,"wx":131700.0,"rx":59.9,"iy":849000.0,"wy":19400.0,"ry":17.4,"rt":22.6})

    def test_all_i_profiles_have_explicit_revit_geometry_parameters(self):
        profiles = self.library.list_profiles(series_id="i")
        self.assertEqual(len(profiles), 8)
        for profile in profiles:
            with self.subTest(profile=profile.designation):
                self.assertEqual(profile.geometry["flange_angle"], 9.46)
                self.assertEqual(profile.geometry["r1"], 7.0)
                self.assertEqual(profile.geometry["r2"], 3.0)
                self.assertAlmostEqual(
                    profile.geometry["tl"],
                    (profile.geometry["bf"] - profile.geometry["tw"]) / 4.0,
                )

    def test_i_3x9_68_effective_weak_axis_properties_come_from_one_geometry(self):
        profile = self.by_id["i-3x9.68"]
        geometry = build_section_geometry(profile)
        calculated = section_geometric_properties(geometry)
        effective = profile.section_properties
        half_width = profile.geometry["bf"] / 2.0
        self.assertAlmostEqual(effective["iy"], calculated.iy, places=7)
        self.assertAlmostEqual(effective["wy"], calculated.iy / half_width, places=7)
        self.assertAlmostEqual(
            effective["ry"], math.sqrt(calculated.iy / calculated.area), places=10,
        )
        self.assertAlmostEqual(calculated.area, geometry.area, places=7)
        self.assertNotEqual(effective["iy"], profile.reported_section_properties["iy"])
        self.assertNotEqual(effective["wy"], profile.reported_section_properties["wy"])
        self.assertNotEqual(effective["ry"], profile.reported_section_properties["ry"])

    def test_i_3x9_68_preserves_reported_gerdau_values_and_structured_decision(self):
        profile = self.by_id["i-3x9.68"]
        self.assertEqual(
            {key: profile.reported_section_properties[key] for key in ("iy", "wy", "ry")},
            {"iy": 456000.0, "wy": 11480.0, "ry": 19.2},
        )
        override = profile.section_property_override
        self.assertEqual(override.basis, "nominal_revit_geometry")
        self.assertEqual(set(override.properties), {"iy", "wy", "ry"})
        for evidence in (
            "inconsistência geométrica confirmada", "decisão técnica do projeto",
            "eventual esclarecimento da Gerdau", "valores publicados permanecem preservados",
        ):
            self.assertIn(evidence, override.note)

    def test_other_seven_i_profiles_continue_using_reported_properties(self):
        others = [
            profile for profile in self.library.list_profiles(series_id="i")
            if profile.ref.profile_id != "i-3x9.68"
        ]
        self.assertEqual(len(others), 7)
        for profile in others:
            with self.subTest(profile=profile.designation):
                self.assertIsNone(profile.section_property_override)
                self.assertEqual(
                    dict(profile.section_properties),
                    dict(profile.reported_section_properties),
                )

    def test_complete_u_boundary_samples_and_centroid_semantics(self):
        self.assert_profile("u-3x6.10", {"d":76.2,"tw":4.32,"bf":35.81,"tf":6.93,
                            "r1":6.0,"r2":1.8,"flange_angle":8.3}, 6.1, 7.78,
                            {"ix":689000.0,"wx":18100.0,"rx":29.8,"iy":82000.0,"wy":3320.0,"ry":10.3}, 1.11)
        self.assert_profile("u-12x37.00", {"d":305.0,"tw":9.8,"bf":77.0,"tf":12.7,
                            "r1":16.7,"r2":4.5,"flange_angle":8.3}, 37.0, 47.4,
                            {"ix":60100000.0,"wx":394000.0,"rx":113.0,"iy":1860000.0,"wy":30900.0,"ry":19.8}, 1.71)
        pending = {
            item.ref.profile_id for item in self.library.list_profiles(series_id="u")
            if item.geometry_status == "pending_technical_review"
        }
        self.assertEqual(pending, {"u-3x7.44", "u-10x30.80", "u-12x29.76"})
        self.assertTrue(all(
            item.geometry_status == "released"
            for item in self.library.list_profiles(series_id="u")
            if item.ref.profile_id not in pending
        ))

    def test_complete_t_boundary_samples_and_published_equalities(self):
        self.assert_profile("t-0.625x0.125", {"d":15.88,"bf":15.88,"tw":3.18,"tf":3.18}, .71, .90,
                            {"ix":2000.0,"wx":190.0,"rx":4.7,"iy":1100.0,"wy":140.0,"ry":3.5}, .51)
        self.assert_profile("t-2x0.25", {"d":50.8,"bf":50.8,"tw":6.35,"tf":6.35}, 4.74, 6.05,
                            {"ix":144700.0,"wx":4040.0,"rx":15.5,"iy":70300.0,"wy":2770.0,"ry":10.8}, 1.50)
        for item in self.library.list_profiles(series_id="t"):
            self.assertEqual(item.geometry["d"], item.geometry["bf"])
            self.assertEqual(item.geometry["tw"], item.geometry["tf"])
            self.assertEqual(dict(item.centroid), {})
            self.assertIsNotNone(item.centroid_from_top_flange_face)

    def test_t_7_8_preserves_official_iy_without_effective_override(self):
        item = self.by_id["t-0.875x0.125"]
        self.assertEqual(item.section_properties["iy"], 3300.0)
        self.assertEqual(item.reported_section_properties["iy"], 3300.0)
        self.assertIsNone(item.section_property_override)

    def test_complete_angle_samples_symmetry_and_rz_min(self):
        self.assert_profile("equal-angle-inch-0.5x0.125", {"b":12.7,"t":3.18}, .55, .70,
                            {"ix":1000.0,"iy":1000.0,"wx":110.0,"wy":110.0,"rx":3.7,"ry":3.7,"rz_min":2.5}, .43)
        self.assert_profile("equal-angle-inch-2x0.25", {"b":50.8,"t":6.35}, 4.74, 6.06,
                            {"ix":146000.0,"iy":146000.0,"wx":4100.0,"wy":4100.0,"rx":15.5,"ry":15.5,"rz_min":9.9}, 1.50)
        self.assert_profile("equal-angle-metric-40x4", {"b":40.0,"t":4.0}, 2.42, 3.08,
                            {"ix":44700.0,"iy":44700.0,"wx":1550.0,"wy":1550.0,"rx":12.2,"ry":12.2,"rz_min":7.9}, 1.15)
        for sid in ("equal-angle-inch", "equal-angle-metric"):
            for item in self.library.list_profiles(series_id=sid):
                self.assertEqual(item.section_properties["ix"], item.section_properties["iy"])
                self.assertEqual(item.section_properties["wx"], item.section_properties["wy"])
                self.assertEqual(item.section_properties["rx"], item.section_properties["ry"])
                self.assertIn("rz_min", item.section_properties)
                self.assertEqual(set(item.centroid), {"x"})

    def test_corrected_metric_boundaries_and_previously_omitted_sizes(self):
        items = self.library.list_profiles(series_id="equal-angle-metric")
        self.assertEqual(items[0].designation, "L 40 x 3")
        designations = {item.designation for item in items}
        self.assertNotIn("L 30 x 3", designations)
        self.assertTrue({"L 40 x 3", "L 50 x 3", "L 65 x 4", "L 75 x 5", "L 80 x 5"}.issubset(designations))

    def test_source_spot_checks_cover_middle_and_end_of_each_new_series(self):
        checks = {
            "i-5x14.88": (14.88, 18.80, 511.00),
            "u-8x20.50": (20.50, 25.93, 1490.00),
            "t-1.5x0.1875": (2.65, 3.40, 4.56),
            "equal-angle-inch-4x0.375": (14.57, 18.45, 183.00),
            "equal-angle-inch-8x0.75": (57.90, 73.81, 2901.10),
            "equal-angle-metric-75x6": (6.87, 8.72, 45.70),
            "equal-angle-metric-100x9": (13.50, 17.20, 164.30),
        }
        for profile_id, (mass, area, ix) in checks.items():
            item = self.by_id[profile_id]
            with self.subTest(profile=profile_id):
                self.assertEqual(item.physical_properties.mass_per_length_kg_m, mass)
                self.assertAlmostEqual(item.physical_properties.area_mm2, area * 100.0)
                self.assertAlmostEqual(item.section_properties["ix"], ix * 10000.0)

    def test_fractional_aliases_are_minimal_and_useful(self):
        self.assertIn("T1.25x0.1875", self.by_id["t-1.25x0.1875"].aliases)
        self.assertIn("L2x1/4", self.by_id["equal-angle-inch-2x0.25"].aliases)
        self.assertIn("L2x0.25", self.by_id["equal-angle-inch-2x0.25"].aliases)


class GeometryValidationTests(unittest.TestCase):
    def payload_for(self, profile_id):
        value = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
        value["profiles"] = [next(p for p in value["profiles"] if p["id"] == profile_id)]
        return value

    def assert_invalid_geometry(self, profile_id, **changes):
        value = self.payload_for(profile_id)
        value["profiles"][0]["geometry"].update(changes)
        with self.assertRaises(CatalogValidationError):
            validate_catalog_payload(value, Path("invalid-stage2b.json"))

    def test_channel_tee_and_equal_angle_constraints(self):
        for pid, changes in (("u-3x6.10", {"tw":36}), ("u-3x6.10", {"tf":38.1}),
                             ("t-2x0.25", {"tw":50.8}), ("t-2x0.25", {"tf":50.8}),
                             ("equal-angle-metric-40x4", {"t":40}),
                             ("equal-angle-metric-40x4", {"b":0})):
            with self.subTest(profile=pid, changes=changes):
                self.assert_invalid_geometry(pid, **changes)

    def test_channel_nominal_bim_parameters_are_required_and_validated(self):
        for changes in ({"r1": 0}, {"r2": -1}, {"flange_angle": 0}, {"flange_angle": 45}):
            with self.subTest(changes=changes):
                self.assert_invalid_geometry("u-3x6.10", **changes)
        value = self.payload_for("u-3x6.10")
        del value["profiles"][0]["geometry"]["r1"]
        with self.assertRaises(CatalogValidationError):
            validate_catalog_payload(value, Path("missing-u-radius.json"))

    def test_tapered_i_revit_parameters_are_required_and_validated(self):
        for changes in (
            {"r1": 0}, {"r2": -1}, {"tl": 0}, {"tl": 28},
            {"flange_angle": 0}, {"flange_angle": 45},
        ):
            with self.subTest(changes=changes):
                self.assert_invalid_geometry("i-3x8.48", **changes)
        for parameter in ("r1", "r2", "tl", "flange_angle"):
            value = self.payload_for("i-3x8.48")
            del value["profiles"][0]["geometry"][parameter]
            with self.subTest(parameter=parameter), self.assertRaises(CatalogValidationError):
                validate_catalog_payload(value, Path("missing-i-revit-parameter.json"))

    def test_section_property_override_requires_complete_weak_axis_set(self):
        for properties in ([], ["iy"], ["iy", "wy", "ry", "ix"]):
            value = self.payload_for("i-3x9.68")
            value["profiles"][0]["section_property_override"]["properties"] = properties
            with self.subTest(properties=properties), self.assertRaises(CatalogValidationError):
                validate_catalog_payload(value, Path("invalid-property-override.json"))

    def test_tee_validation_does_not_impose_catalog_specific_equalities(self):
        value = self.payload_for("t-2x0.25")
        value["profiles"][0]["geometry"].update(d=60, bf=50, tw=5, tf=6)
        _, _, _, profiles = validate_catalog_payload(value, Path("valid-independent-tee.json"))
        self.assertEqual(dict(profiles[0].geometry), {"d":60.0,"bf":50.0,"tw":5.0,"tf":6.0})

    def test_centroid_is_a_section_property_and_only_x_is_accepted(self):
        value = self.payload_for("u-3x6.10")
        value["profiles"][0]["centroid"]["y"] = 1
        with self.assertRaises(CatalogValidationError):
            validate_catalog_payload(value, Path("invalid-centroid.json"))

    def test_geometry_status_is_optional_released_and_rejects_unknown_values(self):
        value = self.payload_for("u-3x6.10")
        _, _, _, profiles = validate_catalog_payload(value, Path("default-status.json"))
        self.assertEqual(profiles[0].geometry_status, "released")
        value["profiles"][0]["geometry_status"] = "invented"
        with self.assertRaises(CatalogValidationError):
            validate_catalog_payload(value, Path("invalid-status.json"))


if __name__ == "__main__":
    unittest.main()
