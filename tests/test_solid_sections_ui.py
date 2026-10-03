"""Solid-bar presentation and native annotation contracts without a GUI session."""

from __future__ import annotations

from dataclasses import replace
import math
import types
import unittest

from freecad.SteelStructures.profiles import (
    CatalogMetadata, CatalogSource, PhysicalProperties, ProfileDefinition, ProfileRef,
    build_section_geometry, section_insertion_references,
)
from freecad.SteelStructures.profiles.models import ProfileSourceMetadata
from freecad.SteelStructures.profiles.presentation import (
    profile_dimension_rows, profile_preview_dimension_rows,
    profile_property_groups, profile_source_groups,
)
from freecad.SteelStructures.profiles.preview_geometry import (
    SchematicCubic2D, schematic_section_for_geometry, transform_preview_point,
)
from tests.test_profile_browser import (
    _FakeScene, _load_browser_runtime_module, _load_preview_runtime_module,
)


def fixture(variant, dimensions):
    catalog = CatalogMetadata(
        id="test-solid-ui", name="Steel Structures — fixture de desenvolvimento",
        catalog_version="0", manufacturer=None, units={},
        source=CatalogSource("fixture de desenvolvimento", source_type="development_fixture"),
    )
    area = (math.pi * dimensions["d"] ** 2 / 4.0 if variant == "circular"
            else dimensions["b"] * dimensions.get("t", dimensions["b"]))
    return ProfileDefinition(
        ref=ProfileRef(catalog.id, variant), designation=f"{variant} fixture",
        equivalent_designation=None, aliases=(), catalog_markers=(),
        availability_status="test-only", geometry_status="released", series_id=variant,
        category_id="solid-steel", manufacturer=None, family=variant.upper(),
        geometry_type="solid_section", geometry_variant=variant,
        geometry_notes="fixture nominal ideal", geometry=dimensions,
        physical_properties=PhysicalProperties(area * 0.00785, area),
        section_properties={}, reported_section_properties={}, section_property_override=None,
        centroid_from_top_flange_face=None, centroid={"x": 0.0, "y": 0.0}, catalog=catalog,
        source_metadata=ProfileSourceMetadata(
            mass_type="calculated_fixture", density_kg_m3=7850.0,
        ),
    )


class SolidSectionPresentationTests(unittest.TestCase):
    def test_browser_subtitle_identifies_development_fixture_without_opening_source_tab(self):
        module = _load_browser_runtime_module()
        profile = fixture("circular", {"d": 20.0})
        self.assertEqual(module._profile_subtitle(profile, "Barra Redonda"),
                         "Barra Redonda — Steel Structures — fixture de desenvolvimento")

    def test_dimension_fields_follow_bar_semantics_and_keep_units(self):
        cases = (
            ("circular", {"d": 6.35}, {"Diâmetro (D)": "6,35 mm"}, {"ØD": "6,35 mm"}),
            ("square", {"b": 12.7}, {"Lado (B)": "12,7 mm"}, {"B": "12,7 mm"}),
            ("rectangular", {"b": 50.8, "t": 6.35},
             {"Largura (B)": "50,8 mm", "Espessura (t)": "6,35 mm"},
             {"B": "50,8 mm", "t": "6,35 mm"}),
        )
        for variant, dimensions, expected_fields, expected_preview in cases:
            with self.subTest(variant=variant):
                profile = fixture(variant, dimensions)
                self.assertEqual({row.label: row.value for row in profile_dimension_rows(profile)},
                                 expected_fields)
                self.assertEqual({row.label: row.value for row in profile_preview_dimension_rows(profile)},
                                 expected_preview)
                self.assertEqual(dict(profile.geometry), dimensions)

    def test_small_bar_mass_and_area_have_useful_precision_without_changing_values(self):
        profile = fixture("circular", {"d": 6.35})
        before = profile.physical_properties
        rows = {row.label: row for group in profile_property_groups(profile) for row in group.rows}
        self.assertEqual(rows["Massa linear"].value, "0,249 kg/m")
        self.assertEqual(rows["Área"].value, "0,32 cm²")
        self.assertIn("fixture", rows["Massa linear"].tooltip)
        self.assertEqual(profile.physical_properties, before)

    def test_fixture_provenance_is_explicit_without_fabricated_source_page(self):
        profile = fixture("square", {"b": 10.0})
        groups = profile_source_groups(profile)
        rows = {row.label: row.value for group in groups for row in group.rows}
        self.assertEqual(rows["Origem"], "Steel Structures — fixture de desenvolvimento")
        self.assertEqual(rows["Massa linear"], "Calculada para a fixture")
        self.assertEqual(rows["Densidade adotada"], "7.850 kg/m³")
        self.assertNotIn("Página da fonte", rows)
        self.assertNotIn("Fabricante", rows)
        self.assertNotIn("Norma", rows)
        self.assertEqual(rows["Definição"], "Seção maciça nominal ideal")

    def test_absent_source_page_is_omitted_outside_fixture_branch_too(self):
        profile = fixture("square", {"b": 10.0})
        profile = replace(profile, catalog=replace(
            profile.catalog, source=CatalogSource("fonte de teste"),
        ))
        rows = {row.label: row.value for group in profile_source_groups(profile) for row in group.rows}
        self.assertNotIn("Página da fonte", rows)


class SolidSectionInsertionAndPreviewTests(unittest.TestCase):
    def test_reference_counts_and_face_corner_points_are_real(self):
        for variant, dimensions, expected_count in (
            ("circular", {"d": 12.0}, 5),
            ("square", {"b": 12.0}, 9),
            ("rectangular", {"b": 80.0, "t": 4.0}, 9),
        ):
            with self.subTest(variant=variant):
                geometry = build_section_geometry(fixture(variant, dimensions))
                references = {reference.id: reference for reference in section_insertion_references(geometry)}
                self.assertEqual(len(references), expected_count)
                self.assertEqual(references["centroid"].point, geometry.origin)
                self.assertEqual(references["left"].point.x, geometry.bounds.min_x)
                self.assertEqual(references["right"].point.x, geometry.bounds.max_x)
                self.assertEqual(references["top"].point.y, geometry.bounds.max_y)
                self.assertEqual(references["bottom"].point.y, geometry.bounds.min_y)
                if expected_count == 9:
                    self.assertEqual(references["top_right"].point.x, geometry.bounds.max_x)
                    self.assertEqual(references["top_right"].point.y, geometry.bounds.max_y)

    def test_flat_miniature_preserves_proportions_and_rotation_of_insertion(self):
        geometry = build_section_geometry(fixture("rectangular", {"b": 80.0, "t": 4.0}))
        schematic = schematic_section_for_geometry(geometry)
        self.assertIsNotNone(schematic)
        self.assertFalse(schematic.inner_segments)
        width = max(p.x for p in schematic.outline) - min(p.x for p in schematic.outline)
        height = max(p.y for p in schematic.outline) - min(p.y for p in schematic.outline)
        self.assertAlmostEqual(width / height, 20.0)
        right = next(item.point for item in schematic.references if item.id == "right")
        rotated = transform_preview_point(right, schematic.center, 90.0)
        self.assertAlmostEqual(rotated.x, 0.0)
        self.assertAlmostEqual(abs(rotated.y), abs(right.x))

    def test_round_miniature_has_curves_and_no_hole(self):
        geometry = build_section_geometry(fixture("circular", {"d": 6.35}))
        schematic = schematic_section_for_geometry(geometry)
        self.assertTrue(schematic.segments)
        self.assertTrue(all(isinstance(segment, SchematicCubic2D) for segment in schematic.segments))
        self.assertFalse(schematic.inner_segments)
        self.assertEqual(len(schematic.references), 5)

    def renderer(self):
        module = _load_preview_runtime_module()
        scene = _FakeScene()
        renderer = object.__new__(module.SectionPreviewView)
        renderer.scene = lambda: scene
        renderer.viewport = lambda: types.SimpleNamespace(width=lambda: 500, height=lambda: 240)
        return module, renderer, scene

    def test_native_dimensions_have_only_the_requested_symbols(self):
        cases = (
            ("circular", {"d": 6.35}, ("<b>Ø</b>&nbsp;6,35",)),
            ("square", {"b": 12.7}, ("<b>(b)</b>&nbsp;12,7",)),
            ("rectangular", {"b": 50.8, "t": 6.35},
             ("<b>(b)</b>&nbsp;50,8", "<b>(t)</b>&nbsp;6,35")),
        )
        for variant, dimensions, expected in cases:
            with self.subTest(variant=variant):
                _module, renderer, scene = self.renderer()
                profile = fixture(variant, dimensions)
                geometry = build_section_geometry(profile)
                renderer._add_dimensions(geometry, {
                    row.label: row.value for row in profile_preview_dimension_rows(profile)
                })
                annotations = [item.html for item in scene.text_items]
                self.assertEqual(len(annotations), len(expected))
                for actual, substring in zip(annotations, expected):
                    self.assertIn(substring, actual)
                self.assertTrue(all(item.flag == (1, True) for item in scene.text_items))

    def test_flat_thickness_dimension_is_vertical_beside_the_real_faces(self):
        _module, renderer, scene = self.renderer()
        profile = fixture("rectangular", {"b": 80.0, "t": 4.0})
        geometry = build_section_geometry(profile)
        renderer._add_dimensions(geometry, {"B": "80 mm", "t": "4 mm"})
        self.assertTrue(any(
            x1 == x2 and x1 > geometry.bounds.max_x and y1 == -2.0 and y2 == 2.0
            for x1, y1, x2, y2, _pen in scene.lines
        ))

    def test_dimension_fit_is_proportional_for_small_large_and_flat_bars(self):
        module, renderer, _scene = self.renderer()
        for variant, first, second in (
            ("circular", {"d": 3.0}, {"d": 300.0}),
            ("square", {"b": 3.0}, {"b": 300.0}),
            ("rectangular", {"b": 10.0, "t": 0.5}, {"b": 1000.0, "t": 50.0}),
        ):
            with self.subTest(variant=variant):
                small = build_section_geometry(fixture(variant, first))
                large = build_section_geometry(fixture(variant, second))
                u_small = renderer._hollow_units_per_pixel(small.bounds)
                u_large = renderer._hollow_units_per_pixel(large.bounds)
                self.assertAlmostEqual(u_large / u_small, 100.0)
                first_rect = module._hollow_section_envelope(small.bounds, u_small)
                second_rect = module._hollow_section_envelope(large.bounds, u_large)
                for a, b in zip(first_rect, second_rect):
                    self.assertAlmostEqual(b, a * 100.0)

    def test_property_axes_do_not_dwarf_a_small_bar(self):
        _module, renderer, scene = self.renderer()
        geometry = build_section_geometry(fixture("circular", {"d": 3.0}))
        renderer._add_axes(geometry)
        x_axis = scene.lines[0]
        self.assertLess(x_axis[2] - x_axis[0], 6.0)
        self.assertEqual((x_axis[1], x_axis[3]), (0.0, 0.0))


if __name__ == "__main__":
    unittest.main()
