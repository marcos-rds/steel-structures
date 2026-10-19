"""Local modal draft checkpoint; persistence remains owned by TrussEditSession."""
from copy import deepcopy
from PySide import QtWidgets


def _numeric_state(widget):
    if isinstance(widget, QtWidgets.QDoubleSpinBox):
        value = QtWidgets.QDoubleSpinBox.value(widget)
        line = widget.lineEdit()
    elif isinstance(widget, QtWidgets.QSpinBox):
        value = QtWidgets.QSpinBox.value(widget)
        line = widget.lineEdit()
    else:
        value, line = widget._value, widget
    metadata = {key: deepcopy(getattr(widget, key)) for key in
                ("_value", "_presented", "_editing_text", "_unit_factor", "_unit", "_had_error")
                if hasattr(widget, key)}
    return value, line.text(), line.isModified(), metadata


def _restore_numeric(widget, state):
    value, text, modified, metadata = state
    if isinstance(widget, QtWidgets.QDoubleSpinBox):
        QtWidgets.QDoubleSpinBox.setValue(widget, value)
        line = widget.lineEdit()
    elif isinstance(widget, QtWidgets.QSpinBox):
        QtWidgets.QSpinBox.setValue(widget, value)
        line = widget.lineEdit()
    else:
        widget.setValue(value)
        line = widget
    for key, value in metadata.items():
        setattr(widget, key, deepcopy(value))
    line.setText(text)
    line.setModified(modified)


class TrussEditorCheckpoint:
    def __init__(self, panel, editor):
        self.config = panel.session.snapshot()
        self.candidate = deepcopy(panel.controller.last_candidate)
        self.applied_state = panel.session.applied_state
        self.edge_snapshot_origin=deepcopy(getattr(panel.session,"_edge_snapshot_origin",None))
        self.reference_link_preference=getattr(panel.session,"_reference_link_preference",False)
        self.axis = deepcopy(panel._axis_direction)
        self.reference = self._reference(panel)
        self.reference_source = (panel.document.getObject(self.config.get("reference_source", ""))
                                 if self.config.get("reference_linked") else None)
        self.controls = []
        spacing = panel.spacing_editor
        self.spacings = [_numeric_state(widget) for widget in spacing._spins]
        for widget in panel.form.findChildren(QtWidgets.QWidget):
            if widget.window() is not panel.form.window() or editor.isAncestorOf(widget) or spacing.isAncestorOf(widget):
                continue
            if isinstance(widget, QtWidgets.QComboBox):
                state = ([(widget.itemText(i), deepcopy(widget.itemData(i)))
                          for i in range(widget.count())], widget.currentIndex())
                kind = "combo"
            elif isinstance(widget, QtWidgets.QCheckBox):
                kind, state = "check", widget.isChecked()
            elif isinstance(widget, (QtWidgets.QDoubleSpinBox, QtWidgets.QSpinBox)) or hasattr(widget, "_value"):
                kind, state = "number", _numeric_state(widget)
            else:
                continue
            self.controls.append((widget, kind, state))

    def _reference(self, panel):
        if not self.config.get("reference_linked"):
            return None
        from ..truss_reference import resolve_linked_reference
        try:
            resolved = resolve_linked_reference(panel.document, deepcopy(self.config), panel.session.owner)
            return {key: deepcopy(resolved.get(key)) for key in ("start", "end", "plane_normal", "height")}
        except (ValueError, RuntimeError, ReferenceError):
            return None  # An already-invalid reference remains repairable.

    def restore(self, panel):
        if panel._closed:
            return False
        try:
            panel.controller.bind_session(self.config)  # Existing context/persistence conflict checks.
            source = (panel.document.getObject(self.config.get("reference_source", ""))
                      if self.config.get("reference_linked") else None)
            if (self.applied_state != panel.session.applied_state or source is not self.reference_source
                    or self.reference != self._reference(panel)):
                panel.session.conflict_reason = "A referência ou o estado aplicado mudou externamente. Reabra a ferramenta."
                raise ValueError(panel.session.conflict_reason)
        except (ValueError, RuntimeError, ReferenceError) as exc:
            panel._show_error(str(exc))
            return False
        panel._preview_timer.stop()
        panel._updating = True
        try:
            panel.session.replace_config(self.config)
            panel.session._edge_snapshot_origin=deepcopy(self.edge_snapshot_origin)
            panel.session._reference_link_preference=self.reference_link_preference
            panel.controller.last_candidate = deepcopy(self.candidate)
            panel.session.invalidate("")
            panel._axis_direction = deepcopy(self.axis)
            for widget, kind, state in self.controls:
                blocked = widget.blockSignals(True)
                try:
                    if kind == "combo":
                        items, index = state
                        current = [(widget.itemText(i), widget.itemData(i)) for i in range(widget.count())]
                        # Keep native models/items alive when their options did
                        # not change; only the selected value needs restoring.
                        if current != items:
                            widget.clear()
                            for text, data in items:
                                widget.addItem(text, deepcopy(data))
                        widget.setCurrentIndex(index)
                    elif kind == "check":
                        widget.setChecked(state)
                    else:
                        _restore_numeric(widget, state)
                finally:
                    widget.blockSignals(blocked)
            panel.spacing_editor.set_values([state[0] for state in self.spacings])
            for widget, state in zip(panel.spacing_editor._spins, self.spacings):
                _restore_numeric(widget, state)
            for role in panel.role_buttons:
                panel._update_role_button(role)
        finally:
            panel._updating = False
        panel._refresh()
        return True
