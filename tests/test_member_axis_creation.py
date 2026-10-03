"""Stable integration contracts for creation from a selected Draft Line."""

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "freecad/SteelStructures"


class MemberAxisCreationContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.commands = (PACKAGE / "commands.py").read_text(encoding="utf-8")
        cls.member = (PACKAGE / "member.py").read_text(encoding="utf-8")
        cls.controller = (PACKAGE / "interactive/member_controller.py").read_text(encoding="utf-8")
        cls.member_tool = (PACKAGE / "interactive/draft_member_tool.py").read_text(encoding="utf-8")
        cls.column_tool = (PACKAGE / "interactive/draft_column_tool.py").read_text(encoding="utf-8")
        cls.widget = (PACKAGE / "interactive/axis_source_widget.py").read_text(encoding="utf-8")

    def test_commands_normalize_exactly_one_preselected_line_for_both_tools(self):
        self.assertEqual(self.commands.count("axis_source_from_selection(selection_ex)"), 2)
        self.assertIn("axis_source=axis_source", self.commands)

    def test_checkbox_is_unchecked_by_default_and_shared_by_member_and_column(self):
        self.assertIn('QCheckBox("Manter v\u00ednculo com a linha")', self.widget)
        self.assertIn("self.keep_link.setChecked(False)", self.widget)
        self.assertIn("AxisSourceWidget", self.member_tool)
        self.assertIn("axis_source_controls", self.column_tool)

    def test_member_schema_has_independent_and_linked_axis_definition(self):
        self.assertIn('"AxisDefinitionMode"', self.member)
        self.assertIn('"App::PropertyLinkSub", "AxisSource"', self.member)
        self.assertIn('(\"Independent\", \"Linked\")', self.member)
        self.assertIn("self._sync_axis_from_source(obj)", self.member)

    def test_link_visibility_changes_inside_controller_transaction_only(self):
        hide = self.controller.index("source.ViewObject.Visibility = False")
        commit = self.controller.index("self.document.commitTransaction()")
        self.assertLess(hide, commit)
        self.assertIn("previous_visibility", self.controller)

    def test_source_is_never_owned_grouped_or_deleted(self):
        combined = self.member + self.controller + self.member_tool + self.column_tool
        for forbidden in ("addObject(source)", "claimChildren(source)", "removeObject(source"):
            self.assertNotIn(forbidden, combined)

    def test_member_and_column_both_forward_link_choice(self):
        self.assertIn("source, linked", self.member_tool)
        self.assertIn("CreationGeometryMode.SOURCE_AXIS", self.member_tool)
        self.assertIn("CreationGeometryMode.SOURCE_AXIS", self.column_tool)

    def test_source_axis_uses_standard_confirm_without_graphical_acquisition(self):
        for tool in (self.member_tool, self.column_tool):
            self.assertIn("configure_source_axis_draft_ui(self.ui)", tool)
            self.assertIn("self.call = None", tool)
            self.assertIn("install_source_axis_create_button(", tool)
            self.assertIn("remove_source_axis_create_button(", tool)
        self.assertNotIn("self.node = [App.Vector(resolved.start)]", self.member_tool)

    def test_source_axis_presentation_is_compact(self):
        profile = (PACKAGE / "interactive/profile_options_widget.py").read_text(
            encoding="utf-8"
        )
        self.assertIn('QLabel("Eixo: %s" % label)', self.widget)
        self.assertNotIn('QGroupBox("Origem")', self.widget)
        self.assertNotIn('QGroupBox("Identificação")', profile)
        self.assertNotIn('QGroupBox("Seleção do perfil")', profile)
        self.assertIn("self.orientation_panel", profile)

    def test_source_axis_hides_continue_and_native_point_controls(self):
        self.assertIn('"continueCmd"', self.widget)
        self.assertIn("ui.continueMode = False", self.widget)
        self.assertIn('QPushButton("Criar", button_box)', self.widget)
        self.assertIn('"SteelStructuresSourceAxisCreate"', self.widget)
        self.assertIn("QDialogButtonBox.ActionRole", self.widget)

    def test_column_panel_has_no_redundant_internal_pillar_title(self):
        column_panel = (PACKAGE / "interactive/column_task_panel.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("class ColumnTaskPanel(QtWidgets.QWidget):", column_panel)
        self.assertNotIn('super().__init__("Pilar", parent)', column_panel)
        self.assertIn('QGroupBox("Geometria")', column_panel)


if __name__ == "__main__":
    unittest.main()
