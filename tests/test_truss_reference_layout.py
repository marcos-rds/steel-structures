"""Real Qt layout/scroll regression; run inside FreeCAD by reference_layout gate."""
import json
import os
from pathlib import Path
import unittest

try:
    import FreeCAD as App
    import FreeCADGui as Gui
    from PySide import QtCore, QtWidgets
    from PySide6 import QtTest
except ImportError:
    App = None


@unittest.skipIf(App is None, 'FreeCAD GUI and Qt required')
class ReferenceLayoutTests(unittest.TestCase):
    def setUp(self):
        from freecad.SteelStructures.interactive import truss_controller
        self.host = truss_controller
        self.document = App.newDocument('ReferenceLayout')
        self.panel = self.host.open_truss_panel(self.document)
        self.window = Gui.getMainWindow()
        self.output = Path(os.environ.get('SS_DUOPITCH_OUT', '.'))
        self.samples = []
        self.settle()
        self.dock = self.panel.form
        while self.dock is not None and not isinstance(self.dock, QtWidgets.QDockWidget):
            self.dock = self.dock.parentWidget()
        self.assertIsNotNone(self.dock, 'Task View dock not found')

    def tearDown(self):
        command=getattr(App,'activeDraftCommand',None)
        if command is not None: command.finish()
        for _ in range(6): QtWidgets.QApplication.processEvents()
        if self.host._active_panel is not None:
            self.host._active_panel.reject()
        for _ in range(4): QtWidgets.QApplication.processEvents()
        if self.document.Name in App.listDocuments(): App.closeDocument(self.document.Name)

    def settle(self):
        for _ in range(6): QtWidgets.QApplication.processEvents()
        QtTest.QTest.qWait(20)
        if not self.panel._closed and not self.panel._suspended and self.panel._preview_timer is not None:
            self.panel._preview_timer.stop()

    def resize_task(self, width, height):
        self.window.resize(1150, height)
        self.window.resizeDocks([self.dock], [width], QtCore.Qt.Horizontal)
        self.settle()

    def check_reference_geometry(self, label):
        panel = self.panel
        content = panel.sections['Referência'][1]
        section = content.parentWidget()
        widgets = [panel.reference_mode, panel.pick_button, panel.select_reference_button,
                   panel.draw_reference_button, panel.source_label, panel.keep_reference_link]
        visible = [widget for widget in widgets if widget.isVisible()]
        def rect(widget):
            return QtCore.QRect(widget.mapTo(panel.form, QtCore.QPoint()), widget.size())
        scroll = panel.form.parentWidget()
        while scroll is not None and not isinstance(scroll, QtWidgets.QScrollArea):
            scroll = scroll.parentWidget()
        self.assertIsNotNone(scroll, 'Native Task View scroll missing')
        sample = dict(label=label, form=[panel.form.width(), panel.form.height()],
                      form_minimum=[panel.form.minimumHeight(),panel.form.minimumSizeHint().height(),panel.form.sizeHint().height()],
                      root_minimum=panel.form.layout().minimumSize().height(),
                      root_height_for_width=panel.form.layout().totalHeightForWidth(panel.form.width()),
                      root_items=[dict(geometry=panel.form.layout().itemAt(i).geometry().getRect(),
                          minimum=panel.form.layout().itemAt(i).minimumSize().height(),
                          hint=panel.form.layout().itemAt(i).sizeHint().height(),
                          widget=type(panel.form.layout().itemAt(i).widget()).__name__)
                          for i in range(panel.form.layout().count())],
                      viewport=[scroll.viewport().width(), scroll.viewport().height()],
                      scroll_maximum=scroll.verticalScrollBar().maximum(),
                      section=[section.height(), section.minimumSizeHint().height(), section.sizeHint().height()],
                      content=[content.height(), content.minimumSizeHint().height(), content.sizeHint().height()],
                      controls={widget.objectName() or str(i):dict(height=widget.height(), hint=widget.sizeHint().height(),
                          minimum_width=widget.minimumWidth(), minimum_hint_width=widget.minimumSizeHint().width(),
                          hint_width=widget.sizeHint().width(), horizontal_policy=widget.sizePolicy().horizontalPolicy().value,
                          minimum=widget.minimumSizeHint().height(),
                          height_for_width=widget.heightForWidth(widget.width()) if widget.hasHeightForWidth() else None,
                          rect=rect(widget).getRect())
                          for i,widget in enumerate(visible)})
        self.samples.append(sample)
        (self.output/(self._testMethodName+'.json')).write_text(json.dumps(self.samples,indent=2),encoding='utf-8')
        self.window.grab().save(str(self.output/(label+'.png')))
        for widget in visible:
            required = widget.minimumSizeHint().height()
            if widget.hasHeightForWidth(): required = max(required, widget.heightForWidth(widget.width()))
            else: required = max(required, widget.sizeHint().height())
            self.assertGreaterEqual(widget.height(), required, label+': clipped '+widget.objectName())
            current = widget
            # Outside the scroll viewport is allowed; outside any own container is not.
            while current is not panel.form:
                parent = current.parentWidget()
                self.assertTrue(parent.rect().contains(current.geometry()), label+': outside '+parent.objectName())
                current = parent
            if isinstance(widget, QtWidgets.QPushButton):
                text_width = max(widget.fontMetrics().horizontalAdvance(line) for line in widget.text().splitlines())
                if not widget.icon().isNull(): text_width += widget.iconSize().width()+4
                option = QtWidgets.QStyleOptionButton()
                widget.initStyleOption(option)
                contents = widget.style().subElementRect(QtWidgets.QStyle.SE_PushButtonContents, option, widget)
                self.assertGreaterEqual(contents.width(), text_width, label+': clipped button text')
            self.assertLessEqual(rect(widget).right(), scroll.viewport().width(), label+': horizontal viewport clipping')
        for i,widget in enumerate(visible):
            for other in visible[i+1:]:
                self.assertFalse(rect(widget).intersects(rect(other)), label+': overlapping controls')
        self.assertGreaterEqual(rect(panel.editor_button).top(), rect(section).bottom()+1, label+': section/editor overlap')
        self.assertGreaterEqual(rect(panel.preview).top(), rect(panel.editor_button).bottom()+1, label+': editor/preview overlap')
        self.assertGreaterEqual(content.height(), content.minimumSizeHint().height(), label+': compressed reference content')
        if panel.form.height() > scroll.viewport().height():
            self.assertGreater(scroll.verticalScrollBar().maximum(),0,label+': content cannot scroll')
        return sample

    def test_conditional_modes_under_height_pressure(self):
        # Invalid source deliberately retains the existing diagnostic below the preview.
        for width,height in ((380,760),(300,520),(260,420)):
            self.resize_task(width,height)
            for cycle in range(3):
                for mode in ('TwoPoints','DraftLine'):
                    self.panel.reference_mode.setCurrentIndex(self.panel.reference_mode.findData(mode))
                    self.settle()
                    self.check_reference_geometry(f'{width}_{height}_{cycle}_{mode}')

    def test_source_caption_wraps_and_section_can_collapse(self):
        import Draft
        self.resize_task(300,460)
        source = Draft.make_line(App.Vector(0,0,0),App.Vector(10000,0,0))
        source.Label = 'Referência com identificação extensa para conferir quebra de linha e altura natural'
        self.document.recompute()
        self.panel.reference_mode.setCurrentIndex(self.panel.reference_mode.findData('DraftLine'))
        Gui.Selection.clearSelection()
        Gui.Selection.addSelection(source)
        self.panel.select_reference_button.click()
        self.settle()
        self.check_reference_geometry('long_source_label')
        box,content = self.panel.sections['Referência']
        box.setChecked(False)
        self.settle()
        self.assertTrue(content.isHidden())
        box.setChecked(True)
        self.settle()
        self.check_reference_geometry('expanded_again')

    def test_geometry_after_native_draft_completion_and_escape(self):
        self.resize_task(300,520)
        self.panel.reference_mode.setCurrentIndex(self.panel.reference_mode.findData('DraftLine'))
        self.settle()
        session=self.panel.session
        self.panel.draw_reference_button.click()
        self.settle()
        tool=App.activeDraftCommand
        tool.numericInput(0,0,0)
        tool.numericInput(10000,0,0)
        self.settle()
        self.panel=self.host._active_panel
        self.assertIs(self.panel.session,session)
        self.check_reference_geometry('after_native_completion')
        previous=self.panel.get_config()
        self.panel.draw_reference_button.click()
        self.settle()
        tool=App.activeDraftCommand
        tool.ui.xValue.setFocus()
        QtTest.QTest.keyClick(tool.ui.xValue,QtCore.Qt.Key_Escape)
        self.settle()
        self.panel=self.host._active_panel
        self.assertIs(self.panel.session,session)
        self.assertEqual(self.panel.get_config(),previous)
        self.check_reference_geometry('after_native_escape')

    def test_vertical_scroll_reaches_reference_controls(self):
        self.resize_task(260,420)
        self.panel.reference_mode.setCurrentIndex(self.panel.reference_mode.findData('DraftLine'))
        self.settle()
        scroll=self.panel.form.parentWidget()
        while scroll is not None and not isinstance(scroll,QtWidgets.QScrollArea):
            scroll=scroll.parentWidget()
        self.assertIsNotNone(scroll)
        self.assertGreater(scroll.verticalScrollBar().maximum(),0)
        for widget in (self.panel.reference_mode,self.panel.select_reference_button,
                       self.panel.draw_reference_button,self.panel.keep_reference_link):
            scroll.ensureWidgetVisible(widget)
            self.settle()
            rect=QtCore.QRect(widget.mapTo(scroll.viewport(),QtCore.QPoint()),widget.size())
            self.assertTrue(scroll.viewport().rect().contains(rect),'Control inaccessible through native scrolling')


if __name__=='__main__': unittest.main()
