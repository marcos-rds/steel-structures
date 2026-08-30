"""Tests for controlled local finite-solid member clipping."""

import math
import types
import unittest

from freecad.SteelStructures.member_plane_cut import (
    bounding_box_corners,
    build_plane_cut,
    finite_clip_plan,
    global_plane_to_member_local,
    is_orthogonal_plane,
    orthonormal_plane_basis,
    plane_point_at_axis_station,
)
from tests.test_member_placement import Placement, Rotation, Vector


class Bounds:
    XMin, XMax, YMin, YMax, ZMin, ZMax = -50.0, 50.0, -100.0, 100.0, 0.0, 1000.0
    XLength, YLength, ZLength = 100.0, 200.0, 1000.0


class SectionFace:
    Area = 1000.0
    BoundBox = Bounds()
    def __init__(self): self.z = 0.0
    def copy(self):
        copied = SectionFace(); copied.z = self.z; return copied
    def translate(self, vector): self.z += vector.z
    def extrude(self, vector): return Prism(self.z, self.z + vector.z)


class Prism:
    def __init__(self, z_min, z_max):
        self.z_min, self.z_max = z_min, z_max
        self.BoundBox = types.SimpleNamespace(
            XMin=-50.0, XMax=50.0, YMin=-100.0, YMax=100.0,
            ZMin=z_min, ZMax=z_max, XLength=100.0, YLength=200.0,
            ZLength=z_max-z_min,
        )
    def common(self, keep_solid): return Clipped(self, keep_solid)


class Clipped:
    def __init__(self, prism, keep_solid):
        self.prism, self.keep_solid = prism, keep_solid
        self.Volume = 1000.0 * 1000.0
        point, normal = keep_solid.face.point, keep_solid.normal
        self.cap_vertices = []
        for x in (-50.0, 50.0):
            for y in (-100.0, 100.0):
                z = point.z - (normal.x * (x - point.x)
                               + normal.y * (y - point.y)) / normal.z
                self.cap_vertices.append(Vector(x, y, z))
    def isNull(self): return False
    def isValid(self): return True


class FakePart:
    calls = []
    @classmethod
    def makePolygon(cls, points):
        cls.calls.append(("makePolygon", len(points)))
        return list(points)
    @classmethod
    def Face(cls, wire): return PlaneFace(wire)


class PlaneFace:
    def __init__(self, wire):
        self.point = Vector(
            sum(value.x for value in wire[:4]) / 4.0,
            sum(value.y for value in wire[:4]) / 4.0,
            sum(value.z for value in wire[:4]) / 4.0,
        )
    def extrude(self, vector): return KeepSolid(self, vector)


class KeepSolid:
    def __init__(self, face, vector):
        self.face = face
        length = vector.Length
        self.normal = Vector(vector.x / length, vector.y / length, vector.z / length)
        self.Volume = 1.0
    def isNull(self): return False
    def isValid(self): return True


class MemberPlaneCutTests(unittest.TestCase):
    def setUp(self): FakePart.calls = []

    def test_orthogonal_fast_path_classification_is_normal_sign_invariant(self):
        self.assertTrue(is_orthogonal_plane((0, 0, 1)))
        self.assertTrue(is_orthogonal_plane((0, 0, -5)))
        self.assertFalse(is_orthogonal_plane((1, 0, 1)))

    def test_global_plane_to_local_identity_translation_rotation_and_combined(self):
        cases = (
            (Placement(), (2, 3, 4), (0, 0, 1), (2, 3, 4), (0, 0, 1)),
            (Placement(Vector(10, -5, 2), Rotation()), (12, -2, 6), (0, 0, 3), (2, 3, 4), (0, 0, 1)),
            (Placement(Vector(), Rotation(Vector(0, 0, 1), 90)), (0, 2, 4), (0, 1, 0), (2, 0, 4), (1, 0, 0)),
            (Placement(Vector(10, -5, 2), Rotation(Vector(0, 0, 1), 90)), (7, -3, 6), (0, 2, 0), (2, 3, 4), (1, 0, 0)),
        )
        for placement, point, normal, expected_point, expected_normal in cases:
            with self.subTest(point=point, normal=normal):
                local_point, local_normal = global_plane_to_member_local(
                    placement, Vector, point, normal
                )
                for actual, expected in zip(local_point, expected_point):
                    self.assertAlmostEqual(actual, expected)
                for actual, expected in zip(local_normal, expected_normal):
                    self.assertAlmostEqual(actual, expected)
                round_trip = placement.multVec(Vector(*local_point))
                for actual, expected in zip((round_trip.x, round_trip.y, round_trip.z), point):
                    self.assertAlmostEqual(actual, expected)

    def test_global_plane_to_local_inverted_normal_only_changes_sign(self):
        placement = Placement(Vector(3, 4, 5), Rotation(Vector(0, 1, 0), 30))
        positive = global_plane_to_member_local(placement, Vector, (7, 8, 9), (1, 2, 3))
        negative = global_plane_to_member_local(placement, Vector, (7, 8, 9), (-1, -2, -3))
        self.assertEqual(positive[0], negative[0])
        for value, inverse in zip(positive[1], negative[1]):
            self.assertAlmostEqual(value, -inverse)

    def test_plane_point_preserves_plane_and_moves_axis_intersection(self):
        point = plane_point_at_axis_station((10, -20, 30), (1, 2, 4), 100)
        normal = (1, 2, 4)
        self.assertAlmostEqual(normal[0] * (0 - point[0]) + normal[1] * (0 - point[1])
                               + normal[2] * (100 - point[2]), 0.0)

    def test_orthonormal_basis_is_unit_and_mutually_perpendicular(self):
        for angle in (15, 30, 31, 45):
            radians = math.radians(angle)
            e1, e2, normal = orthonormal_plane_basis(
                (math.sin(radians), 0, math.cos(radians))
            )
            vectors = (e1, e2, normal)
            for vector in vectors:
                self.assertAlmostEqual(sum(value * value for value in vector), 1.0)
            self.assertAlmostEqual(sum(a * b for a, b in zip(e1, e2)), 0.0)
            self.assertAlmostEqual(sum(a * b for a, b in zip(e1, normal)), 0.0)
            self.assertAlmostEqual(sum(a * b for a, b in zip(e2, normal)), 0.0)

    def test_finite_clip_plan_covers_bbox_and_orients_normal_to_keep_side(self):
        for angle in (15, 30, 31, 45):
            radians = math.radians(angle)
            source_normal = (math.sin(radians), 0, math.cos(radians))
            for normal in (source_normal, tuple(-value for value in source_normal)):
                with self.subTest(angle=angle, normal=normal):
                    plan = finite_clip_plan(Bounds(), (0, 0, 500), normal, (0, 0, 0))
                    self.assertIsNotNone(plan)
                    self.assertGreater(sum((keep - point) * component for keep, point, component
                                           in zip((0, 0, 0), plan.point, plan.normal)), 0.0)
                    for corner in bounding_box_corners(Bounds()):
                        relative = tuple(value - origin for value, origin in zip(corner, plan.point))
                        e1 = sum(value * axis for value, axis in zip(relative, plan.e1))
                        e2 = sum(value * axis for value, axis in zip(relative, plan.e2))
                        along = sum(value * axis for value, axis in zip(relative, plan.normal))
                        self.assertLessEqual(plan.e1_min, e1); self.assertLessEqual(e1, plan.e1_max)
                        self.assertLessEqual(plan.e2_min, e2); self.assertLessEqual(e2, plan.e2_max)
                        self.assertLessEqual(along, plan.depth)

    def test_bbox_has_exactly_eight_unique_corners(self):
        corners = bounding_box_corners(Bounds())
        self.assertEqual(len(corners), 8)
        self.assertEqual(len(set(corners)), 8)

    def test_oblique_angles_build_cap_coplanar_with_requested_plane(self):
        for angle in (15, 30, 45):
            with self.subTest(angle=angle):
                radians = math.radians(angle)
                normal = (math.sin(radians), 0, math.cos(radians))
                result = build_plane_cut(FakePart, Vector, SectionFace(), 1000, 1000, normal, "End")
                self.assertIsNotNone(result)
                for vertex in result.shape.cap_vertices:
                    residual = normal[0] * vertex.x + normal[1] * vertex.y + normal[2] * (vertex.z - 1000)
                    self.assertAlmostEqual(residual, 0.0, places=7)
                self.assertGreaterEqual(result.pre_end, max(vertex.z for vertex in result.shape.cap_vertices))

    def test_start_and_end_margins_derive_from_section_bounds(self):
        normal = (1, 0, 1)
        start = build_plane_cut(FakePart, Vector, SectionFace(), 1000, 0, normal, "Start")
        end = build_plane_cut(FakePart, Vector, SectionFace(), 1000, 1000, normal, "End")
        self.assertEqual(start.pre_end, 1000)
        self.assertEqual(end.pre_start, 0)
        self.assertLess(start.pre_start, -50)
        self.assertGreater(end.pre_end, 1050)
        self.assertGreater(start.shape.keep_solid.normal.z, 0)
        self.assertLess(end.shape.keep_solid.normal.z, 0)

    def test_normal_inversion_selects_same_retained_side(self):
        positive = build_plane_cut(FakePart, Vector, SectionFace(), 1000, 1000, (1, 0, 1), "End")
        negative = build_plane_cut(FakePart, Vector, SectionFace(), 1000, 1000, (-1, 0, -1), "End")
        self.assertEqual((positive.pre_start, positive.pre_end), (negative.pre_start, negative.pre_end))
        self.assertLess(positive.shape.keep_solid.normal.z, 0)
        self.assertLess(negative.shape.keep_solid.normal.z, 0)

    def test_parallel_and_zero_normals_are_invalid(self):
        self.assertIsNone(build_plane_cut(FakePart, Vector, SectionFace(), 1000, 1000, (1, 0, 0), "End"))
        self.assertIsNone(build_plane_cut(FakePart, Vector, SectionFace(), 1000, 1000, (0, 0, 0), "End"))


if __name__ == "__main__":
    unittest.main()
