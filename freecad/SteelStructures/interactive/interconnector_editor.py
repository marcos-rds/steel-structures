"""Small interconnector controls added beside the existing composition editor."""
from dataclasses import asdict, replace
from PySide import QtCore, QtGui, QtWidgets
from ..trusses.interconnector_options import (KINDS, is_lacing, compatible_profile, default_connector,
                                    edited_connector, stations_to_quantity)
from .. import profile_catalog
from ..assemblies import SectionTransform


class InterconnectorEditor(QtWidgets.QGroupBox):
    changed = QtCore.Signal()

    def __init__(self, specs=(), parent=None):
        super().__init__("Interconectores", parent)
        self._loading = True
        self._specs = list(specs)
        self._current_index = 0
        self._profile_edited = bool(specs)
        self._value = specs[0] if specs else default_connector("Battens")
        layout = QtWidgets.QVBoxLayout(self)
        self.selector = QtWidgets.QComboBox()
        self.selector.addItems([f"Conjunto {i+1}" for i in range(max(1, len(specs)))])
        self.selector.setVisible(len(specs) > 1)
        layout.addWidget(self.selector)
        form = QtWidgets.QFormLayout()
        layout.addLayout(form)
        self.kind = QtWidgets.QComboBox()
        for key, label in KINDS:
            self.kind.addItem(label, key)
        form.addRow("Tipo:", self.kind)
        self.plane = QtWidgets.QComboBox()
        for key, label in (("FaceA", "Face A"), ("FaceB", "Face B"), ("Both", "Ambas as faces")):
            self.plane.addItem(label, key)
        # Legacy attachment is displayed explicitly, never converted on opening.
        self.plane.addItem("Eixo-a-eixo (legado)", "AxisToAxis")
        self.plane_label = QtWidgets.QLabel("Plano de ligação:")
        form.addRow(self.plane_label, self.plane)
        self.inner_position = QtWidgets.QLabel("Posição: Entre faces internas")
        form.addRow(self.inner_position)
        self.distribution = QtWidgets.QComboBox()
        self.distribution.addItem("Por quantidade", "ByCount")
        self.distribution.addItem("Por espaçamento máximo", "ByTargetSpacing")
        self.distribution_label = QtWidgets.QLabel("Distribuição:")
        form.addRow(self.distribution_label, self.distribution)
        self.quantity = QtWidgets.QSpinBox()
        self.quantity.setRange(1, 9999)
        self.quantity_label = QtWidgets.QLabel()
        form.addRow(self.quantity_label, self.quantity)
        def distance():
            spin = QtWidgets.QDoubleSpinBox()
            spin.setRange(0., 1e8)
            spin.setDecimals(3)
            spin.setSuffix(" mm")
            return spin
        self.spacing, self.start, self.end = distance(), distance(), distance()
        self.spacing.setValue(250.)
        self.spacing_label = QtWidgets.QLabel("Espaçamento máximo desejado:")
        self.spacing_label.setWordWrap(True)
        form.addRow(self.spacing_label, self.spacing)
        self.start_label, self.end_label = QtWidgets.QLabel("Afastamento inicial:"), QtWidgets.QLabel("Afastamento final:")
        form.addRow(self.start_label, self.start)
        form.addRow(self.end_label, self.end)
        self.start.setToolTip("Medido a partir do início do eixo nominal.")
        self.end.setToolTip("Medido a partir do fim do eixo nominal.")
        self.start_side = QtWidgets.QComboBox()
        self.start_side.addItem("Componente A", "A")
        self.start_side.addItem("Componente B", "B")
        self.side_label = QtWidgets.QLabel("Início do treliçamento:")
        form.addRow(self.side_label, self.start_side)
        self.profile_button = QtWidgets.QPushButton()
        self.profile_button.setToolTip("Editar perfil, inserção, orientação e cor do interconector")
        self.profile_button.clicked.connect(self._edit_profile)
        layout.addWidget(self.profile_button)
        self.reflect = QtWidgets.QCheckBox("Inverter seção lateralmente")
        layout.addWidget(self.reflect)
        self.effective = QtWidgets.QLabel()
        self.effective.setWordWrap(True)
        layout.addWidget(self.effective)
        self.kind.currentIndexChanged.connect(self._kind_changed)
        self.selector.currentIndexChanged.connect(self._select_spec)
        for signal in (self.plane.currentIndexChanged, self.distribution.currentIndexChanged,
                       self.quantity.valueChanged, self.spacing.valueChanged, self.start.valueChanged,
                       self.end.valueChanged, self.start_side.currentIndexChanged, self.reflect.toggled):
            signal.connect(self._changed)
        self._load(self._value, specs[0].kind if specs else "None")
        self._loading = False
        self._sync_visibility()

    def _load(self, value, kind):
        self._loading = True
        self._value = value
        self.kind.setCurrentIndex(self.kind.findData(kind))
        self.plane.setCurrentIndex(max(0, self.plane.findData(value.attachment_plane)))
        self.distribution.setCurrentIndex(self.distribution.findData(value.distribution.mode))
        self.quantity.setValue(max(1, stations_to_quantity(kind, value.distribution.station_count or 4)))
        self.spacing.setValue(value.distribution.target_spacing or 250.)
        self.start.setValue(value.start_offset)
        self.end.setValue(value.end_offset)
        self.start_side.setCurrentIndex(self.start_side.findData(value.start_side))
        self.reflect.setChecked(value.section_transform.reflect_x)
        self._profile_label()
        self._loading = False

    def _profile_label(self):
        designation = profile_catalog.selection_for_ref(self._value.profile_ref)[2]
        self.profile_button.setText(designation+"  …")

    def _select_spec(self, index):
        if self._loading:
            return
        # Preserve unedited specs and stable keys; a None entry removes only this set.
        try:
            self._specs[self._current_index] = self.value()
        except ValueError:
            self.selector.blockSignals(True)
            self.selector.setCurrentIndex(self._current_index)
            self.selector.blockSignals(False)
            return
        self._current_index = index
        value = self._specs[index]
        self._load(value or default_connector("Battens", f"WEB{index+1}"), value.kind if value else "None")
        self._changed()

    def _kind_changed(self, *_):
        if self._loading:
            return
        kind = self.kind.currentData()
        if kind != "None":
            profile = profile_catalog.get(profile_catalog.selection_for_ref(self._value.profile_ref)[2]).definition
            if not self._profile_edited or not compatible_profile(profile, kind):
                self._value = replace(self._value, profile_ref=default_connector(kind).profile_ref,
                                      insertion_reference="centroid")
            if self._value.kind == "SpacerPlate" and kind != "SpacerPlate":
                self.plane.setCurrentIndex(self.plane.findData("FaceA"))
        self._profile_label()
        self._changed()

    def _sync_visibility(self):
        kind = self.kind.currentData()
        enabled = kind != "None"
        legacy = self.plane.currentData() == "AxisToAxis" and kind != "SpacerPlate"
        self.start.setToolTip("Medido do início nominal até " +
                             ("a estação do eixo (legado)." if legacy else "o extremo físico da peça."))
        self.end.setToolTip("Medido do fim nominal até " +
                           ("a estação do eixo (legado)." if legacy else "o extremo físico da peça."))
        count = self.distribution.currentData() == "ByCount"
        self.quantity_label.setText("Número de painéis:" if is_lacing(kind) else "Quantidade de peças:")
        self.quantity.setToolTip("Quantidade por face; Ambas as faces duplica as peças físicas."
                                 if self.plane.currentData() == "Both" and kind != "SpacerPlate" else
                                 "Um painel corresponde ao intervalo entre duas estações." if is_lacing(kind) else
                                 "Uma peça por estação longitudinal.")
        for widget in (self.plane_label, self.plane):
            widget.setVisible(enabled and kind != "SpacerPlate")
        self.inner_position.setVisible(kind == "SpacerPlate")
        for widget in (self.quantity_label, self.quantity):
            widget.setVisible(enabled and count)
        for widget in (self.spacing_label, self.spacing):
            widget.setVisible(enabled and not count)
        for widget in (self.side_label, self.start_side):
            widget.setVisible(kind == "SingleLacing")
        for widget in (self.distribution_label, self.distribution, self.start_label, self.start,
                       self.end_label, self.end, self.profile_button, self.reflect, self.effective):
            widget.setVisible(enabled)

    def _changed(self, *_):
        if not self._loading:
            self._sync_visibility()
            self.changed.emit()

    def value(self):
        value = replace(self._value, section_transform=SectionTransform(
            self._value.section_transform.rotation_degrees, self.reflect.isChecked()))
        return edited_connector(value, self.kind.currentData(), self.plane.currentData(),
            self.distribution.currentData(), self.quantity.value(), self.spacing.value(),
            self.start.value(), self.end.value(), self.start_side.currentData())

    def values(self):
        specs = list(self._specs) or [None]
        specs[self._current_index] = self.value()
        return tuple(s for s in specs if s is not None)

    def _edit_profile(self):
        from .truss_task_panel import _RoleProfileDialog
        value = self._value
        spec = dict(profile_ref=asdict(value.profile_ref), insertion=value.insertion_reference,
                    rotation=value.section_transform.rotation_degrees, color=value.color,
                    section_geometry_mode=value.section_geometry_mode.value, assembly="Single", physical_fit="None")
        dialog = _RoleProfileDialog(None, "Perfil do interconector", spec, self)
        dialog.options.set_profile_filter(lambda p: compatible_profile(p, self.kind.currentData()))
        if dialog.exec() == QtWidgets.QDialog.Accepted:
            from ..profiles.models import ProfileRef
            result = dialog.role_spec()
            self._value = replace(value, profile_ref=ProfileRef(**result["profile_ref"]),
                insertion_reference=result["insertion"], color=tuple(result["color"]),
                section_geometry_mode=result["section_geometry_mode"],
                section_transform=SectionTransform(result["rotation"], self.reflect.isChecked()))
            self._profile_edited = True
            self._profile_label()
            self._changed()
        dialog.deleteLater()
