"""Task-local shortcut focus/ownership contracts under controlled Qt objects."""

import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch


class Signal:
    def __init__(self):
        self.slots = []
    def connect(self, slot):
        self.slots.append(slot)
    def disconnect(self, slot):
        self.slots.remove(slot)
    def emit(self, *args):
        for slot in tuple(self.slots):
            slot(*args)


class Widget:
    def __init__(self, parent=None):
        self.parent = parent
        self.destroyed = Signal()
        self.enabled = self.visible = True
        self.clicks = 0
    def parentWidget(self):
        return self.parent
    def isEnabled(self):
        return self.enabled
    def isVisible(self):
        return self.visible
    def click(self):
        self.clicks += 1
    def setText(self, text):
        self.text = text
    def installEventFilter(self, event_filter):
        self.event_filter = event_filter
    def removeEventFilter(self, event_filter):
        self.event_filter = None


class Shortcut:
    def __init__(self, key, parent):
        self.key, self.parent = key, parent
        self.activated = Signal()
        self.enabled = True
        self.deleted = False
    def setContext(self, context):
        self.context = context
    def setAutoRepeat(self, repeat):
        self.repeat = repeat
    def setEnabled(self, enabled):
        self.enabled = enabled
    def deleteLater(self):
        self.deleted = True


class PlatePanelShortcutsTests(unittest.TestCase):
    def setUp(self):
        self.app = types.SimpleNamespace(focusChanged=Signal(), current=None)
        self.app.focusWidget = lambda: self.app.current
        self.qtwidgets = types.SimpleNamespace(QApplication=types.SimpleNamespace(instance=lambda: self.app))
        for name in ("QLineEdit", "QAbstractSpinBox", "QTextEdit", "QPlainTextEdit", "QComboBox"):
            setattr(self.qtwidgets, name, type(name, (Widget,), {}))
        self.qtwidgets.QComboBox.isEditable = lambda widget: getattr(widget, "editable", False)
        qt = types.ModuleType("PySide")
        qt.QtWidgets = self.qtwidgets
        qt.QtGui = types.SimpleNamespace(QShortcut=Shortcut, QKeySequence=lambda key: key)
        qt.QtCore = types.SimpleNamespace(QObject=object,
            Qt=types.SimpleNamespace(WindowShortcut=1, MouseFocusReason=2,
                TabFocusReason=3, BacktabFocusReason=4, OtherFocusReason=5,
                NoModifier=0, KeypadModifier=8),
            QEvent=types.SimpleNamespace(MouseButtonPress=1, FocusIn=2, KeyPress=3))
        context = patch.dict(sys.modules, {"PySide": qt})
        context.start()
        self.addCleanup(context.stop)
        path = Path(__file__).resolve().parents[1] / "freecad/SteelStructures/interactive/plate_panel_shortcuts.py"
        spec = importlib.util.spec_from_file_location("plate_shortcuts_test_module", path)
        self.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.module)
        self.active = True
        self.parent = Widget()
        self.owner = self.module.PanelShortcuts(self.parent, lambda: self.active)
        self.addCleanup(self.owner.dispose)
        self.button = Widget(self.parent)

    def focus(self, widget):
        old, self.app.current = self.app.current, widget
        self.app.focusChanged.emit(old, widget)

    def bind(self):
        self.assertTrue(self.owner.bind(self.button, "A", label="Adicionar ponto"))
        return self.owner._bindings[0][0]

    def test_window_owned_single_activation_and_no_repeat(self):
        shortcut = self.bind()
        self.assertIs(shortcut.parent, self.parent)
        self.assertEqual(shortcut.context, 1)
        self.assertFalse(shortcut.repeat)
        self.assertEqual(self.button.text, "Adicionar ponto (A)")
        shortcut.activated.emit()
        self.assertEqual(self.button.clicks, 1)

    def test_disabled_while_editing_and_restored_outside(self):
        shortcut = self.bind()
        for name in ("QLineEdit", "QAbstractSpinBox", "QTextEdit", "QPlainTextEdit"):
            self.focus(getattr(self.qtwidgets, name)())
            self.assertFalse(shortcut.enabled)
            shortcut.activated.emit()
            self.assertEqual(self.button.clicks, 0)
        self.focus(Widget())
        self.assertTrue(shortcut.enabled)
        shortcut.activated.emit()
        self.assertEqual(self.button.clicks, 1)

    def test_editable_combo_and_editor_child_are_protected(self):
        shortcut = self.bind()
        combo = self.qtwidgets.QComboBox()
        combo.editable = True
        self.focus(combo)
        self.assertFalse(shortcut.enabled)
        self.focus(Widget(self.qtwidgets.QLineEdit()))
        self.assertFalse(shortcut.enabled)
        combo.editable = False
        self.focus(combo)
        self.assertTrue(shortcut.enabled)

    def test_real_action_states_and_owner_guard(self):
        shortcut = self.bind()
        self.button.enabled = False
        shortcut.activated.emit()
        self.button.enabled = True
        self.button.visible = False
        shortcut.activated.emit()
        self.button.visible = True
        self.active = False
        shortcut.activated.emit()
        self.assertEqual(self.button.clicks, 0)

    def test_duplicate_empty_keys_have_no_decorative_labels(self):
        self.bind()
        other = Widget()
        self.assertFalse(self.owner.bind(other, "A", label="Duplicado"))
        self.assertFalse(self.owner.bind(other, "", label="Vazio"))
        self.assertEqual(other.text, "Vazio")

    def test_dispose_disconnects_and_late_activation_is_inert(self):
        shortcut = self.bind()
        late = shortcut.activated.slots[0]
        self.owner.dispose()
        self.owner.dispose()
        self.assertFalse(shortcut.enabled)
        self.assertTrue(shortcut.deleted)
        self.assertEqual(self.app.focusChanged.slots, [])
        self.assertEqual(shortcut.activated.slots, [])
        late()
        self.assertEqual(self.button.clicks, 0)

    def test_initial_editable_focus_disables_immediately(self):
        self.focus(self.qtwidgets.QLineEdit())
        self.assertFalse(self.bind().enabled)

    def test_parent_destruction_releases_application_connection_and_late_action(self):
        shortcut = self.bind()
        late = shortcut.activated.slots[0]
        self.parent.destroyed.emit(self.parent)
        self.assertEqual(self.app.focusChanged.slots, [])
        self.assertEqual(self.parent.destroyed.slots, [])
        self.assertFalse(shortcut.enabled)
        self.assertTrue(shortcut.deleted)
        self.focus(Widget())
        late()
        self.assertEqual(self.button.clicks, 0)

    def test_preferences_keep_native_mapping_and_tolerate_absent_key(self):
        params = types.SimpleNamespace(get_param=lambda entry: {"inCommandShortcutClose": "o"}.get(entry))
        with patch.dict(sys.modules, {"draftutils": types.SimpleNamespace(params=params)}):
            keys = self.module.draft_shortcut_keys()
        self.assertEqual(keys["Close"], "O")
        self.assertEqual(keys["Global"], "")
        self.assertIn("SelectEdge", keys)

    def test_vertex_key_never_overrides_native_radius_or_user_preferences(self):
        self.assertEqual(self.module.point_shortcut_key({"Exit": "A"}), "P")
        self.assertEqual(self.module.point_shortcut_key({"IncreaseRadius": "P"}), "V")
        self.assertEqual(self.module.point_shortcut_key({"IncreaseRadius": "P", "Copy": "V"}), "")

    def test_native_programmatic_focus_is_not_manual_editing(self):
        field = self.qtwidgets.QLineEdit()
        tracker = self.module.DraftCoordinateFocus([field], self.owner.refresh)
        self.addCleanup(tracker.dispose)
        self.owner.is_editing = tracker.protects
        shortcut = self.bind()
        self.focus(field)
        self.assertTrue(shortcut.enabled)
        event = types.SimpleNamespace(type=lambda: 2, reason=lambda: 5)
        self.assertFalse(tracker.eventFilter(field, event))
        shortcut.activated.emit()
        self.assertEqual(self.button.clicks, 1)
        event.reason = lambda: 2
        tracker.eventFilter(field, event)
        self.assertFalse(shortcut.enabled)
        shortcut.activated.emit()
        self.assertEqual(self.button.clicks, 1)
        tracker.set_editing(False)
        self.assertTrue(shortcut.enabled)
        self.focus(self.qtwidgets.QLineEdit())
        self.assertFalse(shortcut.enabled, "Other editable controls remain protected")

    def test_native_keypress_fallback_uses_same_guarded_binding_only_when_graphical(self):
        field = self.qtwidgets.QLineEdit()
        tracker = self.module.DraftCoordinateFocus([field], self.owner.refresh, self.owner.run_key)
        self.owner.is_editing = tracker.protects
        self.bind()
        self.focus(field)
        event = types.SimpleNamespace(type=lambda: 3, text=lambda: "a", modifiers=lambda: 0,
                                      isAutoRepeat=lambda: False)
        self.assertTrue(tracker.eventFilter(field, event))
        self.assertEqual(self.button.clicks, 1)
        event.isAutoRepeat = lambda: True
        self.assertTrue(tracker.eventFilter(field, event))
        self.assertEqual(self.button.clicks, 1)
        event.isAutoRepeat = lambda: False
        tracker.set_editing(True)
        self.assertFalse(tracker.eventFilter(field, event))
        self.assertEqual(self.button.clicks, 1)
        tracker.set_editing(False)
        event.text = lambda: "m"
        self.assertFalse(tracker.eventFilter(field, event))
        event.text = lambda: "A"
        event.modifiers = lambda: 32
        self.assertFalse(tracker.eventFilter(field, event))
        event.modifiers = lambda: 0
        self.button.enabled = False
        self.assertTrue(tracker.eventFilter(field, event))
        self.assertEqual(self.button.clicks, 1)
        tracker.dispose()
        self.assertIsNone(field.event_filter)
        event.modifiers = lambda: 0
        self.assertFalse(tracker.eventFilter(field, event))


if __name__ == "__main__":
    unittest.main()
