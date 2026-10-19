"""Native raw-subelement, Snapshot and unchanged Draft reference contracts."""
from copy import deepcopy
import json
from unittest.mock import patch

from tests import test_truss_reference_selection_gui as selection_tests

App=selection_tests.App

if App is not None:
    import FreeCADGui as Gui
    import Part
    import Draft
    from PySide import QtCore,QtWidgets
    from PySide6 import QtTest


class EdgeSnapshotGuiTests(selection_tests.ReferenceSelectionGuiTests):
    def reopen(self, selection=()):
        self.panel.reject(); self.settle()
        Gui.Selection.clearSelection()
        for obj, sub in selection:
            Gui.Selection.addSelection(self.document.Name, obj.Name, sub)
        names={obj.Name for obj in self.document.Objects}
        Gui.runCommand('SteelStructures_CreateTruss', 0)
        self.panel=self.host._active_panel
        self.assertIsNotNone(self.panel)
        self.settle()
        self.assertEqual(names,{obj.Name for obj in self.document.Objects})
        self.assertIsNone(self.panel.controller.object)
        return self.panel.get_config()

    def test_opening_and_interactive_capture_have_identical_snapshots(self):
        from freecad.SteelStructures import profile_catalog
        from freecad.SteelStructures.member import create_member
        profile=next(iter(profile_catalog.profiles().values()))
        member=create_member(self.document,App.Vector(100,200,300),App.Vector(6100,200,300),profile.designation)
        rectangle=Draft.make_rectangle(4000,2300)
        outer=self.document.addObject('App::Part','Outer')
        inner=self.document.addObject('App::Part','Inner')
        outer.addObject(inner)
        box=self.box()
        inner.addObject(box)
        outer.Placement=App.Placement(App.Vector(100,200,300),App.Rotation(App.Vector(0,0,1),35))
        inner.Placement=App.Placement(App.Vector(400,500,600),App.Rotation(App.Vector(1,0,0),25))
        box.Placement=App.Placement(App.Vector(700,800,900),App.Rotation(App.Vector(0,1,0),15))
        member.Placement=App.Placement(App.Vector(120,340,560),App.Rotation(App.Vector(1,1,1),31))
        rectangle.Placement=App.Placement(App.Vector(300,600,900),App.Rotation(App.Vector(1,0,0),20))
        plain=self.box('PlainBox')
        self.document.recompute()
        for obj,sub in ((plain,'Edge1'),(member,'Edge1'),(rectangle,'Edge2'),
                        (outer,'Inner.Source.Edge1'),(box,'Edge1')):
            with self.subTest(source=obj.Name,path=sub):
                self.reopen()
                self.panel.reference_mode.setCurrentIndex(self.panel.reference_mode.findData('DraftLine'))
                interactive=self.capture(obj,sub)
                origin=deepcopy(self.panel.session._edge_snapshot_origin)
                with patch.object(App.Console,'PrintWarning') as warning:
                    opening=self.reopen([(obj,sub)])
                warning.assert_not_called()
                self.assertEqual(opening,interactive)
                self.assertEqual(self.panel.session._edge_snapshot_origin,origin)
                self.assertEqual(self.panel.reference_mode.currentText(),'Linha ou aresta')
                self.assertFalse(self.panel.keep_reference_link.isChecked())
                self.assertFalse(self.panel.keep_reference_link.isEnabled())
                self.assertIn('Snapshot',self.panel.source_label.text())
                self.assertTrue(self.panel._valid)
                self.assertEqual(self.panel._last_preview_config,opening)
                self.assertIsNotNone(self.panel.session.validated_candidate)
                self.assertEqual(self.panel._read_vector(self.panel.start_inputs),opening['start'])
                self.assertEqual(self.panel._read_vector(self.panel.end_inputs),opening['end'])
                self.assertAlmostEqual(self.panel.span.value(),opening['span'])
                self.panel._update_preview3d()
                self.assertIsNotNone(self.panel.controller._preview)
        self.panel.form.grab().save(str(self.output/'opening_edge_snapshot.png'))

    def test_opening_draft_line_retains_optional_association(self):
        outer=self.document.addObject('App::Part','LineParent')
        outer.addObject(self.line)
        outer.Placement=App.Placement(App.Vector(123,456,789),App.Rotation(App.Vector(0,0,1),31))
        self.document.recompute()
        for obj,sub in ((self.line,''),(self.line,'Edge1'),(outer,self.line.Name+'.Edge1')):
            with self.subTest(path=sub):
                config=self.reopen([(obj,sub)])
                self.assertEqual(config['reference_mode'],'DraftLine')
                self.assertEqual(config['reference_source'],self.line.Name)
                self.assertFalse(config['reference_linked'])
                self.assertTrue(self.panel.keep_reference_link.isEnabled())
                self.assertIsNone(self.panel.session._edge_snapshot_origin)
                self.assertTrue(self.panel._valid)
        self.panel.keep_reference_link.setChecked(True)
        self.assertTrue(self.panel.apply())
        owner=self.panel.controller.object
        self.assertEqual(owner.ReferenceSource[0],self.line)
        self.line.End=App.Vector(12000,0,0)
        self.document.recompute()
        from freecad.SteelStructures.truss import config_from_object
        self.assertAlmostEqual(config_from_object(owner)['span'],12000.)

    def test_opening_whole_draft_rectangle_preserves_envelope_and_base_choice(self):
        parent=self.document.addObject('App::Part','RectangleParent')
        parent.Placement=App.Placement(App.Vector(200,300,400),App.Rotation(App.Vector(1,0,0),27))
        for width,height in ((4000,2300),(3000,3000)):
            rectangle=Draft.make_rectangle(width,height)
            parent.addObject(rectangle)
            self.document.recompute()
            config=self.reopen([(parent,rectangle.Name+'.')])
            self.assertEqual(config['reference_mode'],'DraftRectangle')
            self.assertIsNone(self.panel.session._edge_snapshot_origin)
            if width!=height:
                self.assertEqual(config['reference_edge'],'Edge1')
                self.assertAlmostEqual(config['span'],width)
                self.assertAlmostEqual(config['height'],height)
            else:
                self.assertEqual(config['reference_edge'],'')
                self.assertFalse(config['reference_defined'])
                self.assertFalse(self.panel._valid)
            self.panel.reference_edge.setCurrentIndex(self.panel.reference_edge.findData('Edge2'))
            self.settle()
            self.assertTrue(self.panel._valid)
            config=self.panel.get_config()
            self.assertAlmostEqual(config['span'],height)
            self.assertAlmostEqual(config['height'],width)

    def test_opening_invalid_and_multiple_references_leave_default_draft_intact(self):
        box=self.box()
        curve=self.document.addObject('Part::Feature','Curve')
        curve.Shape=Part.makeCircle(500)
        null=self.document.addObject('Part::Feature','Null')
        self.document.recompute()
        baseline=self.reopen()
        for selection in ([(box,'')],[(box,'Face1')],[(box,'Vertex1')],[(curve,'Edge1')],
                          [(null,'')],[(self.line,'Vertex1')],[(box,'Edge1'),(self.line,'')],
                          [(box,'Edge1'),(box,'Edge2')]):
            with self.subTest(selection=[(obj.Name,sub) for obj,sub in selection]):
                with patch.object(App.Console,'PrintWarning') as warning:
                    config=self.reopen(selection)
                warning.assert_called_once()
                self.assertNotIn('Referência deve ser Linha ou Retângulo',warning.call_args.args[0])
                self.assertEqual(config,baseline)
                self.assertIsNone(getattr(self.panel.session,'_edge_snapshot_origin',None))
                self.assertEqual(self.panel.reference_mode.currentData(),'TwoPoints')

    def test_opening_snapshot_cancel_apply_ok_and_undo_redo(self):
        self.document.UndoMode=1
        box=self.box()
        names={obj.Name for obj in self.document.Objects}
        captured=self.reopen([(box,'Edge1')])
        self.panel.reject(); self.settle()
        self.assertEqual(names,{obj.Name for obj in self.document.Objects})
        self.reopen([(box,'Edge1')])
        operation=self.begin(); self.escape()
        self.assertTrue(operation.closed)
        self.assertEqual(self.panel.get_config(),captured)
        self.assertTrue(self.panel.apply())
        owner=self.panel.controller.object
        name=owner.Name
        self.assertIsNone(owner.ReferenceSource)
        self.assertEqual(owner.ReferenceContainers,[])
        self.assertNotIn(box,owner.OutList)
        self.assertTrue(self.panel.accept())
        self.settle()
        self.assertIsNone(self.host._active_panel)
        self.document.undo(); self.settle()
        self.assertIsNone(self.document.getObject(name))
        self.document.redo(); self.settle()
        owner=self.document.getObject(name)
        self.assertIsNotNone(owner)
        self.assertIsNone(owner.ReferenceSource)
        from freecad.SteelStructures.truss import config_from_object
        stored=config_from_object(owner)
        # Placement reconstructs the persisted axis with floating point rotation.
        for key in ('start','end'):
            self.assertLess((App.Vector(*stored[key])-App.Vector(*captured[key])).Length,1e-7)
        for key in ('reference_mode','reference_linked','reference_source','reference_edge'):
            self.assertEqual(stored[key],captured[key])

    def box(self, name='Source'):
        obj=self.document.addObject('Part::Box',name)
        obj.Length=4000
        obj.Width=2000
        obj.Height=1000
        self.document.recompute()
        return obj

    def capture(self, obj, sub='Edge1'):
        names={item.Name for item in self.document.Objects}
        operation=self.begin()
        self.choose(obj,sub)
        self.assertTrue(operation.closed,self.panel.source_label.text())
        self.assertEqual(names,{item.Name for item in self.document.Objects})
        config=self.panel.get_config()
        self.assertEqual(config['reference_mode'],'TwoPoints')
        self.assertFalse(config['reference_linked'])
        self.assertEqual(config['reference_source'],'')
        self.assertEqual(config['reference_edge'],'')
        self.assertFalse(self.panel.keep_reference_link.isChecked())
        self.assertFalse(self.panel.keep_reference_link.isEnabled())
        self.assertIn('Snapshot',self.panel.source_label.text())
        self.assertEqual(self.panel.reference_mode.currentData(),'DraftLine')
        self.assertFalse(self.panel.controller._point_callbacks)
        self.assertIsNone(operation.shortcut)
        self.assertFalse(operation.observing)
        return config

    def test_explicit_rectangle_edge_is_not_envelope(self):
        rectangle=Draft.make_rectangle(4000,2000)
        self.document.recompute()
        height=self.panel.height.value()
        config=self.capture(rectangle,'Edge2')
        self.assertAlmostEqual(config['span'],2000)
        self.assertEqual(config['height'],height)
        self.assertIn(rectangle.Label+' · Edge2',self.panel.source_label.text())
        self.panel.form.grab().save(str(self.output/'edge_snapshot.png'))

    def test_nested_part_and_body_use_global_endpoints_once(self):
        from freecad.SteelStructures.truss_edge_snapshot import selected_path,capture_edge
        from types import SimpleNamespace
        outer=self.document.addObject('App::Part','Outer')
        inner=self.document.addObject('App::Part','Inner')
        outer.addObject(inner)
        obj=self.box()
        inner.addObject(obj)
        outer.Placement=App.Placement(App.Vector(100,200,300),App.Rotation(App.Vector(0,0,1),35))
        inner.Placement=App.Placement(App.Vector(400,500,600),App.Rotation(App.Vector(1,0,0),25))
        obj.Placement=App.Placement(App.Vector(700,800,900),App.Rotation(App.Vector(0,1,0),15))
        self.document.recompute()
        local=Part.makeBox(4000,2000,1000).Edges[0]
        matrix=obj.getGlobalPlacement()
        expected=[matrix.multVec(local.valueAt(t)) for t in (local.FirstParameter,local.LastParameter)]
        config=self.capture(outer,'Inner.Source.Edge1')
        for actual,wanted in zip((config['start'],config['end']),expected):
            self.assertLess((App.Vector(*actual)-wanted).Length,1e-7)
        # SelectionEx(resolve=0) must supply the complete path even when a
        # preselection was requested by leaf Name in Python/the tree.
        Gui.Selection.clearSelection()
        Gui.Selection.addSelection(self.document.Name,obj.Name,'Edge1')
        self.panel.select_reference_button.click(); self.settle()
        leaf=self.panel.get_config()
        self.assertIsNone(self.panel._reference_selection)
        self.assertEqual(leaf['start'],config['start'])
        self.assertEqual(leaf['end'],config['end'])
        # Body is an object path authority too, not a second transform.
        body=self.document.addObject('PartDesign::Body','Body')
        inner.addObject(body)
        feature=body.newObject('PartDesign::Feature','BodyShape')
        feature.Shape=Part.makeBox(4500,2500,1200)
        body.Placement=App.Placement(App.Vector(321,654,987),App.Rotation(App.Vector(0,0,1),67))
        self.document.recompute()
        path=selected_path([SimpleNamespace(Object=outer,SubElementNames=('Inner.Body.BodyShape.Edge1',))],self.document)
        _selected,values,_origin=capture_edge(*path,[0,0,1],[0,1,0])
        local=Part.makeBox(4500,2500,1200).Edges[0]
        expected=[feature.getGlobalPlacement().multVec(local.valueAt(t))
                  for t in (local.FirstParameter,local.LastParameter)]
        for actual,wanted in zip((values['start'],values['end']),expected):
            self.assertLess((App.Vector(*actual)-wanted).Length,1e-7)
        nested=self.capture(body,'BodyShape.Edge1')
        self.assertEqual(nested['start'],values['start'])
        self.assertEqual(nested['end'],values['end'])
        direct=self.capture(body,'Edge1')
        self.assertEqual(direct['start'],values['start'])
        self.assertEqual(direct['end'],values['end'])

    def test_structural_member_plate_and_nontruss_source_unchanged(self):
        from freecad.SteelStructures import profile_catalog
        from freecad.SteelStructures.member import create_member
        from freecad.SteelStructures.plate import create_plate
        profile=next(iter(profile_catalog.profiles().values()))
        member=create_member(self.document,App.Vector(100,200,300),App.Vector(6100,200,300),profile.designation)
        plate=create_plate(self.document,[(0,0),(4500,0),(4500,2300),(0,2300)],thickness=12.)
        self.document.recompute()
        for obj in (member,plate):
            signature=obj.Shape.hashCode()
            config=self.capture(obj)
            self.assertTrue(config['span']>0)
            self.assertEqual(signature,obj.Shape.hashCode())
            self.assertIsNone(self.panel.controller.object)

    def test_link_arrays_curves_infinite_missing_and_cycles_are_rejected(self):
        source=self.box()
        link=self.document.addObject('App::Link','Occurrence')
        link.setLink(source)
        spline=self.document.addObject('Part::Feature','Spline')
        curve=Part.BSplineCurve()
        curve.interpolate([App.Vector(0,0,0),App.Vector(500,100,0),App.Vector(1000,0,0)])
        spline.Shape=curve.toShape()
        infinite=self.document.addObject('Part::Feature','Infinite')
        infinite.Shape=Part.Line().toShape()
        array=self.document.addObject('Part::Feature','Array')
        array.Shape=source.Shape
        array.addProperty('App::PropertyString','ArrayType')
        array.ArrayType='ortho'
        self.document.recompute()
        before=deepcopy(self.panel.get_config())
        operation=self.begin()
        for obj,sub in ((link,'Edge1'),(spline,'Edge1'),(infinite,'Edge1'),(array,'Edge1')):
            self.choose(obj,sub)
            self.assertFalse(operation.closed,(obj.Name,self.panel.source_label.text()))
            self.assertEqual(self.panel.get_config(),before)
        from types import SimpleNamespace
        with self.assertRaises((ValueError,RuntimeError)):
            self.panel.controller.selected_linear_reference([SimpleNamespace(Object=source,SubElementNames=('Edge999',))],[0,0,1])
        self.escape()
        self.capture(source)
        self.assertTrue(self.panel.apply())
        owner=self.panel.controller.object
        before=deepcopy(self.panel.get_config())
        operation=self.begin()
        self.choose(owner.GeneratedMembers[0])
        self.assertFalse(operation.closed)
        self.assertEqual(self.panel.get_config(),before)
        self.assertIn('própria treliça',self.panel.source_label.text())
        self.escape()

    def test_snapshot_apply_source_changes_delete_undo_persistence_and_copy(self):
        from freecad.SteelStructures.truss import config_from_object as get_config
        self.document.UndoMode=1
        obj=self.box()
        config=self.capture(obj)
        self.assertTrue(self.panel.apply())
        owner=self.panel.controller.object
        state=owner.AppliedState
        stored=deepcopy(get_config(owner))
        self.assertIsNone(owner.ReferenceSource)
        self.assertEqual(owner.ReferenceContainers,[])
        self.assertNotIn(obj,owner.OutList)
        self.assertNotIn('Edge1',owner.C2Configuration)
        self.assertNotIn(obj.Name,owner.C2Configuration)
        self.assertTrue(self.panel.apply())
        self.assertIs(owner,self.panel.controller.object)
        self.assertEqual(state,owner.AppliedState)
        self.document.openTransaction('Change source')
        obj.Length=6000
        obj.Placement=App.Placement(App.Vector(1000,2000,3000),App.Rotation(App.Vector(0,1,0),40))
        self.document.recompute()
        self.document.commitTransaction()
        self.assertEqual(get_config(owner),stored)
        self.assertEqual(self.panel.get_config()['start'],config['start'])
        self.document.undo(); self.settle()
        self.assertEqual(get_config(owner),stored)
        self.document.redo(); self.settle()
        self.assertEqual(get_config(owner),stored)
        name=obj.Name
        self.document.openTransaction('Delete source')
        self.document.removeObject(name)
        self.document.recompute()
        self.document.commitTransaction()
        self.assertTrue(self.panel._refresh())
        self.assertEqual(get_config(owner),stored)
        self.assertNotIn(name,self.panel.source_label.text())
        self.assertIn('Snapshot',self.panel.source_label.text())
        self.document.undo(); self.settle()
        self.assertEqual(get_config(owner),stored)
        self.panel.reject(); self.settle()
        self.assertEqual(get_config(owner),stored)
        # Native independent copy, then save/reopen: no source metadata or links.
        copied=self.document.copyObject(owner,True)
        self.document.recompute()
        self.assertEqual(get_config(copied)['start'],stored['start'])
        self.assertIsNone(copied.ReferenceSource)
        self.assertEqual(copied.ReferenceContainers,[])
        path=self.output/'snapshot_persistence.FCStd'
        self.document.saveAs(str(path))
        owner_name=owner.Name
        copy_name=copied.Name
        App.closeDocument(self.document.Name)
        self.document=App.openDocument(str(path))
        for item in (self.document.getObject(owner_name),self.document.getObject(copy_name)):
            self.assertEqual(get_config(item)['start'],stored['start'])
            self.assertIsNone(item.ReferenceSource)
        self.panel=self.host.open_truss_panel(self.document,self.document.getObject(owner_name))
        self.settle()
        self.assertEqual(self.panel.reference_mode.currentData(),'TwoPoints')
        self.assertTrue(self.panel._valid)

    def test_link_preference_replacement_esc_checkpoint_and_native_draw(self):
        from freecad.SteelStructures.interactive.truss_topology_editor import TopologyEditor
        from freecad.SteelStructures.interactive.truss_editor_checkpoint import TrussEditorCheckpoint
        source=self.box()
        for linked in (False,True):
            self.begin(); self.choose(self.line)
            self.panel.keep_reference_link.setChecked(linked)
            snapshot=self.capture(source)
            before=deepcopy(self.panel.session._edge_snapshot_origin)
            operation=self.begin(); self.escape()
            self.assertTrue(operation.closed)
            self.assertEqual(self.panel.get_config(),snapshot)
            editor=TopologyEditor(self.panel)
            checkpoint=TrussEditorCheckpoint(self.panel,editor)
            self.begin(); self.choose(self.other)
            self.assertEqual(self.panel.keep_reference_link.isChecked(),linked)
            self.assertTrue(self.panel.keep_reference_link.isEnabled())
            self.assertTrue(checkpoint.restore(self.panel))
            self.assertEqual(self.panel.get_config(),snapshot)
            self.assertEqual(self.panel.session._edge_snapshot_origin,before)
            self.assertFalse(self.panel.keep_reference_link.isEnabled())
            editor.deleteLater(); self.settle()
            session=self.panel.session
            self.panel.draw_reference_button.click(); self.settle()
            App.activeDraftCommand.finish(); self.settle()
            self.panel=self.host._active_panel
            self.assertIs(self.panel.session,session)
            self.assertEqual(self.panel.get_config(),snapshot)
            self.assertEqual(self.panel.session._edge_snapshot_origin,before)
            self.assertFalse(self.panel.keep_reference_link.isEnabled())

    def test_preselection_snapshot_and_label_identity(self):
        obj=self.box()
        Gui.Selection.addSelection(self.document.Name,obj.Name,'Edge3')
        self.panel.select_reference_button.click(); self.settle()
        self.assertIsNone(self.panel._reference_selection)
        config=self.panel.get_config()
        self.assertEqual(config['reference_mode'],'TwoPoints')
        obj.Label='Renamed source'
        self.settle()
        self.assertIn('Renamed source · Edge3 — Snapshot',self.panel.source_label.text())
        name=obj.Name
        self.document.removeObject(name); self.settle()
        replacement=self.box(name)
        self.settle()
        self.assertNotIn(replacement.Label,self.panel.source_label.text())
        self.assertEqual(self.panel.get_config()['start'],config['start'])

    def test_draft_line_in_parent_keeps_legacy_association(self):
        group=self.document.addObject('App::Part','Group')
        group.addObject(self.line)
        group.Placement=App.Placement(App.Vector(123,456,789),App.Rotation(App.Vector(0,0,1),31))
        self.document.recompute()
        self.begin(); self.choose(group,self.line.Name+'.Edge1')
        config=self.panel.get_config()
        self.assertEqual(config['reference_mode'],'DraftLine')
        self.assertEqual(config['reference_source'],self.line.Name)
        self.assertTrue(config['reference_linked'])
        self.assertTrue(self.panel.apply())
        self.assertEqual(self.panel.controller.object.ReferenceSource[0],self.line)

    def test_real_viewport_edge_click(self):
        obj=self.box()
        self.line.ViewObject.Visibility=False
        self.other.ViewObject.Visibility=False
        obj.ViewObject.DisplayMode='Wireframe'
        self.document.recompute()
        view=Gui.activeDocument().activeView()
        Gui.updateGui()
        view.viewTop(); view.fitAll(); view.redraw(); self.settle()
        operation=self.begin()
        viewport=next(w for w in Gui.getMainWindow().findChildren(QtWidgets.QWidget)
                      if w.inherits('SIM::Coin3D::Quarter::QuarterWidget') and w.isVisible())
        QtWidgets.QApplication.setActiveWindow(Gui.getMainWindow())
        viewport.setFocus(); self.settle()
        view.redraw(); Gui.updateGui(); self.settle()
        screen=view.getPointOnScreen(App.Vector(2000,0,1000))
        pixel=QtCore.QPoint(round(screen[0]),viewport.height()-round(screen[1]))
        QtTest.QTest.mouseClick(viewport,QtCore.Qt.LeftButton,QtCore.Qt.NoModifier,pos=pixel)
        self.settle()
        (self.output/'edge_mouse.json').write_text(json.dumps(dict(pixel=[pixel.x(),pixel.y()],
            viewport=[viewport.width(),viewport.height()],selection=[str(item) for item in Gui.Selection.getSelectionEx('',0)]),indent=2))
        Gui.getMainWindow().grab().save(str(self.output/'viewport_edge_snapshot.png'))
        self.assertTrue(operation.closed,self.panel.source_label.text())
        self.assertEqual(self.panel.get_config()['reference_mode'],'TwoPoints')
        self.assertIn(obj.Label+' · Edge',self.panel.source_label.text())
        Gui.getMainWindow().grab().save(str(self.output/'viewport_edge_snapshot.png'))

    def test_custom_composite_gusset_and_alignment_are_preserved(self):
        from freecad.SteelStructures.trusses.assemblies import configure_assembly
        from freecad.SteelStructures.trusses.interconnector_options import default_connector
        self.begin(); self.choose(self.line)
        edge=next(edge for edge in self.panel.session.validated_candidate.graph.edges if edge.role=='DIAGONAL')
        self.panel.apply_topology_edit('remove_edge',key=edge.key)
        self.panel.session.config['role_specs']['TOP_CHORD']=configure_assembly(
            self.panel.session.config['role_specs']['TOP_CHORD'],'SpacedPair',240.,
            interconnectors=(default_connector('Battens'),))
        self.panel.session.config['connection_intents']={'B_S_MAIN_1_3':dict(form='Gusset',gusset=dict(plate_thickness=12.))}
        self.panel.reference_alignment.setCurrentIndex(self.panel.reference_alignment.findData('TopChordSupports'))
        self.panel._refresh()
        before=deepcopy(self.panel.get_config())
        box=self.box()
        config=self.capture(box)
        for key in ('height','role_specs','connection_intents','custom_topology','topology_mode','reference_alignment'):
            self.assertEqual(config[key],before[key],key)
        self.assertIsNone(self.panel.controller.object)

    def test_modal_cancel_x_and_apply_checkpoint_restore_snapshot_metadata(self):
        source=self.box()
        self.capture(source)
        origin=deepcopy(self.panel.session._edge_snapshot_origin)
        def modal(action):
            failures=[]
            def callback():
                editor=self.panel._topology_editor
                try: action(editor)
                except Exception as exc: failures.append(exc)
                finally:
                    if editor.isVisible(): editor.reject()
            QtCore.QTimer.singleShot(0,callback)
            self.panel.editor_button.click()
            self.settle()
            if failures: raise failures[0]
            self.assertFalse(self.panel._closed)
            self.assertIsNotNone(Gui.Control.activeDialog())
            self.assertEqual(self.panel.session._edge_snapshot_origin,origin)
            self.assertFalse(self.panel.keep_reference_link.isEnabled())
        for close in ('cancel','x'):
            before=deepcopy(self.panel.get_config())
            def change(editor):
                self.panel.reference_mode.setCurrentIndex(self.panel.reference_mode.findData('TwoPoints'))
                self.panel.height.setValue(self.panel.height.value()+100.)
                if close=='x': editor.close()
                else: editor.cancel_button.click()
            modal(change)
            self.assertEqual(self.panel.get_config(),before)
            self.assertIsNone(self.panel.controller.object)
        applied=[]
        def apply_then_cancel(editor):
            editor.apply_button.click()
            self.assertIsNotNone(self.panel.controller.object)
            applied.append(deepcopy(self.panel.get_config()))
            self.panel.height.setValue(self.panel.height.value()+100.)
            editor.cancel_button.click()
        modal(apply_then_cancel)
        self.assertEqual(self.panel.get_config(),applied[0])
        owner=self.panel.controller.object
        def ok(editor):
            self.panel.height.setValue(self.panel.height.value()+50.)
            editor.ok_button.click()
        modal(ok)
        self.assertIs(self.panel.controller.object,owner)
        self.assertIsNone(owner.ReferenceSource)

    def test_snapshot_controls_fit_narrow_panel(self):
        source=self.box()
        window=Gui.getMainWindow()
        dock=self.panel.form
        while dock is not None and not isinstance(dock,QtWidgets.QDockWidget): dock=dock.parentWidget()
        self.assertIsNotNone(dock)
        for width in (380,260):
            window.resize(1150,600)
            window.resizeDocks([dock],[width],QtCore.Qt.Horizontal)
            self.settle()
            QtTest.QTest.qWait(100)
            self.settle()
            before=self.panel.reference_mode.height()
            self.capture(source)
            self.settle()
            controls=[self.panel.reference_mode,self.panel.select_reference_button,self.panel.draw_reference_button,
                      self.panel.source_label,self.panel.keep_reference_link,self.panel.editor_button]
            self.panel.form.grab().save(str(self.output/('snapshot_width_'+str(width)+'.png')))
            (self.output/('snapshot_width_'+str(width)+'.json')).write_text(json.dumps([
                dict(kind=type(w).__name__,name=w.objectName(),size=[w.width(),w.height()],
                     hint=[w.sizeHint().width(),w.sizeHint().height()],minimum=w.minimumSizeHint().height(),
                     maximum=w.maximumHeight(),before_combo_height=before,
                     font_height=w.fontMetrics().height(),height_for_width=w.heightForWidth(w.width())) for w in controls],indent=2))
            for widget in controls:
                required=widget.minimumSizeHint().height()
                if widget.hasHeightForWidth(): required=max(required,widget.heightForWidth(widget.width()))
                else: required=max(required,widget.sizeHint().height())
                self.assertGreaterEqual(widget.height(),required,type(widget).__name__+':'+widget.objectName())
            for left in controls:
                for right in controls:
                    if left is right: continue
                    a=QtCore.QRect(left.mapTo(self.panel.form,QtCore.QPoint()),left.size())
                    b=QtCore.QRect(right.mapTo(self.panel.form,QtCore.QPoint()),right.size())
                    self.assertFalse(a.intersects(b),(left.objectName(),right.objectName()))

    def test_successful_native_drawing_replaces_snapshot_without_new_owner(self):
        self.capture(self.box())
        session=self.panel.session
        baseline=session.baseline_config
        self.panel.draw_reference_button.click(); self.settle()
        tool=App.activeDraftCommand
        tool.numericInput(100,300,0); self.settle()
        tool.numericInput(8100,300,0); self.settle()
        self.panel=self.host._active_panel
        self.assertIs(self.panel.session,session)
        self.assertEqual(session.baseline_config,baseline)
        self.assertIsNone(self.panel.controller.object)
        self.assertIsNone(session._edge_snapshot_origin)
        self.assertEqual(self.panel.reference_mode.currentData(),'DraftLine')
        self.assertTrue(self.panel.keep_reference_link.isEnabled())
        self.assertTrue(self.panel.keep_reference_link.isChecked())
        config=self.panel.get_config()
        self.assertEqual(config['reference_mode'],'DraftLine')
        self.assertTrue(config['reference_linked'])
        self.assertEqual(config['start'],[100,300,0])
        self.assertEqual(config['end'],[8100,300,0])

    def test_undo_application_blocks_external_conflict_without_overwriting_draft(self):
        self.document.UndoMode=1
        source=self.box()
        self.capture(source,'Edge1')
        self.assertTrue(self.panel.apply())
        owner=self.panel.controller.object
        original=owner.AppliedState
        self.capture(source,'Edge9')
        self.assertEqual(owner.AppliedState,original)
        self.assertTrue(self.panel.apply())
        self.assertIs(self.panel.controller.object,owner)
        changed=owner.AppliedState
        self.assertNotEqual(changed,original)
        before=deepcopy(self.panel.get_config())
        origin=deepcopy(self.panel.session._edge_snapshot_origin)
        self.document.undo(); self.settle()
        self.assertEqual(owner.AppliedState,original)
        self.assertFalse(self.panel._refresh())
        operation=self.begin()
        self.choose(self.line)
        self.assertFalse(operation.closed)
        self.assertEqual(self.panel.get_config(),before)
        self.assertEqual(self.panel.session._edge_snapshot_origin,origin)
        self.escape()
        self.panel.reject(); self.settle()
        self.document.redo(); self.settle()
        self.assertEqual(owner.AppliedState,changed)
        self.panel=self.host.open_truss_panel(self.document,owner)
        self.settle()
        self.assertTrue(self.panel._valid)
