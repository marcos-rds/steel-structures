"""Numerical rigid-Placement regression tests for structural members."""

from __future__ import annotations

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
        if hasattr(x, "x"): x, y, z = x.x, x.y, x.z
        elif isinstance(x, (tuple, list)): x, y, z = x
        self.x, self.y, self.z = float(x), float(y), float(z)
    @property
    def Length(self): return math.sqrt(self.x * self.x + self.y * self.y + self.z * self.z)
    def add(self, other): return Vector(self.x + other.x, self.y + other.y, self.z + other.z)
    def sub(self, other): return Vector(self.x - other.x, self.y - other.y, self.z - other.z)
    def __mul__(self, value): return Vector(self.x * value, self.y * value, self.z * value)
    def dot(self, other): return self.x * other.x + self.y * other.y + self.z * other.z
    def cross(self, other):
        return Vector(self.y * other.z - self.z * other.y,
                      self.z * other.x - self.x * other.z,
                      self.x * other.y - self.y * other.x)
    def normalize(self):
        length = self.Length; self.x /= length; self.y /= length; self.z /= length


def mat_mul(a, b):
    return tuple(tuple(sum(a[i][k] * b[k][j] for k in range(3)) for j in range(3)) for i in range(3))


def mat_vec(matrix, vector):
    values = (vector.x, vector.y, vector.z)
    return Vector(*(sum(matrix[i][j] * values[j] for j in range(3)) for i in range(3)))


def transpose(matrix): return tuple(tuple(matrix[j][i] for j in range(3)) for i in range(3))


class Rotation:
    def __init__(self, axis=None, value=None, z_axis=None, priority=None, matrix=None):
        if matrix is not None:
            self.matrix = matrix; return
        if z_axis is not None:
            x, y, z = Vector(axis), Vector(value), Vector(z_axis)
            self.matrix = ((x.x, y.x, z.x), (x.y, y.y, z.y), (x.z, y.z, z.z))
            return
        axis = Vector(axis or Vector(0, 0, 1))
        if isinstance(value, Vector):
            target = Vector(value); target.normalize()
            z = Vector(0, 0, 1)
            cross = Vector(-target.y, target.x, 0)
            dot = target.z
            if cross.Length < 1e-12:
                self.matrix = ((1, 0, 0), (0, 1 if dot > 0 else -1, 0), (0, 0, 1 if dot > 0 else -1))
            else:
                cross.normalize(); self.matrix = self._axis_angle(cross, math.degrees(math.acos(max(-1, min(1, dot)))))
        else:
            self.matrix = self._axis_angle(axis, float(value or 0.0))
    @staticmethod
    def _axis_angle(axis, degrees):
        axis = Vector(axis); axis.normalize(); x, y, z = axis.x, axis.y, axis.z
        angle = math.radians(degrees); c, s, t = math.cos(angle), math.sin(angle), 1 - math.cos(angle)
        return ((t*x*x+c, t*x*y-s*z, t*x*z+s*y), (t*x*y+s*z, t*y*y+c, t*y*z-s*x),
                (t*x*z-s*y, t*y*z+s*x, t*z*z+c))
    def multiply(self, other): return Rotation(matrix=mat_mul(self.matrix, other.matrix))


class Placement:
    def __init__(self, base=None, rotation=None):
        if isinstance(base, Placement):
            self.Base = Vector(base.Base); self.Rotation = Rotation(matrix=base.Rotation.matrix)
        else:
            self.Base = Vector(base or Vector()); self.Rotation = rotation or Rotation()
    def multiply(self, other):
        return Placement(self.multVec(other.Base), self.Rotation.multiply(other.Rotation))
    def inverse(self):
        inverse_rotation = Rotation(matrix=transpose(self.Rotation.matrix))
        return Placement(mat_vec(inverse_rotation.matrix, self.Base) * -1, inverse_rotation)
    def multVec(self, vector): return mat_vec(self.Rotation.matrix, Vector(vector)).add(self.Base)


class Quantity:
    def __init__(self, value): self.Value = float(value)


class Face:
    Area = 1000.0
    def __init__(self, wire): self.wire = wire; self.translation = Vector()
    def translate(self, vector): self.translation = Vector(vector)
    def copy(self):
        copied = Face(self.wire); copied.translation = Vector(self.translation); return copied
    @property
    def BoundBox(self):
        points = [point for edge in self.wire.edges for point in edge]
        xs = [point.x + self.translation.x for point in points]
        ys = [point.y + self.translation.y for point in points]
        return types.SimpleNamespace(XMin=min(xs), XMax=max(xs), YMin=min(ys), YMax=max(ys),
                                     XLength=max(xs)-min(xs), YLength=max(ys)-min(ys))
    @property
    def point(self):
        points = [point for edge in self.wire.edges for point in edge]
        return Vector(
            sum(point.x for point in points) / len(points) + self.translation.x,
            sum(point.y for point in points) / len(points) + self.translation.y,
            sum(point.z for point in points) / len(points) + self.translation.z,
        )
    def extrude(self, vector):
        solid = Solid(Vector(vector), Vector(self.translation), self.Area * max(vector.Length, 1.0))
        solid.face = self
        solid.normal = Vector(vector)
        if solid.normal.Length:
            solid.normal.normalize()
        self.normal = solid.normal
        return solid


class Solid:
    def __init__(self, vector, translation, volume):
        self.local_vector, self.face_translation, self.Volume = vector, translation, volume
        self.empty = False; self.clipped = False
        self.BoundBox = types.SimpleNamespace(
            XMin=-100.0, XMax=100.0, YMin=-100.0, YMax=100.0,
            ZMin=min(translation.z, translation.z + vector.z),
            ZMax=max(translation.z, translation.z + vector.z),
            XLength=200.0, YLength=200.0, ZLength=abs(vector.z),
        )
    def common(self, half_space):
        result = Solid(self.local_vector, self.face_translation, self.Volume * 0.9)
        result.clipped = True; result.half_space = half_space
        return result
    def isNull(self): return False
    def isValid(self): return True


class Wire:
    def __init__(self, edges): self.edges = list(edges)
    def isClosed(self): return bool(self.edges) and self.edges[-1][1].x == self.edges[0][0].x and self.edges[-1][1].y == self.edges[0][0].y


PROFILE = types.SimpleNamespace(bf=150.0, d=150.0, tw=6.0, tf=9.0, mass_per_m=13.0,
                                manufacturer="Test", family="W", area_cm2=16.6, source="Test",
                                designation="W 150 x 13,0", category="Aço laminado", series="Perfis W")


def load_member():
    package_name = "_member_placement_package"
    package = types.ModuleType(package_name); package.__path__ = [str(MEMBER.parent)]
    app = types.ModuleType("FreeCAD")
    app.Vector, app.Rotation, app.Placement = Vector, Rotation, Placement
    app.Console = types.SimpleNamespace(PrintWarning=lambda *_args: None)
    part = types.ModuleType("Part"); part.Face = Face; part.Wire = Wire; part.Shape = lambda: types.SimpleNamespace(empty=True)
    part.makePolygon = lambda points: Wire([(points[index], points[index + 1]) for index in range(len(points) - 1)])
    part.makeLine = lambda start, end: (start, end)
    part.Arc = lambda start, _mid, end: types.SimpleNamespace(toShape=lambda: (start, end))
    catalog = types.ModuleType(f"{package_name}.profile_catalog")
    catalog.Profile = object; catalog.get = lambda _name: PROFILE
    catalog.property_designation = lambda value: str(value).replace('"', "″")
    catalog.property_designations = lambda *_args: []
    catalog.categories = lambda: ["Aço laminado"]
    catalog.series_for_category = lambda _category: ["Perfis W"]
    catalog.insertion_options = lambda _profile: ("Centroide",)
    paths = types.ModuleType(f"{package_name}.paths"); paths.OBJECT_ICON = "member.svg"
    injected = {package_name: package, "FreeCAD": app, "Part": part,
                f"{package_name}.profile_catalog": catalog, f"{package_name}.paths": paths}
    old = {name: sys.modules.get(name) for name in injected}; sys.modules.update(injected)
    spec = importlib.util.spec_from_file_location(f"{package_name}.member", MEMBER)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    for name, previous in old.items():
        if previous is None: sys.modules.pop(name, None)
        else: sys.modules[name] = previous
    return module


class MemberObject:
    def __setattr__(self, name, value):
        current = self.__dict__.get(name)
        if isinstance(current, Quantity) and isinstance(value, (int, float)):
            current.Value = float(value)
            return
        object.__setattr__(self, name, value)

    def __init__(self, start, end):
        self.StartPoint, self.EndPoint = Vector(start), Vector(end)
        self.Length = Quantity(self.EndPoint.sub(self.StartPoint).Length); self.MemberLength = 0.0
        self.StartExtension = Quantity(0); self.EndExtension = Quantity(0)
        self.EndAdjustmentMode = "None"; self.AdjustedEnd = "Start"
        self.AdjustmentGap = Quantity(0); self.FixedReferenceOffset = Quantity(0)
        self.AdjustmentReference = None
        self.AdjustmentGeometryMode = "LengthLimit"; self.FixedPlaneNormal = Vector()
        self.EffectiveStartPoint = Vector(start); self.EffectiveEndPoint = Vector(end)
        self.AdjustedLength = 0.0
        self.OffsetX = Quantity(0); self.OffsetY = Quantity(0); self.Rotation = Quantity(0)
        self.Profile = "W 150 x 13,0"; self.Insertion = "Centroide"; self.MassPerMeter = 13.0
        self.ElementType = "Membro"
        self.ProfileCategory = "Aço laminado"; self.DisplayName = "Member"
        self.TotalMass = 0.0; self.Placement = Placement()
        self.PropertiesList = ["ProfileCategory", "DisplayName", "Length", "EndAdjustmentMode",
                               "AdjustedEnd", "AdjustmentGap", "FixedReferenceOffset",
                               "EffectiveStartPoint", "EffectiveEndPoint", "AdjustedLength",
                               "AdjustmentReference",
                               "AdjustmentGeometryMode", "FixedPlaneNormal",
                               "StartPoint", "EndPoint", "StartExtension", "EndExtension",
                               "OffsetX", "OffsetY", "Rotation", "Profile", "Insertion",
                               "MassPerMeter", "MemberLength", "TotalMass", "ElementType"]
        self.ExpressionEngine = []
        self.Label = "Member"
        self.editor_modes = {}
    def getExpression(self, _name): return None
    def addProperty(self, property_type, name, _group, _description):
        self.PropertiesList.append(name)
        if property_type == "App::PropertyLinkSub": setattr(self, name, None)
        elif property_type in ("App::PropertyDistance", "App::PropertyLength", "App::PropertyAngle"):
            setattr(self, name, Quantity(0))
        elif property_type == "App::PropertyVector": setattr(self, name, Vector())
        elif property_type == "App::PropertyFloat": setattr(self, name, 0.0)
        else: setattr(self, name, "")
    def setPropertyStatus(self, _name, _status): pass
    def setEditorMode(self, name, mode): self.editor_modes[name] = mode


class MemberPlacementTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.member = load_member()

    def proxy(self):
        proxy = self.member.StructuralMemberProxy.__new__(self.member.StructuralMemberProxy)
        proxy._updating = proxy._syncing_length = proxy._syncing_placement = False
        proxy._placement_from_points_pending = True; proxy._last_placement = None
        proxy._last_section_rotation = 0.0; proxy._last_valid_length = None
        return proxy

    def create(self, start, end):
        obj, proxy = MemberObject(start, end), self.proxy(); proxy.execute(obj); return obj, proxy

    def assertVector(self, actual, expected, places=6):
        for value, wanted in zip((actual.x, actual.y, actual.z), expected): self.assertAlmostEqual(value, wanted, places=places)

    def translate(self, obj, proxy, dx, dy, dz):
        moved = Placement(obj.Placement); moved.Base = moved.Base.add(Vector(dx, dy, dz))
        obj.Placement = moved; proxy.onChanged(obj, "Placement")

    def rotate_world(self, obj, proxy, axis, degrees):
        rigid = Placement(Vector(), Rotation(Vector(*axis), degrees))
        obj.Placement = rigid.multiply(obj.Placement); proxy.onChanged(obj, "Placement")

    def test_horizontal_vertical_and_diagonal_creation(self):
        for start, end in (((0, 0, 0), (10, 0, 0)), ((0, 0, 6), (0, 0, 16)), ((1, 2, 3), (4, 6, 15))):
            with self.subTest(start=start, end=end):
                obj, _proxy = self.create(start, end)
                self.assertAlmostEqual(obj.MemberLength, Vector(end).sub(Vector(start)).Length)
                self.assertVector(obj.Placement.Base, start)

    def test_manual_base_xyz_and_repeated_recompute_persist(self):
        for delta in ((7, 0, 0), (0, 8, 0), (0, 0, -3), (7, 8, -3)):
            with self.subTest(delta=delta):
                obj, proxy = self.create((0, 0, 6), (10, 0, 6)); original_length = obj.MemberLength
                self.translate(obj, proxy, *delta); expected_base = Vector(*delta).add(Vector(0, 0, 6))
                for _ in range(3): proxy.execute(obj); self.assertVector(obj.Placement.Base, (expected_base.x, expected_base.y, expected_base.z))
                self.assertVector(obj.StartPoint, (expected_base.x, expected_base.y, expected_base.z))
                self.assertVector(obj.EndPoint, (expected_base.x + 10, expected_base.y, expected_base.z))
                self.assertAlmostEqual(obj.MemberLength, original_length)

    def test_rotation_and_recompute_rotate_global_axis_without_double_transform(self):
        obj, proxy = self.create((0, 0, 0), (10, 0, 0)); original_shape = obj.Shape
        self.rotate_world(obj, proxy, (0, 0, 1), 90)
        self.assertVector(obj.StartPoint, (0, 0, 0)); self.assertVector(obj.EndPoint, (0, 10, 0))
        for _ in range(2): proxy.execute(obj)
        self.assertVector(obj.EndPoint, (0, 10, 0)); self.assertVector(obj.Placement.multVec(Vector(0, 0, 10)), (0, 10, 0))
        self.assertAlmostEqual(obj.MemberLength, 10); self.assertIsNot(obj.Shape, original_shape)

    def test_translation_rotation_orders_and_profile_change_preserve_transform(self):
        for order in ("translate_rotate", "rotate_translate"):
            obj, proxy = self.create((0, 0, 0), (0, 0, 10))
            if order == "translate_rotate":
                self.translate(obj, proxy, 2, 3, 4); self.rotate_world(obj, proxy, (0, 1, 0), 90)
            else:
                self.rotate_world(obj, proxy, (0, 1, 0), 90); self.translate(obj, proxy, 2, 3, 4)
            placement = Placement(obj.Placement); points = (Vector(obj.StartPoint), Vector(obj.EndPoint))
            obj.Profile = "W 200 x 15,0"; proxy.onChanged(obj, "Profile"); proxy.execute(obj)
            self.assertVector(obj.Placement.Base, (placement.Base.x, placement.Base.y, placement.Base.z))
            self.assertVector(obj.StartPoint, (points[0].x, points[0].y, points[0].z))
            self.assertVector(obj.EndPoint, (points[1].x, points[1].y, points[1].z))
            self.assertEqual(obj.Profile, "W 200 x 15,0")

    def test_section_rotation_changes_roll_without_restoring_moved_base(self):
        obj, proxy = self.create((0, 0, 0), (0, 0, 10)); self.translate(obj, proxy, 3, 4, 5)
        before_points = (Vector(obj.StartPoint), Vector(obj.EndPoint)); obj.Rotation = Quantity(35)
        proxy.onChanged(obj, "Rotation"); proxy.execute(obj)
        self.assertVector(obj.Placement.Base, (3, 4, 5)); self.assertVector(obj.StartPoint, (3, 4, 5))
        self.assertVector(obj.EndPoint, (3, 4, 15)); self.assertAlmostEqual(obj.MemberLength, 10)
        self.assertEqual((before_points[0].Length, before_points[1].sub(before_points[0]).Length), (math.sqrt(50), 10))

    def test_direct_start_and_end_edits_remain_authoritative(self):
        obj, proxy = self.create((0, 0, 0), (10, 0, 0))
        obj.StartPoint = Vector(1, 2, 3); proxy.onChanged(obj, "StartPoint"); proxy.execute(obj)
        self.assertVector(obj.Placement.Base, (1, 2, 3)); self.assertAlmostEqual(obj.MemberLength, math.sqrt(94))
        obj.EndPoint = Vector(1, 2, 13); proxy.onChanged(obj, "EndPoint"); proxy.execute(obj)
        self.assertVector(obj.Placement.Base, (1, 2, 3)); self.assertAlmostEqual(obj.MemberLength, 10)

    def test_fixed_start_gap_extensions_lengths_and_mass(self):
        obj, proxy = self.create((0, 0, 0), (3000, 0, 0))
        obj.EndAdjustmentMode = "Fixed"; obj.AdjustedEnd = "Start"
        obj.FixedReferenceOffset = Quantity(100); obj.AdjustmentGap = Quantity(20)
        obj.StartExtension = Quantity(50); obj.EndExtension = Quantity(30)
        nominal_start, nominal_end = Vector(obj.StartPoint), Vector(obj.EndPoint)
        proxy.execute(obj)
        self.assertVector(obj.EffectiveStartPoint, (120, 0, 0)); self.assertVector(obj.EffectiveEndPoint, (3030, 0, 0))
        self.assertAlmostEqual(obj.AdjustedLength, 2910); self.assertAlmostEqual(obj.Shape.local_vector.Length, 2910)
        self.assertAlmostEqual(obj.TotalMass, 13.0 * 2.91)
        self.assertVector(obj.StartPoint, (nominal_start.x, nominal_start.y, nominal_start.z))
        self.assertVector(obj.EndPoint, (nominal_end.x, nominal_end.y, nominal_end.z))
        self.assertAlmostEqual(obj.Length.Value, 3000); self.assertAlmostEqual(obj.MemberLength, 3000)
        obj.FixedReferenceOffset = Quantity(110); proxy.execute(obj)
        self.assertVector(obj.EffectiveStartPoint, (130, 0, 0)); self.assertEqual(obj.AdjustmentGap.Value, 20)

    def test_fixed_end_gap_is_independent_and_opposite_extension_is_kept(self):
        obj, proxy = self.create((0, 0, 0), (3000, 0, 0))
        obj.EndAdjustmentMode = "Fixed"; obj.AdjustedEnd = "End"
        obj.FixedReferenceOffset = Quantity(100); obj.AdjustmentGap = Quantity(20)
        obj.StartExtension = Quantity(40); obj.EndExtension = Quantity(90)
        proxy.execute(obj)
        self.assertVector(obj.EffectiveStartPoint, (-40, 0, 0)); self.assertVector(obj.EffectiveEndPoint, (2880, 0, 0))
        self.assertAlmostEqual(obj.AdjustedLength, 2920)
        obj.AdjustmentGap = Quantity(30); proxy.execute(obj)
        self.assertEqual(obj.FixedReferenceOffset.Value, 100)
        self.assertVector(obj.EffectiveEndPoint, (2870, 0, 0)); self.assertAlmostEqual(obj.AdjustedLength, 2910)
        obj.EndAdjustmentMode = "None"; proxy.execute(obj)
        self.assertVector(obj.EffectiveEndPoint, (3090, 0, 0)); self.assertAlmostEqual(obj.AdjustedLength, 3130)

    def test_fixed_reference_remains_anchored_when_nominal_endpoint_changes(self):
        obj, proxy = self.create((0, 0, 0), (1000, 0, 0))
        obj.EndAdjustmentMode = "Fixed"; obj.AdjustedEnd = "End"
        obj.FixedReferenceOffset = Quantity(100); obj.AdjustmentGap = Quantity(20)
        obj.EndPoint = Vector(1500, 0, 0); proxy.onChanged(obj, "EndPoint"); proxy.execute(obj)
        self.assertVector(obj.EffectiveEndPoint, (1380, 0, 0)); self.assertEqual(obj.FixedReferenceOffset.Value, 100)
        self.assertAlmostEqual(obj.MemberLength, 1500)

    def test_fixed_start_remains_anchored_when_nominal_start_changes(self):
        obj, proxy = self.create((0, 0, 0), (1000, 0, 0))
        obj.EndAdjustmentMode = "Fixed"; obj.AdjustedEnd = "Start"
        obj.FixedReferenceOffset = Quantity(100); obj.AdjustmentGap = Quantity(20)
        obj.StartPoint = Vector(100, 0, 0); proxy.onChanged(obj, "StartPoint"); proxy.execute(obj)
        self.assertVector(obj.EffectiveStartPoint, (220, 0, 0)); self.assertEqual(obj.FixedReferenceOffset.Value, 100)
        self.assertAlmostEqual(obj.MemberLength, 900)

    def test_fixed_placement_translation_rotation_and_recompute_have_no_drift(self):
        obj, proxy = self.create((0, 0, 0), (10, 0, 0))
        obj.EndAdjustmentMode = "Fixed"; obj.AdjustedEnd = "Start"
        obj.FixedReferenceOffset = Quantity(2); obj.AdjustmentGap = Quantity(1)
        proxy.execute(obj); self.translate(obj, proxy, 5, 6, 7); self.rotate_world(obj, proxy, (0, 0, 1), 90)
        for _ in range(4):
            proxy.execute(obj)
            self.assertVector(obj.StartPoint, (-6, 5, 7)); self.assertVector(obj.EndPoint, (-6, 15, 7))
            self.assertVector(obj.EffectiveStartPoint, (-6, 8, 7)); self.assertVector(obj.EffectiveEndPoint, (-6, 15, 7))
            self.assertVector(obj.Placement.Base, (-6, 8, 7))
            self.assertEqual(obj.FixedReferenceOffset.Value, 2); self.assertEqual(obj.AdjustmentGap.Value, 1)

    def test_invalid_fixed_interval_is_empty_and_consistent(self):
        obj, proxy = self.create((0, 0, 0), (10, 0, 0))
        obj.EndAdjustmentMode = "Fixed"; obj.AdjustedEnd = "Start"
        for offset in (10, 11, 1000):
            obj.FixedReferenceOffset = Quantity(offset); proxy.execute(obj)
            self.assertTrue(obj.Shape.empty); self.assertEqual(obj.AdjustedLength, 0)
            self.assertVector(obj.EffectiveEndPoint, (offset, 0, 0))
            self.assertEqual(obj.TotalMass, 0); self.assertEqual(obj.MemberLength, 10)

    def test_profile_and_rotation_edits_preserve_effective_contract(self):
        obj, proxy = self.create((0, 0, 0), (0, 0, 100))
        obj.EndAdjustmentMode = "Fixed"; obj.AdjustedEnd = "End"
        obj.FixedReferenceOffset = Quantity(10); obj.AdjustmentGap = Quantity(2); proxy.execute(obj)
        expected = (Vector(obj.EffectiveStartPoint), Vector(obj.EffectiveEndPoint), obj.AdjustedLength)
        obj.Profile = "W 200 x 15,0"; proxy.onChanged(obj, "Profile")
        obj.Rotation = Quantity(25); proxy.onChanged(obj, "Rotation"); proxy.execute(obj)
        self.assertVector(obj.EffectiveStartPoint, (expected[0].x, expected[0].y, expected[0].z))
        self.assertVector(obj.EffectiveEndPoint, (expected[1].x, expected[1].y, expected[1].z))
        self.assertEqual(obj.AdjustedLength, expected[2])

    def test_restore_and_legacy_proxy_preserve_existing_placement(self):
        obj, proxy = self.create((0, 0, 6), (10, 0, 6)); self.translate(obj, proxy, 1, 2, -3)
        restored = self.proxy(); restored.__setstate__(None); restored._setup_properties = lambda _obj: None
        restored.onDocumentRestored(obj); placement = Placement(obj.Placement); restored.execute(obj)
        self.assertVector(obj.Placement.Base, (placement.Base.x, placement.Base.y, placement.Base.z))
        self.assertVector(obj.StartPoint, (1, 2, 3)); self.assertVector(obj.EndPoint, (11, 2, 3))

    def test_existing_column_type_survives_recompute_and_restore(self):
        obj, proxy = self.create((0, 0, 0), (0, 0, 3000))
        obj.ElementType = "Pilar"
        proxy.execute(obj)
        self.assertEqual(obj.ElementType, "Pilar")
        restored = self.proxy(); restored.__setstate__(None)
        restored._setup_properties = lambda _obj: None
        restored.onDocumentRestored(obj)
        restored.execute(obj)
        self.assertEqual(obj.ElementType, "Pilar")

    def test_restore_installs_legacy_adjustment_properties_with_none_default(self):
        obj = MemberObject((0, 0, 0), (0, 0, 100))
        for name in ("EndAdjustmentMode", "AdjustedEnd", "AdjustmentGap", "FixedReferenceOffset",
                     "EffectiveStartPoint", "EffectiveEndPoint", "AdjustedLength", "AdjustmentReference",
                     "AdjustmentGeometryMode", "FixedPlaneNormal"):
            obj.PropertiesList.remove(name); delattr(obj, name)
        restored = self.proxy(); restored.__setstate__(None); restored.onDocumentRestored(obj)
        self.assertEqual(obj.EndAdjustmentMode, "None"); self.assertEqual(obj.AdjustedEnd, "Start")
        self.assertEqual(obj.AdjustmentGap.Value, 0); self.assertEqual(obj.FixedReferenceOffset.Value, 0)
        self.assertIsNone(obj.AdjustmentReference)
        self.assertEqual(obj.AdjustmentGeometryMode, "LengthLimit")
        self.assertVector(obj.FixedPlaneNormal, (0, 0, 0))
        for name in ("EffectiveStartPoint", "EffectiveEndPoint", "AdjustedLength"):
            self.assertEqual(obj.editor_modes[name], 1)

    def test_restore_preserves_existing_fixed_values(self):
        obj, proxy = self.create((0, 0, 0), (0, 0, 100))
        obj.EndAdjustmentMode = "Fixed"; obj.AdjustedEnd = "End"
        obj.FixedReferenceOffset = Quantity(-15); obj.AdjustmentGap = Quantity(7); proxy.execute(obj)
        restored = self.proxy(); restored.__setstate__(None); restored.onDocumentRestored(obj); restored.execute(obj)
        self.assertEqual(obj.EndAdjustmentMode, "Fixed"); self.assertEqual(obj.AdjustedEnd, "End")
        self.assertEqual(obj.FixedReferenceOffset.Value, -15); self.assertEqual(obj.AdjustmentGap.Value, 7)
        self.assertVector(obj.EffectiveEndPoint, (0, 0, 108))

    def test_guards_release_after_sync_exception_and_block_recursion(self):
        obj, proxy = self.create((0, 0, 0), (10, 0, 0)); self.translate(obj, proxy, 1, 0, 0)
        old = proxy._last_placement; proxy._last_placement = types.SimpleNamespace(inverse=lambda: (_ for _ in ()).throw(RuntimeError("fail")))
        proxy.onChanged(obj, "Placement")
        self.assertFalse(proxy._syncing_placement); self.assertFalse(proxy._syncing_length)
        proxy._last_placement = old; proxy.onChanged(obj, "Placement"); self.assertFalse(proxy._syncing_placement)


if __name__ == "__main__":
    unittest.main()
