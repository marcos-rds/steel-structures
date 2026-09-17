"""Insertion-reference contracts for typology-specific section geometry."""

import unittest

from freecad.SteelStructures.paths import CATALOGS_DIR
from freecad.SteelStructures.profiles import (
    ProfileLibrary, build_section_geometry, insertion_translation,
    section_insertion_references,
)


class SectionInsertionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.library = ProfileLibrary(CATALOGS_DIR)

    def geometry(self, designation):
        return build_section_geometry(self.library.search(designation)[0])

    def test_equal_angle_references_use_real_centroidal_points(self):
        expected_ids = (
            "centroid", "envelope_center", "outer_corner", "top_tip", "right_tip", "inner_corner",
        )
        expected_labels = (
            "Centroide", "Centro do envelope", "Quina externa", "Ponta superior", "Ponta direita", "Quina interna",
        )
        for designation in ("L40x3", "L100x9", "L1/2x1/8", "L2x1/4", "L6x1/2", "L8x3/4"):
            geometry = self.geometry(designation)
            references = section_insertion_references(geometry)
            points = {item.id: item.point for item in references}
            inner = geometry.outer_path.segments[3].start
            with self.subTest(designation=designation):
                self.assertEqual(tuple(item.id for item in references), expected_ids)
                self.assertEqual(tuple(item.label for item in references), expected_labels)
                self.assertEqual((points["centroid"].x, points["centroid"].y), (0.0, 0.0))
                self.assertEqual((points["outer_corner"].x, points["outer_corner"].y),
                                 (geometry.bounds.min_x, geometry.bounds.min_y))
                self.assertEqual((points["top_tip"].x, points["top_tip"].y),
                                 (geometry.bounds.min_x, geometry.bounds.max_y))
                self.assertEqual((points["right_tip"].x, points["right_tip"].y),
                                 (geometry.bounds.max_x, geometry.bounds.min_y))
                self.assertEqual(points["inner_corner"], inner)
                center = points["envelope_center"]
                self.assertNotEqual(center, points["centroid"])
                self.assertAlmostEqual(center.x, (geometry.bounds.min_x+geometry.bounds.max_x)/2.)
                self.assertAlmostEqual(center.y, (geometry.bounds.min_y+geometry.bounds.max_y)/2.)

    def test_every_reference_translation_places_its_point_on_axis(self):
        for designation in ("L40x3", "L100x9"):
            geometry = self.geometry(designation)
            for reference in section_insertion_references(geometry):
                tx, ty = insertion_translation(geometry, reference.id)
                with self.subTest(designation=designation, insertion=reference.id):
                    self.assertAlmostEqual(reference.point.x + tx, 0.0)
                    self.assertAlmostEqual(reference.point.y + ty, 0.0)

    def test_w_hp_labels_and_offsets_remain_unchanged(self):
        geometry = self.geometry("W310x52")
        references = section_insertion_references(geometry)
        self.assertEqual(tuple(item.label for item in references), (
            "Centroide", "Face esquerda", "Face direita", "Face superior", "Face inferior",
            "Canto superior esquerdo", "Canto superior direito",
            "Canto inferior esquerdo", "Canto inferior direito",
        ))
        self.assertEqual(insertion_translation(geometry, "Face superior"),
                         (0.0, -geometry.bounds.max_y))

    def test_tapered_i_reuses_the_nine_symmetric_i_references(self):
        for designation in ('I3x8.48', 'I6x22.00'):
            geometry = self.geometry(designation)
            references = section_insertion_references(geometry)
            points = {item.id: item.point for item in references}
            with self.subTest(designation=designation):
                self.assertEqual(tuple(item.id for item in references), (
                    "centroid", "left", "right", "top", "bottom",
                    "top_left", "top_right", "bottom_left", "bottom_right",
                ))
                self.assertEqual(points["centroid"], geometry.origin)
                self.assertEqual(points["left"], type(geometry.origin)(geometry.bounds.min_x, 0.0))
                self.assertEqual(points["top_right"], type(geometry.origin)(
                    geometry.bounds.max_x, geometry.bounds.max_y,
                ))
                for reference in references:
                    tx, ty = insertion_translation(geometry, reference.id)
                    self.assertAlmostEqual(reference.point.x + tx, 0.0)
                    self.assertAlmostEqual(reference.point.y + ty, 0.0)

    def test_standard_tee_exposes_exactly_five_real_references(self):
        for designation in ('T5/8x1/8', 'T2x1/4'):
            geometry = self.geometry(designation)
            references = section_insertion_references(geometry)
            points = {item.id: item.point for item in references}
            with self.subTest(designation=designation):
                self.assertEqual(tuple(item.id for item in references), (
                    "centroid", "top", "bottom", "top_left", "top_right",
                ))
                self.assertEqual(tuple(item.label for item in references), (
                    "Centroide", "Face superior", "Ponta inferior da alma",
                    "Canto superior esquerdo", "Canto superior direito",
                ))
                self.assertEqual(points["centroid"], geometry.origin)
                self.assertEqual((points["top"].x, points["top"].y),
                                 (0.0, geometry.bounds.max_y))
                self.assertEqual((points["bottom"].x, points["bottom"].y),
                                 (0.0, geometry.bounds.min_y))
                self.assertEqual(points["top_left"], type(geometry.origin)(
                    geometry.bounds.min_x, geometry.bounds.max_y,
                ))
                self.assertEqual(points["top_right"], type(geometry.origin)(
                    geometry.bounds.max_x, geometry.bounds.max_y,
                ))

    def test_u_semantic_references_follow_real_contour_for_small_and_large_profiles(self):
        expected = (
            ("centroid", "Centroide"),
            ("web_center", "Centro da alma"),
            ("web_back", "Face externa da alma"),
            ("rear_top", "Canto superior traseiro"),
            ("rear_bottom", "Canto inferior traseiro"),
            ("flange_top_tip", "Ponta superior da mesa"),
            ("flange_bottom_tip", "Ponta inferior da mesa"),
        )
        for designation, tw in (("U3x6.10", 4.32), ("U12x37.00", 9.8)):
            geometry = self.geometry(designation)
            references = section_insertion_references(geometry)
            points = {item.id: item.point for item in references}
            rear_bottom = geometry.outer_path.segments[0].start
            lower_tip = geometry.outer_path.segments[0].end
            upper_tip = geometry.outer_path.segments[10].start
            rear_top = geometry.outer_path.segments[10].end
            with self.subTest(designation=designation):
                self.assertEqual(tuple((item.id, item.label) for item in references), expected)
                self.assertEqual(points["centroid"], geometry.origin)
                self.assertAlmostEqual(points["web_center"].x, rear_bottom.x + tw / 2.0)
                self.assertEqual(points["web_center"].y, 0.0)
                self.assertEqual(points["web_back"], type(rear_bottom)(rear_bottom.x, 0.0))
                self.assertEqual(points["rear_top"], rear_top)
                self.assertEqual(points["rear_bottom"], rear_bottom)
                self.assertEqual(points["flange_top_tip"], upper_tip)
                self.assertEqual(points["flange_bottom_tip"], lower_tip)
                self.assertAlmostEqual(points["rear_top"].y, -points["rear_bottom"].y)
                self.assertAlmostEqual(points["flange_top_tip"].y,
                                       -points["flange_bottom_tip"].y)
                for reference in references:
                    tx, ty = insertion_translation(geometry, reference.label)
                    self.assertAlmostEqual(reference.point.x + tx, 0.0)
                    self.assertAlmostEqual(reference.point.y + ty, 0.0)

    def test_ue_outer_references_use_nominal_faces_and_tangent_midpoint(self):
        expected_new = (
            ("outer_top_mid", "Centro externo superior"),
            ("outer_bottom_mid", "Centro externo inferior"),
            ("outer_lip_top_corner", "Canto externo do enrijecedor superior"),
            ("outer_lip_bottom_corner", "Canto externo do enrijecedor inferior"),
        )
        for designation in (
                "Ue 50x25x10x1.20",
                "Ue 150x60x20x3.00",
                "Ue 300x85x25x2.25"):
            geometry = self.geometry(designation)
            stations = dict(geometry.dimension_stations)
            references = section_insertion_references(geometry)
            points = {item.id: item.point for item in references}
            outer_flange_mid_x = (
                stations["flange_web_tangent_x"]
                + stations["flange_lip_tangent_x"]
            ) / 2.0
            top_straight = next(
                segment for segment in geometry.outer_path.segments
                if segment.start.y == segment.end.y == stations["nominal_top_y"]
                and {segment.start.x, segment.end.x} == {
                    stations["flange_web_tangent_x"],
                    stations["flange_lip_tangent_x"],
                }
            )
            bottom_straight = next(
                segment for segment in geometry.outer_path.segments
                if segment.start.y == segment.end.y == stations["nominal_bottom_y"]
                and {segment.start.x, segment.end.x} == {
                    stations["flange_web_tangent_x"],
                    stations["flange_lip_tangent_x"],
                }
            )
            with self.subTest(designation=designation):
                self.assertEqual(
                    tuple((item.id, item.label) for item in references[-4:]),
                    expected_new,
                )
                self.assertEqual(
                    points["outer_top_mid"],
                    type(geometry.origin)(
                        outer_flange_mid_x, stations["nominal_top_y"]
                    ),
                )
                self.assertEqual(
                    points["outer_bottom_mid"],
                    type(geometry.origin)(
                        outer_flange_mid_x, stations["nominal_bottom_y"]
                    ),
                )
                self.assertEqual(
                    points["outer_lip_top_corner"],
                    type(geometry.origin)(
                        stations["nominal_flange_tip_x"],
                        stations["nominal_top_y"],
                    ),
                )
                self.assertEqual(
                    points["outer_lip_bottom_corner"],
                    type(geometry.origin)(
                        stations["nominal_flange_tip_x"],
                        stations["nominal_bottom_y"],
                    ),
                )
                self.assertEqual(points["outer_top_mid"].x,
                                 points["outer_bottom_mid"].x)
                self.assertLess(stations["flange_web_tangent_x"],
                                points["outer_top_mid"].x)
                self.assertLess(points["outer_top_mid"].x,
                                stations["flange_lip_tangent_x"])
                self.assertEqual(
                    points["outer_top_mid"].x,
                    (top_straight.start.x + top_straight.end.x) / 2.0,
                )
                self.assertEqual(
                    points["outer_bottom_mid"].x,
                    (bottom_straight.start.x + bottom_straight.end.x) / 2.0,
                )
                self.assertEqual(points["outer_lip_top_corner"].x,
                                 points["outer_lip_bottom_corner"].x)
                self.assertEqual(points["rear_top"].y,
                                 points["outer_lip_top_corner"].y)
                self.assertEqual(points["rear_bottom"].y,
                                 points["outer_lip_bottom_corner"].y)
                self.assertEqual(points["rear_top"].x,
                                 stations["external_web_x"])
                for identifier, label in expected_new:
                    for value in (identifier, label):
                        tx, ty = insertion_translation(geometry, value)
                        self.assertAlmostEqual(points[identifier].x + tx, 0.0)
                        self.assertAlmostEqual(points[identifier].y + ty, 0.0)

    def test_ue_rejected_mean_line_extension_ids_are_absent(self):
        geometry = self.geometry("Ue 150x60x20x3.00")
        references = section_insertion_references(geometry)
        identifiers = {item.id for item in references}
        labels = {item.label for item in references}
        self.assertEqual(len(references), 11)
        self.assertTrue({
            "flange_top_mid", "flange_bottom_mid", "lip_top_root", "lip_bottom_root",
        }.isdisjoint(identifiers))
        self.assertTrue({
            "Meio da mesa superior", "Meio da mesa inferior",
            "Raiz do enrijecedor superior", "Raiz do enrijecedor inferior",
        }.isdisjoint(labels))


if __name__ == "__main__":
    unittest.main()
