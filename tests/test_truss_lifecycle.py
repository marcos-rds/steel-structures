"""Fault and external-destruction coverage, without requiring Qt/FreeCAD."""
from types import SimpleNamespace
import unittest

from tests import test_truss_apply_session as apply_tests
from tests.test_truss_task_panel import make_panel


class LifecycleTests(unittest.TestCase):
    def test_external_destruction_does_not_touch_deleted_qt_or_close_successor(self):
        panel = make_panel()
        events = []
        panel._on_close = lambda close_dialog=True: events.append(close_dialog)
        panel._preview_timer = SimpleNamespace(stop=lambda: self.fail("deleted timer accessed"))
        panel._form_destroyed()
        panel._form_destroyed()
        panel.reject()
        self.assertEqual(events, [False])
        self.assertEqual(panel.controller.cancels, 1)
        self.assertTrue(panel._closed and panel.session.closed)
        self.assertIsNone(panel.form)
        self.assertIsNone(panel._preview_timer)

    def test_cleanup_failure_still_releases_session_and_host_reference(self):
        panel = make_panel()
        events = []
        panel._on_close = lambda close_dialog=True: events.append(close_dialog)
        panel.controller.cancel = lambda: (_ for _ in ()).throw(RuntimeError("native cleanup"))
        with self.assertRaisesRegex(RuntimeError, "native cleanup"):
            panel._form_destroyed()
        self.assertEqual(events, [False])
        self.assertTrue(panel._closed and panel.session.closed)
        self.assertTrue(panel.reject())

    def test_dead_view_callbacks_are_released_and_never_retried(self):
        controller, _ = apply_tests.ApplySessionTests().controller()
        events = []
        namespace = controller.finish.__globals__
        namespace["Gui"].Snapper = SimpleNamespace(off=lambda: events.append("snapper.off"))
        namespace["App"].activeDraftCommand = SimpleNamespace(controller=controller)
        def remove(kind, token):
            events.append(token)
            raise RuntimeError("view already deleted")
        controller._view = SimpleNamespace(removeEventCallback=remove)
        controller._point_callbacks = [("mouse", 1), ("key", 2)]
        controller._document_is_open = lambda: True
        # Restore the real method hidden by the Apply test fixture.
        del controller.cancel_picker
        controller.finish()
        previous = list(events)
        controller.finish()
        self.assertEqual(events, previous)
        self.assertEqual(events[:2], [1, 2])
        self.assertIsNone(controller._view)
        self.assertFalse(controller._point_callbacks)
        self.assertIsNone(namespace["App"].activeDraftCommand)
        self.assertTrue(controller.closed and controller.session.closed)

    def test_completed_picker_still_turns_snapper_off_at_final_handoff(self):
        controller, _ = apply_tests.ApplySessionTests().controller()
        namespace = controller.finish.__globals__
        namespace["App"].activeDraftCommand = SimpleNamespace(controller=controller)
        commands = []
        namespace["Gui"].Snapper = SimpleNamespace(
            off=lambda: commands.append(namespace["App"].activeDraftCommand))
        controller.finish()
        self.assertEqual(commands, [None])


if __name__ == "__main__":
    unittest.main()
