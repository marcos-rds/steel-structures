"""Tests for the pure structural-member adjustment geometry."""

import math
import unittest

from freecad.SteelStructures.member_adjustment_geometry import (
    apply_gap,
    axis_geometry,
    fixed_reference_point,
    intersect_infinite_axis_with_plane,
    nominal_length,
    closest_point_on_member_axis,
    plane_axial_span,
    physical_extents,
)


class MemberAdjustmentGeometryTests(unittest.TestCase):
    def assertPoint(self, actual, expected, places=7):
        for value, wanted in zip(actual, expected):
            self.assertAlmostEqual(value, wanted, places=places)

    def test_axes_and_nominal_lengths_in_x_y_z_and_inclined_3d(self):
        cases = [
            ((0, 0, 0), (10, 0, 0), (1, 0, 0), 10),
            ((1, 2, 3), (1, 7, 3), (0, 1, 0), 5),
            ((1, 2, 3), (1, 2, -1), (0, 0, -1), 4),
            ((1, 2, 3), (3, 5, 9), (2/7, 3/7, 6/7), 7),
        ]
        for start, end, direction, length in cases:
            with self.subTest(start=start, end=end):
                axis = axis_geometry(start, end)
                self.assertPoint(axis.direction, direction)
                self.assertAlmostEqual(axis.length, length)
                self.assertAlmostEqual(nominal_length(start, end), length)

    def test_infinite_axis_plane_intersections_before_inside_and_after(self):
        for x in (-5, 4, 15):
            with self.subTest(x=x):
                point = intersect_infinite_axis_with_plane((0, 0, 0), (10, 0, 0), (x, 8, 9), (1, 0, 0))
                self.assertPoint(point, (x, 0, 0))

    def test_plane_normal_orientation_and_scale_do_not_change_intersection(self):
        expected = (4, 4, 4)
        for normal in ((1, 1, 1), (-1, -1, -1), (1e-9, 1e-9, 1e-9), (1e9, 1e9, 1e9)):
            with self.subTest(normal=normal):
                result = intersect_infinite_axis_with_plane((0, 0, 0), (8, 8, 8), expected, normal)
                self.assertPoint(result, expected)

    def test_parallel_zero_normal_and_null_axis_are_invalid(self):
        self.assertIsNone(intersect_infinite_axis_with_plane((0, 0, 0), (10, 0, 0), (0, 2, 0), (0, 1, 0)))
        self.assertIsNone(intersect_infinite_axis_with_plane((0, 0, 0), (10, 0, 0), (2, 0, 0), (0, 0, 0)))
        self.assertIsNone(intersect_infinite_axis_with_plane((1, 1, 1), (1, 1, 1), (2, 0, 0), (1, 0, 0)))

    def test_gap_sign_for_start_and_end(self):
        direction = (1, 0, 0)
        for adjusted_end, gap, expected in (
            ("Start", 0, (5, 0, 0)), ("Start", 2, (7, 0, 0)), ("Start", -2, (3, 0, 0)),
            ("End", 0, (5, 0, 0)), ("End", 2, (3, 0, 0)), ("End", -2, (7, 0, 0)),
        ):
            self.assertPoint(apply_gap((5, 0, 0), direction, adjusted_end, gap), expected)
        with self.assertRaises(ValueError):
            apply_gap((0, 0, 0), direction, "Auto", 0)

    def test_fixed_reference_selection_accepts_signed_offsets(self):
        self.assertPoint(fixed_reference_point((0, 0, 0), (10, 0, 0), "Start", -2), (-2, 0, 0))
        self.assertPoint(fixed_reference_point((0, 0, 0), (10, 0, 0), "End", -2), (12, 0, 0))

    def test_none_includes_both_extensions_and_associative_is_defensive(self):
        for mode in ("None", "Associative"):
            result = physical_extents((0, 0, 0), (10, 0, 0), mode=mode, start_extension=2, end_extension=3)
            self.assertTrue(result.valid)
            self.assertPoint(result.start, (-2, 0, 0)); self.assertPoint(result.end, (13, 0, 0))
            self.assertEqual(result.length, 15)

    def test_fixed_start_ignores_start_extension_and_keeps_end_extension(self):
        result = physical_extents((0, 0, 0), (10, 0, 0), mode="Fixed", adjusted_end="Start",
                                  reference_offset=2, gap=1, start_extension=8, end_extension=4)
        self.assertPoint(result.start, (3, 0, 0)); self.assertPoint(result.end, (14, 0, 0))
        self.assertEqual(result.length, 11)

    def test_fixed_end_ignores_end_extension_and_keeps_start_extension(self):
        result = physical_extents((0, 0, 0), (10, 0, 0), mode="Fixed", adjusted_end="End",
                                  reference_offset=2, gap=1, start_extension=4, end_extension=8)
        self.assertPoint(result.start, (-4, 0, 0)); self.assertPoint(result.end, (7, 0, 0))
        self.assertEqual(result.length, 11)

    def test_reference_offset_and_gap_remain_independent(self):
        first = physical_extents((0, 0, 0), (3000, 0, 0), mode="Fixed", adjusted_end="End",
                                 reference_offset=100, gap=20)
        second = physical_extents((0, 0, 0), (3000, 0, 0), mode="Fixed", adjusted_end="End",
                                  reference_offset=100, gap=30)
        self.assertPoint(first.end, (2880, 0, 0)); self.assertPoint(second.end, (2870, 0, 0))

    def test_associative_reference_point_uses_same_start_end_gap_contract(self):
        for adjusted_end, gap, expected_start, expected_end in (
            ("Start", 20, (220, 0, 0), (3050, 0, 0)),
            ("Start", -20, (180, 0, 0), (3050, 0, 0)),
            ("End", 20, (-50, 0, 0), (2780, 0, 0)),
            ("End", -20, (-50, 0, 0), (2820, 0, 0)),
        ):
            result = physical_extents(
                (0, 0, 0), (3000, 0, 0), mode="Associative", adjusted_end=adjusted_end,
                reference_point=(200 if adjusted_end == "Start" else 2800, 0, 0), gap=gap,
                start_extension=50, end_extension=50,
            )
            self.assertPoint(result.start, expected_start); self.assertPoint(result.end, expected_end)

    def test_zero_inverted_and_tolerance_lengths_are_invalid(self):
        self.assertFalse(physical_extents((0, 0, 0), (0, 0, 0)).valid)
        for offset in (10, 11, 10 - 5e-8):
            with self.subTest(offset=offset):
                result = physical_extents((0, 0, 0), (10, 0, 0), mode="Fixed",
                                          adjusted_end="Start", reference_offset=offset)
                self.assertFalse(result.valid); self.assertEqual(result.length, 0)

    def test_closest_point_between_infinite_axis_and_reference_lines(self):
        cases = [
            ((5, -2, 0), (0, 1, 0), (5, 0, 0)),
            ((5, -2, 7), (0, 1, 0), (5, 0, 0)),
            ((5, -2, 7), (0, 1, 1), (5, 0, 0)),
            ((5, 2, 0), (0, -1, 0), (5, 0, 0)),
        ]
        for point, direction, expected in cases:
            with self.subTest(point=point, direction=direction):
                result = closest_point_on_member_axis((0, 0, 0), (10, 0, 0), point, direction)
                self.assertPoint(result, expected)

    def test_parallel_near_parallel_and_degenerate_reference_lines_are_invalid(self):
        self.assertIsNone(closest_point_on_member_axis((0, 0, 0), (10, 0, 0), (2, 3, 0), (1, 0, 0)))
        self.assertIsNone(closest_point_on_member_axis((0, 0, 0), (10, 0, 0), (2, 3, 0), (1, 1e-9, 0)))
        self.assertIsNone(closest_point_on_member_axis((0, 0, 0), (10, 0, 0), (2, 3, 0), (0, 0, 0)))

    def test_plane_axial_span_uses_section_bounds_and_rejects_parallel(self):
        span = plane_axial_span(100, (1, 0, 1), (-10, 20), (-5, 5))
        self.assertPoint((span[0], span[1], 0), (80, 110, 0))
        self.assertIsNone(plane_axial_span(100, (1, 0, 0), (-10, 20), (-5, 5)))


if __name__ == "__main__":
    unittest.main()
