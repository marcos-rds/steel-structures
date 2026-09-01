"""Tests for the FreeCAD-independent structural-grid mathematical contract."""

from __future__ import annotations

import ast
import dataclasses
import importlib.util
import math
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "freecad/SteelStructures/grid_geometry.py"


def load_grid_geometry():
    name = "_steel_structures_grid_geometry_test"
    spec = importlib.util.spec_from_file_location(name, MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        sys.modules.pop(name, None)
        raise
    return module


grid = load_grid_geometry()


class ValidationTests(unittest.TestCase):
    def test_imports_without_freecad_modules(self):
        self.assertIsNotNone(grid.GridGeometry)

    def test_accumulated_spacings(self):
        self.assertEqual(
            grid.accumulated_positions([6000.0, 6000.0]),
            (0.0, 6000.0, 12000.0),
        )

    def test_empty_spacings_produce_origin_only(self):
        self.assertEqual(grid.accumulated_positions([]), (0.0,))

    def test_zero_spacing_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "greater than zero"):
            grid.validate_spacings([1, 0], "X")

    def test_negative_spacing_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "X spacing at index 0"):
            grid.validate_spacings([-1], "X")

    def test_nan_spacing_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "finite"):
            grid.validate_spacings([math.nan], "X")

    def test_infinite_spacing_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "finite"):
            grid.validate_spacings([math.inf], "Y")

    def test_boolean_spacing_is_rejected(self):
        with self.assertRaisesRegex(TypeError, "numeric"):
            grid.validate_spacings([True], "X")

    def test_zero_extension_is_accepted(self):
        self.assertEqual(grid.validate_extension(0, "extension"), 0.0)

    def test_negative_extension_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "greater than or equal"):
            grid.validate_extension(-0.1, "extension")

    def test_nonfinite_and_boolean_extensions_are_rejected(self):
        for value, error in ((math.nan, ValueError), (math.inf, ValueError), (True, TypeError)):
            with self.subTest(value=value), self.assertRaises(error):
                grid.validate_extension(value, "extension")

    def test_text_and_object_are_rejected_as_spacings_and_extensions(self):
        for value in ("1000", object()):
            with self.subTest(kind="spacing", value=value), self.assertRaises(TypeError):
                grid.validate_spacings([value], "X")
            with self.subTest(kind="extension", value=value), self.assertRaises(TypeError):
                grid.validate_extension(value, "extension")

    def test_accumulated_positions_reject_cumulative_overflow(self):
        with self.assertRaisesRegex(ValueError, "Accumulated position overflow"):
            grid.accumulated_positions([1e308, 1e308])


class IdentifierTests(unittest.TestCase):
    def test_numeric_identifiers(self):
        self.assertEqual(grid.numeric_axis_identifier(0), "1")
        self.assertEqual(grid.numeric_axis_identifier(1), "2")
        self.assertEqual(grid.numeric_axis_identifier(9), "10")

    def test_alphabetic_identifiers_beyond_z(self):
        expected = {0: "A", 25: "Z", 26: "AA", 27: "AB", 51: "AZ", 52: "BA"}
        self.assertEqual(
            {index: grid.alphabetic_axis_identifier(index) for index in expected},
            expected,
        )


class LabelAnchorTests(unittest.TestCase):
    def geometry(self):
        return grid.build_grid_geometry(
            [6000, 6000], [5000, 5000],
            x_start_extension=1000, x_end_extension=1500,
            y_start_extension=750, y_end_extension=1250,
        )

    def test_start_end_and_both_anchor_exact_axis_extensions(self):
        geometry = self.geometry()
        start = grid.grid_label_anchors(geometry, "Start", 250)
        end = grid.grid_label_anchors(geometry, "End", 250)
        both = grid.grid_label_anchors(geometry, "Both", 250)
        self.assertEqual(len(start), 6)
        self.assertEqual(len(end), 6)
        self.assertEqual({item.side for item in start}, {"bottom", "left"})
        self.assertEqual({item.side for item in end}, {"top", "right"})
        self.assertEqual(len(both), len(start) + len(end))
        x_start = next(item for item in start if item.family == "X")
        x_end = next(item for item in end if item.family == "X")
        y_start = next(item for item in start if item.family == "Y")
        y_end = next(item for item in end if item.family == "Y")
        self.assertEqual(x_start.anchor_point_local[1], -1000.0)
        self.assertEqual(x_end.anchor_point_local[1], 11500.0)
        self.assertEqual(y_start.anchor_point_local[0], -1250.0)
        self.assertEqual(y_end.anchor_point_local[0], 13750.0)

    def test_offset_custom_two_digits_and_letters_are_preserved(self):
        geometry = grid.build_grid_geometry(
            [1000], [2000], x_identifier_scheme="custom",
            y_identifier_scheme="custom", x_identifiers=["10", "25"],
            y_identifiers=["Z", "AA"],
        )
        anchors = grid.grid_label_anchors(geometry, "End", 400)
        self.assertEqual([item.text for item in anchors], ["10", "25", "Z", "AA"])
        self.assertEqual(anchors[0].anchor_point_local, (0.0, 2400.0, 0.0))
        self.assertEqual(anchors[-1].anchor_point_local, (1400.0, 2000.0, 0.0))

    def test_invalid_position_and_offset_are_rejected(self):
        geometry = self.geometry()
        with self.assertRaises(ValueError):
            grid.grid_label_anchors(geometry, "Middle", 250)
        with self.assertRaises(ValueError):
            grid.grid_label_anchors(geometry, "Both", -1)

    def test_invalid_identifier_indices_are_rejected(self):
        for value, error in ((-1, ValueError), (1.5, TypeError), (True, TypeError)):
            with self.subTest(value=value), self.assertRaises(error):
                grid.numeric_axis_identifier(value)

    def test_alphabetic_identifier_directly_rejects_invalid_indices(self):
        for value, error in ((-1, ValueError), (1.5, TypeError), (True, TypeError)):
            with self.subTest(value=value), self.assertRaises(error):
                grid.alphabetic_axis_identifier(value)

    def test_automatic_identifier_schemes_generate_requested_count(self):
        self.assertEqual(
            grid.normalize_identifiers(None, 3, "numeric"), ("1", "2", "3")
        )
        self.assertEqual(
            grid.normalize_identifiers(None, 3, "alphabetic"), ("A", "B", "C")
        )

    def test_valid_custom_identifiers_are_trimmed(self):
        self.assertEqual(
            grid.normalize_identifiers([" A ", "B 2"], 2, "custom"),
            ("A", "B 2"),
        )

    def test_wrong_custom_identifier_count_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "exactly 2"):
            grid.normalize_identifiers(["A"], 2, "custom")

    def test_empty_custom_identifier_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "cannot be empty"):
            grid.normalize_identifiers(["  "], 1, "custom")

    def test_duplicate_custom_identifiers_are_rejected_after_trimming(self):
        with self.assertRaisesRegex(ValueError, "duplicates"):
            grid.normalize_identifiers(["A", " A "], 2, "custom")

    def test_invalid_scheme_and_count_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "Unknown identifier scheme"):
            grid.normalize_identifiers(None, 1, "roman")
        for count, error in ((-1, ValueError), (1.5, TypeError), (True, TypeError)):
            with self.subTest(count=count), self.assertRaises(error):
                grid.normalize_identifiers(None, count, "numeric")


class GeometryTests(unittest.TestCase):
    def build(self):
        return grid.build_grid_geometry(
            [3000, 4000],
            [5000],
            x_start_extension=100,
            x_end_extension=200,
            y_start_extension=300,
            y_end_extension=400,
        )

    def test_x_and_y_spacing_lists_are_independent(self):
        result = self.build()
        self.assertEqual(result.x_positions, (0.0, 3000.0, 7000.0))
        self.assertEqual(result.y_positions, (0.0, 5000.0))

    def test_one_empty_list_produces_one_axis_in_that_family(self):
        result = grid.build_grid_geometry([], [10, 20])
        self.assertEqual(result.x_positions, (0.0,))
        self.assertEqual(len(result.x_axes), 1)
        self.assertEqual(len(result.y_axes), 3)

    def test_both_empty_lists_produce_one_intersection(self):
        result = grid.build_grid_geometry([], [])
        self.assertEqual((len(result.x_axes), len(result.y_axes)), (1, 1))
        self.assertEqual(result.intersections[0].point, (0.0, 0.0, 0.0))

    def test_x_family_axes_have_constant_x_and_run_along_y(self):
        result = self.build()
        self.assertEqual(result.x_axes[1].family, "X")
        self.assertEqual(result.x_axes[1].geometric_direction, "Y")
        self.assertEqual(result.x_axes[1].start, (3000.0, -300.0, 0.0))
        self.assertEqual(result.x_axes[1].end, (3000.0, 5400.0, 0.0))

    def test_y_family_axes_have_constant_y_and_run_along_x(self):
        result = self.build()
        self.assertEqual(result.y_axes[1].family, "Y")
        self.assertEqual(result.y_axes[1].geometric_direction, "X")
        self.assertEqual(result.y_axes[1].start, (-100.0, 5000.0, 0.0))
        self.assertEqual(result.y_axes[1].end, (7200.0, 5000.0, 0.0))

    def test_intersection_count_and_x_major_order(self):
        result = self.build()
        self.assertEqual(len(result.intersections), 6)
        self.assertEqual(
            [(item.x_index, item.y_index, item.point) for item in result.intersections],
            [
                (0, 0, (0.0, 0.0, 0.0)),
                (0, 1, (0.0, 5000.0, 0.0)),
                (1, 0, (3000.0, 0.0, 0.0)),
                (1, 1, (3000.0, 5000.0, 0.0)),
                (2, 0, (7000.0, 0.0, 0.0)),
                (2, 1, (7000.0, 5000.0, 0.0)),
            ],
        )

    def test_all_axis_and_intersection_coordinates_have_zero_z(self):
        result = self.build()
        points = [axis.start for axis in result.x_axes + result.y_axes]
        points += [axis.end for axis in result.x_axes + result.y_axes]
        points += [item.point for item in result.intersections]
        self.assertTrue(all(point[2] == 0.0 for point in points))

    def test_overall_and_displayed_lengths(self):
        result = self.build()
        self.assertEqual((result.overall_length_x, result.overall_length_y), (7000.0, 5000.0))
        self.assertEqual((result.displayed_length_x, result.displayed_length_y), (7300.0, 5700.0))

    def test_custom_family_identifiers_are_applied(self):
        result = grid.build_grid_geometry(
            [10], [], x_identifier_scheme="custom", x_identifiers=["E1", "E2"]
        )
        self.assertEqual(tuple(axis.identifier for axis in result.x_axes), ("E1", "E2"))
        self.assertEqual(result.y_axes[0].identifier, "A")

    def test_input_lists_are_not_modified(self):
        x_spacings = [4, 2]
        y_spacings = [3]
        x_identifiers = [" X1 ", "X2", "X3"]
        originals = (x_spacings.copy(), y_spacings.copy(), x_identifiers.copy())
        grid.build_grid_geometry(
            x_spacings,
            y_spacings,
            x_identifier_scheme="custom",
            x_identifiers=x_identifiers,
        )
        self.assertEqual((x_spacings, y_spacings, x_identifiers), originals)

    def test_results_are_frozen_and_contain_tuples(self):
        result = self.build()
        self.assertTrue(dataclasses.is_dataclass(result))
        with self.assertRaises(dataclasses.FrozenInstanceError):
            result.overall_length_x = 1
        with self.assertRaises(dataclasses.FrozenInstanceError):
            result.x_axes[0].identifier = "changed"
        self.assertIsInstance(result.intersections, tuple)
        self.assertIsInstance(result.x_axes[0].start, tuple)

    def test_displayed_length_overflow_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Displayed X length overflow"):
            grid.build_grid_geometry([1e308], [], x_end_extension=1e308)
        with self.assertRaisesRegex(ValueError, "Displayed Y length overflow"):
            grid.build_grid_geometry([], [1e308], y_start_extension=1e308)


class NearestIntersectionTests(unittest.TestCase):
    def setUp(self):
        self.intersections = grid.build_grid_geometry([10], [10]).intersections

    def test_returns_nearest_point_inside_tolerance(self):
        found = grid.nearest_intersection((9.8, 10.1, 0), self.intersections, 0.25)
        self.assertEqual((found.x_index, found.y_index), (1, 1))

    def test_returns_none_outside_tolerance(self):
        self.assertIsNone(grid.nearest_intersection((5, 5, 0), self.intersections, 1))

    def test_tie_preserves_first_input_intersection(self):
        first = grid.GridIntersection(4, 1, (-1.0, 0.0, 0.0))
        second = grid.GridIntersection(9, 2, (1.0, 0.0, 0.0))
        found = grid.nearest_intersection((0, 0, 0), [first, second], 1)
        self.assertIs(found, first)

    def test_large_finite_coordinates_do_not_overflow_distance_calculation(self):
        distant = grid.GridIntersection(0, 0, (-1e308, 0.0, 0.0))
        nearest = grid.GridIntersection(1, 0, (1e308, 0.0, 0.0))
        found = grid.nearest_intersection(
            (5e307, 0.0, 0.0), [distant, nearest], 6e307
        )
        self.assertIs(found, nearest)

    def test_invalid_tolerance_is_rejected(self):
        for value, error in ((-1, ValueError), (math.nan, ValueError), (True, TypeError)):
            with self.subTest(value=value), self.assertRaises(error):
                grid.nearest_intersection((0, 0, 0), self.intersections, value)


class DependencyTests(unittest.TestCase):
    def test_module_has_no_forbidden_imports(self):
        forbidden = {
            "FreeCAD", "FreeCADGui", "Part", "Draft", "PySide", "PySide2",
            "PySide6", "pivy", "Coin3D",
        }
        tree = ast.parse(MODULE_PATH.read_text(encoding="utf-8"))
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".", 1)[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".", 1)[0])
        self.assertFalse(imported.intersection(forbidden))


if __name__ == "__main__":
    unittest.main()
