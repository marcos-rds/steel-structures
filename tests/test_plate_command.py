"""CreatePlate selection and unified session ownership with controlled modules."""

import builtins
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
        self.calls, self.controllers, self.panels, self.sessions = [], [], [], []
        self.registered, self.errors, self.warnings = {}, [], []
        self.dialog = self.source = self.source_mode = self.face = None
        self.fail_start = False
        self.selection = [object()]
        self.document = types.SimpleNamespace(Name="PlateDocument", opened=0)
        self.shown = None
        self.gui = types.SimpleNamespace(
            Control=types.SimpleNamespace(
                activeDialog=lambda: self.dialog,
                showDialog=lambda panel: setattr(self, "shown", panel),
                closeDialog=lambda: self.calls.append("close dialog"),
                clearTaskWatcher=lambda: self.calls.append("clear watchers")),
            Selection=types.SimpleNamespace(getSelectionEx=lambda: self.selection),
            addCommand=lambda name, command: self.registered.update({name: command}),
            getMainWindow=lambda: None)
        self.app = types.SimpleNamespace(
            ActiveDocument=self.document, Gui=self.gui, activeDraftCommand=None,
            newDocument=self._new_document,
            Console=types.SimpleNamespace(PrintWarning=self.warnings.append,
                                          PrintError=self.errors.append))
        package = types.ModuleType(self.package_name)
        package.__path__ = [str(COMMANDS.parent)]
        interactive = types.ModuleType(self.package_name + ".interactive")
        interactive.__path__ = []
        paths = types.SimpleNamespace(
            MEMBER_ICON="member.svg", COLUMN_ICON="column.svg",
            GRID_COMMAND_ICON="grid.svg", ADJUST_MEMBER_ICON="adjust.svg",
            PLATE_ICON="plate.svg")
        controller_module = types.ModuleType(self.package_name + ".interactive.plate_controller")
        panel_module = types.ModuleType(self.package_name + ".interactive.plate_task_panel")
        session_module = types.ModuleType(self.package_name + ".interactive.plate_creation_session")
        planes_module = types.ModuleType(self.package_name + ".plate_planes")
        controller_module.selected_plate_source = self._selected_source
        planes_module.selected_plane_face = self._selected_face
        harness = self

        class Controller:
            def __init__(self, document, source=None, source_mode=None, plane_face=None):
                harness.calls.append(("construct controller", document, source, source_mode, plane_face))
                harness.controllers.append(self)
                self.document, self.source = document, source
                self.source_mode, self.plane_face = source_mode, plane_face
                self.cancelled = False

            def cancel(self):
                self.cancelled = True

        class Panel:
            def __init__(self, controller, on_close):
                harness.panels.append(self)
                self.controller, self.on_close = controller, on_close
                self._closed = False

            def reject(self):
                self.controller.cancel()
                self._closed = True
                self.on_close(self, False)

        class Session:
            def __init__(self, document, plane_face=None, on_closed=None):
                harness.calls.append("construct native session")
                harness.sessions.append(self)
                self.document, self.plane_face = document, plane_face
                self.on_closed, self._closed = on_closed, False
                self.start_count = self.finish_count = 0

            def start(self):
                harness.calls.append("start native session")
                self.start_count += 1
                if harness.fail_start:
                    raise RuntimeError("native session start failed")

            def finish(self):
                self.finish_count += 1
                self._closed = True
                self.on_closed(self)

            def is_active(self):
                return not self._closed

        controller_module.PlateController = Controller
        panel_module.PlateTaskPanel = Panel
        session_module.PlateCreationSession = Session
        qt = types.SimpleNamespace(QMessageBox=types.SimpleNamespace(warning=lambda *_args: None))
        modules = {
            self.package_name: package,
            self.package_name + ".interactive": interactive,
            self.package_name + ".paths": paths,
            controller_module.__name__: controller_module,
            panel_module.__name__: panel_module,
            session_module.__name__: session_module,
            planes_module.__name__: planes_module,
            "FreeCAD": self.app, "PySide": types.SimpleNamespace(QtWidgets=qt),
            "DraftTools": types.ModuleType("DraftTools"), "DraftGui": types.ModuleType("DraftGui"),
        }
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

    def _selected_source(self, selection, document):
        self.assertIs(selection, self.selection)
        self.assertIs(document, self.app.ActiveDocument)
        return self.source, self.source_mode

    def _selected_face(self, selection, document):
        self.assertIs(selection, self.selection)
        self.assertIs(document, self.app.ActiveDocument)
        self.calls.append("capture selected face")
        return self.face

    def _new_document(self, name):
        self.calls.append(("new document", name))
        self.app.ActiveDocument = types.SimpleNamespace(Name=name, opened=0)
        return self.app.ActiveDocument

    def test_only_unified_plate_command_is_publicly_registered(self):
        self.assertIn("SteelStructures_CreatePlate", self.registered)
        self.assertNotIn("SteelStructures_CreatePlateRectangle", self.registered)

    def test_preselected_draft_sources_keep_controller_and_panel_without_native_capture(self):
        for source_mode in ("DraftRectangle", "DraftWire"):
            with self.subTest(source_mode=source_mode):
                self.source, self.source_mode = object(), source_mode
                self.module.CreatePlateCommand().Activated()
                panel = self.module._active_plate_panel
                self.assertIs(self.shown, panel)
                self.assertIs(panel.controller.document, self.document)
                self.assertIs(panel.controller.source, self.source)
                self.assertEqual(panel.controller.source_mode, source_mode)
                self.assertIsNone(panel.controller.plane_face)
                self.assertEqual(self.document.opened, 0)
                self.assertEqual(self.sessions, [])
                self.assertIsNone(self.module._active_plate_session)
                self.assertTrue(self.module.close_plate_panel())
                self.assertTrue(panel.controller.cancelled)
                self.assertIsNone(self.module._active_plate_panel)

    def test_no_source_starts_unified_native_session_with_face_and_official_draft(self):
        self.face = object()
        real_import = builtins.__import__
        imports = []

        def traced_import(name, *args, **kwargs):
            imports.append(name)
            if name in ("DraftTools", "DraftGui"):
                self.calls.append(("import", name))
            return real_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=traced_import):
            self.module.CreatePlateCommand().Activated()
        session = self.sessions[0]
        self.assertIs(self.module._active_plate_session, session)
        self.assertIs(session.document, self.document)
        self.assertIs(session.plane_face, self.face)
        self.assertEqual(session.start_count, 1)
        self.assertIsNone(self.module._active_plate_panel)
        self.assertEqual(self.controllers, [])
        self.assertEqual(self.panels, [])
        self.assertIn("DraftTools", imports)
        self.assertIn("DraftGui", imports)
        self.assertLess(self.calls.index(("import", "DraftGui")),
                        self.calls.index("construct native session"))
        self.assertLess(self.calls.index("clear watchers"),
                        self.calls.index("start native session"))
        self.assertEqual(self.errors, [])

    def test_no_face_uses_current_working_plane_session(self):
        self.module.CreatePlateCommand().Activated()
        self.assertIsNone(self.sessions[0].plane_face)
        self.assertEqual(self.controllers, [])

    def test_no_document_creates_document_before_native_session(self):
        self.app.ActiveDocument = None
        self.module.CreatePlateCommand().Activated()
        self.assertIn(("new document", "SteelStructures"), self.calls)
        self.assertIs(self.sessions[0].document, self.app.ActiveDocument)

    def test_existing_native_owner_prevents_duplicate_session(self):
        self.module.CreatePlateCommand().Activated()
        first = self.sessions[0]
        self.module.CreatePlateCommand().Activated()
        self.assertEqual(self.sessions, [first])
        self.assertEqual(first.start_count, 1)
        self.assertEqual(first.finish_count, 0)
        self.assertTrue(self.warnings)

    def test_existing_source_panel_prevents_duplicate_session(self):
        self.source, self.source_mode = object(), "DraftWire"
        self.module.CreatePlateCommand().Activated()
        panel = self.panels[0]
        self.source, self.source_mode = None, None
        self.module.CreatePlateCommand().Activated()
        self.assertEqual(self.panels, [panel])
        self.assertEqual(self.sessions, [])
        self.assertIs(self.module._active_plate_panel, panel)
        self.assertFalse(panel.controller.cancelled)
        self.assertTrue(self.warnings)

    def test_foreign_task_dialog_or_draft_command_prevents_creation(self):
        for dialog, command in ((object(), None), (None, object())):
            with self.subTest(dialog=dialog, command=command):
                self.dialog, self.app.activeDraftCommand = dialog, command
                self.module.CreatePlateCommand().Activated()
                self.assertEqual(self.sessions, [])
                self.assertEqual(self.controllers, [])
                self.assertEqual(self.calls, [])
                self.assertIsNone(self.module._active_plate_session)
        self.assertEqual(len(self.warnings), 2)

    def test_failed_start_finishes_partial_session_and_releases_owner(self):
        self.fail_start = True
        self.module.CreatePlateCommand().Activated()
        self.assertEqual(len(self.sessions), 1)
        self.assertEqual(self.sessions[0].finish_count, 1)
        self.assertIsNone(self.module._active_plate_session)
        self.assertIsNone(self.module._active_plate_panel)
        self.assertEqual(self.controllers, [])
        self.assertTrue(any("native session start failed" in error for error in self.errors))

    def test_stale_closed_callback_does_not_clear_new_native_owner(self):
        self.module.CreatePlateCommand().Activated()
        first = self.sessions[0]
        first.finish()
        self.module.CreatePlateCommand().Activated()
        second = self.sessions[1]
        self.module._plate_session_closed(first)
        self.assertIs(self.module._active_plate_session, second)
        self.assertEqual(second.finish_count, 0)

    def test_close_plate_panel_delegates_to_session_without_closing_foreign_dialog(self):
        self.module.CreatePlateCommand().Activated()
        session = self.sessions[0]
        self.assertTrue(self.module.close_plate_panel())
        self.assertEqual(session.finish_count, 1)
        self.assertIsNone(self.module._active_plate_session)
        self.assertFalse(self.module.close_plate_panel())
        self.assertNotIn("close dialog", self.calls)


if __name__ == "__main__":
    unittest.main()
