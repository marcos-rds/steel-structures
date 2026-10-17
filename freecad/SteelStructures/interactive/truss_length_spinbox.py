"""Native spinbox with exact storage and the approved FreeCAD length parser."""
from PySide import QtCore, QtGui, QtWidgets
from .truss_reference_field import TrussReferenceField
from .truss_units import length_text, preferred_length


class TrussLengthSpinBox(QtWidgets.QDoubleSpinBox):
    inputError = QtCore.Signal(str)
    normal = False
    _parse = TrussReferenceField._parse

    def __init__(self, parent=None):
        self._unit_factor = 1.
        self._unit = "mm"
        self._editing_text = None
        self._activate = lambda: None
        self._had_error = False
        super().__init__(parent)
        self.setAccessibleName("Comprimento")
        # QDoubleSpinBox rounds storage to decimals. Keep all double precision;
        # textFromValue alone controls the two-decimal presentation.
        self.setDecimals(323)
        self.setKeyboardTracking(False)
        self.setGroupSeparatorShown(True)

    def textFromValue(self, value):
        # Qt also formats the range extrema while calculating size hints.
        # Formatting a probe must never change the unit of a real pending edit.
        return length_text(value, self.locale())

    def valueFromText(self, text):
        if not self.lineEdit().isModified() and text in (self.textFromValue(super().value()), self._editing_text):
            return super().value()
        return self._parse(text)

    def value(self):
        if self.lineEdit().isModified():
            try:
                value=self._parse(self.lineEdit().text())
                if not self.minimum() <= value <= self.maximum():
                    raise ValueError("Comprimento fora do intervalo permitido.")
                return value
            except ValueError:
                self._had_error=True
                raise
        return super().value()

    def validate(self, text, position):
        try:
            value = self._parse(text)
            state = (QtGui.QValidator.Acceptable if self.minimum() <= value <= self.maximum()
                     else QtGui.QValidator.Intermediate)
        except ValueError:
            state = QtGui.QValidator.Intermediate
        return state, text, position

    def setValue(self, value):
        if self.hasFocus() and float(value) == super().value():
            return  # Includes a partial edit during synchronization.
        if self.hasFocus():
            try:
                if float(value) == self.value():
                    return  # A valid pending edit also keeps its exact text/selection.
            except ValueError:
                pass
        super().setValue(value)
        self._unit_factor,self._unit=preferred_length(super().value())
        self._editing_text=None

    def focusInEvent(self, event):
        self._activate()
        super().focusInEvent(event)
        if self.lineEdit().isModified():
            return
        self._unit_factor,self._unit=preferred_length(super().value())
        locale = QtCore.QLocale(self.locale())
        locale.setNumberOptions(locale.numberOptions() | QtCore.QLocale.OmitGroupSeparator)
        self._editing_text = locale.toString(super().value() / self._unit_factor, "g", 17) + " " + self._unit
        self.lineEdit().setText(self._editing_text)
        self.lineEdit().setModified(False)

    def _commit(self):
        try:
            value = self.valueFromText(self.lineEdit().text())
            if not self.minimum() <= value <= self.maximum():
                raise ValueError("Comprimento fora do intervalo permitido.")
        except ValueError as exc:
            self._had_error=True
            self.inputError.emit(str(exc))
            return False
        previous=super().value()
        recover=self._had_error
        self._had_error=False
        super().setValue(value)
        self._unit_factor,self._unit=preferred_length(super().value())
        self.lineEdit().setText(self.textFromValue(super().value()))
        self.lineEdit().setModified(False)
        if recover and previous == value:
            self.valueChanged.emit(value)
        return True

    def focusOutEvent(self, event):
        self._commit()
        # Qt's default fixup would silently replace incomplete input.
        QtWidgets.QWidget.focusOutEvent(self, event)
        self.editingFinished.emit()

    def keyPressEvent(self, event):
        if event.key() in (QtCore.Qt.Key_Return, QtCore.Qt.Key_Enter):
            self._commit()
            event.accept()
        elif event.key() == QtCore.Qt.Key_Escape:
            notify=self._had_error or self.lineEdit().isModified()
            self._had_error=False
            self.lineEdit().setText(self.textFromValue(super().value()))
            self.lineEdit().setModified(False)
            if notify:
                self.valueChanged.emit(super().value())
            event.accept()
        else:
            super().keyPressEvent(event)

    def wheelEvent(self, event):
        if self.hasFocus():
            super().wheelEvent(event)
        else:
            event.ignore()

    def stepBy(self, steps):
        super().stepBy(steps)
        self._unit_factor,self._unit=preferred_length(super().value())
        self._editing_text=None
