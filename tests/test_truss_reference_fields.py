"""Real FreeCAD units and Qt text entry; skipped when that runtime is absent."""
import importlib.util
import os
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

try:
    import FreeCAD as App
    from PySide6 import QtCore, QtGui, QtWidgets, QtTest
    import shiboken6
except ImportError:
    App = None


@unittest.skipIf(App is None, "FreeCAD units and PySide6 required")
class TrussReferenceFieldTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if QtWidgets.QApplication.instance() is None:
            os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        path = Path(__file__).resolve().parents[1] / "freecad/SteelStructures/interactive/truss_reference_field.py"
        spec = importlib.util.spec_from_file_location("_truss_reference_field_tests", path)
        module = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {"PySide": SimpleNamespace(QtCore=QtCore, QtWidgets=QtWidgets)}):
            spec.loader.exec_module(module)
        cls.field_class = module.TrussReferenceField

    def setUp(self):
        self.schema = App.Units.getSchema()
        self.params = App.ParamGet("User parameter:BaseApp/Preferences/Units")
        self.decimals = self.params.GetInt("Decimals", 2)
        App.Units.setSchema(0)
        self.dialog = QtWidgets.QDialog()
        layout = QtWidgets.QVBoxLayout(self.dialog)
        self.field = self.field_class(1234.567890123456, parent=self.dialog)
        self.field.setAccessibleName("P0 X")
        self.other = QtWidgets.QLineEdit(self.dialog)
        self.ok = QtWidgets.QPushButton("OK", self.dialog)
        self.ok.setDefault(True)
        self.ok.clicked.connect(self.dialog.accept)
        for widget in (self.field, self.other, self.ok):
            layout.addWidget(widget)
        self.errors, self.values = [], []
        self.field.inputError.connect(self.errors.append)
        self.field.valueChanged.connect(self.values.append)
        self.dialog.show()
        QtWidgets.QApplication.setActiveWindow(self.dialog)
        self.other.setFocus()
        self.app.processEvents()

    def tearDown(self):
        self.dialog.deleteLater()
        QtCore.QCoreApplication.sendPostedEvents(None, QtCore.QEvent.DeferredDelete)
        self.app.processEvents()
        self.assertFalse(shiboken6.isValid(self.dialog))
        App.Units.setSchema(self.schema)
        self.params.SetInt("Decimals", self.decimals)

    def focus(self):
        QtWidgets.QApplication.setActiveWindow(self.dialog)
        self.field.setFocus()
        self.app.processEvents()
        self.assertTrue(self.field.hasFocus())

    def test_display_preferences_and_bare_number_in_displayed_unit(self):
        for schema in (0, 3, 4, 5, 7, 9):
            with self.subTest(schema=schema):
                App.Units.setSchema(schema)
                self.field.setValue(1234.567890123456)
                quantity = App.Units.Quantity(self.field.value(), App.Units.Length)
                factor,unit=quantity.getUserPreferred()[1:]
                self.assertEqual(self.field.text(), self.field.locale().toString(self.field.value()/factor,"f",2)+" "+unit)
                factor = quantity.getUserPreferred()[1]
                self.field.setText("2")
                self.assertTrue(self.field.commit())
                self.assertEqual(self.field.value(), 2 * factor)

    def test_precision_preferences_do_not_change_internal_value(self):
        exact = self.field.value()
        for precision in (0, 2, 6, 12):
            self.params.SetInt("Decimals", precision)
            self.field.setValue(exact)
            self.assertEqual(self.field.text(), self.field.locale().toString(exact,"f",2)+" mm")
            self.assertEqual(self.params.GetInt("Decimals"),precision)
            self.assertEqual(self.field.value(), exact)

    def test_explicit_units_negative_locale_and_scientific_notation(self):
        for text, value in (("-2 cm", -20.), ("0.5 m", 500.), ("1,5 mm", 1.5),
                            ("2 in", 50.8), ("1e-7 mm", 1e-7)):
            self.field.setText(text)
            self.assertTrue(self.field.commit())
            self.assertEqual(self.field.value(), value)

    def test_partial_invalid_and_wrong_dimension_keep_text_and_last_exact_value(self):
        exact = self.field.value()
        for text in ("", "-", "1e", "nan", "inf", "1 kg", "2 deg", "abc"):
            self.field.setText(text)
            self.assertFalse(self.field.commit())
            self.assertEqual(self.field.text(), text)
            self.assertEqual(self.field._value, exact)
            with self.assertRaises(ValueError):
                self.field.value()
        self.assertEqual(len(self.errors), 8)
        self.assertFalse(self.values)

    def test_normal_is_dimensionless_and_does_not_inherit_length_schema(self):
        App.Units.setSchema(9)
        normal = self.field_class(-.123456789012345, normal=True, parent=self.dialog)
        normal.setAccessibleName("Normal Y")
        self.assertEqual(normal.text(), App.Units.Quantity(normal.value()).UserString)
        normal.setText("-0,75")
        self.assertTrue(normal.commit())
        self.assertEqual(normal.value(), -.75)
        normal.setText("1 mm")
        self.assertFalse(normal.commit())
        self.assertEqual(normal.text(), "1 mm")

    def test_untouched_focus_return_tab_keep_all_double_digits(self):
        for schema in (0, 3, 5, 9):
            App.Units.setSchema(schema)
            for exact in (1.123456789012345, 1e-10, 123456789.12345679):
                self.field.setValue(exact)
                self.values.clear()
                self.focus()
                QtTest.QTest.keyClick(self.field, QtCore.Qt.Key_Return)
                QtTest.QTest.keyClick(self.field, QtCore.Qt.Key_Tab)
                self.app.processEvents()
                self.assertEqual(self.field.value(), exact)
        self.assertFalse(self.values)

    def test_enter_confirms_field_without_accepting_dialog(self):
        self.focus()
        self.field.selectAll()
        QtTest.QTest.keyClicks(self.field, "1234.123456789 mm")
        QtTest.QTest.keyClick(self.field, QtCore.Qt.Key_Return)
        self.assertEqual(self.field.value(), 1234.123456789)
        self.assertEqual(self.values, [1234.123456789])
        self.assertTrue(self.dialog.isVisible())
        self.assertEqual(self.dialog.result(), 0)

    def test_explicit_rounding_to_presented_text_is_a_real_edit(self):
        for normal in (False, True):
            field = self.field_class(1.123456789012345, normal=normal, parent=self.dialog)
            self.dialog.layout().insertWidget(0,field)
            shown = field.text()
            field.setFocus()
            self.app.processEvents()
            field.selectAll()
            QtTest.QTest.keyClicks(field,shown)
            expected = App.Units.Quantity(shown).Value
            self.assertTrue(field.commit())
            self.assertEqual(field.value(),expected)

    def test_tab_preserves_incomplete_edit_and_native_focus(self):
        self.focus()
        self.field.selectAll()
        QtTest.QTest.keyClicks(self.field, "1e")
        QtTest.QTest.keyClick(self.field, QtCore.Qt.Key_Tab)
        self.app.processEvents()
        self.assertTrue(self.other.hasFocus())
        self.assertEqual(self.field.text(), "1e")
        self.assertTrue(self.errors)
        self.assertFalse(self.values)
        self.focus()
        self.assertEqual(self.field.text(), "1e")

    def test_selection_edit_and_same_candidate_sync_keep_cursor(self):
        self.focus()
        self.field.setText("12.3456789 cm")
        self.field.setSelection(1, 4)
        cursor, selected = self.field.cursorPosition(), self.field.selectedText()
        self.field.setValue(self.field.value())
        self.assertEqual(self.field.text(), "12.3456789 cm")
        self.assertEqual((self.field.cursorPosition(), self.field.selectedText()), (cursor, selected))
        self.field.selectAll()
        QtTest.QTest.keyClicks(self.field, "20 mm")
        self.field.setSelection(0, 1)
        QtTest.QTest.keyClicks(self.field, "3")
        self.assertTrue(self.field.commit())
        self.assertEqual(self.field.value(), 30.)

    def test_new_reference_replaces_pending_text_without_emitting_numeric_edit(self):
        self.focus()
        self.field.setText("-")
        exact = 2.123456789012345
        with QtCore.QSignalBlocker(self.field):
            self.field.setValue(exact)
        self.assertEqual(self.field.value(), exact)
        self.assertFalse(self.values)

    def test_programmatic_setter_notifies_once_and_supports_signal_blocking(self):
        self.field.setValue(25.)
        self.assertEqual(self.values,[25.])
        self.field.setValue(25.)
        self.assertEqual(self.values,[25.])
        with QtCore.QSignalBlocker(self.field):
            self.field.setValue(26.)
        self.assertEqual(self.field.value(),26.)
        self.assertEqual(self.values,[25.])

    def test_escape_restores_value_and_recovers_from_error(self):
        exact = self.field.value()
        self.focus()
        self.field.setText("-")
        self.assertFalse(self.field.commit())
        QtTest.QTest.keyClick(self.field, QtCore.Qt.Key_Escape)
        self.assertEqual(self.field.value(), exact)
        self.assertEqual(self.values, [exact])
        self.assertTrue(self.dialog.isVisible())

    def test_escape_notifies_after_validation_without_field_commit(self):
        self.focus()
        self.field.selectAll()
        QtTest.QTest.keyClicks(self.field,"-")
        with self.assertRaises(ValueError):
            self.field.value()  # The panel's existing preview timer can read it.
        QtTest.QTest.keyClick(self.field,QtCore.Qt.Key_Escape)
        self.assertEqual(self.values,[self.field.value()])

    def test_repair_same_numeric_value_emits_to_revalidate_panel(self):
        exact = self.field.value()
        self.field.setText("-")
        self.assertFalse(self.field.commit())
        self.field.setText(str(exact) + " mm")
        self.assertTrue(self.field.commit())
        self.assertEqual(self.values, [exact])


if __name__ == "__main__":
    unittest.main()
