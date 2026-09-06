"""Static checks for the public native-Draft creation command."""

from __future__ import annotations

import ast
import importlib.util
import sys
import types
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
COMMANDS = ROOT / "freecad" / "SteelStructures" / "commands.py"
INTERACTIVE = ROOT / "freecad" / "SteelStructures" / "interactive"
LEGACY_MODULES = (
    "member_task_panel.py",
    "point_capture.py",
    "preview_tracker.py",
    "snap_adapter.py",
)


class NativeCommandTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = COMMANDS.read_text(encoding="utf-8")
        cls.tree = ast.parse(cls.source, filename=str(COMMANDS))

    def test_only_public_creation_command_is_registered(self):
        names = []
        for node in ast.walk(self.tree):
            if not isinstance(node, ast.Call) or len(node.args) < 2:
                continue
            if (
                isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "Gui"
                and node.func.attr == "addCommand"
                and isinstance(node.args[0], ast.Constant)
            ):
                names.append(node.args[0].value)
        self.assertEqual(names, [
            "SteelStructures_CreateMember", "SteelStructures_CreateColumn", "SteelStructures_CreateGrid",
            "SteelStructures_AdjustMember", "SteelStructures_ProfileBrowser", "SteelStructures_CreateTruss",
            "SteelStructures_UpdateTruss", "SteelStructures_MoveCopy"
        ])

    def test_command_loads_structural_member_draft_tool(self):
        self.assertIn("StructuralMemberDraftTool", self.source)
        self.assertIn("draft_native_available", self.source)
        self.assertIn("tool.Activated(", self.source)

    def test_command_initializes_official_draft_modules(self):
        self.assertIn("import DraftTools", self.source)
        self.assertIn("import DraftGui", self.source)
        self.assertIn('hasattr(Gui, "draftToolBar")', self.source)

    def test_command_has_no_legacy_numeric_interface(self):
        for forbidden in (
            "MemberTaskPanel",
            "MemberDialog",
            "_open_numeric_task_panel",
            "_run_numeric_" + "fallback",
            "start_automatic_capture",
        ):
            self.assertNotIn(forbidden, self.source)

    def test_draft_failure_reports_native_error_without_alternate_panel(self):
        self.assertIn("DraftInterfaceUnavailable", self.source)
        self.assertIn("Não foi possível iniciar a ferramenta nativa", self.source)
        member_source = self.source.split("class CreateGridCommand", 1)[0]
        self.assertNotIn("Gui.Control.showDialog", member_source)

    def test_close_helper_only_finishes_owned_native_tool(self):
        self.assertIn("tool.finish(cont=False)", self.source)
        self.assertNotIn("shutdown", self.source)

    def test_legacy_modules_are_removed(self):
        for filename in LEGACY_MODULES:
            with self.subTest(filename=filename):
                self.assertFalse((INTERACTIVE / filename).exists())

    def test_no_deleted_module_is_imported_by_runtime_package(self):
        runtime = "\n".join(
            path.read_text(encoding="utf-8")
            for path in (ROOT / "freecad").rglob("*.py")
        )
        for module in ("member_task_panel", "point_capture", "preview_tracker", "snap_adapter"):
            with self.subTest(module=module):
                self.assertNotIn(module, runtime)


class NativeCommandLifecycleTests(unittest.TestCase):
    def setUp(self):
        package_name = "_metal_command_test"
        package = types.ModuleType(package_name)
        package.__path__ = [str(COMMANDS.parent)]
        paths = types.ModuleType(f"{package_name}.paths")
        paths.MEMBER_ICON = "CreateMember.svg"
        paths.COLUMN_ICON = "CreateColumn.svg"
        paths.GRID_COMMAND_ICON = "CreateGrid.svg"
        paths.ADJUST_MEMBER_ICON = "AdjustMember.svg"

        self.console_errors = []
        self.console_warnings = []
        self.app = types.ModuleType("FreeCAD")
        self.app.ActiveDocument = object()
        self.app.activeDraftCommand = None
        self.app.Console = types.SimpleNamespace(
            PrintError=self.console_errors.append,
            PrintWarning=self.console_warnings.append,
        )
        self.app.newDocument = lambda _name: object()

        self.control = types.SimpleNamespace(
            activeDialog=lambda: None,
            clearTaskWatcher=lambda: None,
        )
        self.gui = types.SimpleNamespace(
            Control=self.control,
            draftToolBar=object(),
            getMainWindow=lambda: None,
            addCommand=lambda *_args: None,
        )
        self.app.Gui = self.gui
        self.warning_messages = []
        qtwidgets = types.SimpleNamespace(
            QMessageBox=types.SimpleNamespace(
                warning=lambda _parent, _title, text: self.warning_messages.append(text),
                information=lambda *_args: None,
            )
        )
        pyside = types.ModuleType("PySide")
        pyside.QtWidgets = qtwidgets
        draft_tools = types.ModuleType("DraftTools")
        draft_gui = types.ModuleType("DraftGui")
        injected = {
            package_name: package,
            f"{package_name}.paths": paths,
            "FreeCAD": self.app,
            "PySide": pyside,
            "DraftTools": draft_tools,
            "DraftGui": draft_gui,
        }
        self.previous = {name: sys.modules.get(name) for name in injected}
        sys.modules.update(injected)
        spec = importlib.util.spec_from_file_location(f"{package_name}.commands", COMMANDS)
        self.module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = self.module
        spec.loader.exec_module(self.module)
        self.package_name = package_name

    def tearDown(self):
        for name in list(sys.modules):
            if name == self.package_name or name.startswith(f"{self.package_name}."):
                sys.modules.pop(name, None)
        for name, old in self.previous.items():
            if old is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = old

    def tool_class(self, instances, fail=False):
        module = self.module
        app = self.app

        class Tool:
            def __init__(self, on_closed):
                self.on_closed = on_closed
                self.active = False
                self.finish_calls = 0
                self.abort_calls = 0
                instances.append(self)

            def Activated(self, **_kwargs):
                if fail:
                    raise RuntimeError("native activation failed")
                self.active = True
                app.activeDraftCommand = self

            def is_active(self):
                return self.active

            def finish(self, **_kwargs):
                self.finish_calls += 1
                self.active = False
                app.activeDraftCommand = None
                self.on_closed(self)

            def abort_activation(self, **_kwargs):
                self.abort_calls += 1
                self.active = False
                app.activeDraftCommand = None
                self.on_closed(self)

        return Tool

    def test_real_draft_import_failure_reports_error_without_opening_panel(self):
        def unavailable():
            raise self.module.DraftInterfaceUnavailable("Draft ausente")

        self.module._load_native_draft_tool = unavailable
        self.module.CreateMemberCommand().Activated()
        self.assertIsNone(self.module._active_member_tool)
        self.assertTrue(self.console_errors)
        self.assertIn("interface Draft indisponível", self.console_errors[-1])
        self.assertIn("Consulte a Vista de relatório", self.warning_messages[-1])
        self.assertNotIn("showDialog", vars(self.control))

    def test_terminal_close_allows_reopening_with_a_fresh_instance(self):
        instances = []
        self.module._load_native_draft_tool = lambda: self.tool_class(instances)
        command = self.module.CreateMemberCommand()
        command.Activated()
        first = self.module._active_member_tool
        self.assertTrue(self.module.close_member_tool())
        command.Activated()
        second = self.module._active_member_tool
        self.assertIsNot(first, second)
        self.assertEqual(first.finish_calls, 1)
        self.assertEqual(len(instances), 2)

    def test_second_activation_does_not_duplicate_active_native_session(self):
        instances = []
        self.module._load_native_draft_tool = lambda: self.tool_class(instances)
        command = self.module.CreateMemberCommand()
        command.Activated()
        current = self.module._active_member_tool
        command.Activated()
        self.assertIs(self.module._active_member_tool, current)
        self.assertEqual(len(instances), 1)

    def test_unexpected_activation_error_is_reported_and_partial_session_cleared(self):
        instances = []
        self.module._load_native_draft_tool = lambda: self.tool_class(instances, fail=True)
        self.module.CreateMemberCommand().Activated()
        self.assertIsNone(self.module._active_member_tool)
        self.assertGreaterEqual(instances[0].abort_calls, 1)
        self.assertIn("falha inesperada", self.console_errors[0])
        self.assertIn("native activation failed", self.console_errors[0])

    def test_unrelated_active_task_dialog_blocks_native_activation(self):
        self.control.activeDialog = lambda: object()
        called = []
        self.module._load_native_draft_tool = lambda: called.append(True)
        self.module.CreateMemberCommand().Activated()
        self.assertEqual(called, [])
        self.assertIsNone(self.module._active_member_tool)


if __name__ == "__main__":
    unittest.main()
