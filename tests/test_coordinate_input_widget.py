"""Native Qt tests; standalone Python skips them instead of simulating a GUI.

Run through tests/manual_plate_numeric_input.py in a real FreeCAD session.
"""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "freecad"))
try:
    import FreeCAD as App
    import FreeCADGui as Gui
    from PySide import QtCore, QtWidgets
    try:
        from PySide6 import QtTest
    except ImportError:
        from PySide2 import QtTest
    from SteelStructures.interactive.coordinate_input_widget import length_value
    from SteelStructures.interactive.plate_controller import PlateController
    from SteelStructures.interactive.plate_task_panel import PlateTaskPanel
    from SteelStructures.interactive.point_input import PointCandidate
    NATIVE = bool(App.GuiUp)
except ImportError:
    NATIVE = False


@unittest.skipUnless(NATIVE, "Real FreeCAD GUI / Qt event loop required")
class CoordinateInputWidgetTests(unittest.TestCase):
    def setUp(self):
        Gui.activateWorkbench("DraftWorkbench")
        self.doc = App.newDocument("NumericPlateQt")
        self.controller = PlateController(self.doc, placement=App.Placement())
        self.panel = PlateTaskPanel(self.controller,
                                    lambda _panel, _accepted: Gui.Control.closeDialog())
        Gui.Control.showDialog(self.panel)
        # Gates run with a hidden native main window. Qt otherwise keeps the
        # prior task's inactive focus widget and never delivers FocusOut/Tab to
        # the requested editor. Establish the same active-window prerequisite
        # as the native integrated acquisition tests.
        QtWidgets.QApplication.setActiveWindow(Gui.getMainWindow())
        QtWidgets.QApplication.processEvents()
        self.widget = self.panel.coordinate_input

    def tearDown(self):
        self.panel.reject()
        QtWidgets.QApplication.processEvents()
        if self.doc.Name in App.listDocuments():
            App.closeDocument(self.doc.Name)

    def fill(self, values):
        for field, value in zip(self.widget.fields, values):
            field.setText(str(value))

    def focus(self, widget):
        QtWidgets.QApplication.setActiveWindow(Gui.getMainWindow())
        widget.setFocus()
        QtWidgets.QApplication.processEvents()
        self.assertTrue(widget.hasFocus(), "Native focus prerequisite was not established")

    def add(self, values):
        self.fill(values)
        self.widget.confirm()

    def assertPoint(self, expected, actual):
        self.assertIsNotNone(actual)
        for a, b in zip(expected, actual):
            self.assertAlmostEqual(a, b, places=8)

    def test_units_negative_invalid_nonfinite_and_empty(self):
        for text, expected in (("-2 cm", -20), ("0.5 m", 500), ("3 mm", 3), ("4", 4)):
            self.assertAlmostEqual(expected, length_value(text))
        for text in ("", "-", "1e", "nan", "inf", "1 kg", "2 deg", "abc"):
            with self.subTest(text=text), self.assertRaises(ValueError):
                length_value(text)
        self.fill(("-2 cm", "0.5 m", "3 mm"))
        self.assertPoint((-20, 500, 3), self.controller.candidate.world)
        self.widget.confirm()
        self.assertPoint((-20, 500, 3), self.controller.last_point)

    def test_availability_no_plane_no_relative_and_after_first_direction(self):
        self.assertFalse(any(field.text() for field in self.widget.fields))
        self.assertFalse(self.widget.editing)
        self.assertFalse(self.widget.add_button.isEnabled())
        self.assertIsNone(self.controller.candidate)
        self.assertFalse(self.widget.global_coordinates.isEnabled())
        self.assertFalse(self.widget.relative.isEnabled())
        output = ROOT / "test-results"
        output.mkdir(exist_ok=True)
        self.panel.input_form.grab().save(str(output / "point_input_global.png"))
        self.add((0, 0, 8))
        self.assertTrue(self.widget.relative.isEnabled())
        self.assertFalse(self.widget.global_coordinates.isEnabled())
        self.add((10, 0, 8))
        self.assertEqual("FIRST_DIRECTION", self.controller.plane_state)
        self.assertFalse(self.widget.global_coordinates.isEnabled())
        self.add((10, 10, 8))
        self.assertTrue(self.widget.global_coordinates.isEnabled())
        self.assertEqual("PLANE_DEFINED", self.controller.plane_state)
        self.widget.global_coordinates.setChecked(False)
        self.panel.input_form.grab().save(str(output / "point_input_plane.png"))

    def test_coordinate_checkboxes_preserve_axis_and_origin_semantics(self):
        self.assertIsInstance(self.widget.relative, QtWidgets.QCheckBox)
        self.assertIsInstance(self.widget.global_coordinates, QtWidgets.QCheckBox)
        self.assertTrue(self.widget.global_coordinates.isChecked())
        self.assertFalse(self.widget.global_coordinates.isEnabled())
        self.assertFalse(self.widget.relative.isChecked())
        self.add((2, 3, 4))
        self.assertTrue(self.widget.relative.isEnabled())
        self.widget.relative.setChecked(True)
        self.fill(("-2 cm", "1 mm", "3 mm"))
        self.assertPoint((-18, 4, 7), self.controller.candidate.world)
        self.widget.confirm()
        self.assertPoint((-18, 4, 7), self.controller.last_point)

    def test_effective_xyz_labels_and_local_z_is_display_only(self):
        self.assertEqual(["X", "Y", "Z"], [label.text() for label in self.widget.labels])
        for point in ((2, 3, 4), (12, 3, 7), (15, 9, 8)):
            self.add(point)
        self.widget.relative.setChecked(True)
        self.assertEqual(["Global ΔX", "Global ΔY", "Global ΔZ"],
                         [label.text() for label in self.widget.labels])
        self.widget.global_coordinates.setChecked(False)
        self.assertEqual(["Local ΔX", "Local ΔY", "Local ΔZ"],
                         [label.text() for label in self.widget.labels])
        self.widget.relative.setChecked(False)
        self.assertEqual(["Local X", "Local Y", "Local Z"],
                         [label.text() for label in self.widget.labels])
        self.assertTrue(self.widget.fields[2].isReadOnly())
        self.assertFalse(self.widget.fields[2].isHidden())
        candidate = PointCandidate(tuple(self.controller.placement.multVec(App.Vector(20, 30, 0))))
        self.controller.set_candidate(candidate)
        self.assertPoint((20, 30, 0), [length_value(f.text()) for f in self.widget.fields])
        self.assertIs(candidate, self.controller.candidate)
        self.widget.confirm()
        self.assertPoint(candidate.world, self.controller.last_point)

    def test_field_metrics_and_theme_match_native_unit_editor(self):
        native = Gui.UiLoader().createWidget("Gui::InputField")
        native.setParent(self.panel.input_form)
        native.hide()
        try:
            for field in self.widget.fields:
                self.assertGreaterEqual(field.height(), native.sizeHint().height())
                self.assertEqual(field.font(), native.font())
                self.assertEqual(field.alignment(), native.alignment())
                self.assertEqual(field.textMargins(), native.textMargins())
                self.assertEqual(field.palette(), native.palette())
        finally:
            native.deleteLater()

    def test_native_properties_section_collapse_keeps_capture_and_footer(self):
        self.assertEqual([self.panel.input_form, self.panel.properties_form, self.panel.footer_form],
                         self.panel.form)
        def box(widget):
            while widget is not None and not widget.inherits("Gui::TaskView::TaskBox"):
                widget = widget.parentWidget()
            return widget
        properties = box(self.panel.properties_form)
        self.assertIsNotNone(properties)
        header = next(w for w in properties.findChildren(QtWidgets.QWidget)
                      if w.inherits("QSint::TaskHeader"))
        self.assertFalse(self.panel.properties_form.isHidden())
        callbacks = list(self.controller._callbacks)
        QtTest.QTest.mouseClick(header, QtCore.Qt.LeftButton)
        QtTest.QTest.qWait(700)
        self.assertFalse(self.panel.properties_form.isVisible())
        self.assertTrue(self.panel.status.isVisible())
        self.assertFalse(self.panel._closed)
        self.assertEqual(callbacks, self.controller._callbacks)
        QtTest.QTest.mouseClick(header, QtCore.Qt.LeftButton)
        QtTest.QTest.qWait(700)
        self.assertTrue(self.panel.properties_form.isVisible())
        footer = box(self.panel.footer_form)
        self.assertTrue(all(w.isHidden() for w in footer.findChildren(QtWidgets.QWidget)
                            if w.inherits("QSint::TaskHeader")))

    def test_defined_plane_ray_rejects_parallel_invalid_and_behind_eye(self):
        from types import SimpleNamespace
        for point in ((0, 0, 20), (10, 0, 20), (10, 10, 20)):
            self.add(point)
        original_view = self.controller._view
        view = SimpleNamespace(
            getPoint=lambda *_pixels: App.Vector(1, 2, 0),
            getCameraType=lambda: "Orthographic",
            getViewDirection=lambda: App.Vector(1, 0, 0),
            getCameraNode=lambda: SimpleNamespace(getField=lambda _name: SimpleNamespace(
                getValue=lambda: (0, 0, 10))))
        self.controller._view = view
        try:
            self.assertIsNone(self.controller._point_on_defined_plane((1, 2)))
            self.assertIsNone(self.controller._point_on_defined_plane((1, 2, 3)))
            view.getViewDirection = lambda: App.Vector(0, 0, 0)
            self.assertIsNone(self.controller._point_on_defined_plane((1, 2)))
            view.getViewDirection = lambda: App.Vector(0, 0, -1)
            view.getPoint = lambda *_pixels: App.Vector(float("nan"), 2, 0)
            self.assertIsNone(self.controller._point_on_defined_plane((1, 2)))
            view.getPoint = lambda *_pixels: App.Vector(1, 2, 0)
            view.getCameraType = lambda: "Perspective"
            self.assertIsNone(self.controller._point_on_defined_plane((1, 2)))
            self.assertEqual(3, self.controller.point_count)
        finally:
            self.controller._view = original_view

    def test_native_display_precision_never_rounds_confirmed_candidate(self):
        from SteelStructures.interactive.coordinate_input_widget import display_length
        parameters = App.ParamGet("User parameter:BaseApp/Preferences/Units")
        previous = parameters.GetInt("Decimals", 2)
        try:
            parameters.SetInt("Decimals", 2)
            candidate = PointCandidate((-1448.171234567891, 2.123456789123, 8.987654321))
            self.controller.set_candidate(candidate)
            self.widget.present_candidate(candidate)
            self.assertEqual(display_length(candidate.world[0]), self.widget.fields[0].text())
            self.assertNotIn("171234567891", self.widget.fields[0].text())
            self.assertIs(candidate, self.controller.candidate)
            self.widget.confirm()
            self.assertEqual(candidate.world, self.controller.last_point)
            second = PointCandidate((-1400.123456789123, 12.987654321, 10.123456789))
            self.controller.set_candidate(second)
            self.widget.present_candidate(second)
            for relative in (True, False, True):
                self.widget.relative.setChecked(relative)
                self.assertIs(second, self.controller.candidate)
                self.assertFalse(self.widget.editing)
            self.widget.confirm()
            self.assertEqual(second.world, self.controller.last_point)
        finally:
            parameters.SetInt("Decimals", previous)

    def test_preview_only_and_incomplete_text(self):
        self.add((0, 0, 8))
        self.fill(("10", "-", "8"))
        self.assertTrue(self.widget.editing)
        self.assertFalse(self.widget.add_button.isEnabled())
        self.assertIsNone(self.controller.candidate)
        self.widget.confirm()
        self.assertEqual(1, self.controller.point_count)
        self.widget.fields[1].setText("5")
        self.assertPoint((10, 5, 8), self.controller.candidate.world)
        self.assertEqual(1, self.controller.point_count)
        self.assertEqual("NO_PLANE", self.controller.plane_state)
        self.assertIsNone(self.controller.placement)
        self.panel.thickness.setValue(12)
        self.assertPoint((10, 5, 8), self.controller.candidate.world)

    def test_external_add_action_disables_with_unchanged_context_while_editing(self):
        self.fill(("10", "5", "8"))
        self.assertTrue(self.widget.editing)
        self.assertTrue(self.widget.add_button.isEnabled())
        # The unified panel places the action in its own grid. Disabling the
        # coordinate group must explicitly disable this separate child.
        self.widget.add_button.setParent(self.panel.input_form)
        context = self.widget._context
        self.widget.set_context(*context, available=False)
        self.assertFalse(self.widget.add_button.isEnabled())
        self.widget.present_candidate(PointCandidate((12, 5, 8)))
        self.assertFalse(self.widget.add_button.isEnabled())
        self.assertEqual(["10", "5", "8"], [f.text() for f in self.widget.fields])

    def test_empty_incomplete_and_exact_text_survive_tab_and_focus_out(self):
        field = self.widget.fields[0]
        for text in ("", "-", "1e", "0.123456789123 mm"):
            with self.subTest(text=text):
                self.focus(field)
                field.setText(text)
                QtTest.QTest.keyClick(field, QtCore.Qt.Key_Tab)
                self.assertTrue(self.widget.fields[1].hasFocus())
                self.assertEqual(text, field.text())
                self.assertEqual(0, self.controller.point_count)
                self.widget.confirm()
                self.assertEqual(0, self.controller.point_count)
        self.fill(("-", "2", "3"))
        self.focus(field)
        self.focus(self.panel.thickness)
        self.assertEqual("-", field.text())
        self.widget.confirm()
        self.assertEqual(0, self.controller.point_count)

    def test_hide_show_never_restores_previous_field_values(self):
        self.add((10, 20, 30))
        self.assertFalse(any(field.text() for field in self.widget.fields))
        self.widget.hide()
        self.widget.show()
        QtWidgets.QApplication.processEvents()
        self.assertFalse(any(field.text() for field in self.widget.fields))
        self.assertFalse(self.widget.editing)
        self.assertIsNone(self.controller.candidate)

    def test_tab_shift_tab_and_enter_once_without_dialog_accept(self):
        self.fill(("0", "0", "8"))
        field = self.widget.fields[0]
        self.focus(field)
        QtTest.QTest.keyClick(field, QtCore.Qt.Key_Tab)
        self.assertTrue(self.widget.fields[1].hasFocus())
        QtTest.QTest.keyClick(self.widget.fields[1], QtCore.Qt.Key_Backtab)
        self.assertTrue(field.hasFocus())
        QtTest.QTest.keyClick(field, QtCore.Qt.Key_Return)
        self.assertEqual(1, self.controller.point_count)
        self.assertFalse(self.panel._closed)
        self.assertEqual(0, len(self.doc.Objects))
        self.assertFalse(any(f.text() for f in self.widget.fields))
        # A subsequent Enter on empty fields cannot repeat the previous point.
        QtTest.QTest.keyClick(field, QtCore.Qt.Key_Return)
        self.assertEqual(1, self.controller.point_count)
        self.fill(("10", "0", "8"))
        QtTest.QTest.keyClick(field, QtCore.Qt.Key_Enter)
        self.assertEqual(2, self.controller.point_count)

    def test_enter_with_closed_polygon_does_not_create_plate(self):
        for point in ((0, 0, 8), (10, 0, 8), (10, 10, 8)):
            self.add(point)
        self.controller.close_outline()
        self.assertFalse(self.widget.isEnabled())
        self.assertTrue(self.panel.accept())
        self.assertEqual(1, len(self.doc.Objects))

    def test_local_escape_defers_teardown_and_late_signals_are_inert(self):
        field = self.widget.fields[0]
        self.focus(field)
        QtTest.QTest.keyClick(field, QtCore.Qt.Key_Escape)
        self.assertTrue(self.panel._closing)
        self.assertTrue(self.controller.closed)
        QtWidgets.QApplication.processEvents()
        self.assertTrue(self.panel._closed)
        self.assertTrue(self.controller._teardown_done)
        self.assertFalse(self.controller._callbacks)
        self.assertFalse(Gui.Control.activeDialog())
        self.panel._confirm_point(PointCandidate((1, 2, 3)))
        self.panel._candidate_changed(PointCandidate((1, 2, 3)))
        self.widget.confirm()
        self.widget._text_changed()
        self.widget._system_changed()
        self.assertEqual(0, len(self.doc.Objects))

    def test_reference_mode_roundtrip_preserves_world_inclined(self):
        for point in ((2, 3, 4), (12, 3, 7), (15, 9, 8)):
            self.add(point)
        expected = tuple(self.controller.placement.multVec(App.Vector(-5, 12, 0)))
        self.fill(expected)
        self.assertPoint(expected, self.controller.candidate.world)
        for reference, mode in ((1, 0), (1, 1), (0, 1), (0, 0)):
            self.widget.global_coordinates.setChecked(reference == 0)
            self.widget.relative.setChecked(mode == 1)
            self.assertPoint(expected, self.controller.candidate.world)
        self.widget.confirm()
        self.assertPoint(expected, self.controller.last_point)

    def test_graphical_candidate_reference_roundtrip(self):
        self.controller.set_plane_mode("WorkPlane")
        candidate = PointCandidate((12, -3, 0))
        self.controller.set_candidate(candidate)
        self.assertFalse(self.widget.editing)
        self.widget.global_coordinates.setChecked(False)
        self.assertEqual([12, -3], [length_value(f.text()) for f in self.widget.fields[:2]])
        self.widget.global_coordinates.setChecked(True)
        self.assertPoint(candidate.world, self.controller.candidate.world)

    def test_snap_presentation_updates_xyz_without_confirmation_or_input_signals(self):
        emitted = []
        self.widget.candidateChanged.connect(emitted.append)
        for expected in ((12, -3, 8), (-2, 14, 30)):
            candidate = PointCandidate(expected)
            self.controller.set_candidate(candidate)
            self.widget.present_candidate(candidate)
            self.assertPoint(expected, tuple(length_value(f.text()) for f in self.widget.fields))
            self.assertFalse(self.widget.editing)
            self.assertTrue(self.widget.add_button.isEnabled())
            self.assertEqual(0, self.controller.point_count)
        self.assertEqual([], emitted)
        self.widget.present_candidate(None)
        self.assertFalse(any(field.text() for field in self.widget.fields))
        self.assertFalse(self.widget.add_button.isEnabled())
        self.assertIn("snap 3D", self.widget.candidate_status.text())
        # Empty coordinates are neutral QLineEdits; no InputField invalid-value
        # decoration or quantity coercion is attached to this ordinary state.
        self.assertTrue(all(type(field) is QtWidgets.QLineEdit for field in self.widget.fields))

    def test_snap_does_not_replace_numeric_edit_and_focus_out_resumes_mouse(self):
        field = self.widget.fields[0]
        self.focus(field)
        self.fill(("-", "2", "3"))
        self.widget.present_candidate(PointCandidate((10, 20, 30)))
        self.assertEqual(["-", "2", "3"], [field.text() for field in self.widget.fields])
        self.assertTrue(self.widget.editing)
        self.focus(self.panel.thickness)
        self.assertFalse(self.widget.editing)
        self.assertEqual("-", field.text())
        self.widget.present_candidate(PointCandidate((10, 20, 30)))
        self.assertPoint((10, 20, 30), tuple(length_value(f.text()) for f in self.widget.fields))
        self.assertFalse(self.widget.editing)
        self.assertEqual(0, self.controller.point_count)

    def test_incomplete_text_survives_focus_out_then_checkbox_toggle(self):
        self.add((1, 2, 3))
        self.focus(self.widget.fields[0])
        self.fill(("-", "2", "3"))
        self.focus(self.widget.relative)
        self.assertFalse(self.widget.editing)
        self.widget.relative.setChecked(True)
        self.assertEqual(0, int(self.widget.relative.isChecked()))
        self.assertEqual(["-", "2", "3"], [field.text() for field in self.widget.fields])
        self.assertEqual(1, self.controller.point_count)

    def test_graphical_absolute_relative_toggle_never_locks_mouse_b1(self):
        self.add((1, 2, 3))
        first = PointCandidate((11, 22, 33))
        self.controller.set_candidate(first)
        self.widget.present_candidate(first)
        self.widget.relative.setChecked(True)
        self.assertFalse(self.widget.editing)
        self.assertPoint((10, 20, 30), tuple(length_value(f.text()) for f in self.widget.fields))
        second = PointCandidate((41, 52, 63))
        self.controller.set_candidate(second)
        self.widget.present_candidate(second)
        self.assertPoint((40, 50, 60), tuple(length_value(f.text()) for f in self.widget.fields))
        self.widget.relative.setChecked(False)
        self.assertFalse(self.widget.editing)
        self.assertPoint(second.world, tuple(length_value(f.text()) for f in self.widget.fields))
        self.assertEqual(1, self.controller.point_count)

    def test_snap_local_presentation_after_plane_preserves_world_candidate(self):
        for point in ((2, 3, 4), (12, 3, 7), (15, 9, 8)):
            self.add(point)
        expected = tuple(self.controller.placement.multVec(App.Vector(5, 8, 0)))
        candidate = PointCandidate(expected)
        self.controller.set_candidate(candidate)
        self.widget.present_candidate(candidate)
        self.widget.global_coordinates.setChecked(False)
        self.assertFalse(self.widget.editing)
        self.assertAlmostEqual(5, length_value(self.widget.fields[0].text()))
        self.assertAlmostEqual(8, length_value(self.widget.fields[1].text()))
        self.assertIs(candidate, self.controller.candidate)
        self.widget.confirm()
        self.assertPoint(expected, self.controller.last_point)

    def test_presentation_keeps_tolerated_normal_residual_through_confirm(self):
        self.controller.set_plane_mode("WorkPlane")
        candidate = PointCandidate((12, -3, 5e-6))
        self.controller.set_candidate(candidate)
        for reference in (1, 0, 1):
            self.widget.global_coordinates.setChecked(reference == 0)
            self.assertIs(candidate, self.controller.candidate)
        received = []
        original = self.controller.add_point

        def record(point, **kwargs):
            received.append(point)
            original(point, **kwargs)

        self.controller.add_point = record
        self.widget.confirm()
        self.assertEqual([candidate.world], received)

    def test_incomplete_edit_not_reinterpreted_or_automatically_switched(self):
        self.add((0, 0, 8))
        self.add((10, 0, 8))
        self.widget.fields[0].setText("-")
        self.controller.add_point((10, 10, 8))
        # A graphical confirmation is not possible through the live callback
        # while editing; direct controller changes prepare a fresh next editor.
        self.fill(("-", "2", "8"))
        self.widget.global_coordinates.setChecked(False)
        self.assertEqual(0, int(not self.widget.global_coordinates.isChecked()))
        self.assertEqual("-", self.widget.fields[0].text())
        self.widget.relative.setChecked(True)
        self.assertEqual(0, int(self.widget.relative.isChecked()))
        self.assertEqual(3, self.controller.point_count)

    def test_off_plane_global_rejected_preview_and_confirmation(self):
        for point in ((0, 0, 8), (10, 0, 8), (10, 10, 8)):
            self.add(point)
        self.fill((0, 10, 9))
        self.assertIsNone(self.controller.candidate)
        self.widget.confirm()
        self.assertEqual(3, self.controller.point_count)
        self.assertIn("fora do plano", self.panel.status.text())
        self.widget.global_coordinates.setChecked(False)
        self.assertEqual(0, int(not self.widget.global_coordinates.isChecked()))

    def test_reset_modes_and_empty_fields_resume_graphical_input(self):
        self.fill(("-", "", ""))
        self.assertTrue(self.widget.editing)
        self.panel.mode.setCurrentIndex(1)
        self.assertFalse(self.widget.editing)
        self.assertIsNone(self.controller.candidate)
        self.fill(("1", "2", "3"))
        for field in self.widget.fields:
            field.setText("")
        self.assertFalse(self.widget.editing)
        self.assertIsNone(self.controller.candidate)

    def test_repeated_open_cancel_then_draft_command(self):
        for _ in range(4):
            self.panel.reject()
            QtWidgets.QApplication.processEvents()
            self.controller = PlateController(self.doc, placement=App.Placement())
            self.panel = PlateTaskPanel(self.controller,
                                        lambda _panel, _accepted: Gui.Control.closeDialog())
            Gui.Control.showDialog(self.panel)
            QtWidgets.QApplication.processEvents()
            self.widget = self.panel.coordinate_input
            self.assertTrue(self.controller._capturing)
        self.panel.reject()
        QtWidgets.QApplication.processEvents()
        Gui.runCommand("Draft_Line")
        QtWidgets.QApplication.processEvents()
        self.assertTrue(Gui.Control.activeDialog())
        App.activeDraftCommand.finish()
        QtWidgets.QApplication.processEvents()
        self.assertFalse(Gui.Control.activeDialog())

    def test_draft_source_has_no_numeric_editor(self):
        import Draft
        self.panel.reject()
        source = Draft.make_rectangle(10, 20)
        self.doc.recompute()
        self.controller = PlateController(self.doc, source=source, source_mode="DraftRectangle")
        self.panel = PlateTaskPanel(self.controller,
                                    lambda _panel, _accepted: Gui.Control.closeDialog())
        Gui.Control.showDialog(self.panel)
        QtWidgets.QApplication.processEvents()
        self.assertIsNone(self.panel.coordinate_input)
        self.assertFalse(self.controller._capturing)

    def test_rectangle_three_numeric_and_two_with_plane(self):
        self.panel.mode.setCurrentIndex(1)
        self.add((2, 3, 4))
        self.widget.relative.setChecked(True)
        self.add((10, 0, 3))
        self.add((0, 8, 1))
        self.assertIsNotNone(self.controller.contour)
        self.assertEqual(4, len(self.controller.contour.vertices))
        self.panel.mode.setCurrentIndex(0)
        self.panel.plane_mode.setCurrentIndex(1)
        self.panel.mode.setCurrentIndex(1)
        self.widget.global_coordinates.setChecked(False)
        self.add((2, 3))
        self.widget.relative.setChecked(True)
        self.add((10, -8))
        self.assertAlmostEqual(80, self.controller.contour.area)

    def test_final_plate_persistence_no_editor_properties(self):
        for point in ((2, 3, 4), (12, 3, 7), (15, 9, 8)):
            self.add(point)
        self.controller.close_outline()
        self.assertTrue(self.panel.accept())
        plate = self.doc.Objects[0]
        contour, volume, name = plate.ContourData, plate.Shape.Volume, plate.Name
        self.assertFalse(any("Candidate" in p or "Input" in p or "Coordinate" in p
                             for p in plate.PropertiesList))
        path = ROOT / "test-results" / ("numeric_plate_persistence_"
                                        + "".join(App.Version()[:3]) + ".FCStd")
        path.parent.mkdir(exist_ok=True)
        try:
            self.doc.saveAs(str(path))
            App.closeDocument(self.doc.Name)
            self.doc = App.openDocument(str(path))
            self.doc.recompute()
            restored = self.doc.getObject(name)
            self.assertEqual(contour, restored.ContourData)
            self.assertAlmostEqual(volume, restored.Shape.Volume)
            self.assertTrue(restored.Shape.isValid())
        finally:
            if path.exists():
                path.unlink()


if __name__ == "__main__":
    unittest.main()
