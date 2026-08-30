# SPDX-License-Identifier: LGPL-2.1-or-later
"""Task panel for configuring one structural-member end adjustment."""

from __future__ import annotations

import FreeCAD as App
from FreeCAD import Gui
from PySide import QtCore, QtWidgets

from .member_adjustment_controller import (
    AdjustmentValidationError,
    MemberAdjustmentController,
    is_structural_member,
    member_display_name,
    reference_display_name,
)


GEOMETRY_LABELS = {
    "Limitar comprimento": "LengthLimit",
    "Recortar pelo plano": "PlaneCut",
}
END_LABELS = {"Automático": "Auto", "Início": "Start", "Fim": "End"}


def standard_buttons_value(button_box_type):
    buttons = button_box_type.Ok | button_box_type.Cancel
    return int(getattr(buttons, "value", buttons))


class _SelectionObserver:
    def __init__(self, panel):
        self.panel = panel

    def addSelection(self, document_name, object_name, subelement="", _point=None):
        panel = self.panel
        if panel is not None:
            panel._selection_received(document_name, object_name, subelement)

    def clear(self):
        self.panel = None


class MemberAdjustmentTaskPanel:
    """Hold proposed state locally and persist it only when accept() succeeds."""

    def __init__(self, document, member=None, on_closed=None):
        self.document = document
        self.controller = MemberAdjustmentController(document, member)
        self._on_closed = on_closed
        self._closed = False
        self._capture_mode = None
        self._selection_observer = None
        self._loading_slot = False
        self._active_choice = "Auto"
        self._drafts = {}
        self.reference = None
        self._last_error = None
        self.form = QtWidgets.QWidget()
        self.form.setWindowTitle("Recortar / Ajustar Membro")
        root = QtWidgets.QVBoxLayout(self.form)

        member_group = QtWidgets.QGroupBox("Membro")
        member_layout = QtWidgets.QVBoxLayout(member_group)
        self.member_label = QtWidgets.QLabel()
        self.member_label.setWordWrap(True)
        self.slot_summary = QtWidgets.QLabel()
        self.select_member_button = QtWidgets.QPushButton("Selecionar membro")
        member_layout.addWidget(self.member_label)
        member_layout.addWidget(self.slot_summary)
        member_layout.addWidget(self.select_member_button)
        root.addWidget(member_group)

        adjustment = QtWidgets.QGroupBox("Tipo de ajuste")
        adjustment_form = QtWidgets.QFormLayout(adjustment)
        self.geometry_mode = QtWidgets.QComboBox()
        self.geometry_mode.addItems(list(GEOMETRY_LABELS))
        self.end_choice = QtWidgets.QComboBox()
        self.end_choice.addItems(list(END_LABELS))
        self.gap = QtWidgets.QDoubleSpinBox()
        self.gap.setRange(-1.0e9, 1.0e9)
        self.gap.setDecimals(2)
        self.gap.setSuffix(" mm")
        adjustment_form.addRow("Operação:", self.geometry_mode)
        adjustment_form.addRow("Extremidade:", self.end_choice)
        adjustment_form.addRow("Gap:", self.gap)
        root.addWidget(adjustment)

        reference_group = QtWidgets.QGroupBox("Referência")
        reference_layout = QtWidgets.QVBoxLayout(reference_group)
        self.reference_label = QtWidgets.QLabel("Nenhuma referência selecionada")
        self.reference_label.setWordWrap(True)
        self.select_reference_button = QtWidgets.QPushButton("Selecionar referência")
        self.keep_reference = QtWidgets.QCheckBox("Manter vínculo com a referência")
        self.keep_reference.setChecked(True)
        reference_layout.addWidget(self.reference_label)
        reference_layout.addWidget(self.select_reference_button)
        reference_layout.addWidget(self.keep_reference)
        root.addWidget(reference_group)

        self.validation_message = QtWidgets.QLabel()
        self.validation_message.setWordWrap(True)
        root.addWidget(self.validation_message)
        self.remove_button = QtWidgets.QPushButton("Remover ajuste")
        self.remove_button.setVisible(False)
        root.addWidget(self.remove_button)
        root.addStretch(1)

        self.select_member_button.clicked.connect(lambda: self._begin_capture("member"))
        self.select_reference_button.clicked.connect(lambda: self._begin_capture("reference"))
        self.geometry_mode.currentTextChanged.connect(self._configuration_changed)
        self.end_choice.currentTextChanged.connect(self._end_changed)
        self.gap.valueChanged.connect(self._configuration_changed)
        self.keep_reference.toggled.connect(self._configuration_changed)
        self.remove_button.clicked.connect(self.remove_adjustment)
        self._initialize_drafts()
        self._refresh()

    def _slot_draft(self, prefix):
        obj = self.controller.member
        mode = str(getattr(obj, prefix + "AdjustmentGeometryMode", "LengthLimit"))
        link_mode = str(getattr(obj, prefix + "AdjustmentMode", "None"))
        return {
            "geometry": next(
            (label for label, value in GEOMETRY_LABELS.items() if value == mode),
            "Limitar comprimento",
            ),
            "gap": float(getattr(getattr(obj, prefix + "AdjustmentGap", 0.0), "Value",
                                 getattr(obj, prefix + "AdjustmentGap", 0.0))),
            "keep": link_mode != "Fixed",
            "reference": (getattr(obj, prefix + "AdjustmentReference", None)
                          if link_mode == "Associative" else None),
            "mode": link_mode,
        }

    def _initialize_drafts(self):
        obj = self.controller.member
        if obj is None:
            self._drafts = {"Auto": {"geometry": "Limitar comprimento", "gap": 0.0,
                                      "keep": True, "reference": None, "mode": "None"}}
            self._load_draft("Auto")
            return
        self._drafts = {prefix: self._slot_draft(prefix) for prefix in ("Start", "End")}
        self._drafts["Auto"] = {"geometry": "Limitar comprimento", "gap": 0.0,
                                 "keep": True, "reference": None, "mode": "None"}
        self._loading_slot = True
        self.end_choice.setCurrentText("Automático")
        self._loading_slot = False
        self._load_draft("Auto")

    def _save_active_draft(self):
        if self._active_choice not in self._drafts:
            return
        draft = self._drafts[self._active_choice]
        draft.update(geometry=self.geometry_mode.currentText(), gap=self.gap.value(),
                     keep=self.keep_reference.isChecked(), reference=self.reference)

    def _load_draft(self, choice):
        self._active_choice = choice
        draft = self._drafts[choice]
        self._loading_slot = True
        self.geometry_mode.setCurrentText(draft["geometry"])
        self.gap.setValue(draft["gap"])
        self.keep_reference.setChecked(draft["keep"])
        self.reference = draft["reference"]
        self._loading_slot = False

    def _end_changed(self, label):
        if self._loading_slot:
            return
        self._save_active_draft()
        self._load_draft(END_LABELS[label])
        self._refresh()

    def _begin_capture(self, mode):
        self._remove_selection_observer()
        self._capture_mode = mode
        observer = _SelectionObserver(self)
        Gui.Selection.addObserver(observer)
        self._selection_observer = observer
        self._set_message(
            "Selecione um membro estrutural." if mode == "member"
            else self._reference_selection_prompt(),
            error=False,
        )

    def _reference_kind_description(self):
        if GEOMETRY_LABELS[self.geometry_mode.currentText()] == "PlaneCut":
            return "uma Face plana"
        return "uma Face plana ou uma Edge reta"

    def _reference_selection_prompt(self):
        return "Selecione %s na vista." % self._reference_kind_description()

    def _reference_validation_prompt(self):
        return "Selecione %s." % self._reference_kind_description()

    def _selection_received(self, document_name, object_name, subelement):
        if self._closed or document_name != self.document.Name:
            return
        obj = self.document.getObject(object_name)
        mode = self._capture_mode
        if mode == "member":
            if not is_structural_member(obj):
                self._set_message("Selecione um membro estrutural.", error=True)
                return
            self.controller.set_member(obj)
            self._remove_selection_observer()
            self._initialize_drafts()
        elif mode == "reference":
            if not (str(subelement).startswith("Face") or str(subelement).startswith("Edge")):
                self._set_message("Selecione explicitamente uma Face ou Edge.", error=True)
                return
            self.reference = (obj, [str(subelement)])
            self._drafts[self._active_choice]["reference"] = self.reference
            self._remove_selection_observer()
        self._refresh()

    def _remove_selection_observer(self):
        observer = self._selection_observer
        if observer is not None:
            try:
                Gui.Selection.removeObserver(observer)
            except Exception:
                pass
            observer.clear()
        self._selection_observer = None
        self._capture_mode = None

    def _proposal_values(self):
        return {
            "geometry_mode": GEOMETRY_LABELS[self.geometry_mode.currentText()],
            "end_choice": END_LABELS[self.end_choice.currentText()],
            "gap": self.gap.value(),
            "keep_reference": self.keep_reference.isChecked(),
            "reference": self.reference,
        }

    def _validate(self):
        values = self._proposal_values()
        if self.reference is None and not values["keep_reference"]:
            return self.controller.validate_existing_fixed(
                geometry_mode=values["geometry_mode"],
                end_choice=values["end_choice"], gap=values["gap"],
            )
        return self.controller.validate(**values)

    def _configuration_changed(self, _value=None):
        if self._loading_slot:
            return
        self._save_active_draft()
        self._refresh()

    def _refresh(self):
        obj = self.controller.member
        self.member_label.setText(
            member_display_name(obj) if obj is not None else "Selecione um membro estrutural."
        )
        if obj is not None:
            def summary(prefix):
                mode = str(getattr(obj, prefix + "AdjustmentMode", "None"))
                geometry = str(getattr(obj, prefix + "AdjustmentGeometryMode", "LengthLimit"))
                return "Sem ajuste" if mode == "None" else geometry
            self.slot_summary.setText(
                "Início: %s   •   Fim: %s" % (summary("Start"), summary("End"))
            )
        else:
            self.slot_summary.setText("Início: Sem ajuste   •   Fim: Sem ajuste")
        if self.reference is not None:
            self.reference_label.setText(reference_display_name(self.reference))
        elif (obj is None or self._active_choice == "Auto"
              or str(getattr(obj, self._active_choice + "AdjustmentMode", "None")) != "Fixed"):
            self.reference_label.setText("Nenhuma referência selecionada")
        else:
            self.reference_label.setText("Ajuste fixo")
        current_mode = (str(getattr(obj, self._active_choice + "AdjustmentMode", "None"))
                        if obj is not None and self._active_choice in ("Start", "End") else "None")
        self.remove_button.setVisible(current_mode != "None")
        try:
            resolved = self._validate()
            self._last_error = None
            self._set_message(resolved.message, error=False)
            self._set_accept_enabled(True)
            return True
        except AdjustmentValidationError as exc:
            self._last_error = str(exc)
            message = str(exc)
            if (obj is not None and self.reference is None
                    and message in (
                        "Selecione uma referência geométrica.",
                        "Selecione uma Face plana ou uma Edge reta.",
                    )):
                message = self._reference_validation_prompt()
            self._set_message(message, error=True)
            self._set_accept_enabled(False)
            return False

    def _set_message(self, text, error):
        self.validation_message.setText(text)
        self.validation_message.setStyleSheet("color: #c33" if error else "color: #287a3b")

    def _set_accept_enabled(self, enabled):
        try:
            window = self.form.window()
            box = window.findChild(QtWidgets.QDialogButtonBox)
            button = box.button(QtWidgets.QDialogButtonBox.Ok) if box is not None else None
            if button is not None:
                button.setEnabled(bool(enabled))
        except Exception:
            pass

    def isValid(self):
        return self._last_error is None

    def accept(self):
        try:
            resolved = self._validate()
            self.controller.apply(resolved)
        except Exception as exc:
            self._last_error = str(exc)
            self._set_message(str(exc), error=True)
            self._set_accept_enabled(False)
            return False
        self._finish(True)
        return True

    def reject(self):
        self._finish(False)
        return True

    def remove_adjustment(self):
        try:
            choice = END_LABELS[self.end_choice.currentText()]
            if choice == "Auto":
                if self.reference is None:
                    raise AdjustmentValidationError("Escolha Início ou Fim para remover o ajuste.")
                choice = self._validate().adjusted_end
            self.controller.remove_adjustment(choice)
        except Exception as exc:
            self._set_message(str(exc), error=True)
            return False
        self._finish(True)
        return True

    def _finish(self, accepted):
        if self._closed:
            return
        self._closed = True
        self._remove_selection_observer()
        callback, self._on_closed = self._on_closed, None
        if callback:
            callback(self, accepted)

    def getStandardButtons(self):
        return standard_buttons_value(QtWidgets.QDialogButtonBox)


__all__ = ["MemberAdjustmentTaskPanel", "standard_buttons_value"]
