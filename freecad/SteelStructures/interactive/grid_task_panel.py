# SPDX-License-Identifier: LGPL-2.1-or-later
"""Task panel for the first local Structural Grid visual prototype."""

from __future__ import annotations

from PySide import QtCore, QtGui, QtWidgets

from ..grid_geometry import build_grid_geometry
from ..paths import (
    GRID_RESET_DEFAULTS_ICON,
    GRID_SPACING_ADD_ICON,
    GRID_SPACING_DUPLICATE_ICON,
    GRID_SPACING_REMOVE_ICON,
)
from ..preferences import (
    GridAppearanceSettings,
    default_grid_appearance,
    load_grid_appearance_settings,
    save_grid_appearance_settings,
)
SCHEMES = {
    "Numérica": "Numeric",
    "Alfabética": "Alphabetic",
    "Personalizada": "Custom",
}


class SpacingDoubleSpinBox(QtWidgets.QDoubleSpinBox):
    """Normal Qt editor that reports explicit focus without reacting to hover."""

    def __init__(self, activate, parent=None):
        super().__init__(parent)
        self._activate = activate
        self.setFocusPolicy(QtCore.Qt.StrongFocus)

    def focusInEvent(self, event):
        self._activate()
        super().focusInEvent(event)

    def wheelEvent(self, event):
        if self.hasFocus():
            super().wheelEvent(event)
        else:
            event.ignore()


def standard_buttons_value(button_box):
    """Return FreeCAD's integer mask for legacy and PySide6 enum APIs."""
    standard = getattr(button_box, "StandardButton", button_box)
    buttons = standard.Ok | standard.Cancel
    return int(getattr(buttons, "value", buttons))


def stabilize_compact_tool_button(button):
    """Prevent external margins and padding from clipping a compact tool icon."""
    button.setStyleSheet("QToolButton { margin: 0px; padding: 2px; }")


class _EscapeEventFilter(QtCore.QObject):
    """QObject bridge that routes Escape to a safe panel callback."""

    def __init__(self, callback, parent=None):
        super().__init__(parent)
        self._callback = callback
        self._triggered = False

    def eventFilter(self, watched, event):
        event_types = {
            getattr(QtCore.QEvent, "KeyPress", None),
            getattr(QtCore.QEvent, "ShortcutOverride", None),
        }
        qt_key = getattr(QtCore.Qt, "Key", QtCore.Qt)
        escape = getattr(qt_key, "Key_Escape", getattr(QtCore.Qt, "Key_Escape", None))
        if event.type() in event_types and event.key() == escape:
            accept = getattr(event, "accept", None)
            if callable(accept):
                accept()
            callback = self._callback
            if callback is not None and not self._triggered:
                self._triggered = True
                callback()
            return True
        return super().eventFilter(watched, event)

    def clear(self):
        self._callback = None


def parse_custom_identifiers(text, count):
    """Parse comma-separated labels; mathematical validation remains centralized."""
    values = [value.strip() for value in str(text).split(",")]
    if str(text).strip() == "":
        values = []
    # This call is deliberately the single source of count/empty/duplicate validation.
    build_grid_geometry([], [1.0] * max(count - 1, 0), y_identifier_scheme="custom", y_identifiers=values)
    return values


def _supported_font_name(view, requested, fallback):
    try:
        options = tuple(str(value) for value in view.getEnumerationsOfProperty("FontName"))
    except (AttributeError, ReferenceError, RuntimeError, TypeError):
        options = ()
    requested = str(requested or "")
    return requested if requested and (not options or requested in options) else str(fallback or "")


class SpacingEditor(QtWidgets.QGroupBox):
    """Independent editable list of positive spacings for one axis family."""

    def __init__(self, title, defaults, on_change, parent=None):
        super().__init__(title, parent)
        self._on_change = on_change
        self._spins = []
        self._active_spin = None
        self._field_minimum_width = 0
        layout = QtWidgets.QVBoxLayout(self)
        compact_spacing = max(round(self.fontMetrics().lineSpacing() * 0.25), 3)
        layout.setContentsMargins(compact_spacing, compact_spacing,
                                  compact_spacing, compact_spacing)
        layout.setSpacing(compact_spacing)
        content = QtWidgets.QHBoxLayout()
        content.setContentsMargins(0, 0, 0, 0)
        content.setSpacing(compact_spacing)
        self.scroll = QtWidgets.QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QtWidgets.QFrame.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.editor_container = QtWidgets.QWidget()
        self.editor_layout = QtWidgets.QVBoxLayout(self.editor_container)
        self.editor_layout.setContentsMargins(0, 0, 0, 0)
        self.editor_layout.setSpacing(0)
        self.editor_layout.setAlignment(QtCore.Qt.AlignTop)
        self.scroll.setWidget(self.editor_container)
        self.scroll.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        content.addWidget(self.scroll, 1)
        actions = QtWidgets.QVBoxLayout()
        actions.setContentsMargins(0, 0, 0, 0)
        actions.setSpacing(compact_spacing)
        self.add_button = self._action_button(
            GRID_SPACING_ADD_ICON, "+", "Adicionar vão"
        )
        self.duplicate_button = self._action_button(
            GRID_SPACING_DUPLICATE_ICON, "⧉", "Duplicar vão selecionado"
        )
        self.remove_button = self._action_button(
            GRID_SPACING_REMOVE_ICON, "−", "Remover vão selecionado"
        )
        for button in (self.add_button, self.duplicate_button, self.remove_button):
            actions.addWidget(button)
        actions.addStretch(1)
        content.addLayout(actions)
        layout.addLayout(content)
        self.summary = QtWidgets.QLabel()
        layout.addWidget(self.summary)
        self.add_button.clicked.connect(self.add_spacing)
        self.duplicate_button.clicked.connect(self.duplicate_spacing)
        self.remove_button.clicked.connect(self.remove_spacing)
        for value in defaults:
            self._append(value)
        self._update_editor_metrics()
        self._update_summary()

    def _action_button(self, icon_path, fallback, description):
        button = QtWidgets.QToolButton()
        stabilize_compact_tool_button(button)
        icon = QtGui.QIcon(icon_path)
        if icon.isNull():
            button.setText(fallback)
        else:
            button.setIcon(icon)
        button.setToolTip(description)
        button.setAccessibleName(description)
        button.setFocusPolicy(QtCore.Qt.StrongFocus)
        return button

    def _update_editor_metrics(self):
        probe = self._spins[0] if self._spins else SpacingDoubleSpinBox(lambda: None)
        metrics = probe.fontMetrics()
        text_width = metrics.horizontalAdvance("100000,00 mm")
        style = probe.style()
        arrow_width = style.pixelMetric(QtWidgets.QStyle.PM_ScrollBarExtent, None, probe)
        frame_width = style.pixelMetric(QtWidgets.QStyle.PM_SpinBoxFrameWidth, None, probe)
        field_width = max(probe.sizeHint().width(), text_width + arrow_width + 2 * frame_width)
        row_height = probe.sizeHint().height()
        spacing = max(self.editor_layout.spacing(), 0)
        margins = self.editor_layout.contentsMargins()
        chrome = self.scroll.frameWidth() * 2 + margins.top() + margins.bottom()
        height_for = lambda rows: chrome + rows * row_height + (rows - 1) * spacing
        content_rows = max(len(self._spins), 1)
        self.editor_container.setMinimumHeight(
            margins.top() + margins.bottom() + content_rows * row_height
            + (content_rows - 1) * spacing
        )
        self._field_minimum_width = field_width
        self.scroll.setMinimumWidth(
            field_width + style.pixelMetric(QtWidgets.QStyle.PM_ScrollBarExtent)
            + self.scroll.frameWidth() * 2
        )
        visible_rows = min(max(len(self._spins), 1), 7)
        self.scroll.setFixedHeight(height_for(visible_rows))
        for spin in self._spins:
            spin.setMinimumWidth(field_width)
            spin.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        tool_extent = row_height
        icon_extent = max(round(tool_extent * 0.62), 16)
        for button in (self.add_button, self.duplicate_button, self.remove_button):
            button.setFixedSize(tool_extent, tool_extent)
            button.setIconSize(QtCore.QSize(icon_extent, icon_extent))
        if probe not in self._spins:
            probe.deleteLater()

    def _append(self, value):
        spin = SpacingDoubleSpinBox(lambda: self._set_active(spin))
        spin.setRange(0.0, 1.0e9)
        spin.setDecimals(2)
        spin.setSuffix(" mm")
        spin.setValue(float(value))
        spin.valueChanged.connect(self._changed)
        self._spins.append(spin)
        self.editor_layout.addWidget(spin)
        if self._field_minimum_width:
            spin.setMinimumWidth(self._field_minimum_width)
        spin.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        return spin

    def _set_active(self, spin):
        if spin in self._spins:
            self._active_spin = spin

    def active_index(self):
        if self._active_spin in self._spins:
            return self._spins.index(self._active_spin)
        return len(self._spins) - 1

    def set_values(self, values):
        for spin in self._spins:
            self.editor_layout.removeWidget(spin)
            spin.deleteLater()
        self._spins = []
        self._active_spin = None
        for value in values:
            self._append(value)
        self._update_editor_metrics()
        self._changed()

    def values(self):
        return [spin.value() for spin in self._spins]

    def _changed(self, _value=None):
        self._update_summary()
        self._on_change()

    def _update_summary(self):
        values = self.values()
        self.summary.setText(f"{len(values) + 1} eixos • total: {sum(values):g} mm")

    def add_spacing(self):
        values = self.values()
        spin = self._append(values[-1] if values else 1000.0)
        self._update_editor_metrics()
        spin.setFocus(QtCore.Qt.OtherFocusReason)
        self._changed()

    def duplicate_spacing(self):
        row = self.active_index()
        values = self.values()
        spin = self._append(values[row] if 0 <= row < len(values)
                            else (values[-1] if values else 1000.0))
        self._update_editor_metrics()
        spin.setFocus(QtCore.Qt.OtherFocusReason)
        self._changed()

    def remove_spacing(self):
        row = self.active_index()
        if row >= 0:
            spin = self._spins.pop(row)
            self.editor_layout.removeWidget(spin)
            spin.deleteLater()
            self._active_spin = None
            if self._spins:
                next_spin = self._spins[min(row, len(self._spins) - 1)]
                next_spin.setFocus(QtCore.Qt.OtherFocusReason)
            self._update_editor_metrics()
            self._changed()


class GridTaskPanel:
    """Own one preview object until the FreeCAD task dialog accepts or rejects it."""

    def __init__(self, document, grid_object, on_closed=None):
        self.document = document
        self.grid_object = grid_object
        self._on_closed = on_closed
        self._closed = False
        self._initializing = True
        self._last_error = None
        self._escape_filter = None
        self._escape_filter_target = None
        self.form = QtWidgets.QWidget()
        root = QtWidgets.QVBoxLayout(self.form)

        panel_spacing = max(round(self.form.fontMetrics().lineSpacing() * 0.3), 4)
        root.setContentsMargins(panel_spacing, panel_spacing,
                                panel_spacing, panel_spacing)
        root.setSpacing(panel_spacing)
        header = QtWidgets.QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(panel_spacing)
        name_label = QtWidgets.QLabel("Nome do grid:")
        self.name_edit = QtWidgets.QLineEdit("Grid Estrutural")
        self.name_edit.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        self.reset_button = QtWidgets.QToolButton()
        stabilize_compact_tool_button(self.reset_button)
        self.reset_button.setToolTip("Redefinir todos os padrões do Grid")
        self.reset_button.setAccessibleName("Redefinir todos os padrões do Grid")
        reset_icon = QtGui.QIcon(GRID_RESET_DEFAULTS_ICON)
        if reset_icon.isNull():
            self.reset_button.setText("↺")
        else:
            self.reset_button.setIcon(reset_icon)
        reset_extent = self.name_edit.sizeHint().height()
        self.reset_button.setFixedSize(reset_extent, reset_extent)
        reset_icon_extent = max(round(reset_extent * 0.62), 16)
        self.reset_button.setIconSize(QtCore.QSize(reset_icon_extent, reset_icon_extent))
        self.reset_button.setFocusPolicy(QtCore.Qt.StrongFocus)
        header.addWidget(name_label)
        header.addWidget(self.name_edit, 1)
        header.addWidget(self.reset_button)
        root.addLayout(header)

        self.x_editor = SpacingEditor("Vãos em X", [6000, 6000], self.update_preview)
        self.y_editor = SpacingEditor("Vãos em Y", [5000, 5000], self.update_preview)
        root.addWidget(self.x_editor)
        root.addWidget(self.y_editor)

        extensions = QtWidgets.QGroupBox("Extensões")
        extension_form = QtWidgets.QFormLayout(extensions)
        self.extensions = {}
        for key, label in (("XStartExtension", "Início em X:"), ("XEndExtension", "Fim em X:"),
                           ("YStartExtension", "Início em Y:"), ("YEndExtension", "Fim em Y:")):
            spin = QtWidgets.QDoubleSpinBox()
            spin.setRange(0.0, 1.0e9)
            spin.setDecimals(2)
            spin.setSuffix(" mm")
            spin.setValue(1000.0)
            self.extensions[key] = spin
            extension_form.addRow(label, spin)
        root.addWidget(extensions)

        identification = QtWidgets.QGroupBox("Identificação")
        identification_form = QtWidgets.QFormLayout(identification)
        self.x_scheme, self.y_scheme = QtWidgets.QComboBox(), QtWidgets.QComboBox()
        for combo in (self.x_scheme, self.y_scheme):
            combo.addItems(list(SCHEMES))
        self.x_scheme.setCurrentText("Numérica")
        self.y_scheme.setCurrentText("Alfabética")
        self.x_labels, self.y_labels = QtWidgets.QLineEdit(), QtWidgets.QLineEdit()
        self.x_labels.setPlaceholderText("Ex.: 1, 2, 3")
        self.y_labels.setPlaceholderText("Ex.: A, B, C")
        self.x_labels.textChanged.connect(self.update_preview)
        self.y_labels.textChanged.connect(self.update_preview)
        identification_form.addRow("Eixos X:", self.x_scheme)
        self.x_labels_label = QtWidgets.QLabel("Identificadores X:")
        identification_form.addRow(self.x_labels_label, self.x_labels)
        identification_form.addRow("Eixos Y:", self.y_scheme)
        self.y_labels_label = QtWidgets.QLabel("Identificadores Y:")
        identification_form.addRow(self.y_labels_label, self.y_labels)
        root.addWidget(identification)

        appearance = QtWidgets.QGroupBox("Aparência")
        appearance_form = QtWidgets.QFormLayout(appearance)
        current_view = getattr(grid_object, "ViewObject", None)
        current_font = str(getattr(current_view, "FontName", "") or "")
        self._factory_appearance = default_grid_appearance(current_font)
        appearance_settings = load_grid_appearance_settings()
        self._font_name = _supported_font_name(
            current_view, appearance_settings.font_name, current_font
        )
        self.line_color = QtGui.QColor.fromRgbF(*appearance_settings.line_color)
        self.point_color = QtGui.QColor.fromRgbF(*appearance_settings.intersection_color)
        self.line_color_button = self._color_swatch("Cor das linhas")
        self.point_color_button = self._color_swatch("Cor dos pontos")
        self.line_width = QtWidgets.QDoubleSpinBox()
        self.line_width.setRange(1.0, 20.0)
        self.line_width.setValue(appearance_settings.line_width)
        self.show_points = QtWidgets.QCheckBox()
        self.show_points.setChecked(appearance_settings.show_intersections)
        self.point_size = QtWidgets.QDoubleSpinBox()
        self.point_size.setRange(1.0, 30.0)
        self.point_size.setValue(appearance_settings.intersection_size)
        self.show_labels = QtWidgets.QCheckBox()
        self.show_labels.setChecked(appearance_settings.show_labels)
        self.label_position = QtWidgets.QComboBox()
        self.label_position.addItems(["Start", "End", "Both"])
        self.label_position.setCurrentText(appearance_settings.label_position)
        self.label_offset = QtWidgets.QDoubleSpinBox()
        self.label_offset.setRange(0.0, 1.0e9)
        self.label_offset.setDecimals(2)
        self.label_offset.setSuffix(" mm")
        self.label_offset.setValue(appearance_settings.label_offset)
        self.font_size = QtWidgets.QDoubleSpinBox()
        self.font_size.setRange(1.0, 200.0)
        self.font_size.setValue(appearance_settings.font_size)
        self.text_color = QtGui.QColor.fromRgbF(*appearance_settings.text_color)
        self.text_color_button = self._color_swatch("Cor do texto")
        self._color_buttons = {
            "line": self.line_color_button,
            "point": self.point_color_button,
            "text": self.text_color_button,
        }
        for target, button in self._color_buttons.items():
            button.clicked.connect(
                lambda _checked=False, selected_target=target:
                self._choose_color(selected_target)
            )
        appearance_form.addRow("Cor das linhas:", self.line_color_button)
        appearance_form.addRow("Espessura das linhas:", self.line_width)
        appearance_form.addRow("Exibir pontos:", self.show_points)
        appearance_form.addRow("Cor dos pontos:", self.point_color_button)
        appearance_form.addRow("Tamanho dos pontos:", self.point_size)
        appearance_form.addRow("Exibir identificadores:", self.show_labels)
        appearance_form.addRow("Posição:", self.label_position)
        appearance_form.addRow("Afastamento:", self.label_offset)
        appearance_form.addRow("Tamanho do texto:", self.font_size)
        appearance_form.addRow("Cor do texto:", self.text_color_button)
        root.addWidget(appearance)

        self.validation_message = QtWidgets.QLabel()
        self.validation_message.setWordWrap(True)
        root.addWidget(self.validation_message)
        root.addStretch(1)
        # Connect only after every identification and appearance widget exists.
        for combo in (self.x_scheme, self.y_scheme): combo.currentTextChanged.connect(self._identification_changed)
        for spin in self.extensions.values(): spin.valueChanged.connect(self.update_preview)
        for widget in (self.line_width, self.point_size, self.label_offset, self.font_size):
            widget.valueChanged.connect(self.update_preview)
        for widget in (self.show_points, self.show_labels): widget.toggled.connect(self.update_preview)
        self.label_position.currentTextChanged.connect(self.update_preview)
        self.name_edit.textChanged.connect(self.update_preview)
        self.reset_button.clicked.connect(self.reset_defaults)
        try:
            self._install_escape_filter()
            self._initializing = False
            self._identification_changed()
            self._refresh_color_buttons()
            self.update_preview()
        except Exception:
            self._remove_escape_filter()
            raise

    def _color_swatch(self, description):
        button = QtWidgets.QToolButton()
        button.setText("")
        button.setToolTip(description)
        button.setAccessibleName(description)
        button.setFocusPolicy(QtCore.Qt.StrongFocus)
        height = max(self.name_edit.sizeHint().height(), self.form.fontMetrics().lineSpacing())
        button.setFixedSize(max(round(height * 2.4), height), height)
        return button

    def _color_for_target(self, target):
        return {"line": self.line_color, "point": self.point_color,
                "text": self.text_color}[target]

    def _choose_color(self, target):
        if target not in self._color_buttons:
            return
        current = self._color_for_target(target)
        selected = QtWidgets.QColorDialog.getColor(current, self.form, "Escolher cor")
        if selected.isValid():
            self._apply_color(target, selected)

    def _apply_color(self, target, value):
        if target not in self._color_buttons:
            return
        selected = QtGui.QColor(*value) if isinstance(value, tuple) else QtGui.QColor(value)
        if not selected.isValid() or selected == self._color_for_target(target):
            return
        if target == "line":
            self.line_color = selected
        elif target == "point":
            self.point_color = selected
        else:
            self.text_color = selected
        self._refresh_color_buttons()
        self.update_preview()

    def _refresh_color_buttons(self):
        border = self.form.palette().color(QtGui.QPalette.Mid).name()
        for target, button in self._color_buttons.items():
            button.setStyleSheet(
                "QToolButton { background-color: %s; border: 1px solid %s; }"
                % (self._color_for_target(target).name(), border)
            )

    def _identification_changed(self, _value=None):
        x_custom = SCHEMES[self.x_scheme.currentText()] == "Custom"
        y_custom = SCHEMES[self.y_scheme.currentText()] == "Custom"
        self.x_labels_label.setVisible(x_custom)
        self.x_labels.setVisible(x_custom)
        self.y_labels_label.setVisible(y_custom)
        self.y_labels.setVisible(y_custom)
        if not self._initializing:
            self.update_preview()

    def _labels(self, combo, edit, count):
        if SCHEMES[combo.currentText()] != "Custom":
            return None
        return parse_custom_identifiers(edit.text(), count)

    def _values(self):
        x_values, y_values = self.x_editor.values(), self.y_editor.values()
        x_scheme, y_scheme = SCHEMES[self.x_scheme.currentText()], SCHEMES[self.y_scheme.currentText()]
        x_labels = self._labels(self.x_scheme, self.x_labels, len(x_values) + 1)
        y_labels = self._labels(self.y_scheme, self.y_labels, len(y_values) + 1)
        extension_values = {name: spin.value() for name, spin in self.extensions.items()}
        # Validate the exact proposed state before mutating the preview object.
        build_grid_geometry(x_values, y_values, x_identifier_scheme=x_scheme.lower(),
                            y_identifier_scheme=y_scheme.lower(), x_identifiers=x_labels,
                            y_identifiers=y_labels, **{
                                "x_start_extension": extension_values["XStartExtension"],
                                "x_end_extension": extension_values["XEndExtension"],
                                "y_start_extension": extension_values["YStartExtension"],
                                "y_end_extension": extension_values["YEndExtension"],
                            })
        return x_values, y_values, x_scheme, y_scheme, x_labels, y_labels, extension_values

    def update_preview(self, _value=None):
        try:
            x, y, xs, ys, xl, yl, extensions = self._values()
        except Exception as exc:
            self._last_error = str(exc)
            self.validation_message.setText("Entrada inválida: " + str(exc))
            self.validation_message.setStyleSheet("color: #c33")
            self._set_accept_enabled(False)
            return False
        obj = self.grid_object
        obj.Proxy._updating = True
        try:
            obj.DisplayName = self.name_edit.text().strip() or "Grid Estrutural"
            obj.Label = obj.DisplayName
            obj.XSpacings, obj.YSpacings = x, y
            obj.XAxisIdentification, obj.YAxisIdentification = xs, ys
            obj.XAxisLabels, obj.YAxisLabels = xl or [], yl or []
            for name, value in extensions.items():
                setattr(obj, name, value)
        finally:
            obj.Proxy._updating = False
        self.document.recompute()
        view = getattr(obj, "ViewObject", None)
        if view is not None:
            view.LineColor = self.line_color.redF(), self.line_color.greenF(), self.line_color.blueF()
            view.LineWidth = self.line_width.value()
            view.IntersectionPointColor = self.point_color.redF(), self.point_color.greenF(), self.point_color.blueF()
            view.IntersectionPointSize = self.point_size.value()
            view.ShowIntersections = self.show_points.isChecked()
            view.ShowLabels = self.show_labels.isChecked()
            view.LabelPosition = self.label_position.currentText()
            view.LabelOffset = self.label_offset.value()
            if self._font_name:
                view.FontName = self._font_name
            view.FontSize = self.font_size.value()
            view.TextColor = self.text_color.redF(), self.text_color.greenF(), self.text_color.blueF()
            try:
                view.DrawStyle = "Dashdot"
            except Exception:
                pass
        self._last_error = None
        self.validation_message.setText("")
        self._set_accept_enabled(True)
        return True

    def _set_accept_enabled(self, enabled):
        """Best-effort access to FreeCAD's standard OK button after dialog creation."""
        try:
            window = self.form.window()
            button_box = window.findChild(QtWidgets.QDialogButtonBox)
            if button_box is not None:
                button = button_box.button(QtWidgets.QDialogButtonBox.Ok)
                if button is not None:
                    button.setEnabled(bool(enabled))
        except Exception:
            pass

    def isValid(self):
        return self._last_error is None

    def accept(self):
        if not self.update_preview():
            return False
        try:
            self.document.commitTransaction()
            save_grid_appearance_settings(self._appearance_settings())
            return True
        finally:
            self._finish(True)

    def reject(self):
        if self._closed:
            return True
        try:
            name = getattr(self.grid_object, "Name", None)
            if name is not None and callable(getattr(self.document, "removeObject", None)):
                self.document.removeObject(name)
            self.document.abortTransaction()
            if callable(getattr(self.document, "recompute", None)):
                self.document.recompute()
            return True
        finally:
            self._finish(False)

    def _install_escape_filter(self):
        application = QtWidgets.QApplication.instance()
        if application is None:
            raise RuntimeError("QApplication não está disponível para capturar Esc.")
        event_filter = _EscapeEventFilter(self.reject, application)
        try:
            application.installEventFilter(event_filter)
        except Exception:
            event_filter.clear()
            event_filter.deleteLater()
            raise
        self._escape_filter = event_filter
        self._escape_filter_target = application

    def _remove_escape_filter(self):
        event_filter = self._escape_filter
        if event_filter is None:
            return
        target = self._escape_filter_target
        if target is not None:
            try:
                target.removeEventFilter(event_filter)
            except Exception:
                pass
        event_filter.clear()
        try:
            event_filter.deleteLater()
        except Exception:
            pass
        self._escape_filter_target = None
        self._escape_filter = None

    def _finish(self, accepted):
        if self._closed:
            return
        self._closed = True
        self._remove_escape_filter()
        callback, self._on_closed = self._on_closed, None
        self.grid_object = None
        if callback:
            callback(self, accepted)

    def reset_defaults(self):
        self.name_edit.setText("Grid Estrutural")
        self.x_editor.set_values([6000.0, 6000.0])
        self.y_editor.set_values([5000.0, 5000.0])
        self.x_scheme.setCurrentText("Numérica")
        self.y_scheme.setCurrentText("Alfabética")
        for spin in self.extensions.values(): spin.setValue(1000.0)
        defaults = self._factory_appearance
        self.line_color = QtGui.QColor.fromRgbF(*defaults.line_color)
        self.point_color = QtGui.QColor.fromRgbF(*defaults.intersection_color)
        self.text_color = QtGui.QColor.fromRgbF(*defaults.text_color)
        self._font_name = defaults.font_name
        self.line_width.setValue(defaults.line_width)
        self.show_points.setChecked(defaults.show_intersections)
        self.point_size.setValue(defaults.intersection_size)
        self.show_labels.setChecked(defaults.show_labels)
        self.label_position.setCurrentText(defaults.label_position)
        self.label_offset.setValue(defaults.label_offset)
        self.font_size.setValue(defaults.font_size)
        self._refresh_color_buttons()
        self.update_preview()

    def _appearance_settings(self):
        return GridAppearanceSettings(
            (self.line_color.redF(), self.line_color.greenF(), self.line_color.blueF()),
            self.line_width.value(), self.show_points.isChecked(),
            (self.point_color.redF(), self.point_color.greenF(), self.point_color.blueF()),
            self.point_size.value(), self.show_labels.isChecked(),
            self.label_position.currentText(), self.label_offset.value(),
            self._font_name, self.font_size.value(),
            (self.text_color.redF(), self.text_color.greenF(), self.text_color.blueF()),
        )

    def getStandardButtons(self):
        return standard_buttons_value(QtWidgets.QDialogButtonBox)


__all__ = ["GridTaskPanel", "SpacingEditor", "parse_custom_identifiers", "standard_buttons_value"]
