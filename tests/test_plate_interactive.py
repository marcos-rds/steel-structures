"""Behavioral tests for the plate session without a running FreeCAD GUI."""

import importlib.util
import sys
import types
import unittest
from pathlib import Path


PACKAGE = Path(__file__).resolve().parents[1] / "freecad" / "SteelStructures"


class Vector:
    def __init__(self, x, y=None, z=None):
        if y is None:
            if isinstance(x, Vector):
                x, y, z = x.x, x.y, x.z
            else:
                x, y, z = x
        self.x, self.y, self.z = float(x), float(y), float(z)

    def sub(self, other):
        return Vector(self.x - other.x, self.y - other.y, self.z - other.z)

    def cross(self, other):
        return Vector(self.y * other.z - self.z * other.y,
                      self.z * other.x - self.x * other.z,
                      self.x * other.y - self.y * other.x)

    def dot(self, other):
        return self.x * other.x + self.y * other.y + self.z * other.z

    @property
    def Length(self):
        return (self.x**2 + self.y**2 + self.z**2) ** .5


class Placement:
    def inverse(self):
        return self

    def multVec(self, point):
        return Vector(point)


class PointFrame:
    def __init__(self, origin, x_axis, y_axis, normal, inverse=False):
        self.Base = Vector(origin)
        self.axes = (x_axis, y_axis, normal)
        self._inverse = inverse

    def inverse(self):
        return PointFrame(self.Base, *self.axes, inverse=not self._inverse)

    def multVec(self, point):
        point = Vector(point)
        if self._inverse:
            delta = point.sub(self.Base)
            return Vector(*(delta.dot(axis) for axis in self.axes))
        x, y, z = self.axes
        return Vector(self.Base.x + x.x * point.x + y.x * point.y + z.x * point.z,
                      self.Base.y + x.y * point.x + y.y * point.y + z.y * point.z,
                      self.Base.z + x.z * point.x + y.z * point.y + z.z * point.z)


class RaisedPlacement:
    def __init__(self, height, center=None):
        self.height = height
        self.Base = Vector(center if center is not None else (0, 0, height))

    def inverse(self):
        return RaisedPlacement(-self.height)

    def multVec(self, point):
        point = Vector(point)
        return Vector(point.x, point.y, point.z + self.height)


class VerticalPlacement:
    def __init__(self, inverse=False):
        self._inverse = inverse

    def inverse(self):
        return VerticalPlacement(not self._inverse)

    def multVec(self, point):
        point = Vector(point)
        if self._inverse:
            return Vector(point.y - 200, point.z - 300, point.x - 100)
        return Vector(100 + point.z, 200 + point.x, 300 + point.y)


class Preview:
    def __init__(self, _view):
        self.removed = False
        self.remove_calls = 0
        self.outlines = []
        self.solids = []

    def outline(self, points, cursor=None):
        self.outlines.append((points, cursor))

    def solid(self, contour, placement, thickness, offset):
        self.solids.append((contour, placement, thickness, offset))

    def clear(self):
        pass

    def remove(self):
        self.removed = True
        self.remove_calls += 1


class Document:
    def __init__(self):
        self.opened = self.committed = self.aborted = 0

    def openTransaction(self, _name):
        self.opened += 1

    def commitTransaction(self):
        self.committed += 1

    def abortTransaction(self):
        self.aborted += 1


class PlateInteractiveTests(unittest.TestCase):
    def setUp(self):
        namespace = "_plate_interactive_test"
        package = types.ModuleType(namespace)
        package.__path__ = [str(PACKAGE)]
        interactive = types.ModuleType(namespace + ".interactive")
        interactive.__path__ = [str(PACKAGE / "interactive")]
        freecad = types.ModuleType("FreeCAD")
        freecad.Vector = Vector
        freecad.Console = types.SimpleNamespace(PrintWarning=lambda _text: None)
        self.selection = types.SimpleNamespace(clearSelection=lambda: None,
                                               addSelection=lambda _obj: None)
        gui = types.ModuleType("FreeCADGui")
        gui.Selection = self.selection
        gui.activeDocument = lambda: types.SimpleNamespace(activeView=lambda: self.view)
        preview = types.ModuleType(namespace + ".interactive.plate_preview")
        preview.PlatePreview = Preview
        source = types.ModuleType(namespace + ".plate_sources")
        source.is_draft_rectangle = lambda obj: getattr(obj, "kind", "") == "rectangle"
        source.is_draft_wire = lambda obj: getattr(obj, "kind", "") == "wire"
        source.resolve_plate_source = self._resolve_source
        planes = types.ModuleType(namespace + ".plate_planes")
        planes.placement_from_face = self._face_placement
        planes.placement_from_points = self._points_placement
        planes.view_pick = self._view_pick
        planes.preselection_pick = lambda item, _document: (
            item if item is not None else (None, None))
        planes.screen_coordinates = lambda position: (
            tuple(position.getValue()) if hasattr(position, "getValue")
            else tuple(position)) if position is not None else None
        plate = types.ModuleType(namespace + ".plate")
        plate.create_plate = self._create_plate
        self.view = types.SimpleNamespace()
        self.created = []
        self.injections = {
            namespace: package, namespace + ".interactive": interactive,
            namespace + ".interactive.plate_preview": preview,
            namespace + ".plate_sources": source,
            namespace + ".plate_planes": planes,
            namespace + ".plate": plate,
            "FreeCAD": freecad, "FreeCADGui": gui,
        }
        self.old = {key: sys.modules.get(key) for key in self.injections}
        sys.modules.update(self.injections)
        for name, filename in (("plate_geometry", PACKAGE / "plate_geometry.py"),
                               ("interactive.plate_controller",
                                PACKAGE / "interactive" / "plate_controller.py")):
            fullname = namespace + "." + name
            spec = importlib.util.spec_from_file_location(fullname, filename)
            module = importlib.util.module_from_spec(spec)
            sys.modules[fullname] = module
            spec.loader.exec_module(module)
        self.module = sys.modules[namespace + ".interactive.plate_controller"]
        self.geometry = sys.modules[namespace + ".plate_geometry"]
        self.document = Document()

    def tearDown(self):
        for key in list(sys.modules):
            if key.startswith("_plate_interactive_test"):
                sys.modules.pop(key, None)
        for key, old in self.old.items():
            if old is None:
                sys.modules.pop(key, None)
            else:
                sys.modules[key] = old

    def _resolve_source(self, source, _mode):
        contour = self.geometry.PlateContour2D.from_points(source.vertices)
        return types.SimpleNamespace(contour=contour, placement=Placement())

    @staticmethod
    def _face_placement(face):
        if not face.planar:
            raise ValueError("A face selecionada deve ser plana.")
        return face.placement

    @staticmethod
    def _points_placement(first, second, third):
        origin = Vector(first)
        side = Vector(second).sub(origin)
        if side.Length <= 1e-7:
            return None
        cross = side.cross(Vector(third).sub(origin))
        if cross.Length / side.Length <= 1e-7:
            return None
        x_axis = Vector(side.x / side.Length, side.y / side.Length,
                        side.z / side.Length)
        normal = Vector(cross.x / cross.Length, cross.y / cross.Length,
                        cross.z / cross.Length)
        y_axis = normal.cross(x_axis)
        return PointFrame(origin, x_axis, y_axis, normal)

    @staticmethod
    def _view_pick(view, position, _document):
        info = view.getObjectInfo(position) if hasattr(view, "getObjectInfo") else None
        return info, Vector(info["point"]) if info else None

    def _create_plate(self, *args, **kwargs):
        obj = types.SimpleNamespace(args=args, kwargs=kwargs)
        self.created.append(obj)
        return obj

    def controller(self, **kwargs):
        kwargs.setdefault("placement", Placement())
        kwargs.setdefault("plane_mode", "WorkPlane")
        return self.module.PlateController(self.document, view=self.view, **kwargs)

    def test_polygon_closes_near_first_and_creates_once(self):
        controller = self.controller()
        for point in ((0, 0, 0), (100, 0, 0), (120, 40, 0), (50, 80, 0)):
            controller.add_point(point)
        controller.add_point((.0001, .0001, 0))
        self.assertEqual(4, len(controller.contour.vertices))
        plate = controller.create(8, -3)
        self.assertIs(plate, self.created[0])
        self.assertEqual((1, 1, 0),
                         (self.document.opened, self.document.committed,
                          self.document.aborted))
        self.assertEqual("InteractivePolygon", plate.kwargs["source_mode"])
        self.assertTrue(controller.preview.removed)

    def test_explicit_close_rejects_crossing_final_edge_without_object(self):
        controller = self.controller()
        for point in ((0, 0, 0), (3, 0, 0), (0, 3, 0), (3, 3, 0)):
            controller.add_point(point)
        with self.assertRaises(ValueError):
            controller.close_outline()
        self.assertIsNone(controller.contour)
        self.assertEqual(4, len(controller.points))
        self.assertEqual(0, self.document.opened)

    def test_three_point_close_and_cancel_before_close(self):
        controller = self.controller()
        for point in ((0, 0, 0), (10, 0, 0), (5, 5, 0)):
            controller.add_point(point)
        controller.close_outline()
        self.assertAlmostEqual(25, controller.contour.area)
        cancelled = self.controller()
        cancelled.add_point((0, 0, 0))
        cancelled.cancel()
        self.assertTrue(cancelled.preview.removed)
        self.assertEqual(0, self.document.opened)

    def test_six_vertex_polygon_explicit_close(self):
        controller = self.controller()
        for point in ((0, 0, 0), (10, 0, 0), (12, 4, 0),
                      (8, 8, 0), (4, 9, 0), (-2, 4, 0)):
            controller.add_point(point)
        controller.close_outline()
        self.assertEqual(6, len(controller.contour.vertices))
        self.assertGreater(controller.contour.area, 0)

    def test_rectangle_uses_four_generic_vertices(self):
        controller = self.controller()
        controller.set_mode("InteractiveRectangle")
        controller.add_point((2, 3, 0))
        controller.add_point((8, 9, 0))
        self.assertEqual(((2, 3), (8, 3), (8, 9), (2, 9)),
                         controller.contour.vertices)
        self.assertEqual("InteractiveRectangle", controller.create(6, 1).kwargs["source_mode"])

    def test_rectangle_hover_draws_four_sides_and_updates_opposite_corner(self):
        controller = self.controller()
        controller.set_mode("InteractiveRectangle")
        controller.add_point((2, 3, 0))
        controller.update_preview(6, 0, Vector(8, 9, 0))
        first = controller.preview.outlines[-1][0]
        self.assertEqual([(2, 3), (8, 3), (8, 9), (2, 9), (2, 3)],
                         [(p.x, p.y) for p in first])
        controller.update_preview(6, 0, Vector(-4, 12, 0))
        second = controller.preview.outlines[-1][0]
        self.assertEqual([(2, 3), (-4, 3), (-4, 12), (2, 12), (2, 3)],
                         [(p.x, p.y) for p in second])
        self.assertEqual([], controller.preview.solids)
        controller.cancel()
        self.assertEqual(1, controller.preview.remove_calls)

    def test_rectangle_hover_stays_on_vertical_local_plane(self):
        controller = self.controller(placement=VerticalPlacement())
        controller.set_mode("InteractiveRectangle")
        controller.add_point((100, 202, 303))
        controller.update_preview(6, 0, Vector(100, 208, 309))
        points = controller.preview.outlines[-1][0]
        self.assertEqual([(100, 202, 303), (100, 208, 303),
                          (100, 208, 309), (100, 202, 309),
                          (100, 202, 303)],
                         [(p.x, p.y, p.z) for p in points])
        controller.cancel()

    def test_auto_uses_selected_face_and_rejects_off_plane_next_point(self):
        face = types.SimpleNamespace(planar=True, placement=Placement())
        controller = self.controller(plane_mode="Auto", plane_face=face)
        self.assertIs(controller.placement, face.placement)
        self.assertEqual("Face", controller._plane_kind)
        controller.add_point((1, 2, 0))
        with self.assertRaisesRegex(ValueError, "fora do plano da chapa"):
            controller.add_point((3, 4, 1))
        self.assertEqual(1, len(controller.points))
        controller.cancel()

    def test_auto_polygon_plane_is_defined_by_ordered_points(self):
        cases = (
            ((20, 0, 0), (40, 0, 0), (60, 20, 0)),
            ((20, 0, 0), (20, 0, 40), (60, 0, 40)),
            ((0, 20, 0), (0, 20, 40), (0, 80, 40)),
            ((4, 5, 6), (14, 5, 9), (17, 15, 11)),
        )
        for vertices in cases:
            with self.subTest(vertices=vertices):
                controller = self.controller(plane_mode="Auto")
                self.assertEqual(self.module.NO_PLANE, controller.plane_state)
                self.assertIsNone(controller.placement)
                controller.add_point(vertices[0])
                self.assertEqual(self.module.NO_PLANE, controller.plane_state)
                controller.add_point(vertices[1])
                self.assertEqual(self.module.FIRST_DIRECTION, controller.plane_state)
                self.assertIsNone(controller.placement)
                controller.add_point(vertices[2])
                self.assertEqual(self.module.PLANE_DEFINED, controller.plane_state)
                self.assertEqual("Points", controller._plane_kind)
                self.assertEqual(3, len(controller.points))
                self.assertTrue(all(abs(controller.placement.inverse().multVec(
                    Vector(point)).z) < 1e-6 for point in vertices))
                expected = Vector(vertices[1]).sub(Vector(vertices[0])).cross(
                    Vector(vertices[2]).sub(Vector(vertices[0])))
                self.assertGreater(controller.placement.axes[2].dot(expected), 0)
                controller.close_outline()
                self.assertGreater(controller.contour.area, 0)
                self.assertEqual(3, len(controller.contour.vertices))
                controller.cancel()

    def test_auto_polygon_keeps_collinear_prefix_until_plane_exists(self):
        controller = self.controller(plane_mode="Auto")
        for point in ((0, 0, 5), (10, 0, 5), (20, 0, 5), (30, 0, 5)):
            controller.add_point(point)
        self.assertEqual(self.module.FIRST_DIRECTION, controller.plane_state)
        self.assertEqual(4, controller.point_count)
        with self.assertRaisesRegex(ValueError, "pelo menos"):
            controller.close_outline()
        controller.add_point((30, 10, 5))
        self.assertEqual(5, len(controller.points))
        self.assertEqual(self.module.PLANE_DEFINED, controller.plane_state)
        controller.add_point((0, 10, 5))
        with self.assertRaisesRegex(ValueError, "fora do plano da chapa"):
            controller.add_point((0, 20, 6))
        self.assertEqual(6, controller.point_count)
        controller.close_outline()
        self.assertEqual(6, len(controller.contour.vertices))
        controller.cancel()

    def test_auto_plane_is_independent_of_cursor_position(self):
        vertices = ((4, 5, 6), (14, 5, 9), (17, 15, 11))
        normals = []
        for screens in (((10, 10), (11, 11), (12, 12)),
                        ((800, 500), (2, 999), (400, 1))):
            controller = self.controller(plane_mode="Auto")
            for point, screen in zip(vertices, screens):
                controller.add_point(point, screen_position=screen)
            normals.append(controller.placement.axes[2])
            controller.cancel()
        self.assertLess(normals[0].sub(normals[1]).Length, 1e-12)

    def test_auto_snap_uses_3d_points_without_hover_plane(self):
        face = types.SimpleNamespace(planar=True, placement=RaisedPlacement(128))
        self.view.getObjectInfo = lambda _position: {
            "Component": "Face6", "point": Vector(50, 50, 128), "face": face}
        controller, callbacks, _removed, _snaps = self._capture_session()
        controller.set_plane_mode("Auto")
        self.module.Gui.Snapper.cursorMode = "endpoint"
        values = iter((Vector(0, 0, 128), Vector(10, 0, 128),
                       Vector(10, 20, 128), Vector(0, 20, 129)))
        self.module.Gui.Snapper.snap = lambda *_args, **_kwargs: next(values)
        errors = []
        controller.on_error = errors.append
        click = callbacks["SoMouseButtonEvent"]
        for kind in ("Vertex1", "Edge1", "Vertex2"):
            self.module.Gui.Snapper.snapInfo = {"Component": kind}
            click({"Position": (1, 2), "State": "DOWN", "Button": "BUTTON1"})
        self.assertEqual(self.module.PLANE_DEFINED, controller.plane_state)
        self.assertEqual("Points", controller._plane_kind)
        self.assertEqual(128, controller.placement.Base.z)
        click({"Position": (999, 888), "State": "DOWN", "Button": "BUTTON1"})
        self.assertEqual(3, controller.point_count)
        self.assertEqual(1, len(errors))
        self.assertIn("fora do plano da chapa", errors[0])
        controller.cancel()

    def test_auto_passive_snap_uses_native_3d_pick_only_as_point(self):
        self.view.getObjectInfo = lambda _position: {
            "Component": "Vertex1", "point": Vector(4, 5, 128)}
        controller, callbacks, _removed, _snaps = self._capture_session()
        controller.set_plane_mode("Auto")
        self.module.Gui.Snapper.cursorMode = "passive"
        callbacks["SoMouseButtonEvent"]({
            "Position": (1, 2), "State": "DOWN", "Button": "BUTTON1"})
        self.assertEqual(128, controller._pending_world_points[0].z)
        self.assertEqual(self.module.NO_PLANE, controller.plane_state)
        controller.cancel()

    def test_auto_snap_bypasses_draft_work_plane_projection_temporarily(self):
        controller = self.controller(plane_mode="Auto")
        real = Vector(5, 7, 128)
        def project(point):
            return Vector(point.x, point.y, 0)
        snapper = types.SimpleNamespace(toWP=project, snapInfo={},
                                        snap=lambda *_args, **_kwargs: snapper.toWP(real))
        self.module.Gui.Snapper = snapper
        result = controller._snap_point({"Position": (1, 2)})
        self.assertEqual(128, result.z)
        self.assertIs(snapper.toWP, project)
        self.assertEqual(0, snapper.toWP(real).z)
        def fail(*_args, **_kwargs):
            raise RuntimeError("snap failed")
        snapper.snap = fail
        with self.assertRaisesRegex(RuntimeError, "snap failed"):
            controller._snap_point({"Position": (1, 2)})
        self.assertIs(snapper.toWP, project)
        controller.cancel()

    def test_auto_pending_points_block_plane_switch_and_cancel_cleanly(self):
        for mode, count in (("InteractivePolygon", 0),
                            ("InteractivePolygon", 1),
                            ("InteractivePolygon", 2),
                            ("InteractivePolygon", 3),
                            ("InteractiveRectangle", 2)):
            with self.subTest(mode=mode, count=count):
                controller = self.controller(plane_mode="Auto")
                controller.set_mode(mode)
                for point in ((0, 0, 128), (10, 0, 128), (10, 5, 128))[:count]:
                    controller.add_point(point)
                if count:
                    with self.assertRaisesRegex(ValueError, "antes do primeiro ponto"):
                        controller.set_plane_mode("WorkPlane")
                controller.cancel()
                controller.cancel()
                self.assertTrue(controller.preview.removed)
                self.assertEqual(1, controller.preview.remove_calls)
                self.assertEqual(0, self.document.opened)

    def test_auto_rectangle_requires_three_points_and_previews_local_rectangle(self):
        for vertices in (
            ((0, 0, 0), (10, 0, 0), (10, 5, 0)),
            ((0, 0, 0), (0, 0, 10), (5, 0, 10)),
            ((0, 0, 0), (0, 0, 10), (0, 5, 10)),
            ((2, 3, 4), (12, 3, 7), (15, 9, 8)),
        ):
            with self.subTest(vertices=vertices):
                controller = self.controller(plane_mode="Auto")
                controller.set_mode("InteractiveRectangle")
                controller.add_point(vertices[0])
                controller.update_preview(6, 0, Vector(vertices[1]))
                self.assertEqual(1, len(controller.preview.outlines[-1][0]))
                self.assertIsNotNone(controller.preview.outlines[-1][1])
                controller.add_point(vertices[1])
                self.assertEqual(self.module.FIRST_DIRECTION, controller.plane_state)
                self.assertIsNone(controller.contour)
                controller.update_preview(6, 0, Vector(vertices[2]))
                outline = controller.preview.outlines[-1][0]
                self.assertEqual(5, len(outline))
                self.assertLess(outline[0].sub(outline[-1]).Length, 1e-7)
                controller.add_point(vertices[2])
                self.assertEqual(4, len(controller.contour.vertices))
                self.assertEqual(self.module.PLANE_DEFINED, controller.plane_state)
                self.assertGreater(controller.contour.area, 0)
                controller.cancel()
                self.assertTrue(controller.preview.removed)

    def test_auto_rectangle_collinear_third_point_keeps_pending_state(self):
        controller = self.controller(plane_mode="Auto")
        controller.set_mode("InteractiveRectangle")
        controller.add_point((0, 0, 0))
        controller.add_point((10, 0, 0))
        with self.assertRaisesRegex(ValueError, "terceiro ponto"):
            controller.add_point((20, 0, 0))
        self.assertEqual(2, controller.point_count)
        self.assertIsNone(controller.placement)
        controller.cancel()

    def test_auto_rectangle_third_point_sets_width_not_a_skew_side(self):
        controller = self.controller(plane_mode="Auto")
        controller.set_mode("InteractiveRectangle")
        for point in ((0, 0, 0), (10, 0, 0), (13, 5, 0)):
            controller.add_point(point)
        self.assertEqual(((0, 0), (10, 0), (10, 5), (0, 5)),
                         controller.contour.vertices)
        controller.cancel()

    def test_auto_face_selected_rectangle_remains_two_points(self):
        face = types.SimpleNamespace(planar=True, placement=RaisedPlacement(128))
        controller = self.controller(plane_mode="Auto", plane_face=face)
        controller.set_mode("InteractiveRectangle")
        controller.add_point((2, 3, 128))
        controller.add_point((8, 9, 128))
        self.assertEqual(4, len(controller.contour.vertices))
        self.assertEqual("Face", controller._plane_kind)
        controller.cancel()

    def test_work_plane_ignores_face_pick_on_first_click(self):
        face = types.SimpleNamespace(planar=True, placement=RaisedPlacement(128))
        self.view.getObjectInfo = lambda _position: {
            "Component": "Face6", "point": Vector(20, 15, 128), "face": face}
        controller, callbacks, _removed, _snaps = self._capture_session()
        controller.set_plane_mode("WorkPlane")
        self.module.Gui.Snapper.snap = lambda *_args, **_kwargs: Vector(20, 15, 128)
        callbacks["SoMouseButtonEvent"]({
            "Position": (1, 2), "State": "DOWN", "Button": "BUTTON1"})
        self.assertEqual([], controller.points)
        self.assertEqual("WorkPlane", controller._plane_kind)
        controller.cancel()

    def test_nonplanar_face_rejected_and_work_plane_mode_unchanged(self):
        curved = types.SimpleNamespace(planar=False, placement=Placement())
        with self.assertRaisesRegex(ValueError, "face selecionada deve ser plana"):
            self.controller(plane_mode="Auto", plane_face=curved)
        controller = self.controller(plane_mode="WorkPlane", plane_face=curved)
        with self.assertRaisesRegex(ValueError, "fora do plano de trabalho"):
            controller.add_point((1, 2, 1))
        controller.add_point((1, 2, 0))
        with self.assertRaisesRegex(ValueError, "antes do primeiro ponto"):
            controller.set_plane_mode("Auto")
        controller.cancel()

    def test_out_of_plane_point_rejected(self):
        controller = self.controller()
        with self.assertRaisesRegex(ValueError, "fora do plano"):
            controller.add_point((1, 2, 1))
        self.assertFalse(controller.points)

    def test_escape_removes_callbacks_and_preview_without_transaction(self):
        callbacks = {}
        removed = []
        def add(kind, handler):
            callbacks[kind] = handler
            return kind
        self.view.addEventCallback = add
        self.view.removeEventCallback = lambda kind, token: removed.append((kind, token))
        snapper = types.SimpleNamespace(show=lambda: None,
                                        off=lambda: removed.append(("snap", "off")))
        self.module.Gui.Snapper = snapper
        controller = self.controller()
        controller.on_cancel = controller.cancel
        controller.start_capture(lambda: 10, lambda: 0)
        self.assertEqual(3, len(callbacks))
        callbacks["SoKeyboardEvent"]({"Key": "ESCAPE", "State": "DOWN"})
        self.assertTrue(controller.closed)
        self.assertTrue(controller.preview.removed)
        self.assertEqual(4, len(removed))
        self.assertEqual(0, self.document.opened)

    def _capture_session(self):
        callbacks = {}
        removed = []
        snaps = []

        def add(kind, handler):
            token = (kind, len(callbacks))
            callbacks[kind] = handler
            return token

        self.view.addEventCallback = add
        self.view.removeEventCallback = lambda kind, token: removed.append((kind, token))

        def snap(position, lastpoint=None, active=False):
            snaps.append((position, lastpoint, active))
            return Vector(10, 20, 0)

        snapper = types.SimpleNamespace(
            show=lambda: removed.append(("snap", "show")),
            off=lambda: removed.append(("snap", "off")), snap=snap)
        self.module.Gui.Snapper = snapper
        controller = self.controller()
        controller.start_capture(lambda: 10, lambda: 0)
        return controller, callbacks, removed, snaps

    def test_snap_feedback_runs_before_first_point(self):
        controller, callbacks, _removed, snaps = self._capture_session()
        position = (42, 77)
        callbacks["SoLocation2Event"]({"Position": position})
        self.assertEqual(1, len(snaps))
        self.assertEqual((position, None, True), snaps[0])
        self.assertEqual([], controller.preview.outlines)
        callbacks["SoMouseButtonEvent"]({
            "Position": position, "State": "DOWN", "Button": "BUTTON1"})
        self.assertEqual((position, None, True), snaps[1])
        self.assertEqual([(10.0, 20.0)], controller.points)
        callbacks["SoLocation2Event"]({"Position": position})
        self.assertIsNotNone(snaps[-1][1])
        controller.cancel()

    def test_cancel_is_idempotent_and_late_callbacks_are_inert(self):
        for count in (0, 1, 3):
            with self.subTest(points=count):
                controller, callbacks, removed, snaps = self._capture_session()
                for index in range(count):
                    controller.add_point((index * 10, index * 5, 0))
                controller.cancel()
                controller.cancel()
                self.assertTrue(controller.closed)
                self.assertEqual(1, controller.preview.remove_calls)
                self.assertEqual(3, len([item for item in removed
                                         if item[0] != "snap"]))
                self.assertEqual(1, removed.count(("snap", "off")))
                before = len(snaps)
                for callback in callbacks.values():
                    callback({"Position": (1, 2), "Key": "ESCAPE",
                              "State": "DOWN", "Button": "BUTTON1"})
                self.assertEqual(before, len(snaps))
                self.assertEqual(0, self.document.opened)

    def test_escape_inactivates_immediately_and_new_session_starts(self):
        for count in (0, 1, 3):
            with self.subTest(points=count):
                controller, callbacks, removed, snaps = self._capture_session()
                for index in range(count):
                    controller.add_point((index * 10, index * 5, 0))
                requests = []
                controller.on_cancel = lambda: requests.append(controller.cancel)
                callbacks["SoKeyboardEvent"]({"Key": "ESCAPE", "State": "DOWN"})
                self.assertTrue(controller.closed)
                self.assertEqual(1, len(requests))
                callbacks["SoLocation2Event"]({"Position": (1, 2)})
                callbacks["SoMouseButtonEvent"]({
                    "Position": (1, 2), "State": "DOWN", "Button": "BUTTON1"})
                callbacks["SoKeyboardEvent"]({"Key": "ESCAPE", "State": "DOWN"})
                self.assertEqual([], snaps)
                self.assertEqual(1, len(requests))
                requests[0]()
                self.assertEqual(1, controller.preview.remove_calls)
                self.assertEqual(3, len([item for item in removed
                                         if item[0] != "snap"]))
                next_controller, next_callbacks, _removed, next_snaps = self._capture_session()
                next_callbacks["SoLocation2Event"]({"Position": (7, 8)})
                self.assertEqual(1, len(next_snaps))
                for point in ((0, 0, 0), (10, 0, 0), (0, 10, 0)):
                    next_controller.add_point(point)
                next_controller.close_outline()
                self.assertIsNotNone(next_controller.create(6, 0))
                self.assertEqual(1, next_controller.preview.remove_calls)

    def test_preselected_source_uses_no_points_and_snapshot_or_link(self):
        source = types.SimpleNamespace(
            kind="wire", vertices=((0, 0), (2, 0), (1, 1)),
            ViewObject=types.SimpleNamespace(Visibility=True))
        controller = self.module.PlateController(
            self.document, source=source, source_mode="DraftWire", view=self.view)
        self.assertEqual((), tuple(controller.points))
        controller.create(5, 0, keep_source_link=True)
        self.assertTrue(self.created[-1].kwargs["keep_source_link"])
        self.assertFalse(source.ViewObject.Visibility)
        source.ViewObject.Visibility = True
        snapshot = self.module.PlateController(
            self.document, source=source, source_mode="DraftWire", view=self.view)
        snapshot.create(5, 0, keep_source_link=False)
        self.assertFalse(self.created[-1].kwargs["keep_source_link"])

    def test_draft_selection_uses_whole_object_even_when_face_is_selected(self):
        source = types.SimpleNamespace(kind="rectangle", Document=self.document)
        selection = types.SimpleNamespace(Object=source, SubElementNames=["Face1"])
        self.assertEqual((source, "DraftRectangle"),
                         self.module.selected_plate_source([selection], self.document))

    def test_failed_creation_aborts_and_keeps_session_for_correction(self):
        controller = self.controller()
        for point in ((0, 0, 0), (10, 0, 0), (0, 10, 0)):
            controller.add_point(point)
        controller.close_outline()
        def fail(*_args, **_kwargs):
            raise ValueError("invalid shape")
        controller._factory = fail
        with self.assertRaisesRegex(ValueError, "invalid shape"):
            controller.create(10, 0)
        self.assertEqual((1, 0, 1),
                         (self.document.opened, self.document.committed,
                          self.document.aborted))
        self.assertFalse(controller.closed)
        self.assertFalse(controller.preview.removed)


if __name__ == "__main__":
    unittest.main()
