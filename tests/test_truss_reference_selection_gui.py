"""Real native Selection/Task View integration; run with reference_selection gate."""
from copy import deepcopy
import os
from pathlib import Path
import unittest

try:
    import FreeCAD as App
    import FreeCADGui as Gui
    import Part
    import Draft
    from PySide import QtCore, QtWidgets
    from PySide6 import QtTest
except ImportError:
    App = None


@unittest.skipIf(App is None, 'FreeCAD GUI and Qt required')
class ReferenceSelectionGuiTests(unittest.TestCase):
    def setUp(self):
        from freecad.SteelStructures.interactive import truss_controller
        self.host=truss_controller
        self.document=App.newDocument('ReferenceSelection')
        self.line=Draft.make_line(App.Vector(0,0,0),App.Vector(10000,0,0))
        self.other=Draft.make_line(App.Vector(100,200,0),App.Vector(12100,200,0))
        self.document.recompute()
        Gui.Selection.clearSelection()
        self.panel=self.host.open_truss_panel(self.document)
        self.settle()
        self.panel.reference_mode.setCurrentIndex(self.panel.reference_mode.findData('DraftLine'))
        self.panel.keep_reference_link.setChecked(True)
        self.settle()
        self.output=Path(os.environ['SS_DUOPITCH_OUT'])

    def settle(self):
        for _ in range(6): QtWidgets.QApplication.processEvents()
        QtTest.QTest.qWait(15)
        if not self.panel._closed and self.panel._preview_timer is not None:
            self.panel._preview_timer.stop()

    def tearDown(self):
        if self.host._active_panel is not None: self.host._active_panel.reject()
        self.settle()
        for name in list(App.listDocuments()): App.closeDocument(name)
        self.settle()

    def begin(self):
        Gui.Selection.clearSelection()
        self.panel.select_reference_button.click()
        self.settle()
        self.assertIsNotNone(self.panel._reference_selection)
        self.assertIn('Clique',self.panel.source_label.text())
        return self.panel._reference_selection

    def choose(self, obj, edge='Edge1'):
        Gui.Selection.addSelection(self.document.Name,obj.Name,edge)
        self.settle()

    def escape(self):
        window=Gui.getMainWindow()
        QtWidgets.QApplication.setActiveWindow(window)
        viewport=next(w for w in window.findChildren(QtWidgets.QWidget)
                      if w.inherits('SIM::Coin3D::Quarter::QuarterWidget') and w.isVisible())
        viewport.setFocus()
        self.settle()
        QtTest.QTest.keyClick(viewport,QtCore.Qt.Key_Escape)
        self.settle()

    def test_button_first_native_selection_preserves_session_and_synchronizes(self):
        session=self.panel.session
        baseline=session.baseline_config
        # Establish a valid candidate so the connection intent below has its
        # ordinary canonical defaults before taking the preservation snapshot.
        Gui.Selection.addSelection(self.other)
        self.panel.select_reference_button.click()
        self.settle()
        self.panel.height.setValue(1437.125678)
        from freecad.SteelStructures.trusses.assemblies import configure_assembly
        from freecad.SteelStructures.trusses.interconnector_options import default_connector
        self.panel.session.config['role_specs']['TOP_CHORD']=configure_assembly(
            self.panel.session.config['role_specs']['TOP_CHORD'],'SpacedPair',240.,
            interconnectors=(default_connector('Battens'),))
        self.panel.session.config['connection_intents']={'B_S_MAIN_1_3':dict(form='Gusset',gusset=dict(plate_thickness=12.))}
        self.panel._refresh()
        before=deepcopy(self.panel.get_config())
        names={obj.Name for obj in self.document.Objects}
        operation=self.begin()
        self.choose(self.line)
        self.assertTrue(operation.closed)
        self.assertIsNone(self.panel._reference_selection)
        self.assertIs(self.panel.session,session)
        self.assertIsNone(self.panel.controller.object)
        config=self.panel.get_config()
        self.assertEqual(config['reference_source'],self.line.Name)
        self.assertEqual(config['start'],[0,0,0])
        self.assertEqual(config['end'],[10000,0,0])
        for key in ('height','role_specs','connection_intents','reference_alignment'):
            self.assertEqual(config.get(key),before.get(key))
        self.assertEqual(session.baseline_config,baseline)
        self.assertEqual(names,{obj.Name for obj in self.document.Objects})
        self.assertTrue(self.panel._valid)
        self.assertIsNotNone(session.validated_candidate)
        self.assertFalse(self.panel.controller._point_callbacks)
        self.assertIn(self.line.Label,self.panel.source_label.text())
        self.panel.form.grab().save(str(self.output/'selected_reference.png'))

    def test_real_viewport_mouse_click_selects_after_button(self):
        view=Gui.activeDocument().activeView()
        view.viewTop()
        view.fitAll()
        self.settle()
        operation=self.begin()
        viewport=next(w for w in Gui.getMainWindow().findChildren(QtWidgets.QWidget)
                      if w.inherits('SIM::Coin3D::Quarter::QuarterWidget') and w.isVisible())
        screen=view.getPointOnScreen(App.Vector(5000,0,0))
        point=QtCore.QPoint(int(screen[0]),viewport.height()-int(screen[1]))
        QtTest.QTest.mouseClick(viewport,QtCore.Qt.LeftButton,QtCore.Qt.NoModifier,pos=point)
        self.settle()
        self.assertTrue(operation.closed)
        self.assertEqual(self.panel.get_config()['reference_source'],self.line.Name)
        Gui.getMainWindow().grab().save(str(self.output/'viewport_selection.png'))

    def test_native_drawing_after_capture_cleans_observer_and_restores_session(self):
        operation=self.begin()
        session=self.panel.session
        before=deepcopy(self.panel.get_config())
        self.panel.draw_reference_button.click()
        self.settle()
        self.assertTrue(operation.closed)
        from freecad.SteelStructures.interactive.truss_draft_reference import ReferenceLine
        tool=App.activeDraftCommand
        self.assertIsInstance(tool,ReferenceLine)
        tool.finish()
        self.settle()
        self.panel=self.host._active_panel
        self.assertIsNotNone(self.panel)
        self.assertIs(self.panel.session,session)
        self.assertEqual(self.panel.get_config(),before)
        self.assertIsNone(self.panel._reference_selection)

    def test_escape_in_viewport_preserves_exact_previous_draft_and_repeats(self):
        Gui.Selection.addSelection(self.line)
        self.panel.select_reference_button.click()
        self.settle()
        before=deepcopy(self.panel.get_config())
        for _ in range(3):
            operation=self.begin()
            self.escape()
            self.assertTrue(operation.closed)
            self.assertFalse(self.panel._closed)
            self.assertFalse(self.panel.session.closed)
            self.assertIsNotNone(Gui.Control.activeDialog())
            self.assertEqual(self.panel.get_config(),before)
        self.begin()
        self.choose(self.other)
        self.assertEqual(self.panel.get_config()['reference_source'],self.other.Name)

    def test_invalid_geometry_leaves_draft_and_capture_intact(self):
        rectangle=Draft.make_rectangle(3000,1500)
        solid=self.document.addObject('Part::Feature','Solid')
        solid.Shape=Part.makeBox(4000,2000,1000)
        circle=self.document.addObject('Part::Feature','Curve')
        circle.Shape=Part.makeCircle(500)
        null=self.document.addObject('Part::Feature','Null')
        degenerate=Draft.make_line(App.Vector(),App.Vector())
        self.document.recompute()
        before=deepcopy(self.panel.get_config())
        operation=self.begin()
        for obj,sub in ((solid,'Edge1'),(solid,'Face1'),(solid,'Vertex1'),(circle,'Edge1'),
                        (rectangle,'Edge2'),(null,''),(degenerate,''),(self.line,'Vertex1')):
            self.choose(obj,sub)
            self.assertFalse(operation.closed,(obj.Name,sub))
            self.assertEqual(self.panel.get_config(),before)
            self.assertIsNone(self.panel.controller.object)
        self.choose(self.line)
        self.assertTrue(operation.closed)
        self.assertEqual(self.panel.get_config()['reference_source'],self.line.Name)

    def test_rectangle_mode_requires_explicit_base_and_retains_legacy_semantics(self):
        rectangle=Draft.make_rectangle(3000,1500)
        self.document.recompute()
        self.panel.reference_mode.setCurrentIndex(self.panel.reference_mode.findData('DraftRectangle'))
        Gui.Selection.clearSelection()
        self.panel.pick_button.click()
        self.settle()
        operation=self.panel._reference_selection
        self.choose(rectangle,'')
        self.assertFalse(operation.closed)
        self.assertIn('explicitamente',self.panel.source_label.text())
        self.choose(rectangle,'Edge2')
        self.assertTrue(operation.closed)
        config=self.panel.get_config()
        self.assertEqual(config['reference_mode'],'DraftRectangle')
        self.assertEqual(config['reference_edge'],'Edge2')
        self.assertAlmostEqual(config['span'],1500)
        self.assertAlmostEqual(config['height'],3000)
        self.assertIn(' · Edge2',self.panel.source_label.text())

    def test_association_apply_replacement_undo_redo_and_existing_owner(self):
        self.begin(); self.choose(self.line)
        self.document.openTransaction('Move native reference')
        self.line.End=App.Vector(11000,0,0)
        self.document.recompute()
        self.document.commitTransaction()
        self.assertTrue(self.panel._refresh())
        self.assertAlmostEqual(self.panel.span.value(),11000)
        self.document.undo(); self.settle()
        self.assertTrue(self.panel._refresh())
        self.assertAlmostEqual(self.panel.span.value(),10000)
        self.document.redo(); self.settle()
        self.assertTrue(self.panel._refresh())
        self.assertAlmostEqual(self.panel.span.value(),11000)
        self.assertTrue(self.panel.apply())
        owner=self.panel.controller.object
        state=owner.AppliedState
        self.assertEqual(owner.ReferenceSource[0],self.line)
        operation=self.begin()
        self.escape()
        self.assertTrue(operation.closed)
        self.assertIs(self.panel.controller.object,owner)
        self.assertEqual(owner.AppliedState,state)
        self.begin(); self.choose(self.other)
        self.assertIs(self.panel.controller.object,owner)
        self.assertTrue(self.panel.apply())
        self.assertIs(self.panel.controller.object,owner)
        self.assertEqual(owner.ReferenceSource[0],self.other)
        self.panel.reject(); self.settle()
        self.panel=self.host.open_truss_panel(self.document,owner)
        self.settle()
        self.assertEqual(self.panel.get_config()['reference_source'],self.other.Name)
        self.assertIn(self.other.Label,self.panel.source_label.text())

    def test_external_change_keeps_persistence_conflict_and_draft(self):
        self.begin(); self.choose(self.line)
        self.assertTrue(self.panel.apply())
        owner=self.panel.controller.object
        self.line.End=App.Vector(11000,0,0)
        self.document.recompute()
        # Native linked recompute changes the persisted requested definition.
        # Acquisition must honor the existing conflict/reopen contract.
        self.assertFalse(self.panel._refresh())
        self.assertIn('fora desta sessão',self.panel.session.conflict_reason)
        before=deepcopy(self.panel.get_config())
        operation=self.begin()
        self.choose(self.other)
        self.assertFalse(operation.closed)
        self.assertEqual(self.panel.get_config(),before)
        self.assertIn('fora desta sessão',self.panel.source_label.text())
        self.escape()
        self.panel.reject(); self.settle()
        self.panel=self.host.open_truss_panel(self.document,owner)
        self.settle()
        self.assertTrue(self.panel._valid)
        self.assertAlmostEqual(self.panel.span.value(),11000)

    def test_dependency_cycle_rejected_before_draft_change(self):
        self.begin(); self.choose(self.line)
        self.assertTrue(self.panel.apply())
        owner=self.panel.controller.object
        dependent=Draft.make_line(App.Vector(),App.Vector(13000,0,0))
        dependent.addProperty('App::PropertyLink','DependentOn')
        dependent.DependentOn=owner
        self.document.recompute()
        before=deepcopy(self.panel.get_config())
        operation=self.begin()
        self.choose(dependent)
        self.assertFalse(operation.closed)
        self.assertEqual(self.panel.get_config(),before)
        self.assertIn('própria treliça',self.panel.source_label.text())
        self.escape()

    def test_external_task_close_detaches_queued_selection(self):
        operation=self.begin()
        Gui.Selection.addSelection(self.line)
        Gui.Control.closeDialog()
        self.settle()
        self.assertTrue(operation.closed)
        self.assertIsNone(operation.panel)
        self.assertIsNone(operation.shortcut)
        self.assertTrue(self.panel.session.closed)
        self.assertIsNone(self.host._active_panel)
        Gui.Selection.clearSelection()
        Gui.Selection.addSelection(self.other)
        self.settle()
        self.assertIsNone(self.host._active_panel)

    def test_switch_and_close_document_detach_observers(self):
        operation=self.begin()
        other=App.newDocument('SelectionOtherDocument')
        self.settle()
        self.assertTrue(operation.closed)
        self.assertIsNone(operation.panel)
        self.assertIsNone(self.panel._reference_selection)
        App.setActiveDocument(self.document.Name)
        self.settle()
        operation=self.begin()
        App.closeDocument(self.document.Name)
        self.settle()
        self.assertTrue(operation.closed)
        self.assertTrue(self.panel.session.closed)
        self.assertIsNotNone(other)

    def test_successor_command_cleans_capture_and_no_preview_callbacks(self):
        operation=self.begin()
        Gui.runCommand('Draft_Line',0)
        self.settle()
        self.assertTrue(operation.closed)
        self.assertTrue(self.panel.session.closed)
        self.assertIsNone(self.panel.controller._preview)
        self.assertFalse(self.panel.controller._point_callbacks)
        command=App.activeDraftCommand
        self.assertIsNot(command,self.panel)
        command.finish()
        self.settle()
        self.assertIsNone(self.host._active_panel)


if __name__=='__main__': unittest.main()
