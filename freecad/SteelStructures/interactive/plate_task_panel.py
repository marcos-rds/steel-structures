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
    def __init__(self, controller, on_close, advanced=False, session=None):
        self.controller = controller
        self.on_close = on_close
        self._closed = False
        self._closing = False
        self._advanced = advanced
        self._shortcuts = None
        self.session = session
        self.input_form = QtWidgets.QWidget()
        self.properties_form = QtWidgets.QWidget()
        self.footer_form = QtWidgets.QWidget()
        # One TaskPanel, using the same native multi-form TaskBox contract as
        # DraftTaskPanel. Each form has one owner; no additional acquisition.
        self.form = [self.input_form, self.properties_form, self.footer_form]
        from PySide import QtGui
        from ..paths import PLATE_ICON
        self.input_form.setWindowTitle("Criar Chapa Estrutural")
        self.input_form.setWindowIcon(QtGui.QIcon(PLATE_ICON))
        self.properties_form.setWindowTitle("Propriedades da chapa")
        self.properties_form.setWindowIcon(QtGui.QIcon(PLATE_ICON))
        self.footer_form.setWindowTitle("")
        layout = QtWidgets.QVBoxLayout(self.input_form)
        layout.setSpacing(6)

        if controller.source is None:
            self.mode = QtWidgets.QComboBox()
            self.mode.addItem("Polígono livre" if advanced and session is None else "Polígono", "InteractivePolygon")
            oriented = advanced and (session is None or session._advanced)
            self.mode.addItem("Retângulo orientado — 3 pontos" if oriented else "Retângulo", "InteractiveRectangle")
            self.mode.setCurrentIndex(1 if controller.mode == "InteractiveRectangle" else 0)
            layout.addWidget(QtWidgets.QLabel("Forma" if session is not None else "Modo"))
            layout.addWidget(self.mode)
            self.mode.currentIndexChanged.connect(self._mode_changed)
            self.plane_mode = QtWidgets.QComboBox()
            if session is not None:
                session.configure_plane_combo(self.plane_mode)
            else:
                self.plane_mode.addItem("Plano livre por pontos" if advanced else "Automático", "Auto")
                if not advanced:
                    self.plane_mode.addItem("Plano de trabalho", "WorkPlane")
            layout.addWidget(QtWidgets.QLabel("Plano de criação" if session is not None else "Plano"))
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
        self.reverse = QtWidgets.QCheckBox("Inverter sentido da extrusão")
        fields.addRow(self.reverse)

        self.coordinate_input = None
        if controller.source is None:
            from .coordinate_input_widget import CoordinateInputWidget

            self.coordinate_input = CoordinateInputWidget(
                lambda: controller.candidate, self.input_form)
            self.coordinate_input.add_button.setIcon(QtGui.QIcon(":/icons/Draft_AddPoint.svg"))
            self.coordinate_input.candidateChanged.connect(self._candidate_changed)
            self.coordinate_input.confirmRequested.connect(self._confirm_point)
            self.coordinate_input.cancelRequested.connect(self._cancel_from_view)
            self.coordinate_input.errorOccurred.connect(self._show_error)
            controller.numeric_editing = lambda: self.coordinate_input.editing
            layout.addWidget(QtWidgets.QLabel("Entrada de pontos"))
            layout.addWidget(self.coordinate_input)
            self.coordinate_input.candidate_status.hide()

        self.link = QtWidgets.QCheckBox("Manter vínculo com a geometria de origem")
        self.link.setVisible(controller.source is not None)
        self.undo_button = QtWidgets.QPushButton("Desfazer ponto")
        self.undo_button.setIcon(QtGui.QIcon(":/icons/Draft_Rotate.svg"))
        self.undo_button.setToolTip("Remover o último ponto confirmado.")
        self.undo_button.clicked.connect(self._undo_point)
        self.clear_button = QtWidgets.QPushButton("Limpar pontos")
        self.clear_button.setIcon(QtGui.QIcon(":/icons/Draft_Wipe.svg"))
        self.clear_button.setToolTip("Remover todos os pontos e começar o contorno novamente.")
        self.clear_button.clicked.connect(self._clear_points)
        self.close_button = QtWidgets.QPushButton("Fechar contorno")
        self.close_button.setIcon(QtGui.QIcon(":/icons/Draft_Lock.svg"))
        self.close_button.setToolTip("Unir o último vértice ao primeiro e fechar o contorno.")
        self.close_button.setVisible(controller.source is None)
        self.close_button.clicked.connect(self._close_outline)
        actions = QtWidgets.QGridLayout()
        self.point_actions = actions
        if self.coordinate_input is not None:
            add = self.coordinate_input.add_button
            self.coordinate_input.layout().removeWidget(add)
            add.setToolTip("Confirmar o ponto candidato ou as coordenadas completas.")
            actions.addWidget(add, 0, 0)
        actions.addWidget(self.undo_button, 0, 1)
        actions.addWidget(self.close_button, 1, 0)
        actions.addWidget(self.clear_button, 1, 1)
        layout.addLayout(actions)
        self.status = QtWidgets.QLabel()
        self.status.setWordWrap(True)
        properties = QtWidgets.QVBoxLayout(self.properties_form)
        properties.setSpacing(6)
        properties.addLayout(fields)
        properties.addWidget(self.link)
        footer = QtWidgets.QVBoxLayout(self.footer_form)
        footer.setContentsMargins(0, 0, 0, 0)
        footer.addWidget(self.status)
        font = self.status.font()
        font.setPointSizeF(max(8.0, font.pointSizeF() - 1.0))
        self.status.setFont(font)

        self.thickness.valueChanged.connect(self._parameters_changed)
        self.offset.valueChanged.connect(self._parameters_changed)
        self.reverse.toggled.connect(self._parameters_changed)
        self.controller.on_change = self._refresh
        self.controller.on_error = self._show_error
        self.controller.on_cancel = self._cancel_from_view
        self.controller.on_candidate = self._candidate_updated
        self._refresh()
        # Owned timers can be stopped before FreeCAD destroys the task dialog.
        self._start_timer = QtCore.QTimer(self.input_form)
        self._start_timer.setSingleShot(True)
        self._start_timer.timeout.connect(self._start_capture)
        self._escape_timer = QtCore.QTimer(self.input_form)
        self._escape_timer.setSingleShot(True)
        self._escape_timer.timeout.connect(self.reject)
        if self.coordinate_input is not None:
            from .plate_panel_shortcuts import PanelShortcuts, draft_shortcut_keys, point_shortcut_key
            keys = draft_shortcut_keys()
            self._shortcuts = PanelShortcuts(
                self.input_form, lambda: not self._closed and not self._closing)
            for control, action, label in (
                    (self.coordinate_input.relative, "Relative", "Relativo"),
                    (self.coordinate_input.global_coordinates, "Global", "Global"),
                    (self.undo_button, "Undo", "Desfazer ponto"),
                    (self.close_button, "Close", "Fechar contorno"),
                    (self.clear_button, "Wipe", "Limpar pontos")):
                self._shortcuts.bind(control, keys[action], label=label)
            self._shortcuts.bind(self.coordinate_input.add_button, point_shortcut_key(keys), label="Adicionar ponto")
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
        # A footer is not a third titled section. Hide only its presentation
        # header, after FreeCAD has wrapped the forms in native TaskBoxes.
        box = self.footer_form.parentWidget()
        while box is not None and not box.inherits("Gui::TaskView::TaskBox"):
            box = box.parentWidget()
        if box is not None:
            for child in box.findChildren(QtWidgets.QWidget):
                if child.inherits("QSint::TaskHeader"):
                    child.hide()
        self.controller.start_capture(
            lambda: self.thickness.value(), lambda: self.offset.value())
        self._parameters_changed()

    def _mode_changed(self, index):
        if self._closed or self._closing:
            return
        if self.session is not None:
            mode = self.mode.itemData(index)
            self.session._change_panel(shape="Rectangle" if mode == "InteractiveRectangle" else "Polygon")
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
        if self.session is not None:
            self.session._change_panel(plane=self.plane_mode.itemData(index))
            return
        try:
            self.controller.set_plane_mode(self.plane_mode.itemData(index))
        except (ValueError, RuntimeError) as exc:
            self._show_error(exc)

    def _show_error(self, message):
        if self._closed or self._closing:
            return
        if str(message) == "Não foi possível obter um ponto 3D real neste local.":
            self.status.setStyleSheet("")
            self.status.setText("Use geometria, snap ou XYZ.")
            return
        self.status.setStyleSheet("color: #b03030;")
        self.status.setText(str(message))

    def _refresh(self):
        if self._closed or self._closing:
            return
        controller = self.controller
        if controller.contour is not None:
            self.status.setStyleSheet("")
            self.status.setText("Contorno fechado. Confirme a chapa.")
        elif controller.mode == "InteractivePolygon":
            self.status.setStyleSheet("")
            if controller.point_count == 0 and controller.plane_state != "PLANE_DEFINED":
                self.status.setText(
                    "Selecione o primeiro ponto.")
            elif controller.point_count == 1 and controller.plane_state != "PLANE_DEFINED":
                self.status.setText("Defina a direção.")
            elif controller.plane_state != "PLANE_DEFINED":
                self.status.setText("Defina o plano.")
            else:
                self.status.setText(
                    "Adicione vértices ou feche o contorno.")
        else:
            self.status.setStyleSheet("")
            if controller.plane_state == "PLANE_DEFINED":
                self.status.setText("Selecione o canto oposto.")
            else:
                self.status.setText(
                    ("Selecione o primeiro ponto.", "Defina a direção.", "Defina o plano.")
                    [min(controller.point_count, 2)])
        self.close_button.setEnabled(controller.source is None
                                     and controller.mode == "InteractivePolygon"
                                     and controller.contour is None
                                     and controller.plane_state == "PLANE_DEFINED"
                                     and controller.point_count >= 3)
        if self._advanced:
            self.close_button.setVisible(controller.mode == "InteractivePolygon")
        polygon = controller.source is None and controller.mode == "InteractivePolygon"
        self.undo_button.setVisible(polygon)
        self.undo_button.setEnabled(polygon and controller.point_count > 0)
        self.clear_button.setVisible(polygon or (controller.source is None and controller.point_count > 0))
        self.clear_button.setEnabled(controller.source is None and controller.point_count > 0)
        if self.plane_mode is not None and self.session is None:
            self.plane_mode.setEnabled(not controller.point_count
                                       and controller.contour is None)
        if self._advanced and self.session is None:
            self.mode.setEnabled(not controller.point_count and controller.contour is None)
            self.mode.setToolTip("Use Reiniciar traçado antes de alterar a forma.")
        if self.coordinate_input is not None:
            self.coordinate_input.set_context(
                controller.input_plane, controller.last_point, controller.mode,
                available=controller.contour is None)
            self._present_candidate(controller.candidate)

    def _present_candidate(self, candidate):
        if not self._closed and not self._closing and self.coordinate_input is not None:
            self.coordinate_input.present_candidate(candidate)

    def _candidate_updated(self, candidate):
        self._present_candidate(candidate)
        if (candidate is not None and not self._closed and not self._closing
                and self.status.text() == "Use geometria, snap ou XYZ."):
            self._refresh()
        if (not self._closed and not self._closing and candidate is None
                and self.coordinate_input is not None and not self.coordinate_input.editing
                and self.controller.contour is None):
            self.status.setStyleSheet("color: palette(mid);")
            self.status.setText("Use geometria, snap ou XYZ.")

    def _undo_point(self):
        if self._closed or self._closing:
            return
        self.controller.undo_point()
        self.controller.start_capture(lambda: self.thickness.value(), lambda: self.offset.value())
        self._parameters_changed()

    def _clear_points(self):
        if self._closed or self._closing:
            return
        self.controller.clear_points()
        self.controller.start_capture(lambda: self.thickness.value(), lambda: self.offset.value())
        self._parameters_changed()

    def _candidate_changed(self, candidate):
        if self._closed or self._closing or self.controller.contour is not None:
            return
        try:
            self.controller.set_candidate(candidate)
            self.controller.update_preview(self.thickness.value(), self.offset.value())
        except (ValueError, RuntimeError) as exc:
            self.controller.set_candidate(None)
            self.controller.update_preview(self.thickness.value(), self.offset.value())
            self._show_error(exc)

    def _confirm_point(self, candidate):
        if self._closed or self._closing or self.controller.contour is not None:
            return
        try:
            self.controller.set_candidate(candidate)
            self.controller.add_point(self.controller.candidate.world, close_on_first=False)
            self.coordinate_input.clear()
            self.controller.update_preview(self.thickness.value(), self.offset.value())
        except (ValueError, RuntimeError) as exc:
            self._show_error(exc)

    def _parameters_changed(self, *_args):
        if self._closed or self._closing:
            return
        try:
            self.controller.reverse_extrusion = self.reverse.isChecked()
            thickness, offset = self.thickness.value(), self.offset.value()
            low, high = (offset - thickness, offset) if self.reverse.isChecked() else (offset, offset + thickness)
            self.reverse.setToolTip("Face de referência em Offset. Extrusão em Z local: %g até %g mm." % (low, high))
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
                                   self.link.isChecked(), reverse_extrusion=self.reverse.isChecked())
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
        self.controller.closed = True
        self._closing = True
        self._escape_timer.start(0)

    def _finish(self, accepted):
        if self._closed:
            return
        self._closed = True
        self._closing = True
        on_close, self.on_close = self.on_close, None
        self.controller.numeric_editing = None
        self.controller.on_change = None
        self.controller.on_error = None
        self.controller.on_cancel = None
        self.controller.on_candidate = None
        try:
            self._disconnect_widgets()
        except (RuntimeError, TypeError):
            # FreeCAD can destroy children before releasing the task form.
            # Acquisition and ownership still have to be released below.
            pass
        finally:
            try:
                self.controller.cancel()
            finally:
                if on_close is not None:
                    on_close(self, accepted)

    def _disconnect_widgets(self):
        if self._shortcuts is not None:
            self._shortcuts.dispose()
            self._shortcuts = None
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
        self.reverse.toggled.disconnect(self._parameters_changed)
        self.undo_button.clicked.disconnect(self._undo_point)
        self.clear_button.clicked.disconnect(self._clear_points)
        self.close_button.clicked.disconnect(self._close_outline)
        if self.coordinate_input is not None:
            self.coordinate_input.dispose()
            self.coordinate_input.candidateChanged.disconnect(self._candidate_changed)
            self.coordinate_input.confirmRequested.disconnect(self._confirm_point)
            self.coordinate_input.cancelRequested.disconnect(self._cancel_from_view)
            self.coordinate_input.errorOccurred.disconnect(self._show_error)
