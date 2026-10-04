"""CreatePlate command selection and session ownership with controlled modules."""

import importlib.util
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch


COMMANDS = Path(__file__).resolve().parents[1] / "freecad/SteelStructures/commands.py"


class PlateCommandTests(unittest.TestCase):
    def setUp(self):
        self.package_name = "_plate_command_test"
        package = types.ModuleType(self.package_name)
        package.__path__ = [str(COMMANDS.parent)]
        paths = types.SimpleNamespace(
            MEMBER_ICON="member.svg", COLUMN_ICON="column.svg",
            GRID_COMMAND_ICON="grid.svg", ADJUST_MEMBER_ICON="adjust.svg")
        self.document = types.SimpleNamespace(opened=0)
        self.gui = types.SimpleNamespace(
            Control=types.SimpleNamespace(
                activeDialog=lambda: None,
                showDialog=lambda panel: setattr(self, "shown", panel),
                closeDialog=lambda: None),
            Selection=types.SimpleNamespace(),
            addCommand=lambda *_args: None,
            getMainWindow=lambda: None)
        app = types.SimpleNamespace(
            ActiveDocument=self.document, Gui=self.gui,
            Console=types.SimpleNamespace(PrintWarning=lambda _text: None,
                                          PrintError=lambda _text: None))
        qt = types.SimpleNamespace(QMessageBox=types.SimpleNamespace(
            warning=lambda *_args: None))
        modules = {self.package_name: package,
                   self.package_name + ".paths": paths,
                   "FreeCAD": app, "PySide": types.SimpleNamespace(QtWidgets=qt)}
        self.modules = patch.dict(sys.modules, modules)
        self.modules.start()
        self.addCleanup(self.modules.stop)
        spec = importlib.util.spec_from_file_location(self.package_name + ".commands", COMMANDS)
        self.module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = self.module
        spec.loader.exec_module(self.module)

    def tearDown(self):
        for name in tuple(sys.modules):
            if name.startswith(self.package_name + "."):
                sys.modules.pop(name, None)

    def test_plate_command_uses_preselected_draft_without_point_capture(self):
        source = object()
        selection = types.SimpleNamespace(Object=source, SubElementNames=[])
        self.gui.Selection.getSelectionEx = lambda: [selection]
        controller_module = types.ModuleType(
            self.package_name + ".interactive.plate_controller")
        panel_module = types.ModuleType(
            self.package_name + ".interactive.plate_task_panel")
        planes_module = types.ModuleType(self.package_name + ".plate_planes")
        planes_module.selected_plane_face = lambda _items, _document: None
        calls = []

        def select_source(items, document):
            self.assertEqual(items, [selection])
            self.assertIs(document, self.document)
            return source, "DraftRectangle"

        class Controller:
            def __init__(self, document, source, source_mode, plane_face=None):
                calls.append((document, source, source_mode, plane_face))
                self.cancelled = False

            def cancel(self):
                self.cancelled = True

        class Panel:
            def __init__(self, controller, on_close):
                self.controller = controller
                self.on_close = on_close
                self._closed = False

            def reject(self):
                self.controller.cancel()
                self._closed = True
                self.on_close(self, False)

        controller_module.selected_plate_source = select_source
        controller_module.PlateController = Controller
        panel_module.PlateTaskPanel = Panel
        inserted = {controller_module.__name__: controller_module,
                    panel_module.__name__: panel_module,
                    planes_module.__name__: planes_module}
        previous = {name: sys.modules.get(name) for name in inserted}
        sys.modules.update(inserted)
        try:
            self.module.CreatePlateCommand().Activated()
            panel = self.module._active_plate_panel
            self.assertEqual(calls, [(self.document, source, "DraftRectangle", None)])
            self.assertIs(self.shown, panel)
            self.assertEqual(self.document.opened, 0)
            self.assertTrue(self.module.close_plate_panel())
            self.assertTrue(panel.controller.cancelled)
            self.assertIsNone(self.module._active_plate_panel)
            face = object()
            controller_module.selected_plate_source = lambda _items, _document: (None, None)
            planes_module.selected_plane_face = lambda _items, _document: face
            self.module.CreatePlateCommand().Activated()
            self.assertEqual(calls[-1], (self.document, None, None, face))
            self.assertTrue(self.module.close_plate_panel())
        finally:
            for name, old in previous.items():
                if old is None:
                    sys.modules.pop(name, None)
                else:
                    sys.modules[name] = old


if __name__ == "__main__":
    unittest.main()
