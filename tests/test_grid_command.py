"""Behavioral command tests using explicit FreeCAD GUI doubles."""

from __future__ import annotations

import importlib.util
import sys
import types
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
COMMANDS = ROOT / "freecad/SteelStructures/commands.py"


class Document:
    def __init__(self):
        self.opened = self.committed = self.aborted = 0
        self.objects = []
        self.removed = []

    def openTransaction(self, name):
        self.opened += 1
        self.transaction_name = name

    def commitTransaction(self): self.committed += 1
    def abortTransaction(self): self.aborted += 1
    def removeObject(self, name):
        self.removed.append(name)
        self.objects = [obj for obj in self.objects if obj.Name != name]


class GridCommandTests(unittest.TestCase):
    def setUp(self):
        self.package_name = "_grid_command_test"
        package = types.ModuleType(self.package_name)
        package.__path__ = [str(COMMANDS.parent)]
        paths = types.ModuleType(self.package_name + ".paths")
        paths.MEMBER_ICON = "member.svg"
        paths.COLUMN_ICON = "column.svg"
        paths.GRID_COMMAND_ICON = "grid.svg"
        paths.ADJUST_MEMBER_ICON = "adjust.svg"
        self.document = Document()
        self.new_documents = []
        self.warnings, self.errors, self.registered = [], [], []
        self.app = types.ModuleType("FreeCAD")
        self.app.ActiveDocument = self.document
        self.app.activeDraftCommand = None
        self.app.newDocument = self._new_document
        self.app.Console = types.SimpleNamespace(PrintWarning=self.warnings.append, PrintError=self.errors.append)
        self.control = types.SimpleNamespace(activeDialog=lambda: None, showDialog=lambda panel: setattr(self, "shown", panel),
                                             closeDialog=lambda: setattr(self, "closed", True), clearTaskWatcher=lambda: None)
        self.gui = types.SimpleNamespace(Control=self.control, addCommand=lambda name, cmd: self.registered.append((name, cmd)),
                                         Selection=types.SimpleNamespace(clearSelection=lambda: None, addSelection=lambda _o: None),
                                         activeDocument=lambda: types.SimpleNamespace(activeView=lambda: types.SimpleNamespace(fitAll=lambda: None)),
                                         getMainWindow=lambda: None, draftToolBar=object())
        self.app.Gui = self.gui
        pyside = types.ModuleType("PySide")
        pyside.QtWidgets = types.SimpleNamespace(QMessageBox=types.SimpleNamespace(information=lambda *_a: None, warning=lambda *_a: None))
        injected = {self.package_name: package, self.package_name + ".paths": paths, "FreeCAD": self.app, "PySide": pyside}
        self.old = {name: sys.modules.get(name) for name in injected}
        sys.modules.update(injected)
        spec = importlib.util.spec_from_file_location(self.package_name + ".commands", COMMANDS)
        self.module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = self.module
        spec.loader.exec_module(self.module)
        self.created = []
        self.created_kwargs = []
        grid_module = types.ModuleType(self.package_name + ".grid")
        def create_grid(document, **kw):
            obj = types.SimpleNamespace(Name="StructuralGrid")
            self.created.append(obj)
            self.created_kwargs.append(kw)
            document.objects.append(obj)
            return obj
        grid_module.create_grid = create_grid
        self.grid_module = grid_module
        panel_module = types.ModuleType(self.package_name + ".interactive.grid_task_panel")
        outer = self
        class Panel:
            def __init__(self, document, obj, callback):
                self.document, self.grid_object, self.callback, self._closed = document, obj, callback, False
            def accept(self):
                self.document.commitTransaction(); self._closed = True; self.callback(self, True); return True
            def reject(self):
                self.document.removeObject(self.grid_object.Name)
                self.document.abortTransaction(); self._closed = True; self.callback(self, False); return True
        panel_module.GridTaskPanel = Panel
        sys.modules[grid_module.__name__] = grid_module
        sys.modules[panel_module.__name__] = panel_module

    def tearDown(self):
        for name in list(sys.modules):
            if name == self.package_name or name.startswith(self.package_name + "."):
                sys.modules.pop(name, None)
        for name, value in self.old.items():
            if value is None: sys.modules.pop(name, None)
            else: sys.modules[name] = value

    def _new_document(self, _name):
        self.document = Document(); self.app.ActiveDocument = self.document; self.new_documents.append(self.document); return self.document

    def test_registration_and_resources(self):
        self.assertEqual([name for name, _cmd in self.registered], [
            "SteelStructures_CreateMember", "SteelStructures_CreateColumn", "SteelStructures_CreateGrid",
            "SteelStructures_AdjustMember",
            "SteelStructures_ProfileBrowser", "SteelStructures_CreateTruss", "SteelStructures_UpdateTruss"
        ])
        resources = self.module.CreateGridCommand().GetResources()
        self.assertEqual(resources["Pixmap"], "grid.svg")
        self.assertEqual(resources["MenuText"], "Criar Grid")
        self.assertTrue(resources["ToolTip"])

    def test_creates_document_transaction_one_object_and_one_session(self):
        self.app.ActiveDocument = None
        command = self.module.CreateGridCommand(); command.Activated(); command.Activated()
        self.assertEqual((len(self.new_documents), self.document.opened, len(self.created)), (1, 1, 1))
        self.assertEqual(self.document.transaction_name, "Criar Grid Estrutural")
        self.assertEqual(
            {name: self.created_kwargs[0][name] for name in
             ("x_start_extension", "x_end_extension", "y_start_extension", "y_end_extension")},
            {"x_start_extension": 1000.0, "x_end_extension": 1000.0,
             "y_start_extension": 1000.0, "y_end_extension": 1000.0},
        )
        self.assertTrue(self.warnings)

    def test_accept_commits_and_clears_session(self):
        self.module.CreateGridCommand().Activated()
        panel = self.module._active_grid_panel
        self.assertTrue(panel.accept())
        self.assertEqual((self.document.committed, self.document.aborted), (1, 0))
        self.assertIsNone(self.module._active_grid_panel)

    def test_cancel_aborts_and_cleanup_is_idempotent(self):
        self.module.CreateGridCommand().Activated()
        self.assertTrue(self.module.close_grid_panel())
        self.assertFalse(self.module.close_grid_panel())
        self.assertEqual((self.document.committed, self.document.aborted), (0, 1))

    def test_active_foreign_dialog_blocks_creation(self):
        self.control.activeDialog = lambda: object()
        self.module.CreateGridCommand().Activated()
        self.assertFalse(self.created)

    def test_panel_creation_failure_removes_partial_aborts_and_allows_retry(self):
        panel_module = sys.modules[self.package_name + ".interactive.grid_task_panel"]
        good_panel = panel_module.GridTaskPanel
        panel_module.GridTaskPanel = lambda *_args: (_ for _ in ()).throw(RuntimeError("panel failed"))
        command = self.module.CreateGridCommand()
        command.Activated()
        self.assertEqual(self.document.removed, ["StructuralGrid"])
        self.assertEqual(self.document.objects, [])
        self.assertEqual(self.document.aborted, 1)
        self.assertIsNone(self.module._active_grid_panel)
        self.assertIn("panel failed", self.errors[-1])
        panel_module.GridTaskPanel = good_panel
        command.Activated()
        self.assertIsNotNone(self.module._active_grid_panel)
        self.assertEqual(len(self.document.objects), 1)

    def test_show_dialog_failure_cancels_panel_and_clears_session(self):
        self.control.showDialog = lambda _panel: (_ for _ in ()).throw(RuntimeError("show failed"))
        self.module.CreateGridCommand().Activated()
        self.assertEqual(self.document.removed, ["StructuralGrid"])
        self.assertEqual(self.document.aborted, 1)
        self.assertIsNone(self.module._active_grid_panel)
        self.assertIn("show failed", self.errors[-1])


if __name__ == "__main__":
    unittest.main()
