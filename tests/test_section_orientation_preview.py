"""Pure schematic geometry and interaction contracts for the creation preview."""

from __future__ import annotations

import math
import unittest
from pathlib import Path

from freecad.SteelStructures.paths import CATALOGS_DIR
from freecad.SteelStructures.profiles import (
    GeometryTemporarilyUnavailableError, ProfileLibrary, build_section_geometry,
)
from freecad.SteelStructures.profiles.preview_geometry import (
    background_needs_dark_outline_halo, nearest_reference, preview_screen_point,
    profile_presentation_radius, schematic_section_for_geometry,
    SchematicCubic2D, SchematicLine2D, transform_preview_point,
)


class SectionOrientationPreviewGeometryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.library = ProfileLibrary(CATALOGS_DIR)

    def geometry(self, query):
        return build_section_geometry(self.library.search(query)[0])

    def schematic(self, query):
        return schematic_section_for_geometry(self.geometry(query))

    def test_every_bitola_in_each_supported_family_uses_one_schematic(self):
        pairs = (
            ("W150x13", "W360x32.9", "i_section"),
            ("HP310x79", "HP310x132", "i_section"),
            ('I3x8.48', 'I6x22.00', "i_section"),
            ("U3x6.10", "U12x37.00", "channel_section"),
            ("Ue 50x25x10x1.20", "Ue 300x85x25x2.25", "cold_formed_channel"),
            ("L40x3", "L100x9", "equal_angle"),
            ("L2x1/4", "L8x3/4", "equal_angle"),
            ("T5/8x1/8", "T2x1/4", "tee_section"),
        )
        for first, second, geometry_type in pairs:
            with self.subTest(first=first, second=second):
                left, right = self.schematic(first), self.schematic(second)
                self.assertIsNotNone(left)
                self.assertEqual(left.typology_key[0], geometry_type)
                self.assertEqual(left.outline, right.outline)
                self.assertEqual(left.references, right.references)

    def test_real_reference_ids_and_labels_map_to_schematic_hotspots(self):
        expected = {
            "W150x13": {"centroid", "left", "right", "top", "bottom",
                         "top_left", "top_right", "bottom_left", "bottom_right"},
            "I3x8.48": {"centroid", "left", "right", "top", "bottom",
                          "top_left", "top_right", "bottom_left", "bottom_right"},
            "U6x12.2": {"centroid", "web_center", "web_back", "rear_top",
                         "rear_bottom", "flange_top_tip", "flange_bottom_tip"},
            "Ue 150x60x20x3.00": {
                "centroid", "web_center", "web_back", "rear_top", "rear_bottom",
                "lip_top_tip", "lip_bottom_tip", "outer_top_mid",
                "outer_bottom_mid", "outer_lip_top_corner", "outer_lip_bottom_corner",
            },
            "L50x5": {"centroid", "envelope_center", "outer_corner", "top_tip", "right_tip",
                       "inner_corner"},
            "T2x1/4": {"centroid", "top", "bottom", "top_left", "top_right"},
        }
        for query, identifiers in expected.items():
            schematic = self.schematic(query)
            self.assertEqual({item.id for item in schematic.references}, identifiers)
            self.assertTrue(all(item.label for item in schematic.references))

    def test_tee_schematic_has_parallel_faces_and_centroid_above_bbox_center(self):
        schematic = self.schematic("T2x1/4")
        self.assertEqual(len(schematic.outline), 8)
        self.assertTrue(all(isinstance(segment, SchematicLine2D)
                            for segment in schematic.segments))
        bounds_center_y = (
            min(point.y for point in schematic.outline)
            + max(point.y for point in schematic.outline)
        ) / 2.0
        centroid = next(item.point for item in schematic.references
                        if item.id == "centroid")
        self.assertGreater(centroid.y, bounds_center_y)
        radius = profile_presentation_radius(schematic.outline, schematic.center)
        for angle in (0, 45, 90, 180):
            rotated = tuple(transform_preview_point(point, schematic.center, angle)
                            for point in schematic.outline)
            self.assertAlmostEqual(
                profile_presentation_radius(rotated, schematic.center), radius,
            )

    def test_rolled_channel_has_tapered_inner_faces_and_thicker_roots(self):
        schematic = self.schematic("U6x12.2")
        inner_faces = [
            segment for segment in schematic.segments
            if isinstance(segment, SchematicLine2D)
            and segment.start.x > 0.5 and segment.end.x < 0.0
        ]
        self.assertEqual(len(inner_faces), 2)
        lower_inner = next(segment for segment in inner_faces if segment.start.y < 0.0)
        self.assertNotAlmostEqual(lower_inner.start.y, lower_inner.end.y)
        tip_thickness = abs(-1.0 - lower_inner.start.y)
        root_thickness = abs(-1.0 - lower_inner.end.y)
        self.assertGreater(root_thickness, tip_thickness * 1.5)

    def test_rolled_channel_uses_large_root_and_smaller_toe_curves(self):
        schematic = self.schematic("U6x12.2")
        curves = [
            segment for segment in schematic.segments
            if isinstance(segment, SchematicCubic2D)
        ]
        root_curves = [
            curve for curve in curves
            if min(curve.start.x, curve.end.x) < -0.15
        ]
        toe_curves = [curve for curve in curves if curve not in root_curves]
        self.assertEqual((len(root_curves), len(toe_curves)), (2, 4))
        root_span = max(
            math.hypot(curve.end.x - curve.start.x, curve.end.y - curve.start.y)
            for curve in root_curves
        )
        toe_span = max(
            math.hypot(curve.end.x - curve.start.x, curve.end.y - curve.start.y)
            for curve in toe_curves
        )
        self.assertGreater(root_span, toe_span)

    def test_tapered_i_has_its_own_inclined_symmetric_schematic(self):
        parallel = self.schematic("W150x13")
        tapered = self.schematic("I3x8.48")
        self.assertNotEqual(tapered.outline, parallel.outline)
        self.assertTrue(any(
            isinstance(segment, SchematicCubic2D) for segment in tapered.segments
        ))
        inner_faces = [
            segment for segment in tapered.segments
            if isinstance(segment, SchematicLine2D)
            and max(abs(segment.start.x), abs(segment.end.x)) > 0.6
            and 0.1 < min(abs(segment.start.x), abs(segment.end.x)) < 0.3
            and abs(segment.start.y - segment.end.y) > 0.05
        ]
        self.assertEqual(len(inner_faces), 4)
        for face in inner_faces:
            self.assertNotAlmostEqual(face.start.y, face.end.y)

        reflected = {
            (round(-point.x, 8), round(-point.y, 8)) for point in tapered.outline
        }
        self.assertEqual(
            reflected,
            {(round(point.x, 8), round(point.y, 8)) for point in tapered.outline},
        )

    def test_tapered_i_root_is_thicker_and_curves_are_larger_than_toes(self):
        schematic = self.schematic("I5x14.88")
        lower_right = next(
            segment for segment in schematic.segments
            if isinstance(segment, SchematicLine2D)
            and segment.start.x > 0.6 and 0.1 < segment.end.x < 0.3
            and segment.start.y < 0.0
        )
        tip_thickness = abs(-1.0 - lower_right.start.y)
        root_thickness = abs(-1.0 - lower_right.end.y)
        self.assertGreater(root_thickness, tip_thickness)
        schematic_angle = math.degrees(math.atan2(
            abs(lower_right.end.y - lower_right.start.y),
            abs(lower_right.end.x - lower_right.start.x),
        ))
        self.assertGreater(schematic_angle, 12.0)
        self.assertLess(schematic_angle, 15.5)

        curves = [
            segment for segment in schematic.segments
            if isinstance(segment, SchematicCubic2D)
        ]
        root_curves = [
            curve for curve in curves
            if max(abs(curve.start.x), abs(curve.end.x)) < 0.3
        ]
        toe_curves = [curve for curve in curves if curve not in root_curves]
        self.assertEqual(len(root_curves), 4)
        self.assertGreater(
            min(math.hypot(
                curve.end.x - curve.start.x, curve.end.y - curve.start.y
            ) for curve in root_curves),
            min(math.hypot(
                curve.end.x - curve.start.x, curve.end.y - curve.start.y
            ) for curve in toe_curves),
        )

    def test_w_hp_remain_parallel_and_all_tapered_i_sizes_share_new_scheme(self):
        w = self.schematic("W150x13")
        hp = self.schematic("HP310x132")
        tapered = tuple(self.schematic(query) for query in (
            "I3x8.48", "I3x9.68", "I4x11.46", "I4x12.65",
            "I5x14.88", "I5x18.24", "I6x18.60", "I6x22.00",
        ))
        self.assertEqual(w.outline, hp.outline)
        self.assertEqual(w.segments, hp.segments)
        for schematic in tapered[1:]:
            self.assertEqual(schematic.outline, tapered[0].outline)
            self.assertEqual(schematic.segments, tapered[0].segments)
            self.assertEqual(schematic.references, tapered[0].references)
        self.assertNotEqual(w.outline, tapered[0].outline)
        self.assertEqual(len(tapered[0].references), 9)
        parallel_radius = profile_presentation_radius(w.outline, w.center)
        tapered_radius = profile_presentation_radius(
            tapered[0].outline, tapered[0].center
        )
        self.assertLess(abs(parallel_radius - tapered_radius) / parallel_radius, 0.03)

    def test_u_envelope_and_hotspot_semantics_remain_stable(self):
        schematics = tuple(
            self.schematic(query)
            for query in ("U3x6.10", "U4x8.04", "U6x12.2", "U8x17.1", "U10x22.77", "U12x37")
        )
        first = schematics[0]
        for schematic in schematics[1:]:
            self.assertEqual(schematic.outline, first.outline)
            self.assertEqual(schematic.segments, first.segments)
            self.assertEqual(schematic.references, first.references)
        xs = [point.x for point in first.outline]
        ys = [point.y for point in first.outline]
        self.assertAlmostEqual(max(xs) - min(xs), 1.30, places=6)
        self.assertAlmostEqual(max(ys) - min(ys), 2.00, places=6)
        points = {reference.id: reference.point for reference in first.references}
        self.assertLess(points["web_back"].x, points["web_center"].x)
        self.assertGreater(points["flange_top_tip"].x, points["web_center"].x)
        self.assertGreater(points["flange_top_tip"].y, 0.0)
        self.assertLess(points["flange_bottom_tip"].y, 0.0)

    def test_i_and_l_schematics_remain_straight_and_unchanged(self):
        expected_counts = {"W150x13": 12, "L50x5": 6}
        for query, expected_count in expected_counts.items():
            schematic = self.schematic(query)
            self.assertEqual(len(schematic.segments), expected_count)
            self.assertTrue(all(
                isinstance(segment, SchematicLine2D)
                for segment in schematic.segments
            ))

    def test_insertion_never_changes_outline_center_or_scale(self):
        for query in ("W150x13", "HP310x132", "I3x8.48", "U6x12.2", "L50x5"):
            schematic = self.schematic(query)
            radius = profile_presentation_radius(schematic.outline, schematic.center)
            for reference in schematic.references:
                with self.subTest(query=query, reference=reference.id):
                    self.assertEqual(schematic.outline, self.schematic(query).outline)
                    self.assertEqual(schematic.center, self.schematic(query).center)
                    self.assertEqual(
                        radius,
                        profile_presentation_radius(
                            self.schematic(query).outline, self.schematic(query).center
                        ),
                    )

    def test_rotation_preserves_scale_and_rotates_outline_and_hotspots_together(self):
        for query, reference_id in (("U6x12.2", "web_back"), ("I3x8.48", "top_right")):
            schematic = self.schematic(query)
            radius = profile_presentation_radius(schematic.outline, schematic.center)
            reference = next(
                item for item in schematic.references if item.id == reference_id
            )
            relative = transform_preview_point(reference.point, schematic.center, 0)
            rotated = transform_preview_point(reference.point, schematic.center, 90)
            self.assertAlmostEqual(rotated.x, -relative.y, places=9)
            self.assertAlmostEqual(rotated.y, relative.x, places=9)
            for angle in (0, 45, 90, -45, 450):
                farthest = max(
                    math.hypot(
                        transform_preview_point(point, schematic.center, angle).x,
                        transform_preview_point(point, schematic.center, angle).y,
                    )
                    for point in schematic.outline
                )
                self.assertAlmostEqual(farthest, radius, places=9)

    def test_selected_hotspot_maps_to_its_own_screen_position_not_viewport_center(self):
        schematic = self.schematic("U6x12.2")
        wanted = next(item for item in schematic.references if item.id == "flange_top_tip")
        x, y = preview_screen_point(wanted.point, schematic.center, 45, 100, 80, 40)
        self.assertNotEqual((x, y), (100, 80))
        found = nearest_reference(
            schematic.references, schematic.center, 45, 100, 80, 40,
            x + 2, y - 1, 10,
        )
        self.assertEqual(found.id, wanted.id)

    def test_ue_new_hotspots_share_rotation_scale_and_hit_testing(self):
        schematic = self.schematic("Ue 150x60x20x3.00")
        radius = profile_presentation_radius(schematic.outline, schematic.center)
        new_ids = (
            "outer_top_mid", "outer_bottom_mid",
            "outer_lip_top_corner", "outer_lip_bottom_corner",
        )
        references = {item.id: item for item in schematic.references}
        self.assertEqual(len(schematic.segments), 20)
        self.assertEqual(len(references), 11)
        for identifier in new_ids:
            reference = references[identifier]
            with self.subTest(identifier=identifier):
                x, y = preview_screen_point(
                    reference.point, schematic.center, 37, 120, 90, 48
                )
                selected = nearest_reference(
                    schematic.references, schematic.center, 37,
                    120, 90, 48, x + 1, y - 1, 9,
                )
                self.assertEqual(selected.id, identifier)
                relative = transform_preview_point(
                    reference.point, schematic.center, 0
                )
                rotated = transform_preview_point(
                    reference.point, schematic.center, 90
                )
                self.assertAlmostEqual(rotated.x, -relative.y)
                self.assertAlmostEqual(rotated.y, relative.x)
                self.assertEqual(
                    profile_presentation_radius(schematic.outline, schematic.center),
                    radius,
                )
        self.assertGreater(references["outer_lip_top_corner"].point.x,
                           references["outer_top_mid"].point.x)
        self.assertAlmostEqual(references["outer_top_mid"].point.y,
                               -references["outer_bottom_mid"].point.y)
        self.assertEqual(references["outer_top_mid"].point,
                         type(schematic.center)(0.06, 0.90))
        self.assertEqual(references["outer_lip_bottom_corner"].point,
                         type(schematic.center)(0.72, -0.90))

    def test_pending_u_never_produces_schematic_or_structural_geometry(self):
        pending = self.library.search("U3x7.44")[0]
        with self.assertRaises(GeometryTemporarilyUnavailableError):
            build_section_geometry(pending)

    def test_widget_paints_schematic_independently_of_member_color(self):
        root = Path(__file__).resolve().parents[1]
        source = (root / "freecad/SteelStructures/interactive/section_orientation_preview.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("schematic_section_for_geometry", source)
        self.assertIn("QtGui.QColor(244, 244, 241)", source)
        self.assertIn("QtGui.QColor(38, 40, 43)", source)
        self.assertNotIn("set_color", source)
        self.assertNotIn("member_color", source)
        for forbidden in ("recompute(", "addObject(", "ActiveDocument"):
            self.assertNotIn(forbidden, source)
        main_contour = source.index("outline_pen = QtGui.QPen(outline_color)")
        available_ring = source.index(
            "painter.drawEllipse(QtCore.QPointF(x, y), normal_radius", main_contour
        )
        self.assertLess(main_contour, available_ring)

    def test_dark_background_enables_thin_halo_but_light_background_does_not(self):
        self.assertTrue(background_needs_dark_outline_halo(0.08, 0.09, 0.10))
        self.assertTrue(background_needs_dark_outline_halo(0.20, 0.20, 0.20))
        self.assertFalse(background_needs_dark_outline_halo(0.75, 0.75, 0.75))
        self.assertFalse(background_needs_dark_outline_halo(0.96, 0.96, 0.96))

    def test_halo_is_conditional_and_painted_before_dark_main_contour(self):
        root = Path(__file__).resolve().parents[1]
        source = (root / "freecad/SteelStructures/interactive/section_orientation_preview.py").read_text(
            encoding="utf-8"
        )
        decision = source.index("background_needs_dark_outline_halo(")
        halo = source.index("halo_pen = QtGui.QPen(fill_color)", decision)
        main = source.index("outline_pen = QtGui.QPen(outline_color)", halo)
        self.assertLess(decision, halo)
        self.assertLess(halo, main)

    def test_available_hover_and_selected_hotspots_use_blue_red_hierarchy(self):
        root = Path(__file__).resolve().parents[1]
        source = (root / "freecad/SteelStructures/interactive/section_orientation_preview.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("HOTSPOT_AVAILABLE_COLOR = (47, 128, 237)", source)
        self.assertIn("HOTSPOT_HOVER_COLOR = (66, 145, 245)", source)
        self.assertIn("HOTSPOT_SELECTED_COLOR = (205, 45, 45)", source)
        self.assertIn("available_color = QtGui.QColor(*HOTSPOT_AVAILABLE_COLOR)", source)
        self.assertNotIn("available_halo_pen", source)
        self.assertIn("point_pen.setWidthF(1.9)", source)
        self.assertNotIn("hover_halo_pen", source)
        self.assertIn("QtGui.QColor(*HOTSPOT_HOVER_COLOR)", source)
        self.assertIn("hover_pen.setWidthF(2.7)", source)
        self.assertIn("selected_color = QtGui.QColor(*HOTSPOT_SELECTED_COLOR)", source)
        self.assertIn("target_pen.setWidthF(2.0)", source)
        self.assertIn("painter.setBrush(QtCore.Qt.NoBrush)", source)
        available_block = source.split("# Available references", 1)[1].split(
            "if self._hovered", 1
        )[0]
        self.assertIn("painter.setBrush(QtCore.Qt.NoBrush)", available_block)
        self.assertNotIn("painter.setBrush(fill_color)", available_block)
        self.assertIn("painter.drawLine(selected_x - arm", source)
        self.assertIn("painter.setBrush(selected_color)", source)
        contour = source.index("outline_pen = QtGui.QPen(outline_color)")
        normal = source.index("point_pen = QtGui.QPen(available_color)", contour)
        hover = source.index("hover_pen = QtGui.QPen", normal)
        selected = source.index("target_pen = QtGui.QPen", hover)
        self.assertLess(contour, normal)
        self.assertLess(normal, hover)
        self.assertLess(hover, selected)

    def test_hit_area_remains_larger_than_every_visible_hotspot_symbol(self):
        root = Path(__file__).resolve().parents[1]
        source = (root / "freecad/SteelStructures/interactive/section_orientation_preview.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("normal_radius = max(self.fontMetrics().lineSpacing() * 0.28, 4.0)", source)
        self.assertIn("hover_radius = max(self.fontMetrics().lineSpacing() * 0.43, 6.3)", source)
        self.assertIn("hit_radius = max(self.fontMetrics().lineSpacing() * 0.65, 9.0)", source)

    def test_hotspot_painting_is_shared_by_every_supported_family(self):
        for query in ("W150x13", "HP310x132", "U6x12.2", "L50x5", "L2x1/4"):
            schematic = self.schematic(query)
            self.assertGreater(len(schematic.references), 1)


if __name__ == "__main__":
    unittest.main()
