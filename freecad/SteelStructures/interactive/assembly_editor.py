"""Compact composition editor built on the existing role profile dialog."""
from PySide import QtCore, QtGui, QtWidgets
from .truss_task_panel import _RoleProfileDialog, role_spec_from_options
from .assembly_preview import AssemblyPreview
from ..trusses.assemblies import (ASSEMBLY_MODES, compatible_modes,
                                 configure_assembly, role_assembly_spec)
from ..assemblies.transforms import SectionTransform


class AssemblyEditor(_RoleProfileDialog):
    def __init__(self, document, title, spec, parent=None):
        super().__init__(document, title, spec, parent)
        self._building = True
        self._last_mode = spec.get("assembly", "Single")
        self._notice = ""
        self._profile_choices = {}
        self.mode = QtWidgets.QComboBox()
        for key, label in ASSEMBLY_MODES:
            self.mode.addItem(label, key)
        self.mode.setCurrentIndex(self.mode.findData(self._last_mode))
        self.spacing = QtWidgets.QDoubleSpinBox()
        self.spacing.setRange(0., 1e6)
        self.spacing.setDecimals(3)
        self.spacing.setSuffix(" mm")
        self.spacing.setToolTip("Distância entre os eixos de inserção dos componentes; não é folga entre faces.")
        self.assembly_insertion = QtWidgets.QComboBox()
        self.assembly_insertion.addItem("Centro", "Center")
        self.assembly_insertion.addItem("Par simétrico", "SymmetricPair")
        self.angle_arrangement = QtWidgets.QComboBox()
        self.angle_arrangement.addItem("Abas para fora", "outward")
        self.angle_arrangement.addItem("Abas para dentro", "inward")
        self.component_orientations = []
        for _ in range(2):
            combo = QtWidgets.QComboBox()
            for mirrored in (False, True):
                for angle in (0, 90, 180, 270):
                    label = ("Invertida lateralmente" if mirrored else "Original")
                    if angle:
                        label += f" · giro {angle}°"
                    combo.addItem(label, (angle, mirrored))
            self.component_orientations.append(combo)
        group = QtWidgets.QGroupBox("Composição")
        self.composition_form = QtWidgets.QFormLayout(group)
        self.composition_form.addRow("Composição:", self.mode)
        self.spacing_label = QtWidgets.QLabel("Distância entre eixos:")
        self.insertion_label = QtWidgets.QLabel("Inserção do conjunto:")
        self.angle_label = QtWidgets.QLabel("Disposição das cantoneiras:")
        self.composition_form.addRow(self.spacing_label, self.spacing)
        self.composition_form.addRow(self.insertion_label, self.assembly_insertion)
        self.composition_form.addRow(self.angle_label, self.angle_arrangement)
        self.component_labels = []
        for key, combo in zip(("A", "B"), self.component_orientations):
            label = QtWidgets.QLabel("Disposição "+key+":")
            self.component_labels.append(label)
            self.composition_form.addRow(label, combo)
        self.layout().insertWidget(0, group)
        self.preview = AssemblyPreview()
        self.preview.setMaximumHeight(250)
        self.options.orientation_panel._preview_layout.insertWidget(0, self.preview, 1)
        self.message = QtWidgets.QLabel()
        self.message.setWordWrap(True)
        self.layout().insertWidget(self.layout().count()-1, self.message)
        self.buttons = self.findChild(QtWidgets.QDialogButtonBox)
        current = role_assembly_spec(spec)
        self.spacing.setValue(current.component_spacing if current.component_spacing is not None else 100.)
        self.assembly_insertion.setCurrentIndex(self.assembly_insertion.findData(
            current.assembly_insertion.value if self._last_mode != "Single" else "SymmetricPair"))
        self._set_transforms(tuple(c.section_transform for c in current.components))
        if self._last_mode == "DoubleAngle":
            a = next(c for c in current.components if c.component_key == "A")
            self.angle_arrangement.setCurrentIndex(0 if a.section_transform.reflect_x else 1)
        self._refresh_timer = QtCore.QTimer(self)
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.setInterval(0)
        self._refresh_timer.timeout.connect(self._refresh_composition)
        self.mode.currentIndexChanged.connect(self._mode_changed)
        for signal in (self.spacing.valueChanged, self.assembly_insertion.currentIndexChanged,
                       self.angle_arrangement.currentIndexChanged, self.options.profile.currentIndexChanged,
                       self.options.category.currentIndexChanged, self.options.series.currentIndexChanged,
                       self.options.insertion.currentTextChanged, self.options.rotation.valueChanged,
                       self.options.colorChanged, self.options.sectionGeometryModeChanged):
            signal.connect(self._queue_refresh)
        for combo in self.component_orientations:
            combo.currentIndexChanged.connect(self._queue_refresh)
        self._filter_profiles()
        self._building = False
        self._refresh_composition()
        self.adjustSize()
        self.resize(510, self.sizeHint().height())

    def _set_transforms(self, transforms):
        for combo, transform in zip(self.component_orientations, transforms):
            data = (transform.rotation_degrees, transform.reflect_x)
            # Qt converts tuple userData to QVariantList on some PySide versions.
            index = next((i for i in range(combo.count()) if tuple(combo.itemData(i)) == data), -1)
            if index < 0:
                combo.addItem(f"Giro {transform.rotation_degrees:g}°"+(
                    " · invertida lateralmente" if transform.reflect_x else ""), data)
                index = combo.count()-1
            combo.setCurrentIndex(index)

    def _queue_refresh(self, *_):
        if not self._building:
            self._refresh_timer.start()

    def _filter_profiles(self):
        mode = self.mode.currentData()
        self.options.set_profile_filter(
            lambda profile: mode in compatible_modes(profile), self._profile_choices.get(mode))

    def _mode_changed(self, *_):
        self._profile_choices[self._last_mode] = self.options.profile_designation
        self._filter_profiles()
        mode = self.mode.currentData()
        if mode != self._last_mode:
            if mode == "SpacedPair":
                self._set_transforms((SectionTransform(), SectionTransform()))
            elif mode == "DoubleAngle":
                self.angle_arrangement.setCurrentIndex(0)
        if mode != "Single" and self._last_mode == "Single":
            self.options.rotation.setValue(0.)
            self._notice = "Orientação inicial do conjunto: 0°. Ajuste a rotação se necessário."
            self.assembly_insertion.setCurrentIndex(self.assembly_insertion.findData("SymmetricPair"))
        self._last_mode = mode
        self._queue_refresh()

    def role_spec(self):
        role = role_spec_from_options(self._previous, self.options)
        mode = self.mode.currentData()
        transforms = None
        if mode == "SpacedPair":
            transforms = tuple(SectionTransform(*combo.currentData()) for combo in self.component_orientations)
        elif mode == "DoubleAngle":
            transforms = (SectionTransform(reflect_x=True), SectionTransform())
            if self.angle_arrangement.currentData() == "inward":
                transforms = transforms[::-1]
        return configure_assembly(role, mode, self.spacing.value(),
                                  self.assembly_insertion.currentData(), transforms)

    def _refresh_composition(self):
        mode = self.mode.currentData()
        multiple = mode != "Single"
        for widget in (self.spacing_label, self.spacing, self.insertion_label, self.assembly_insertion):
            widget.setVisible(multiple)
        for widget in (self.angle_label, self.angle_arrangement):
            widget.setVisible(mode == "DoubleAngle")
        for widget in self.component_labels+self.component_orientations:
            widget.setVisible(mode == "SpacedPair")
        self.preview.setVisible(multiple)
        self.options.orientation_preview.setVisible(not multiple)
        # Do not reserve the hidden single-profile preview's vertical space.
        layout = self.options.orientation_panel._preview_layout
        active = self.preview if multiple else self.options.orientation_preview
        hidden = self.options.orientation_preview if multiple else self.preview
        layout.removeWidget(hidden)
        if layout.indexOf(active) < 0:
            layout.insertWidget(0, active, 1)
        self.options.orientation_panel.preview = active
        self.options.orientation_panel.setTitle("Orientação do conjunto" if multiple else "Orientação da seção")
        self.options.orientation_panel._labels[0].setText("Rotação do conjunto:" if multiple else "Rotação da seção:")
        self.options.rotation.setToolTip("Gira o conjunto, incluindo os eixos dos componentes." if multiple else "Rotação da seção.")
        try:
            role = self.role_spec()
            self.preview.set_role(role)
            self.message.setText(self._notice)
            self.message.setStyleSheet("")
            self.buttons.button(QtWidgets.QDialogButtonBox.Ok).setEnabled(True)
            self._valid_composition = True
        except (ValueError, KeyError, TypeError) as exc:
            self.message.setText(str(exc))
            self.message.setStyleSheet("color: #c44;")
            self.preview.set_error("Composição incompatível. Selecione um perfil compatível ou Simples.")
            self.buttons.button(QtWidgets.QDialogButtonBox.Ok).setEnabled(False)
            self._valid_composition = False

    def accept(self):
        self._refresh_composition()
        if self._valid_composition:
            super().accept()
