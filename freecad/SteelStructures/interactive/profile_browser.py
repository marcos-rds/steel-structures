# SPDX-License-Identifier: LGPL-2.1-or-later
"""Reusable native profile catalog browser dialog."""

from __future__ import annotations

from PySide import QtCore, QtGui, QtWidgets

from ..paths import CATALOGS_DIR
from ..profiles import (
    GeometryTemporarilyUnavailableError, ProfileLibrary, ProfileNotFoundError,
    UnsupportedSectionGeometryError,
    build_section_geometry,
)
from ..profiles.presentation import (
    profile_dimension_rows, profile_preview_dimension_rows,
    profile_property_groups, profile_source_groups,
)
from .profile_browser_model import ProfileBrowserModel
from .profile_browser_preview import (
    DIMENSIONS_MODE, NEUTRAL_MODE, PROPERTIES_MODE, SectionPreviewView,
)


def _user_role():
    return getattr(QtCore.Qt, "UserRole", QtCore.Qt.ItemDataRole.UserRole)


def _profile_subtitle(profile, series_name):
    parts = [series_name]
    if profile.catalog.source.source_type == "development_fixture":
        parts.append(profile.catalog.name)
        return " — ".join(parts)
    if profile.geometry_type == "solid_section" and profile.catalog.source.source_type == "normative":
        parts.append(profile.catalog.source.source_name)
        return " — ".join(parts)
    if (profile.geometry_type, profile.geometry_variant) == ("equal_angle", "equal_leg"):
        parts.append("Abas iguais")
    if profile.manufacturer is not None:
        parts.append(profile.manufacturer.name)
    elif profile.catalog.issuer is not None:
        parts.append(profile.catalog.issuer.name)
    return " — ".join(parts)


class ProfileBrowserDialog(QtWidgets.QDialog):
    BROWSE_MODE = "browse"
    SELECT_MODE = "select"

    def __init__(self, parent=None, mode=BROWSE_MODE, library=None,
                 initial_profile_ref=None, is_profile_selectable=None,
                 insertion=None, profile_filter=None):
        super().__init__(parent)
        if mode not in (self.BROWSE_MODE, self.SELECT_MODE):
            raise ValueError("modo inválido para o Catálogo de Perfis")
        self.mode = mode
        self.library = library or ProfileLibrary(CATALOGS_DIR)
        self.model = ProfileBrowserModel(self.library)
        self._is_profile_selectable = is_profile_selectable or (lambda _profile: True)
        self._filter_catalog = profile_filter is not None
        self._profile_filter = profile_filter or (lambda _profile: True)
        self.insertion = insertion if mode == self.SELECT_MODE else None
        self._series = {item.id: item for item in self.library.list_series()}
        self.setWindowTitle("Catálogo de Perfis")
        self.setModal(True)
        self.resize(900, 700)
        self.setMinimumSize(760, 500)
        self._build_ui()
        self._populate_tree()
        self._select_initial_profile(initial_profile_ref)

    def selected_profile_ref(self):
        return self.model.selected_ref

    def selected_profile(self):
        return self.model.selected_profile()

    def _build_ui(self):
        root = QtWidgets.QVBoxLayout(self)
        splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        self.tree = QtWidgets.QTreeWidget()
        self.tree.setHeaderLabel("Categorias / Séries")
        splitter.addWidget(self.tree)

        center = QtWidgets.QWidget()
        center_layout = QtWidgets.QVBoxLayout(center)
        center_layout.setContentsMargins(0, 0, 0, 0)
        self.search = QtWidgets.QLineEdit()
        self.search.setPlaceholderText("Pesquisar perfil...")
        self.search.setClearButtonEnabled(True)
        center_layout.addWidget(self.search)
        self.table = QtWidgets.QTableWidget(0, 1)
        self.table.setHorizontalHeaderLabels(("Perfil",))
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(self.table.fontMetrics().height() + 6)
        header = self.table.horizontalHeader()
        header.setStretchLastSection(True)
        header.setSectionResizeMode(0, QtWidgets.QHeaderView.Stretch)
        center_layout.addWidget(self.table)
        splitter.addWidget(center)

        right = QtWidgets.QWidget()
        right_layout = QtWidgets.QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        self.title = QtWidgets.QLabel("Selecione um perfil")
        title_font = self.title.font()
        title_font.setBold(True)
        title_font.setPointSize(title_font.pointSize() + 2)
        self.title.setFont(title_font)
        right_layout.addWidget(self.title)
        self.subtitle = QtWidgets.QLabel()
        palette = self.subtitle.palette()
        subtitle_color = palette.color(QtGui.QPalette.Text)
        subtitle_color.setAlpha(180)
        palette.setColor(QtGui.QPalette.WindowText, subtitle_color)
        self.subtitle.setPalette(palette)
        right_layout.addWidget(self.subtitle)
        self.preview_stack = QtWidgets.QStackedWidget()
        self.preview = SectionPreviewView()
        self.preview_message = QtWidgets.QLabel()
        self.preview_message.setAlignment(QtCore.Qt.AlignCenter)
        self.preview_message.setWordWrap(True)
        self.preview_stack.addWidget(self.preview)
        self.preview_stack.addWidget(self.preview_message)
        right_layout.addWidget(self.preview_stack)
        self.tabs = QtWidgets.QTabWidget()
        right_layout.addWidget(self.tabs, 1)
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 1)
        splitter.setStretchFactor(2, 3)
        splitter.setSizes((185, 205, 510))
        root.addWidget(splitter)

        buttons = QtWidgets.QDialogButtonBox()
        if self.mode == self.SELECT_MODE:
            buttons.setStandardButtons(QtWidgets.QDialogButtonBox.Cancel | QtWidgets.QDialogButtonBox.Ok)
            buttons.button(QtWidgets.QDialogButtonBox.Ok).setText("Selecionar")
            buttons.accepted.connect(self._accept_selected)
            buttons.rejected.connect(self.reject)
            self.select_button = buttons.button(QtWidgets.QDialogButtonBox.Ok)
            self.select_button.setEnabled(False)
        else:
            buttons.setStandardButtons(QtWidgets.QDialogButtonBox.Close)
            buttons.rejected.connect(self.reject)
            self.select_button = None
        self.selection_message = QtWidgets.QLabel()
        self.selection_message.setWordWrap(True)
        self.selection_message.setVisible(False)
        root.addWidget(self.selection_message)
        root.addWidget(buttons)
        self.tree.currentItemChanged.connect(self._tree_changed)
        self.search.textChanged.connect(self._search_changed)
        self.table.itemSelectionChanged.connect(self._selection_changed)
        self.table.itemDoubleClicked.connect(self._double_clicked)
        self.tabs.currentChanged.connect(self._tab_changed)

    def _populate_tree(self):
        role = _user_role()
        visible = [p for p in self.library.list_profiles() if self._profile_filter(p)]
        for category in self.library.list_categories():
            if self._filter_catalog and not any(p.category_id == category.id for p in visible):
                continue
            root = QtWidgets.QTreeWidgetItem((category.name,))
            root.setData(0, role, (category.id, None))
            self.tree.addTopLevelItem(root)
            for series in self.library.list_series(category.id):
                if self._filter_catalog and not any(p.series_id == series.id and p.category_id == category.id for p in visible):
                    continue
                child = QtWidgets.QTreeWidgetItem((series.name,))
                child.setData(0, role, (category.id, series.id))
                root.addChild(child)
            root.setExpanded(True)

    def _select_initial_series(self):
        root = self.tree.topLevelItem(0)
        self.tree.setCurrentItem(root.child(0) if root and root.childCount() else root)

    def _select_initial_profile(self, initial_ref):
        profile = None
        if initial_ref is not None:
            try:
                profile = self.library.get(initial_ref)
            except (ProfileNotFoundError, TypeError):
                pass
        if profile is None or not self._profile_filter(profile):
            profile = next(
                (item for item in self.library.list_profiles()
                 if self._is_profile_selectable(item) and self._profile_filter(item)),
                None,
            )
        if profile is None:
            self._select_initial_series()
            return
        role = _user_role()
        for root_index in range(self.tree.topLevelItemCount()):
            root = self.tree.topLevelItem(root_index)
            candidates = [root] + [root.child(i) for i in range(root.childCount())]
            for item in candidates:
                if item.data(0, role) == (profile.category_id, profile.series_id):
                    self.tree.setCurrentItem(item)
                    self._select_table_ref(profile.ref)
                    return
        self._select_initial_series()

    def _select_table_ref(self, ref):
        role = _user_role()
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if item.data(role) == ref:
                self.table.selectRow(row)
                self.table.scrollToItem(item)
                return True
        return False

    def _tree_changed(self, current, _previous):
        if current is None:
            return
        category_id, series_id = current.data(0, _user_role())
        self.model.set_filter(category_id, series_id)
        self._populate_table()

    def _search_changed(self, text):
        self.model.set_query(text)
        self._populate_table()

    def _populate_table(self):
        self.table.blockSignals(True)
        self.table.setRowCount(0)
        role = _user_role()
        visible = [p for p in self.model.profiles if self._profile_filter(p)]
        for row, profile in enumerate(visible):
            self.table.insertRow(row)
            designation = QtWidgets.QTableWidgetItem(profile.designation)
            designation.setData(role, profile.ref)
            self.table.setItem(row, 0, designation)
        self.table.blockSignals(False)
        if visible:
            self.table.selectRow(0)
            self._show_profile(visible[0])
        else:
            self.model.selected_ref = None
            self._show_empty("Nenhum perfil encontrado.")

    def _selection_changed(self):
        row = self.table.currentRow()
        item = self.table.item(row, 0) if row >= 0 else None
        if item is not None:
            self._show_profile(self.model.select(item.data(_user_role())))

    def _double_clicked(self, _item):
        if self.mode == self.SELECT_MODE:
            self._accept_selected()

    def _current_profile_is_selectable(self):
        profile = self.selected_profile()
        return profile is not None and self._is_profile_selectable(profile)

    def _accept_selected(self):
        if self.mode == self.SELECT_MODE and self._current_profile_is_selectable():
            self.accept()

    def _clear_layout(self, layout):
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _add_rows(self, form, rows):
        for row in rows:
            label = QtWidgets.QLabel(row.label)
            value = QtWidgets.QLabel(row.value)
            value.setWordWrap(True)
            if row.tooltip:
                label.setToolTip(row.tooltip)
                value.setToolTip(row.tooltip)
            form.addRow(label, value)

    def _rows_widget(self, rows):
        widget = QtWidgets.QWidget()
        form = QtWidgets.QFormLayout(widget)
        form.setFieldGrowthPolicy(QtWidgets.QFormLayout.AllNonFixedFieldsGrow)
        self._add_rows(form, rows)
        return widget

    def _properties_widget(self, groups):
        page = QtWidgets.QWidget()
        layout = QtWidgets.QGridLayout(page)
        positions = {
            "Físicas": (0, 0, 1, 2),
            "Eixo X-X": (1, 0, 1, 1),
            "Eixo Y-Y": (1, 1, 1, 1),
            "Torção / estabilidade": (2, 0, 1, 2),
        }
        next_row = 3
        for group in groups:
            box = QtWidgets.QGroupBox(group.title)
            form = QtWidgets.QFormLayout(box)
            form.setContentsMargins(8, 5, 8, 5)
            form.setVerticalSpacing(2)
            self._add_rows(form, group.rows)
            position = positions.get(group.title)
            if position is None:
                position = (next_row, 0, 1, 2)
                next_row += 1
            layout.addWidget(box, *position)
        layout.setRowStretch(next_row, 1)
        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(page)
        return scroll

    def _source_widget(self, groups):
        page = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(page)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)
        for group in groups:
            box = QtWidgets.QGroupBox(group.title)
            form = QtWidgets.QFormLayout(box)
            form.setContentsMargins(8, 5, 8, 5)
            form.setVerticalSpacing(2)
            form.setFieldGrowthPolicy(QtWidgets.QFormLayout.AllNonFixedFieldsGrow)
            self._add_rows(form, group.rows)
            layout.addWidget(box)
        layout.addStretch(1)
        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(page)
        return scroll

    def _show_profile(self, profile):
        self.title.setText(profile.designation)
        self.subtitle.setText(_profile_subtitle(
            profile, self._series[profile.series_id].name
        ))
        current_tab = max(self.tabs.currentIndex(), 0)
        self.tabs.blockSignals(True)
        self.tabs.clear()
        self.tabs.addTab(self._rows_widget(profile_dimension_rows(profile)), "Dimensões")
        self.tabs.addTab(self._properties_widget(profile_property_groups(profile)), "Propriedades")
        self.tabs.addTab(self._source_widget(profile_source_groups(profile)), "Fonte")
        self.tabs.setCurrentIndex(min(current_tab, self.tabs.count() - 1))
        self.tabs.blockSignals(False)
        self._update_preview(profile)
        if self.select_button is not None:
            selectable = self._is_profile_selectable(profile)
            message = (
                "" if selectable else
                "Criação geométrica ainda não disponível para esta série."
            )
            self.select_button.setEnabled(selectable)
            self.select_button.setToolTip(message)
            self.selection_message.setText(message)
            self.selection_message.setVisible(not selectable)

    def _current_preview_mode(self):
        tabs = getattr(self, "tabs", None)
        index = tabs.currentIndex() if tabs is not None else 0
        return (DIMENSIONS_MODE, PROPERTIES_MODE, NEUTRAL_MODE)[index if 0 <= index <= 2 else 0]

    def _tab_changed(self, _index):
        profile = self.model.selected_profile()
        if profile is not None:
            self._update_preview(profile)

    def _update_preview(self, profile):
        """Switch preview state atomically for supported and unsupported profiles."""
        try:
            geometry = build_section_geometry(profile)
        except GeometryTemporarilyUnavailableError:
            self.preview.clear_geometry()
            self.preview_message.setText(
                "Geometria temporariamente indisponível — "
                "inconsistência entre fontes técnicas Gerdau."
            )
            self.preview_stack.setCurrentWidget(self.preview_message)
        except UnsupportedSectionGeometryError:
            self.preview.clear_geometry()
            self.preview_message.setText(
                "Pré-visualização geométrica ainda não disponível.\n"
                "Os dados técnicos deste perfil estão disponíveis abaixo."
            )
            self.preview_stack.setCurrentWidget(self.preview_message)
        else:
            self.preview.set_geometry(
                geometry, profile_preview_dimension_rows(profile),
                self._current_preview_mode(), getattr(self, "insertion", None),
            )
            self.preview_stack.setCurrentWidget(self.preview)

    def _show_empty(self, message):
        self.title.setText(message)
        self.subtitle.clear()
        self.preview.clear_geometry()
        self.preview_message.setText(message)
        self.preview_stack.setCurrentWidget(self.preview_message)
        self.tabs.clear()
        if self.select_button is not None:
            self.select_button.setEnabled(False)
            self.selection_message.clear()
            self.selection_message.setVisible(False)


def browse_profiles(parent=None):
    dialog = ProfileBrowserDialog(parent=parent, mode=ProfileBrowserDialog.BROWSE_MODE)
    return dialog.exec()


__all__ = ["ProfileBrowserDialog", "browse_profiles"]
