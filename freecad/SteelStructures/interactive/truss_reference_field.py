# SPDX-License-Identifier: LGPL-2.1-or-later
"""Unit-aware text entry for the truss frame, independent of Draft acquisition."""
import math
import re

import FreeCAD as App
from PySide import QtCore, QtWidgets


class TrussReferenceField(QtWidgets.QLineEdit):
    """Keep exact internal values while FreeCAD formats their presentation."""
    valueChanged = QtCore.Signal(float)
    inputError = QtCore.Signal(str)

    def __init__(self, value, *, normal=False, parent=None):
        super().__init__(parent)
        self.normal = normal
        self._unit_factor = 1.
        self._unit = ""
        self._presented = self._editing_text = None
        self._had_error = False
        self.setMinimumWidth(110)
        self.setMinimumHeight(self.sizeHint().height())
        self.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred)
        self.setValue(value)
        self.editingFinished.connect(self.commit)

    def _parse(self, text):
        try:
            if not text.strip():
                raise ValueError("empty")
            try:
                quantity = App.Units.Quantity(text.strip())
            except ValueError:
                # FreeCAD accepts decimal comma/dot, but not locale grouping.
                # Let QLocale validate grouped numeric input before handing the
                # unit expression back to the existing FreeCAD parser.
                match=re.fullmatch(r"\s*([+-]?\d[\d.,\u00a0\u202f ]*(?:[eE][+-]?\d+)?)\s*(.*?)\s*",text)
                number,ok=self.locale().toDouble(match[1].strip()) if match else (0.,False)
                if not ok:
                    raise
                quantity=App.Units.Quantity(repr(number)+" "+match[2])
            scalar = App.Units.Quantity(1).Unit
            length = App.Units.Quantity(1, App.Units.Length).Unit
            if quantity.Unit == scalar:
                value = float(quantity.Value) * (1. if self.normal else self._unit_factor)
            elif not self.normal and quantity.Unit == length:
                value = float(quantity.Value)
            else:
                raise ValueError("dimension")
            if not math.isfinite(value):
                raise ValueError("nonfinite")
            return value
        except (ValueError, TypeError, RuntimeError, OverflowError) as exc:
            kind = "um número sem unidade" if self.normal else "um comprimento válido"
            raise ValueError(f"{self.accessibleName()}: informe {kind}.") from exc

    def value(self):
        # Never parse a rounded presentation or an untouched full-precision edit.
        return (self._value if not self.isModified() and self.text() in (self._presented, self._editing_text)
                else self._parse(self.text()))

    def _present_value(self):
        quantity = (App.Units.Quantity(self._value) if self.normal else
                    App.Units.Quantity(self._value, App.Units.Length))
        if not self.normal:
            _text, self._unit_factor, self._unit = quantity.getUserPreferred()
        self._presented = (quantity.UserString.strip() if self.normal else
                           self.locale().toString(self._value / self._unit_factor, "f", 2)
                           + " " + self._unit)
        self._editing_text = None
        self.setText(self._presented)
        self.setModified(False)

    def setValue(self, value):
        value = float(value)
        previous = getattr(self, "_value", None)
        # Synchronization must not disturb a partial edit, cursor or selection
        # when the incoming candidate has the same numeric value.
        if self.hasFocus() and self._presented is not None:
            if previous == value:
                return
            try:
                if self.value() == value:
                    self._value = value
                    if previous is not None and previous != value:
                        self.valueChanged.emit(value)
                    return
            except ValueError:
                pass  # An explicit new reference may replace an unfinished edit.
        self._value = value
        self._present_value()
        if previous is not None and previous != value:
            self.valueChanged.emit(value)

    def commit(self):
        edited = self.isModified() or self.text() not in (self._presented, self._editing_text)
        try:
            value = self.value()
        except ValueError as exc:
            self._had_error = True
            self.inputError.emit(str(exc))
            return False
        notify = edited or self._had_error
        self._had_error = False
        self._value = value
        self._present_value()
        if notify:
            self.valueChanged.emit(value)
        return True

    def focusInEvent(self, event):
        super().focusInEvent(event)
        if not self.isModified() and self.text() in (self._presented, self._editing_text):
            locale = QtCore.QLocale(self.locale())
            locale.setNumberOptions(locale.numberOptions() | QtCore.QLocale.OmitGroupSeparator)
            text = locale.toString(self._value / self._unit_factor, "g", 17)
            self._editing_text = text + (" " + self._unit if not self.normal else "")
            self.setText(self._editing_text)

    def keyPressEvent(self, event):
        if event.key() in (QtCore.Qt.Key_Return, QtCore.Qt.Key_Enter):
            self.commit()
            event.accept()  # Confirm this field, never the TaskDialog's OK action.
        elif event.key() == QtCore.Qt.Key_Escape:
            notify = (self._had_error or self.isModified()
                      or self.text() not in (self._presented, self._editing_text))
            self._had_error = False
            self._present_value()
            if notify:
                self.valueChanged.emit(self._value)
            event.accept()
        else:
            super().keyPressEvent(event)
