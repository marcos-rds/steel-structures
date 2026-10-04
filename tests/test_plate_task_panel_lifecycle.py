"""Task-panel teardown checks without a FreeCAD GUI event loop."""

import importlib.util
import sys
import types
import unittest
from pathlib import Path


PANEL_PATH = (Path(__file__).resolve().parents[1] / "freecad" / "SteelStructures"
              / "interactive" / "plate_task_panel.py")


class Signal:
    def __init__(self, events, name):
        self.events = events
        self.name = name

    def disconnect(self, _slot):
        self.events.append("disconnect:" + self.name)


class Timer:
    def __init__(self, events, name):
        self.events = events
        self.name = name
        self.timeout = Signal(events, name)

    def start(self, milliseconds):
        self.events.append(("start:" + self.name, milliseconds))

    def stop(self):
        self.events.append("stop:" + self.name)


class PlateTaskPanelLifecycleTests(unittest.TestCase):
    def setUp(self):
        pyside = types.ModuleType("PySide")
        pyside.QtCore = types.SimpleNamespace()
        pyside.QtWidgets = types.SimpleNamespace()
        self.previous = sys.modules.get("PySide")
        sys.modules["PySide"] = pyside
        spec = importlib.util.spec_from_file_location(
            "_plate_panel_lifecycle_test", PANEL_PATH)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.panel_type = module.PlateTaskPanel

    def tearDown(self):
        if self.previous is None:
            sys.modules.pop("PySide", None)
        else:
            sys.modules["PySide"] = self.previous

    def panel(self):
        events = []
        panel = self.panel_type.__new__(self.panel_type)
        panel._closed = False
        panel._closing = False
        panel._start_timer = Timer(events, "start")
        panel._escape_timer = Timer(events, "escape")
        panel.mode = types.SimpleNamespace(
            currentIndexChanged=Signal(events, "mode"))
        panel.plane_mode = types.SimpleNamespace(
            currentIndexChanged=Signal(events, "plane_mode"))
        panel.thickness = types.SimpleNamespace(
            valueChanged=Signal(events, "thickness"))
        panel.offset = types.SimpleNamespace(
            valueChanged=Signal(events, "offset"))
        panel.close_button = types.SimpleNamespace(
            clicked=Signal(events, "close_button"))
        panel.controller = types.SimpleNamespace(
            on_change=panel._refresh, on_error=panel._show_error,
            on_cancel=panel._cancel_from_view,
            cancel=lambda: events.append("controller.cancel"))
        panel.on_close = lambda _panel, accepted: events.append(
            ("close_dialog", accepted))
        return panel, events

    def test_escape_defers_teardown_then_closes_once(self):
        panel, events = self.panel()
        panel._cancel_from_view()
        panel._cancel_from_view()
        self.assertEqual([("start:escape", 0)], events)
        self.assertTrue(panel._closing)
        self.assertFalse(panel._closed)
        panel.reject()  # Simulates the next Qt event-loop turn.
        panel.reject()
        self.assertEqual(1, events.count("controller.cancel"))
        self.assertEqual(1, events.count(("close_dialog", False)))
        self.assertLess(events.index("controller.cancel"),
                        events.index(("close_dialog", False)))
        self.assertIsNone(panel.controller.on_cancel)
        self.assertIsNone(panel.on_close)

    def test_cancel_before_start_timer_and_late_slots_are_inert(self):
        panel, events = self.panel()
        panel.reject()
        before = len(events)
        panel._start_capture()
        panel._mode_changed(0)
        panel._show_error("late")
        panel._refresh()
        panel._parameters_changed()
        panel._close_outline()
        panel._cancel_from_view()
        self.assertFalse(panel.accept())
        self.assertEqual(before, len(events))
        self.assertEqual(1, events.count("stop:start"))
        self.assertEqual(1, events.count("stop:escape"))

    def test_plane_mode_signal_sets_work_plane_only_while_panel_is_active(self):
        panel, events = self.panel()
        panel.plane_mode.itemData = lambda _index: "WorkPlane"
        panel.controller.set_plane_mode = lambda mode: events.append(("plane", mode))
        panel._plane_mode_changed(1)
        self.assertIn(("plane", "WorkPlane"), events)
        panel.reject()
        before = len(events)
        panel._plane_mode_changed(0)
        self.assertEqual(before, len(events))


if __name__ == "__main__":
    unittest.main()
