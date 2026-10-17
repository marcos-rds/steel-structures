"""Reference actions/captions are a presentation of the existing truss draft."""
from copy import deepcopy
import sys
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch

from tests.test_truss_task_panel import make_panel, panel_module


class Widget:
    def __init__(self): self.visible = True; self.text = ''
    def setVisible(self, value): self.visible = value
    def setText(self, value): self.text = value


class ReferenceControlTests(unittest.TestCase):
    def setUp(self):
        self.panel=make_panel()
        self.panel.draft_reference_actions=Widget()
        self.panel.pick_button=Widget()
        self.panel.source_label=Widget()
        self.source=NS(Name='Line001',Label='Eixo principal')
        self.document=NS(getObject=lambda name:self.source if name=='Line001' else None)
        self.source.Document=self.document
        self.panel.document=self.document
        self.panel.session.config.update(reference_mode='DraftLine',reference_source='Line001')
        self.line_check=patch('freecad.SteelStructures.truss_reference.is_draft_line',lambda source:source is self.source)
        self.line_check.start()
        self.addCleanup(self.line_check.stop)

    def test_two_points_has_only_original_point_action(self):
        self.panel._sync_reference_actions('TwoPoints')
        self.assertFalse(self.panel.draft_reference_actions.visible)
        self.assertTrue(self.panel.pick_button.visible)
        self.assertEqual(self.panel.pick_button.text,'Selecionar dois pontos')

    def test_draft_line_has_pair_of_actions_without_point_action(self):
        self.panel._sync_reference_actions('DraftLine')
        self.assertTrue(self.panel.draft_reference_actions.visible)
        self.assertFalse(self.panel.pick_button.visible)

    def test_rectangle_and_three_points_keep_their_existing_action(self):
        for mode,text in [('DraftRectangle','Usar seleção Draft'),('ThreePoints','Selecionar três pontos')]:
            self.panel._sync_reference_actions(mode)
            self.assertFalse(self.panel.draft_reference_actions.visible)
            self.assertTrue(self.panel.pick_button.visible)
            self.assertEqual(self.panel.pick_button.text,text)

    def test_caption_uses_label_and_does_not_change_the_draft(self):
        before=deepcopy(self.panel.session.config)
        self.panel._sync_reference_source()
        self.assertEqual(self.panel.source_label.text,'Referência selecionada: Eixo principal')
        self.assertEqual(self.panel.session.config,before)
        self.source.Label=''
        self.panel._sync_reference_source()
        self.assertTrue(self.panel.source_label.text.endswith('Line001'))

    def test_missing_deleted_or_foreign_source_never_leaves_old_name(self):
        self.panel._sync_reference_source()
        self.document.getObject=lambda name:None
        self.panel._sync_reference_source()
        self.assertEqual(self.panel.source_label.text,'Nenhuma linha selecionada')
        self.document.getObject=lambda name:self.source
        self.source.Document=object()
        self.panel._sync_reference_source()
        self.assertEqual(self.panel.source_label.text,'Nenhuma linha selecionada')
        self.source.Document=self.document
        self.panel._sync_reference_source(excluded=self.source)
        self.assertEqual(self.panel.source_label.text,'Nenhuma linha selecionada')

    def test_two_points_hides_caption(self):
        self.panel.session.config['reference_mode']='TwoPoints'
        self.panel._sync_reference_source()
        self.assertFalse(self.panel.source_label.visible)

    def test_line_only_selection_rejects_rectangle_before_changing_reference(self):
        before=deepcopy(self.panel.session.config)
        self.panel.controller.selected_reference=lambda:dict(reference_mode='DraftRectangle',reference_source='Rectangle')
        self.panel._select_draft_reference(line_only=True)
        self.assertEqual(self.panel.session.config,before)
        self.assertIn('Linha Draft',self.panel.message.text)

    def test_invalid_geometry_is_rejected_before_mutating_draft_or_widgets(self):
        before=deepcopy(self.panel.session.config)
        self.panel.controller.reference_geometry=lambda _config:(_ for _ in ()).throw(ValueError('Degenerada'))
        with self.assertRaisesRegex(ValueError,'Degenerada'):
            self.panel._adopt_selected_reference(dict(reference_mode='DraftLine',reference_source='Other',reference_edge='Edge1'))
        self.assertEqual(self.panel.session.config,before)

    def test_incompatible_custom_envelope_is_rejected_before_mutation(self):
        self.panel.session.config['custom_topology']={'envelope_type':'DuoPitch'}
        before=deepcopy(self.panel.session.config)
        self.panel.controller.reference_geometry=lambda _config:dict(envelope_type='Parallel')
        with self.assertRaisesRegex(ValueError,'Custom preservado'):
            self.panel._adopt_selected_reference(dict(reference_mode='DraftRectangle',reference_source='Rectangle',reference_edge='Edge2'))
        self.assertEqual(self.panel.session.config,before)

    def test_presentation_observer_updates_and_detaches_idempotently(self):
        observers=[]
        app=NS(addDocumentObserver=observers.append,removeDocumentObserver=observers.remove)
        self.panel.form=NS(destroyed=NS(connect=lambda callback:None))
        with patch.dict(sys.modules,{'FreeCAD':app}):
            observer=panel_module._ReferenceSourceObserver(self.panel)
        self.source.Label='Eixo renomeado'
        observer.slotChangedObject(self.source,'Label')
        self.assertTrue(self.panel.source_label.text.endswith('Eixo renomeado'))
        observer.slotDeletedObject(self.source)
        self.assertEqual(self.panel.source_label.text,'Nenhuma linha selecionada')
        observer.slotRedoDocument(self.document)
        self.assertTrue(self.panel.source_label.text.endswith('Eixo renomeado'))
        self.panel._suspended=True
        self.source.Label='Não apresentar durante suspensão'
        observer.slotChangedObject(self.source,'Label')
        self.assertTrue(self.panel.source_label.text.endswith('Eixo renomeado'))
        observer.close()
        observer.close()
        self.assertFalse(observers)
        self.source.Label='Não apresentar após fechar'
        observer.slotRecomputedDocument(self.document)
        self.assertTrue(self.panel.source_label.text.endswith('Eixo renomeado'))


if __name__=='__main__': unittest.main()
