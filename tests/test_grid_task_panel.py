"""Focused tests for the grid task-panel contract without a real FreeCAD GUI."""

from __future__ import annotations

import ast
import enum
import unittest
from pathlib import Path

try:
    from .test_grid_geometry import grid as grid_geometry
except ImportError:  # unittest discovery loads this file as a top-level module.
    from test_grid_geometry import grid as grid_geometry


ROOT = Path(__file__).resolve().parents[1]
PANEL = ROOT / "freecad/SteelStructures/interactive/grid_task_panel.py"
PATHS = ROOT / "freecad/SteelStructures/paths.py"
GRID_ICONS = {
    "GRID_SPACING_ADD_ICON": ROOT / "Resources/Icons/GridSpacingAdd.svg",
    "GRID_SPACING_DUPLICATE_ICON": ROOT / "Resources/Icons/GridSpacingDuplicate.svg",
    "GRID_SPACING_REMOVE_ICON": ROOT / "Resources/Icons/GridSpacingRemove.svg",
    "GRID_RESET_DEFAULTS_ICON": ROOT / "Resources/Icons/GridResetDefaults.svg",
}


def extracted_panel_methods(tree, names, globals_):
    original = next(node for node in tree.body
                    if isinstance(node, ast.ClassDef) and node.name == "GridTaskPanel")
    methods = [node for node in original.body
               if isinstance(node, ast.FunctionDef) and node.name in names]
    cls = ast.ClassDef(name="Panel", bases=[], keywords=[], body=methods, decorator_list=[])
    namespace = dict(globals_)
    exec(compile(ast.fix_missing_locations(ast.Module(body=[cls], type_ignores=[])),
                 str(PANEL), "exec"), namespace)
    return namespace["Panel"]


class GridTaskPanelContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = PANEL.read_text(encoding="utf-8")
        cls.tree = ast.parse(cls.source)

    def test_panel_has_independent_x_and_y_editors_and_sections(self):
        for text in ("Vãos em X", "Vãos em Y", "Extensões", "Identificação", "Aparência"):
            self.assertIn(text, self.source)
        self.assertIn("self.x_editor = SpacingEditor", self.source)
        self.assertIn("self.y_editor = SpacingEditor", self.source)

    def test_spacing_controls_and_summary_are_present(self):
        for control in ("Adicionar", "Duplicar", "Remover", "eixos • total:"):
            self.assertIn(control, self.source)

    def test_spacing_spin_delegates_native_editing_and_activates_only_on_click(self):
        spin_node = next(node for node in self.tree.body
                         if isinstance(node, ast.ClassDef) and node.name == "SpacingDoubleSpinBox")

        class BaseSpin:
            def __init__(self, parent=None):
                self.parent = parent
                self.focus_policy = None
                self.focused = False
                self.focus_events = []
                self.wheel_events = []
            def setFocusPolicy(self, policy): self.focus_policy = policy
            def hasFocus(self): return self.focused
            def focusInEvent(self, event): self.focus_events.append(event)
            def wheelEvent(self, event): self.wheel_events.append(event)

        qt = type("Qt", (), {"StrongFocus": 11})
        namespace = {
            "QtCore": type("QtCore", (), {"Qt": qt}),
            "QtWidgets": type("QtWidgets", (), {"QDoubleSpinBox": BaseSpin}),
        }
        exec(compile(ast.Module(body=[spin_node], type_ignores=[]), str(PANEL), "exec"), namespace)
        activated = []
        spin = namespace["SpacingDoubleSpinBox"](lambda: activated.append(True))

        focus = object()
        spin.focusInEvent(focus)
        self.assertEqual(activated, [True])
        self.assertEqual(spin.focus_events, [focus])
        self.assertEqual(spin.focus_policy, qt.StrongFocus)

        class Wheel:
            def __init__(self): self.ignored = False
            def ignore(self): self.ignored = True
        unfocused = Wheel()
        spin.wheelEvent(unfocused)
        self.assertTrue(unfocused.ignored)
        self.assertEqual(spin.wheel_events, [])
        spin.focused = True
        focused = Wheel()
        spin.wheelEvent(focused)
        self.assertFalse(focused.ignored)
        self.assertEqual(spin.wheel_events, [focused])

        self.assertIn("spin = SpacingDoubleSpinBox(lambda: self._set_active(spin))", self.source)
        self.assertNotIn("def enterEvent", ast.unparse(spin_node))
        self.assertNotIn("MouseMove", ast.unparse(spin_node))
        self.assertNotIn("installEventFilter", ast.unparse(spin_node))

    def test_spacing_editor_uses_simple_scroll_layout_not_an_item_view(self):
        spacing = next(node for node in self.tree.body
                       if isinstance(node, ast.ClassDef) and node.name == "SpacingEditor")
        rendered = ast.unparse(spacing)
        self.assertIn("QScrollArea", rendered)
        self.assertIn("QVBoxLayout", rendered)
        self.assertIn("self._spins", rendered)
        self.assertNotIn("QListWidget", rendered)
        self.assertNotIn("QListWidgetItem", rendered)
        self.assertNotIn("setItemWidget", rendered)
        for method in ("active_index", "add_spacing", "duplicate_spacing",
                       "remove_spacing", "set_values", "values"):
            self.assertIn("def " + method, rendered)

    def test_spacing_actions_are_compact_accessible_tool_buttons(self):
        spacing = next(node for node in self.tree.body
                       if isinstance(node, ast.ClassDef) and node.name == "SpacingEditor")
        rendered = ast.unparse(spacing)
        self.assertEqual(rendered.count("self._action_button("), 3)
        for tooltip in ("Adicionar vão", "Duplicar vão selecionado",
                        "Remover vão selecionado"):
            self.assertIn(tooltip, rendered)
        self.assertIn("QToolButton", rendered)
        self.assertIn("setToolTip(description)", rendered)
        self.assertIn("setAccessibleName(description)", rendered)
        self.assertNotIn("QPushButton", rendered)
        self.assertIn("QVBoxLayout()", rendered)

    def test_grid_action_icons_exist_are_packaged_paths_and_have_explicit_color(self):
        paths_source = PATHS.read_text(encoding="utf-8")
        for constant, path in GRID_ICONS.items():
            with self.subTest(icon=path.name):
                self.assertTrue(path.is_file())
                self.assertIn(constant, paths_source)
                self.assertIn(path.name, paths_source)
                svg = path.read_text(encoding="utf-8")
                self.assertIn('viewBox="0 0 20 20"', svg)
                self.assertNotIn("currentColor", svg)
                self.assertRegex(svg, r'#[0-9A-Fa-f]{6}')

    def test_action_icons_use_qicon_explicit_size_and_exclusive_fallback(self):
        spacing = next(node for node in self.tree.body
                       if isinstance(node, ast.ClassDef) and node.name == "SpacingEditor")
        action = next(node for node in spacing.body
                      if isinstance(node, ast.FunctionDef) and node.name == "_action_button")
        rendered = ast.unparse(action)
        self.assertIn("QtGui.QIcon(icon_path)", rendered)
        self.assertIn("if icon.isNull()", rendered)
        self.assertIn("button.setText(fallback)", rendered)
        self.assertIn("else", rendered)
        self.assertIn("button.setIcon(icon)", rendered)
        metrics = next(node for node in spacing.body
                       if isinstance(node, ast.FunctionDef)
                       and node.name == "_update_editor_metrics")
        self.assertIn("button.setIconSize(QtCore.QSize", ast.unparse(metrics))

    def test_compact_tool_button_style_is_local_reused_and_scope_limited(self):
        helper = next(node for node in self.tree.body
                      if isinstance(node, ast.FunctionDef)
                      and node.name == "stabilize_compact_tool_button")
        rendered = ast.unparse(helper)
        self.assertIn("button.setStyleSheet", rendered)
        self.assertIn("margin: 0px", rendered)
        self.assertIn("padding: 2px", rendered)
        for forbidden in ("background", "color", "border", "hover", "pressed",
                          "checked", "disabled", "focus"):
            self.assertNotIn(forbidden, rendered.lower())
        self.assertEqual(self.source.count(
            'QToolButton { margin: 0px; padding: 2px; }'), 1)

        spacing = next(node for node in self.tree.body
                       if isinstance(node, ast.ClassDef) and node.name == "SpacingEditor")
        action = next(node for node in spacing.body
                      if isinstance(node, ast.FunctionDef) and node.name == "_action_button")
        self.assertIn("stabilize_compact_tool_button(button)", ast.unparse(action))

        panel = next(node for node in self.tree.body
                     if isinstance(node, ast.ClassDef) and node.name == "GridTaskPanel")
        init = next(node for node in panel.body
                    if isinstance(node, ast.FunctionDef) and node.name == "__init__")
        self.assertIn("stabilize_compact_tool_button(self.reset_button)",
                      ast.unparse(init))

    def test_spacing_metrics_are_dpi_aware_for_five_to_seven_rows(self):
        spacing = next(node for node in self.tree.body
                       if isinstance(node, ast.ClassDef) and node.name == "SpacingEditor")
        metrics = next(node for node in spacing.body
                       if isinstance(node, ast.FunctionDef)
                       and node.name == "_update_editor_metrics")
        rendered = ast.unparse(metrics)
        for contract in ("sizeHint().height()", "editor_layout.spacing()",
                         "frameWidth()", "visible_rows",
                         "min(max(len(self._spins), 1), 7)",
                         "editor_container.setMinimumHeight",
                         "horizontalAdvance", "100000,00 mm",
                         "PM_SpinBoxFrameWidth", "PM_ScrollBarExtent"):
            self.assertIn(contract, rendered)
        self.assertIn("ScrollBarAlwaysOff", ast.unparse(spacing))
        self.assertIn("AlignTop", ast.unparse(spacing))
        self.assertIn("setFixedHeight(height_for(visible_rows))", rendered)
        self.assertIn("self.editor_layout.setSpacing(0)", ast.unparse(spacing))

    def test_spacing_layout_expands_without_fixed_width_or_residual_stretch(self):
        spacing = next(node for node in self.tree.body
                       if isinstance(node, ast.ClassDef) and node.name == "SpacingEditor")
        rendered = ast.unparse(spacing)
        self.assertIn("self.scroll.setSizePolicy(QtWidgets.QSizePolicy.Expanding", rendered)
        self.assertIn("content.addWidget(self.scroll, 1)", rendered)
        self.assertIn("self.scroll.setMinimumWidth", rendered)
        self.assertIn("spin.setMinimumWidth", rendered)
        self.assertIn("spin.setSizePolicy(QtWidgets.QSizePolicy.Expanding", rendered)
        self.assertNotIn("self.scroll.setFixedWidth", rendered)
        self.assertNotIn("spin.setFixedWidth", rendered)
        self.assertNotIn("content.addStretch", rendered)

    def test_spacing_add_duplicate_remove_and_active_editor_behavior(self):
        spacing = next(node for node in self.tree.body
                       if isinstance(node, ast.ClassDef) and node.name == "SpacingEditor")
        qt = type("Qt", (), {"OtherFocusReason": 7})
        namespace = {
            "QtCore": type("QtCore", (), {"Qt": qt}),
            "QtWidgets": type("QtWidgets", (), {"QGroupBox": object}),
        }
        exec(compile(ast.Module(body=[spacing], type_ignores=[]), str(PANEL), "exec"), namespace)
        editor = namespace["SpacingEditor"].__new__(namespace["SpacingEditor"])

        class Spin:
            def __init__(self, value):
                self._value = float(value); self.focused = self.deleted = False
            def value(self): return self._value
            def setFocus(self, _reason):
                self.focused = True; editor._set_active(self)
            def deleteLater(self): self.deleted = True
        class Layout:
            def __init__(self): self.removed = []
            def removeWidget(self, widget): self.removed.append(widget)
        class Summary:
            def setText(self, text): self.text = text

        editor._spins = [Spin(6000), Spin(5000)]
        editor._active_spin = None
        editor.editor_layout = Layout()
        editor.summary = Summary()
        editor._update_editor_metrics = lambda: None
        changes = []
        editor._on_change = lambda: changes.append(editor.values())
        def append(value):
            spin = Spin(value); editor._spins.append(spin); return spin
        editor._append = append

        self.assertEqual(editor.active_index(), 1)
        editor._set_active(editor._spins[0])
        self.assertEqual(editor.active_index(), 0)
        editor.duplicate_spacing()
        self.assertEqual(editor.values(), [6000.0, 5000.0, 6000.0])
        self.assertEqual(editor.active_index(), 2)
        editor.add_spacing()
        self.assertEqual(editor.values()[-1], 6000.0)
        self.assertEqual(editor.active_index(), 3)
        removed = editor._spins[-1]
        editor.remove_spacing()
        self.assertTrue(removed.deleted)
        self.assertEqual(editor.values(), [6000.0, 5000.0, 6000.0])
        self.assertTrue(changes)

    def test_dynamic_height_refreshes_after_every_spacing_mutation(self):
        spacing = next(node for node in self.tree.body
                       if isinstance(node, ast.ClassDef) and node.name == "SpacingEditor")
        for name in ("add_spacing", "duplicate_spacing", "remove_spacing", "set_values"):
            method = next(node for node in spacing.body
                          if isinstance(node, ast.FunctionDef) and node.name == name)
            self.assertIn("self._update_editor_metrics()", ast.unparse(method))

    def test_positive_spacing_validation_is_delegated_to_geometry_contract(self):
        with self.assertRaisesRegex(ValueError, "greater than zero"):
            grid_geometry.build_grid_geometry([0], [1])
        with self.assertRaisesRegex(ValueError, "greater than zero"):
            grid_geometry.build_grid_geometry([-1], [1])
        self.assertIn("build_grid_geometry(x_values, y_values", self.source)

    def test_all_extension_fields_are_wired(self):
        for name in ("XStartExtension", "XEndExtension", "YStartExtension", "YEndExtension"):
            self.assertIn(name, self.source)

    def test_identification_schemes_and_custom_rules_come_from_geometry(self):
        for label in ("Numérica", "Alfabética", "Personalizada"):
            self.assertIn(label, self.source)
        for bad in ((["A"], 2), (["A", "A"], 2), (["A", " "], 2)):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                grid_geometry.normalize_identifiers(bad[0], bad[1], "custom")
        self.assertEqual(grid_geometry.normalize_identifiers([" A ", "B"], 2, "custom"), ("A", "B"))

    def test_preview_mutates_existing_object_and_validates_before_mutation(self):
        method = next(node for node in self.tree.body if isinstance(node, ast.ClassDef) and node.name == "GridTaskPanel")
        update = next(node for node in method.body if isinstance(node, ast.FunctionDef) and node.name == "update_preview")
        calls = [node for node in ast.walk(update) if isinstance(node, ast.Call)]
        self.assertFalse(any(isinstance(call.func, ast.Name) and call.func.id == "create_grid" for call in calls))
        self.assertIn("self._values()", ast.unparse(update))
        self.assertIn("self.document.recompute()", ast.unparse(update))

    def test_invalid_input_preserves_preview_and_validity_blocks_acceptance(self):
        update_source = ast.unparse(next(node for node in ast.walk(self.tree) if isinstance(node, ast.FunctionDef) and node.name == "update_preview"))
        self.assertLess(update_source.index("self._values()"), update_source.index("obj = self.grid_object"))
        self.assertIn("return False", update_source)
        self.assertIn("if not self.update_preview()", self.source)

    def test_visual_properties_and_provisional_defaults(self):
        for prop in ("LineColor", "LineWidth", "PointColor", "PointSize"):
            self.assertIn(prop, self.source)
        self.assertIn("IntersectionPointColor", self.source)
        self.assertIn("IntersectionPointSize", self.source)
        self.assertNotIn("view.PointColor =", self.source)
        self.assertNotIn("view.PointSize =", self.source)
        self.assertIn("default_grid_appearance(current_font)", self.source)
        self.assertIn("load_grid_appearance_settings()", self.source)
        self.assertIn("self.line_width.setValue(appearance_settings.line_width)", self.source)
        self.assertIn("self.point_size.setValue(appearance_settings.intersection_size)", self.source)
        self.assertIn("self.label_offset.setValue(appearance_settings.label_offset)", self.source)

    def test_accept_cancel_and_idempotent_cleanup_contract(self):
        for call in ("commitTransaction()", "abortTransaction()", "removeObject(name)"):
            self.assertIn(call, self.source)
        self.assertIn("if self._closed:", self.source)
        self.assertIn("self._remove_escape_filter()", self.source)
        self.assertIn("self._finish(True)", self.source)
        self.assertIn("self._finish(False)", self.source)
        self.assertIn("event_filter.deleteLater()", self.source)

    def test_preferences_load_on_create_save_only_after_successful_accept(self):
        panel_node = next(node for node in self.tree.body
                          if isinstance(node, ast.ClassDef) and node.name == "GridTaskPanel")
        init = next(node for node in panel_node.body
                    if isinstance(node, ast.FunctionDef) and node.name == "__init__")
        accept = next(node for node in panel_node.body
                      if isinstance(node, ast.FunctionDef) and node.name == "accept")
        reject = next(node for node in panel_node.body
                      if isinstance(node, ast.FunctionDef) and node.name == "reject")
        self.assertIn("load_grid_appearance_settings()", ast.unparse(init))
        self.assertIn("save_grid_appearance_settings(self._appearance_settings())",
                      ast.unparse(accept))
        self.assertNotIn("save_grid_appearance_settings", ast.unparse(reject))
        self.assertLess(ast.unparse(accept).index("update_preview()"),
                        ast.unparse(accept).index("save_grid_appearance_settings"))
        self.assertLess(ast.unparse(accept).index("commitTransaction()"),
                        ast.unparse(accept).index("save_grid_appearance_settings"))

    def test_identification_signals_are_connected_after_both_label_widgets_exist(self):
        labels = self.source.index("self.x_labels, self.y_labels =")
        connection = self.source.index("currentTextChanged.connect(self._identification_changed)")
        self.assertLess(labels, connection)
        self.assertIn("self._initializing", self.source)

    def test_custom_identifier_labels_and_fields_toggle_independently_without_data_loss(self):
        class Widget:
            def __init__(self, text=""): self.visible = None; self._text = text
            def setVisible(self, visible): self.visible = bool(visible)
            def text(self): return self._text
        class Combo:
            def __init__(self, text): self.value = text
            def currentText(self): return self.value
        Panel = extracted_panel_methods(
            self.tree, {"_identification_changed"}, {"SCHEMES": {
                "Numérica": "Numeric", "Alfabética": "Alphabetic",
                "Personalizada": "Custom",
            }}
        )
        panel = Panel()
        panel.x_scheme, panel.y_scheme = Combo("Numérica"), Combo("Personalizada")
        panel.x_labels, panel.y_labels = Widget("X1, X2"), Widget("Y1, Y2")
        panel.x_labels_label, panel.y_labels_label = Widget(), Widget()
        panel._initializing = True
        panel._identification_changed()
        self.assertEqual((panel.x_labels_label.visible, panel.x_labels.visible),
                         (False, False))
        self.assertEqual((panel.y_labels_label.visible, panel.y_labels.visible),
                         (True, True))
        panel.x_scheme.value, panel.y_scheme.value = "Personalizada", "Alfabética"
        panel._identification_changed()
        self.assertEqual((panel.x_labels_label.visible, panel.x_labels.visible),
                         (True, True))
        self.assertEqual((panel.y_labels_label.visible, panel.y_labels.visible),
                         (False, False))
        self.assertEqual((panel.x_labels.text(), panel.y_labels.text()),
                         ("X1, X2", "Y1, Y2"))

    def test_header_is_compact_accessible_and_has_no_general_group(self):
        panel = next(node for node in self.tree.body
                     if isinstance(node, ast.ClassDef) and node.name == "GridTaskPanel")
        init = next(node for node in panel.body
                    if isinstance(node, ast.FunctionDef) and node.name == "__init__")
        rendered = ast.unparse(init)
        self.assertNotIn('QGroupBox("Geral")', rendered)
        self.assertIn("QLabel", rendered)
        self.assertIn("Nome do grid:", rendered)
        self.assertIn("self.name_edit", rendered)
        self.assertIn("self.reset_button = QtWidgets.QToolButton()", rendered)
        self.assertIn("Redefinir todos os padrões do Grid", rendered)
        self.assertIn("setAccessibleName", rendered)
        self.assertIn("QtGui.QIcon(GRID_RESET_DEFAULTS_ICON)", rendered)
        self.assertIn("self.reset_button.setIconSize(QtCore.QSize", rendered)
        self.assertNotIn("SP_BrowserReload", rendered)
        self.assertIn("self.reset_button.clicked.connect(self.reset_defaults)", rendered)

    def test_grid_color_swatches_open_full_dialog_directly_and_are_accessible(self):
        self.assertNotIn("QuickColorMenu", self.source)
        self.assertNotIn("_show_quick_color_menu", self.source)
        self.assertNotIn("moreColorsRequested", self.source)
        self.assertNotIn('QPushButton("Escolher cor")', self.source)
        for description in ("Cor das linhas", "Cor dos pontos", "Cor do texto"):
            self.assertIn(f'self._color_swatch("{description}")', self.source)
        for contract in ("button.setText(\"\")", "button.setToolTip(description)",
                         "button.setAccessibleName(description)",
                         "self._choose_color(selected_target)",
                         "QtWidgets.QColorDialog.getColor"):
            self.assertIn(contract, self.source)

    def test_full_color_dialog_applies_only_valid_color_to_requested_target(self):
        class Color:
            def __init__(self, value=None):
                if isinstance(value, Color): self.value, self.valid = value.value, value.valid
                else: self.value, self.valid = value, value is not None
            def isValid(self): return self.valid
            def __eq__(self, other): return isinstance(other, Color) and self.value == other.value
        class QColor(Color):
            def __init__(self, *value): super().__init__(value[0] if len(value) == 1 else tuple(value))
        selected_dialog = QColor("dialog")
        qt_gui = type("QtGui", (), {"QColor": QColor})
        qt_widgets = type("QtWidgets", (), {"QColorDialog": type("Dialog", (), {
            "getColor": staticmethod(lambda *_args: selected_dialog)
        })})
        Panel = extracted_panel_methods(
            self.tree, {"_color_for_target", "_choose_color", "_apply_color"},
            {"QtGui": qt_gui, "QtWidgets": qt_widgets}
        )
        panel = Panel()
        panel.line_color, panel.point_color, panel.text_color = (
            QColor("line"), QColor("point"), QColor("text")
        )
        panel._color_buttons = {"line": object(), "point": object(), "text": object()}
        panel.form = object(); panel.refreshes = panel.previews = 0
        panel._refresh_color_buttons = lambda: setattr(panel, "refreshes", panel.refreshes + 1)
        panel.update_preview = lambda: setattr(panel, "previews", panel.previews + 1)
        panel._apply_color("point", (1, 2, 3))
        self.assertEqual(panel.line_color.value, "line")
        self.assertEqual(panel.point_color.value, (1, 2, 3))
        self.assertEqual(panel.text_color.value, "text")
        panel._choose_color("text")
        self.assertEqual(panel.text_color.value, "dialog")
        self.assertEqual((panel.refreshes, panel.previews), (2, 2))

        selected_dialog.valid = False
        panel._choose_color("line")
        self.assertEqual(panel.line_color.value, "line")
        self.assertEqual((panel.refreshes, panel.previews), (2, 2))

    def test_reset_defaults_refreshes_all_color_swatches(self):
        panel = next(node for node in self.tree.body
                     if isinstance(node, ast.ClassDef) and node.name == "GridTaskPanel")
        reset = next(node for node in panel.body
                     if isinstance(node, ast.FunctionDef) and node.name == "reset_defaults")
        rendered = ast.unparse(reset)
        for name in ("line_color", "point_color", "text_color"):
            self.assertIn(f"self.{name} = QtGui.QColor.fromRgbF", rendered)
        self.assertLess(rendered.index("self._refresh_color_buttons()"),
                        rendered.index("self.update_preview()"))

    def test_escape_and_visual_view_properties_are_wired(self):
        for text in ("installEventFilter", "Key_Escape", "_EscapeEventFilter(self.reject", "ShowIntersections", "ShowLabels",
                     "LabelPosition", "FontSize", "TextColor", 'view.DrawStyle = "Dashdot"'):
            self.assertIn(text, self.source)
        self.assertNotIn("LabelFrame", self.source)

    def test_escape_cancels_once_removes_only_preview_aborts_and_closes(self):
        filter_node = next(node for node in self.tree.body if isinstance(node, ast.ClassDef) and node.name == "_EscapeEventFilter")
        panel_node = next(node for node in self.tree.body if isinstance(node, ast.ClassDef) and node.name == "GridTaskPanel")
        class QObject:
            def __init__(self, parent=None): self.parent = parent
            def eventFilter(self, _watched, _event): return False
            def deleteLater(self): self.deleted = True
        qt = type("Qt", (), {"Key": type("Key", (), {"Key_Escape": 27}), "Key_Escape": 27})
        qt_core = type("QtCore", (), {"QObject": QObject,
                                      "QEvent": type("QEvent", (), {"KeyPress": 6, "ShortcutOverride": 51}), "Qt": qt})
        application = Widget = None
        namespace = {"QtCore": qt_core}
        exec(compile(ast.Module(body=[filter_node, panel_node], type_ignores=[]), str(PANEL), "exec"), namespace)
        panel = namespace["GridTaskPanel"].__new__(namespace["GridTaskPanel"])
        class Widget(QObject):
            def __init__(self): super().__init__(); self.filters = []
            def installEventFilter(self, event_filter):
                if not isinstance(event_filter, QObject):
                    raise TypeError("installEventFilter requires QObject")
                self.filters.append(event_filter)
            def removeEventFilter(self, event_filter): self.filters.remove(event_filter)
            def findChildren(self, kind): return [] if kind is QObject else []
        application = Widget()
        namespace["QtWidgets"] = type("QtWidgets", (), {
            "QApplication": type("QApplication", (), {"instance": staticmethod(lambda: application)})})
        class Document:
            def __init__(self): self.names = ["ConfirmedGrid", "PreviewGrid"]; self.aborted = self.recomputed = 0
            def removeObject(self, name): self.names.remove(name)
            def abortTransaction(self): self.aborted += 1
            def recompute(self): self.recomputed += 1
        document = Document(); closed = []
        panel.document = document
        panel.grid_object = type("Object", (), {"Name": "PreviewGrid"})()
        panel.form = Widget(); panel._closed = False
        panel._on_closed = lambda _panel, accepted: closed.append(accepted)
        panel._escape_filter = None; panel._escape_filter_target = None
        with self.assertRaises(TypeError): panel.form.installEventFilter(panel)
        panel._install_escape_filter()
        self.assertIsInstance(panel._escape_filter, QObject)
        class Event:
            def __init__(self, event_type, key): self.event_type, self.key_value, self.accepted = event_type, key, False
            def type(self): return self.event_type
            def key(self): return self.key_value
            def accept(self): self.accepted = True
        event = Event(51, 27)
        other = type("Event", (), {"type": lambda self: 6, "key": lambda self: 65})()
        focused_widgets = [object() for _name in ("form", "spin", "list", "combo", "custom", "main_window")]
        for focused in focused_widgets:
            self.assertFalse(panel._escape_filter.eventFilter(focused, other))
        event_filter = panel._escape_filter
        self.assertTrue(event_filter.eventFilter(focused_widgets[-1], event))
        self.assertTrue(event.accepted)
        self.assertEqual((document.names, document.aborted, document.recomputed, closed),
                         (["ConfirmedGrid"], 1, 1, [False]))
        self.assertTrue(event_filter.eventFilter(focused_widgets[1], Event(6, 27)))
        self.assertEqual((document.names, document.aborted, closed), (["ConfirmedGrid"], 1, [False]))
        self.assertEqual(application.filters, [])

    def test_standard_buttons_unwrap_pyside6_value_before_int(self):
        function = next(node for node in self.tree.body if isinstance(node, ast.FunctionDef) and node.name == "standard_buttons_value")
        namespace = {}
        exec(compile(ast.Module(body=[function], type_ignores=[]), str(PANEL), "exec"), namespace)
        class StrictButton(enum.Flag):
            Ok = 1
            Cancel = 2
            def __int__(self):
                raise TypeError("PySide6 StandardButton is not directly convertible")
        box = type("ButtonBox", (), {"StandardButton": StrictButton})
        self.assertEqual(namespace["standard_buttons_value"](box), 3)


if __name__ == "__main__":
    unittest.main()
