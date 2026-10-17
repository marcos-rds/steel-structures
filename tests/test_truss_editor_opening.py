"""Editor entry-point and modal lifetime contracts without a Qt runtime."""
from types import SimpleNamespace
import sys
import unittest
from unittest.mock import patch

from tests import test_truss_task_panel as panel_tests
from tests.test_truss_manual_fixes import definition


class Signal:
    def __init__(self):
        self.slots = []

    def connect(self, slot):
        self.slots.append(slot)

    def emit(self):
        for slot in self.slots:
            slot()


class EditorOpeningTests(unittest.TestCase):
    def panel_and_factory(self, action):
        panel = panel_tests.make_panel()
        panel._refresh = lambda: True
        panel.controller.cancel_picker = lambda: None
        editors = []

        class Dialog:
            def __init__(self, owner):
                self.panel = owner
                self.destroyed = Signal()
                self.disposals = self.raises = 0
                editors.append(self)

            def exec(self):
                action(self)

            def deleteLater(self):
                self.disposals += 1
                self.destroyed.emit()

            def raise_(self):
                self.raises += 1

            def activateWindow(self):
                pass

        module = SimpleNamespace(TopologyEditor=Dialog)
        name = panel_tests.panel_module.__package__ + ".truss_topology_editor"
        return panel, editors, patch.dict(sys.modules, {name: module})

    def test_reentrant_entry_reuses_modal_and_preserves_draft(self):
        def action(dialog):
            dialog.panel._open_topology_editor()
            self.assertIs(dialog.panel._topology_editor, dialog)
            dialog.panel.session.config["advanced_marker"] = {"keep": [1, 2]}

        panel, editors, factory = self.panel_and_factory(action)
        with factory:
            panel._open_topology_editor()
            panel._open_topology_editor()
        self.assertEqual(len(editors), 2)
        self.assertEqual([editor.raises for editor in editors], [1, 1])
        self.assertEqual([editor.disposals for editor in editors], [1, 1])
        self.assertIsNone(panel._topology_editor)
        self.assertEqual(panel.session.config["advanced_marker"], {"keep": [1, 2]})
        self.assertFalse(panel.session.closed)
        self.assertFalse(panel.controller.applies or panel.controller.accepts)
        self.assertEqual(panel.controller.cancels, 0)

    def test_destroyed_modal_is_not_disposed_twice(self):
        def action(dialog):
            dialog.panel._form_destroyed()
            dialog.destroyed.emit()

        panel, editors, factory = self.panel_and_factory(action)
        with factory:
            panel._open_topology_editor()
        self.assertEqual(editors[0].disposals, 0)
        self.assertIsNone(panel._topology_editor)
        self.assertTrue(panel.session.closed)

    def test_exec_failure_releases_owned_reference(self):
        def action(_dialog):
            raise RuntimeError("native modal failure")

        panel, editors, factory = self.panel_and_factory(action)
        with factory, self.assertRaisesRegex(RuntimeError, "native modal failure"):
            panel._open_topology_editor()
        self.assertIsNone(panel._topology_editor)
        self.assertEqual(editors[0].disposals, 1)
        self.assertFalse(panel.session.closed)

    def test_invalid_draft_opens_for_repair_but_closed_or_conflicted_session_does_not(self):
        panel, editors, factory = self.panel_and_factory(lambda _: None)
        with factory:
            panel._refresh = lambda: False
            panel._open_topology_editor()
            self.assertEqual(len(editors),1)
            panel.session.conflict_reason="external edit"
            panel._open_topology_editor()
            panel._closed = True
            panel._refresh = lambda: self.fail("closed panel refreshed")
            panel._open_topology_editor()
        self.assertEqual(len(editors),1)

    def test_modal_document_observer_is_scoped_even_on_destruction_or_error(self):
        for mode in ("switch", "destroy", "error"):
            with self.subTest(mode=mode):
                observers, removed = [], []
                app = SimpleNamespace(addDocumentObserver=observers.append,
                                      removeDocumentObserver=removed.append)
                document = object()

                class BaseDialog:
                    def exec(editor):
                        observer = observers[0]
                        observer.slotActivateDocument(document)
                        self.assertEqual(editor.rejects, 0)
                        if mode == "destroy":
                            editor.destroyed.emit()
                        observer.slotActivateDocument(object())
                        if mode == "error":
                            raise RuntimeError("modal failed")
                        return 0

                cls = definition("interactive/truss_topology_editor.py", "TopologyEditor",
                                 dict(QtWidgets=SimpleNamespace(QDialog=BaseDialog)))
                editor = object.__new__(cls)
                editor.destroyed = Signal()
                editor.panel = SimpleNamespace(document=document)
                editor._capture_checkpoint = lambda: None
                editor.rejects = 0
                editor.reject = lambda: setattr(editor, "rejects", editor.rejects + 1)
                with patch.dict(sys.modules, {"FreeCAD": app}):
                    if mode == "error":
                        with self.assertRaisesRegex(RuntimeError, "modal failed"):
                            editor.exec()
                    else:
                        self.assertEqual(editor.exec(), 0)
                self.assertEqual(editor.rejects, 0 if mode == "destroy" else 1)
                self.assertEqual(observers, removed)


if __name__ == "__main__":
    unittest.main()
