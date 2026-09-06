# SPDX-License-Identifier: LGPL-2.1-or-later
"""Compact C1 truss controls, using the shared controller and profile editors."""

from __future__ import annotations

from copy import deepcopy
import math

from PySide import QtCore, QtGui, QtWidgets

from .. import profile_catalog
from ..profiles import ProfileRef, build_section_geometry, section_insertion_references
from .grid_task_panel import (
    SpacingDoubleSpinBox, standard_buttons_value, stabilize_compact_tool_button,
)
from .profile_options_widget import ProfileOptionsWidget
from .section_orientation_preview import SectionOrientationPreview
from .truss_preview import TrussPreview2D


ROLE_LABELS = (
    ("TOP_CHORD", "Banzo superior"),
    ("BOTTOM_CHORD", "Banzo inferior"),
    ("VERTICAL", "Montantes"),
    ("DIAGONAL", "Diagonais"),
    ("END_POST_LEFT", "Fechamento esquerdo"),
    ("END_POST_RIGHT", "Fechamento direito"),
)
CONTINUITIES = (
    ("Contínuo", "Continuous"),
    ("Dividir nas mudanças de direção", "SegmentAtBreaks"),
    ("Dividir em cada nó", "SegmentAtEveryNode"),
)
PREVIEW_DELAY_MS = 200


class _DisclosureButton(QtWidgets.QToolButton):
    """Keep the native text/focus handling, with a small palette-aware arrow."""

    def paintEvent(self, event):
        option = QtWidgets.QStyleOptionToolButton()
        self.initStyleOption(option)
        arrow = option.arrowType
        option.arrowType = QtCore.Qt.NoArrow
        option.features &= ~QtWidgets.QStyleOptionToolButton.Arrow
        option.state &= ~QtWidgets.QStyle.State_On
        option.rect.adjust(10, 0, 0, 0)
        painter = QtWidgets.QStylePainter(self)
        painter.drawComplexControl(QtWidgets.QStyle.CC_ToolButton, option)
        x, y = 5.0, self.height() / 2.0
        points = ((x - 3.5, y - 2.0), (x + 3.5, y - 2.0), (x, y + 2.0)) if arrow == QtCore.Qt.DownArrow else (
            (x - 2.0, y - 3.5), (x - 2.0, y + 3.5), (x + 2.0, y))
        color = option.palette.color(QtGui.QPalette.ButtonText)
        color.setAlphaF(0.65)
        painter.setPen(QtCore.Qt.NoPen)
        painter.setBrush(color)
        painter.drawPolygon(QtGui.QPolygonF([QtCore.QPointF(*point) for point in points]))


class _DisclosureHeader(QtWidgets.QWidget):
    """A flat disclosure row; the separator is part of its click target."""

    def __init__(self, title, expanded=False, parent=None):
        super().__init__(parent)
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        self.button = _DisclosureButton(self)
        self.button.setText(title)
        font = self.button.font()
        font.setBold(True)
        self.button.setFont(font)
        self.button.setAutoRaise(True)
        self.button.setCheckable(True)
        self.button.setChecked(expanded)
        self.button.setToolButtonStyle(QtCore.Qt.ToolButtonTextBesideIcon)
        self.button.setIconSize(QtCore.QSize(8, 8))
        self.button.setStyleSheet(
            "QToolButton { border: none; background: transparent; }"
        )
        self.button.toggled.connect(self._set_arrow)
        self._set_arrow(expanded)
        line = QtWidgets.QFrame(self)
        line.setFrameShape(QtWidgets.QFrame.NoFrame)
        line.setFixedHeight(1)
        line.setStyleSheet("QFrame { border: none; background-color: palette(mid); }")
        line.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents)
        layout.addWidget(self.button)
        layout.addWidget(line, 1)

    def _set_arrow(self, expanded):
        self.button.setArrowType(QtCore.Qt.DownArrow if expanded else QtCore.Qt.RightArrow)

    def mouseReleaseEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton and self.rect().contains(event.pos()):
            self.button.click()
            event.accept()
        else:
            super().mouseReleaseEvent(event)


def point_components(value):
    """Accept native FreeCAD vectors as well as the controller's JSON points."""
    values = (value.x, value.y, value.z) if hasattr(value, "x") else value
    result = [float(component) for component in values]
    if len(result) != 3 or not all(math.isfinite(component) for component in result):
        raise ValueError("O ponto deve ter três coordenadas finitas.")
    return result


def point_distance(start, end):
    return math.sqrt(sum((b - a) ** 2 for a, b in zip(start, end)))


def role_geometry(spec):
    ref = ProfileRef(**spec["profile_ref"])
    _category, _series, designation = profile_catalog.selection_for_ref(ref)
    profile = profile_catalog.get(designation)
    geometry = build_section_geometry(profile.definition, spec["section_geometry_mode"])
    return designation, geometry


def role_spec_from_options(previous, options):
    """Translate display labels into stable insertion IDs and real ProfileRefs."""
    spec = deepcopy(previous)
    ref = profile_catalog.ref_for_designation(options.profile_designation)
    profile = profile_catalog.get(options.profile_designation)
    geometry = build_section_geometry(profile.definition, options.section_geometry_mode)
    selected = options.insertion.currentText()
    insertion = next(
        (item.id for item in section_insertion_references(geometry)
         if selected in (item.id, item.label)), None,
    )
    if insertion is None:
        raise ValueError("Selecione uma referência de inserção válida.")
    spec.update(
        profile_ref={"catalog_id": ref.catalog_id, "profile_id": ref.profile_id},
        insertion=insertion, rotation=float(options.rotation.value()),
        section_geometry_mode=options.section_geometry_mode,
        color=[float(value) for value in options.rgb],
    )
    return spec


class _RoleProfileDialog(QtWidgets.QDialog):
    def __init__(self, document, title, spec, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self._previous = deepcopy(spec)
        self.options = ProfileOptionsWidget(document, self, element_types=("Membro",))
        self.options.setCheckable(False)
        self.options.name_edit.parentWidget().hide()
        self.options.set_profile_ref(ProfileRef(**spec["profile_ref"]))
        _designation, geometry = role_geometry(spec)
        insertion_label = next(
            (item.label for item in section_insertion_references(geometry)
             if spec["insertion"] in (item.id, item.label)), spec["insertion"],
        )
        state = self.options.state()
        state.update(
            insertion=insertion_label, rotation=spec["rotation"],
            generate_radii=spec["section_geometry_mode"] == "Detailed",
            color=QtGui.QColor.fromRgbF(*spec["color"]),
        )
        self.options.restore_state(state)
        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(self.options)
        from ..paths import ICONS_DIR
        rotation_area = QtWidgets.QWidget()
        rotation_layout = QtWidgets.QVBoxLayout(rotation_area)
        rotation_layout.setContentsMargins(0, 0, 0, 0)
        rotation_layout.setSpacing(3)
        orientation = self.options.orientation_panel
        orientation._controls_grid.removeWidget(self.options.rotation)
        rotation_layout.addWidget(self.options.rotation)
        quick = QtWidgets.QHBoxLayout()
        quick.setSpacing(3)
        self.rotation_buttons = []
        for icon, delta in (("TrussRotateClockwise.svg", -90), ("TrussRotateCounterclockwise.svg", 90)):
            button = QtWidgets.QToolButton()
            stabilize_compact_tool_button(button)
            button.setAutoRaise(True)
            button.setIcon(QtGui.QIcon(str(ICONS_DIR / icon)))
            button.setIconSize(QtCore.QSize(18, 18))
            button.setFixedSize(26, 26)
            button.setToolTip(f"Girar {delta:+d}\N{DEGREE SIGN}")
            button.setAccessibleName(button.toolTip())
            button.clicked.connect(lambda _checked=False, step=delta:
                self.options.rotation.setValue((self.options.rotation.value() + step + 180) % 360 - 180))
            quick.addWidget(button)
            self.rotation_buttons.append(button)
        quick.addStretch(1)
        rotation_layout.addLayout(quick)
        # Keep the shared responsive layout, changing only this dialog's slot.
        orientation._widgets[0] = rotation_area
        horizontal = orientation._horizontal
        orientation._horizontal = None
        orientation._apply_layout(horizontal)
        layout.addWidget(buttons)
        self.resize(460, 560)

    def role_spec(self):
        return role_spec_from_options(self._previous, self.options)


class TrussTaskPanel:
    """Own Qt state; document mutation, validation and previews belong to controller."""

    def __init__(self, document, controller, initial_config, on_close=None,
                 point_picker=None):
        self.document = document
        self.controller = controller
        self._initial = deepcopy(initial_config)
        self._role_specs = deepcopy(initial_config["role_specs"])
        for side in ("END_POST_LEFT", "END_POST_RIGHT"):
            if side not in self._role_specs:
                self._role_specs[side] = deepcopy(self._role_specs["END_POST"])
        self._on_close = on_close
        self._point_picker = point_picker
        self._closed = False
        self._updating = True
        self._valid = False
        self._last_preview_config = None
        self._point_generation = 0
        start, end = initial_config["start"], initial_config["end"]
        length = point_distance(start, end)
        self._axis_direction = (
            [(b - a) / length for a, b in zip(start, end)] if length > 1e-9 else None
        )
        self.form = QtWidgets.QWidget()
        try:
            self._build_form(initial_config)
        except Exception:
            # The controller still owns document cleanup; this form was never shown.
            self._closed = True
            self._on_close = None
            timer = getattr(self, "_preview_timer", None)
            if timer is not None:
                timer.stop()
            self.form.deleteLater()
            raise

    def _build_form(self, initial_config):
        self.form.setWindowTitle("Gerador de Treliças")
        root = QtWidgets.QVBoxLayout(self.form)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(5)
        self.preview = TrussPreview2D()
        root.addWidget(self.preview)
        self.summary = QtWidgets.QLabel()
        self.summary.setWordWrap(True)
        root.addWidget(self.summary)
        self.sections = {}
        self._build_geometry(root, initial_config)
        self._build_web(root, initial_config)
        self._build_profiles(root)
        self._build_reference(root, initial_config)
        self.show_3d = QtWidgets.QCheckBox("Preview 3D")
        self.show_3d.setChecked(True)
        root.addWidget(self.show_3d)
        self.message = QtWidgets.QLabel()
        self.message.setWordWrap(True)
        root.addWidget(self.message)
        root.addStretch(1)
        self._preview_timer = QtCore.QTimer(self.form)
        self._preview_timer.setSingleShot(True)
        self._preview_timer.setInterval(PREVIEW_DELAY_MS)
        self._preview_timer.timeout.connect(self._update_preview3d)
        self.show_3d.toggled.connect(self._toggle_preview3d)
        self._updating = False
        self._refresh()

    def _section(self, root, title, expanded=False):
        container = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(container)
        header = _DisclosureHeader(title, expanded)
        box = header.button
        layout.addWidget(header)
        layout.setContentsMargins(6, 5, 6, 5)
        content = QtWidgets.QWidget()
        form = QtWidgets.QFormLayout(content)
        form.setContentsMargins(0, 0, 0, 0)
        form.setSpacing(4)
        layout.addWidget(content)
        content.setVisible(expanded)
        box.toggled.connect(lambda checked: self._expand_section(title, checked))
        self.sections[title] = (box, content)
        root.addWidget(container)
        return form

    def _expand_section(self, title, expanded):
        for name, (box, content) in self.sections.items():
            if name == title:
                box.setArrowType(QtCore.Qt.DownArrow if expanded else QtCore.Qt.RightArrow)
                content.setVisible(expanded)
            elif expanded:
                previous = box.blockSignals(True)
                box.setChecked(False)
                box.setArrowType(QtCore.Qt.RightArrow)
                box.blockSignals(previous)
                content.hide()

    def _number(self, value, minimum=-1e9, maximum=1e9, suffix=" mm"):
        spin = SpacingDoubleSpinBox(lambda: None)
        spin.setRange(minimum, maximum)
        spin.setDecimals(3 if suffix else 6)
        spin.setSuffix(suffix)
        spin.setValue(0.0 if abs(float(value)) < 0.5e-6 else float(value))
        spin.setKeyboardTracking(False)
        return spin

    @staticmethod
    def _combo(options, value):
        combo = QtWidgets.QComboBox()
        for label, key in options:
            combo.addItem(label, key)
        index = combo.findData(value)
        if index >= 0:
            combo.setCurrentIndex(index)
        return combo

    def _build_geometry(self, root, config):
        form = self._section(root, "Geometria", True)
        self.envelope_type = self._combo(
            (("Paralela", "Parallel"), ("Duas águas", "DuoPitch")), config["envelope_type"]
        )
        self.span = self._number(point_distance(config["start"], config["end"]), 0)
        self.height = self._number(config["height"], 0)
        self.apex = self._number(config["apex_position"] * 100.0, 0, 100, " %")
        self.apex_label = QtWidgets.QLabel("Posição da cumeeira:")
        self.pitch_note = QtWidgets.QLabel("Duas águas: extremidades com altura zero.")
        self.pitch_note.setWordWrap(True)
        form.addRow("Forma:", self.envelope_type)
        form.addRow("Vão nominal:", self.span)
        form.addRow("Altura nominal:", self.height)
        form.addRow(self.apex_label, self.apex)
        form.addRow(self.pitch_note)
        self.envelope_type.currentIndexChanged.connect(self._refresh)
        self.height.valueChanged.connect(self._refresh)
        self.apex.valueChanged.connect(self._refresh)
        self.span.valueChanged.connect(self._span_changed)

    def _build_web(self, root, config):
        form = self._section(root, "Alma")
        self.preset = self._combo(
            (("Warren", "Warren"), ("Pratt", "Pratt")), config["topology_preset"]
        )
        self.panel_count = QtWidgets.QSpinBox()
        self.panel_count.setRange(4, 200)
        self.panel_count.setValue(config["panel_count"])
        self.panel_count.setKeyboardTracking(False)
        self.top_continuity = self._combo(CONTINUITIES, config["top_continuity"])
        self.bottom_continuity = self._combo(CONTINUITIES, config["bottom_continuity"])
        self.closure = QtWidgets.QLabel()
        self.closure.setWordWrap(True)
        form.addRow("Padrão:", self.preset)
        form.addRow("Número de painéis:", self.panel_count)
        form.addRow("Banzo superior:", self.top_continuity)
        form.addRow("Banzo inferior:", self.bottom_continuity)
        form.addRow(self.closure)
        for combo in (self.preset, self.top_continuity, self.bottom_continuity):
            combo.currentIndexChanged.connect(self._refresh)
        self.panel_count.valueChanged.connect(self._refresh)

    def _build_profiles(self, root):
        form = self._section(root, "Perfis")
        self.role_buttons = {}
        self.role_labels = {}
        for role, label in ROLE_LABELS:
            button = QtWidgets.QToolButton()
            button.setToolButtonStyle(QtCore.Qt.ToolButtonTextBesideIcon)
            button.setSizePolicy(QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Fixed)
            button.setMinimumWidth(150)
            button.setIconSize(QtCore.QSize(60, 42))
            button.setMinimumHeight(46)
            button.setAccessibleName("Editar perfil: " + label)
            button.clicked.connect(lambda _checked=False, key=role: self._edit_role(key))
            self.role_buttons[role] = button
            self.role_labels[role] = QtWidgets.QLabel(label + ":")
            form.addRow(self.role_labels[role], button)
            self._update_role_button(role)

    def _update_role_button(self, role):
        spec = self._role_specs[role]
        designation, geometry = role_geometry(spec)
        button = self.role_buttons[role]
        insertion = next(
            (item.label for item in section_insertion_references(geometry)
             if spec["insertion"] in (item.id, item.label)), spec["insertion"],
        )
        text = f"{designation}\n{insertion} · {spec['rotation']:g}°  ..."
        button.setText(text)
        button.setToolTip(text + "\nAbrir perfil, inserção e orientação")
        miniature = SectionOrientationPreview(self.form)
        miniature.set_geometry(geometry, spec["insertion"], spec["rotation"])
        miniature.resize(miniature.sizeHint())
        pixmap = QtGui.QPixmap(120, 84)
        pixmap.fill(QtCore.Qt.transparent)
        painter = QtGui.QPainter(pixmap)
        try:
            painter.scale(120.0 / miniature.width(), 84.0 / miniature.height())
            miniature.render(painter, QtCore.QPoint())
        finally:
            painter.end()
            miniature.deleteLater()
        button.setIcon(QtGui.QIcon(pixmap))

    def _edit_role(self, role):
        title = dict(ROLE_LABELS)[role]
        dialog = _RoleProfileDialog(self.document, title, self._role_specs[role], self.form)
        if dialog.exec() == QtWidgets.QDialog.Accepted:
            self._role_specs[role] = dialog.role_spec()
            self._update_role_button(role)
            self._refresh()

    def _vector_inputs(self, value, *, normal=False):
        container = QtWidgets.QWidget()
        layout = QtWidgets.QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(3)
        spins = []
        for axis, component in zip(("X", "Y", "Z"), value):
            spin = self._number(component, suffix="")
            spin.setSizePolicy(QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Fixed)
            spin.setMinimumWidth(65)
            # Display precision must not quantize picked/restored frame coordinates.
            spin._truss_exact_value = float(component)
            spin._truss_display_value = float(spin.value())
            spin.setToolTip(("Normal " if normal else "Coordenada global ") + axis)
            spin.setAccessibleName(("Normal " if normal else "Coordenada global ") + axis)
            layout.addWidget(spin)
            spins.append(spin)
        return container, spins

    def _build_reference(self, root, config):
        form = self._section(root, "Referência")
        start_widget, self.start_inputs = self._vector_inputs(config["start"])
        end_widget, self.end_inputs = self._vector_inputs(config["end"])
        normal_widget, self.normal_inputs = self._vector_inputs(config["plane_normal"], normal=True)
        form.addRow("Modo:", QtWidgets.QLabel("Dois pontos"))
        advanced = QtWidgets.QWidget()
        advanced_form = QtWidgets.QFormLayout(advanced)
        advanced_form.addRow("P0 (X, Y, Z), mm:", start_widget)
        advanced_form.addRow("P1 (X, Y, Z), mm:", end_widget)
        advanced_form.addRow("Normal (X, Y, Z):", normal_widget)
        axes = QtWidgets.QLabel("X segue P0 ? P1; Y = normal ? X.")
        axes.setWordWrap(True)
        advanced_form.addRow(axes)
        advanced.hide()
        header = QtWidgets.QToolButton()
        header.setText("? Avan?ado")
        header.setCheckable(True)
        header.toggled.connect(lambda checked: (
            advanced.setVisible(checked), header.setText(("? " if checked else "? ") + "Avan?ado")))
        self.pick_button = QtWidgets.QPushButton("Selecionar dois pontos")
        self.pick_button.setEnabled(self._point_picker is not None)
        self.pick_button.clicked.connect(self._pick_points)
        form.addRow(self.pick_button)
        self.plane_label = QtWidgets.QLabel()
        self.plane_label.setWordWrap(True)
        form.addRow(self.plane_label)
        form.addRow(header)
        form.addRow(advanced)
        for spin in self.start_inputs + self.end_inputs:
            spin.valueChanged.connect(self._points_changed)
        for spin in self.normal_inputs:
            spin.valueChanged.connect(self._refresh)

    @staticmethod
    def _read_vector(spins):
        return [
            (spin._truss_exact_value
             if hasattr(spin, "_truss_display_value")
             and float(spin.value()) == spin._truss_display_value
             else float(spin.value()))
            for spin in spins
        ]

    @staticmethod
    def _write_vector(spins, value):
        for spin, component in zip(spins, value):
            previous = spin.blockSignals(True)
            spin.setValue(0.0 if abs(component) < 0.5e-6 else component)
            spin._truss_exact_value = float(component)
            spin._truss_display_value = float(spin.value())
            spin.blockSignals(previous)

    def get_config(self):
        config = deepcopy(self._initial)
        start = self._read_vector(self.start_inputs)
        end = self._read_vector(self.end_inputs)
        config.update(
            envelope_type=self.envelope_type.currentData(),
            span=point_distance(start, end), height=float(self.height.value()),
            apex_position=float(self.apex.value()) / 100.0,
            panel_count=int(self.panel_count.value()),
            topology_preset=self.preset.currentData(),
            top_continuity=self.top_continuity.currentData(),
            bottom_continuity=self.bottom_continuity.currentData(),
            start=start, end=end, plane_normal=self._read_vector(self.normal_inputs),
            role_specs=deepcopy(self._role_specs),
        )
        return config

    def _points_changed(self, _value=None):
        if self._updating or self._closed:
            return
        start, end = self._read_vector(self.start_inputs), self._read_vector(self.end_inputs)
        length = point_distance(start, end)
        if length > 1e-9:
            self._axis_direction = [(b - a) / length for a, b in zip(start, end)]
        previous = self.span.blockSignals(True)
        self.span.setValue(length)
        self.span.blockSignals(previous)
        self._refresh()

    def _span_changed(self, value):
        if self._updating or self._closed:
            return
        if self._axis_direction is None:
            self._show_error("Defina dois pontos distintos para estabelecer a direção do vão.")
            return
        start = self._read_vector(self.start_inputs)
        end = [a + float(value) * direction for a, direction in zip(start, self._axis_direction)]
        self._write_vector(self.end_inputs, end)
        self._refresh()

    def _pick_points(self):
        if self._closed or self._point_picker is None:
            return
        self._point_generation += 1
        generation = self._point_generation
        self.pick_button.setEnabled(False)
        self.message.setText("Selecione P0 e P1 na vista 3D; o plano continua explícito.")
        def received(start, end, normal=None):
            if self._closed or generation != self._point_generation:
                return
            self.pick_button.setEnabled(True)
            if start is None or end is None:
                self._refresh()
                return
            try:
                start_value = point_components(start)
                end_value = point_components(end)
            except (TypeError, ValueError) as exc:
                self._show_error(str(exc))
                return
            if normal is not None:
                self._write_vector(self.normal_inputs, point_components(normal))
            self._write_vector(self.start_inputs, start_value)
            self._write_vector(self.end_inputs, end_value)
            self._points_changed()
        try:
            self._point_picker(received)
        except (RuntimeError, ValueError) as exc:
            self.pick_button.setEnabled(True)
            self._show_error(str(exc))

    def _show_error(self, message):
        self._preview_timer.stop()
        self._valid = False
        self.message.setText("Entrada inválida: " + message + "\nPreview anterior desatualizado.")
        self.message.setStyleSheet("color: #b33;")
        self._set_accept_enabled(False)

    def _refresh(self, _value=None):
        if self._updating or self._closed:
            return False
        self._preview_timer.stop()
        config = self.get_config()
        pitched = config["envelope_type"] == "DuoPitch"
        for widget in (self.apex, self.apex_label, self.pitch_note):
            widget.setVisible(pitched)
        normal = config["plane_normal"]
        self.plane_label.setText(
            "Normal explícita: (%g, %g, %g). X segue P0 → P1; Y = normal × X."
            % tuple(normal)
        )
        try:
            model = self.controller.preview(config)
            self.preview.set_model(model)
            present = {edge["role"] for edge in model["edges"]}
            for role, button in getattr(self, "role_buttons", {}).items():
                visible = ("END_POST" if role.startswith("END_POST_") else role) in present
                button.setVisible(visible)
                self.role_labels[role].setVisible(visible)
        except (ValueError, RuntimeError) as exc:
            self._show_error(str(exc))
            return False
        self._last_preview_config = deepcopy(config)
        self._valid = True
        self._set_accept_enabled(True)
        self.summary.setText(f"{len(model['nodes'])} nós · {len(model['edges'])} barras nominais")
        stations = sorted({float(item["x"]) for item in model["stations"]})
        if pitched:
            apex_x = config["span"] * config["apex_position"]
            tolerance = max(config["span"], 1.0) * 1e-9
            left = model.get("left_panels")
            right = model.get("right_panels")
            if left is None:
                left = sum(x < apex_x - tolerance for x in stations)
            if right is None:
                right = sum(x > apex_x + tolerance for x in stations)
            self.closure.setText(f"Fechamento: {left} painéis à esquerda + {right} à direita.")
        else:
            self.closure.setText(f"Fechamento: {max(len(stations) - 1, 0)} painéis no vão.")
        warnings = list(model.get("warnings", ()))
        self.message.setStyleSheet("")
        self.message.setText("\n".join(warnings + ["Preview 2D atualizado."]))
        if self.show_3d.isChecked():
            self._preview_timer.start()
        return True

    def _update_preview3d(self):
        if self._closed or not self._valid or not self.show_3d.isChecked():
            return
        config = self.get_config()
        if config != self._last_preview_config:
            self._refresh()
            return
        try:
            self.controller.preview3d(config, enabled=True)
        except (ValueError, RuntimeError) as exc:
            self._show_error(str(exc))

    def _toggle_preview3d(self, enabled):
        if self._closed:
            return
        self._preview_timer.stop()
        if enabled:
            self._refresh()
        else:
            self.controller.preview3d(self.get_config(), enabled=False)

    def _set_accept_enabled(self, enabled):
        window = self.form.window()
        buttons = window.findChild(QtWidgets.QDialogButtonBox)
        if buttons is not None:
            button = buttons.button(QtWidgets.QDialogButtonBox.Ok)
            if button is not None:
                button.setEnabled(bool(enabled))

    def accept(self):
        if self._closed:
            return True
        self._preview_timer.stop()
        if not self._refresh():
            return False
        self._preview_timer.stop()
        try:
            self.controller.accept(self.get_config())
        except (ValueError, RuntimeError) as exc:
            self._show_error(str(exc))
            return False
        self._finish()
        return True

    def reject(self):
        if self._closed:
            return True
        self._preview_timer.stop()
        self._point_generation += 1
        try:
            self.controller.cancel()
        finally:
            self._finish()
        return True

    def _finish(self):
        if self._closed:
            return
        self._closed = True
        self._point_generation += 1
        self._preview_timer.stop()
        callback, self._on_close = self._on_close, None
        if callback is not None:
            try:
                callback()
            except Exception:
                # Preserve the original integration error after releasing Qt ownership.
                self.form.deleteLater()
                raise

    def getStandardButtons(self):
        return standard_buttons_value(QtWidgets.QDialogButtonBox)


__all__ = ["TrussTaskPanel"]
