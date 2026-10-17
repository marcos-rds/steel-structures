"""Two-decimal display using the actual FreeCAD Units and Qt editor."""
import importlib
import os
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import patch

try:
    import FreeCAD as App
    from PySide6 import QtCore, QtGui, QtWidgets, QtTest
except ImportError:
    App = None


@unittest.skipIf(App is None, "FreeCAD Units and PySide6 required")
class LengthPrecisionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        cls.app=QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        package=ModuleType("freecad.SteelStructures.interactive")
        package.__path__=[str(Path(__file__).resolve().parents[1]/"freecad/SteelStructures/interactive")]
        cls.modules=patch.dict(sys.modules,{
            "freecad.SteelStructures.interactive":package,
            "PySide":SimpleNamespace(QtCore=QtCore,QtGui=QtGui,QtWidgets=QtWidgets)})
        cls.modules.start()
        cls.addClassCleanup(cls.modules.stop)
        cls.spin_class=importlib.import_module("freecad.SteelStructures.interactive.truss_length_spinbox").TrussLengthSpinBox

    def setUp(self):
        self.schema=App.Units.getSchema()
        App.Units.setSchema(0)
        self.params=App.ParamGet("User parameter:BaseApp/Preferences/Units")
        self.decimals=self.params.GetInt("Decimals",2)
        self.dialog=QtWidgets.QDialog()
        layout=QtWidgets.QVBoxLayout(self.dialog)
        self.spin=self.spin_class()
        self.spin.setRange(-1e9,1e9)
        self.other=QtWidgets.QLineEdit()
        layout.addWidget(self.spin)
        layout.addWidget(self.other)
        self.dialog.show()
        QtWidgets.QApplication.setActiveWindow(self.dialog)
        self.other.setFocus()
        self.app.processEvents()

    def tearDown(self):
        self.dialog.deleteLater()
        self.app.sendPostedEvents(None,QtCore.QEvent.DeferredDelete)
        App.Units.setSchema(self.schema)
        self.params.SetInt("Decimals",self.decimals)

    def focus(self):
        self.spin.setFocus()
        self.app.processEvents()
        self.assertTrue(self.spin.hasFocus())

    def test_exact_roundtrip_with_two_decimals_independent_of_global_preferences(self):
        for precision in (0,3,12):
            self.params.SetInt("Decimals",precision)
            for exact in (10000.123456789012,1e-17,1250.1234567890123):
                self.other.setFocus()
                self.spin.setValue(exact)
                factor,unit=App.Units.Quantity(exact,App.Units.Length).getUserPreferred()[1:]
                self.assertEqual(self.spin.text(),self.spin.locale().toString(exact/factor,"f",2)+" "+unit)
                self.focus()
                QtTest.QTest.keyClick(self.spin,QtCore.Qt.Key_Return)
                QtTest.QTest.keyClick(self.spin,QtCore.Qt.Key_Tab)
                self.assertEqual(self.spin.value(),exact)
                self.assertEqual(self.params.GetInt("Decimals"),precision)

    def test_units_locales_and_explicit_entry(self):
        for locale in ("pt_BR","en_US","de_DE"):
            self.spin.setLocale(QtCore.QLocale(locale))
            for schema in (0,3,4,5,7,9):
                App.Units.setSchema(schema)
                self.other.setFocus()
                self.spin.setValue(1234.567890123456)
                factor,unit=App.Units.Quantity(self.spin.value(),App.Units.Length).getUserPreferred()[1:]
                self.assertEqual(self.spin.text(),self.spin.locale().toString(self.spin.value()/factor,"f",2)+" "+unit)
                self.focus()
                self.spin.lineEdit().selectAll()
                QtTest.QTest.keyClicks(self.spin,"2 cm")
                QtTest.QTest.keyClick(self.spin,QtCore.Qt.Key_Return)
                self.assertEqual(self.spin.value(),20.)

    def test_partial_selection_sync_and_tab_never_replace_input(self):
        self.spin.setValue(1250.123456789)
        self.focus()
        self.spin.lineEdit().selectAll()
        QtTest.QTest.keyClicks(self.spin,"1e")
        self.spin.lineEdit().setSelection(0,1)
        self.spin.setValue(1250.123456789)
        self.assertEqual(self.spin.lineEdit().text(),"1e")
        self.assertEqual(self.spin.lineEdit().selectedText(),"1")
        QtTest.QTest.keyClick(self.spin,QtCore.Qt.Key_Tab)
        self.assertTrue(self.other.hasFocus())
        self.assertEqual(self.spin.lineEdit().text(),"1e")
        with self.assertRaises(ValueError):
            self.spin.value()
        self.focus()
        self.assertEqual(self.spin.lineEdit().text(),"1e")

    def test_retyping_rounded_value_is_an_intentional_edit_and_emits_once(self):
        self.spin.setValue(1250.123456789)
        self.focus()
        values=[]
        self.spin.valueChanged.connect(values.append)
        self.spin.lineEdit().selectAll()
        QtTest.QTest.keyClicks(self.spin,"1250.12 mm")
        QtTest.QTest.keyClick(self.spin,QtCore.Qt.Key_Return)
        self.assertEqual(self.spin.value(),1250.12)
        self.assertEqual(values,[1250.12])
        self.assertTrue(self.dialog.isVisible())

    def test_grouped_regional_input(self):
        for locale,text in (("pt_BR","1.250,12 mm"),("en_US","1,250.12 mm"),("de_DE","1.250,12 mm")):
            self.other.setFocus()
            self.spin.setLocale(QtCore.QLocale(locale))
            self.focus()
            self.spin.lineEdit().selectAll()
            QtTest.QTest.keyClicks(self.spin,text)
            QtTest.QTest.keyClick(self.spin,QtCore.Qt.Key_Return)
            self.assertEqual(self.spin.value(),1250.12)

    def test_size_probes_never_change_the_unit_of_bare_input(self):
        for schema in (0,2):
            App.Units.setSchema(schema)
            self.other.setFocus()
            self.spin.setValue(1250.)
            factor=App.Units.Quantity(1250.,App.Units.Length).getUserPreferred()[1]
            self.spin.sizeHint()
            self.spin.minimumSizeHint()
            self.spin.textFromValue(self.spin.maximum())
            self.focus()
            self.spin.sizeHint()
            self.spin.textFromValue(self.spin.maximum())
            self.spin.lineEdit().selectAll()
            QtTest.QTest.keyClicks(self.spin,"2")
            QtTest.QTest.keyClick(self.spin,QtCore.Qt.Key_Return)
            self.assertEqual(self.spin.value(),2*factor)

    def test_sync_of_a_valid_pending_value_preserves_text_and_selection(self):
        self.spin.setValue(1000.)
        self.focus()
        self.spin.lineEdit().selectAll()
        QtTest.QTest.keyClicks(self.spin,"1250.12345678900 mm")
        self.spin.lineEdit().setSelection(3,5)
        self.spin.setValue(self.spin.value())
        self.assertEqual(self.spin.lineEdit().text(),"1250.12345678900 mm")
        self.assertEqual(self.spin.lineEdit().selectedText(),"0.123")
        self.assertEqual(self.spin.value(),1250.123456789)

    def test_invalid_input_notifies_and_escape_or_same_value_repair_recovers(self):
        for escape in (False,True):
            self.other.setFocus()
            self.spin.setValue(500.)
            self.focus()
            errors,values=[],[]
            self.spin.inputError.connect(errors.append)
            self.spin.valueChanged.connect(values.append)
            self.spin.lineEdit().selectAll()
            QtTest.QTest.keyClicks(self.spin,"1e")
            QtTest.QTest.keyClick(self.spin,QtCore.Qt.Key_Return)
            self.assertTrue(errors)
            if escape:
                QtTest.QTest.keyClick(self.spin,QtCore.Qt.Key_Escape)
            else:
                self.spin.lineEdit().selectAll()
                QtTest.QTest.keyClicks(self.spin,"500 mm")
                QtTest.QTest.keyClick(self.spin,QtCore.Qt.Key_Return)
            self.assertEqual(self.spin.value(),500.)
            self.assertEqual(values,[500.])
            self.spin.inputError.disconnect(errors.append)
            self.spin.valueChanged.disconnect(values.append)
