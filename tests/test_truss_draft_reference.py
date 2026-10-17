"""Scoped native handoff contracts without a FreeCAD/Qt runtime."""
from copy import deepcopy
import importlib.util
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace as NS
import unittest
from unittest.mock import patch

from tests.test_truss_task_panel import make_panel


class NativeLine:
    def __init__(self, mode): self.mode = mode
    def Activated(self):
        self.operation.backend_app.activeDraftCommand = self
        self.ui = NS()
        self.node = []
    def commit(self, name, commands): self.commands = commands
    def finish(self, cont=False, closed=False):
        self.native_finish = (cont, closed)
        self.operation.backend_app.activeDraftCommand = None
    def end_callbacks(self, call): self.removed = call


class ReferenceTests(unittest.TestCase):
    def setUp(self):
        self.queue, self.observers, self.shown, self.commits = [], [], [], []
        self.app = NS(activeDraftCommand=None, ActiveDocument=None,
                      addDocumentObserver=self.observers.append,
                      removeDocumentObserver=self.observers.remove,
                      Console=NS(PrintError=lambda value: None))
        self.gui = NS(Control=NS(activeDialog=lambda: False),
                      doCommand=lambda text:None,
                      draftToolBar=NS(baseWidget=NS(destroyed=NS(connect=lambda f: None))))
        self.params = NS(get_param=lambda key: False)
        self.todo = NS(ToDo=NS(delayAfter=lambda f, arg: self.queue.append(f),
                              delay=lambda f, arg:self.queue.append(lambda:f(arg)),
                              delayCommit=self.commits.extend))
        self.modules = {'FreeCAD':self.app, 'FreeCADGui':self.gui,
            'draftguitools':ModuleType('draftguitools'),
            'draftguitools.gui_lines':NS(Line=NativeLine),
            'draftutils':NS(params=self.params,todo=self.todo)}
        self.patcher = patch.dict(sys.modules,self.modules)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)
        name='freecad.SteelStructures.interactive.truss_draft_reference'
        path=Path(__file__).resolve().parents[1]/'freecad/SteelStructures/interactive/truss_draft_reference.py'
        spec=importlib.util.spec_from_file_location(name,path)
        self.module=importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.module)
        self.panel=make_panel()
        self.doc=NS(getObject=lambda name: self.line if name=='ExactLine' else None)
        self.line=NS(Name='ExactLine',Document=self.doc)
        self.panel.document=self.doc
        self.panel.session.document=self.doc
        self.panel.controller.object=None
        self.panel._topology_editor=None
        self.panel.form=object()
        self.panel.controller._assert_active_document=lambda: None
        self.panel.controller.bind_session=lambda config: self.panel.session
        self.panel.controller.cancel_picker=lambda: None
        self.panel.controller.remove_preview=lambda: None
        self.panel.controller._document_is_open=lambda: True
        self.app.ActiveDocument=self.doc
        self.app.activeDraftCommand=self.panel
        self.gui.Control.closeDialog=self.panel._form_destroyed
        self.host=NS(_active_panel=self.panel,_show_truss_panel=self.show)
        self.host_patch=patch.dict(sys.modules,{
            'freecad.SteelStructures.interactive.truss_controller':self.host,
            'WorkingPlane':NS(get_working_plane=lambda:NS(v=[0,1,0]))})
        self.host_patch.start()
        self.addCleanup(self.host_patch.stop)

    def show(self,controller,config,session):
        self.shown.append((controller,deepcopy(config),session))
        return NS(show_3d=NS(setChecked=lambda value:None),_show_error=lambda text:None)

    def start(self):
        operation=self.module.ReferenceLineOperation(self.panel)
        operation.backend_app=self.app
        operation.start()
        return operation

    def finish(self,operation):
        operation.tool.finish(cont=True)
        self.assertFalse(self.shown)
        self.queue.pop(0)()

    def test_suspension_releases_form_but_preserves_same_session_and_deep_draft(self):
        config=self.panel.get_config()
        operation=self.start()
        self.assertTrue(self.panel._suspended)
        self.assertIsNone(self.panel.form)
        self.assertFalse(self.panel.session.closed)
        self.panel.session.config['start'][0]=123
        self.assertEqual(operation.config,config)
        self.assertEqual(self.panel.controller.cancels,0)

    def test_escape_restores_original_draft_same_controller_session_and_baseline(self):
        baseline=self.panel.session.baseline_config
        operation=self.start()
        self.finish(operation)
        controller,config,session=self.shown[0]
        self.assertIs(controller,self.panel.controller)
        self.assertIs(session,self.panel.session)
        self.assertEqual(config,operation.config)
        self.assertEqual(session.baseline_config,baseline)
        self.assertFalse(session.closed)
        self.assertFalse(self.observers or self.module._operations)
        self.assertEqual(operation.tool.native_finish,(False,False))

    def test_commit_delivers_exact_result_not_selection_or_document_difference(self):
        operation=self.start()
        original=['line = Draft.make_wire(points)','FreeCAD.ActiveDocument.recompute()']
        operation.tool.commit('Create Wire',original)
        self.assertEqual(len(original),2)
        self.assertFalse(self.commits)
        self.queue.pop(0)()
        commands=self.commits[0][1]
        self.assertIn(repr(operation.token),commands[-1])
        self.assertTrue(commands[-1].endswith(', line)'))
        self.module.deliver('another-operation',self.line)
        self.assertIsNone(operation.result)
        self.module.deliver(operation.token,self.line)
        self.assertIs(operation.result,self.line)

    def test_native_queued_commands_are_guarded_against_document_switch(self):
        operation=self.start()
        self.assertTrue(self.module.in_document(operation.token))
        self.app.ActiveDocument=object()
        self.assertFalse(self.module.in_document(operation.token))
        self.app.ActiveDocument=self.doc
        operation.abandoned=True
        self.assertFalse(self.module.in_document(operation.token))
        self.assertFalse(self.module.in_document('expired'))

    def test_no_transaction_is_enqueued_when_last_document_closed(self):
        operation=self.start()
        operation.tool.commit('Create Wire',['line = Draft.make_wire(points)','FreeCAD.ActiveDocument.recompute()'])
        self.app.ActiveDocument=None
        self.queue.pop(0)()
        self.assertFalse(self.commits)
        self.queue.pop(0)()
        self.assertTrue(self.panel.session.closed)

    def test_removed_owner_cleans_suspended_session(self):
        operation=self.start()
        self.panel.session.assert_context=lambda *args: (_ for _ in ()).throw(ValueError('removed'))
        self.finish(operation)
        self.assertTrue(self.panel.session.closed)
        self.assertFalse(self.shown or self.observers or self.module._operations)

    def test_success_changes_only_reference_without_apply_or_owner_creation(self):
        operation=self.start()
        self.module.is_draft_line=lambda line: line is self.line
        self.module.source_geometry=lambda *args:dict(start=[10,20,30],end=[110,20,30],span=100,plane_normal=[0,0,1])
        baseline=self.panel.session.baseline_config
        self.module.deliver(operation.token,self.line)
        self.finish(operation)
        config=self.shown[0][1]
        self.assertEqual(config['reference_source'],'ExactLine')
        self.assertTrue(config['reference_linked'] and config['reference_defined'])
        self.assertEqual(config['start'],[10,20,30])
        for key in ('role_specs','custom_topology','reference_alignment','height','panel_count'):
            self.assertEqual(config.get(key),operation.config.get(key))
        self.assertEqual(self.panel.session.baseline_config,baseline)
        self.assertEqual(self.panel.controller.applies,[])
        self.assertIsNone(self.panel.session.owner)

    def test_document_switch_abandons_without_resurrecting_task(self):
        operation=self.start()
        self.app.ActiveDocument=object()
        operation.slotActivateDocument(self.app.ActiveDocument)
        self.queue.pop(0)()
        self.assertFalse(self.shown)
        self.assertTrue(self.panel.session.closed)
        self.assertFalse(self.observers or self.module._operations)

    def test_deleted_document_abandons_without_return(self):
        operation=self.start()
        operation.slotDeletedDocument(self.doc)
        self.queue.pop(0)()
        self.assertTrue(self.panel.controller._document_deleted)
        self.assertTrue(self.panel.session.closed)
        self.assertFalse(self.shown)

    def test_successor_command_is_not_closed_or_replaced(self):
        operation=self.start()
        operation.tool.finish()
        successor=object()
        self.app.activeDraftCommand=successor
        self.queue.pop(0)()
        self.assertIs(self.app.activeDraftCommand,successor)
        self.assertFalse(self.shown)
        self.assertTrue(self.panel.session.closed)

    def test_external_task_destruction_abandons_and_is_idempotent(self):
        operation=self.start()
        operation._draft_form_destroyed()
        self.queue.pop(0)()
        self.queue.pop(0)()
        operation.complete()
        self.assertFalse(self.shown or self.observers or self.module._operations)
        self.assertTrue(self.panel.session.closed)

    def test_part_primitive_preference_is_rejected_before_suspension(self):
        self.params.get_param=lambda key:True
        with self.assertRaisesRegex(ValueError,'primitivas Part'):
            self.module.start_reference_line(self.panel)
        self.assertFalse(self.panel._suspended)
        self.assertIsNotNone(self.panel.form)
        self.assertFalse(self.panel.session.closed)

    def test_temporary_cleanup_skips_closed_document(self):
        operation=self.start()
        operation.tool.obj=object()
        operation.tool.removeTemporaryObject()
        self.assertIsNone(operation.tool.obj)
        self.panel.controller._document_is_open=lambda:False
        self.queue.pop(0)()  # Must not read any property of the dead preview.

    def test_temporary_cleanup_removes_only_its_exact_preview(self):
        operation=self.start()
        obj=NS(Name='Preview')
        removed=[]
        self.doc.getObject=lambda name:obj
        self.doc.removeObject=removed.append
        operation.tool.obj=obj
        operation.tool.removeTemporaryObject()
        self.queue.pop(0)()
        self.assertEqual(removed,['Preview'])


if __name__=='__main__': unittest.main()
