"""Validation, indexing and compatibility tests for profile schema v2."""

from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from freecad.SteelStructures import profile_catalog
from freecad.SteelStructures.paths import CATALOGS_DIR
from freecad.SteelStructures.profiles import (
    CatalogValidationError,
    ProfileLibrary,
    ProfileNotFoundError,
    ProfileRef,
)
from freecad.SteelStructures.profiles.validation import validate_catalog_payload


CATALOG_PATH = CATALOGS_DIR / "gerdau_construcao_metalica_2023_01.json"
HOLLOW_DEV_PATH = CATALOGS_DIR / "dev" / "hollow_sections_validation.json"
EXPECTED_IDS = (
    "w-150x13.0", "w-150x18.0", "w-150x24.0",
    "w-200x15.0", "w-200x19.3", "w-200x22.5", "w-200x26.6", "w-200x31.3",
    "w-250x17.9", "w-250x22.3", "w-250x25.3", "w-250x28.4", "w-250x32.7", "w-250x38.5", "w-250x44.8",
    "w-310x21.0", "w-310x23.8", "w-310x28.3", "w-310x32.7", "w-310x38.7", "w-310x44.5", "w-310x52.0",
)

OLD_22_VALUES = {
    "w-150x13.0": (148, 100, 4.3, 4.9, 13.0, 16.6), "w-150x18.0": (153, 102, 5.8, 7.1, 18.0, 23.4),
    "w-150x24.0": (160, 102, 6.6, 10.3, 24.0, 31.5), "w-200x15.0": (200, 100, 4.3, 5.2, 15.0, 19.4),
    "w-200x19.3": (203, 102, 5.8, 6.5, 19.3, 25.1), "w-200x22.5": (206, 102, 6.2, 8.0, 22.5, 29.0),
    "w-200x26.6": (207, 133, 5.8, 8.4, 26.6, 34.2), "w-200x31.3": (210, 134, 6.4, 10.2, 31.3, 40.3),
    "w-250x17.9": (251, 101, 4.8, 5.3, 17.9, 23.1), "w-250x22.3": (254, 102, 5.8, 6.9, 22.3, 28.9),
    "w-250x25.3": (257, 102, 6.1, 8.4, 25.3, 32.6), "w-250x28.4": (260, 102, 6.4, 10.0, 28.4, 36.6),
    "w-250x32.7": (258, 146, 6.1, 9.1, 32.7, 42.1), "w-250x38.5": (262, 147, 6.6, 11.2, 38.5, 49.6),
    "w-250x44.8": (266, 148, 7.6, 13.0, 44.8, 57.6), "w-310x21.0": (303, 101, 5.1, 5.7, 21.0, 27.2),
    "w-310x23.8": (305, 101, 5.6, 6.7, 23.8, 30.7), "w-310x28.3": (309, 102, 6.0, 8.9, 28.3, 36.5),
    "w-310x32.7": (313, 102, 6.6, 10.8, 32.7, 42.1), "w-310x38.7": (310, 165, 5.8, 9.7, 38.7, 49.7),
    "w-310x44.5": (313, 166, 6.6, 11.2, 44.5, 57.2), "w-310x52.0": (317, 167, 7.6, 13.2, 52.0, 67.0),
}


def payload():
    return json.loads(CATALOG_PATH.read_text(encoding="utf-8"))


class SchemaValidationTests(unittest.TestCase):
    def assert_invalid(self, mutate):
        value = payload()
        mutate(value)
        with self.assertRaises(CatalogValidationError):
            validate_catalog_payload(value, Path("invalid.json"))

    def test_invalid_root_and_duplicate_ids(self):
        cases = (
            lambda p: p.update(schema_version=1),
            lambda p: p["catalog"].pop("id"),
            lambda p: p["categories"].append(copy.deepcopy(p["categories"][0])),
            lambda p: p["series"].append(copy.deepcopy(p["series"][0])),
            lambda p: p["profiles"].append(copy.deepcopy(p["profiles"][0])),
        )
        for mutate in cases:
            with self.subTest(mutate=mutate):
                self.assert_invalid(mutate)

    def test_invalid_references_and_strings(self):
        cases = (
            lambda p: p["series"][0].update(category_id="missing"),
            lambda p: p["profiles"][0].update(series_id="missing"),
            lambda p: p["profiles"][0].pop("geometry_type"),
            lambda p: p["profiles"][0].update(designation=""),
            lambda p: p["catalog"]["manufacturer"].update(name=""),
        )
        for mutate in cases:
            with self.subTest(mutate=mutate):
                self.assert_invalid(mutate)

    def test_invalid_i_section_geometry(self):
        cases = (
            lambda p: p["profiles"][0]["geometry"].pop("d"),
            lambda p: p["profiles"][0]["geometry"].update(d=0),
            lambda p: p["profiles"][0]["geometry"].update(bf=-1),
            lambda p: p["profiles"][0]["geometry"].update(tw=0),
            lambda p: p["profiles"][0]["geometry"].update(tf=-1),
            lambda p: p["profiles"][0]["geometry"].update(tw=100),
            lambda p: p["profiles"][0]["geometry"].update(tf=74),
        )
        for mutate in cases:
            with self.subTest(mutate=mutate):
                self.assert_invalid(mutate)

    def test_invalid_physical_values_and_non_finite_numbers(self):
        cases = (
            lambda p: p["profiles"][0]["physical_properties"].update(mass_per_length=-1),
            lambda p: p["profiles"][0]["physical_properties"].update(area=-1),
            lambda p: p["profiles"][0]["geometry"].update(d=float("nan")),
            lambda p: p["profiles"][0]["geometry"].update(d=float("inf")),
        )
        for mutate in cases:
            with self.subTest(mutate=mutate):
                self.assert_invalid(mutate)

    def test_unknown_unit_reports_file_catalog_and_field(self):
        value = payload()
        value["units"]["area"] = "banana"
        with self.assertRaises(CatalogValidationError) as caught:
            validate_catalog_payload(value, Path("bad-units.json"))
        message = str(caught.exception)
        self.assertIn("bad-units.json", message)
        self.assertIn("gerdau-construcao-metalica-2023-01", message)
        self.assertIn("units.area", message)
        self.assertIn("banana", message)

    def test_hollow_validation_rejects_invalid_dimensions_and_canonical_rhs_duplicate(self):
        base = json.loads(HOLLOW_DEV_PATH.read_text(encoding="utf-8"))
        cases = []
        shs = copy.deepcopy(base); shs["profiles"][0]["geometry"]["b"] = 16.0; cases.append(shs)
        rhs = copy.deepcopy(base); rhs["profiles"][1]["geometry"].update(h=100.0, b=150.0); cases.append(rhs)
        chs = copy.deepcopy(base); chs["profiles"][3]["geometry"]["d"] = 6.0; cases.append(chs)
        duplicate = copy.deepcopy(base)
        clone = copy.deepcopy(duplicate["profiles"][1])
        clone.update(id="rhs-reversed-duplicate", designation="RHS duplicate")
        clone["geometry"].update(h=100.0, b=150.0)
        duplicate["profiles"].append(clone); cases.append(duplicate)
        for value in cases:
            with self.subTest(value=value["profiles"][-1]["id"]):
                with self.assertRaises(CatalogValidationError):
                    validate_catalog_payload(value, Path("invalid-hollow.json"))


class CurrentCatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw = payload()
        cls.library = ProfileLibrary(CATALOGS_DIR)
        cls.profiles = tuple(
            item for item in cls.library.list_profiles()
            if item.ref.catalog_id == "gerdau-construcao-metalica-2023-01"
        )

    def test_identity_metadata_and_exact_profile_set(self):
        self.assertEqual(len(self.profiles), 218)
        self.assertTrue(set(EXPECTED_IDS).issubset({item.ref.profile_id for item in self.profiles}))
        self.assertTrue(all(item.ref.catalog_id == "gerdau-construcao-metalica-2023-01" for item in self.profiles))
        self.assertTrue(any(item.id == "rolled-steel"
                            for item in self.library.list_categories()))
        self.assertTrue(any(item.id == "w" for item in self.library.list_series()))
        self.assertEqual(len(self.library.list_profiles(series_id="w")), 100)
        self.assertEqual(len(self.library.list_profiles(series_id="hp")), 8)
        expected_counts = {"w": 100, "hp": 8, "i": 8, "u": 12, "t": 10,
                           "equal-angle-inch": 50, "equal-angle-metric": 30}
        self.assertEqual(
            {series: len(self.library.list_profiles(series_id=series)) for series in expected_counts},
            expected_counts,
        )
        metadata = next(item for item in self.library.list_catalogs()
                        if item.id == "gerdau-construcao-metalica-2023-01")
        self.assertEqual(metadata.manufacturer.name, "Gerdau")
        self.assertEqual(metadata.source.source_revision, "01/23")
        self.assertIsNone(metadata.source.source_date)
        self.assertEqual(metadata.standard_references, ("ABNT NBR 15980", "ASTM A6/A6M"))

    def test_boundary_profiles_preserve_exact_values(self):
        first = self.library.get(ProfileRef("gerdau-construcao-metalica-2023-01", "w-150x13.0"))
        last = self.library.get(ProfileRef("gerdau-construcao-metalica-2023-01", "w-310x52.0"))
        self.assertEqual((first.designation, dict(first.geometry), first.physical_properties.mass_per_length_kg_m, first.physical_properties.area_mm2),
                         ("W 150 x 13,0", {"d": 148.0, "bf": 100.0, "tw": 4.3, "tf": 4.9, "h": 138.0, "d_prime": 118.0}, 13.0, 1660.0))
        self.assertEqual((last.designation, dict(last.geometry), last.physical_properties.mass_per_length_kg_m, last.physical_properties.area_mm2),
                         ("W 310 x 52,0", {"d": 317.0, "bf": 167.0, "tw": 7.6, "tf": 13.2, "h": 291.0, "d_prime": 271.0}, 52.0, 6700.0))

    def test_every_commercial_value_round_trips(self):
        by_id = {item.ref.profile_id: item for item in self.profiles}
        for raw in self.raw["profiles"]:
            item = by_id[raw["id"]]
            with self.subTest(profile=raw["id"]):
                self.assertEqual(item.designation, raw["designation"])
                self.assertEqual(dict(item.geometry), {key: float(value) for key, value in raw["geometry"].items()})
                self.assertEqual(item.physical_properties.mass_per_length_kg_m, float(raw["physical_properties"]["mass_per_length"]))
                self.assertEqual(item.physical_properties.area_mm2 / 100.0, float(raw["physical_properties"]["area"]))

    def test_get_uses_typed_ref_and_missing_has_specific_error(self):
        ref = ProfileRef("gerdau-construcao-metalica-2023-01", "w-150x13.0")
        self.assertEqual(self.library.get(ref).ref, ref)
        with self.assertRaises(ProfileNotFoundError):
            self.library.get(ProfileRef("gerdau-construcao-metalica-2023-01", "missing"))

    def test_definitions_are_immutable(self):
        item = self.profiles[0]
        with self.assertRaises(TypeError):
            item.geometry["d"] = 1
        with self.assertRaises(TypeError):
            item.section_properties["ix"] = 1
        with self.assertRaises((AttributeError, TypeError)):
            item.aliases[0] = "changed"

    def test_original_22_profiles_have_no_dimension_mass_or_area_regression(self):
        by_id = {item.ref.profile_id: item for item in self.profiles}
        for profile_id, expected in OLD_22_VALUES.items():
            item = by_id[profile_id]
            actual = (item.geometry["d"], item.geometry["bf"], item.geometry["tw"], item.geometry["tf"],
                      item.physical_properties.mass_per_length_kg_m, item.physical_properties.area_mm2 / 100.0)
            with self.subTest(profile_id=profile_id):
                self.assertEqual(actual, expected)

    def test_w610x153_is_distinct_and_preserves_published_mass(self):
        special = self.library.get(ProfileRef("gerdau-construcao-metalica-2023-01", "w-610x153.0"))
        neighbour = self.library.get(ProfileRef("gerdau-construcao-metalica-2023-01", "w-610x155.0"))
        self.assertNotEqual(special.ref, neighbour.ref)
        self.assertEqual(special.designation, "W 610 x 153,0")
        self.assertEqual(special.physical_properties.mass_per_length_kg_m, 154.2)
        self.assertEqual(special.equivalent_designation, "W 24 x 103")
        self.assertEqual(neighbour.physical_properties.mass_per_length_kg_m, 155.0)

    def test_markers_availability_and_all_published_property_groups(self):
        hp = self.library.get(ProfileRef("gerdau-construcao-metalica-2023-01", "hp-310x132.0"))
        self.assertEqual(hp.catalog_markers, ("H", "*"))
        self.assertEqual(hp.availability_status, "made_to_order")
        self.assertEqual(hp.equivalent_designation, "HP 12 x 89")
        self.assertEqual(hp.physical_properties.surface_area_per_length_m2_m, 1.82)
        self.assertEqual(hp.section_properties["it"], 2067900.0)
        self.assertEqual(hp.section_properties["cw"], 2044445000000.0)
        self.assertEqual(hp.section_properties["rt"], 84.1)
        self.assertEqual(hp.section_properties["slenderness_flange"], 8.55)
        self.assertEqual(hp.section_properties["slenderness_web"], 13.41)

    def test_thousands_separators_and_canonical_conversions(self):
        sample = self.library.get(ProfileRef("gerdau-construcao-metalica-2023-01", "w-310x52.0"))
        self.assertEqual(sample.section_properties["ix"], 119090000.0)
        self.assertEqual(sample.section_properties["cw"], 236422000000.0)
        self.assertEqual(sample.section_properties["wx"], 751400.0)
        self.assertEqual(sample.section_properties["rx"], 133.3)

    def test_all_218_records_have_unique_ids_and_w_hp_complete_fields(self):
        self.assertEqual(len({p["id"] for p in self.raw["profiles"]}), 218)
        section_keys = {"ix", "wx", "rx", "zx", "iy", "wy", "ry", "zy", "rt", "it", "cw",
                        "slenderness_flange", "slenderness_web"}
        for raw in (p for p in self.raw["profiles"] if p["series_id"] in {"w", "hp"}):
            with self.subTest(profile=raw["id"]):
                self.assertEqual(set(raw["geometry"]), {"d", "bf", "tw", "tf", "h", "d_prime"})
                self.assertEqual(set(raw["physical_properties"]), {"mass_per_length", "area", "surface_area_per_length"})
                self.assertEqual(set(raw["section_properties"]), section_keys)
                self.assertIn(raw["availability_status"], {"standard", "made_to_order"})
                self.assertIsInstance(raw["equivalent_designation"], str)
                self.assertTrue(raw["equivalent_designation"] in raw["aliases"])

    def test_five_mandatory_cross_check_samples_preserve_every_table_column(self):
        expected = {
            "w-150x13.0": ([148,100,4.3,4.9,138,118], [13.0,16.6,0.67],
                [635,85.8,6.18,96.4,82,16.4,2.22,25.5,2.60,1.72,10.20,27.49,4181], "W 6 x 8,5"),
            "w-310x52.0": ([317,167,7.6,13.2,291,271], [52.0,67.0,1.27],
                [11909,751.4,13.33,842.5,1026,122.9,3.91,188.8,4.45,31.81,6.33,35.61,236422], "W 12 x 35"),
            "w-610x217.0": ([628,328,16.5,27.7,573,541], [217.0,278.4,2.51],
                [191395,6095.4,26.22,6868.8,16316,994.9,7.66,1531.6,8.73,570.21,5.92,32.76,14676643], "W 24 x 146"),
            "hp-200x53.0": ([204,207,11.3,11.3,181,161], [53.0,68.1,1.20],
                [4977,488.0,8.55,551.3,1673,161.7,4.96,248.6,5.57,31.93,9.16,14.28,155075], "HP 8 x 36"),
            "hp-310x132.0": ([314,313,18.3,18.3,277,245], [132.0,167.5,1.82],
                [28731,1830.0,13.10,2075.5,9371,598.8,7.48,922.4,8.41,206.79,8.55,13.41,2044445], "HP 12 x 89"),
        }
        raw_by_id = {p["id"]: p for p in self.raw["profiles"]}
        geometry_keys = ("d", "bf", "tw", "tf", "h", "d_prime")
        physical_keys = ("mass_per_length", "area", "surface_area_per_length")
        section_keys = ("ix", "wx", "rx", "zx", "iy", "wy", "ry", "zy", "rt", "it",
                        "slenderness_flange", "slenderness_web", "cw")
        for profile_id, (geometry, physical, section, equivalent) in expected.items():
            raw = raw_by_id[profile_id]
            with self.subTest(profile_id=profile_id):
                self.assertEqual([raw["geometry"][key] for key in geometry_keys], geometry)
                self.assertEqual([raw["physical_properties"][key] for key in physical_keys], physical)
                self.assertEqual([raw["section_properties"][key] for key in section_keys], section)
                self.assertEqual(raw["equivalent_designation"], equivalent)


class MultiCatalogAndReloadTests(unittest.TestCase):
    def write(self, directory, name, value):
        (Path(directory) / name).write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")

    def test_same_designation_and_profile_id_are_valid_in_different_catalogs(self):
        with tempfile.TemporaryDirectory() as directory:
            first = payload()
            second = payload()
            second["catalog"]["id"] = "another-catalog"
            second["catalog"]["name"] = "Outro catálogo"
            self.write(directory, "a.json", first)
            self.write(directory, "b.json", second)
            library = ProfileLibrary(Path(directory))
            self.assertEqual(len(library.list_profiles()), 436)
            self.assertEqual(library.list_profiles()[0].designation, library.list_profiles()[218].designation)

    def test_duplicate_profile_ref_across_files_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            self.write(directory, "a.json", payload())
            self.write(directory, "b.json", payload())
            with self.assertRaisesRegex(CatalogValidationError, "ProfileRef duplicada"):
                ProfileLibrary(Path(directory)).list_profiles()

    def test_reload_discards_old_indices_and_order_is_deterministic(self):
        with tempfile.TemporaryDirectory() as directory:
            value = payload()
            self.write(directory, "b.json", value)
            library = ProfileLibrary(Path(directory))
            self.assertEqual(library.list_profiles()[0].designation, "W 150 x 13,0")
            value["profiles"][0]["designation"] = "Changed"
            self.write(directory, "b.json", value)
            self.assertEqual(library.list_profiles()[0].designation, "W 150 x 13,0")
            library.reload()
            self.assertEqual(library.list_profiles()[0].designation, "Changed")
            self.assertEqual(tuple(p.ref.profile_id for p in library.list_profiles()), tuple(p["id"] for p in value["profiles"]))

    def test_installed_development_catalog_is_discovered_after_new_instance_and_reload(self):
        expected = {
            "SHS 100x100x4,00", "RHS 150x100x4,75",
            "RHS 203,20x76,20x16", "CHS 88,90x3,00",
        }
        first = ProfileLibrary(CATALOGS_DIR)
        second = ProfileLibrary(CATALOGS_DIR)
        for library in (first, second.reload()):
            self.assertTrue(any(item.id == "tubular" and item.name == "Aço Tubular"
                                for item in library.list_categories()))
            self.assertEqual(
                {item.name for item in library.list_series("tubular")},
                {"SHS — Tubo quadrado", "RHS — Tubo retangular", "CHS — Tubo redondo"},
            )
            self.assertEqual(
                {item.designation for item in library.list_profiles(category_id="tubular")},
                expected,
            )
            self.assertTrue(all(
                item.availability_status == "development_fixture"
                for item in library.list_profiles(category_id="tubular")
            ))


class LegacyFacadeTests(unittest.TestCase):
    def test_legacy_hierarchy_and_real_folded_category_are_preserved(self):
        self.assertEqual(profile_catalog.categories(), ["Aço Laminado", "Aço Dobrado", "Aço Tubular"])
        self.assertEqual(
            profile_catalog.series_for_category("Aço Laminado"),
            ["Perfis W", "Perfis HP", "Perfis I", "Perfis U", "Perfis T", "Cantoneiras - Polegadas", "Cantoneiras - Métricas"],
        )
        self.assertEqual(
            profile_catalog.series_for_category("Aço Dobrado"),
            ["U Enrijecido (Ue) — NBR 6355"],
        )
        self.assertEqual(
            profile_catalog.series_for_category("Aço Tubular"),
            ["SHS — Tubo quadrado", "RHS — Tubo retangular", "CHS — Tubo redondo"],
        )
        self.assertEqual(len(profile_catalog.designations("Aço Laminado", "Perfis W")), 100)
        self.assertEqual(len(profile_catalog.designations("Aço Laminado", "Perfis HP")), 8)
        self.assertEqual(len(profile_catalog.designations("Aço Laminado", "Perfis I")), 8)
        self.assertEqual(len(profile_catalog.designations("Aço Laminado", "Perfis U")), 9)
        self.assertEqual(len(profile_catalog.designations("Aço Laminado", "Perfis T")), 10)
        self.assertEqual(len(profile_catalog.profiles()), 304)
        self.assertEqual(len(profile_catalog.designations("Aço Laminado", "Cantoneiras - Polegadas")), 50)
        self.assertEqual(len(profile_catalog.designations("Aço Laminado", "Cantoneiras - Métricas")), 30)
        self.assertEqual(profile_catalog.get('U 3" x 6,10').family, "u")
        with self.assertRaises(KeyError):
            profile_catalog.get('U 3" x 7,44')

    def test_freecad_property_designations_are_quote_safe_and_lookup_is_canonical(self):
        cases = ('U 6" x 12,20', 'U 10" x 22,77', 'T 2" x 1/4"', 'L 2" x 1/4"')
        for canonical in cases:
            safe = profile_catalog.property_designation(canonical)
            with self.subTest(canonical=canonical):
                self.assertNotIn('"', safe)
                self.assertIn("″", safe)
                compile(f'obj.Profile = u"{safe}"', "<freecad-property>", "exec")
                self.assertIs(profile_catalog.get(safe), profile_catalog.get(canonical))
                self.assertEqual(profile_catalog.canonical_designation(safe), canonical)
                self.assertEqual(
                    profile_catalog.ref_for_designation(safe),
                    profile_catalog.ref_for_designation(canonical),
                )

    def test_profile_property_can_switch_between_w_and_quote_safe_u_values(self):
        values = (
            "W 150 x 13,0",
            profile_catalog.property_designation('U 6" x 12,20'),
            profile_catalog.property_designation('U 10" x 22,77'),
            "W 310 x 32,7",
        )
        selected = tuple(profile_catalog.get(value) for value in values)
        self.assertEqual(tuple(item.family for item in selected), ("w", "u", "u", "w"))
        self.assertEqual(selected[1].designation, 'U 6" x 12,20')
        self.assertEqual(selected[2].designation, 'U 10" x 22,77')

    def test_search_normalizes_ascii_and_typographic_inch_marks_in_one_layer(self):
        library = ProfileLibrary(CATALOGS_DIR)
        ascii_results = library.search('U 6" x 12,20')
        safe_results = library.search("U 6″ x 12,20")
        self.assertEqual(tuple(item.ref for item in safe_results),
                         tuple(item.ref for item in ascii_results))

    def test_property_options_keep_w_hp_unchanged_and_protect_all_inch_families(self):
        self.assertEqual(
            profile_catalog.property_designations("Aço Laminado", "Perfis W"),
            profile_catalog.designations("Aço Laminado", "Perfis W"),
        )
        for series in ("Perfis U", "Cantoneiras - Polegadas"):
            options = profile_catalog.property_designations("Aço Laminado", series)
            self.assertTrue(options)
            self.assertTrue(all('"' not in value for value in options))

    def test_legacy_profile_contract_and_quantitative_values_are_preserved(self):
        item = profile_catalog.get("W 150 x 13,0")
        expected_fields = ("category", "series", "manufacturer", "family", "designation", "mass_per_m", "d", "bf", "tw", "tf", "area_cm2", "source")
        self.assertTrue(all(hasattr(item, field) for field in expected_fields))
        self.assertEqual((item.mass_per_m, item.area_cm2), (13.0, 16.6))
        self.assertEqual(item.mass_per_m * 3000.0 / 1000.0, 39.0)
        with self.assertRaises(KeyError):
            profile_catalog.get("missing")

    def test_hp_facade_shape_dimensions_and_mass_calculations(self):
        hp = profile_catalog.get("HP 310 x 132,0")
        self.assertEqual((hp.d, hp.bf, hp.tw, hp.tf), (314.0, 313.0, 18.3, 18.3))
        self.assertEqual(hp.mass_per_m * 1000.0 / 1000.0, 132.0)
        w = profile_catalog.get("W 150 x 13,0")
        self.assertEqual(w.mass_per_m * 3000.0 / 1000.0, 39.0)
