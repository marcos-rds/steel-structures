"""Face-picking ownership gates without a Coin callback or native snapper."""
import importlib.util
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch


MODULE = (Path(__file__).resolve().parents[1] / "freecad" / "SteelStructures"
          / "interactive" / "plate_face_selection.py")


class Widget:
    def __init__(self, *_args):
        self.destroyed = Mock()
        self.parent = None
        self.text = ""

    def setWindowTitle(self, title):
        self.title = title

    def setWordWrap(self, value):
        pass

    def setToolTip(self, value):
        self.tooltip = value

    def setStyleSheet(self, value):
        self.style = value

    def setText(self, value):
        self.text = value

    def inherits(self, name):
        return False

    def parentWidget(self):
        return self.parent


class FaceSelectionTests(unittest.TestCase):
    def setUp(self):
        self.document = types.SimpleNamespace(Name="PlateDoc")
        self.view = object()
        self.documents = {"PlateDoc": self.document}
        self.timers = []
        self.closed = Mock()
        self.app = types.ModuleType("FreeCAD")
        self.app.listDocuments = lambda: self.documents
        self.app.activeDraftCommand = None
        self.app.addDocumentObserver = Mock()
        self.app.removeDocumentObserver = Mock()
        self.app.Placement = lambda base, rotation: types.SimpleNamespace(Base=base, Rotation=rotation)
        self.gui = types.ModuleType("FreeCADGui")
        self.gui.getDocument = Mock(return_value=types.SimpleNamespace(
            mdiViewsOfType=lambda kind: [self.view]))
        self.gui.getMainWindow = lambda: types.SimpleNamespace(findChild=lambda kind: None)
        self.gui.Control = types.SimpleNamespace(
            activeDialog=Mock(return_value=False), showDialog=Mock(), closeDialog=Mock())
        self.gui.Selection = types.SimpleNamespace(
            addObserver=Mock(), removeObserver=Mock(), clearSelection=Mock(),
            getSelectionEx=Mock(return_value=[object()]))
        qt = types.ModuleType("PySide")
        qt.QtCore = types.SimpleNamespace(QObject=object, QEvent=types.SimpleNamespace(Close=19, Hide=18),
            Qt=types.SimpleNamespace(WindowShortcut=1),
            QTimer=types.SimpleNamespace(singleShot=lambda delay, callback: self.timers.append(callback)))
        self.shortcut = types.SimpleNamespace(activated=Mock(), setContext=Mock(),
            setEnabled=Mock(), deleteLater=Mock())
        self.shortcut_factory = Mock(return_value=self.shortcut)
        qt.QtGui = types.SimpleNamespace(QShortcut=self.shortcut_factory, QKeySequence=lambda key: key)
        qt.QtWidgets = types.SimpleNamespace(QWidget=Widget, QLabel=Widget,
            QVBoxLayout=lambda widget: types.SimpleNamespace(addWidget=Mock(), addStretch=Mock()),
            QMdiArea=object, QDialogButtonBox=types.SimpleNamespace(Cancel=1))
        shiboken = types.ModuleType("shiboken6")
        shiboken.isValid = lambda value: value is not None
        draft = types.ModuleType("draftutils")
        self.utils = types.SimpleNamespace(get_3d_view=lambda: self.view)
        draft.gui_utils = self.utils
        planes = types.ModuleType("_face_selection_tests.plate_planes")
        self.reference = object()
        self.placement = types.SimpleNamespace(Base=object(), Rotation=object())
        planes.selected_plane_face = Mock(return_value=self.reference)
        planes.placement_from_face = Mock(return_value=self.placement)
        self.planes = planes
        modules = {"FreeCAD": self.app, "FreeCADGui": self.gui, "PySide": qt,
                   "shiboken6": shiboken, "draftutils": draft,
                   "_face_selection_tests.plate_planes": planes}
        self.module_patch = patch.dict(sys.modules, modules)
        self.module_patch.start()
        self.addCleanup(self.module_patch.stop)
        spec = importlib.util.spec_from_file_location(
            "_face_selection_tests.interactive.plate_face_selection", MODULE)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.picker = module.PlateFaceSelection(self.document, self.view, self.closed)

    def drain(self):
        timers, self.timers = self.timers, []
        for callback in timers:
            callback()

    def test_start_owns_only_selection_and_document_observers(self):
        self.picker.start()
        self.gui.Selection.clearSelection.assert_called_once_with()
        self.gui.Selection.addObserver.assert_called_once_with(self.picker)
        self.app.addDocumentObserver.assert_called_once_with(self.picker)
        self.gui.Control.showDialog.assert_called_once_with(self.picker)
        self.assertIsNone(self.app.activeDraftCommand)

    def test_success_is_deferred_and_returns_captured_placement(self):
        self.picker.start()
        self.picker.addSelection("PlateDoc", "Box", "Face1")
        self.assertTrue(self.picker._finishing)
        self.closed.assert_not_called()
        self.gui.Selection.removeObserver.assert_not_called()
        self.gui.Control.closeDialog.assert_not_called()
        self.picker.addSelection("PlateDoc", "Box", "Face2")
        self.planes.placement_from_face.assert_called_once_with(self.reference)
        self.drain()
        args = self.closed.call_args.args
        self.assertIs(args[0], self.picker)
        self.assertIs(args[1], self.reference)
        self.assertIsNot(args[2], self.placement)
        self.assertIs(args[2].Base, self.placement.Base)
        self.gui.Selection.removeObserver.assert_called_once_with(self.picker)
        self.app.removeDocumentObserver.assert_called_once_with(self.picker)

    def test_nonplanar_face_keeps_picker_open_with_feedback(self):
        self.planes.placement_from_face.side_effect = ValueError("A face selecionada deve ser plana.")
        self.picker.start()
        self.picker.addSelection("PlateDoc", "Cylinder", "Face1")
        self.assertIn("deve ser plana", self.picker.status.text)
        self.assertFalse(self.picker._finishing)
        self.closed.assert_not_called()

    def test_ambiguous_selection_is_rejected(self):
        self.planes.selected_plane_face.return_value = None
        self.picker.addSelection("PlateDoc", "Box", "")
        self.assertIn("somente uma face", self.picker.status.text)
        self.planes.placement_from_face.assert_not_called()

    def test_foreign_document_selection_is_rejected(self):
        self.picker.addSelection("OtherDoc", "Box", "Face1")
        self.planes.selected_plane_face.assert_not_called()
        self.assertIn("documento da chapa", self.picker.status.text)

    def test_dead_document_never_calls_old_view(self):
        self.documents.clear()
        self.picker.addSelection("PlateDoc", "Box", "Face1")
        self.gui.getDocument.assert_not_called()
        self.drain()
        self.closed.assert_called_once_with(self.picker, None, None)

    def test_reject_and_late_notifications_are_inert(self):
        self.picker.start()
        self.assertTrue(self.picker.reject())
        self.picker.addSelection("PlateDoc", "Box", "Face1")
        self.planes.selected_plane_face.assert_not_called()
        self.drain()
        self.picker.finish()
        self.picker.addSelection("PlateDoc", "Box", "Face1")
        self.closed.assert_called_once_with(self.picker, None, None)

    def test_outer_cancel_supersedes_pending_acceptance(self):
        self.picker.start()
        self.picker.addSelection("PlateDoc", "Box", "Face1")
        self.picker.finish()
        self.drain()
        self.closed.assert_called_once_with(self.picker, None, None)

    def test_replacement_dialog_is_never_closed(self):
        self.picker.start()
        self.picker._task_box = types.SimpleNamespace(
            parentWidget=lambda: types.SimpleNamespace(inherits=lambda kind: False),
            removeEventFilter=Mock())
        self.picker.finish()
        self.gui.Control.closeDialog.assert_not_called()

    def test_only_attached_owned_dialog_is_closed(self):
        self.picker.start()
        parent = types.SimpleNamespace(inherits=lambda kind: True,
            layout=lambda: types.SimpleNamespace(indexOf=lambda widget: 0))
        self.picker._task_box = types.SimpleNamespace(
            parentWidget=lambda: parent, isVisibleTo=lambda widget: True,
            removeEventFilter=Mock())
        self.picker.finish()
        self.gui.Control.closeDialog.assert_called_once_with()

    def test_view_switch_document_delete_and_form_destroy_defer_cancel(self):
        for trigger in (lambda: self.picker._view_changed(),
                        lambda: self.picker.slotDeletedDocument(self.document),
                        lambda: self.picker._form_destroyed()):
            with self.subTest(trigger=trigger):
                self.picker._closed = self.picker._finishing = False
                self.picker.on_closed = self.closed
                self.utils.get_3d_view = lambda: object()
                trigger()
                self.assertTrue(self.picker._finishing)
                self.drain()
        self.assertEqual(self.closed.call_count, 3)

    def test_start_refuses_active_draft_or_foreign_dialog(self):
        self.app.activeDraftCommand = object()
        self.picker.start()
        self.gui.Selection.addObserver.assert_not_called()
        self.gui.Control.showDialog.assert_not_called()
        self.closed.assert_called_once_with(self.picker, None, None)

    def test_start_refuses_foreign_dialog(self):
        self.gui.Control.activeDialog.return_value = True
        self.picker.start()
        self.gui.Selection.addObserver.assert_not_called()
        self.gui.Control.showDialog.assert_not_called()
        self.closed.assert_called_once_with(self.picker, None, None)

    def test_only_owned_taskbox_hide_cancels_selection(self):
        self.picker._task_box = object()
        event = types.SimpleNamespace(type=lambda: 18)
        self.assertFalse(self.picker.eventFilter(object(), event))
        self.assertFalse(self.picker._finishing)
        self.assertFalse(self.picker.eventFilter(self.picker._task_box, event))
        self.assertTrue(self.picker._finishing)
        # The owning native QObject can be gone before the timer runs.
        self.picker._task_box = None
        self.drain()
        self.closed.assert_called_once_with(self.picker, None, None)

    def test_ordinary_window_close_defers_cancel(self):
        self.assertFalse(self.picker.eventFilter(object(), types.SimpleNamespace(type=lambda: 19)))
        self.closed.assert_not_called()
        self.drain()
        self.closed.assert_called_once_with(self.picker, None, None)

    def test_standard_cancel_button_returns_int_for_pyside6(self):
        self.assertIsInstance(self.picker.getStandardButtons(), int)
        self.assertEqual(self.picker.getStandardButtons(), 1)

    def test_escape_shortcut_is_scoped_to_form_and_cancels_after_dispatch(self):
        self.picker.start()
        self.shortcut_factory.assert_called_once_with("Escape", self.picker.form)
        self.shortcut.setContext.assert_called_once_with(1)
        callback = self.shortcut.activated.connect.call_args.args[0]
        callback()
        self.assertTrue(self.picker._finishing)
        self.closed.assert_not_called()
        self.drain()
        self.shortcut.setEnabled.assert_called_once_with(False)
        self.shortcut.activated.disconnect.assert_called_once_with(callback)
        self.shortcut.deleteLater.assert_called_once_with()
        self.assertIsNone(self.picker._escape_shortcut)
        callback()  # Queued activation from the old form cannot cancel another tool.
        self.closed.assert_called_once_with(self.picker, None, None)

    def test_success_removes_escape_shortcut_before_notifying_session(self):
        self.picker.start()
        self.closed.side_effect = lambda *args: self.shortcut.setEnabled.assert_called_once_with(False)
        self.picker.addSelection("PlateDoc", "Box", "Face1")
        self.drain()
        self.assertIsNone(self.picker._escape_shortcut)


if __name__ == "__main__":
    unittest.main()
