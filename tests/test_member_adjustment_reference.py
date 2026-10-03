"""Tests for planar LinkSub references and dependency-cycle validation."""

import math
import types
import unittest

from freecad.SteelStructures.member_adjustment_reference import (
    linear_reference_from_link,
    plane_reference_from_link,
    unpack_link_sub,
    would_create_adjustment_cycle,
)
from tests.test_member_placement import Placement, Rotation, Vector


class Surface:
    def __init__(self, planar=True): self.TypeId = "Part::GeomPlane" if planar else "Part::GeomCylinder"
    def isDerivedFrom(self, type_id): return self.TypeId == type_id


class Face:
    ShapeType = "Face"
    ParameterRange = (0.0, 2.0, 0.0, 2.0)
    def __init__(self, point, normal, planar=True, valid=True):
        self.point, self.normal, self.Surface = Vector(point), Vector(normal), Surface(planar)
        self.valid = valid
    def isNull(self): return False
    def isValid(self): return self.valid
    def valueAt(self, _u, _v): return Vector(self.point)
    def normalAt(self, _u, _v): return Vector(self.normal)


class Shape:
    def __init__(self, present=True, valid=True): self.present, self.valid = present, valid
    def isNull(self): return not self.present
    def isValid(self): return self.valid


class Reference:
    def __init__(self, point=(0, 0, 0), normal=(1, 0, 0), placement=None,
                 planar=True, missing=False, shape=True, shape_valid=True, face_valid=True):
        self.local_face = Face(point, normal, planar)
        self.Placement = placement or Placement()
        self.Shape = Shape(shape, shape_valid)
        self.face_valid = face_valid
        self.missing = missing
        self.calls = []
        self.OutList = []
    def getSubObject(self, name):
        self.calls.append(name)
        if self.missing or name != "Face3": return None
        face = self.local_face
        return Face(self.Placement.multVec(face.point),
                    mat_vector(self.Placement.Rotation.matrix, face.normal),
                    face.Surface.TypeId == "Part::GeomPlane", self.face_valid)


class Curve:
    def __init__(self, linear=True): self.TypeId = "Part::GeomLine" if linear else "Part::GeomCircle"
    def isDerivedFrom(self, type_id): return self.TypeId == type_id


class Edge:
    ShapeType = "Edge"
    FirstParameter = 0.0
    LastParameter = 1.0
    def __init__(self, start, end, linear=True, valid=True):
        self.start, self.end, self.Curve, self.valid = Vector(start), Vector(end), Curve(linear), valid
    def isNull(self): return False
    def isValid(self): return self.valid
    def valueAt(self, parameter): return Vector(self.start if parameter == self.FirstParameter else self.end)


class EdgeReference:
    def __init__(self, start, end, placement=None, linear=True, valid=True):
        self.edge = Edge(start, end, linear, valid); self.Shape = Shape(); self.Placement = placement or Placement()
        self.calls = []; self.OutList = []
    def getSubObject(self, name):
        self.calls.append(name)
        if name != "Edge3": return None
        return Edge(self.Placement.multVec(self.edge.start), self.Placement.multVec(self.edge.end),
                    self.edge.Curve.TypeId == "Part::GeomLine", self.edge.valid)


def mat_vector(matrix, vector):
    values = (vector.x, vector.y, vector.z)
    return Vector(*(sum(matrix[row][column] * values[column] for column in range(3))
                    for row in range(3)))


class MemberAdjustmentReferenceTests(unittest.TestCase):
    def assertPoint(self, actual, expected, places=7):
        for value, wanted in zip(actual, expected): self.assertAlmostEqual(value, wanted, places=places)

    def test_unpack_requires_one_explicit_face(self):
        reference = object()
        for value in ((reference, "Face3"), (reference, ["Face3"]), (reference, ("Face3",))):
            self.assertEqual(unpack_link_sub(value), (reference, "Face3"))
        for value in (None, (None, []), (reference, []), (reference, ["Face1", "Face2"]),
                      (reference, ["Vertex1"]), (reference, ["Face0"]), (reference, ["Edge0"])):
            self.assertIsNone(unpack_link_sub(value))
        self.assertEqual(unpack_link_sub((reference, ["Edge1"])), (reference, "Edge1"))

    def test_identity_translation_rotation_and_combined_global_plane(self):
        cases = [
            (Placement(), (1, 0, 0), (1, 0, 0)),
            (Placement(Vector(10, 20, 30), Rotation()), (11, 20, 30), (1, 0, 0)),
            (Placement(Vector(), Rotation(Vector(0, 0, 1), 90)), (0, 1, 0), (0, 1, 0)),
            (Placement(Vector(10, 20, 30), Rotation(Vector(0, 0, 1), 90)), (10, 21, 30), (0, 1, 0)),
        ]
        for placement, point, normal in cases:
            with self.subTest(point=point):
                reference = Reference(point=(1, 0, 0), normal=(1, 0, 0), placement=placement)
                plane = plane_reference_from_link((reference, ["Face3"]))
                self.assertPoint(plane.point_global, point); self.assertPoint(plane.normal_global, normal)
                self.assertEqual(reference.calls, ["Face3"])

    def test_inverted_normal_describes_same_plane(self):
        positive = plane_reference_from_link((Reference(normal=(1, 0, 0)), ["Face3"]))
        negative = plane_reference_from_link((Reference(normal=(-1, 0, 0)), ["Face3"]))
        self.assertPoint(positive.point_global, negative.point_global)
        self.assertPoint(positive.normal_global, tuple(-value for value in negative.normal_global))

    def test_invalid_face_states_are_safe(self):
        cases = [None, (Reference(shape=False), ["Face3"]), (Reference(missing=True), ["Face3"]),
                 (Reference(shape_valid=False), ["Face3"]), (Reference(face_valid=False), ["Face3"]),
                 (Reference(planar=False), ["Face3"]), (Reference(), ["Face99"])]
        for value in cases:
            with self.subTest(value=value): self.assertIsNone(plane_reference_from_link(value))
        wrong_type = Reference(); wrong_type.getSubObject = lambda _name: types.SimpleNamespace(ShapeType="Edge")
        self.assertIsNone(plane_reference_from_link((wrong_type, ["Face3"])))

    def test_linear_edge_resolution_uses_infinite_global_support_line(self):
        reference = EdgeReference((0, 0, 0), (0, 2, 0),
                                  Placement(Vector(10, 20, 30), Rotation(Vector(1, 0, 0), 90)))
        line = linear_reference_from_link((reference, ["Edge3"]))
        self.assertPoint(line.point_global, (10, 20, 30)); self.assertPoint(line.direction_global, (0, 0, 1))
        self.assertEqual(reference.calls, ["Edge3"])

    def test_curved_degenerate_invalid_and_wrong_subelement_edges_are_rejected(self):
        for reference in (EdgeReference((0, 0, 0), (0, 2, 0), linear=False),
                          EdgeReference((1, 1, 1), (1, 1, 1)),
                          EdgeReference((0, 0, 0), (0, 2, 0), valid=False)):
            self.assertIsNone(linear_reference_from_link((reference, ["Edge3"])))
        self.assertIsNone(linear_reference_from_link((EdgeReference((0, 0, 0), (0, 2, 0)), ["Face3"])))

    def test_cycle_detection_self_direct_indirect_and_legitimate_chain(self):
        a, b, c, d = (Reference() for _ in range(4))
        self.assertTrue(would_create_adjustment_cycle(a, a))
        b.OutList = [a]
        self.assertTrue(would_create_adjustment_cycle(a, b))
        b.OutList = [c]; c.OutList = [a]
        self.assertTrue(would_create_adjustment_cycle(a, b))
        c.OutList = [d]
        self.assertFalse(would_create_adjustment_cycle(a, b))


if __name__ == "__main__":
    unittest.main()
