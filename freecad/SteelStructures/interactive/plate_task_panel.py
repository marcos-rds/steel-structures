# SPDX-License-Identifier: LGPL-2.1-or-later
"""Compact task panel for the generic flat StructuralPlate creation command."""

from __future__ import annotations

from PySide import QtCore, QtWidgets


_MODE_LABELS = {
    "DraftRectangle": "Retângulo Draft selecionado",
    "DraftWire": "Wire/Polyline Draft selecionada",
    "InteractivePolygon": "Polígono por pontos",
    "InteractiveRectangle": "Retângulo por pontos",
}


class PlateTaskPanel:
    def __init__(self, controller, on_close):
        self.controller = controller
        self.on_close = on_close
        self._closed = False
        self._closing = False
        self.form = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(self.form)
        layout.addWidget(QtWidgets.QLabel("Criar Chapa Estrutural"))

        if controller.source is None:
            self.mode = QtWidgets.QComboBox()
            self.mode.addItem("Polígono", "InteractivePolygon")
            self.mode.addItem("Retângulo", "InteractiveRectangle")
            layout.addWidget(QtWidgets.QLabel("Modo"))
            layout.addWidget(self.mode)
            self.mode.currentIndexChanged.connect(self._mode_changed)
            self.plane_mode = QtWidgets.QComboBox()
            self.plane_mode.addItem("Automático", "Auto")
            self.plane_mode.addItem("Plano de trabalho", "WorkPlane")
            layout.addWidget(QtWidgets.QLabel("Plano"))
            layout.addWidget(self.plane_mode)
            self.plane_mode.currentIndexChanged.connect(self._plane_mode_changed)
        else:
            self.mode = None
            self.plane_mode = None
            layout.addWidget(QtWidgets.QLabel(_MODE_LABELS[controller.mode]))
            layout.addWidget(QtWidgets.QLabel("Origem: " + controller.source.Label))

        fields = QtWidgets.QFormLayout()
        self.thickness = QtWidgets.QDoubleSpinBox()
        self.thickness.setRange(0.001, 1000000.0)
        self.thickness.setDecimals(3)
        self.thickness.setValue(10.0)
        self.thickness.setSuffix(" mm")
        self.offset = QtWidgets.QDoubleSpinBox()
        self.offset.setRange(-1000000.0, 1000000.0)
        self.offset.setDecimals(3)
        self.offset.setValue(0.0)
        self.offset.setSuffix(" mm")
        fields.addRow("Espessura", self.thickness)
        fields.addRow("Offset", self.offset)
        layout.addLayout(fields)

        self.link = QtWidgets.QCheckBox("Manter vínculo com a geometria de origem")
        self.link.setVisible(controller.source is not None)
        layout.addWidget(self.link)
        self.close_button = QtWidgets.QPushButton("Fechar contorno")
        self.close_button.setVisible(controller.source is None)
        self.close_button.clicked.connect(self._close_outline)
        layout.addWidget(self.close_button)
        self.status = QtWidgets.QLabel()
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        layout.addStretch(1)

        self.thickness.valueChanged.connect(self._parameters_changed)
        self.offset.valueChanged.connect(self._parameters_changed)
        self.controller.on_change = self._refresh
        self.controller.on_error = self._show_error
        self.controller.on_cancel = self._cancel_from_view
        self._refresh()
        # Owned timers can be stopped before FreeCAD destroys the task dialog.
        self._start_timer = QtCore.QTimer(self.form)
        self._start_timer.setSingleShot(True)
        self._start_timer.timeout.connect(self._start_capture)
        self._escape_timer = QtCore.QTimer(self.form)
        self._escape_timer.setSingleShot(True)
        self._escape_timer.timeout.connect(self.reject)
        # FreeCAD establishes its task dialog before native view callbacks start.
        self._start_timer.start(0)

    def getStandardButtons(self):
        button = getattr(QtWidgets.QDialogButtonBox, "StandardButton",
                         QtWidgets.QDialogButtonBox)
        flags = button.Ok | button.Cancel
        return int(getattr(flags, "value", flags))

    def _start_capture(self):
        if self._closed or self._closing:
            return
        self.controller.start_capture(
            lambda: self.thickness.value(), lambda: self.offset.value())
        self._parameters_changed()

    def _mode_changed(self, index):
        if self._closed or self._closing:
            return
        try:
            self.controller.set_mode(self.mode.itemData(index))
            self.controller.start_capture(
                lambda: self.thickness.value(), lambda: self.offset.value())
        except (ValueError, RuntimeError) as exc:
            self._show_error(exc)

    def _plane_mode_changed(self, index):
        if self._closed or self._closing:
            return
        try:
            self.controller.set_plane_mode(self.plane_mode.itemData(index))
        except (ValueError, RuntimeError) as exc:
            self._show_error(exc)

    def _show_error(self, message):
        if self._closed or self._closing:
            return
        self.status.setStyleSheet("color: #b03030;")
        self.status.setText(str(message))

    def _refresh(self):
        if self._closed or self._closing:
            return
        controller = self.controller
        if controller.contour is not None:
            self.status.setStyleSheet("")
            self.status.setText("Contorno fechado: %d vértices. Confirme para criar a chapa."
                                % len(controller.contour.vertices))
        elif controller.mode == "InteractivePolygon":
            self.status.setStyleSheet("")
            if controller.plane_state != "PLANE_DEFINED":
                self.status.setText(
                    "%d pontos 3D. Defina a primeira direção e um ponto fora dela para estabelecer o plano."
                    % controller.point_count)
            else:
                self.status.setText(
                    "%d vértices. Clique perto do primeiro ponto ou use Fechar contorno."
                    % controller.point_count)
        else:
            self.status.setStyleSheet("")
            if controller.plane_state == "PLANE_DEFINED":
                self.status.setText("Selecione dois cantos no plano da chapa.")
            else:
                self.status.setText(
                    "%d/3 pontos: primeiro canto, direção/comprimento e largura/plano."
                    % controller.point_count)
        self.close_button.setEnabled(controller.source is None
                                     and controller.mode == "InteractivePolygon"
                                     and controller.contour is None
                                     and controller.plane_state == "PLANE_DEFINED"
                                     and controller.point_count >= 3)
        if self.plane_mode is not None:
            self.plane_mode.setEnabled(not controller.point_count
                                       and controller.contour is None)

    def _parameters_changed(self, *_args):
        if self._closed or self._closing:
            return
        try:
            self.controller.update_preview(self.thickness.value(), self.offset.value())
        except (ValueError, RuntimeError) as exc:
            self._show_error(exc)

    def _close_outline(self):
        if self._closed or self._closing:
            return
        try:
            self.controller.close_outline()
            self._parameters_changed()
        except (ValueError, RuntimeError) as exc:
            self._show_error(exc)

    def accept(self):
        if self._closed or self._closing:
            return False
        try:
            self.controller.create(self.thickness.value(), self.offset.value(),
                                   self.link.isChecked())
        except (ValueError, RuntimeError, ReferenceError) as exc:
            self._show_error(exc)
            return False
        self._finish(True)
        return True

    def reject(self):
        self._finish(False)
        return True

    def _cancel_from_view(self):
        """Leave the Coin callback before removing its view or closing Qt UI."""
        if self._closed or self._closing:
            return
        self._closing = True
        self._escape_timer.start(0)

    def _finish(self, accepted):
        if self._closed:
            return
        self._closed = True
        self._closing = True
        self._start_timer.stop()
        self._escape_timer.stop()
        self._start_timer.timeout.disconnect(self._start_capture)
        self._escape_timer.timeout.disconnect(self.reject)
        if self.mode is not None:
            self.mode.currentIndexChanged.disconnect(self._mode_changed)
        if self.plane_mode is not None:
            self.plane_mode.currentIndexChanged.disconnect(self._plane_mode_changed)
        self.thickness.valueChanged.disconnect(self._parameters_changed)
        self.offset.valueChanged.disconnect(self._parameters_changed)
        self.close_button.clicked.disconnect(self._close_outline)
        self.controller.on_change = None
        self.controller.on_error = None
        self.controller.on_cancel = None
        on_close, self.on_close = self.on_close, None
        try:
            self.controller.cancel()
        finally:
            if on_close is not None:
                on_close(self, accepted)
