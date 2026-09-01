"""Contracts for the transient 3D preview used by SourceAxis member creation."""

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INTERACTIVE = ROOT / "freecad/SteelStructures/interactive"


class MemberSourceAxisPreviewContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.member = (INTERACTIVE / "draft_member_tool.py").read_text(encoding="utf-8")
        cls.column = (INTERACTIVE / "draft_column_tool.py").read_text(encoding="utf-8")
        cls.preview = (INTERACTIVE / "member_creation_preview.py").read_text(
            encoding="utf-8"
        )

    def test_member_source_axis_creates_transient_preview_without_view_callback(self):
        self.assertIn('"SteelStructuresMemberPreview"', self.member)
        self.assertIn("configure_preview_object(self.obj)", self.member)
        self.assertIn("self._update_source_axis_preview()", self.member)
        source_branch = self.member.split("if self.axis_source is not None:", 1)[1].split(
            "else:", 1
        )[0]
        self.assertIn("self.call = None", source_branch)

    def test_interactive_member_keeps_native_draft_preview_path(self):
        self.assertIn('"SteelStructuresDraftPreview"', self.member)
        self.assertIn('self.view.addEventCallback("SoEvent", self.action)', self.member)

    def test_profile_insertion_rotation_and_color_signals_refresh_preview(self):
        connect = self.member.split("def _connect_source_axis_preview", 1)[1].split(
            "def _preview_options_changed", 1
        )[0]
        for control in (
                "category.currentTextChanged", "series.currentTextChanged",
                "profile.currentIndexChanged", "insertion.currentIndexChanged",
                "rotation.valueChanged", "colorChanged", "sectionGeometryModeChanged"):
            self.assertIn(control, connect)

    def test_link_toggle_updates_but_does_not_change_preview_axis(self):
        link = self.member.split("def _axis_link_changed", 1)[1].split(
            "def _connect_source_axis_preview", 1
        )[0]
        self.assertIn("self._update_source_axis_preview()", link)
        self.assertNotIn("linked", link.split("\n", 1)[1])
        update = self.member.split("def _update_source_axis_preview", 1)[1].split(
            "def _install_source_axis_create_button", 1
        )[0]
        self.assertIn("resolved.start, resolved.end", update)

    def test_preview_uses_shared_member_geometry_pipeline_and_offsets(self):
        for contract in (
                "_section_face(profile, section_geometry_mode)",
                "_insertion_translation(profile, insertion, section_geometry_mode)",
                "_member_frame_rotation(direction)", "offset_x", "offset_y",
                "PREVIEW_TRANSPARENCY = 65", "ShowInTree = False",
                "Selectable = False"):
            self.assertIn(contract, self.preview)
        self.assertIn("str(section_geometry_mode)", self.preview)
        self.assertIn("update_member_preview", self.column)
        self.assertIn("update_member_preview", self.member)

    def test_preview_is_removed_on_create_close_and_failure(self):
        self.assertIn("self.removeTemporaryObject()", self.member)
        failure = self.member.split("def _confirm_axis_source", 1)[1].split(
            "def _apply_point_stage_ui", 1
        )[0]
        self.assertIn("self._terminate_native_session()", failure)
        removal = self.member.split("def removeTemporaryObject", 1)[1]
        self.assertIn("todo.ToDo.delay(self.doc.removeObject, name)", removal)
        column_failure = self.column.split("def _confirm_axis_source", 1)[1].split(
            "def finish", 1
        )[0]
        self.assertIn("if not self._create_from_options(options):", column_failure)
        self.assertIn("self._terminate_native_session()", column_failure)

    def test_preview_update_never_creates_persistent_member(self):
        update = self.member.split("def _update_source_axis_preview", 1)[1].split(
            "def _install_source_axis_create_button", 1
        )[0]
        self.assertNotIn("controller.create", update)
        self.assertNotIn("openTransaction", update)


if __name__ == "__main__":
    unittest.main()
