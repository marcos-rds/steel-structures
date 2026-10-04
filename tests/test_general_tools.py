"""Behavioral tests for native Draft General Tools integration."""

from __future__ import annotations

import importlib.util
import sys
import types
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "freecad/SteelStructures"


class Workbench:
    def __init__(self):
        self.toolbars = []
        self.menus = []

    def appendToolbar(self, title, commands):
        self.toolbars.append((title, list(commands)))

    def appendMenu(self, title, commands):
        self.menus.append((title, list(commands)))


class Move:
    activated = []

    def __init__(self):
        self.copymode = False

    def Activated(self):
        self.activated.append(self.copymode)


class GeneralToolsTests(unittest.TestCase):
    def setUp(self):
        self.package_name = "_general_tools_test"
        package = types.ModuleType(self.package_name)
        package.__path__ = [str(PACKAGE)]
        self.registered = {
            "Draft_Move": object(), "Draft_Rotate": object(), "Draft_Clone": object()
        }
        self.warnings = []
        self.add_calls = []
        self.run_calls = []
        def add_command(name, command):
            self.add_calls.append(name)
            self.registered[name] = command
        self.gui = types.SimpleNamespace(
            Workbench=Workbench,
            Control=types.SimpleNamespace(clearTaskWatcher=lambda: None),
            listCommands=lambda: list(self.registered),
            addCommand=add_command,
            runCommand=lambda name: self.run_calls.append(name),
            addWorkbench=lambda workbench: setattr(self, "workbench", workbench),
            activeWorkbench=lambda: None,
        )
        app = types.ModuleType("FreeCAD")
        app.Gui = self.gui
        app.ActiveDocument = object()
        app.activeDraftCommand = None
        app.Console = types.SimpleNamespace(PrintWarning=self.warnings.append)
        paths = types.ModuleType(f"{self.package_name}.paths")
        paths.WORKBENCH_ICON = "workbench.svg"
        paths.MEMBER_ICON = "member.svg"
        paths.COLUMN_ICON = "column.svg"
        paths.GRID_COMMAND_ICON = "grid.svg"
        paths.ADJUST_MEMBER_ICON = "adjust.svg"
        draft_tools = types.ModuleType("DraftTools")
        draft_tools.Move = Move
        draftutils = types.ModuleType("draftutils")
        draftutils.init_tools = types.SimpleNamespace(
            get_draft_snap_commands=lambda: ["Draft_Snap_Endpoint"]
        )
        pyside = types.ModuleType("PySide")
        qtcore = types.ModuleType("PySide.QtCore")
        qtcore.QTimer = types.SimpleNamespace(singleShot=lambda _delay, callback: callback())
        qtcore.QT_TRANSLATE_NOOP = lambda _context, text: text
        pyside.QtCore = qtcore
        pyside.QtWidgets = types.SimpleNamespace(QMessageBox=types.SimpleNamespace())
        self.injected = {
            self.package_name: package, "FreeCAD": app, "DraftTools": draft_tools,
            "draftutils": draftutils, "PySide": pyside, "PySide.QtCore": qtcore,
            f"{self.package_name}.paths": paths,
        }
        self.previous = {name: sys.modules.get(name) for name in self.injected}
        sys.modules.update(self.injected)
        self.commands = self._load("commands")
        self.module = self._load("init_gui")

    def _load(self, short_name):
        name = f"{self.package_name}.{short_name}"
        spec = importlib.util.spec_from_file_location(name, PACKAGE / f"{short_name}.py")
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
        return module

    def tearDown(self):
        Move.activated.clear()
        for name in list(sys.modules):
            if name == self.package_name or name.startswith(self.package_name + "."):
                sys.modules.pop(name, None)
        for name, previous in self.previous.items():
            if previous is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = previous

    def test_native_ids_and_optional_copy_are_ordered_once(self):
        native_objects = {name: self.registered[name] for name in self.registered}
        result = self.module.load_general_tools(self.commands)
        self.assertEqual(result, ["Draft_Move", "SteelStructures_MoveCopy", "Draft_Rotate", "Draft_Clone"])
        self.assertEqual(len(result), len(set(result)))
        for name, command in native_objects.items():
            self.assertIs(self.registered[name], command)
        self.assertNotIn("SteelStructures_Move", self.registered)
        self.assertNotIn("SteelStructures_Rotate", self.registered)
        self.assertNotIn("SteelStructures_Clone", self.registered)

    def test_native_toolbar_ids_execute_through_gui_without_wrappers(self):
        for command in self.module.GENERAL_TOOLS_NATIVE:
            self.gui.runCommand(command)
        self.assertEqual(self.run_calls, list(self.module.GENERAL_TOOLS_NATIVE))

    def test_move_copy_registration_is_idempotent(self):
        self.assertTrue(self.commands.register_move_copy_command())
        self.assertTrue(self.commands.register_move_copy_command())
        self.assertEqual(self.add_calls.count("SteelStructures_MoveCopy"), 1)

    def test_move_copy_delegates_to_native_move_copy_mode_only(self):
        self.assertTrue(self.commands.register_move_copy_command())
        command = self.registered["SteelStructures_MoveCopy"]
        self.assertEqual(command.GetResources()["Pixmap"], "BIM_Copy")
        command.Activated()
        self.assertEqual(Move.activated, [True])
        self.assertFalse(hasattr(command, "move"))
        self.assertFalse(hasattr(command, "action"))

    def test_toolbar_menu_and_creation_commands_are_preserved(self):
        workbench = self.workbench
        workbench.Initialize()
        expected = ("Ferramentas Gerais", self.module.GENERAL_TOOLS_ORDER)
        self.assertIn(expected, [(title, tuple(items)) for title, items in workbench.toolbars])
        self.assertIn(expected, [(title, tuple(items)) for title, items in workbench.menus])
        self.assertIn(("Steel Structures", [
            "SteelStructures_CreateMember", "SteelStructures_CreateColumn",
            "SteelStructures_AdjustMember", "SteelStructures_CreateGrid",
            "SteelStructures_CreateTruss", "SteelStructures_CreatePlate"
        ]), workbench.menus)

    def test_repeated_activation_does_not_duplicate_bars(self):
        workbench = self.workbench
        workbench.Initialize(); before = (list(workbench.toolbars), list(workbench.menus))
        workbench.Activated(); workbench.Activated()
        self.assertEqual((workbench.toolbars, workbench.menus), before)

    def test_missing_draft_is_safe_and_warns_once(self):
        sys.modules["DraftTools"] = None
        self.registered.clear()
        self.module._draft_tools_warning_emitted = False
        self.assertEqual(self.module.load_general_tools(self.commands), [])
        self.assertEqual(self.module.load_general_tools(self.commands), [])
        self.assertEqual(len(self.warnings), 1)

    def test_copy_is_omitted_when_move_has_no_copy_mode(self):
        class MoveWithoutCopy:
            pass
        sys.modules["DraftTools"].Move = MoveWithoutCopy
        self.registered.pop("SteelStructures_MoveCopy", None)
        self.commands._move_copy_registered = False
        self.assertFalse(self.commands.register_move_copy_command())
        self.assertNotIn("SteelStructures_MoveCopy", self.registered)


if __name__ == "__main__":
    unittest.main()
