"""Stable source contracts for the adjustment Task Panel."""

import ast
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PANEL = ROOT / "freecad/SteelStructures/interactive/member_adjustment_task_panel.py"


class MemberAdjustmentTaskPanelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = PANEL.read_text(encoding="utf-8")
        cls.tree = ast.parse(cls.source)

    def test_required_controls_and_portuguese_labels(self):
        for text in ("Recortar pelo plano", "Limitar comprimento", "Automático",
                     "Início", "Fim", "Selecionar referência", "Gap:",
                     "Manter vínculo com a referência", "Remover ajuste"):
            self.assertIn(text, self.source)

    def test_reference_and_member_capture_are_explicit(self):
        self.assertIn('_begin_capture("member")', self.source)
        self.assertIn('_begin_capture("reference")', self.source)
        self.assertIn("Gui.Selection.addObserver(observer)", self.source)
        self.assertIn("Gui.Selection.removeObserver(observer)", self.source)

    def test_cleanup_is_shared_by_accept_cancel_remove_and_close(self):
        self.assertIn("self._remove_selection_observer()", self.source)
        for method in ("accept", "reject", "remove_adjustment"):
            node = next(item for item in ast.walk(self.tree)
                        if isinstance(item, ast.FunctionDef) and item.name == method)
            self.assertIn("self._finish", ast.unparse(node))

    def test_panel_does_not_mutate_member_before_accept(self):
        init = next(item for item in ast.walk(self.tree)
                    if isinstance(item, ast.FunctionDef) and item.name == "__init__")
        text = ast.unparse(init)
        self.assertNotIn("controller.apply", text)
        self.assertNotIn("document.recompute", text)
        self.assertIn("controller.apply(resolved)", self.source)

    def test_geometry_change_revalidates_without_replacing_reference(self):
        self.assertIn("currentTextChanged.connect(self._configuration_changed)", self.source)
        self.assertNotIn("self.reference = None", ast.unparse(next(
            item for item in ast.walk(self.tree)
            if isinstance(item, ast.FunctionDef) and item.name == "_configuration_changed"
        )))

    def test_standard_ok_cancel_and_negative_gap(self):
        self.assertIn("button_box_type.Ok | button_box_type.Cancel", self.source)
        self.assertIn("self.gap.setRange(-1.0e9, 1.0e9)", self.source)
        self.assertIn("self.keep_reference.setChecked(True)", self.source)

    def test_dual_slot_drafts_preserve_independent_temporary_state(self):
        for text in ('self._drafts = {prefix: self._slot_draft(prefix)',
                     'self._drafts["Auto"]', 'self._save_active_draft()',
                     'self._load_draft(END_LABELS[label])'):
            self.assertIn(text, self.source)

    def test_initial_slot_is_always_auto(self):
        initializer = next(item for item in ast.walk(self.tree)
                           if isinstance(item, ast.FunctionDef) and item.name == "_initialize_drafts")
        text = ast.unparse(initializer)
        self.assertIn("self.end_choice.setCurrentText('Automático')", text)
        self.assertIn("self._load_draft('Auto')", text)
        self.assertNotIn("self._drafts['Start']['mode']", text)

    def test_reference_selection_prompt_depends_on_geometry_mode(self):
        description = next(item for item in ast.walk(self.tree)
                           if isinstance(item, ast.FunctionDef)
                           and item.name == "_reference_kind_description")
        description_text = ast.unparse(description)
        self.assertIn("uma Face plana", description_text)
        self.assertIn("uma Face plana ou uma Edge reta", description_text)
        method = next(item for item in ast.walk(self.tree)
                      if isinstance(item, ast.FunctionDef)
                      and item.name == "_reference_selection_prompt")
        text = ast.unparse(method)
        self.assertIn("Selecione %s na vista.", text)
        self.assertIn("self._reference_kind_description()", text)
        self.assertIn("self._reference_selection_prompt()", self.source)

    def test_reference_validation_prompt_depends_on_geometry_mode(self):
        method = next(item for item in ast.walk(self.tree)
                      if isinstance(item, ast.FunctionDef)
                      and item.name == "_reference_validation_prompt")
        text = ast.unparse(method)
        self.assertIn("Selecione %s.", text)
        self.assertIn("self._reference_kind_description()", text)
        self.assertIn("message = self._reference_validation_prompt()", self.source)

    def test_generic_controller_missing_reference_message_is_replaced(self):
        refresh = next(item for item in ast.walk(self.tree)
                       if isinstance(item, ast.FunctionDef) and item.name == "_refresh")
        text = ast.unparse(refresh)
        self.assertIn("Selecione uma Face plana ou uma Edge reta.", text)
        self.assertIn("message = self._reference_validation_prompt()", text)

    def test_slot_summary_is_compact_and_reference_is_per_draft(self):
        self.assertIn("Início: %s   •   Fim: %s", self.source)
        self.assertIn('self._drafts[self._active_choice]["reference"]', self.source)

    def test_remove_requires_or_resolves_one_slot(self):
        method = next(item for item in ast.walk(self.tree)
                      if isinstance(item, ast.FunctionDef) and item.name == "remove_adjustment")
        text = ast.unparse(method)
        self.assertIn("if choice == 'Auto'", text)
        self.assertIn("controller.remove_adjustment(choice)", text)


if __name__ == "__main__":
    unittest.main()
