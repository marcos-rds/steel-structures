"""Headless integration checks for Profile Browser selection in shared options."""

from __future__ import annotations

import importlib.util
import sys
import types
import unittest
from pathlib import Path

from freecad.SteelStructures import profile_catalog


ROOT = Path(__file__).resolve().parents[1]


def _load_options_runtime_module():
    root_name = "_profile_options_runtime"
    root = types.ModuleType(root_name)
    root.__path__ = []
    interactive = types.ModuleType(root_name + ".interactive")
    interactive.__path__ = []
    pyside = types.ModuleType("PySide")
    pyside.QtCore = types.SimpleNamespace(Signal=lambda *_args: object())
    pyside.QtGui = types.SimpleNamespace()
    pyside.QtWidgets = types.SimpleNamespace(
        QGroupBox=object, QPushButton=object, QToolButton=object,
        QDialog=types.SimpleNamespace(Accepted=1)
    )
    member = types.ModuleType(root_name + ".member")
    member.ELEMENT_TYPES = ("Membro", "Pilar")
    member.INSERTION_OPTIONS = ("Centro",)
    preferences = types.ModuleType(root_name + ".preferences")
    preferences.MemberCreationSettings = object
    controller = types.ModuleType(root_name + ".interactive.member_controller")
    controller.CreationGeometryMode = types.SimpleNamespace(INTERACTIVE=object())
    controller.MemberCreationOptions = object
    controller.compact_profile_designation = lambda value: value
    controller.next_default_label = lambda *_args: "Membro"
    orientation = types.ModuleType(root_name + ".interactive.section_orientation_preview")
    orientation.SectionOrientationPreview = object
    quick_color = types.ModuleType(root_name + ".interactive.quick_color_menu")
    quick_color.QuickColorMenu = object
    injected = {
        root_name: root,
        root_name + ".interactive": interactive,
        root_name + ".profile_catalog": profile_catalog,
        root_name + ".profiles": sys.modules["freecad.SteelStructures.profiles"],
        root_name + ".member": member,
        root_name + ".preferences": preferences,
        root_name + ".interactive.member_controller": controller,
        root_name + ".interactive.quick_color_menu": quick_color,
        root_name + ".interactive.section_orientation_preview": orientation,
        "PySide": pyside,
    }
    previous = {name: sys.modules.get(name) for name in injected}
    sys.modules.update(injected)
    path = ROOT / "freecad/SteelStructures/interactive/profile_options_widget.py"
    spec = importlib.util.spec_from_file_location(
        root_name + ".interactive.profile_options_widget", path
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        for name, old in previous.items():
            if old is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = old
    return module


class _Signal:
    def __init__(self):
        self.values = []

    def emit(self, value):
        self.values.append(value)


class _Combo:
    def __init__(self, items=()):
        self.items = [(value, value) for value in items]
        self.index = 0 if self.items else -1
        self.blocked = False
        self.currentIndexChanged = _Signal()

    def blockSignals(self, blocked):
        previous, self.blocked = self.blocked, blocked
        return previous

    def clear(self):
        self.items = []
        self.index = -1

    def addItems(self, values):
        self.items.extend((value, value) for value in values)
        if self.index < 0 and self.items:
            self.index = 0

    def addItem(self, text, data):
        self.items.append((text, data))
        if self.index < 0:
            self.index = 0

    def findData(self, data):
        return next((i for i, item in enumerate(self.items) if item[1] == data), -1)

    def setCurrentIndex(self, index):
        self.index = index

    def setCurrentText(self, text):
        index = next((i for i, item in enumerate(self.items) if item[0] == text), -1)
        if index >= 0:
            self.index = index

    def currentIndex(self):
        return self.index

    def currentText(self):
        return self.items[self.index][0] if self.index >= 0 else ""

    def currentData(self):
        return self.items[self.index][1] if self.index >= 0 else None


class ProfileOptionsBrowserIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = _load_options_runtime_module()

    def make_widget(self):
        widget = types.SimpleNamespace(
            category=_Combo(profile_catalog.categories()),
            series=_Combo(profile_catalog.series_for_category("Aço Laminado")),
            profile=_Combo(), insertion="Centro", rotation=17.0,
            color=(0.1, 0.2, 0.3), height=4321.0, refreshed=0,
        )
        for designation in profile_catalog.designations("Aço Laminado", "Perfis W"):
            widget.profile.addItem(designation, designation)
        widget.refresh_automatic_name = lambda: setattr(
            widget, "refreshed", widget.refreshed + 1
        )
        widget.set_profile_ref = types.MethodType(
            self.module.ProfileOptionsWidget.set_profile_ref, widget
        )
        return widget

    def test_confirming_hp_updates_three_combos_and_emits_one_profile_change(self):
        widget = self.make_widget()
        selected = profile_catalog.ref_for_designation("HP 310 x 132,0")
        widget.set_profile_ref(selected)
        self.assertEqual(widget.category.currentText(), "Aço Laminado")
        self.assertEqual(widget.series.currentText(), "Perfis HP")
        self.assertEqual(widget.profile.currentData(), "HP 310 x 132,0")
        self.assertEqual(widget.profile.currentIndexChanged.values, [widget.profile.currentIndex()])
        self.assertEqual(widget.refreshed, 1)
        self.assertEqual((widget.insertion, widget.rotation, widget.color, widget.height),
                         ("Centro", 17.0, (0.1, 0.2, 0.3), 4321.0))

    def test_cancel_does_not_read_or_apply_the_dialog_selection(self):
        widget = self.make_widget()
        before = (widget.category.currentText(), widget.series.currentText(), widget.profile.currentData())
        dialog = types.SimpleNamespace(
            exec=lambda: 0,
            selected_profile_ref=lambda: self.fail("selection must not be read after cancel"),
        )
        widget._create_profile_browser_dialog = lambda: dialog
        widget.set_profile_ref = lambda _ref: self.fail("selection must not be applied after cancel")
        self.module.ProfileOptionsWidget._open_profile_browser(widget)
        after = (widget.category.currentText(), widget.series.currentText(), widget.profile.currentData())
        self.assertEqual(after, before)

    def test_insertion_combo_switches_between_w_and_equal_angle_options(self):
        widget = object.__new__(self.module.ProfileOptionsWidget)
        widget.profile = _Combo()
        widget.insertion = _Combo(("Face superior",))
        for designation in profile_catalog.designations("Aço Laminado", "Perfis W"):
            widget.profile.addItem(designation, designation)
        widget.profile.setCurrentIndex(widget.profile.findData("W 150 x 13,0"))
        self.module.ProfileOptionsWidget._refresh_insertion_options(widget)
        self.assertIn("Face superior", [item[0] for item in widget.insertion.items])

        widget.profile.clear()
        for designation in profile_catalog.designations("Aço Laminado", "Cantoneiras - Métricas"):
            widget.profile.addItem(designation, designation)
        widget.profile.setCurrentIndex(widget.profile.findData("L 50 x 5"))
        self.module.ProfileOptionsWidget._refresh_insertion_options(widget)
        self.assertEqual([item[0] for item in widget.insertion.items], [
            "Centroide", "Centro do envelope", "Quina externa", "Ponta superior",
            "Ponta direita", "Quina interna",
        ])
        self.assertEqual(widget.insertion.currentText(), "Centroide")

        widget.profile.clear()
        for designation in profile_catalog.designations("Aço Laminado", "Perfis W"):
            widget.profile.addItem(designation, designation)
        widget.profile.setCurrentIndex(widget.profile.findData("W 150 x 13,0"))
        self.module.ProfileOptionsWidget._refresh_insertion_options(widget)
        self.assertEqual(widget.insertion.currentText(), "Centroide")

    def test_browser_creation_receives_current_insertion_without_global_state(self):
        source = (ROOT / "freecad/SteelStructures/interactive/profile_options_widget.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("insertion=self.insertion.currentText()", source)

    def test_local_preview_uses_current_profile_insertion_and_rotation(self):
        class Preview:
            def __init__(self): self.calls = []
            def set_geometry(self, *args): self.calls.append(args)

        widget = object.__new__(self.module.ProfileOptionsWidget)
        widget.profile = _Combo()
        widget.profile.addItem('U 6" x 12,20', 'U 6" x 12,20')
        widget.insertion = _Combo(("Face externa da alma",))
        widget.rotation = types.SimpleNamespace(value=lambda: 45.0)
        widget.orientation_preview = Preview()
        widget.document = types.SimpleNamespace(
            recompute=lambda: self.fail("local preview must not recompute the document")
        )
        self.module.ProfileOptionsWidget._update_orientation_preview(widget)
        geometry, insertion, rotation = widget.orientation_preview.calls[-1]
        self.assertEqual(geometry.geometry_type, "channel_section")
        self.assertEqual((insertion, rotation), ("Face externa da alma", 45.0))

    def test_unavailable_profile_clears_local_preview_without_document_mutation(self):
        class Preview:
            def __init__(self): self.calls = []
            def set_geometry(self, *args): self.calls.append(args)

        widget = object.__new__(self.module.ProfileOptionsWidget)
        widget.profile = _Combo()
        widget.profile.addItem('U 3" x 7,44', 'U 3" x 7,44')
        widget.insertion = _Combo(("Centroide",))
        widget.rotation = types.SimpleNamespace(value=lambda: 0.0)
        widget.orientation_preview = Preview()
        widget.document = types.SimpleNamespace(
            recompute=lambda: self.fail("local preview must not recompute the document")
        )
        self.module.ProfileOptionsWidget._update_orientation_preview(widget)
        self.assertIsNone(widget.orientation_preview.calls[-1][0])

    def test_graphic_and_combo_are_wired_bidirectionally(self):
        source = (ROOT / "freecad/SteelStructures/interactive/profile_options_widget.py").read_text(
            encoding="utf-8"
        )
        self.assertIn(
            "referenceSelected.connect(self._select_insertion_reference)", source
        )
        self.assertIn(
            "currentTextChanged.connect(self.orientation_preview.set_insertion)", source
        )
        self.assertIn(
            "valueChanged.connect(self.orientation_preview.set_rotation)", source
        )
        self.assertIn("_InsertionMenuButton(self.insertion)", source)
        self.assertIn("self.insertion_selector.refresh()", source)

    def test_responsive_breakpoint_uses_actual_available_width(self):
        choose = self.module.orientation_uses_columns
        self.assertFalse(choose(359, 180, 170, 10))
        self.assertTrue(choose(360, 180, 170, 10))
        self.assertTrue(choose(500, 180, 170, 10))

    def test_layout_switch_reuses_controls_instead_of_recreating_them(self):
        source = (ROOT / "freecad/SteelStructures/interactive/profile_options_widget.py").read_text(
            encoding="utf-8"
        )
        method = source.split("    def _apply_layout", 1)[1].split(
            "    def resizeEvent", 1
        )[0]
        for constructor in (
            "QComboBox(", "QDoubleSpinBox(", "QPushButton(",
            "SectionOrientationPreview(",
        ):
            self.assertNotIn(constructor, method)
        self.assertIn("self._preview_area", method)
        self.assertIn("self._widgets", method)

    def test_catalog_button_and_textual_insertion_menu_are_accessible(self):
        source = (ROOT / "freecad/SteelStructures/interactive/profile_options_widget.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("profile_browser_button = QtWidgets.QToolButton()", source)
        self.assertIn('profile_browser_button.setText("...")', source)
        self.assertIn("QtCore.Qt.ToolButtonTextOnly", source)
        self.assertIn('setToolTip("Abrir Catálogo de Perfis")', source)
        self.assertIn('setAccessibleName("Abrir Catálogo de Perfis")', source)
        self.assertIn("setMinimumWidth(button_width)", source)
        self.assertIn("setMaximumWidth(button_width)", source)
        self.assertIn("profile_browser_button.sizeHint().width()", source)
        self.assertIn("self.setMenu(self._menu)", source)
        self.assertIn('self._full_text = "Inserção: %s" % current', source)
        self.assertIn("self.combo.setCurrentText(value)", source)

    def test_catalog_button_width_prefers_native_hint_and_a_practical_minimum(self):
        safe_width = self.module.catalog_button_safe_width
        self.assertEqual(safe_width(24, 15), 36)
        self.assertEqual(safe_width(24, 20), 48)
        self.assertEqual(safe_width(54, 15), 54)

    def test_catalog_button_foreground_uses_palette_contrast_not_fixed_theme_colors(self):
        class Color:
            def __init__(self, red, green, blue, name):
                self.channels = red, green, blue
                self.value = name

            def redF(self): return self.channels[0]
            def greenF(self): return self.channels[1]
            def blueF(self): return self.channels[2]
            def name(self): return self.value

        class Palette:
            def __init__(self, colors): self.colors = colors
            def color(self, role): return self.colors[role]

        roles = types.SimpleNamespace(Button=1, ButtonText=2, Text=3, WindowText=4)
        previous = getattr(self.module.QtGui, "QPalette", None)
        self.module.QtGui.QPalette = roles
        try:
            dark = Palette({
                roles.Button: Color(0.10, 0.10, 0.10, "dark-background"),
                roles.ButtonText: Color(0.12, 0.12, 0.12, "low-contrast"),
                roles.Text: Color(0.90, 0.90, 0.90, "light-foreground"),
                roles.WindowText: Color(0.70, 0.70, 0.70, "medium-foreground"),
            })
            light = Palette({
                roles.Button: Color(0.92, 0.92, 0.92, "light-background"),
                roles.ButtonText: Color(0.10, 0.10, 0.10, "dark-foreground"),
                roles.Text: Color(0.30, 0.30, 0.30, "medium-foreground"),
                roles.WindowText: Color(0.85, 0.85, 0.85, "low-contrast"),
            })
            self.assertEqual(
                self.module.catalog_button_foreground(dark).name(), "light-foreground"
            )
            self.assertEqual(
                self.module.catalog_button_foreground(light).name(), "dark-foreground"
            )
        finally:
            if previous is None:
                delattr(self.module.QtGui, "QPalette")
            else:
                self.module.QtGui.QPalette = previous

        source = (ROOT / "freecad/SteelStructures/interactive/profile_options_widget.py").read_text(
            encoding="utf-8"
        )
        self.assertIn('setObjectName("profileCatalogButton")', source)
        self.assertIn("QToolButton#profileCatalogButton { color: %s; }", source)
        self.assertNotIn("color: white", source)
        self.assertNotIn("color: black", source)
        self.assertNotIn("OpenDark", source)

    def test_profile_updates_cannot_clear_the_shared_catalog_button_text(self):
        source = (ROOT / "freecad/SteelStructures/interactive/profile_options_widget.py").read_text(
            encoding="utf-8"
        )
        self.assertEqual(source.count("profile_browser_button = QtWidgets.QToolButton()"), 1)
        self.assertEqual(source.count('profile_browser_button.setText("...")'), 1)
        self.assertNotIn("profile_browser_button.setIcon", source)
        for method_name in (
            "set_profile_ref", "_category_changed", "_series_changed",
            "_profile_changed", "apply_creation_settings", "restore_state",
        ):
            method = source.split(f"    def {method_name}", 1)[1].split("\n    def ", 1)[0]
            self.assertNotIn("profile_browser_button", method)

    def test_member_and_column_use_the_same_catalog_button_owner(self):
        member_source = (
            ROOT / "freecad/SteelStructures/interactive/draft_member_tool.py"
        ).read_text(encoding="utf-8")
        column_source = (
            ROOT / "freecad/SteelStructures/interactive/column_task_panel.py"
        ).read_text(encoding="utf-8")
        self.assertIn("self.profile_options = ProfileOptionsWidget(self.doc)", member_source)
        self.assertIn(
            'self.profile_options = ProfileOptionsWidget(document, element_types=("Pilar",))',
            column_source,
        )
        self.assertNotIn("profile_browser_button", member_source)
        self.assertNotIn("profile_browser_button", column_source)

    def test_orientation_control_spacing_groups_each_label_with_its_widget(self):
        source = (ROOT / "freecad/SteelStructures/interactive/profile_options_widget.py").read_text(
            encoding="utf-8"
        )
        method = source.split("    def _apply_layout", 1)[1].split(
            "    def resizeEvent", 1
        )[0]
        self.assertIn("base = row * 3", method)
        self.assertIn("setVerticalSpacing(max(round(line * 0.22), 2))", method)
        self.assertIn("base + 2, max(round(line * 0.45), 6)", method)
        self.assertIn("self._controls, 0, 1, QtCore.Qt.AlignTop", method)

    def test_graphic_hotspot_id_is_resolved_to_existing_combo_label(self):
        source = (ROOT / "freecad/SteelStructures/interactive/profile_options_widget.py").read_text(
            encoding="utf-8"
        )
        method = source.split("    def _select_insertion_reference", 1)[1].split(
            "    def _update_orientation_preview", 1
        )[0]
        self.assertIn("reference_label(identifier)", method)
        self.assertIn("self.insertion.setCurrentText(label)", method)

    def test_color_swatch_reflects_current_color_without_text(self):
        class Color:
            def __init__(self, value): self.value = value
            def name(self): return self.value

        class Button:
            def __init__(self): self.styles = []
            def setStyleSheet(self, value): self.styles.append(value)

        widget = object.__new__(self.module.ProfileOptionsWidget)
        widget._color = Color("#f4d03f")
        widget.color_button = Button()
        widget.palette = lambda: types.SimpleNamespace(
            color=lambda _role: Color("#737373")
        )
        self.module.QtGui.QPalette = types.SimpleNamespace(Mid=1)
        self.module.ProfileOptionsWidget._update_color_button(widget)
        style = widget.color_button.styles[-1]
        self.assertIn("background-color: #f4d03f", style)
        self.assertIn("border: 1px solid #737373", style)
        self.assertNotIn("color:", style.replace("background-color:", ""))

    def test_quick_and_full_color_paths_update_one_state_and_emit_one_signal(self):
        class Color:
            def __init__(self, *value):
                if len(value) == 1 and isinstance(value[0], Color):
                    self.value = value[0].value
                else:
                    self.value = tuple(value)
            def isValid(self): return True
            def __eq__(self, other): return isinstance(other, Color) and self.value == other.value

        class Signal:
            def __init__(self): self.count = 0
            def emit(self): self.count += 1

        previous = getattr(self.module.QtGui, "QColor", None)
        self.module.QtGui.QColor = Color
        try:
            widget = object.__new__(self.module.ProfileOptionsWidget)
            widget._color = Color(1, 2, 3)
            widget.colorChanged = Signal()
            widget.updates = 0
            widget._update_color_button = lambda: setattr(
                widget, "updates", widget.updates + 1
            )
            self.module.ProfileOptionsWidget._apply_color(widget, (55, 111, 166))
            self.assertEqual(widget._color, Color(55, 111, 166))
            self.assertEqual((widget.updates, widget.colorChanged.count), (1, 1))
            self.module.ProfileOptionsWidget._apply_color(widget, Color(55, 111, 166))
            self.assertEqual((widget.updates, widget.colorChanged.count), (1, 1))
        finally:
            if previous is None:
                delattr(self.module.QtGui, "QColor")
            else:
                self.module.QtGui.QColor = previous


if __name__ == "__main__":
    unittest.main()
