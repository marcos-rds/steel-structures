"""Pure contracts for resolving one Draft Line as a nominal member axis."""

import math
import types
import unittest

from freecad.SteelStructures.member_axis_source import (
    axis_source_from_selection,
    resolve_axis_source,
)


class Vector:
    def __init__(self, x=0, y=0, z=0):
        self.x, self.y, self.z = float(x), float(y), float(z)

    def sub(self, other):
        return Vector(self.x-other.x, self.y-other.y, self.z-other.z)

    @property
    def Length(self):
        return math.sqrt(self.x*self.x + self.y*self.y + self.z*self.z)


class Placement:
    def __init__(self, offset):
        self.offset = Vector(offset.x, offset.y, offset.z)

    def inverse(self):
        return Placement(Vector(-self.offset.x, -self.offset.y, -self.offset.z))

    def multiply(self, other):
        return Placement(Vector(self.offset.x + other.offset.x,
                                self.offset.y + other.offset.y,
                                self.offset.z + other.offset.z))

    def multVec(self, point):
        return Vector(point.x+self.offset.x, point.y+self.offset.y, point.z+self.offset.z)


class Wire:
    __module__ = "draftobjects.wire"


class Curve:
    def isDerivedFrom(self, type_id):
        return type_id == "Part::GeomLine"


class Edge:
    ShapeType = "Edge"
    Curve = Curve()
    Vertexes = (object(), object())

    def isNull(self): return False
    def isValid(self): return True


class Shape:
    Edges = (Edge(),)

    def isNull(self): return False
    def isValid(self): return True


class InvalidShape(Shape):
    def isNull(self): return True
    def isValid(self): return False


class DraftLine:
    TypeId = "Part::FeaturePython"
    Proxy = Wire()
    PropertiesList = ["Start", "End", "Shape"]
    Shape = Shape()
    Closed = False

    def __init__(self, start, end, parent_offset=Vector()):
        self.Start, self.End = start, end
        self.Placement = Placement(Vector())
        self._global = Placement(parent_offset)

    def getGlobalPlacement(self): return self._global
    def getSubObject(self, name): return Edge() if name == "Edge1" else None


def xyz(value):
    return value.x, value.y, value.z


class MemberAxisSourceTests(unittest.TestCase):
    def test_preserves_a_to_b_and_b_to_a_direction(self):
        for start, end in ((Vector(1,2,3), Vector(4,5,6)),
                           (Vector(4,5,6), Vector(1,2,3))):
            result = resolve_axis_source((DraftLine(start, end), ["Edge1"]))
            self.assertEqual(xyz(result.start), xyz(start))
            self.assertEqual(xyz(result.end), xyz(end))

    def test_applies_parent_placement_once(self):
        line = DraftLine(Vector(1,2,3), Vector(11,22,33), Vector(100,200,300))
        result = resolve_axis_source((line, ["Edge1"]))
        self.assertEqual(xyz(result.start), (101,202,303))
        self.assertEqual(xyz(result.end), (111,222,333))

    def test_degenerate_missing_and_wrong_subobject_are_rejected(self):
        point = Vector(1,2,3)
        self.assertIsNone(resolve_axis_source((DraftLine(point, point), ["Edge1"])))
        self.assertIsNone(resolve_axis_source(None))
        self.assertIsNone(resolve_axis_source((DraftLine(point, Vector(2,3,4)), ["Edge2"])))

    def test_semantic_endpoints_recover_even_while_draft_shape_is_invalid(self):
        line = DraftLine(Vector(1,2,3), Vector(4,5,6))
        line.Shape = InvalidShape()
        result = resolve_axis_source((line, ["Edge1"]))
        self.assertEqual(xyz(result.start), (1,2,3))
        self.assertEqual(xyz(result.end), (4,5,6))

    def test_draft_closed_flag_does_not_invalidate_one_linear_edge(self):
        line = DraftLine(Vector(), Vector(10,0,0))
        line.Closed = True
        self.assertIsNotNone(resolve_axis_source((line, ["Edge1"])))

    def test_selection_accepts_whole_line_or_edge1_but_not_multiple(self):
        line = DraftLine(Vector(), Vector(0,0,10))
        whole = types.SimpleNamespace(Object=line, SubElementNames=[])
        edge = types.SimpleNamespace(Object=line, SubElementNames=["Edge1"])
        self.assertIsNotNone(axis_source_from_selection([whole]))
        self.assertIsNotNone(axis_source_from_selection([edge]))
        self.assertIsNone(axis_source_from_selection([whole, edge]))


if __name__ == "__main__":
    unittest.main()
