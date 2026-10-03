"""Integration contracts for SteelStructures_CreateColumn and its native Draft tool."""

from __future__ import annotations

import ast
import math
import types
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
COMMANDS = ROOT / "freecad/SteelStructures/commands.py"
TOOL = ROOT / "freecad/SteelStructures/interactive/draft_column_tool.py"
PREVIEW = ROOT / "freecad/SteelStructures/interactive/member_creation_preview.py"
GUI = ROOT / "freecad/SteelStructures/init_gui.py"
MEMBER = ROOT / "freecad/SteelStructures/member.py"
ICON = ROOT / "Resources/Icons/CreateColumn.svg"


class Vector:
    def __init__(self, x=0.0, y=0.0, z=0.0):
        if hasattr(x, "x"):
            x, y, z = x.x, x.y, x.z
        self.x, self.y, self.z = float(x), float(y), float(z)

    def sub(self, other):
        return Vector(self.x - other.x, self.y - other.y, self.z - other.z)

    @property
    def Length(self):
        return math.sqrt(self.x ** 2 + self.y ** 2 + self.z ** 2)


class ColumnCommandContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.commands = COMMANDS.read_text(encoding="utf-8")
        cls.tool = TOOL.read_text(encoding="utf-8")
        cls.preview = PREVIEW.read_text(encoding="utf-8")
        cls.gui = GUI.read_text(encoding="utf-8")

    def test_command_is_registered_with_portuguese_resources(self):
        self.assertIn('Gui.addCommand("SteelStructures_CreateColumn", CreateColumnCommand())', self.commands)
        self.assertIn('"MenuText": "Criar Pilar"', self.commands)
        self.assertIn("ponto de base", self.commands)

    def test_toolbar_and_menu_place_column_next_to_member(self):
        expected = '["SteelStructures_CreateMember", "SteelStructures_CreateColumn", "SteelStructures_AdjustMember", "SteelStructures_CreateGrid"]'
        self.assertIn(expected, self.gui)

    def test_icon_exists_and_is_valid_svg(self):
        self.assertTrue(ICON.is_file())
        self.assertIn("<svg", ICON.read_text(encoding="utf-8"))

    def test_column_and_member_share_one_session_slot(self):
        column = self.commands.split("class CreateColumnCommand", 1)[1].split(
            "class CreateGridCommand", 1
        )[0]
        self.assertIn("_member_session_is_active()", column)
        self.assertIn("_active_member_tool", column)
        self.assertNotIn("_active_column_tool", self.commands)

    def test_column_loads_its_native_draft_tool(self):
        self.assertIn("StructuralColumnDraftTool", self.commands)
        self.assertIn("_load_native_draft_tool(column=True)", self.commands)

    def test_tool_uses_native_line_snap_and_numeric_pipeline(self):
        self.assertIn("class StructuralColumnDraftTool(gui_lines.Line):", self.tool)
        self.assertIn("super().action(arg)", self.tool)
        self.assertIn("super().numericInput(numx, numy, numz)", self.tool)
        self.assertNotIn("workingPlane", self.tool)
        self.assertNotIn("camera", self.tool.lower())

    def test_one_acquired_base_creates_one_member(self):
        self.assertIn("before == 0 and len(self.node) == 1", self.tool)
        self.assertEqual(self.tool.count("self.controller.create("), 1)
        self.assertIn("self.column_panel.creation_options(base)", self.tool)

    def test_confirmation_uses_existing_member_controller(self):
        self.assertIn("MemberController", self.tool)
        self.assertNotIn("ColumnProxy", self.tool)
        self.assertNotIn("PillarProxy", self.tool)

    def test_preview_uses_real_profile_insertion_rotation_and_global_z(self):
        for statement in (
            "profile_catalog.get", "_section_face(profile, section_geometry_mode)",
            "_insertion_translation", "face.extrude(App.Vector(0.0, 0.0, length))",
            "App.Rotation(App.Vector(0.0, 0.0, 1.0)",
        ):
            self.assertIn(statement, self.preview)

    def test_preview_tracks_current_snapped_point(self):
        self.assertIn("self._current_hover_point = candidate", self.tool)
        self.assertIn("point = self._current_hover_point", self.tool)
        self.assertIn("obj.Placement = App.Placement(start, alignment.multiply(roll))", self.preview)

    def test_native_location_event_consumes_draft_snapped_point(self):
        action = self.tool.split("    def action(self, arg):", 1)[1].split(
            "    def numericInput", 1
        )[0]
        self.assertIn('arg.get("Type") == "SoLocation2Event"', action)
        self.assertIn("self._set_hover_point(self.point)", action)
        self.assertNotIn("arg[\"Position\"]", action)

    def test_preview_is_temporary_hidden_and_removed(self):
        self.assertIn('addObject("Part::Feature", "SteelStructuresColumnPreview")', self.tool)
        self.assertIn("ShowInTree = False", self.preview)
        self.assertIn("todo.ToDo.delay(self.doc.removeObject, name)", self.tool)

    def test_preview_is_excluded_from_snap_candidates_at_creation(self):
        activated = self.tool.split("    def Activated", 1)[1].split(
            "    def action", 1
        )[0]
        self.assertIn("configure_preview_object(self.obj)", activated)
        exclusion = self.tool.split("    def _keep_preview_unsnappable", 1)[1].split(
            "    def numericInput", 1
        )[0]
        self.assertIn("obj.ViewObject.Selectable = False", exclusion)

    def test_native_mouse_release_cannot_reenable_preview_snapping(self):
        action = self.tool.split("    def action(self, arg):", 1)[1].split(
            "    def _keep_preview_unsnappable", 1
        )[0]
        self.assertLess(action.index("super().action(arg)"),
                        action.index("self._keep_preview_unsnappable()"))

    def test_hover_does_not_create_members_transactions_or_preview_objects(self):
        hover = self.tool.split("    def _set_hover_point", 1)[1].split(
            "    def _preview_options_changed", 1
        )[0]
        for forbidden in ("controller.create", "openTransaction", "addObject", "recompute"):
            self.assertNotIn(forbidden, hover)

    def test_shape_is_cached_while_only_placement_moves(self):
        update = self.preview.split("def update_member_preview", 1)[1]
        self.assertIn("shape_signature != state.shape_signature", update)
        self.assertIn("placement_signature != state.placement_signature", update)
        self.assertIn("if shape_changed or placement_signature", update)
        self.assertLess(update.index("shape_signature !="), update.index("obj.Shape ="))

    def test_continue_preserves_panel_and_options(self):
        reset = self.tool.split("    def _reset_for_continue", 1)[1].split(
            "    def _terminate_native_session", 1
        )[0]
        self.assertIn("self.node = []", reset)
        for forbidden in ("self.column_panel =", "self.controller =", "ColumnTaskPanel("):
            self.assertNotIn(forbidden, reset)

    def test_continue_clears_confirmed_hover_before_next_move(self):
        reset = self.tool.split("    def _reset_for_continue", 1)[1].split(
            "    def _clear_hover_state", 1
        )[0]
        self.assertIn("self._clear_hover_state()", reset)
        clear = self.tool.split("    def _clear_hover_state", 1)[1].split(
            "    def _terminate_native_session", 1
        )[0]
        self.assertIn("self._current_hover_point = None", clear)
        self.assertIn("Visibility = False", clear)

    def test_continue_false_terminates_and_true_resets(self):
        confirm = self.tool.split("    def _confirm_base", 1)[1].split(
            "    def finish", 1
        )[0]
        self.assertIn("if self.ui.continueMode:", confirm)
        self.assertIn("self._reset_for_continue()", confirm)
        self.assertIn("self._terminate_native_session()", confirm)

    def test_escape_and_cancel_share_terminal_cleanup(self):
        finish = self.tool.split("    def finish", 1)[1].split(
            "    def _reset_for_continue", 1
        )[0]
        self.assertIn("self._terminate_native_session()", finish)
        terminal = self.tool.split("    def _terminate_native_session", 1)[1]
        self.assertIn("self.end_callbacks(call)", terminal)
        self.assertIn("self.removeTemporaryObject()", terminal)
        self.assertIn("gui_base_original.Creator.finish(self)", terminal)
        self.assertGreaterEqual(self.tool.count("self._clear_hover_state()"), 3)

    def test_column_schema_is_the_existing_structural_member_schema(self):
        member_source = MEMBER.read_text(encoding="utf-8")
        self.assertIn('ELEMENT_TYPES = ["Membro", "Pilar",', member_source)
        self.assertIn('addObject("Part::FeaturePython", "StructuralMember")', member_source)
        self.assertFalse((MEMBER.parent / "column.py").exists())

    def test_member_implementation_was_not_duplicated(self):
        tree = ast.parse(self.tool)
        classes = [node.name for node in tree.body if isinstance(node, ast.ClassDef)]
        self.assertEqual(classes, ["StructuralColumnDraftTool"])
        self.assertNotIn("StructuralMemberProxy", self.tool)


class ColumnHoverBehaviorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = TOOL.read_text(encoding="utf-8")
        tree = ast.parse(source)
        original = next(node for node in tree.body if isinstance(node, ast.ClassDef))

        action = next(node for node in original.body if isinstance(node, ast.FunctionDef)
                      and node.name == "action")
        action_class = ast.ClassDef(
            name="StructuralColumnDraftTool", bases=[ast.Name(id="FakeLine", ctx=ast.Load())],
            keywords=[], body=[action], decorator_list=[]
        )

        class FakeLine:
            def action(self, event):
                if event["Type"] == "SoLocation2Event":
                    self.point = Vector(event["snapped"])
                elif event["Type"] == "SoMouseButtonEvent" and event.get("State") == "UP":
                    self.obj.ViewObject.Selectable = True
                elif event["Type"] == "SoMouseButtonEvent":
                    self.node.append(Vector(event["snapped"]))
                return event["Type"]

        namespace = {"FakeLine": FakeLine}
        exec(compile(ast.fix_missing_locations(ast.Module(
            body=[action_class], type_ignores=[])), str(TOOL), "exec"), namespace)
        cls.ActionTool = namespace["StructuralColumnDraftTool"]

        methods = [next(node for node in original.body if isinstance(node, ast.FunctionDef)
                        and node.name == name)
                   for name in ("_points_equal", "_set_hover_point", "_clear_hover_state")]
        hover_class = ast.ClassDef(
            name="HoverTool", bases=[], keywords=[], body=methods, decorator_list=[]
        )
        namespace = {
            "App": types.SimpleNamespace(Vector=Vector),
            "PreviewState": lambda: None,
        }
        exec(compile(ast.fix_missing_locations(ast.Module(
            body=[hover_class], type_ignores=[])), str(TOOL), "exec"), namespace)
        cls.HoverTool = namespace["HoverTool"]

    def action_tool(self):
        tool = self.ActionTool()
        tool.node = []
        tool.point = None
        tool.hovered = []
        tool.confirmed = []
        tool.obj = types.SimpleNamespace(
            ViewObject=types.SimpleNamespace(Selectable=False)
        )
        tool.is_active = lambda: True
        tool._set_hover_point = lambda point: tool.hovered.append(Vector(point))
        tool._confirm_base = lambda point: tool.confirmed.append(Vector(point))
        tool._keep_preview_unsnappable = lambda: setattr(
            tool.obj.ViewObject, "Selectable", False
        )
        return tool

    def test_move_event_updates_hover_before_any_click(self):
        tool = self.action_tool()
        tool.action({"Type": "SoLocation2Event", "Position": (9, 9),
                     "snapped": Vector(1, 2, 3)})
        self.assertEqual(len(tool.hovered), 1)
        self.assertEqual((tool.hovered[0].x, tool.hovered[0].y, tool.hovered[0].z), (1, 2, 3))
        self.assertEqual(tool.confirmed, [])

    def test_distinct_moves_use_snapped_points_and_click_alone_confirms(self):
        tool = self.action_tool()
        tool.action({"Type": "SoLocation2Event", "Position": (100, 100),
                     "snapped": Vector(10, 20, 0)})
        tool.action({"Type": "SoLocation2Event", "Position": (200, 200),
                     "snapped": Vector(30, 40, 0)})
        self.assertEqual([(p.x, p.y) for p in tool.hovered], [(10, 20), (30, 40)])
        self.assertEqual(tool.confirmed, [])
        tool.action({"Type": "SoMouseButtonEvent", "State": "DOWN",
                     "snapped": Vector(30, 40, 0)})
        self.assertEqual(len(tool.confirmed), 1)

    def test_button_release_keeps_preview_out_of_snap_candidates(self):
        tool = self.action_tool()
        real_grid = types.SimpleNamespace(
            Name="StructuralGrid", ViewObject=types.SimpleNamespace(Selectable=True)
        )
        confirmed = types.SimpleNamespace(
            Name="StructuralMember", ViewObject=types.SimpleNamespace(Selectable=True)
        )
        document_objects = [real_grid, confirmed, tool.obj]
        candidates = lambda: [obj.Name for obj in document_objects
                              if obj.ViewObject.Selectable]
        self.assertEqual(candidates(), ["StructuralGrid", "StructuralMember"])
        tool.action({"Type": "SoMouseButtonEvent", "State": "UP",
                     "snapped": Vector()})
        self.assertFalse(tool.obj.ViewObject.Selectable)
        self.assertEqual(candidates(), ["StructuralGrid", "StructuralMember"])

    def test_identical_hover_is_ignored_and_new_hover_updates_same_tool(self):
        tool = self.HoverTool()
        tool._current_hover_point = None
        tool.updates = 0
        tool._update_preview = lambda: setattr(tool, "updates", tool.updates + 1)
        self.assertTrue(tool._set_hover_point(Vector(1, 2, 3)))
        self.assertFalse(tool._set_hover_point(Vector(1, 2, 3)))
        self.assertTrue(tool._set_hover_point(Vector(4, 5, 6)))
        self.assertEqual(tool.updates, 2)

    def test_hover_round_trip_p1_p2_p1_is_exact_and_history_independent(self):
        tool = self.HoverTool()
        tool._current_hover_point = None
        visited = []
        tool._update_preview = lambda: visited.append(
            (tool._current_hover_point.x, tool._current_hover_point.y,
             tool._current_hover_point.z)
        )
        for point in (Vector(10, 20, 0), Vector(30, 40, 0), Vector(10, 20, 0)):
            tool._set_hover_point(point)
        self.assertEqual(visited, [(10, 20, 0), (30, 40, 0), (10, 20, 0)])

    def test_clear_removes_hover_and_hides_only_temporary_preview(self):
        tool = self.HoverTool()
        tool._current_hover_point = Vector(1, 2, 3)
        tool._preview_state = object()
        view = types.SimpleNamespace(Visibility=True)
        tool.obj = types.SimpleNamespace(ViewObject=view)
        tool._clear_hover_state()
        self.assertIsNone(tool._current_hover_point)
        self.assertIsNone(tool._preview_state)
        self.assertFalse(view.Visibility)


if __name__ == "__main__":
    unittest.main()
