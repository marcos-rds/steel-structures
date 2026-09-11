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
        from ..trusses.editing import custom_state
        initial_config=custom_state(initial_config)
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
        if initial_config.get("reference_mode")=="DraftRectangle" and not initial_config.get("reference_edge"):
            self.sections["Referência"][0].setChecked(True)
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
        from ..trusses.preset_contracts import PRESETS, compatible_presets
        from .grid_task_panel import SpacingEditor
        class TrussSpacingEditor(SpacingEditor):
            # Grid displays two decimals. Preserve reference-derived spacings
            # exactly until the user edits them, including an explicit remainder.
            def _append(self,value):
                spin=super()._append(value)
                blocked=spin.blockSignals(True)
                spin.setDecimals(6)
                spin.setValue(value)
                spin._truss_exact_value=float(value)
                spin._truss_display_value=float(spin.value())
                spin.blockSignals(blocked)
                return spin

            def values(self):
                return [spin._truss_exact_value if spin.value()==spin._truss_display_value
                        else float(spin.value()) for spin in self._spins]

        form = self._section(root, "Alma")
        self.preset = self._combo(
            tuple(("Custom" if key=="Custom" else PRESETS[key].label,key) for key in compatible_presets(config["envelope_type"])), config["topology_preset"]
        )
        self.topology_state=QtWidgets.QLabel()
        self.driver=self._combo((("Número de painéis","ByPanelCount"),("Espaçamento desejado","ByTargetSpacing"),
                                 ("Ângulo desejado das diagonais","ByTargetDiagonalAngle"),("Lista de espaçamentos","CustomSpacingList")),
                                config.get("panelization_mode","ByPanelCount"))
        self.target_spacing=self._number(config.get("target_spacing",1000.),.001)
        self.target_angle=self._number(config.get("target_angle",45.),.01,89.99,"°")
        self.spacing_editor=TrussSpacingEditor("Espaçamentos absolutos",config.get("custom_spacings",[config["span"]/config["panel_count"]]*config["panel_count"]),self._refresh)
        self.spacing_editor.summary.hide()
        self.x_connection=self._combo((("Sem conexão central","Disconnected"),("Conectado: nó central + 4 segmentos","Connected")),config.get("x_connection","Disconnected"))
        self.x_label=QtWidgets.QLabel("Variante X:")
        self.panel_count = QtWidgets.QSpinBox()
        self.panel_count.setRange(4, 200)
        self.panel_count.setValue(config["panel_count"])
        self.panel_count.setKeyboardTracking(False)
        self.top_continuity = self._combo(CONTINUITIES, config["top_continuity"])
        self.bottom_continuity = self._combo(CONTINUITIES, config["bottom_continuity"])
        self.closure = QtWidgets.QLabel()
        self.closure.setWordWrap(True)
        form.addRow("Padrão:", self.preset)
        form.addRow(self.topology_state)
        form.addRow("Panelização:",self.driver)
        form.addRow("Número de painéis:", self.panel_count)
        self.target_spacing_label=QtWidgets.QLabel("Espaçamento desejado:")
        self.target_angle_label=QtWidgets.QLabel("Ângulo desejado:")
        form.addRow(self.target_spacing_label,self.target_spacing)
        form.addRow(self.target_angle_label,self.target_angle)
        form.addRow(self.spacing_editor)
        self.spacing_balance=QtWidgets.QLabel()
        self.complete_span=QtWidgets.QPushButton("Completar vão")
        self.complete_span.clicked.connect(self._complete_span)
        form.addRow(self.spacing_balance)
        form.addRow(self.complete_span)
        form.addRow(self.x_label,self.x_connection)
        actions=QtWidgets.QWidget()
        actions_layout=QtWidgets.QHBoxLayout(actions)
        actions_layout.setContentsMargins(0,0,0,0)
        for label,callback in (("Editar alma…",self._open_topology_editor),("Restaurar padrão",self._restore_topology)):
            button=QtWidgets.QPushButton(label)
            button.clicked.connect(callback)
            actions_layout.addWidget(button)
        form.addRow(actions)
        form.addRow("Banzo superior:", self.top_continuity)
        form.addRow("Banzo inferior:", self.bottom_continuity)
        form.addRow(self.closure)
        self.preset.currentIndexChanged.connect(self._preset_changed)
        for combo in (self.top_continuity, self.bottom_continuity):
            combo.currentIndexChanged.connect(self._refresh)
        self.panel_count.valueChanged.connect(self._refresh)
        self.driver.currentIndexChanged.connect(self._refresh)
        self.x_connection.currentIndexChanged.connect(self._refresh)
        self.target_spacing.valueChanged.connect(self._refresh)
        self.target_angle.valueChanged.connect(self._refresh)

    def _complete_span(self):
        values=self.spacing_editor.values()
        remaining=self.get_config()["span"]-math.fsum(values)
        if remaining>1e-6:
            self.spacing_editor.set_values(values+[remaining])

    def _sync_presets(self):
        from ..trusses.preset_contracts import PRESETS, compatible_presets
        kind=self.envelope_type.currentData()
        data=self._initial.get("custom_topology")
        if self._initial.get("topology_mode")=="Custom" and data and kind!=data["envelope_type"]:
            blocked=self.envelope_type.blockSignals(True)
            self.envelope_type.setCurrentIndex(self.envelope_type.findData(data["envelope_type"]))
            self.envelope_type.blockSignals(blocked)
            kind=data["envelope_type"]
            self._preset_notice="Custom preservado: use Restaurar padrão antes de trocar o envelope."
        keys=compatible_presets(kind)
        current="Custom" if self._initial.get("topology_mode")=="Custom" else self.preset.currentData()
        if current not in keys:
            current="Warren"
            self._preset_notice="Padrão incompatível com o envelope: selecionado Warren."
        if [self.preset.itemData(i) for i in range(self.preset.count())]!=list(keys):
            blocked=self.preset.blockSignals(True)
            self.preset.clear()
            for key in keys: self.preset.addItem("Custom" if key=="Custom" else PRESETS[key].label,key)
            self.preset.setCurrentIndex(self.preset.findData(current))
            self.preset.blockSignals(blocked)
        self._set_preset_value(current)

    def _set_preset_value(self,value):
        blocked=self.preset.blockSignals(True)
        self.preset.setCurrentIndex(self.preset.findData(value))
        self.preset.blockSignals(blocked)

    def _preset_changed(self):
        if self._updating: return
        selected=self.preset.currentData()
        if self._initial.get("topology_mode")=="Custom":
            if selected!="Custom": self._initial["base_preset"]=selected
            self._set_preset_value("Custom")
        else:
            if selected=="Custom":
                self._initial["base_preset"]=self._initial.get("topology_preset","Warren")
            else:
                self._initial.pop("base_preset",None)
            self._initial["topology_preset"]=selected
        self._refresh()

    def apply_topology_edit(self, action, **args):
        from ..trusses.editing import edit_candidate
        before=self.get_config()
        candidate=self.controller.candidate(before)
        edited=edit_candidate(candidate,action,**args)
        validated=self.controller.candidate(edited)
        self._initial.update(topology_mode="Custom",topology_preset="Custom",
                             base_preset=validated.config["base_preset"],custom_topology=validated.config["custom_topology"])
        self._set_preset_value("Custom")
        blocked=self.driver.blockSignals(True)
        self.driver.setCurrentIndex(self.driver.findData(validated.config["panelization_mode"]))
        self.driver.blockSignals(blocked)
        self._refresh()
        if before.get("panelization_mode")=="ByTargetDiagonalAngle":
            self.message.setText("Topologia Custom: mantida a quantidade efetiva de painéis; ângulo-alvo desativado.")

    def _open_topology_editor(self):
        if not self._refresh(): return
        from .truss_topology_editor import TopologyEditor
        dialog=TopologyEditor(self)
        dialog.exec()
        dialog.deleteLater()
        self._refresh()

    def _restore_topology(self):
        # The named button is the explicit replacement action; selecting a preset
        # while Custom only selects the seed for this operation.
        from ..trusses.editing import restore_preset
        try:
            config=restore_preset(self.get_config())
            candidate=self.controller.candidate(config)
            self._initial.update(topology_mode=candidate.config["topology_mode"],custom_topology=candidate.config.get("custom_topology"))
            self._initial.pop("base_preset",None)
            self._initial["topology_preset"]=candidate.config["topology_preset"]
            self._set_preset_value(candidate.config["topology_preset"])
            self._refresh()
        except (ValueError,RuntimeError) as exc:
            self.message.setText(str(exc))

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
        from ..trusses.assemblies import ASSEMBLY_MODES
        composition = dict(ASSEMBLY_MODES)[spec.get("assembly", "Single")]
        text = f"{designation}\nComposição: {composition}  ..."
        button.setText(text)
        button.setToolTip(text + f"\n{insertion} · {spec['rotation']:g}°\nAbrir perfil, composição e orientação")
        if spec.get("assembly", "Single") == "Single":
            miniature = SectionOrientationPreview(self.form)
            miniature.set_geometry(geometry, spec["insertion"], spec["rotation"])
        else:
            from .assembly_preview import AssemblyPreview
            miniature = AssemblyPreview(self.form)
            try:
                miniature.set_role(spec, self._role_nominal_lengths(role)[0])
            except ValueError as exc:
                miniature.set_error(str(exc))
        miniature.resize(miniature.sizeHint())
        pixmap = QtGui.QPixmap(120, 84)
        pixmap.fill(QtCore.Qt.transparent)
        painter = QtGui.QPainter(pixmap)
        try:
            painter.scale(120.0 / miniature.width(), 84.0 / miniature.height())
            miniature.render(painter, QtCore.QPoint())
        finally:
            painter.end()
            miniature.hide()  # render() must not leave a child overlay until deferred deletion.
            miniature.deleteLater()
        button.setIcon(QtGui.QIcon(pixmap))

    def _edit_role(self, role):
        title = dict(ROLE_LABELS)[role]
        from .assembly_editor import AssemblyEditor
        dialog = AssemblyEditor(self.document, title, self._role_specs[role], self.form,
                                nominal_lengths=self._role_nominal_lengths(role))
        if dialog.exec() == QtWidgets.QDialog.Accepted:
            self._role_specs[role] = dialog.role_spec()
            self._update_role_button(role)
            self._refresh()
        dialog.deleteLater()

    def _role_nominal_lengths(self, role):
        from ..trusses.realization import build_candidate
        config = deepcopy(self._initial if self._updating else self.get_config())
        # Stationing depends only on logical runs. An invalid attachment must
        # not prevent opening its editor to correct it.
        for spec in config["role_specs"].values():
            if spec.get("assembly_spec"):
                spec["assembly_spec"]["spec"]["interconnectors"] = []
        candidate = build_candidate(config)
        lengths = []
        for run in candidate.runs:
            key = run.role
            a = candidate.graph.node(run.start_node_key).position_local
            b = candidate.graph.node(run.end_node_key).position_local
            if key == "END_POST":
                key += "_LEFT" if (a[0]+b[0])/2 < config["span"]/2 else "_RIGHT"
            if key == role:
                lengths.append(math.dist(a, b))
        return tuple(sorted(set(lengths))) or (config["span"],)

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
        self.reference_mode=self._combo((("Dois pontos","TwoPoints"),("Linha Draft","DraftLine"),
                                        ("Retângulo Draft","DraftRectangle"),("Três pontos","ThreePoints")),config.get("reference_mode","TwoPoints"))
        self.keep_reference_link=QtWidgets.QCheckBox("Manter vínculo com a fonte")
        self.keep_reference_link.setChecked(config.get("reference_linked",False))
        self.reference_edge=self._combo((("Selecione o lado da base",""),)+tuple((f"Lado {i} (Edge{i})",f"Edge{i}") for i in range(1,5)),config.get("reference_edge",""))
        self.reference_edge_label=QtWidgets.QLabel("Base do retângulo:")
        self.source_label=QtWidgets.QLabel(config.get("reference_source", ""))
        start_widget, self.start_inputs = self._vector_inputs(config["start"])
        end_widget, self.end_inputs = self._vector_inputs(config["end"])
        normal_widget, self.normal_inputs = self._vector_inputs(config["plane_normal"], normal=True)
        form.addRow("Modo:", self.reference_mode)
        advanced = QtWidgets.QWidget()
        advanced_form = QtWidgets.QFormLayout(advanced)
        advanced_form.addRow("P0 (X, Y, Z), mm:", start_widget)
        advanced_form.addRow("P1 (X, Y, Z), mm:", end_widget)
        advanced_form.addRow("Normal (X, Y, Z):", normal_widget)
        axes = QtWidgets.QLabel("X segue P0 → P1; Y = normal × X.")
        axes.setWordWrap(True)
        advanced_form.addRow(axes)
        advanced.hide()
        header = _DisclosureHeader("Avançado")
        header.button.toggled.connect(advanced.setVisible)
        self.pick_button = QtWidgets.QPushButton("Selecionar dois pontos")
        self.pick_button.setEnabled(self._point_picker is not None)
        self.pick_button.clicked.connect(self._pick_points)
        form.addRow(self.pick_button)
        form.addRow(self.keep_reference_link)
        form.addRow(self.reference_edge_label,self.reference_edge)
        form.addRow(self.source_label)
        self.plane_label = QtWidgets.QLabel()
        self.plane_label.setWordWrap(True)
        form.addRow(self.plane_label)
        form.addRow(header)
        form.addRow(advanced)
        for spin in self.start_inputs + self.end_inputs:
            spin.valueChanged.connect(self._points_changed)
        for spin in self.normal_inputs:
            spin.valueChanged.connect(self._refresh)
        self.reference_mode.currentIndexChanged.connect(self._reference_mode_changed)
        self.keep_reference_link.toggled.connect(self._refresh)
        self.reference_edge.currentIndexChanged.connect(self._reference_edge_changed)

    def _reference_mode_changed(self):
        if self._updating: return
        mode=self.reference_mode.currentData()
        self._initial.update(reference_mode=mode,reference_source="",reference_edge="",reference_defined=mode=="TwoPoints")
        self.keep_reference_link.setChecked(False)
        self._refresh()

    def _apply_reference_values(self, values):
        custom=self._initial.get("custom_topology")
        if custom and values.get("envelope_type",custom["envelope_type"])!=custom["envelope_type"]:
            raise ValueError("Custom preservado: restaure o padrão antes de mudar o envelope da referência.")
        self._initial.update({k:v for k,v in values.items() if k.startswith("reference_")})
        self._initial["reference_defined"]=True
        for key,spins in (("start",self.start_inputs),("end",self.end_inputs),("plane_normal",self.normal_inputs)):
            if key in values: self._write_vector(spins,values[key])
        for key,widget,factor in (("height",self.height,1),("apex_position",self.apex,100)):
            if key in values:
                blocked=widget.blockSignals(True); widget.setValue(values[key]*factor); widget.blockSignals(blocked)
        if "envelope_type" in values:
            blocked=self.envelope_type.blockSignals(True)
            self.envelope_type.setCurrentIndex(self.envelope_type.findData(values["envelope_type"]))
            self.envelope_type.blockSignals(blocked)
        self._points_changed()

    def _reference_edge_changed(self):
        if self._updating or self.reference_mode.currentData()!="DraftRectangle": return
        try:
            self._apply_reference_values(self.controller.reference_geometry(self.get_config()))
        except (ValueError,RuntimeError) as exc:
            self._initial["reference_defined"]=False
            self._show_error(str(exc))

    def _select_draft_reference(self):
        try:
            selected=self.controller.selected_reference()
            self._initial.update(selected)
            self._initial["reference_defined"]=False
            blocked=self.reference_mode.blockSignals(True)
            self.reference_mode.setCurrentIndex(self.reference_mode.findData(selected["reference_mode"]))
            self.reference_mode.blockSignals(blocked)
            blocked=self.reference_edge.blockSignals(True)
            self.reference_edge.setCurrentIndex(self.reference_edge.findData(selected["reference_edge"]))
            self.reference_edge.blockSignals(blocked)
            if not selected["reference_edge"]:
                self._initial["reference_defined"]=False
                self.sections["Referência"][0].setChecked(True)
                self._refresh()
                return
            self._apply_reference_values(self.controller.reference_geometry(self.get_config()))
        except (ValueError,RuntimeError) as exc:
            self._show_error(str(exc))

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
        if hasattr(self,"driver"):
            config.update(panelization_mode=self.driver.currentData(),target_spacing=float(self.target_spacing.value()),
                          target_angle=float(self.target_angle.value()),custom_spacings=self.spacing_editor.values(),
                          x_connection=self.x_connection.currentData())
        if hasattr(self,"reference_mode"):
            config.update(reference_mode=self.reference_mode.currentData(),reference_linked=self.keep_reference_link.isChecked(),
                          reference_edge=self.reference_edge.currentData() if self.reference_mode.currentData()=="DraftRectangle" else "Edge1")
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
        mode=self.reference_mode.currentData() if hasattr(self,"reference_mode") else "TwoPoints"
        if mode in ("DraftLine","DraftRectangle"):
            self._select_draft_reference()
            return
        self._point_generation += 1
        generation = self._point_generation
        self.pick_button.setEnabled(False)
        self.message.setText("Selecione o início e o fim da base na vista 3D.")
        if mode=="ThreePoints":
            from ..trusses.reference_geometry import three_points
            self.message.setText("Selecione início, fim da base e ápice; Esc cancela a captura.")
            def received_three(points):
                if self._closed or generation!=self._point_generation: return
                self.pick_button.setEnabled(True)
                if points is None:
                    self._refresh()
                    return
                try:
                    self._apply_reference_values(three_points(*(point_components(p) for p in points)))
                except ValueError as exc:
                    self._show_error(str(exc))
            try:
                self.controller.pick_points(received_three,count=3)
            except (ValueError,RuntimeError) as exc:
                self.pick_button.setEnabled(True)
                self._show_error(str(exc))
            return
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
            self._initial["reference_defined"]=True
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
        self._preset_notice=""
        if hasattr(self,"driver"): self._sync_presets()
        config = self.get_config()
        if hasattr(self,"driver"):
            from ..trusses.preset_contracts import PRESETS
            mode=config.get("panelization_mode","ByPanelCount")
            custom=config.get("topology_mode","Preset")=="Custom"
            self.topology_state.setText("Topologia: Custom — trocar o padrão só escolhe a semente para Restaurar padrão." if custom else "Topologia: padrão gerado")
            self.topology_state.setWordWrap(True)
            self.panel_count.setEnabled(mode=="ByPanelCount")
            for widget in (self.target_spacing,self.target_spacing_label): widget.setVisible(mode=="ByTargetSpacing")
            for widget in (self.target_angle,self.target_angle_label): widget.setVisible(mode=="ByTargetDiagonalAngle")
            self.spacing_editor.setVisible(mode=="CustomSpacingList")
            total=math.fsum(config["custom_spacings"])
            remaining=config["span"]-total
            self.spacing_balance.setVisible(mode=="CustomSpacingList")
            self.spacing_balance.setText(f"Soma: {total:g} mm · Vão: {config['span']:g} mm · Restante: {remaining:g} mm"+
                                        (" — conflito: soma excede o vão" if remaining < -1e-6 else ""))
            self.complete_span.setVisible(mode=="CustomSpacingList" and remaining>1e-6)
            for widget in (self.x_label,self.x_connection): widget.setVisible(config["topology_preset"]=="X")
            angle_item=self.driver.model().item(self.driver.findData("ByTargetDiagonalAngle"))
            angle_item.setEnabled(not custom and bool(PRESETS[config["topology_preset"]].angle_family))
        if hasattr(self,"reference_mode"):
            mode=config.get("reference_mode","TwoPoints")
            source_mode=mode in ("DraftLine","DraftRectangle")
            self.keep_reference_link.setVisible(source_mode)
            for widget in (self.reference_edge,self.reference_edge_label): widget.setVisible(mode=="DraftRectangle")
            self.source_label.setVisible(source_mode)
            self.source_label.setText(config.get("reference_source", "Nenhuma fonte selecionada"))
            self.pick_button.setText("Usar seleção Draft" if source_mode else "Selecionar três pontos" if mode=="ThreePoints" else "Selecionar dois pontos")
            linked=config.get("reference_linked",False)
            self.span.setEnabled(not linked)
            self.height.setEnabled(not (linked and mode=="DraftRectangle"))
            if mode=="DraftRectangle" and config.get("reference_source") and not config.get("reference_edge"):
                self._valid=False
                self._set_accept_enabled(False)
                self.controller.remove_preview()
                self.message.setStyleSheet("")
                self.message.setText("Retângulo aceito. Escolha Base em Referência: Lado 1, 2, 3 ou 4.")
                return False
        pitched = config["envelope_type"] == "DuoPitch"
        for widget in (self.apex, self.apex_label, self.pitch_note):
            widget.setVisible(pitched)
        self.plane_label.setText(f"Referência definida · Vão: {config['span']:g} mm · Altura: {config['height']:g} mm")
        try:
            model = self.controller.preview(config)
            candidate=getattr(self.controller,"last_candidate",None)
            if candidate is not None:
                effective=candidate.config
                self._initial.update({k:effective[k] for k in ("topology_mode","topology_preset","base_preset","custom_topology","left_panels","right_panels") if k in effective})
                self._set_preset_value(effective["topology_preset"])
                for name,spins in (("start",self.start_inputs),("end",self.end_inputs),("plane_normal",self.normal_inputs)):
                    self._write_vector(spins,effective[name])
                for name,widget,factor in (("span",self.span,1),("height",self.height,1),("apex_position",self.apex,100),("panel_count",self.panel_count,1)):
                    blocked=widget.blockSignals(True); widget.setValue(effective[name]*factor); widget.blockSignals(blocked)
                self._axis_direction=[(b-a)/effective["span"] for a,b in zip(effective["start"],effective["end"])]
                config=self.get_config()
                self.plane_label.setText(f"Referência definida · Vão: {effective['span']:g} mm · Altura: {effective['height']:g} mm")
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
        if "effective" in model:
            result=model["effective"]
            text=f"{result['panel_count']} painéis · espaçamento médio efetivo {result['spacing']:.3f} mm"
            if "angle" in result:
                text+=f" · ângulo médio efetivo {result['angle']:.2f}° ({result['minimum_angle']:.2f}–{result['maximum_angle']:.2f}°)"
            self.closure.setText(text)
        from ..trusses.validation import human_diagnostics
        warnings = human_diagnostics(model.get("warnings", ()))
        if self._preset_notice: warnings.append(self._preset_notice)
        if hasattr(self,"topology_state") and config.get("topology_mode")=="Custom":
            from ..trusses.preset_contracts import PRESETS
            base=config.get("base_preset","Custom")
            self.topology_state.setText("Base para restaurar: "+PRESETS[base].label)
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
