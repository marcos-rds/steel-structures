"""Permanent Stage-A contracts for the 125 NBR 6355 Tabela A.2 simple U sizes."""

import copy
import json
import math
from pathlib import Path
import unittest

from freecad.SteelStructures import profile_catalog
from freecad.SteelStructures.paths import CATALOGS_DIR
from freecad.SteelStructures.profiles import (
    ArcSegment2D, CatalogValidationError, LineSegment2D, ProfileLibrary,
    SectionGeometryError, build_section_geometry, build_simple_u_mean_path,
    build_simple_u_section, insertion_reference, insertion_translation,
    path_self_intersections, physical_section_properties,
    section_geometry_mode_has_effect, section_insertion_references,
    simple_u_derived_dimensions,
)
from freecad.SteelStructures.profiles.validation import validate_catalog_payload
from freecad.SteelStructures.assemblies.transforms import SectionTransform, transform_section
from scripts import generate_nbr6355_simple_u_catalog as generator

CATALOG_ID = "abnt-nbr-6355-2012-a2"
SERIES_ID = "u-simple-nbr-6355"
PATH = CATALOGS_DIR / "abnt_nbr_6355_2012_a2.json"
REFERENCE_IDS = (
    "centroid", "web_center", "web_back", "rear_top", "rear_bottom",
    "flange_top_tip", "flange_bottom_tip", "outer_top_mid", "outer_bottom_mid",
)


class SimpleUCatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw = json.loads(PATH.read_text(encoding="utf-8"))
        cls.snapshot = json.loads(generator.SNAPSHOT.read_text(encoding="utf-8"))
        cls.library = ProfileLibrary(CATALOGS_DIR)
        cls.profiles = cls.library.list_profiles(series_id=SERIES_ID)

    def test_all_125_unique_bitolas_and_numeric_order(self):
        self.assertEqual(len(self.profiles), 125)
        self.assertEqual(len({p.ref for p in self.profiles}), 125)
        self.assertEqual(len({p.designation for p in self.profiles}), 125)
        keys = [tuple(p.geometry[n] for n in ("bw", "bf", "tn")) for p in self.profiles]
        self.assertEqual(keys, sorted(keys))
        self.assertEqual(len(set(keys)), 125)
        self.assertEqual(len({key[:2] for key in keys}), 14)
        self.assertEqual(keys[0], (50, 25, 1.2))
        self.assertEqual(keys[-1], (300, 100, 8))

    def test_every_source_cell_and_canonical_unit_is_preserved(self):
        by_row = {p.source_metadata.source_row: p for p in self.profiles}
        self.assertEqual(set(by_row), set(range(4, 129)))
        specs = {"ix": ("H", 1e4), "wx": ("I", 1e3), "rx": ("J", 10),
                 "x0": ("L", 10), "iy": ("M", 1e4), "wy": ("N", 1e3),
                 "ry": ("O", 10), "it": ("P", 1e4), "cw": ("Q", 1e6), "r0": ("R", 10)}
        for row, profile in by_row.items():
            cells = self.snapshot["cells"][str(row)]
            with self.subTest(row=row, profile=profile.designation):
                self.assertEqual(profile.source_metadata.source_designation, cells["A"])
                self.assertIn(cells["A"], profile.aliases)
                for name, column in (("bw", "D"), ("bf", "E"), ("t", "F"), ("tn", "F"), ("ri", "G")):
                    self.assertEqual(profile.geometry[name], float(cells[column]))
                self.assertEqual(profile.physical_properties.mass_per_length_kg_m, float(cells["B"]))
                self.assertAlmostEqual(profile.physical_properties.area_mm2, float(cells["C"]) * 100, places=9)
                self.assertAlmostEqual(profile.centroid["x"], float(cells["K"]) * 10, places=10)
                self.assertEqual(set(profile.section_properties), set(specs))
                self.assertEqual(profile.reported_section_properties, profile.section_properties)
                self.assertIsNone(profile.section_property_override)
                for name, (column, scale) in specs.items():
                    self.assertTrue(math.isclose(profile.section_properties[name], float(cells[column]) * scale, rel_tol=1e-14))
                source = profile.source_metadata
                self.assertEqual(source.source_table, "A.2")
                self.assertEqual(source.source_pdf_page - source.source_page, 6)
                self.assertEqual(source.mass_basis, "normative_table")
                self.assertEqual(profile.property_provenance["mass_per_length"].source_type, "published")
                self.assertEqual(source.source_mass_per_length_kg_m, float(cells["B"]))

    def test_normative_identity_and_shared_creation_capability(self):
        for profile in self.profiles:
            self.assertEqual(profile.ref.catalog_id, CATALOG_ID)
            self.assertEqual((profile.geometry_type, profile.geometry_variant), ("cold_formed_channel", "simple_u"))
            self.assertEqual(profile.family, "U")
            self.assertIsNone(profile.manufacturer)
            self.assertEqual(profile.catalog.issuer.id, "abnt")
            self.assertIn("Tabela A.2", profile.catalog.standard_references)
            self.assertNotIn("D", profile.geometry)
            self.assertTrue(profile_catalog.is_creation_profile(profile))
        self.assertIn(SERIES_ID, profile_catalog.SUPPORTED_CREATION_SERIES)
        self.assertEqual(len(self.library.list_profiles(series_id="ue-nbr-6355")), 85)
        self.assertEqual(len(self.library.list_profiles(series_id="u")), 12)
        self.assertEqual(len(profile_catalog.designations("Aço Dobrado")), 210)

    def test_snapshot_fingerprint_and_reproducible_catalog(self):
        self.assertEqual(generator.fingerprint(self.snapshot["cells"]),
                         "a0394c448abc0f1c8ecc5beddaf312816dd0562106b53627d878d675cb33883f")
        self.assertEqual(generator.render_catalog(self.snapshot), PATH.read_bytes())
        changed = copy.deepcopy(self.snapshot)
        changed["cells"]["120"]["G"] = "9.53"
        with self.assertRaises(ValueError):
            generator.build_catalog(changed)
        self.assertNotIn("U300x100x2,65", {p.source_metadata.source_designation for p in self.profiles})
        self.assertEqual(self.raw["generation_audit"]["source_corrections_applied"], [])

    def test_radius_threshold_and_fractional_radius(self):
        for profile in self.profiles:
            tn, ri = profile.geometry["tn"], profile.geometry["ri"]
            self.assertAlmostEqual(ri, tn if tn <= 6.3 else 1.5 * tn)
        p = next(p for p in self.profiles if p.source_metadata.source_row == 120)
        self.assertEqual(p.designation, "U 250 × 100 × 6,35")
        self.assertEqual(p.geometry["ri"], 9.525)
        self.assertNotEqual(p.geometry["ri"], p.geometry["t"])
        self.assertEqual(p.source_metadata.source_pdf_page, 30)

    def test_invalid_simple_u_catalog_dimensions_are_rejected(self):
        for changes in ({"ri": 0}, {"ri": -1}, {"ri": float("nan")},
                        {"ri": float("inf")}, {"t": 1.1}, {"D": 10},
                        {"bw": 4.8}, {"bf": 2.4}, {"tn": 6.35}, {"ri": True}):
            value = copy.deepcopy(self.raw)
            value["profiles"][0]["geometry"].update(changes)
            with self.subTest(changes=changes), self.assertRaises(CatalogValidationError):
                validate_catalog_payload(value, Path("invalid-simple-u.json"))
        value = copy.deepcopy(self.raw)
        value["profiles"][116]["geometry"]["ri"] = 9.53
        with self.assertRaises(CatalogValidationError):
            validate_catalog_payload(value, Path("rounded-radius.json"))

    def test_printed_area_discrepancy_is_not_used_as_property_override(self):
        # Item 10 prints one u1, although there are two physical bends. The
        # table is authoritative; this diagnostic does not repair the formula.
        for profile in self.profiles:
            bw, bf, t, ri = (profile.geometry[n] for n in ("bw", "bf", "t", "ri"))
            a, b, rm = bw - 2 * (ri + t), bf - ri - t, ri + t / 2
            table = profile.physical_properties.area_mm2
            physical = t * (a + 2 * b + math.pi * rm)
            printed = t * (a + 2 * b + 1.571 * rm)
            with self.subTest(profile=profile.designation):
                self.assertLessEqual(abs(table - physical), .5 + 1e-9)  # 0.005 cm² rounding
                self.assertGreater(abs(table - printed), .5)
                self.assertNotEqual(table, physical)
        first = self.profiles[0]
        self.assertAlmostEqual(first.physical_properties.area_mm2, 115)
        self.assertEqual(first.physical_properties.mass_per_length_kg_m, .90)


class SimpleUGeometryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.profiles = ProfileLibrary(CATALOGS_DIR).list_profiles(series_id=SERIES_ID)

    def test_all_sizes_have_exact_bends_closed_contour_and_analytic_properties(self):
        for profile in self.profiles:
            inputs = {n: profile.geometry[n] for n in ("bw", "bf", "t", "ri")}
            bw, bf, t, ri = (inputs[n] for n in ("bw", "bf", "t", "ri"))
            folded = build_simple_u_mean_path(**inputs)
            geometry = build_section_geometry(profile)
            with self.subTest(profile=profile.designation):
                self.assertFalse(folded.mean_path.closed)
                self.assertEqual(len(folded.mean_path.segments), 5)
                arcs = [s for s in folded.mean_path.segments if isinstance(s, ArcSegment2D)]
                self.assertEqual(len(arcs), 2)
                for arc in arcs:
                    self.assertAlmostEqual(arc.radius, ri + t / 2, places=10)
                    self.assertAlmostEqual(arc.sweep, math.pi / 2, places=12)
                self.assertEqual(folded.mean_path.segments[0].start.x, bf)
                self.assertEqual(folded.mean_path.segments[-1].end.x, bf)
                path = geometry.outer_path
                self.assertTrue(path.closed)
                self.assertFalse(geometry.inner_paths)
                self.assertEqual(len(path.segments), 12)
                radii = sorted(s.radius for s in path.segments if isinstance(s, ArcSegment2D))
                for actual, expected in zip(radii, [ri, ri, ri + t, ri + t]):
                    self.assertAlmostEqual(actual, expected, places=10)
                self.assertEqual(len(radii), 4)
                for previous, current in zip(path.segments, path.segments[1:] + path.segments[:1]):
                    self.assertEqual(previous.end, current.start)
                self.assertFalse(path_self_intersections(path))
                self.assertAlmostEqual(geometry.bounds.width, bf, places=9)
                self.assertAlmostEqual(geometry.bounds.height, bw, places=9)
                # Independent decomposition: web + two straight flanges + two
                # annular quadrants. No use of the core's numerical integrator.
                re, rm = ri + t, ri + t / 2
                a, b = bw - 2 * re, bf - re
                area = t * (a + 2 * b + math.pi * rm)
                cx = (t * a * t / 2 + t * b * (re + bf)
                      + math.pi * rm * t * re - 2 * (re ** 3 - ri ** 3) / 3) / area
                self.assertAlmostEqual(geometry.area, area, places=8)
                self.assertAlmostEqual(-geometry.bounds.min_x, cx, places=8)
                self.assertAlmostEqual(geometry.bounds.min_y, -bw / 2, places=9)
                physical = physical_section_properties(path)
                self.assertAlmostEqual(physical.area, area, places=8)
                self.assertAlmostEqual(physical.centroid_x, 0, places=9)
                self.assertAlmostEqual(physical.centroid_y, 0, places=9)
                self.assertGreater(physical.ix, 0)
                self.assertGreater(physical.iy, 0)

    def test_nine_semantic_references_for_every_size(self):
        for profile in self.profiles:
            g = build_section_geometry(profile)
            refs = section_insertion_references(g)
            s = dict(g.dimension_stations)
            bw, bf, t, ri = (profile.geometry[n] for n in ("bw", "bf", "t", "ri"))
            rear = g.bounds.min_x
            expected = ((0, 0), (rear + t / 2, 0), (rear, 0),
                        (rear, bw / 2), (rear, -bw / 2),
                        (rear + bf, bw / 2), (rear + bf, -bw / 2),
                        (rear + (ri + t + bf) / 2, bw / 2),
                        (rear + (ri + t + bf) / 2, -bw / 2))
            with self.subTest(profile=profile.designation):
                self.assertEqual(tuple(r.id for r in refs), REFERENCE_IDS)
                self.assertEqual(len({r.point for r in refs}), 9)
                for ref, point in zip(refs, expected):
                    self.assertAlmostEqual(ref.point.x, point[0], places=9)
                    self.assertAlmostEqual(ref.point.y, point[1], places=9)
                    self.assertEqual(insertion_reference(g, ref.label), ref)
                    self.assertEqual(insertion_reference(g, ref.id), ref)
                    self.assertEqual(insertion_translation(g, ref.id), (-ref.point.x, -ref.point.y))
                    self.assertNotIn("enrijecedor", ref.label)
                self.assertEqual(insertion_reference(g, "unknown"), refs[0])
                self.assertAlmostEqual(s["flange_web_tangent_x"], rear + ri + t)

    def test_simplified_preserves_datum_references_and_catalog_properties(self):
        for profile in self.profiles:
            detailed = build_section_geometry(profile)
            simple = build_section_geometry(profile, "Simplified")
            with self.subTest(profile=profile.designation):
                self.assertTrue(section_geometry_mode_has_effect(profile))
                self.assertEqual(simple.bounds, detailed.bounds)
                self.assertEqual(simple.origin, detailed.origin)
                self.assertEqual(simple.dimension_stations, detailed.dimension_stations)
                self.assertEqual(section_insertion_references(simple), section_insertion_references(detailed))
                self.assertEqual(len(simple.outer_path.segments), 8)
                self.assertTrue(all(isinstance(s, LineSegment2D) for s in simple.outer_path.segments))
                self.assertFalse(path_self_intersections(simple.outer_path))
                bw, bf, t = (profile.geometry[n] for n in ("bw", "bf", "t"))
                self.assertAlmostEqual(simple.area, t * (bw + 2 * bf - 2 * t), places=8)
                self.assertGreater(simple.area, detailed.area)

    def test_rotations_and_reflections_preserve_area_and_insertion_positions(self):
        for p in (self.profiles[0], self.profiles[-1], self.profiles[116]):
            g = build_section_geometry(p)
            for angle in (0, 37, 90, 180, 270):
                for mirror in (False, True):
                    transform = SectionTransform(angle, mirror)
                    rotated, refs = transform_section(g, transform)
                    with self.subTest(profile=p.designation, angle=angle, mirror=mirror):
                        self.assertAlmostEqual(rotated.area, g.area, places=8)
                        self.assertFalse(path_self_intersections(rotated.outer_path))
                        self.assertEqual(tuple(r.id for r in refs), REFERENCE_IDS)
                        for old, new in zip(section_insertion_references(g), refs):
                            self.assertEqual(new.point, transform.point(old.point))

    def test_independent_radius_and_invalid_dimensions(self):
        inputs = dict(bw=100, bf=50, t=2.65, ri=7.125)
        g = build_simple_u_section(**inputs)
        self.assertEqual(dict(g.dimension_stations)["internal_radius"], 7.125)
        dims = simple_u_derived_dimensions(**inputs)
        self.assertEqual(dims.b, 50 - 7.125 - 2.65)
        for key in inputs:
            for value in (0, -1, float("inf"), float("nan"), True, None):
                with self.subTest(key=key, value=value), self.assertRaises(SectionGeometryError):
                    build_simple_u_section(**dict(inputs, **{key: value}))
        for values in (dict(inputs, bw=2 * (7.125 + 2.65)), dict(inputs, bf=7.125 + 2.65)):
            with self.assertRaises(SectionGeometryError):
                build_simple_u_section(**values)


if __name__ == "__main__":
    unittest.main()
