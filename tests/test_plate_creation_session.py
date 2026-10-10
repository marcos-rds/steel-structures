"""Regression gates for advanced-panel replacement and native owner teardown."""

import importlib.util
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, call, patch


SESSION = (Path(__file__).resolve().parents[1] / "freecad" / "SteelStructures"
           / "interactive" / "plate_creation_session.py")


class Document:
    def __init__(self):
        self.dead = False

    @property
    def Name(self):
        if self.dead:
            raise ReferenceError("The original document wrapper was deleted")
        return "PlateDocument"


class Combo:
    def __init__(self):
        self.items = []
        self.index = -1
        self.blocked = False

    def addItem(self, label, data):
        self.items.append((label, data))

    def findData(self, data):
        return next((i for i, item in enumerate(self.items) if item[1] == data), -1)

    def setCurrentIndex(self, index):
        self.index = index

    def blockSignals(self, blocked):
        previous, self.blocked = self.blocked, blocked
        return previous

    def setToolTip(self, text):
        self.tooltip = text

    def currentData(self):
        return self.items[self.index][1] if self.index >= 0 else None


class PlateCreationSessionTests(unittest.TestCase):
    def setUp(self):
        self.document = Document()
        self.view = types.SimpleNamespace(removeEventCallback=Mock())
        self.documents = {self.document.Name: self.document}
        self.closed = []
        self.timers = []
        self.removed_observers = []
        self.app = types.ModuleType("FreeCAD")
        self.app.listDocuments = lambda: self.documents
        self.app.activeDraftCommand = None
        self.app.removeDocumentObserver = self.removed_observers.append
        self.app.Console = types.SimpleNamespace(PrintError=Mock())
        self.gui = types.ModuleType("FreeCADGui")
        self.gui.getDocument = lambda name: types.SimpleNamespace(
            mdiViewsOfType=lambda kind: [self.view])
        self.gui.Control = types.SimpleNamespace(closeDialog=Mock(), activeDialog=lambda: True)
        self.gui.Snapper = types.SimpleNamespace(off=Mock())
        qt = types.ModuleType("PySide")
        qt.QtCore = types.SimpleNamespace(
            QObject=object,
            QTimer=types.SimpleNamespace(singleShot=lambda delay, callback: self.timers.append(callback)),
            QEvent=types.SimpleNamespace(Close=19, Hide=18))
        qt.QtWidgets = types.SimpleNamespace()
        shiboken = types.ModuleType("shiboken6")
        # Native shiboken accepts arbitrary Python values, including None.
        # Thus isValid by itself does not prove that a QWidget exists.
        self.is_valid = Mock(return_value=True)
        shiboken.isValid = self.is_valid
        draftutils = types.ModuleType("draftutils")
        draftutils.__path__ = []
        gui_utils = types.ModuleType("draftutils.gui_utils")
        gui_utils.get_3d_view = lambda: self.view
        modules = {
            "FreeCAD": self.app, "FreeCADGui": self.gui,
            "PySide": qt, "shiboken6": shiboken,
            "draftutils": draftutils, "draftutils.gui_utils": gui_utils,
        }
        self.module_patch = patch.dict(sys.modules, modules)
        self.module_patch.start()
        self.addCleanup(self.module_patch.stop)
        spec = importlib.util.spec_from_file_location("_session_advanced_tests.plate_creation_session", SESSION)
        self.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.module)
        self.session = self.module.PlateCreationSession(self.document, on_closed=self.closed.append)

    def _advanced_panel(self):
        controller = types.SimpleNamespace(
            closed=False, _capturing=True,
            _callbacks=[("SoMouseButtonEvent", 17), ("SoKeyboardEvent", 21)],
            preview=types.SimpleNamespace(_scene=object()),
            on_change=object(), on_error=object(), on_cancel=object(),
            numeric_editing=object(), cancel=Mock())
        panel = types.SimpleNamespace(
            form=None, controller=controller,
            reject=Mock(side_effect=AssertionError("An absent form must not read Qt widgets")))
        self.session.panel = panel
        return panel

    def test_legacy_closed_with_none_form_releases_owner_and_preserves_foreign_dialog(self):
        panel = self._advanced_panel()
        self.app.activeDraftCommand = object()
        session = self.session
        session._advanced_observer = True
        signal = types.SimpleNamespace(disconnect=Mock())
        session._mdi = types.SimpleNamespace(subWindowActivated=signal)
        owner_window = types.SimpleNamespace(removeEventFilter=Mock())
        task_box = types.SimpleNamespace(removeEventFilter=Mock())
        session._owner_window, session._advanced_box = owner_window, task_box

        session._legacy_closed(panel, False)

        self.assertIsNone(session.panel)
        self.assertTrue(session._closed)
        self.assertEqual(self.closed, [session])
        self.assertEqual(self.removed_observers, [session])
        signal.disconnect.assert_called_once_with(session._advanced_view_changed)
        owner_window.removeEventFilter.assert_called_once_with(session)
        task_box.removeEventFilter.assert_called_once_with(session)
        self.gui.Control.closeDialog.assert_not_called()
        self.assertNotIn(None, [call.args[0] for call in self.is_valid.call_args_list])

    def test_finish_with_none_form_cancels_controller_and_notifies_without_qt_reads(self):
        panel = self._advanced_panel()
        self.session.finish()

        panel.reject.assert_not_called()
        panel.controller.cancel.assert_called_once_with()
        for attribute in ("on_change", "on_error", "on_cancel", "numeric_editing"):
            self.assertIsNone(getattr(panel.controller, attribute))
        self.assertIsNone(self.session.panel)
        self.assertEqual(self.closed, [self.session])
        self.gui.Control.closeDialog.assert_not_called()
        self.assertEqual(self.is_valid.call_args_list, [])
        self.session.finish()
        panel.controller.cancel.assert_called_once_with()
        self.assertEqual(self.closed, [self.session])

    def test_dead_document_uses_captured_name_and_never_accesses_old_view_or_scene(self):
        panel = self._advanced_panel()
        self.document.dead = True
        self.documents.clear()
        self.gui.getDocument = Mock(side_effect=AssertionError("Dead document view must not be queried"))

        self.assertFalse(self.session._owner_alive())
        self.session.finish()

        self.gui.getDocument.assert_not_called()
        self.view.removeEventCallback.assert_not_called()
        self.assertFalse(panel.controller._capturing)
        self.assertEqual(panel.controller._callbacks, [])
        self.assertIsNone(panel.controller.preview._scene)
        panel.controller.cancel.assert_called_once_with()
        self.assertIsNone(self.session.panel)
        self.assertEqual(self.closed, [self.session])

    def test_foreign_draft_owner_detaches_old_callbacks_without_stopping_its_snapper(self):
        panel = self._advanced_panel()
        foreign_tool = object()
        self.app.activeDraftCommand = foreign_tool
        scene = panel.controller.preview._scene

        self.session.finish()

        self.assertEqual(self.view.removeEventCallback.call_args_list,
                         [call("SoMouseButtonEvent", 17), call("SoKeyboardEvent", 21)])
        self.assertFalse(panel.controller._capturing)
        self.assertEqual(panel.controller._callbacks, [])
        self.assertIs(panel.controller.preview._scene, scene)
        self.assertIs(self.app.activeDraftCommand, foreign_tool)
        self.gui.Snapper.off.assert_not_called()
        self.gui.Control.closeDialog.assert_not_called()
        panel.controller.cancel.assert_called_once_with()
        self.assertEqual(self.closed, [self.session])

    def test_plane_selector_options_follow_shape_and_valid_preselection(self):
        for shape, advanced, face, expected in (
                ("Polygon", False, None, ["WorkPlane", "Face", "Auto"]),
                ("Polygon", False, object(), ["WorkPlane", "Face", "Auto"]),
                ("Rectangle", False, None, ["WorkPlane", "Face"]),
                ("Rectangle", False, object(), ["WorkPlane", "Face"]),
                ("Rectangle", True, None, ["WorkPlane", "Face", "Auto"])):
            with self.subTest(shape=shape, advanced=advanced, face=face is not None):
                self.session.shape, self.session._advanced = shape, advanced
                self.session.plane_face = face
                self.session.plane = "Face" if face is not None else "Auto" if advanced else "WorkPlane"
                combo = Combo()
                self.session.configure_plane_combo(combo)
                self.assertEqual([data for _label, data in combo.items], expected)
                self.assertEqual(combo.currentData(), self.session.plane)
                if "Auto" in expected:
                    self.assertEqual(combo.items[combo.findData("Auto")][0], "Automático — pelos pontos 3D")
                if face is not None:
                    self.assertEqual(combo.items[combo.findData("Face")][0], "Face do modelo")

    def _native_tool(self, points=()):
        self.session.shape = "Polygon"
        shape = Combo()
        for data in ("Polygon", "Rectangle"):
            shape.addItem(data, data)
        shape.setCurrentIndex(0)
        plane = Combo()
        self.session.configure_plane_combo(plane)
        tool = types.SimpleNamespace(
            node=list(points), is_active=lambda: True, shape_combo=shape, plane_combo=plane,
            options=types.SimpleNamespace(status=types.SimpleNamespace(setText=Mock()),
                                          reverse=types.SimpleNamespace(isChecked=lambda: True),
                                          thickness=types.SimpleNamespace(value=lambda: 7),
                                          offset=types.SimpleNamespace(value=lambda: -2)))
        tool.finish = Mock(side_effect=lambda: self.session._tool_closed(tool))
        self.session.tool = tool
        return tool

    def _selectable_panel(self, point_count=0, contour=None):
        self.session.shape, self.session.plane = "Polygon", "Auto"
        mode = Combo()
        for data in ("InteractivePolygon", "InteractiveRectangle"):
            mode.addItem(data, data)
        mode.setCurrentIndex(0)
        plane = Combo()
        self.session.configure_plane_combo(plane)
        panel = types.SimpleNamespace(
            _closed=False, _closing=False, form=None, mode=mode, plane_mode=plane,
            controller=types.SimpleNamespace(point_count=point_count, contour=contour, closed=False),
            thickness=types.SimpleNamespace(value=lambda: 7),
            reverse=types.SimpleNamespace(isChecked=lambda: True),
            offset=types.SimpleNamespace(value=lambda: -2), _show_error=Mock())
        panel.reject = Mock(side_effect=lambda: self.session._legacy_closed(panel, False))
        self.session.panel = panel
        return panel

    def test_native_to_auto_finishes_before_queuing_3d_acquisition(self):
        tool = self._native_tool()
        self.session._start_advanced = Mock()
        self.gui.Control.activeDialog = lambda: False
        self.session._change(tool, plane="Auto")
        tool.finish.assert_called_once_with()
        self.assertIsNone(self.session.tool)
        self.assertEqual((self.session.thickness, self.session.offset), (7, -2))
        self.session._start_advanced.assert_not_called()
        self.assertEqual(len(self.timers), 1)
        self.timers.pop()()
        self.session._start_advanced.assert_called_once_with()
        self.assertFalse(self.session._advanced)  # Auto polygon is a direct plane choice.

    def test_native_plane_switch_with_points_rolls_back_without_discard(self):
        tool = self._native_tool(points=[object()])
        tool.plane_combo.setCurrentIndex(tool.plane_combo.findData("Auto"))
        self.session._change(tool, plane="Auto")
        self.assertEqual(tool.plane_combo.currentData(), "WorkPlane")
        self.assertEqual(len(tool.node), 1)
        tool.finish.assert_not_called()
        self.assertFalse(self.timers)

    def test_3d_plane_switch_with_pending_points_or_closed_contour_preserves_trace(self):
        for count, contour in ((1, None), (2, None), (4, None), (3, object())):
            with self.subTest(count=count, contour=contour is not None):
                panel = self._selectable_panel(count, contour)
                panel.plane_mode.setCurrentIndex(panel.plane_mode.findData("WorkPlane"))
                self.session._change_panel(plane="WorkPlane")
                self.assertEqual(panel.plane_mode.currentData(), "Auto")
                self.assertEqual(panel.controller.point_count, count)
                self.assertIs(panel.controller.contour, contour)
                panel.reject.assert_not_called()
                panel._show_error.assert_called_once()
                self.assertFalse(self.timers)

    def test_3d_shape_switch_with_points_rolls_back(self):
        panel = self._selectable_panel(1)
        panel.mode.setCurrentIndex(1)
        self.session._change_panel(shape="Rectangle")
        self.assertEqual(panel.mode.currentData(), "InteractivePolygon")
        self.assertEqual(self.session.shape, "Polygon")
        panel.reject.assert_not_called()

    def test_auto_to_native_plane_preserves_properties_and_queues_after_teardown(self):
        for plane in ("WorkPlane", "Face"):
            with self.subTest(plane=plane):
                self.session.plane_face = object() if plane == "Face" else None
                panel = self._selectable_panel()
                self.session._change_panel(plane=plane)
                panel.reject.assert_called_once_with()
                self.assertIsNone(self.session.panel)
                self.assertEqual(self.session.plane, plane)
                self.assertEqual((self.session.thickness, self.session.offset), (7, -2))
                self.assertFalse(self.session._advanced)
                self.assertEqual(len(self.timers), 1)
                self.timers.clear()

    def test_auto_to_rectangle_selects_common_2p_work_plane(self):
        self._selectable_panel()
        self.session._change_panel(shape="Rectangle")
        self.assertEqual((self.session.shape, self.session.plane), ("Rectangle", "WorkPlane"))
        self.assertFalse(self.session._advanced)

    def test_explicit_restart_preserves_auto_plane_and_3p_choice(self):
        panel = self._selectable_panel(3, object())
        self.session.shape, self.session._advanced = "Rectangle", True
        self.session._restart_panel_trace()
        panel.reject.assert_called_once_with()
        self.assertEqual((self.session.shape, self.session.plane, self.session._advanced),
                         ("Rectangle", "Auto", True))
        self.assertEqual(len(self.timers), 1)

    def test_3d_capture_without_active_mdi_window_keeps_document_and_view_observers(self):
        for has_mdi in (True, False):
            with self.subTest(has_mdi=has_mdi):
                controller = types.SimpleNamespace(set_mode=Mock())
                form = Mock()
                form.layout.return_value.count.return_value = 4
                form.inherits.return_value = False
                form.parentWidget.return_value = None
                panel = types.SimpleNamespace(input_form=form, thickness=Mock(), offset=Mock(), reverse=Mock(), clear_button=Mock())
                controller_type, panel_type = Mock(return_value=controller), Mock(return_value=panel)
                mdi = Mock() if has_mdi else None
                if mdi is not None:
                    mdi.activeSubWindow.return_value = None
                self.gui.getMainWindow = lambda: types.SimpleNamespace(findChild=lambda _kind: mdi)
                self.gui.Control.showDialog = Mock()
                self.app.addDocumentObserver = Mock()
                self.module.QtWidgets.QMdiArea = object
                self.module.QtWidgets.QPushButton = Mock()
                package = types.ModuleType("_session_advanced_tests")
                package.__path__ = []
                wp = Mock()
                modules = {
                    "_session_advanced_tests": package,
                    "_session_advanced_tests.plate_controller": types.SimpleNamespace(PlateController=controller_type),
                    "_session_advanced_tests.plate_task_panel": types.SimpleNamespace(PlateTaskPanel=panel_type),
                    "WorkingPlane": types.SimpleNamespace(get_working_plane=wp),
                }
                with patch.dict(sys.modules, modules):
                    self.session._start_advanced()
                self.assertIsNone(self.session._owner_window)
                self.app.addDocumentObserver.assert_called_once_with(self.session)
                self.gui.Control.showDialog.assert_called_once_with(panel)
                if mdi is not None:
                    mdi.subWindowActivated.connect.assert_called_once_with(self.session._advanced_view_changed)
                self.assertTrue(self.session._advanced_observer)
                wp.assert_called_once_with(update=False)
                self.assertEqual(controller_type.call_args.kwargs["plane_mode"], "Auto")
                self.assertIsNone(controller_type.call_args.kwargs["plane_face"])

    def test_select_face_blocks_started_trace_and_preserves_engine(self):
        tool = self._native_tool(points=[object()])
        self.session.select_face()
        self.assertFalse(self.session._picking_face)
        tool.finish.assert_not_called()
        self.session.tool = None
        panel = self._selectable_panel(1)
        self.session.select_face()
        self.assertFalse(self.session._picking_face)
        panel.reject.assert_not_called()

    def test_select_face_finishes_acquisition_before_picker_can_start(self):
        tool = self._native_tool()
        self.session.select_face()
        tool.finish.assert_called_once_with()
        self.assertIsNone(self.session.tool)
        self.assertTrue(self.session._picking_face)
        self.assertIsNone(self.session.face_picker)
        self.assertEqual(len(self.timers), 1)
        self.assertTrue(self.session.reverse_extrusion)

    def test_late_face_and_restart_buttons_cannot_change_replacement_trace(self):
        stale = self._selectable_panel()
        current = self._selectable_panel(3, object())
        self.session.select_face(stale)
        self.session._restart_panel_trace(stale)
        self.assertIs(self.session.panel, current)
        self.assertEqual(current.controller.point_count, 3)
        current.reject.assert_not_called()
        self.assertFalse(self.session._picking_face)
        self.assertFalse(self.timers)
        self.session.panel = None
        tool = self._native_tool()
        self.session.select_face(stale)
        tool.finish.assert_not_called()

    def test_face_acceptance_snapshots_plane_then_defers_native_restart(self):
        picker, reference, placement = object(), object(), object()
        self.app.Placement = Mock(return_value="copied_frame")
        self.session.face_picker = picker
        self.session._picking_face = True
        self.session._face_closed(picker, reference, placement)
        self.app.Placement.assert_called_once_with(placement)
        self.assertEqual(self.session._plane_placement, "copied_frame")
        self.assertIs(self.session.plane_face, reference)
        self.assertEqual(self.session.plane, "Face")
        self.assertIsNone(self.session.face_picker)
        self.assertFalse(self.session._picking_face)
        self.assertEqual(len(self.timers), 1)

    def test_face_plane_without_reference_waits_without_changing_previous_plane(self):
        tool = self._native_tool()
        self.session._change(tool, plane="Face")
        self.assertTrue(self.session._picking_face)
        self.assertEqual(self.session.plane, "WorkPlane")
        self.assertIsNone(self.session.tool)
        self.assertEqual(len(self.timers), 1)

    def test_cancel_face_choice_resumes_previous_plane_and_keeps_frame(self):
        picker, frame, reference = object(), object(), object()
        self.session.face_picker = picker
        self.session._plane_placement, self.session.plane_face = frame, reference
        self.session.plane = "Face"
        self.session._face_closed(picker, None, None)
        self.assertFalse(self.session._closed)
        self.assertEqual(self.session.plane, "Face")
        self.assertIs(self.session._plane_placement, frame)
        self.assertIs(self.session.plane_face, reference)
        self.assertEqual(len(self.timers), 1)

    def test_face_description_identifies_object_and_subelement(self):
        self.session.plane_face = types.SimpleNamespace(
            parent=types.SimpleNamespace(Label="StructuralMember"), subelement="Face18")
        self.assertEqual(self.session.face_description(), "StructuralMember — Face18")

    def test_buttons_during_deferred_cancel_cannot_reopen_capture(self):
        tool = self._native_tool()
        tool.is_active = lambda: False
        self.session.select_face(tool)
        tool.finish.assert_not_called()
        self.assertFalse(self.session._picking_face)
        self.session.tool = None
        for attribute in ("_closed", "_closing", "controller.closed"):
            with self.subTest(attribute=attribute):
                panel = self._selectable_panel()
                if attribute == "controller.closed":
                    panel.controller.closed = True
                else:
                    setattr(panel, attribute, True)
                self.session.select_face(panel)
                self.session._restart_panel_trace(panel)
                panel.reject.assert_not_called()
                self.assertFalse(self.session._picking_face)
                self.assertFalse(self.session._pending)
                self.assertFalse(self.timers)


if __name__ == "__main__":
    unittest.main()
