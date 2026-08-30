# SPDX-License-Identifier: LGPL-2.1-or-later
"""Structural profile controls embedded below the native Draft point UI."""

from PySide import QtCore, QtGui, QtWidgets

from .. import profile_catalog
from ..member import ELEMENT_TYPES, INSERTION_OPTIONS
from ..preferences import MemberCreationSettings
from ..profiles import build_section_geometry
from .member_controller import (
    CreationGeometryMode, MemberCreationOptions, compact_profile_designation,
    next_default_label,
)
from .quick_color_menu import QuickColorMenu
from .section_orientation_preview import SectionOrientationPreview


def member_creation_element_types(valid_types=ELEMENT_TYPES):
    """Return model types offered by the generic new-member workflow."""
    return tuple(value for value in valid_types if value != "Pilar")


def orientation_uses_columns(available_width, preview_minimum,
                             controls_minimum, spacing):
    """Choose columns only when both areas fit in the actual useful width."""
    return available_width >= preview_minimum + controls_minimum + spacing


def catalog_button_safe_width(native_width, line_spacing):
    """Return a comfortable DPI-aware width for the catalog text tool button."""
    return max(int(native_width), round(float(line_spacing) * 2.4), 36)


def _color_luminance(color):
    channels = (color.redF(), color.greenF(), color.blueF())
    linear = tuple(
        value / 12.92 if value <= 0.04045
        else ((value + 0.055) / 1.055) ** 2.4
        for value in channels
    )
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def _contrast_ratio(first, second):
    lighter, darker = sorted((_color_luminance(first), _color_luminance(second)), reverse=True)
    return (lighter + 0.05) / (darker + 0.05)


def catalog_button_foreground(palette):
    """Choose the palette foreground with the best contrast against a button."""
    background = palette.color(QtGui.QPalette.Button)
    candidates = (
        palette.color(QtGui.QPalette.ButtonText),
        palette.color(QtGui.QPalette.Text),
        palette.color(QtGui.QPalette.WindowText),
    )
    return max(candidates, key=lambda color: _contrast_ratio(color, background))


class _InsertionMenuButton(QtWidgets.QPushButton):
    """Compact textual mirror of the insertion combo using a standard menu."""

    def __init__(self, combo, parent=None):
        super().__init__(parent)
        self.combo = combo
        self._full_text = ""
        self._menu = QtWidgets.QMenu(self)
        self.setMenu(self._menu)
        self.setMinimumWidth(0)
        self.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        self.combo.currentTextChanged.connect(self.refresh)
        self.refresh()

    def refresh(self, _value=None):
        current = self.combo.currentText()
        self._full_text = "Inserção: %s" % current
        self.setToolTip(self._full_text)
        self.setAccessibleName(self._full_text)
        self._menu.clear()
        for index in range(self.combo.count()):
            label = self.combo.itemText(index)
            action = self._menu.addAction(label)
            action.setCheckable(True)
            action.setChecked(label == current)
            action.triggered.connect(
                lambda _checked=False, value=label: self.combo.setCurrentText(value)
            )
        self._update_elided_text()

    def _update_elided_text(self):
        margin = self.fontMetrics().lineSpacing() * 2
        width = max(self.width() - margin, 1)
        self.setText(self.fontMetrics().elidedText(
            self._full_text, QtCore.Qt.ElideRight, width
        ))

    def resizeEvent(self, event):
        self._update_elided_text()
        super().resizeEvent(event)


class _OrientationPanel(QtWidgets.QGroupBox):
    """Responsive owner of existing preview and orientation controls."""

    def __init__(self, preview, insertion_selector, rotation, color_button, parent=None):
        super().__init__("Orientação da seção", parent)
        self.preview = preview
        self.insertion_selector = insertion_selector
        self.rotation = rotation
        self.color_button = color_button
        self._horizontal = None
        self._grid = QtWidgets.QGridLayout(self)
        self._preview_area = QtWidgets.QWidget()
        self._preview_layout = QtWidgets.QVBoxLayout(self._preview_area)
        self._preview_layout.setContentsMargins(0, 0, 0, 0)
        self._preview_layout.setSpacing(0)
        self._preview_layout.addWidget(preview, 1)
        self._preview_layout.addWidget(insertion_selector)
        self._controls = QtWidgets.QWidget()
        self._controls_grid = QtWidgets.QGridLayout(self._controls)
        self._controls_grid.setContentsMargins(0, 0, 0, 0)
        self._labels = [
            QtWidgets.QLabel("Rotação da seção:"),
            QtWidgets.QLabel("Cor:"),
        ]
        self._widgets = [rotation, color_button]
        self._apply_layout(False)

    @property
    def layout_mode(self):
        return "horizontal" if self._horizontal else "vertical"

    def _spacing(self):
        value = self._grid.horizontalSpacing()
        if value >= 0:
            return value
        return self.style().pixelMetric(QtWidgets.QStyle.PM_LayoutHorizontalSpacing)

    def _use_columns(self):
        margins = self._grid.contentsMargins()
        available = self.width() - margins.left() - margins.right()
        line = self.fontMetrics().lineSpacing()
        preview_minimum = max(self.preview.minimumSizeHint().width(), line * 11)
        controls_minimum = max(self.rotation.minimumSizeHint().width(), line * 7)
        return orientation_uses_columns(
            available, preview_minimum, controls_minimum, self._spacing()
        )

    def _clear_grid(self, layout):
        while layout.count():
            layout.takeAt(0)

    def _apply_layout(self, horizontal):
        horizontal = bool(horizontal)
        if self._horizontal is horizontal:
            return
        self._horizontal = horizontal
        self._clear_grid(self._grid)
        self._clear_grid(self._controls_grid)
        self._grid.setColumnStretch(0, 0)
        self._grid.setColumnStretch(1, 0)
        self._controls_grid.setColumnStretch(0, 0)
        self._controls_grid.setColumnStretch(1, 0)
        for row in range(8):
            self._controls_grid.setRowMinimumHeight(row, 0)
        if horizontal:
            line = self.fontMetrics().lineSpacing()
            self._controls_grid.setVerticalSpacing(max(round(line * 0.22), 2))
            for row, (label, widget) in enumerate(zip(self._labels, self._widgets)):
                base = row * 3
                self._controls_grid.addWidget(label, base, 0)
                self._controls_grid.addWidget(widget, base + 1, 0)
                if row < len(self._widgets) - 1:
                    self._controls_grid.setRowMinimumHeight(
                        base + 2, max(round(line * 0.45), 6)
                    )
            self._grid.addWidget(self._preview_area, 0, 0)
            self._grid.addWidget(self._controls, 0, 1, QtCore.Qt.AlignTop)
            self._grid.setColumnStretch(0, 2)
            self._grid.setColumnStretch(1, 1)
        else:
            self._controls_grid.setVerticalSpacing(self._spacing())
            for row, (label, widget) in enumerate(zip(self._labels, self._widgets)):
                self._controls_grid.addWidget(label, row, 0)
                self._controls_grid.addWidget(widget, row, 1)
            self._controls_grid.setColumnStretch(1, 1)
            self._grid.addWidget(self._preview_area, 0, 0)
            self._grid.addWidget(self._controls, 1, 0)
            self._grid.setColumnStretch(0, 1)

    def resizeEvent(self, event):
        self._apply_layout(self._use_columns())
        super().resizeEvent(event)


class ProfileOptionsWidget(QtWidgets.QGroupBox):
    """Profile-only controls; all point input remains owned by Draft."""

    colorChanged = QtCore.Signal()

    def __init__(self, document, parent=None, element_types=None):
        super().__init__("Opções do perfil", parent)
        self.document = document
        self.setCheckable(True)
        self.setChecked(True)
        self._name_custom = False
        self._programmatic_name = False
        self._color = QtGui.QColor(184, 184, 194)
        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(5)
        identity = QtWidgets.QWidget()
        identity_form = QtWidgets.QFormLayout(identity)
        identity_form.setContentsMargins(0, 0, 0, 0)
        identity_form.setSpacing(4)
        selection = QtWidgets.QWidget()
        selection_form = QtWidgets.QFormLayout(selection)
        selection_form.setContentsMargins(0, 0, 0, 0)
        selection_form.setSpacing(4)
        self.name_edit = QtWidgets.QLineEdit()
        self.name_edit.textEdited.connect(self._mark_custom_name)
        self.element_type = QtWidgets.QComboBox()
        offered_types = member_creation_element_types() if element_types is None else element_types
        self.element_type.addItems(list(offered_types))
        self.element_type.setCurrentText("Membro")
        self.element_type.currentTextChanged.connect(self.refresh_automatic_name)
        self.category = QtWidgets.QComboBox()
        self.category.addItems(profile_catalog.categories())
        self.category.currentTextChanged.connect(self._category_changed)
        self.series = QtWidgets.QComboBox()
        self.series.currentTextChanged.connect(self._series_changed)
        self.profile = QtWidgets.QComboBox()
        self.profile.currentTextChanged.connect(self.refresh_automatic_name)
        self.profile.currentIndexChanged.connect(self._profile_changed)
        self.profile_browser_button = QtWidgets.QToolButton()
        self.profile_browser_button.setObjectName("profileCatalogButton")
        self.profile_browser_button.setText("...")
        self.profile_browser_button.setToolButtonStyle(QtCore.Qt.ToolButtonTextOnly)
        self.profile_browser_button.setToolTip("Abrir Catálogo de Perfis")
        self.profile_browser_button.setAccessibleName("Abrir Catálogo de Perfis")
        self.profile_browser_button.setSizePolicy(
            QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed
        )
        self.profile_browser_button.clicked.connect(self._open_profile_browser)
        self.insertion = QtWidgets.QComboBox()
        self.insertion.addItems(INSERTION_OPTIONS)
        self.insertion.setVisible(False)
        self.insertion_selector = _InsertionMenuButton(self.insertion)
        self.orientation_preview = SectionOrientationPreview()
        self.orientation_preview.referenceSelected.connect(self._select_insertion_reference)
        self.insertion.currentTextChanged.connect(self.orientation_preview.set_insertion)
        self.rotation = QtWidgets.QDoubleSpinBox()
        self.rotation.setRange(-3600.0, 3600.0)
        self.rotation.setDecimals(2)
        self.rotation.setSuffix("°")
        self.rotation.valueChanged.connect(self.orientation_preview.set_rotation)
        self.color_button = QtWidgets.QPushButton("")
        self.color_button.setToolTip("Escolher cor")
        self.color_button.setAccessibleName("Escolher cor")
        self.color_button.setSizePolicy(
            QtWidgets.QSizePolicy.Maximum, QtWidgets.QSizePolicy.Fixed
        )
        swatch_height = self.profile.sizeHint().height()
        self.color_button.setFixedSize(
            max(self.fontMetrics().lineSpacing() * 4, swatch_height), swatch_height
        )
        self.quick_color_menu = QuickColorMenu(self)
        self.quick_color_menu.colorSelected.connect(self._apply_color)
        self.quick_color_menu.moreColorsRequested.connect(self._choose_color)
        self.color_button.clicked.connect(self._show_quick_color_menu)
        self._update_color_button()
        identity_form.addRow("Nome:", self.name_edit)
        identity_form.addRow("Tipo do elemento:", self.element_type)
        selection_form.addRow("Categoria do perfil:", self.category)
        selection_form.addRow("Série do perfil:", self.series)
        profile_row = QtWidgets.QWidget()
        profile_layout = QtWidgets.QHBoxLayout(profile_row)
        profile_layout.setContentsMargins(0, 0, 0, 0)
        profile_layout.addWidget(self.profile, 1)
        button_width = catalog_button_safe_width(
            self.profile_browser_button.sizeHint().width(),
            self.profile_browser_button.fontMetrics().lineSpacing(),
        )
        self.profile_browser_button.setMinimumWidth(button_width)
        self.profile_browser_button.setMaximumWidth(button_width)
        self.profile_browser_button.setMinimumHeight(max(
            self.profile.sizeHint().height(),
            self.profile_browser_button.minimumSizeHint().height(),
        ))
        self.profile_browser_button.ensurePolished()
        catalog_foreground = catalog_button_foreground(
            self.profile_browser_button.palette()
        )
        self.profile_browser_button.setStyleSheet(
            "QToolButton#profileCatalogButton { color: %s; }"
            % catalog_foreground.name()
        )
        profile_layout.addWidget(self.profile_browser_button)
        selection_form.addRow("Perfil:", profile_row)
        self.orientation_panel = _OrientationPanel(
            self.orientation_preview, self.insertion_selector,
            self.rotation, self.color_button
        )
        root.addWidget(identity)
        root.addWidget(selection)
        root.addWidget(self.orientation_panel)
        self._category_changed(self.category.currentText())
        self.refresh_automatic_name()

    def _current_profile_ref(self):
        try:
            return profile_catalog.ref_for_designation(self.profile_designation)
        except KeyError:
            return None

    def _create_profile_browser_dialog(self):
        from .profile_browser import ProfileBrowserDialog
        return ProfileBrowserDialog(
            parent=self,
            mode=ProfileBrowserDialog.SELECT_MODE,
            initial_profile_ref=self._current_profile_ref(),
            is_profile_selectable=profile_catalog.is_creation_profile,
            insertion=self.insertion.currentText(),
        )

    def _open_profile_browser(self):
        dialog = self._create_profile_browser_dialog()
        if dialog.exec() == QtWidgets.QDialog.Accepted:
            selected = dialog.selected_profile_ref()
            if selected is not None:
                self.set_profile_ref(selected)

    def set_profile_ref(self, ref):
        """Apply one Browser selection atomically and notify consumers once."""
        category, series, designation = profile_catalog.selection_for_ref(ref)
        widgets = (self.category, self.series, self.profile)
        previous = [widget.blockSignals(True) for widget in widgets]
        try:
            self.category.setCurrentText(category)
            self.series.clear()
            self.series.addItems(profile_catalog.series_for_category(category))
            self.series.setCurrentText(series)
            self.profile.clear()
            for item in profile_catalog.designations(category, series):
                self.profile.addItem(compact_profile_designation(item), item)
            index = self.profile.findData(designation)
            if index < 0:
                raise ValueError(f"Perfil indisponível para criação: {designation}")
            self.profile.setCurrentIndex(index)
        finally:
            for widget, blocked in zip(widgets, previous):
                widget.blockSignals(blocked)
        self.refresh_automatic_name()
        self.profile.currentIndexChanged.emit(self.profile.currentIndex())

    def _mark_custom_name(self, _text):
        if not self._programmatic_name:
            self._name_custom = True

    def _set_name(self, value):
        self._programmatic_name = True
        try:
            self.name_edit.setText(value)
        finally:
            self._programmatic_name = False

    def _category_changed(self, _text):
        current = self.series.currentText()
        self.series.blockSignals(True)
        self.series.clear()
        self.series.addItems(profile_catalog.series_for_category(self.category.currentText()))
        index = self.series.findText(current)
        if index >= 0:
            self.series.setCurrentIndex(index)
        self.series.blockSignals(False)
        self._series_changed(self.series.currentText())

    def _series_changed(self, _text):
        current = self.profile.currentData()
        self.profile.blockSignals(True)
        self.profile.clear()
        for designation in profile_catalog.designations(self.category.currentText(), self.series.currentText()):
            self.profile.addItem(compact_profile_designation(designation), designation)
        index = self.profile.findData(current)
        if index >= 0:
            self.profile.setCurrentIndex(index)
        self.profile.blockSignals(False)
        self._refresh_insertion_options()
        self.refresh_automatic_name()
        self._update_orientation_preview()

    def _profile_changed(self, _index=None):
        self._refresh_insertion_options()
        self._update_orientation_preview()

    def _select_insertion_reference(self, identifier):
        label = self.orientation_preview.reference_label(identifier)
        self.insertion.setCurrentText(label)

    def _update_orientation_preview(self):
        try:
            profile = profile_catalog.get(self.profile_designation)
            geometry = build_section_geometry(profile.definition)
        except (AttributeError, KeyError, RuntimeError, TypeError, ValueError):
            geometry = None
        self.orientation_preview.set_geometry(
            geometry, self.insertion.currentText(), self.rotation.value()
        )

    def _refresh_insertion_options(self, preferred=None):
        current = preferred or self.insertion.currentText()
        try:
            options = profile_catalog.insertion_options(
                profile_catalog.get(self.profile_designation)
            )
        except KeyError:
            options = tuple(INSERTION_OPTIONS)
        self.insertion.blockSignals(True)
        try:
            self.insertion.clear()
            self.insertion.addItems(options)
            self.insertion.setCurrentText(current if current in options else options[0])
        finally:
            self.insertion.blockSignals(False)
        if hasattr(self, "insertion_selector"):
            self.insertion_selector.refresh()

    @property
    def profile_designation(self):
        value = self.profile.currentData()
        return str(value).strip() if value is not None else ""

    @property
    def rgb(self):
        return self._color.redF(), self._color.greenF(), self._color.blueF()

    def _choose_color(self):
        selected = QtWidgets.QColorDialog.getColor(self._color, self, "Cor do elemento")
        if selected.isValid():
            self._apply_color(selected)

    def _show_quick_color_menu(self):
        self.quick_color_menu.set_current_color(self._color)
        position = self.color_button.mapToGlobal(
            QtCore.QPoint(0, self.color_button.height())
        )
        self.quick_color_menu.popup(position)

    def _apply_color(self, value):
        if isinstance(value, tuple):
            selected = QtGui.QColor(*value)
        else:
            selected = QtGui.QColor(value)
        if not selected.isValid() or selected == self._color:
            return
        self._color = selected
        self._update_color_button()
        self.colorChanged.emit()

    def _update_color_button(self):
        border = self.palette().color(QtGui.QPalette.Mid).name()
        self.color_button.setStyleSheet(
            "QPushButton { background-color: %s; border: 1px solid %s; }"
            % (self._color.name(), border)
        )

    def refresh_automatic_name(self, _value=None):
        if self._name_custom or not self.profile_designation:
            return
        self._set_name(next_default_label(self.document, self.element_type.currentText(), self.profile_designation))

    def creation_options(self, start, end, axis_source=None, link_axis=False,
                         geometry_mode=CreationGeometryMode.INTERACTIVE):
        name = self.name_edit.text().strip() or next_default_label(
            self.document, self.element_type.currentText(), self.profile_designation)
        return MemberCreationOptions(start=start, end=end, designation=self.profile_designation,
            element_type=self.element_type.currentText(), insertion=self.insertion.currentText(),
            rotation=self.rotation.value(), color=self.rgb, display_name=name,
            axis_source=axis_source, link_axis=bool(link_axis),
            geometry_mode=geometry_mode)

    def creation_succeeded(self, next_name):
        self._name_custom = False
        self._set_name(next_name)

    def apply_creation_settings(self, settings):
        """Restore validated reusable values without persisting object names."""
        widgets = (self.element_type, self.category, self.series, self.profile,
                   self.insertion, self.rotation)
        previous = [widget.blockSignals(True) for widget in widgets]
        try:
            self.element_type.setCurrentText(getattr(settings, "element_type", "Pilar"))
            self.category.setCurrentText(settings.category)
            self.series.clear()
            self.series.addItems(profile_catalog.series_for_category(settings.category))
            self.series.setCurrentText(settings.series)
            self.profile.clear()
            for designation in profile_catalog.designations(settings.category, settings.series):
                self.profile.addItem(compact_profile_designation(designation), designation)
            index = self.profile.findData(settings.designation)
            if index >= 0:
                self.profile.setCurrentIndex(index)
            self._refresh_insertion_options(settings.insertion)
            self.rotation.setValue(settings.rotation)
        finally:
            for widget, blocked in zip(widgets, previous):
                widget.blockSignals(blocked)
        red, green, blue = settings.color
        self._color = QtGui.QColor.fromRgbF(red, green, blue)
        self._update_color_button()
        self._name_custom = False
        self.refresh_automatic_name()
        self._update_orientation_preview()

    def creation_settings(self):
        return MemberCreationSettings(
            category=self.category.currentText(), series=self.series.currentText(),
            designation=self.profile_designation,
            insertion=self.insertion.currentText(), rotation=float(self.rotation.value()),
            color=tuple(float(value) for value in self.rgb),
            element_type=self.element_type.currentText(),
        )

    def state(self):
        return {
            "name": self.name_edit.text(), "name_custom": self._name_custom,
            "element_type": self.element_type.currentText(),
            "category": self.category.currentText(), "series": self.series.currentText(),
            "profile": self.profile_designation, "insertion": self.insertion.currentText(),
            "rotation": self.rotation.value(), "color": QtGui.QColor(self._color),
            "expanded": self.isChecked(),
        }

    def restore_state(self, state):
        if not state:
            return
        self.element_type.setCurrentText(state["element_type"])
        self.category.setCurrentText(state["category"])
        self.series.setCurrentText(state["series"])
        index = self.profile.findData(state["profile"])
        if index >= 0:
            self.profile.setCurrentIndex(index)
        self._refresh_insertion_options(state["insertion"])
        self.rotation.setValue(state["rotation"])
        self._color = QtGui.QColor(state["color"])
        self._update_color_button()
        self._name_custom = state["name_custom"]
        self._set_name(state["name"])
        self.setChecked(state["expanded"])
        self._update_orientation_preview()
