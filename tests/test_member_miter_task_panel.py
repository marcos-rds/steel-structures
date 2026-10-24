"""Event/state contracts for the bilateral panel without importing Qt."""

import ast
import colorsys
import re
from pathlib import Path
import types
import unittest
from unittest.mock import Mock


SOURCE = (Path(__file__).resolve().parents[1] / "freecad/SteelStructures"
          / "interactive/member_miter_task_panel.py")


class MiterPanelRefreshTests(unittest.TestCase):
    def panel(self, states):
        tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
        panel_class = next(n for n in tree.body if isinstance(n, ast.ClassDef)
                           and n.name == "MemberMiterTaskPanel")
        method = next(n for n in panel_class.body if isinstance(n, ast.FunctionDef) and n.name == "_refresh")
        namespace = {"_member_caption": lambda obj: (obj.Name, "profile")}
        exec(compile(ast.Module(body=[method], type_ignores=[]), str(SOURCE), "exec"), namespace)
        panel = type("RefreshPanel", (), {"_refresh": namespace["_refresh"]})()
        panel._closed, panel._refreshing = False, False
        panel._state = Mock(side_effect=states)
        panel.controller = types.SimpleNamespace(
            members=(types.SimpleNamespace(Name="First"), types.SimpleNamespace(Name="Second")),
            trim_allowed=Mock(return_value=False),
            prepare_inputs=Mock(), evaluate=Mock(
            return_value=types.SimpleNamespace(plan=types.SimpleNamespace(ends=("Start", "End"), trim_lengths=(0, 0), angle_degrees=90))))
        for obj in panel.controller.members: obj.Label = obj.Name
        panel.member_labels = tuple(types.SimpleNamespace(setText=Mock(), setToolTip=Mock()) for _ in range(2))
        panel.profile_labels = tuple(types.SimpleNamespace(setText=Mock(), setVisible=Mock()) for _ in range(2))
        panel.joint_summary = types.SimpleNamespace(setText=Mock())
        panel._show_candidate = Mock()
        panel.trim_section = types.SimpleNamespace(hide=Mock())
        panel.trim_check = types.SimpleNamespace(setChecked=Mock())
        panel._trim_required = []
        panel._sync_trim_controls = Mock()
        panel._clear_preview = Mock()
        panel._set_message = Mock()
        panel._set_accept_enabled = Mock()
        return panel

    def test_stable_inputs_publish_and_enable_both_candidates(self):
        panel = self.panel([("input-a",), ("input-a",)])
        self.assertTrue(panel._refresh())
        self.assertIsNone(panel._last_error)
        self.assertEqual(panel._watch_state, ("input-a",))
        panel._set_accept_enabled.assert_called_once_with(True)
        panel._clear_preview.assert_not_called()
        panel.controller.prepare_inputs.assert_called_once_with()
        panel._set_message.assert_called_once_with("Encontro válido · 90,00°.", severity="success")
        panel.joint_summary.setText.assert_called_once_with("A: Início  •  B: Fim")

    def test_input_changed_during_evaluation_never_consumes_new_signature(self):
        panel = self.panel([("input-a",), ("input-b",)])
        self.assertFalse(panel._refresh())
        self.assertEqual(panel._watch_state, ("input-a",))
        self.assertIn("mudaram durante", panel._last_error)
        panel._clear_preview.assert_called_once_with()
        panel._set_accept_enabled.assert_called_once_with(False)
        self.assertFalse(panel._refreshing)
        panel._set_message.assert_called_once_with(panel._last_error)

    def test_missing_member_is_neutral_guidance_without_evaluation(self):
        panel = self.panel([("incomplete",)])
        panel.controller.members = (panel.controller.members[0], None)
        self.assertFalse(panel._refresh())
        panel.controller.prepare_inputs.assert_not_called()
        panel.controller.evaluate.assert_not_called()
        panel._set_message.assert_called_once_with("Selecione dois membros estruturais.")
        panel._set_accept_enabled.assert_called_once_with(False)

    def test_prepare_failure_is_objective_error_before_candidate(self):
        panel = self.panel([("rejected",)])
        panel.controller.prepare_inputs.side_effect = ValueError("Perfil diferente.")
        self.assertFalse(panel._refresh())
        panel.controller.evaluate.assert_not_called()
        panel._set_message.assert_called_once_with("Perfil diferente.", error=True)
        self.assertEqual(panel._watch_state, ("rejected",))
        panel.trim_check.setChecked.assert_called_once_with(False)

    def test_state_read_failure_after_export_removes_the_pair(self):
        panel = self.panel([("input-a",), RuntimeError("Document closed")])
        self.assertFalse(panel._refresh())
        self.assertEqual(panel._watch_state, ("input-a",))
        panel._clear_preview.assert_called_once_with()
        panel._set_accept_enabled.assert_called_once_with(False)


class MiterPanelMountTests(unittest.TestCase):
    def test_trim_option_text_uses_pt_br_values_and_stable_internal_ids(self):
        tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
        method = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "_trim_option_text")
        namespace = {}
        exec(compile(ast.Module(body=[method], type_ignores=[]), str(SOURCE), "exec"), namespace)
        format_option = namespace[method.name]
        self.assertEqual(format_option("Start", 5000), "Início (5.000 mm)")
        self.assertEqual(format_option("End", 100.25), "Fim (100,25 mm)")
        self.assertEqual(format_option("Start", .001), "Início (0,001 mm)")
        self.assertEqual(format_option("End", 100, True), "Fim — indisponível")

    def test_sync_updates_both_alternatives_without_parsing_text_or_authorizing(self):
        tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
        node = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "MemberMiterTaskPanel")
        sync = next(n for n in node.body if isinstance(n, ast.FunctionDef) and n.name == "_sync_trim_controls")
        formatter = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "_trim_option_text")
        namespace = {"QtCore": types.SimpleNamespace(Qt=types.SimpleNamespace(ToolTipRole=3))}
        exec(compile(ast.Module(body=[formatter, sync], type_ignores=[]), str(SOURCE), "exec"), namespace)
        class Item:
            def __init__(self): self.enabled = True
            def setEnabled(self, value): self.enabled = value
            def isEnabled(self): return self.enabled
        class Combo:
            def __init__(self):
                self.ids, self.texts, self.items, self.selected = [None, "Start", "End"], {}, [Item(), Item(), Item()], 0
            def findData(self, data): return self.ids.index(data)
            def setItemText(self, index, text): self.texts[index] = text
            def setItemData(self, *_args): pass
            def model(self): return self
            def item(self, index): return self.items[index]
            def setCurrentIndex(self, index): self.selected = index
            def currentIndex(self): return self.selected
        combo = Combo()
        controller = types.SimpleNamespace(trim_context=lambda: types.SimpleNamespace(automatic_ends=(None, "Start")),
            members=[types.SimpleNamespace(StartAdjustmentMode="None", EndAdjustmentMode="Fixed"), None],
            trim_ends=["Start", None], trim_allowed=lambda: False, _trim_token=lambda: "shown",
            trim_length=lambda _context, _index, end: 5000 if end == "Start" else 100)
        panel = types.SimpleNamespace(controller=controller, trim_end_combos=[combo, Combo()],
            trim_rows=[(types.SimpleNamespace(setVisible=Mock()),) for _ in range(2)],
            trim_section=types.SimpleNamespace(hide=Mock(), setVisible=Mock()),
            trim_check=types.SimpleNamespace(setEnabled=Mock(), setChecked=Mock()))
        namespace[sync.name](panel)
        self.assertEqual(combo.texts, {1: "Início (5.000 mm)", 2: "Fim — indisponível"})
        self.assertEqual(combo.ids[combo.selected], "Start")
        self.assertFalse(combo.items[2].enabled)
        panel.trim_check.setChecked.assert_called_with(False)
        controller.trim_length = lambda _context, _index, end: 5100 if end == "Start" else 100
        namespace[sync.name](panel)
        self.assertEqual(combo.texts[1], "Início (5.100 mm)")
        self.assertEqual(combo.ids[combo.selected], "Start")

    def test_opening_popup_refreshes_before_showing_options(self):
        tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
        node = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "_TrimEndCombo")
        events = []
        class Base:
            def showPopup(self): events.append("popup")
        namespace = dict(QtWidgets=types.SimpleNamespace(QComboBox=Base),
            QtCore=types.SimpleNamespace(Signal=lambda: types.SimpleNamespace(emit=lambda: events.append("refresh"))))
        exec(compile(ast.Module(body=[node], type_ignores=[]), str(SOURCE), "exec"), namespace)
        namespace[node.name]().showPopup()
        self.assertEqual(events, ["refresh", "popup"])

    def test_popup_only_rebuilds_the_editor_when_inputs_or_presentation_changed(self):
        tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
        node = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "MemberMiterTaskPanel")
        method = next(n for n in node.body if isinstance(n, ast.FunctionDef) and n.name == "_prepare_trim_popup")
        namespace = {}
        exec(compile(ast.Module(body=[method], type_ignores=[]), str(SOURCE), "exec"), namespace)
        for current, calls in (("shown", 0), ("new-value", 1), ("new-presentation", 1)):
            panel = types.SimpleNamespace(_state=lambda: current, _watch_state="shown", _refresh=Mock())
            namespace[method.name](panel)
            self.assertEqual(panel._refresh.call_count, calls)

    def test_consent_click_cannot_authorize_an_amount_changed_before_polling(self):
        tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
        node = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "MemberMiterTaskPanel")
        method = next(n for n in node.body if isinstance(n, ast.FunctionDef) and n.name == "_trim_allowed_changed")
        namespace = {}
        exec(compile(ast.Module(body=[method], type_ignores=[]), str(SOURCE), "exec"), namespace)
        for checked, current, expected_calls in ((True, "new-amount", 0), (True, "shown-amount", 1),
                                                 (False, "new-amount", 1)):
            panel = types.SimpleNamespace(_closed=False, _refreshing=False,
                _displayed_trim_token="shown-amount", _refresh=Mock(), _set_message=Mock(),
                controller=types.SimpleNamespace(set_trim_allowed=Mock(), _trim_token=lambda: current))
            namespace[method.name](panel, checked)
            self.assertEqual(panel.controller.set_trim_allowed.call_count, expected_calls)
            panel._refresh.assert_called_once_with()

    def test_member_caption_deduplicates_only_presentation(self):
        tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
        method = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "_member_caption")
        namespace = {"re": re}
        exec(compile(ast.Module(body=[method], type_ignores=[]), str(SOURCE), "exec"), namespace)
        fixtures = [("Viga 002 - SHS 100x100x5", "SHS 100x100x5", "Viga 002"),
                    ('Viga - U 2"', 'U 2″', "Viga"),
                    ("Membro - SHS 15,87x15,87x0,001", "SHS 15,87x15,87x0,75", "Membro"),
                    ("Pórtico principal / eixo lateral com nome longo", "W 150 x 13,0", "Pórtico principal / eixo lateral com nome longo"),
                    ("Customizado - SHS 15,87x15,87x0,001", "SHS 15,87x15,87x0,75", "Customizado - SHS 15,87x15,87x0,001")]
        for label, profile, name in fixtures:
            obj = types.SimpleNamespace(Label=label, Name="member", Profile=profile, ElementType="Membro")
            self.assertEqual(namespace[method.name](obj), (name, profile))
            self.assertEqual(obj.Label, label)
        obj = types.SimpleNamespace(Label="SHS 100x100x5 — viga do piso", Profile="SHS 100x100x5", Name="member")
        self.assertEqual(namespace[method.name](obj), (obj.Label, ""))

    def test_show_posts_form_owned_button_sync_for_the_mounted_task_view(self):
        tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
        lifecycle = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "_MiterPanelLifecycle")
        class Base:
            def eventFilter(self, obj, event):
                return False
        class Event:
            Show = 1
            PaletteChange = 2
            ApplicationPaletteChange = 3
            StyleChange = 4
            def __init__(self, kind): self.kind = kind
            def type(self): return self.kind
        posted = []
        namespace = dict(_PanelLifecycle=Base, _ACCEPT_STATE_EVENT=97,
                         QtCore=types.SimpleNamespace(QEvent=Event, QCoreApplication=types.SimpleNamespace(
                             postEvent=lambda obj, event: posted.append((obj, event)))))
        exec(compile(ast.Module(body=[lifecycle], type_ignores=[]), str(SOURCE), "exec"), namespace)
        handler = namespace["_MiterPanelLifecycle"]()
        form = object()
        handler.panel = types.SimpleNamespace(form=form, _closed=False, isValid=lambda: False,
                                               _set_accept_enabled=Mock(), _apply_message_style=Mock())
        self.assertFalse(handler.eventFilter(form, Event(Event.Show)))
        handler.panel._set_accept_enabled.assert_not_called()
        self.assertEqual(len(posted), 1)
        self.assertIs(posted[0][0], form)
        # Model the event after FreeCAD has installed the native button box.
        handler.eventFilter(*posted[0])
        handler.panel._set_accept_enabled.assert_called_once_with(False)
        handler.panel._apply_message_style.assert_called_once_with()
        handler.eventFilter(form, Event(Event.PaletteChange))
        self.assertEqual(handler.panel._apply_message_style.call_count, 2)
        handler.panel._closed = True
        handler.eventFilter(form, Event(97))
        handler.panel._set_accept_enabled.assert_called_once_with(False)
        self.assertEqual(handler.panel._apply_message_style.call_count, 2)


def semantic_functions():
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef)
             and n.name in ("_luminance", "_contrast", "_semantic_message_rgb")]
    namespace = {"colorsys": colorsys}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(SOURCE), "exec"), namespace)
    return namespace


class MiterMessageColorTests(unittest.TestCase):
    def test_status_colors_keep_contrast_in_light_and_dark_palettes(self):
        helpers = semantic_functions()
        for foreground, background in (((.08, .08, .08), (.95, .95, .95)),
                                       ((.95, .95, .95), (.18, .18, .18)),
                                       ((.85, .85, .85), (.12, .14, .16))):
            for severity in ("success", "error"):
                with self.subTest(background=background, severity=severity):
                    color = helpers["_semantic_message_rgb"](foreground, background, severity)
                    self.assertGreaterEqual(helpers["_contrast"](tuple(c/255 for c in color), background), 4.5)
                    dominant = 1 if severity == "success" else 0
                    self.assertEqual(color[dominant], max(color))

    def test_transparent_qss_palette_mismatch_uses_themed_text_polarity(self):
        helpers = semantic_functions()
        for severity in ("success", "error"):
            color = helpers["_semantic_message_rgb"]((1., 1., 1.), (.94, .94, .94), severity)
            self.assertGreaterEqual(helpers["_contrast"](tuple(c/255 for c in color), (.18, .18, .18)), 4.5)

    def test_neutral_guidance_inherits_theme_color(self):
        self.assertIsNone(semantic_functions()["_semantic_message_rgb"]((0., 0., 0.), (1., 1., 1.), "info"))

    def test_message_style_is_local_and_guidance_clears_semantic_tint(self):
        tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
        panel_class = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "MemberMiterTaskPanel")
        methods = [n for n in panel_class.body if isinstance(n, ast.FunctionDef)
                   and n.name in ("_set_message", "_apply_message_style")]
        namespace = semantic_functions()
        namespace["QtGui"] = types.SimpleNamespace(QPalette=types.SimpleNamespace(WindowText="text", Window="background"))
        exec(compile(ast.Module(body=methods, type_ignores=[]), str(SOURCE), "exec"), namespace)
        panel = type("MessagePanel", (), {n.name: namespace[n.name] for n in methods})()
        def color(value):
            return types.SimpleNamespace(redF=lambda: value, greenF=lambda: value, blueF=lambda: value)
        backing = types.SimpleNamespace(palette=lambda: types.SimpleNamespace(color=lambda role: color(.95)))
        reference = types.SimpleNamespace(palette=lambda: types.SimpleNamespace(color=lambda role: color(.08)),
                                          parentWidget=lambda: backing)
        panel.member_labels = (reference, reference)
        panel.validation_message = types.SimpleNamespace(setText=Mock(), setProperty=Mock(), setStyleSheet=Mock())
        panel._set_message("Encontro válido · 60,00°.", severity="success")
        panel.validation_message.setProperty.assert_called_with("miterMessageSeverity", "success")
        self.assertIn("color: rgb(", panel.validation_message.setStyleSheet.call_args.args[0])
        panel._set_message("Selecione dois membros.")
        panel.validation_message.setProperty.assert_called_with("miterMessageSeverity", "info")
        panel.validation_message.setStyleSheet.assert_called_with("")


if __name__ == "__main__":
    unittest.main()
