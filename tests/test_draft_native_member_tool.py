"""Architecture checks for the FreeCAD Draft-native member tool."""

import ast
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "freecad/SteelStructures/interactive/draft_member_tool.py"
OPTIONS = ROOT / "freecad/SteelStructures/interactive/profile_options_widget.py"
COMMANDS = ROOT / "freecad/SteelStructures/commands.py"


class DraftNativeArchitectureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = TOOL.read_text(encoding="utf-8")
        cls.options = OPTIONS.read_text(encoding="utf-8")
        cls.commands = COMMANDS.read_text(encoding="utf-8")
        cls.tree = ast.parse(cls.source)

    def test_tool_inherits_installed_draft_line(self):
        self.assertIn("class StructuralMemberDraftTool(gui_lines.Line):", self.source)

    def test_document_close_lifecycle_remains_owned_by_native_draft_tool(self):
        self.assertIn("class StructuralMemberDraftTool(gui_lines.Line):", self.source)
        self.assertNotIn("addDocumentObserver", self.source)
        self.assertNotIn("slotDeletedDocument", self.source)

    def test_native_line_ui_receives_profile_widget_as_extra(self):
        self.assertIn("self.ui.lineUi(", self.source)
        self.assertIn("extra=self.profile_options", self.source)

    def test_native_line_action_and_getpoint_path_are_reused(self):
        self.assertIn("result = super().action(arg)", self.source)
        self.assertNotIn("PointCapture", self.source)
        self.assertNotIn("SnapAdapter", self.source)
        self.assertNotIn("PreviewTracker", self.source)

    def test_only_native_soevent_callback_is_registered(self):
        self.assertEqual(self.source.count('addEventCallback("SoEvent", self.action)'), 1)
        self.assertNotIn("SoLocation2Event", self.source)

    def test_final_creation_uses_member_controller_not_draft_line_commit(self):
        self.assertIn("self.controller.create(", self.source)
        self.assertIn("gui_base_original.Creator.finish(self)", self.source)
        self.assertNotIn("Draft.make_wire", self.source)
        self.assertNotIn("Part::Line", self.source)

    def test_temporary_line_is_hidden_and_removed(self):
        self.assertIn("self.obj.ViewObject.ShowInTree = False", self.source)
        self.assertIn("self.removeTemporaryObject()", self.source)
        self.assertIn("self.doc.removeObject", self.source)

    def test_continue_is_native_and_defaults_enabled(self):
        self.assertIn("self.ui.continueMode = True", self.source)
        self.assertIn("self.ui.continueCmd.setChecked(self.ui.continueMode)", self.source)
        self.assertIn("self.ui.continueMode", self.source)

    def test_profile_widget_has_no_coordinate_controls(self):
        for forbidden in ("Ponto inicial", "Ponto final", "axis_constraint", "numeric_buffer"):
            self.assertNotIn(forbidden, self.options)

    def test_profile_widget_preserves_canonical_designation(self):
        self.assertIn("compact_profile_designation(designation), designation", self.options)
        self.assertIn("self.profile.currentData()", self.options)

    def test_profile_widget_integrates_the_shared_browser_once(self):
        self.assertIn("profile_browser_button = QtWidgets.QToolButton()", self.options)
        self.assertIn('profile_browser_button.setText("...")', self.options)
        self.assertIn("QtCore.Qt.ToolButtonTextOnly", self.options)
        self.assertIn('setToolTip("Abrir Catálogo de Perfis")', self.options)
        self.assertIn('setAccessibleName("Abrir Catálogo de Perfis")', self.options)
        self.assertIn("ProfileBrowserDialog.SELECT_MODE", self.options)
        self.assertIn("initial_profile_ref=self._current_profile_ref()", self.options)
        self.assertEqual(self.options.count("def _open_profile_browser"), 1)

    def test_profile_color_control_is_a_textless_accessible_swatch(self):
        self.assertIn('self.color_button = QtWidgets.QPushButton("")', self.options)
        self.assertIn('self.color_button.setToolTip("Escolher cor")', self.options)
        self.assertIn('self.color_button.setAccessibleName("Escolher cor")', self.options)
        self.assertNotIn('QPushButton("Escolher cor")', self.options)
        self.assertIn("self.color_button.clicked.connect(self._show_quick_color_menu)", self.options)
        self.assertIn("self.quick_color_menu.colorSelected.connect(self._apply_color)", self.options)
        self.assertIn("self.quick_color_menu.moreColorsRequested.connect(self._choose_color)", self.options)

    def test_browser_selection_updates_combos_atomically_and_notifies_profile_once(self):
        method = self.options.split("    def set_profile_ref", 1)[1].split(
            "    def _mark_custom_name", 1
        )[0]
        self.assertIn("widgets = (self.category, self.series, self.profile)", method)
        self.assertIn("widget.blockSignals(True)", method)
        self.assertEqual(method.count("currentIndexChanged.emit"), 1)
        for unrelated in ("insertion", "rotation", "_color", "element_type"):
            self.assertNotIn(f"self.{unrelated}", method)

    def test_command_uses_official_draft_initialization_without_legacy_panel(self):
        self.assertIn("import DraftTools", self.commands)
        self.assertIn("Não foi possível iniciar a ferramenta nativa", self.commands)
        self.assertNotIn("MemberTaskPanel", self.commands)
        member_source = self.commands.split("class CreateGridCommand", 1)[0]
        self.assertNotIn("Gui.Control.showDialog", member_source)
        self.assertNotIn("panel.start_automatic_capture", self.commands)

    def test_no_custom_axis_filter_or_preview_in_native_tool(self):
        for forbidden in ("eventFilter", "axis_constraint", "numeric_buffer", "SoSeparator"):
            self.assertNotIn(forbidden, self.source)

    def test_escape_is_delegated_entirely_to_native_line(self):
        self.assertNotIn("_cancel_current_segment", self.source)
        action = self.source.split("    def action(self, arg):", 1)[1].split(
            "    def numericInput", 1
        )[0]
        self.assertNotIn("SoKeyboardEvent", action)

    def test_registered_line_key_is_separate_from_preview_name(self):
        self.assertIn('Creator.Activated(self, "Line")', self.source)
        self.assertIn('addObject("Part::Feature", "SteelStructuresDraftPreview")', self.source)
        self.assertNotIn('Creator.Activated(self, "SteelStructuresDraftPreview")', self.source)

    def test_native_line_ui_is_initialized_once_per_activation(self):
        activated = self.source.split("    def Activated", 1)[1].split(
            "    def _apply_point_stage_ui", 1
        )[0]
        self.assertEqual(activated.count("self.ui.lineUi("), 1)

    def test_finish_schedules_toolbar_restore(self):
        self.assertIn("schedule_draft_snap_toolbar_visible()", self.source)

    def test_progressive_native_widgets_follow_confirmed_node_count(self):
        self.assertIn('_toolmsg("Selecione o primeiro ponto")', self.source)
        self.assertIn('_toolmsg("Selecione o próximo ponto")', self.source)
        for name in ("labellength", "lengthValue", "labelangle", "angleValue", "angleLock"):
            self.assertIn(f'"{name}"', self.source)
        self.assertIn("first = len(self.node) == 0", self.source)
        self.assertIn("self._update_point_input_stage()", self.source)

    def test_initial_stage_hides_length_and_angle_without_rebuilding_ui(self):
        self.assertIn('title="Criar elemento estrutural"', self.source)
        self.assertIn("widget.setVisible(not first)", self.source)
        self.assertEqual(self.source.count("self.ui.lineUi("), 1)

    def test_external_title_is_static_and_stage_guidance_uses_status_bar(self):
        self.assertIn('self.ui.baseWidget.setWindowTitle("Criar elemento estrutural")', self.source)
        stage = self.source.split("    def _apply_point_stage_ui", 1)[1].split(
            "    def _update_point_input_stage", 1
        )[0]
        self.assertNotIn("setWindowTitle", stage)
        self.assertIn('_toolmsg("Selecione o primeiro ponto")', stage)
        self.assertIn('_toolmsg("Selecione o próximo ponto")', stage)

    def test_profile_widget_has_no_internal_stage_label_or_empty_wrapper(self):
        self.assertIn("class ProfileOptionsWidget(QtWidgets.QGroupBox):", self.options)
        self.assertNotIn("set_stage_text", self.options)
        self.assertNotIn("set_point_stage", self.options)
        self.assertNotIn("_stage_label", self.options)
        self.assertNotIn("stage_font", self.options)
        self.assertIn('QtWidgets.QGroupBox("Identificação")', self.options)
        self.assertIn('QtWidgets.QGroupBox("Seleção do perfil")', self.options)
        self.assertIn("_OrientationPanel(", self.options)

    def test_continue_restores_first_point_status_without_rebuilding_widget(self):
        reset = self.source.split("    def _reset_segment_for_continue", 1)[1].split(
            "    def _terminate_native_session", 1
        )[0]
        self.assertNotIn("ProfileOptionsWidget", reset)
        self.assertIn("self._apply_point_stage_ui()", reset)
        self.assertIn('_toolmsg("Selecione o primeiro ponto")', self.source)

    def test_native_path_never_traverses_or_mutates_external_taskbox(self):
        for forbidden in (
            "_point_input_taskbox", "Gui::TaskView::TaskBox", "headerText",
            "findChild", "findChildren", "parent()", "parentWidget()",
            "metaObject", "QtWidgets",
        ):
            self.assertNotIn(forbidden, self.source)

    def test_member_icon_and_static_title_are_applied_at_activation(self):
        activated = self.source.split("    def Activated", 1)[1].split(
            "    def _apply_point_stage_ui", 1
        )[0]
        self.assertIn("baseWidget.setWindowIcon(QtGui.QIcon(self._task_icon))", activated)
        self.assertIn("icon or MEMBER_ICON", activated)
        self.assertNotIn('icon="Draft_Line"', activated)
        self.assertNotIn("self.Activated(icon=self._task_icon", self.source)

    def test_continue_resets_same_line_instance_without_terminal_cleanup(self):
        finish = self.source.split("    def finish", 1)[1].split(
            "    def _reset_segment_for_continue", 1
        )[0]
        self.assertNotIn("self.Activated(", finish)
        self.assertNotIn("self.ui.lineUi(", finish)
        self.assertIn("self._reset_segment_for_continue()", finish)
        self.assertNotIn("gui_base_original.Creator.finish(self)", finish)

    def test_external_continue_restart_has_been_removed(self):
        self.assertNotIn("def _member_draft_tool_continue", self.commands)
        self.assertNotIn("on_continue", self.commands)
        self.assertNotIn("on_continue", self.source)

    def test_creator_finish_and_close_notification_are_terminal_only(self):
        reset = self.source.split("    def _reset_segment_for_continue", 1)[1].split(
            "    def _terminate_native_session", 1
        )[0]
        terminal = self.source.split("    def _terminate_native_session", 1)[1].split(
            "    def abort_activation", 1
        )[0]
        for forbidden in (
            "Creator.finish", "lineUi", "offUi", "closeDialog",
            "_start_native_member_tool", "Activated", "removeTemporaryObject",
            "end_callbacks", "_notify_closed", "controller.stop",
        ):
            self.assertNotIn(forbidden, reset)
        self.assertEqual(terminal.count("gui_base_original.Creator.finish(self)"), 1)
        self.assertEqual(terminal.count("self._notify_closed()"), 1)

    def test_continue_preserves_native_session_objects_and_active_state(self):
        reset = self.source.split("    def _reset_segment_for_continue", 1)[1].split(
            "    def _terminate_native_session", 1
        )[0]
        for forbidden in (
            "self.ui =", "self.profile_options =", "self.controller =",
            "self.call =", "self.obj =", "TOOL_FINISHING", "TOOL_FINISHED",
        ):
            self.assertNotIn(forbidden, reset)
        self.assertNotIn("App.activeDraftCommand =", reset)

    def test_continue_resets_segment_constraints_and_native_values(self):
        reset = self.source.split("    def _reset_segment_for_continue", 1)[1].split(
            "    def _terminate_native_session", 1
        )[0]
        for statement in (
            "self.node = []", "self.point = None", "self.pos = []",
            "self.support = None", "self.constrain = None", "self.ui.mask = None",
            "Gui.Snapper.mask = None", "self.ui.reset_ui_values()",
        ):
            self.assertIn(statement, reset)
        for field in ("xValue", "yValue", "zValue", "lengthValue", "angleValue"):
            self.assertIn(f'"{field}"', reset)

    def test_continue_hides_but_keeps_preview_and_restores_first_stage(self):
        reset = self.source.split("    def _reset_segment_for_continue", 1)[1].split(
            "    def _terminate_native_session", 1
        )[0]
        self.assertIn("self.obj.ViewObject.Visibility = False", reset)
        self.assertIn("self._last_input_stage = None", reset)
        self.assertIn("self._apply_point_stage_ui()", reset)
        self.assertNotIn("removeObject", reset)

    def test_continue_uses_official_units_and_blocks_programmatic_signals(self):
        reset = self.source.split("    def _reset_segment_for_continue", 1)[1].split(
            "    def _terminate_native_session", 1
        )[0]
        self.assertIn("App.Units.Length", reset)
        self.assertIn("App.Units.Angle", reset)
        self.assertIn("blockSignals(True)", reset)
        self.assertIn("blockSignals(blocked)", reset)

    def test_official_toolbar_exists_before_tool_construction_and_activation(self):
        start = self.commands.split("def _start_native_member_tool", 1)[1].split(
            "def _member_draft_tool_continue", 1
        )[0]
        self.assertLess(start.index("import DraftGui"), start.index("tool = tool_class("))
        self.assertLess(start.index("tool = tool_class("), start.index("tool.Activated("))
        self.assertIn('hasattr(Gui, "draftToolBar")', start)
        self.assertLess(start.index("Gui.Control.clearTaskWatcher()"), start.index("tool = tool_class("))
        self.assertNotIn("clearTaskWatcher()", start.split("tool.Activated(", 1)[1])
        self.assertNotIn("tool.ui =", start)
        self.assertNotIn("DraftGui.DraftToolBar(", self.commands)

    def test_title_icon_and_progressive_controls_share_one_stage_operation(self):
        stage = self.source.split("    def _apply_point_stage_ui", 1)[1].split(
            "    def _update_point_input_stage", 1
        )[0]
        self.assertIn('_toolmsg("Selecione o primeiro ponto")', stage)
        self.assertIn('_toolmsg("Selecione o próximo ponto")', stage)
        self.assertIn("widget.setVisible(not first)", stage)
        for forbidden in ("TaskBox", "headerText", "findChild", "parent"):
            self.assertNotIn(forbidden, stage)

    def test_stage_update_is_idempotent_and_ignores_closed_tool(self):
        self.assertIn("if App.activeDraftCommand is not self or self.ui is None:", self.source)
        self.assertIn("if stage == self._last_input_stage:", self.source)
        self.assertIn("self._last_input_stage = stage", self.source)

    def test_native_mouse_action_completes_before_deferred_stage_update(self):
        action = self.source.split("    def action(self, arg):", 1)[1].split(
            "    def numericInput", 1
        )[0]
        self.assertLess(action.index("super().action(arg)"), action.index("_schedule_stage_update()"))

    def test_numeric_and_insert_button_path_schedule_after_native_processing(self):
        numeric = self.source.split("    def numericInput", 1)[1].split(
            "    def drawUpdate", 1
        )[0]
        self.assertLess(numeric.index("super().numericInput"), numeric.index("_schedule_stage_update()"))

    def test_deferred_updates_are_consolidated_and_generation_guarded(self):
        self.assertIn("if not self._tool_active or self._stage_update_pending:", self.source)
        self.assertIn("QtCore.QTimer.singleShot(0,", self.source)
        self.assertIn("if generation != self._stage_generation:", self.source)
        self.assertIn("self._stage_generation += 1", self.source)
        self.assertIn("self._tool_active = False", self.source)

    def test_native_instance_has_terminal_lifecycle_states(self):
        for state in ("TOOL_NEW", "TOOL_ACTIVE", "TOOL_FINISHING", "TOOL_FINISHED"):
            self.assertIn(state, self.source)
        self.assertIn("self._lifecycle_state != TOOL_NEW", self.source)
        self.assertIn("self._lifecycle_state = TOOL_FINISHING", self.source)
        self.assertIn("self._lifecycle_state = TOOL_FINISHED", self.source)

    def test_finish_is_idempotent_and_notifies_session_once(self):
        self.assertIn("if self._lifecycle_state in (TOOL_FINISHING, TOOL_FINISHED):", self.source)
        self.assertIn("if self._closed_notified:", self.source)
        self.assertIn("self._on_closed(self)", self.source)

    def test_partial_activation_has_explicit_native_cleanup(self):
        cleanup = self.source.split("    def abort_activation", 1)[1].split(
            "    def _notify_closed", 1
        )[0]
        self.assertIn("self.end_callbacks(call)", cleanup)
        self.assertIn("self.removeTemporaryObject()", cleanup)
        self.assertIn("gui_base_original.Creator.finish(self)", cleanup)
        self.assertIn("controller.stop()", cleanup)


if __name__ == "__main__":
    unittest.main()
