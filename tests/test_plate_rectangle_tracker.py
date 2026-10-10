"""Exercise the local tracker constructor with controlled Coin/Draft modules."""

import importlib.util
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch


SOURCE = (Path(__file__).resolve().parents[1] / "freecad" / "SteelStructures"
          / "interactive" / "plate_rectangle_tracker.py")


class Field:
    def __init__(self):
        self.calls = []
        self.values = []

    def setValue(self, value):
        self.values = value

    def setValues(self, *args):
        self.calls.append(args)
        if len(args) == 3:
            start, count, values = args
            if start != 0 or count != len(values):
                raise AssertionError("Explicit Coin count must match the supplied vectors")
        else:
            values, = args
        self.values = [list(value) if isinstance(value, list) else value for value in values]

    def getNum(self):
        return len(self.values)


class PlateRectangleTrackerTests(unittest.TestCase):
    def setUp(self):
        self.native_constructor_calls = []
        self.plane = types.SimpleNamespace(u=object(), v=object())
        harness = self

        class Tracker:
            def __init__(self, dotted, color, width, children, name):
                self.base_arguments = dotted, color, width, children, name

            def _get_wp(self):
                return harness.plane

            def on(self):
                self.visible = True

            def off(self):
                self.visible = False

            def finalize(self):
                self.finalized = True

            def get_scene_graph(self):
                return "native scene"

        class NativeRectangleTracker(Tracker):
            def __init__(self, *args, **kwargs):
                harness.native_constructor_calls.append((args, kwargs))
                raise AssertionError("Unsafe native rectangle constructor was invoked")

            def update(self, point):
                self.updated = point

            def setorigin(self, point):
                self.origin = point

            def setPlane(self, u, v=None):
                self.u, self.v = u, v

        self.native_rectangle = NativeRectangleTracker
        self.native_tracker = Tracker
        self.trackers = types.ModuleType("draftguitools.gui_trackers")
        self.trackers.rectangleTracker = NativeRectangleTracker
        self.trackers.Tracker = Tracker
        self.trackers.coin = types.SimpleNamespace(
            SoLineSet=lambda: types.SimpleNamespace(numVertices=Field()),
            SoCoordinate3=lambda: types.SimpleNamespace(point=Field()),
            SoMaterial=lambda: types.SimpleNamespace(transparency=Field(), diffuseColor=Field()),
            SoIndexedFaceSet=lambda: types.SimpleNamespace(coordIndex=Field()))
        draftguitools = types.ModuleType("draftguitools")
        draftguitools.__path__ = []
        draftguitools.gui_trackers = self.trackers
        app = types.ModuleType("FreeCAD")
        app.Vector = lambda *args: args
        module_name = "_plate_rectangle_tracker_test"
        spec = importlib.util.spec_from_file_location(module_name, SOURCE)
        self.module = importlib.util.module_from_spec(spec)
        module_patch = patch.dict(sys.modules, {
            "FreeCAD": app, "draftguitools": draftguitools,
            "draftguitools.gui_trackers": self.trackers, module_name: self.module})
        module_patch.start()
        self.addCleanup(module_patch.stop)
        spec.loader.exec_module(self.module)

    def test_constructor_copies_exactly_five_vectors_and_preserves_wp_and_options(self):
        tracker = self.module.PlateRectangleTracker(dotted=True, scolor="steel", swidth=2.5)
        points = [[0, 0, 0], [2, 0, 0], [2, 2, 0], [0, 2, 0], [0, 0, 0]]
        self.assertEqual(tracker.coords.point.calls, [(0, 5, points)])
        self.assertEqual(tracker.coords.point.getNum(), 5)
        self.assertEqual(tracker.coords.point.values, points)
        dotted, color, width, children, name = tracker.base_arguments
        self.assertEqual((dotted, color, width, name), (True, "steel", 2.5, "rectangleTracker"))
        self.assertEqual(len(children), 2)
        self.assertIs(children[0], tracker.coords)
        self.assertEqual(children[1].numVertices.values, 5)
        self.assertEqual(tracker.origin, (0, 0, 0))
        self.assertIs(tracker.u, self.plane.u)
        self.assertIs(tracker.v, self.plane.v)
        self.assertEqual(self.native_constructor_calls, [])

    def test_face_constructor_keeps_native_material_and_four_face_indices(self):
        tracker = self.module.PlateRectangleTracker(face=True)
        children = tracker.base_arguments[3]
        self.assertEqual(len(children), 4)
        material, polygon = children[2:]
        self.assertEqual(material.transparency.values, 0.5)
        self.assertEqual(material.diffuseColor.values, [0.5, 0.5, 1.0])
        self.assertEqual(polygon.coordIndex.calls, [([0, 1, 2, 3],)])
        self.assertEqual(tracker.coords.point.getNum(), 5)
        self.assertEqual(self.native_constructor_calls, [])

    def test_only_constructor_is_specialized_and_draft_globals_are_unchanged(self):
        local = self.module.PlateRectangleTracker
        tracker = local()
        self.assertIsInstance(tracker, self.native_rectangle)
        for name in ("update", "setorigin", "setPlane"):
            self.assertIs(getattr(local, name), getattr(self.native_rectangle, name))
        for name in ("on", "off", "finalize", "get_scene_graph", "_get_wp"):
            self.assertIs(getattr(local, name), getattr(self.native_tracker, name))
        point = object()
        tracker.update(point)
        self.assertIs(tracker.updated, point)
        tracker.off()
        tracker.finalize()
        self.assertFalse(tracker.visible)
        self.assertTrue(tracker.finalized)
        self.assertIs(self.trackers.rectangleTracker, self.native_rectangle)
        self.assertIs(self.trackers.Tracker, self.native_tracker)
        self.assertEqual(self.native_constructor_calls, [])


if __name__ == "__main__":
    unittest.main()
