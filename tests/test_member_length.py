"""Focused tests for the editable structural-member Length property."""

import importlib.util
import math
import sys
import types
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MEMBER = ROOT / "freecad/SteelStructures/member.py"


class Vector:
    def __init__(self, x=0.0, y=0.0, z=0.0):
        if isinstance(x, Vector):
            x, y, z = x.x, x.y, x.z
        self.x, self.y, self.z = float(x), float(y), float(z)

    @property
    def Length(self):
        return math.sqrt(self.x**2 + self.y**2 + self.z**2)

    def sub(self, other):
        return Vector(self.x - other.x, self.y - other.y, self.z - other.z)

    def add(self, other):
        return Vector(self.x + other.x, self.y + other.y, self.z + other.z)

    def normalize(self):
        length = self.Length
        self.x, self.y, self.z = self.x / length, self.y / length, self.z / length

    def __mul__(self, scalar):
        return Vector(self.x * scalar, self.y * scalar, self.z * scalar)


class Quantity:
    def __init__(self, value):
        self.Value = float(value)


def load_member():
    package_name = "_member_length_test_package"
    package = types.ModuleType(package_name)
    package.__path__ = [str(MEMBER.parent)]
    app = types.ModuleType("FreeCAD")
    app.Vector = Vector
    app.Console = types.SimpleNamespace(PrintWarning=lambda *_args: None)
    app.Rotation = app.Placement = object
    part = types.ModuleType("Part")
    part.Face = part.Shape = lambda *_args: object()
    part.makePolygon = lambda *_args: object()
    catalog = types.ModuleType(f"{package_name}.profile_catalog")
    catalog.Profile = object
    paths = types.ModuleType(f"{package_name}.paths")
    paths.OBJECT_ICON = "icon.svg"
    injected = {
        package_name: package,
        "FreeCAD": app,
        "Part": part,
        f"{package_name}.profile_catalog": catalog,
        f"{package_name}.paths": paths,
    }
    previous = {name: sys.modules.get(name) for name in injected}
    sys.modules.update(injected)
    try:
        spec = importlib.util.spec_from_file_location(f"{package_name}.member", MEMBER)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        for name, old in previous.items():
            if old is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = old


class FakeObject:
    def __init__(self, start, end, length=None, expression=False):
        self.StartPoint = Vector(*start)
        self.EndPoint = Vector(*end)
        self.Length = Quantity(length if length is not None else self.EndPoint.sub(self.StartPoint).Length)
        self.MemberLength = 0.0
        self._expression = expression

    def getExpression(self, name):
        return "Spreadsheet.A1" if name == "Length" and self._expression else None


class EditableLengthTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = load_member()

    def proxy(self):
        proxy = self.module.StructuralMemberProxy.__new__(self.module.StructuralMemberProxy)
        proxy._updating = False
        proxy._syncing_length = False
        proxy._last_valid_length = None
        return proxy

    def assertVector(self, vector, expected):
        self.assertEqual((round(vector.x, 7), round(vector.y, 7), round(vector.z, 7)), expected)

    def test_length_change_preserves_start_and_x_direction(self):
        obj = FakeObject((1, 2, 3), (11, 2, 3), 25)
        self.proxy().onChanged(obj, "Length")
        self.assertVector(obj.StartPoint, (1.0, 2.0, 3.0))
        self.assertVector(obj.EndPoint, (26.0, 2.0, 3.0))
        self.assertEqual(obj.MemberLength, 25.0)

    def test_length_change_preserves_inclined_direction(self):
        obj = FakeObject((0, 0, 0), (1, 1, 1), math.sqrt(12))
        self.proxy().onChanged(obj, "Length")
        self.assertVector(obj.EndPoint, (2.0, 2.0, 2.0))

    def test_endpoint_change_updates_length_and_member_length(self):
        obj = FakeObject((0, 0, 0), (0, 3, 4))
        self.proxy().onChanged(obj, "EndPoint")
        self.assertEqual(obj.Length, 5.0)
        self.assertEqual(obj.MemberLength, 5.0)

    def test_startpoint_change_updates_length(self):
        obj = FakeObject((0, 0, 1), (0, 0, 6))
        self.proxy().onChanged(obj, "StartPoint")
        self.assertEqual(obj.Length, 5.0)

    def test_expression_is_not_overwritten_by_point_change(self):
        obj = FakeObject((0, 0, 0), (0, 8, 0), 12, expression=True)
        self.proxy().onChanged(obj, "EndPoint")
        self.assertEqual(obj.Length.Value, 12.0)
        self.assertEqual(obj.MemberLength, 8.0)

    def test_zero_restores_last_valid_length_without_degenerate_endpoint(self):
        obj = FakeObject((0, 0, 0), (10, 0, 0), 0)
        proxy = self.proxy()
        proxy._last_valid_length = 10.0
        proxy.onChanged(obj, "Length")
        self.assertEqual(obj.Length, 10.0)
        self.assertVector(obj.EndPoint, (10.0, 0.0, 0.0))

    def test_degenerate_direction_is_rejected(self):
        obj = FakeObject((1, 1, 1), (1, 1, 1), 20)
        self.assertFalse(self.proxy()._sync_endpoint_from_length(obj))
        self.assertVector(obj.EndPoint, (1.0, 1.0, 1.0))

    def test_recursion_guard_is_released_after_change(self):
        obj = FakeObject((0, 0, 0), (2, 0, 0), 3)
        proxy = self.proxy()
        proxy.onChanged(obj, "Length")
        self.assertFalse(proxy._syncing_length)

    def test_source_adds_editable_length_and_keeps_member_length_read_only(self):
        source = MEMBER.read_text(encoding="utf-8")
        self.assertIn('"App::PropertyLength", "Length"', source)
        self.assertIn('obj.setEditorMode(prop, 1)', source)
        self.assertNotIn('("Length", "MemberLength"', source)

    def test_restore_migrates_and_synchronizes_length(self):
        source = MEMBER.read_text(encoding="utf-8")
        self.assertIn('"StartAdjustmentMode", "StartAdjustmentGeometryMode"', source)
        self.assertIn('"EndAdjustmentMode", "EndAdjustmentGeometryMode"', source)
        self.assertIn("required_properties.issubset", source)
        self.assertIn("self._sync_length_from_points(obj)", source)

    def test_linked_axis_updates_nominal_points_and_length(self):
        obj = FakeObject((0, 0, 0), (0, 0, 10))
        obj.AxisDefinitionMode = "Linked"
        obj.AxisSource = object()
        proxy = self.proxy()
        proxy._syncing_axis_source = False
        proxy._placement_from_points_pending = False
        original = self.module.resolve_axis_source
        self.module.resolve_axis_source = lambda _value: types.SimpleNamespace(
            start=Vector(10, 20, 30), end=Vector(110, 220, 330)
        )
        try:
            self.assertTrue(proxy._sync_axis_from_source(obj))
        finally:
            self.module.resolve_axis_source = original
        self.assertVector(obj.StartPoint, (10.0, 20.0, 30.0))
        self.assertVector(obj.EndPoint, (110.0, 220.0, 330.0))
        self.assertAlmostEqual(obj.MemberLength, math.sqrt(140000))
        self.assertTrue(proxy._placement_from_points_pending)

    def test_invalid_linked_axis_preserves_last_nominal_points(self):
        obj = FakeObject((1, 2, 3), (4, 5, 6))
        obj.AxisDefinitionMode = "Linked"
        obj.AxisSource = None
        proxy = self.proxy()
        original = self.module.resolve_axis_source
        self.module.resolve_axis_source = lambda _value: None
        try:
            self.assertFalse(proxy._sync_axis_from_source(obj))
        finally:
            self.module.resolve_axis_source = original
        self.assertVector(obj.StartPoint, (1.0, 2.0, 3.0))
        self.assertVector(obj.EndPoint, (4.0, 5.0, 6.0))

    def test_linked_axis_rejects_direct_endpoint_edit(self):
        obj = FakeObject((0, 0, 0), (0, 0, 10))
        obj.AxisDefinitionMode = "Linked"
        proxy = self.proxy()
        proxy.onChanged(obj, "EndPoint")
        self.assertEqual(obj.MemberLength, 0.0)


if __name__ == "__main__":
    unittest.main()
