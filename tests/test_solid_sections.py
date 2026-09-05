"""Stage-A solid bars: independent math, static catalog and source contracts."""

import copy
import json
import math
from pathlib import Path
import tempfile
import unittest

from freecad.SteelStructures import profile_catalog
from freecad.SteelStructures.paths import CATALOGS_DIR
from freecad.SteelStructures.profiles import (
    ProfileLibrary, SectionGeometryMode, build_section_geometry,
    build_round_bar, build_square_bar, build_flat_bar, build_circular_hollow_section,
    section_geometric_properties, section_geometry_mode_has_effect,
    solid_section_properties, insertion_reference,
)
from freecad.SteelStructures.profiles.geometry import ArcSegment2D, LineSegment2D
from freecad.SteelStructures.profiles.validation import validate_catalog_payload, CatalogValidationError


FIXTURE_PATH = CATALOGS_DIR / "dev" / "solid_sections_validation.json"
CATALOG_ID = "steelstructures-solid-sections-validation"
CASES = (
    ("circular", {"d": 20}), ("circular", {"d": 50}),
    ("square", {"b": 20}), ("square", {"b": 50}),
    ("rectangular", {"b": 50, "t": 6.35}),
    ("rectangular", {"b": 100, "t": 10}),
    ("rectangular", {"b": 100, "t": 3}),
)
BUILDERS = {"circular": build_round_bar, "square": build_square_bar,
            "rectangular": build_flat_bar}


def payload():
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


class SolidMathTests(unittest.TestCase):
    def test_reference_values_all_required_dimensions(self):
        # Independent tabulated numerical references, evaluated analytically.
        expected = (
            (100 * math.pi, 2500 * math.pi, 2500 * math.pi, 250 * math.pi, 250 * math.pi, 5, 5),
            (625 * math.pi, 390625 * math.pi / 4, 390625 * math.pi / 4,
             15625 * math.pi / 4, 15625 * math.pi / 4, 12.5, 12.5),
            (400, 40000 / 3, 40000 / 3, 4000 / 3, 4000 / 3, 10 / math.sqrt(3), 10 / math.sqrt(3)),
            (2500, 1562500 / 3, 1562500 / 3, 62500 / 3, 62500 / 3, 25 / math.sqrt(3), 25 / math.sqrt(3)),
            (317.5, 1066.866145833333, 66145.83333333333, 336.0208333333333,
             2645.833333333333, 1.8330871046770618, 14.433756729740645),
            (1000, 25000 / 3, 2500000 / 3, 5000 / 3, 50000 / 3,
             5 / math.sqrt(3), 50 / math.sqrt(3)),
            (300, 225, 250000, 150, 5000, math.sqrt(0.75), 50 / math.sqrt(3)),
        )
        names = ("area", "ix", "iy", "wx", "wy", "rx", "ry")
        for (variant, dimensions), values in zip(CASES, expected):
            result = solid_section_properties(variant=variant, **dimensions)
            for name, value in zip(names, values):
                with self.subTest(variant=variant, dimensions=dimensions, property=name):
                    self.assertGreater(getattr(result, name), 0)
                    self.assertAlmostEqual(getattr(result, name) / value, 1, places=11)

    def test_independent_contour_integrals_match_technical_area_and_inertia(self):
        for variant, dimensions in CASES:
            technical = solid_section_properties(variant=variant, **dimensions)
            integrated = section_geometric_properties(BUILDERS[variant](**dimensions))
            for name in ("area", "ix", "iy"):
                with self.subTest(variant=variant, dimensions=dimensions, property=name):
                    self.assertAlmostEqual(getattr(integrated, name) / getattr(technical, name), 1)
            self.assertAlmostEqual(integrated.centroid_x, 0)
            self.assertAlmostEqual(integrated.centroid_y, 0)

    def test_shared_integrator_does_not_alias_circular_hollow_moments(self):
        result = section_geometric_properties(build_circular_hollow_section(d=20, t=2))
        expected = math.pi * (20 ** 4 - 16 ** 4) / 64
        self.assertAlmostEqual(result.ix, expected)
        self.assertAlmostEqual(result.iy, expected)

    def test_flat_axes_are_not_swapped_or_normalized(self):
        p = solid_section_properties(variant="rectangular", b=100, t=3)
        self.assertGreater(p.iy, p.ix * 1000)
        g = build_flat_bar(b=100, t=3)
        self.assertEqual((g.bounds.width, g.bounds.height), (100, 3))
        with self.assertRaises(ValueError):
            build_flat_bar(b=3, t=100)

    def test_dimension_scaling_powers_and_symmetry(self):
        for variant, dimensions in CASES:
            a = solid_section_properties(variant=variant, **dimensions)
            b = solid_section_properties(variant=variant, **{k: 3 * v for k, v in dimensions.items()})
            for name, power in (("area", 2), ("ix", 4), ("iy", 4), ("wx", 3), ("wy", 3), ("rx", 1), ("ry", 1)):
                self.assertAlmostEqual(getattr(b, name) / getattr(a, name), 3 ** power)
            if variant != "rectangular":
                self.assertEqual((a.ix, a.wx, a.rx), (a.iy, a.wy, a.ry))

    def test_invalid_dimensions_rejected_before_freecad(self):
        for variant, dimensions in CASES:
            for key in dimensions:
                for value in (0, -1, math.inf, math.nan, True, "20"):
                    bad = dict(dimensions, **{key: value})
                    with self.subTest(variant=variant, bad=bad), self.assertRaises(ValueError):
                        BUILDERS[variant](**bad)
                    with self.assertRaises(ValueError):
                        solid_section_properties(variant=variant, **bad)
        with self.assertRaises(ValueError):
            build_flat_bar(b=20, t=20)

    def test_exact_closed_paths_and_equivalent_modes(self):
        for variant, dimensions in CASES:
            detailed, simple = [BUILDERS[variant](**dimensions, mode=mode) for mode in SectionGeometryMode]
            self.assertEqual(detailed, simple)
            self.assertEqual(detailed.inner_paths, ())
            segments = detailed.outer_path.segments
            self.assertEqual(segments[0].start, segments[-1].end)
            for first, second in zip(segments, segments[1:]):
                self.assertEqual(first.end, second.start)
            cls = ArcSegment2D if variant == "circular" else LineSegment2D
            self.assertTrue(all(isinstance(segment, cls) for segment in segments))
            self.assertEqual(len(segments), 2 if variant == "circular" else 4)


class SolidCatalogTests(unittest.TestCase):
    def test_installed_fixture_is_discovered_after_fresh_load_and_reload(self):
        for library in (ProfileLibrary(CATALOGS_DIR), ProfileLibrary(CATALOGS_DIR).reload()):
            profiles = library.list_profiles(category_id="solid-steel")
            self.assertEqual(len(profiles), 6)
            self.assertEqual({s.id for s in library.list_series("solid-steel")},
                             {"round-bar", "square-bar", "flat-bar"})
            self.assertEqual(sum(c.id == "solid-steel" for c in library.list_categories()), 1)
            self.assertEqual({p.ref.catalog_id for p in profiles}, {CATALOG_ID})

    def test_source_and_commercial_exclusion_are_explicit(self):
        for p in ProfileLibrary(CATALOGS_DIR).list_profiles(category_id="solid-steel"):
            self.assertIsNone(p.manufacturer)
            self.assertEqual(p.catalog.issuer.name, "Steel Structures")
            self.assertEqual(p.catalog.source.source_type, "development_fixture")
            self.assertEqual(p.availability_status, "development_fixture")
            self.assertEqual(p.catalog.standard_references, ())
            self.assertEqual(p.source_metadata.mass_type, "calculated_fixture")
            self.assertEqual(p.source_metadata.density_kg_m3, 7850)
            self.assertIsNone(p.source_metadata.source_weight_p_kg_per_6m)
            self.assertTrue(p.ref.profile_id.isascii())
            self.assertNotIn("?", p.designation)
            self.assertEqual(dict(p.reported_section_properties), {})

    def test_creation_facade_area_mass_and_local_properties(self):
        for p in ProfileLibrary(CATALOGS_DIR).list_profiles(category_id="solid-steel"):
            g = build_section_geometry(p)
            adapted = profile_catalog.get(p.designation)
            self.assertAlmostEqual(adapted.area_cm2 * 100, g.area)
            self.assertAlmostEqual(adapted.mass_per_m, g.area * 0.00785)
            self.assertEqual(p.property_provenance["mass_per_length"].source_type, "calculated_fixture")
            self.assertEqual(p.property_provenance["area"].source_type, "calculated")
            self.assertFalse(section_geometry_mode_has_effect(p))
            self.assertEqual(build_section_geometry(p, "Detailed"), build_section_geometry(p, "Simplified"))

    def test_corner_aliases_resolve_without_extra_hotspots(self):
        for geometry in (build_square_bar(b=20), build_flat_bar(b=50, t=6.35)):
            for name in ("top_left", "top_right", "bottom_left", "bottom_right"):
                self.assertEqual(insertion_reference(geometry, name), insertion_reference(geometry, "outer_" + name))

    def test_non_catalog_json_in_other_subdirectories_is_not_discovered(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            (root / "dev").mkdir()
            (root / "audit").mkdir()
            (root / "dev" / "fixture.json").write_text(json.dumps(payload()), encoding="utf-8")
            (root / "audit" / "raw.json").write_text("{}", encoding="utf-8")
            self.assertEqual(len(ProfileLibrary(root).list_profiles()), 6)


class SolidSourceValidationTests(unittest.TestCase):
    def validate(self, raw):
        return validate_catalog_payload(raw, FIXTURE_PATH)[3]

    def test_fixture_requires_origin_availability_and_density(self):
        for target, key, value in (("catalog", "source_type", None),
                                   ("profile", "availability_status", "standard"),
                                   ("metadata", "density_kg_m3", None),
                                   ("metadata", "density_kg_m3", True)):
            raw = payload()
            obj = (raw["catalog"]["source"] if target == "catalog" else
                   raw["profiles"][0] if target == "profile" else raw["profiles"][0]["source_metadata"])
            obj[key] = value
            with self.subTest(target=target, key=key), self.assertRaises(CatalogValidationError):
                self.validate(raw)

    def test_solid_schema_rejects_extra_dimensions_family_mismatch_and_bad_flat(self):
        for mutate in (
            lambda p: p["profiles"][0]["geometry"].update(t=1),
            lambda p: p["series"][0].update(family="CHS"),
            lambda p: p["profiles"][-1]["geometry"].update(b=5),
        ):
            raw = payload()
            mutate(raw)
            with self.assertRaises(CatalogValidationError):
                self.validate(raw)

    def test_source_page_and_original_designation_can_be_absent(self):
        raw = payload()
        raw["profiles"][0]["source_metadata"].pop("source_designation")
        p = self.validate(raw)[0]
        self.assertIsNone(p.source_metadata.source_page)
        self.assertIsNone(p.source_metadata.source_designation)

    def test_invalid_optional_page_is_still_rejected(self):
        for page in (False, 0, -1, 1.5, "2"):
            raw = payload()
            raw["profiles"][0]["source_metadata"]["source_page"] = page
            with self.assertRaises(CatalogValidationError):
                self.validate(raw)

    def test_fixture_cannot_claim_published_mass(self):
        raw = payload()
        raw["profiles"][0]["source_metadata"]["source_mass_per_length_kg_m"] = 2.5
        with self.assertRaises(CatalogValidationError):
            self.validate(raw)

    def test_wrong_fixture_mass_is_rejected_at_library_boundary(self):
        raw = payload()
        raw["profiles"][0]["physical_properties"]["mass_per_length"] = 99
        with tempfile.TemporaryDirectory() as name:
            (Path(name) / "wrong.json").write_text(json.dumps(raw), encoding="utf-8")
            with self.assertRaisesRegex(CatalogValidationError, "massa de fixture"):
                ProfileLibrary(Path(name)).reload()

    def test_published_kg_per_m_needs_no_tuper_fields_for_any_family(self):
        for tubular in (False, True):
            raw = payload()
            raw["profiles"] = raw["profiles"][:1]
            raw["series"] = raw["series"][:1]
            raw["catalog"]["source"].pop("source_type")
            record = raw["profiles"][0]
            record.update(availability_status="standard", source_metadata={
                "mass_type": "published", "source_mass_per_length_kg_m": 2.5,
            })
            if tubular:
                raw["series"][0].update(geometry_type="hollow_section", family="CHS")
                record.update(geometry_type="hollow_section", geometry={"d": 20, "t": 2})
            with tempfile.TemporaryDirectory() as name:
                (Path(name) / "example.json").write_text(json.dumps(raw), encoding="utf-8")
                p = ProfileLibrary(Path(name)).list_profiles()[0]
                self.assertEqual(p.physical_properties.mass_per_length_kg_m, 2.5)
                self.assertEqual(p.property_provenance["mass_per_length"].source_type, "published")
                self.assertIsNone(p.source_metadata.source_weight_basis_mm)

    def test_published_mass_conflicts_are_rejected(self):
        raw = payload()
        raw["profiles"][0]["source_metadata"] = {"mass_type": "published", "source_mass_per_length_kg_m": 2.5}
        raw["profiles"][0]["physical_properties"]["mass_per_length"] = 7
        with self.assertRaises(CatalogValidationError):
            self.validate(raw)

    def test_tuper_pair_and_six_metre_basis_are_still_enforced(self):
        source = json.loads((CATALOGS_DIR / "tuper_hollow_2024.json").read_text(encoding="utf-8"))
        source["profiles"] = source["profiles"][:1]
        for mutation in (None, 5000):
            raw = copy.deepcopy(source)
            raw["profiles"][0]["source_metadata"]["source_weight_basis_mm"] = mutation
            with self.assertRaises(CatalogValidationError):
                self.validate(raw)


if __name__ == "__main__":
    unittest.main()
