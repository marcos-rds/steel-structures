"""Editor action dispatch and terminal teardown order without native Qt."""
from types import SimpleNamespace as NS
import unittest

from tests.test_truss_manual_fixes import definition
from tests import test_truss_editor_opening as opening_tests


class EditorActionTests(unittest.TestCase):
    def editor(self, apply=True):
        events=[]
        class Base:
            def accept(self): events.append("dialog.accept")
            def reject(self): events.append("dialog.reject")
        cls=definition("interactive/truss_topology_editor.py","TopologyEditor",dict(QtWidgets=NS(QDialog=Base)))
        editor=cls.__new__(cls)
        editor._submitting=False
        editor._qt_alive=True
        editor._panel_completion=None
        editor.panel=NS(_closed=False,_valid=True)
        editor.panel.apply=lambda:(events.append("panel.apply") or apply)
        editor.action_buttons=NS(setEnabled=lambda enabled:events.append(("buttons",enabled)))
        editor.apply_button=editor.ok_button=NS(setEnabled=lambda enabled:None)
        editor.canvas=NS(cancel_gesture=lambda **kwargs:None)
        editor._commit_inputs=lambda:True
        editor.sync_from_panel=lambda:events.append("sync")
        editor._capture_checkpoint=lambda:events.append("checkpoint")
        editor.findChildren=lambda _kind:[]
        editor.reject=lambda:Base.reject(editor)
        return editor,events

    def test_apply_stays_open_and_ok_closes_only_modal(self):
        for action in ("apply","ok"):
            editor,events=self.editor()
            editor._submit_action(action)
            self.assertEqual(events.count("panel.apply"),1)
            self.assertEqual(editor._panel_completion,"ok" if action=="ok" else None)
            self.assertEqual("dialog.accept" in events,action=="ok")
            self.assertFalse(editor.panel._closed)

    def test_failure_and_incomplete_input_never_close_editor(self):
        for commit in (False,True):
            editor,events=self.editor(apply=False)
            editor._commit_inputs=lambda:commit
            editor._submit_action("ok")
            self.assertIsNone(editor._panel_completion)
            self.assertNotIn("dialog.accept",events)
            self.assertEqual(events.count("panel.apply"),int(commit))
            self.assertFalse(editor._submitting)

    def test_cancel_only_rejects_modal_without_applying(self):
        editor,events=self.editor()
        editor._submit_action("cancel")
        self.assertEqual(events,["dialog.reject"])

    def test_reentrant_action_is_ignored(self):
        editor,events=self.editor()
        def apply():
            events.append("panel.apply")
            editor._submit_action("cancel")
            editor._submit_action("apply")
            return True
        editor.panel.apply=apply
        editor._submit_action("apply")
        self.assertEqual(events.count("panel.apply"),1)
        self.assertNotIn("dialog.reject",events)

    def test_native_destruction_during_apply_never_reuses_qt_objects(self):
        editor,events=self.editor()
        def apply():
            editor._qt_alive=False
            editor.panel._closed=True
            return True
        editor.panel.apply=apply
        editor._submit_action("ok")
        self.assertNotIn("sync",events)
        self.assertEqual(events,[("buttons",False)])

    def test_checkpoint_restore_waits_for_modal_unwind_and_reference_release(self):
        events=[]
        def action(dialog):
            dialog._panel_completion="cancel"
            def restore(panel):
                self.assertEqual(dialog.disposals,1)
                self.assertIsNone(panel._topology_editor)
                events.append("restore")
            dialog._checkpoint=NS(restore=restore)
            events.append("modal callback")
        panel,editors,factory=opening_tests.EditorOpeningTests().panel_and_factory(action)
        panel.accept=panel.reject=lambda:self.fail("Editor must not end TaskPanel")
        with factory: panel._open_topology_editor()
        self.assertEqual(events,["modal callback","restore"])
        self.assertFalse(panel._closed)
