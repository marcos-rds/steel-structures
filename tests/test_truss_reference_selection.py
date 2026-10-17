"""Native-selection lifecycle contracts, independent of FreeCAD/Qt binaries."""
from copy import deepcopy
import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch


class Signal:
    def connect(self, callback): self.callback=callback
    def disconnect(self, callback): self.callback=None


class Shortcut:
    def __init__(self, *_args): self.activated=Signal(); self.enabled=True; self.deleted=False
    def setContext(self, _value): pass
    def setEnabled(self, value): self.enabled=value
    def deleteLater(self): self.deleted=True


class ReferenceSelectionTests(unittest.TestCase):
    def setUp(self):
        self.selection=[]; self.observers=[]; self.doc_observers=[]; self.queue=[]
        self.document=NS(Name='Trusses')
        self.source=NS(Name='Line',Document=self.document)
        self.config=dict(reference_source='Previous',start=[0,0,0],role_specs={'test':[1,2]})
        self.before=deepcopy(self.config)
        self.owner=object(); self.applied=[]; self.error=None; self.mode='DraftLine'
        self.panel=NS(document=self.document,form=object(),_closed=False,_suspended=False,
                      _reference_selection=None)
        self.panel.session=NS(assert_context=lambda *_args:None,config=self.config)
        def selected(items):
            self.last_selection=items
            if self.error: raise ValueError(self.error)
            return dict(reference_mode=self.mode,reference_source=items[0].Object.Name,reference_edge='Edge1')
        self.panel.controller=NS(object=self.owner,selected_reference=selected,_assert_active_document=lambda:None,
                                 bind_session=lambda _config:None)
        self.panel._adopt_selected_reference=lambda value:self.applied.append(value)
        self.panel._sync_reference_source=lambda:None
        gui=NS(Selection=NS(getSelectionEx=lambda:self.selection,
                           clearSelection=lambda:self.selection.clear(),
                           addObserver=self.observers.append,removeObserver=self.observers.remove))
        app=NS(addDocumentObserver=self.doc_observers.append,removeDocumentObserver=self.doc_observers.remove)
        qt=NS(QtCore=NS(Qt=NS(WindowShortcut=1),QTimer=NS(singleShot=lambda _delay,fn:self.queue.append(fn))),
              QtGui=NS(QShortcut=Shortcut,QKeySequence=lambda text:text))
        path=Path(__file__).resolve().parents[1]/'freecad/SteelStructures/interactive/truss_reference_selection.py'
        spec=importlib.util.spec_from_file_location('_truss_selection_contract',path)
        self.module=importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules,{'FreeCAD':app,'FreeCADGui':gui,'PySide':qt,
                                    'shiboken6':NS(isValid=lambda value:not value.deleted)}):
            spec.loader.exec_module(self.module)

    def begin(self, line_only=True):
        operation=self.module.TrussReferenceSelection(self.panel,line_only=line_only)
        self.panel._reference_selection=operation
        operation.start()
        return operation

    def click(self, operation, sub='Edge1'):
        self.selection[:]=[NS(Object=self.source,SubElementNames=(sub,) if sub else ())]
        operation.addSelection('Trusses','Line',sub)

    def flush(self):
        for callback in self.queue[:]: callback()
        self.queue.clear()

    def assert_clean(self, operation):
        self.assertTrue(operation.closed)
        self.assertFalse(self.observers)
        self.assertFalse(self.doc_observers)
        self.assertIsNone(self.panel._reference_selection)
        self.assertEqual(self.config,self.before)

    def test_button_first_attaches_and_delivers_after_native_dispatch(self):
        operation=self.begin()
        self.assertEqual(self.observers,[operation])
        self.click(operation)
        self.assertFalse(self.applied)
        self.flush()
        self.assertEqual(self.applied[0]['reference_source'],'Line')
        self.assert_clean(operation)

    def test_valid_preselection_remains_available_without_observers(self):
        self.selection[:]=[NS(Object=self.source,SubElementNames=())]
        operation=self.begin()
        self.assertEqual(len(self.applied),1)
        self.assert_clean(operation)

    def test_escape_only_cancels_capture_and_can_repeat(self):
        for _ in range(3):
            operation=self.begin()
            shortcut=operation.shortcut
            shortcut.activated.callback()
            self.assertFalse(shortcut.enabled)
            self.assertTrue(shortcut.deleted)
            self.assert_clean(operation)
        self.assertFalse(self.applied)

    def test_rejected_selection_keeps_capture_and_previous_draft(self):
        operation=self.begin()
        self.error='Fonte inválida'
        self.click(operation)
        self.flush()
        self.assertFalse(operation.closed)
        self.assertIn('Fonte inválida',operation.prompt)
        self.assertEqual(self.config,self.before)
        self.error=None
        self.click(operation)
        self.flush()
        self.assert_clean(operation)

    def test_queued_selection_cannot_survive_cancel(self):
        operation=self.begin()
        self.click(operation)
        operation.cancel()
        self.flush()
        self.assertFalse(self.applied)
        self.assert_clean(operation)

    def test_last_explicit_edge_wins_over_other_selected_objects(self):
        operation=self.begin(line_only=False)
        self.selection[:]=[NS(Object=NS(Name='Other',Document=self.document),SubElementNames=('Edge1',)),
                           NS(Object=self.source,SubElementNames=('Edge1','Edge2'))]
        operation.addSelection('Trusses','Line','Edge2')
        self.flush()
        self.assertEqual(self.last_selection[0].SubElementNames,('Edge2',))
        self.assert_clean(operation)

    def test_rectangle_requires_explicit_edge_in_acquisition(self):
        operation=self.begin(line_only=False)
        self.mode='DraftRectangle'
        self.click(operation,sub='')
        self.flush()
        self.assertFalse(operation.closed)
        self.assertIn('explicitamente',operation.prompt)
        self.assertFalse(self.applied)
        self.click(operation,sub='Edge1')
        self.flush()
        self.assert_clean(operation)

    def test_line_mode_rejects_other_modes_without_mutation(self):
        operation=self.begin()
        self.mode='DraftRectangle'
        self.click(operation)
        self.flush()
        self.assertIn('Linha Draft',operation.prompt)
        self.assertFalse(self.applied)
        operation.cancel()
        self.assert_clean(operation)

    def test_foreign_selection_does_not_apply(self):
        operation=self.begin()
        operation.addSelection('Foreign','Line','Edge1')
        self.assertFalse(self.queue)
        self.assertIn('documento da treliça',operation.prompt)
        operation.cancel()
        self.assert_clean(operation)

    def test_persistent_conflict_blocks_adoption_without_mutation(self):
        operation=self.begin()
        self.panel.controller.bind_session=lambda _config:(_ for _ in ()).throw(ValueError('Conflito externo'))
        self.click(operation)
        self.flush()
        self.assertFalse(operation.closed)
        self.assertFalse(self.applied)
        self.assertIn('Conflito externo',operation.prompt)
        operation.cancel()
        self.assert_clean(operation)

    def test_switch_document_detaches_and_late_notification_is_inert(self):
        operation=self.begin()
        operation.slotActivateDocument(object())
        self.click(operation)
        self.assertFalse(self.queue)
        self.assert_clean(operation)

    def test_close_document_detaches(self):
        operation=self.begin()
        operation.slotDeletedDocument(self.document)
        self.assert_clean(operation)

    def test_cleanup_after_qt_parent_destruction_is_idempotent(self):
        operation=self.begin()
        operation.shortcut.deleted=True
        operation.close(refresh=False)
        operation.close()
        self.assert_clean(operation)


if __name__=='__main__': unittest.main()
