"""Tests for the FreeCAD-independent StructuralPlate contour contract."""

from __future__ import annotations

import dataclasses
import importlib.util
import json
import math
import sys
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "freecad/SteelStructures/plate_geometry.py"
MODULE_NAME = "_steel_structures_plate_geometry_test"
SPEC = importlib.util.spec_from_file_location(MODULE_NAME, MODULE_PATH)
plate = importlib.util.module_from_spec(SPEC)
sys.modules[MODULE_NAME] = plate
SPEC.loader.exec_module(plate)


class PlateContourTests(unittest.TestCase):
    def test_arbitrary_polygons_and_areas(self):
        examples = (
            ([(0, 0), (4, 0), (0, 3)], 6),
            ([(0, 0), (5, 0), (5, 2), (0, 2)], 10),
            ([(0, 0), (4, 1), (5, 4), (1, 3)], 11),
            ([(0, 0), (4, 0), (5, 2), (2, 4), (-1, 2)], 16),
            ([(0, 0), (4, 0), (4, 4), (2, 2), (0, 4)], 12),
        )
        for points, expected_area in examples:
            with self.subTest(points=points):
                contour = plate.PlateContour2D.from_points(points)
                self.assertEqual(len(contour.vertices), len(points))
                self.assertAlmostEqual(contour.area, expected_area)
                self.assertEqual(contour.orientation, "CCW")
                self.assertEqual(contour.edges[-1][1], contour.vertices[0])

    def test_clockwise_winding_is_preserved(self):
        points = [(0, 0), (4, 0), (0, 3)]
        contour = plate.PlateContour2D.from_points(reversed(points))
        self.assertEqual(contour.orientation, "CW")
        self.assertEqual(contour.signed_area, -6)
        self.assertEqual(contour.area, 6)

    def test_immutable_and_independent_of_input_list(self):
        points = [[0, 0], [2, 0], [0, 2]]
        contour = plate.PlateContour2D.from_points(points)
        points[0][0] = 99
        self.assertEqual(contour.vertices[0], (0.0, 0.0))
        with self.assertRaises(dataclasses.FrozenInstanceError):
            contour.vertices = ()

    def test_repeated_closing_endpoint_normalizes_only_at_import(self):
        points = [(0, 0), (2, 0), (0, 2), (0, 0)]
        self.assertEqual(len(plate.PlateContour2D.from_points(points).vertices), 3)
        with self.assertRaisesRegex(plate.PlateGeometryError, "coincide"):
            plate.PlateContour2D(tuple(points))

    def test_open_source_and_fewer_than_three_vertices_are_rejected(self):
        with self.assertRaisesRegex(plate.PlateGeometryError, "aberto"):
            plate.PlateContour2D.from_points([(0, 0), (1, 0), (0, 1)], closed=False)
        for points in ([], [(0, 0)], [(0, 0), (1, 0)]):
            with self.subTest(points=points), self.assertRaisesRegex(
                plate.PlateGeometryError, "pelo menos três"
            ):
                plate.PlateContour2D.from_points(points)

    def test_duplicate_and_nearly_duplicate_consecutive_vertices_are_rejected(self):
        for points in (
            [(0, 0), (2, 0), (2, 0), (0, 2)],
            [(0, 0), (2, 0), (2 + 1e-8, 0), (0, 2)],
        ):
            with self.subTest(points=points), self.assertRaisesRegex(
                plate.PlateGeometryError, "coincide"
            ):
                plate.PlateContour2D.from_points(points)

    def test_collinear_polygon_and_backtracking_are_rejected(self):
        with self.assertRaisesRegex(plate.PlateGeometryError, "não degenerada"):
            plate.PlateContour2D.from_points([(0, 0), (1, 0), (2, 0)])
        with self.assertRaises(plate.PlateGeometryError):
            plate.PlateContour2D.from_points([(0, 0), (3, 0), (1, 0), (3, 2), (0, 2)])

    def test_intermediate_collinear_vertex_is_allowed(self):
        contour = plate.PlateContour2D.from_points(
            [(0, 0), (1, 0), (2, 0), (2, 2), (0, 2)]
        )
        self.assertEqual(len(contour.vertices), 5)
        self.assertEqual(contour.area, 4)

    def test_self_crossing_and_touching_nonadjacent_edges_are_rejected(self):
        for points in (
            [(0, 0), (4, 4), (0, 4), (4, 0)],
            [(0, 0), (4, 0), (4, 4), (2, 0), (0, 4)],
            [(0, 0), (4, 0), (4, 4), (0, 4), (4, 0)],
        ):
            with self.subTest(points=points), self.assertRaises(plate.PlateGeometryError):
                plate.PlateContour2D.from_points(points)

    def test_invalid_coordinates_are_rejected(self):
        for invalid in (True, "2", math.inf, math.nan):
            with self.subTest(invalid=invalid), self.assertRaises(plate.PlateGeometryError):
                plate.PlateContour2D.from_points([(0, 0), (invalid, 0), (0, 2)])

    def test_serialization_is_deterministic_and_round_trips(self):
        contour = plate.PlateContour2D.from_points([(0, 0), (4, 1), (5, 4), (1, 3)])
        data = contour.to_data()
        self.assertEqual(data, contour.to_data())
        self.assertEqual(plate.PlateContour2D.from_data(data), contour)
        self.assertEqual(plate.parse_contour(plate.serialize_contour(contour)), contour)
        payload = json.loads(data)
        self.assertEqual(payload["version"], 1)
        self.assertEqual(payload["holes"], [])
        self.assertEqual(payload["outer"]["segments"][0]["type"], "line")
        self.assertEqual(len(payload["outer"]["segments"]), 4)

    def test_bad_or_future_contour_data_is_rejected_clearly(self):
        contour = plate.PlateContour2D.from_points([(0, 0), (3, 0), (0, 3)])
        baseline = json.loads(contour.to_data())
        for mutation in (
            lambda data: data.update(version=2),
            lambda data: data.update(holes=[{}]),
            lambda data: data["outer"]["segments"][0].update(type="arc"),
            lambda data: data["outer"]["segments"][0].update(end=[1, 1]),
        ):
            payload = json.loads(json.dumps(baseline))
            mutation(payload)
            with self.subTest(payload=payload), self.assertRaises(plate.PlateGeometryError):
                plate.PlateContour2D.from_data(json.dumps(payload))
        with self.assertRaises(plate.PlateGeometryError):
            plate.PlateContour2D.from_data("{invalid")


if __name__ == "__main__":
    unittest.main()
