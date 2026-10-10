# SPDX-License-Identifier: LGPL-2.1-or-later
"""Text-only authority for complete numeric point input in a plate task panel."""
import math

import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtCore, QtWidgets

from .point_input import CoordinateMode, CoordinateReference, PointInputSpec


def display_length(value):
    """Use FreeCAD's display schema, precision and locale, never alter geometry."""
    return App.Units.Quantity(value, App.Units.Length).UserString


def length_value(text):
    """Normalize FreeCAD length units; empty or incomplete text is never zero."""
    text = text.strip()
    if not text:
        raise ValueError("Preencha todas as coordenadas.")
    try:
        quantity = App.Units.Quantity(text)
        if quantity.Unit not in (App.Units.Quantity("1 mm").Unit,
                                 App.Units.Quantity("1").Unit):
            raise ValueError("As coordenadas devem ser comprimentos.")
        value = float(quantity.Value)
    except (ValueError, TypeError, RuntimeError, OverflowError) as exc:
        raise ValueError("Informe um comprimento válido em cada campo.") from exc
    if not math.isfinite(value):
        raise ValueError("As coordenadas devem ter valores finitos.")
    return value


class CoordinateInputWidget(QtWidgets.QWidget):
    candidateChanged = QtCore.Signal(object)
    confirmRequested = QtCore.Signal(object)
    cancelRequested = QtCore.Signal()
    errorOccurred = QtCore.Signal(str)

    def __init__(self, get_candidate, parent=None):
        super().__init__(parent)
        self._get_candidate = get_candidate
        self._closed = False
        self._writing = False
        self._editing = False
        self._presentation = False
        self._plane = self._last = None
        self._context = None
        self._spec = PointInputSpec()
        layout = QtWidgets.QFormLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        self.relative = QtWidgets.QCheckBox("Relativo", self)
        self.relative.setToolTip("Usar o último ponto confirmado como origem das coordenadas.")
        self.global_coordinates = QtWidgets.QCheckBox("Global", self)
        self.global_coordinates.setChecked(True)
        self.global_coordinates.setToolTip(
            "Usar os eixos globais XYZ; desmarque para usar os eixos UV do plano definido.")
        axes = QtWidgets.QHBoxLayout()
        axes.addWidget(self.relative)
        axes.addWidget(self.global_coordinates)
        layout.addRow(axes)
        self.fields, self.labels = [], []
        # Sample the native unit editor's current theme and metrics without
        # adopting its focus-out parser (which rewrites incomplete edits).
        native = Gui.UiLoader().createWidget("Gui::InputField")
        native.setParent(self)
        native.hide()
        for name in ("X", "Y", "Z"):
            # An empty coordinate is an ordinary acquisition state, not a
            # quantity error. InputField decorates it as invalid and rewrites
            # unfinished text on focus changes. Parse complete text ourselves.
            field = QtWidgets.QLineEdit(self)
            field.setFont(native.font())
            field.setPalette(native.palette())
            field.setAlignment(native.alignment())
            field.setTextMargins(native.textMargins())
            field.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred)
            field.setMinimumHeight(native.sizeHint().height())
            field.setPlaceholderText("Coordenada em mm")
            field.setToolTip("Comprimento global; aceita unidades, por exemplo 2 cm.")
            field.setObjectName("PlatePoint" + name)
            field.setMinimumWidth(110)
            field.textChanged.connect(self._text_changed)
            field.installEventFilter(self)
            self.fields.append(field)
            label = QtWidgets.QLabel(name, self)
            label.setMinimumWidth(75)
            self.labels.append(label)
            layout.addRow(label, field)
        native.deleteLater()
        self.candidate_status = QtWidgets.QLabel(self)
        self.candidate_status.setWordWrap(True)
        layout.addRow(self.candidate_status)
        self.add_button = QtWidgets.QPushButton("Adicionar ponto", self)
        self.add_button.setAutoDefault(False)
        self.add_button.setDefault(False)
        self.add_button.clicked.connect(self.confirm)
        self.add_button.installEventFilter(self)
        layout.addRow(self.add_button)
        self.global_coordinates.toggled.connect(self._system_changed)
        self.relative.toggled.connect(self._system_changed)
        self.set_context(None, None)
        self._labels()

    @property
    def editing(self):
        return not self._closed and self._editing

    def set_context(self, plane, last_point, session=None, available=True):
        if self._closed:
            return
        context = (plane, last_point, session)
        self._plane, self._last = plane, last_point
        self.setEnabled(available)
        # The task panel places this action outside the coordinate group.
        # A closed contour must disable it even while manual text owns focus.
        if not available:
            self.add_button.setEnabled(False)
        self.global_coordinates.setEnabled(plane is not None)
        self.relative.setEnabled(last_point is not None)
        if context != self._context:
            self._context = context
            self.clear()
        if (plane is None and self._spec.reference == CoordinateReference.PLANE
                or last_point is None and self._spec.mode == CoordinateMode.RELATIVE):
            self._writing = True
            try:
                if plane is None:
                    self.global_coordinates.setChecked(True)
                if last_point is None:
                    self.relative.setChecked(False)
                self._spec = self._selected_spec()
                self._labels()
            finally:
                self._writing = False
        if not self._editing and not self._presentation:
            self._show_waiting_status()

    def _selected_spec(self):
        return PointInputSpec(
            CoordinateReference.GLOBAL if self.global_coordinates.isChecked()
            else CoordinateReference.PLANE,
            CoordinateMode.RELATIVE if self.relative.isChecked()
            else CoordinateMode.ABSOLUTE)

    def _labels(self):
        local = self._spec.reference == CoordinateReference.PLANE
        relative = self._spec.mode == CoordinateMode.RELATIVE
        prefix = "Local " if local else "Global " if relative else ""
        for index, (field, label) in enumerate(zip(self.fields, self.labels)):
            label.setText(prefix + ("Δ" if relative else "") + "XYZ"[index])
            field.setReadOnly(local and index == 2)
            field.setToolTip(
                "Z local pertence ao plano; X e Y correspondem a U e V."
                if local and index == 2 else
                "Comprimento %s; aceita unidades, por exemplo 2 cm."
                % ("no plano da chapa" if local else "global"))

    def _display_values(self, values, candidate):
        if values is None:
            return None
        if self._spec.reference == CoordinateReference.PLANE:
            # UV conversion remains authoritative. Z only displays the normal
            # component; it is not another coordinate input or projection.
            z = self._plane.local(candidate.world)[2]
            if self._spec.mode == CoordinateMode.RELATIVE:
                z -= self._plane.local(self._last)[2]
            return (*values, z)
        return values

    def _show_waiting_status(self):
        self.candidate_status.setText(
            "Use um snap 3D ou informe X, Y e Z."
            if self._spec.component_count == 3 else
            "Use um snap no plano ou informe U e V.")

    def present_candidate(self, candidate):
        """Present an unconfirmed mouse candidate without acquiring or editing.

        Call after set_context; presentation never emits candidateChanged and
        therefore cannot start a second acquisition loop or project a point.
        """
        if self._closed:
            return
        if not self.isEnabled():
            self.add_button.setEnabled(False)
            return
        if self.editing:
            return
        try:
            values = (self._spec.present(candidate, plane=self._plane, last_point=self._last)
                      if candidate is not None else None)
            values = self._display_values(values, candidate)
        except ValueError:
            values = None
        self._writing = True
        try:
            for index, field in enumerate(self.fields):
                field.setText(display_length(values[index])
                              if values is not None and index < len(values) else "")
        finally:
            self._writing = False
        self._presentation = values is not None
        self.add_button.setEnabled(self._presentation and self.isEnabled())
        if self._presentation:
            self.candidate_status.setText("Ponto candidato — ainda não confirmado.")
        else:
            self._show_waiting_status()

    def clear(self):
        if self._closed:
            return
        self._writing = True
        try:
            for field in self.fields:
                field.setText("")
            self._editing = False
            self._presentation = False
            self.add_button.setEnabled(False)
            self._show_waiting_status()
        finally:
            self._writing = False

    def _candidate_from_text(self):
        fields = self.fields[:self._spec.component_count]
        if any(not field.text().strip() for field in fields):
            raise ValueError("Preencha todas as coordenadas com comprimentos válidos.")
        return self._spec.candidate(tuple(length_value(field.text()) for field in fields),
                                    plane=self._plane, last_point=self._last)

    def _text_changed(self, *_args):
        if self._closed or self._writing:
            return
        self._presentation = False
        self._editing = any(field.text().strip()
                            for field in self.fields[:self._spec.component_count])
        try:
            candidate = self._candidate_from_text()
        except ValueError:
            candidate = None
        self.add_button.setEnabled(candidate is not None and self.isEnabled())
        self.candidate_status.setText(
            "Coordenadas prontas para adicionar." if candidate is not None else
            "Complete todas as coordenadas com comprimentos válidos."
            if self._editing else "Use um snap 3D ou informe as coordenadas.")
        self.candidateChanged.emit(candidate)

    def _system_changed(self, *_args):
        if self._closed or self._writing:
            return
        was_editing = self.editing
        proposed = self._selected_spec()
        try:
            # Incomplete edits must retain their meaning, even on an explicit toggle.
            # A focus-out to a checkbox releases mouse ownership before its toggle
            # arrives; it does not discard or validate pending text.
            has_numeric_text = (not self._presentation and any(
                field.text().strip() for field in self.fields[:self._spec.component_count]))
            if has_numeric_text:
                self._candidate_from_text()  # Reject incomplete edits before toggling.
            candidate = self._get_candidate()
            if candidate is None and has_numeric_text:
                candidate = self._candidate_from_text()
            values = (proposed.present(candidate, plane=self._plane, last_point=self._last)
                      if candidate is not None else None)
            proposed.validate_context(self._plane, self._last)
        except ValueError as exc:
            self._writing = True
            try:
                self.global_coordinates.setChecked(self._spec.reference == CoordinateReference.GLOBAL)
                self.relative.setChecked(self._spec.mode == CoordinateMode.RELATIVE)
            finally:
                self._writing = False
            self.errorOccurred.emit(str(exc))
            return
        self._spec = proposed
        self._writing = True
        try:
            self._labels()
            values = self._display_values(values, candidate)
            for index, field in enumerate(self.fields):
                field.setText(display_length(values[index])
                              if values is not None and index < len(values) else "")
        finally:
            self._writing = False
        # This is presentation only. In particular, keep any normal residual
        # accepted by the controller's coplanarity tolerance in the world point.
        self._presentation = candidate is not None
        # A coordinate-system toggle is presentation, not keyboard input. In
        # particular a graphical Absolute -> Relative toggle must leave the
        # mouse callbacks enabled (B1).
        self._editing = was_editing
        self.add_button.setEnabled(candidate is not None and self.isEnabled())
        if candidate is not None:
            self.candidate_status.setText("Ponto candidato — ainda não confirmado.")
        else:
            self._show_waiting_status()
        self.candidateChanged.emit(candidate)

    def confirm(self, *_args):
        if self._closed or not self.isEnabled():
            return
        try:
            candidate = self._candidate_from_text()
            if self._presentation and self._get_candidate() is not None:
                candidate = self._get_candidate()
        except ValueError as exc:
            self.errorOccurred.emit(str(exc))
            return
        self.confirmRequested.emit(candidate)

    def eventFilter(self, watched, event):
        if self._closed:
            return False
        if watched in self.fields:
            if event.type() == QtCore.QEvent.FocusOut:
                # Resolve after Qt has installed the next focus widget. Tab
                # between coordinates keeps the numeric edit; returning to the
                # view resumes snap presentation. Text survives focus-out.
                QtCore.QTimer.singleShot(0, self._finish_focus_out)
        if event.type() in (QtCore.QEvent.ShortcutOverride, QtCore.QEvent.KeyPress):
            key = event.key()
            if key in (QtCore.Qt.Key_Return, QtCore.Qt.Key_Enter, QtCore.Qt.Key_Escape):
                event.accept()
                if event.type() == QtCore.QEvent.KeyPress and not event.isAutoRepeat():
                    if key == QtCore.Qt.Key_Escape:
                        self.cancelRequested.emit()
                    else:
                        self.confirm()
                return True
        return super().eventFilter(watched, event)

    def _finish_focus_out(self):
        if self._closed:
            return
        if QtWidgets.QApplication.focusWidget() not in self.fields:
            self._editing = False

    def dispose(self):
        if self._closed:
            return
        self._closed = True
        self._get_candidate = None
        for field in self.fields:
            field.removeEventFilter(self)
            field.textChanged.disconnect(self._text_changed)
        self.add_button.removeEventFilter(self)
        self.add_button.clicked.disconnect(self.confirm)
        self.global_coordinates.toggled.disconnect(self._system_changed)
        self.relative.toggled.disconnect(self._system_changed)
