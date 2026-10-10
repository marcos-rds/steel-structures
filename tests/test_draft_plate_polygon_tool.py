"""Polygon semantics under controlled Draft modules; no duplicate rectangle suite."""
import math
import sys
import types
import unittest
from unittest.mock import patch

from tests import test_draft_plate_rectangle_tool as rectangle_harness


class DraftPlatePolygonTests(unittest.TestCase):
    def setUp(self):
        # Compose the existing fixture instead of inheriting its test methods.
        self.h = rectangle_harness.DraftPlateRectangleTests(
            "test_inherits_rectangle_and_point_ui_precedes_plate_options")
        self.addCleanup(self.h.doCleanups)
        self.h.setUp()
        vector = rectangle_harness.Vector

        def subtract(first, second):
            return vector(tuple(a - b for a, b in zip(first, second)))

        for name, value in (("sub", subtract), ("__sub__", subtract),
                            ("Length", property(lambda point: math.sqrt(sum(x * x for x in point))))):
            replacement = patch.object(vector, name, value, create=True)
            replacement.start()
            self.addCleanup(replacement.stop)
        self.h.ui.wireUi = self.h.ui.pointUi
        for name in ("finishButton", "orientWPButton", "undoButton", "wipeButton", "closeButton"):
            setattr(self.h.ui, name, rectangle_harness.Widget())
        self.previews = []

        def add_object(type_id, name):
            obj = types.SimpleNamespace(TypeId=type_id, Name=name)
            obj.ViewObject = types.SimpleNamespace(ShowInTree=True, visible=True)
            obj.ViewObject.hide = lambda: setattr(obj.ViewObject, "visible", False)
            self.h.document.Objects.append(obj)
            self.previews.append(obj)
            return obj

        self.h.document.addObject = add_object
        self.h.document.getObject = lambda name: next(
            (obj for obj in self.h.document.Objects if obj.Name == name), None)
        self.h.document.removeObject = lambda name: self.h.document.Objects.remove(
            self.h.document.getObject(name))
        sys.modules["draftutils.gui_utils"].format_object = lambda obj: None
        utils = types.ModuleType("draftutils.utils")
        utils.tolerance = lambda: 1e-7
        sys.modules["draftutils.utils"] = utils
        lines = types.ModuleType("draftguitools.gui_lines")
        harness = self.h
        self.native_draws = []
        native_draws = self.native_draws

        class Line(harness.creator):
            def action(self, event):
                harness.native_actions.append(event)
                if event.get("Key") == "ESCAPE":
                    self.finish()
                elif "point" in event:
                    self.point = event["point"]
                    self.node.append(self.point)
                    self.drawUpdate(self.point)

            def numericInput(self, x, y, z):
                harness.native_numeric.append((x, y, z))
                self.point = vector(x, y, z)
                self.node.append(self.point)
                self.drawUpdate(self.point)

            def drawUpdate(self, point):
                native_draws.append(point)
                self.obj.ViewObject.visible = True

            def undolast(self):
                self.node.pop()

            def update_hints(self):
                pass

            def finish(self, *args, **kwargs):
                raise AssertionError("Native Line.finish would create an intermediate Draft object")

        self.native_line = Line
        lines.Line = Line
        sys.modules["draftguitools.gui_lines"] = lines
        self.module = self.h._load("interactive.draft_plate_polygon_tool",
                                   rectangle_harness.PACKAGE / "interactive/draft_plate_polygon_tool.py")

    def activate(self):
        tool = self.module.StructuralPlatePolygonTool()
        tool.Activated()
        self.assertTrue(tool.is_active())
        return tool

    def points(self, tool, coordinates):
        for point in coordinates:
            tool.numericInput(*point)

    def test_action_states_follow_confirmed_vertices_and_full_clear(self):
        tool = self.activate()
        self.assertFalse(self.h.ui.undoButton.enabled)
        self.assertFalse(self.h.ui.wipeButton.enabled)
        self.assertFalse(self.h.ui.closeButton.enabled)
        tool.numericInput(0, 0, 0)
        self.assertTrue(self.h.ui.undoButton.enabled)
        self.assertTrue(self.h.ui.wipeButton.enabled)
        self.assertFalse(self.h.ui.closeButton.enabled)
        tool.numericInput(10, 0, 0)
        tool.numericInput(10, 10, 0)
        self.assertTrue(self.h.ui.closeButton.enabled)
        tool.undolast()
        self.assertFalse(self.h.ui.closeButton.enabled)
        tool.wipe()
        self.assertEqual(tool.node, [])
        self.assertFalse(self.h.ui.undoButton.enabled)
        self.assertFalse(self.h.ui.wipeButton.enabled)
        self.assertFalse(self.h.ui.closeButton.enabled)

    def test_open_finish_cancel_and_escape_never_create_plate_or_draft_wire(self):
        for end in ("open", "cancel", "escape"):
            with self.subTest(end=end):
                tool = self.activate()
                self.points(tool, ((0, 0, 0), (40, 0, 0), (20, 25, 0)))
                if end == "open":
                    tool.finish(closed=False)
                elif end == "cancel":
                    tool.ui.panel.reject()
                else:
                    tool.action({"Type": "SoKeyboardEvent", "Key": "ESCAPE"})
                self.h.flush()
                self.assertEqual(tool._state, "FINISHED")
                self.assertEqual(self.h.created, [])
                self.assertEqual(self.h.document.Objects, [])

    def test_explicit_valid_close_creates_only_plate_and_removes_transient_preview(self):
        tool = self.activate()
        self.assertTrue(issubclass(type(tool), self.native_line))
        self.assertEqual(tool.mode, "wire")
        self.assertTrue(tool.ui.finishButton.hidden)
        self.assertTrue(tool.ui.orientWPButton.hidden)
        self.points(tool, ((0, 0, 0), (40, 0, 0), (20, 25, 0)))
        tool.finish(closed=True)
        self.h.flush()
        self.assertEqual(len(self.h.created), 1)
        self.assertEqual(self.h.created[0].source_mode, "InteractivePolygon")
        self.assertEqual(self.h.document.Objects, self.h.created)
        contour = self.h.geometry.PlateContour2D.from_data(self.h.created[0].ContourData)
        self.assertEqual(contour.area, 500)
        self.assertEqual(self.h.original_creations, 0)

    def test_invalid_closed_outline_retains_points_and_active_session(self):
        for points in (((0, 0, 0), (40, 0, 0)),
                       ((0, 0, 0), (40, 25, 0), (0, 25, 0), (40, 0, 0))):
            with self.subTest(points=points):
                tool = self.activate()
                self.points(tool, points)
                saved = list(tool.node)
                tool.finish(closed=True)
                self.assertTrue(tool.is_active())
                self.assertEqual(tool.node, saved)
                self.assertEqual(self.h.created, [])
                self.assertTrue(tool.options.status.text)
                tool.finish()
                self.h.flush()

    def test_repeating_first_point_too_early_never_discards_confirmed_points(self):
        for count in (1, 2):
            for method in ("numeric", "mouse"):
                with self.subTest(count=count, method=method):
                    tool = self.activate()
                    self.points(tool, ((0, 0, 0), (40, 0, 0))[:count])
                    saved = list(tool.node)
                    native_calls = len(self.h.native_actions)
                    if method == "numeric":
                        tool.numericInput(0, 0, 0)
                    else:
                        tool.point = rectangle_harness.Vector(0, 0, 0)
                        tool.action({"Type": "SoMouseButtonEvent", "State": "DOWN", "Button": "BUTTON1"})
                        self.assertEqual(len(self.h.native_actions), native_calls)
                    self.assertTrue(tool.is_active())
                    self.assertEqual(tool.node, saved)
                    self.assertEqual(self.h.created, [])
                    tool.finish()
                    self.h.flush()

    def test_repeated_first_point_closes_valid_polygon_without_appending_duplicate(self):
        for method in ("numeric", "mouse"):
            with self.subTest(method=method):
                tool = self.activate()
                self.points(tool, ((0, 0, 0), (40, 0, 0), (20, 25, 0)))
                if method == "numeric":
                    tool.numericInput(0, 0, 0)
                else:
                    tool.point = rectangle_harness.Vector(0, 0, 0)
                    tool.action({"Type": "SoMouseButtonEvent", "State": "DOWN", "Button": "BUTTON1"})
                self.h.flush()
                contour = self.h.geometry.PlateContour2D.from_data(self.h.created[-1].ContourData)
                self.assertEqual(len(contour.vertices), 3)
                self.assertEqual(tool._state, "FINISHED")

    def test_undo_single_point_and_clear_all_leave_trace_ready_for_reuse(self):
        tool = self.activate()
        self.points(tool, ((0, 0, 0),))
        tool.undolast()
        self.assertEqual(tool.node, [])
        self.assertFalse(tool.obj.ViewObject.visible)
        self.points(tool, ((0, 0, 0), (40, 0, 0), (20, 25, 0)))
        tool.undolast()
        self.assertEqual(len(tool.node), 2)
        tool.wipe()
        self.assertEqual(tool.node, [])
        self.assertIsNone(tool.point)
        self.assertFalse(tool.obj.ViewObject.visible)
        self.assertTrue(tool.is_active())
        self.assertEqual(self.h.created, [])

    def test_off_plane_nonfinite_and_consecutive_duplicate_rejected_before_native_draw(self):
        tool = self.activate()
        self.points(tool, ((0, 0, 0), (40, 0, 0)))
        for point in ((40, 0, 0), (20, 25, 0.1), (float("nan"), 20, 0),
                      (float("inf"), 20, 0)):
            with self.subTest(point=point):
                saved, draws = list(tool.node), len(self.native_draws)
                tool.numericInput(*point)
                self.assertEqual(tool.node, saved)
                self.assertEqual(len(self.native_draws), draws)
                self.assertTrue(tool.is_active())
                self.assertEqual(self.h.created, [])

    def test_stale_and_changed_view_callbacks_do_not_close_or_append_polygon(self):
        for method in ("numeric", "mouse"):
            with self.subTest(method=method):
                tool = self.activate()
                self.points(tool, ((0, 0, 0), (40, 0, 0)))
                self.h.active_view = rectangle_harness.View()
                numeric_calls = len(self.h.native_numeric)
                action_calls = len(self.h.native_actions)
                if method == "numeric":
                    tool.numericInput(0, 0, 0)
                else:
                    tool.point = rectangle_harness.Vector(0, 0, 0)
                    tool.action({"Type": "SoMouseButtonEvent", "State": "DOWN", "Button": "BUTTON1"})
                self.h.flush()
                tool.numericInput(20, 25, 0)
                tool.action({"point": rectangle_harness.Vector(20, 25, 0)})
                self.assertEqual(len(self.h.native_numeric), numeric_calls)
                self.assertEqual(len(self.h.native_actions), action_calls)
                self.assertEqual(self.h.created, [])
                self.assertEqual(tool._state, "FINISHED")
                self.h.active_view = self.h.view


if __name__ == "__main__":
    unittest.main()
