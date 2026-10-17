"""Focused Qt presentation checks; numeric semantics stay in their approved tests."""
import importlib.util
import os
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

try:
    from PySide6 import QtCore, QtGui, QtWidgets, QtTest
    import shiboken6
except ImportError:
    QtWidgets = None


@unittest.skipIf(QtWidgets is None,"PySide6 required")
class TrussVisualPolishTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("QT_QPA_PLATFORM","offscreen")
        cls.app=QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        path=Path(__file__).resolve().parents[1]/"freecad/SteelStructures/interactive/truss_task_widgets.py"
        spec=importlib.util.spec_from_file_location("_truss_visual_widgets",path)
        module=importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules,{"PySide":SimpleNamespace(QtCore=QtCore,QtGui=QtGui,QtWidgets=QtWidgets)}):
            spec.loader.exec_module(module)
        cls.widgets=module

    def setUp(self):
        self.errors=[]
        self.old_hook=sys.excepthook
        sys.excepthook=lambda kind,error,trace:self.errors.append(str(error))
        self.fields=[]
        def vector(normal=False):
            widget=QtWidgets.QWidget()
            layout=QtWidgets.QGridLayout(widget) if normal else QtWidgets.QFormLayout(widget)
            layout.setContentsMargins(0,0,0,0)
            layout.setSpacing(3)
            if not normal:
                layout.setFieldGrowthPolicy(QtWidgets.QFormLayout.AllNonFixedFieldsGrow)
                layout.setRowWrapPolicy(QtWidgets.QFormLayout.WrapLongRows)
            for index,axis in enumerate("XYZ"):
                field=QtWidgets.QLineEdit("0" if normal else "1234,56789 mm")
                field.setMinimumWidth(110)
                field.setMinimumHeight(field.sizeHint().height())
                label=QtWidgets.QLabel(axis)
                label.setBuddy(field)
                if normal:
                    layout.addWidget(label,index,0)
                    layout.addWidget(field,index,1)
                else:
                    layout.addRow(label,field)
                self.fields.append(field)
            return widget
        self.form=self.widgets.TrussAdvancedLayout(vector(),vector(),vector(True))
        self.form.resize(620,500)
        self.form.show()
        self.flush()

    def flush(self):
        for _ in range(3):
            self.app.processEvents()

    def tearDown(self):
        getattr(self,"scroll",self.form).deleteLater()
        QtCore.QCoreApplication.sendPostedEvents(None,QtCore.QEvent.DeferredDelete)
        self.flush()
        sys.excepthook=self.old_hook
        self.assertEqual(self.errors,[])
        self.assertTrue(all(not shiboken6.isValid(field) for field in self.fields))

    def test_points_side_by_side_and_normal_horizontal_at_comfortable_width(self):
        start,end=self.form.point_groups
        self.assertEqual([start.title(),end.title(),self.form.normal_group.title()],
                         ["Ponto inicial","Ponto final","Normal do plano"])
        self.assertEqual(start.y(),end.y())
        self.assertLess(start.geometry().right(),end.geometry().left())
        self.assertEqual(len({field.mapTo(self.form,QtCore.QPoint()).y() for field in self.fields[6:]}),1)
        self.assertTrue(all(field.width()>=110 for field in self.fields))

    def test_narrow_form_stacks_points_without_horizontal_overflow(self):
        self.form.resize(220,620)
        self.flush()
        start,end=self.form.point_groups
        self.assertLess(start.geometry().bottom(),end.y())
        for field in self.fields:
            rect=QtCore.QRect(field.mapTo(self.form,QtCore.QPoint()),field.size())
            self.assertTrue(self.form.rect().contains(rect))
            self.assertGreaterEqual(field.width(),110)
            group=self.form.normal_group if field in self.fields[6:] else self.form.point_groups[0 if field in self.fields[:3] else 1]
            self.assertTrue(group.rect().contains(QtCore.QRect(field.mapTo(group,QtCore.QPoint()),field.size())))

    def test_resize_preserves_partial_text_focus_selection_and_field_identity(self):
        held=list(self.fields)
        field=self.fields[0]
        self.form.activateWindow()
        field.setFocus()
        self.flush()
        field.setText("1e")
        field.setSelection(0,1)
        expected=field.cursorPosition(),field.selectedText()
        for width in (220,620,240,700):
            self.form.resize(width,650)
            self.flush()
            self.assertTrue(field.hasFocus())
            self.assertEqual(field.text(),"1e")
            self.assertEqual((field.cursorPosition(),field.selectedText()),expected)
            self.assertEqual(self.fields,held)

    def test_larger_font_reflows_without_clipping_fields(self):
        font=self.form.font()
        font.setPointSize(font.pointSize()+4)
        self.form.setFont(font)
        self.form.resize(380,800)
        self.flush()
        start,end=self.form.point_groups
        self.assertLess(start.geometry().bottom(),end.y())
        for field in self.fields:
            self.assertGreaterEqual(field.height(),field.fontMetrics().height()+2)

    def test_scroll_container_reflows_after_repeated_width_changes(self):
        content=QtWidgets.QWidget()
        layout=QtWidgets.QVBoxLayout(content)
        quick=QtWidgets.QFormLayout()
        quick.setFieldGrowthPolicy(QtWidgets.QFormLayout.AllNonFixedFieldsGrow)
        quick.setRowWrapPolicy(QtWidgets.QFormLayout.WrapLongRows)
        for label in ("Forma:","Alma:","Referência:"):
            quick.addRow(label,QtWidgets.QLineEdit("Valor de teste"))
        layout.addLayout(quick)
        layout.addWidget(self.form)
        layout.addStretch(1)
        self.scroll=QtWidgets.QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setWidget(content)
        self.scroll.resize(640,500)
        self.scroll.show()
        for width in (640,240,620,220):
            margins=layout.contentsMargins()
            chrome=(margins.left()+margins.right()+2*self.scroll.frameWidth()
                    +self.scroll.style().pixelMetric(QtWidgets.QStyle.PM_ScrollBarExtent))
            self.scroll.resize(width+chrome,500)
            self.flush()
            for field in self.fields:
                rect=QtCore.QRect(field.mapTo(content,QtCore.QPoint()),field.size())
                self.assertTrue(content.rect().contains(rect))
            self.assertEqual(self.scroll.horizontalScrollBar().maximum(),0,
                str((width,content.minimumSizeHint().width(),self.form.minimumSizeHint().width(),quick.minimumSize().width())))

    def test_mass_status_reflows_below_without_overlap_and_keeps_fonts(self):
        info=self.widgets.TrussMassInformation(self.form)
        info.set_pending(True)
        info.show()
        for width in (570,230,600):
            info.resize(width,100)
            self.flush()
            status=info.status_box.geometry()
            self.assertTrue(info.clock.isVisible())
            self.assertEqual(info.status.text(),"Aguardando aplicação")
            for key,value in info.values.items():
                self.assertFalse(status.intersects(value.geometry()))
                self.assertFalse(value.font().bold())
                self.assertTrue(info.labels[key].font().bold())
                self.assertNotIn("kg",info.labels[key].text())
            self.assertEqual(info._below,width==230)
            if not info._below:
                center=(info.values["mass"].geometry().top()+info.values["linear_mass"].geometry().bottom())/2
                self.assertLess(abs(status.center().y()-center),3)
        info.set_pending(False)
        self.assertTrue(info.status.isHidden())
        self.assertTrue(info.status_box.isHidden())

    def test_button_keeps_native_states_without_stylesheet(self):
        button=self.widgets.TrussEditorButton("Editor de Treliças...",self.form)
        button.resize(240,40)
        button.setAutoDefault(False)
        button.show()
        self.flush()
        normal=button.grab().toImage()
        button.setDown(True)
        pressed=button.grab().toImage()
        self.assertNotEqual(normal,pressed)
        button.setDown(False)
        button.setEnabled(False)
        disabled=button.grab().toImage()
        self.assertNotEqual(normal,disabled)
        calls=[]
        button.clicked.connect(lambda:calls.append(True))
        button.click()
        self.assertFalse(calls)
        button.setEnabled(True)
        button.setFocus()
        self.flush()
        QtTest.QTest.keyClick(button,QtCore.Qt.Key_Space)
        self.assertEqual(calls,[True])
        self.assertEqual(button.styleSheet(),"")

    def test_button_border_stays_blue_when_theme_accent_is_red(self):
        button=self.widgets.TrussEditorButton("Editor",self.form)
        button.resize(240,40)
        palette=button.palette()
        palette.setColor(QtGui.QPalette.Link,QtGui.QColor("#dc3545"))
        palette.setColor(QtGui.QPalette.Highlight,QtGui.QColor("#dc3545"))
        button.setPalette(palette)
        button.show()
        color=button.grab().toImage().pixelColor(round(120*button.devicePixelRatioF()),0)
        self.assertGreater(color.blue(),color.red())


if __name__=="__main__":
    unittest.main()
