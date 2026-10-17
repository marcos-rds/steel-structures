"""Editor presentations of the TaskPanel controls, never another draft/model."""
from PySide import QtCore, QtWidgets
import math


class _ProfileCard(QtWidgets.QPushButton):
    """Native button surface with wrapping profile text instead of elision."""
    def __init__(self, source):
        super().__init__()
        self.setAutoDefault(False)
        self._text=""
        self._icon=source.icon()
        self._icon_size=source.iconSize()
        row=QtWidgets.QHBoxLayout(self)
        row.setContentsMargins(8,5,8,5)
        self.picture=QtWidgets.QLabel()
        self.caption=QtWidgets.QLabel()
        self.caption.setWordWrap(True)
        for child in (self.picture,self.caption):
            child.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents)
            row.addWidget(child,1 if child is self.caption else 0)
        policy=QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Expanding,QtWidgets.QSizePolicy.Preferred)
        policy.setHeightForWidth(True)
        self.setSizePolicy(policy)

    def setText(self, text):
        self._text=text
        self.caption.setText(text.removesuffix("  ..."))
        self.updateGeometry()

    def text(self):
        return self._text

    def setIcon(self, icon):
        self._icon=icon
        self.picture.setPixmap(icon.pixmap(self._icon_size))

    def icon(self):
        return self._icon

    def sizeHint(self):
        return self.layout().sizeHint()

    def minimumSizeHint(self):
        return self.layout().minimumSize()

    def heightForWidth(self, width):
        return self.layout().totalHeightForWidth(width)


class TrussEditorFields:
    def __init__(self, editor):
        self.editor=editor
        self.panel=editor.panel
        self._syncing=False
        self.controls={}
        self.rows=[]
        self.geometry_page,self.geometry_scroll=editor._add_controls_tab("Geometria")
        self.profiles_page,self.profiles_scroll=editor._add_controls_tab("Perfis")
        self._build_geometry()
        self._build_profiles()
        self.sync()

    @staticmethod
    def _page(page):
        layout=QtWidgets.QVBoxLayout(page)
        layout.setAlignment(QtCore.Qt.AlignTop)
        return layout

    @staticmethod
    def _bounded_content(layout, maximum):
        content=QtWidgets.QWidget()
        content.setMaximumWidth(maximum)
        layout.addWidget(content)
        return content

    @staticmethod
    def _group(layout, title):
        group=QtWidgets.QGroupBox(title)
        form=QtWidgets.QFormLayout(group)
        form.setFieldGrowthPolicy(QtWidgets.QFormLayout.AllNonFixedFieldsGrow)
        form.setRowWrapPolicy(QtWidgets.QFormLayout.WrapLongRows)
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(6)
        layout.addWidget(group)
        return form

    def _mirror(self, name, form=None, label=None, source=None):
        source=source if source is not None else getattr(self.panel,name)
        if isinstance(source,QtWidgets.QComboBox):
            widget=QtWidgets.QComboBox()
            widget.setSizeAdjustPolicy(QtWidgets.QComboBox.AdjustToMinimumContentsLengthWithIcon)
            widget.setMinimumContentsLength(16)
            widget.setMaximumWidth(300)
            widget.currentIndexChanged.connect(lambda _index:self._change(
                source,"setCurrentIndex",source.findData(widget.currentData())))
        elif isinstance(source,QtWidgets.QCheckBox):
            widget=QtWidgets.QCheckBox(source.text())
            widget.toggled.connect(lambda value:self._change(source,"setChecked",value))
        else:
            if isinstance(source,QtWidgets.QDoubleSpinBox):
                suffix=" mm" if getattr(source,"normal",None) is False else source.suffix()
                # An incomplete TaskPanel entry must not prevent opening the
                # editor. Seed from exact storage; sync preserves partial text.
                widget=self.panel._number(QtWidgets.QDoubleSpinBox.value(source),source.minimum(),source.maximum(),suffix)
                widget.setDecimals(source.decimals())
            else:
                widget=QtWidgets.QSpinBox()
            widget.setRange(source.minimum(),source.maximum())
            widget.setSingleStep(source.singleStep())
            widget.setKeyboardTracking(False)
            widget.setMaximumWidth(180)
            widget.valueChanged.connect(lambda value:self._change(source,"setValue",value))
        widget.setObjectName("truss_editor_"+name)
        self.controls[name]=widget
        row_label=QtWidgets.QLabel(label) if label else None
        if form is not None:
            if row_label is None:
                form.addRow(widget)
            else:
                form.addRow(row_label,widget)
        self.rows.append((name,source,widget,row_label))
        return widget

    def _change(self, source, setter, value):
        if self._syncing or self.panel._closed:
            return
        # Existing handlers update the one session and validate it. The panel
        # publishes their result back to this view, including conditional fields.
        getattr(source,setter)(value)
        if setter=="setValue" and not self.panel._valid:
            self.panel._refresh()  # Same-value repair/Escape must clear a partial-input error.

    def _build_geometry(self):
        layout=self._page(self.geometry_page)
        self.geometry_controls=self._bounded_content(layout,1040)
        columns=QtWidgets.QHBoxLayout(self.geometry_controls)
        columns.setContentsMargins(0,0,0,0)
        columns.setSpacing(16)
        left=QtWidgets.QVBoxLayout()
        right=QtWidgets.QVBoxLayout()
        for column in (left,right):
            column.setAlignment(QtCore.Qt.AlignTop)
            column.setSpacing(10)
            columns.addLayout(column,1)
        form=self._group(left,"Geometria")
        for name,label in (("envelope_type","Forma:"),("span","Vão nominal:"),
                           ("height","Altura nominal:"),("apex","Posição da cumeeira:"),
                           ("left_end_height","Altura da extremidade esquerda:"),
                           ("right_end_height","Altura da extremidade direita:"),
                           ("link_end_heights",None)):
            self._mirror(name,form,label)
        form=self._group(right,"Alma e panelização")
        for name,label in (("preset","Padrão da alma:"),("driver","Panelização:"),
                           ("panel_count","Número de painéis:"),("target_spacing","Espaçamento desejado:"),
                           ("target_angle","Ângulo desejado:"),("x_connection","Variante X:")):
            self._mirror(name,form,label)
        source=self.panel.spacing_editor
        try:
            spacings=source.values()
        except ValueError:
            spacings=[QtWidgets.QDoubleSpinBox.value(widget) for widget in source._spins]
        self.spacing_editor=type(source)("Espaçamentos absolutos",spacings,self._spacing_changed)
        self.spacing_editor.summary.hide()
        form.addRow(self.spacing_editor)
        self.complete_span=QtWidgets.QPushButton("Completar vão")
        self.complete_span.clicked.connect(self.panel._complete_span)
        form.addRow(self.complete_span)
        self.restore=QtWidgets.QPushButton("Restaurar padrão")
        self.restore.clicked.connect(self.panel._restore_topology)
        form.addRow(self.restore)
        self.geometry_status=QtWidgets.QLabel()
        self.geometry_status.setWordWrap(True)
        form.addRow(self.geometry_status)
        from .truss_task_widgets import TrussInformationFrame
        self.information_box=TrussInformationFrame()
        self.information_box.setSizePolicy(QtWidgets.QSizePolicy.Preferred,QtWidgets.QSizePolicy.Maximum)
        information_layout=QtWidgets.QVBoxLayout(self.information_box)
        information_layout.setContentsMargins(8,6,8,6)
        title=QtWidgets.QLabel("Informações da treliça")
        font=title.font()
        font.setBold(True)
        title.setFont(font)
        information_layout.addWidget(title)
        information_form=QtWidgets.QFormLayout()
        information_form.setFieldGrowthPolicy(QtWidgets.QFormLayout.AllNonFixedFieldsGrow)
        information_form.setRowWrapPolicy(QtWidgets.QFormLayout.WrapLongRows)
        information_form.setVerticalSpacing(3)
        information_layout.addLayout(information_form)
        self.information_values={}
        for key,label in (("panels","Painéis:"),("spacing","Espaçamento médio efetivo:"),
                          ("nodes","Nós:"),("bars","Barras nominais:")):
            value=QtWidgets.QLabel("—")
            value.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)
            self.information_values[key]=value
            information_form.addRow(label,value)
        separator=QtWidgets.QFrame()
        separator.setFrameShape(QtWidgets.QFrame.HLine)
        information_layout.addWidget(separator)
        from .truss_task_widgets import TrussMassInformation
        self.mass_information=TrussMassInformation()
        self.mass_status=self.mass_information.status
        self.information_values.update(self.mass_information.values)
        information_layout.addWidget(self.mass_information)
        right.addWidget(self.information_box)
        form=self._group(left,"Continuidade dos banzos")
        self._mirror("top_continuity",form,"Banzo superior:")
        self._mirror("bottom_continuity",form,"Banzo inferior:")
        form=self._group(left,"Referência")
        self._mirror("reference_alignment",form,"Linha de referência")
        self.reference_summary=QtWidgets.QLabel()
        self.reference_summary.setWordWrap(True)
        self.reference_summary.setToolTip("Configure modo de criação, fonte, P0, P1 e normal no TaskPanel.")
        form.addRow(self.reference_summary)

    def _spacing_changed(self, *_args):
        if not self._syncing and not self.panel._closed:
            self.panel.spacing_editor.set_values(self.spacing_editor.values())

    def _build_profiles(self):
        layout=self._page(self.profiles_page)
        content=self._bounded_content(layout,760)
        bounded_layout=QtWidgets.QVBoxLayout(content)
        bounded_layout.setContentsMargins(0,0,0,0)
        form=self._group(bounded_layout,"Perfis e composições")
        self.role_buttons={}
        for role,source in self.panel.role_buttons.items():
            button=_ProfileCard(source)
            button.setMinimumHeight(source.minimumHeight())
            button.setAccessibleName(source.accessibleName())
            button.clicked.connect(lambda _checked=False,key=role:self.panel._edit_role(key,parent=self.editor))
            label=QtWidgets.QLabel(self.panel.role_labels[role].text())
            form.addRow(label,button)
            self.role_buttons[role]=(button,label)

    def sync(self):
        self._syncing=True
        try:
            for name,source,widget,label in self.rows:
                blocked=widget.blockSignals(True)
                try:
                    if isinstance(widget,QtWidgets.QComboBox):
                        options=[(source.itemText(i),source.itemData(i)) for i in range(source.count())]
                        if options!=[(widget.itemText(i),widget.itemData(i)) for i in range(widget.count())]:
                            widget.clear()
                            for text,data in options: widget.addItem(text,data)
                        widget.setCurrentIndex(source.currentIndex())
                        for i in range(source.count()):
                            widget.model().item(i).setEnabled(source.model().item(i).isEnabled())
                    elif isinstance(widget,QtWidgets.QCheckBox):
                        widget.setChecked(source.isChecked())
                    else:
                        try:
                            value=source.value()
                        except ValueError:
                            if not widget.hasFocus():
                                from .truss_editor_checkpoint import _numeric_state, _restore_numeric
                                _restore_numeric(widget,_numeric_state(source))
                        else:
                            widget.setValue(value)
                finally:
                    widget.blockSignals(blocked)
                widget.setEnabled(source.isEnabled())
                widget.setVisible(not source.isHidden())
                widget.setToolTip(source.toolTip())
                if label is not None:
                    label.setVisible(not source.isHidden())
                    source_label=getattr(self.panel,name+"_label",None)
                    if source_label is not None: label.setText(source_label.text())
            linked=self.panel.keep_reference_link.isChecked()
            source=self.panel.session.config.get("reference_source")
            self.reference_summary.setText(("Vínculo associativo: "+source if source else
                "Referência associativa sem fonte válida. Corrija a referência no painel.") if linked else "")
            self.reference_summary.setVisible(linked)
            try:
                if self.spacing_editor.values()!=self.panel.spacing_editor.values():
                    self.spacing_editor.set_values(self.panel.spacing_editor.values())
            except ValueError:
                pass  # An incomplete spacing is retained until confirmed or canceled.
            self.spacing_editor.setVisible(not self.panel.spacing_editor.isHidden())
            self.complete_span.setVisible(not self.panel.complete_span.isHidden())
            status="\n".join(text for text in (self.panel.topology_state.text(),
                self.panel.spacing_balance.text() if not self.panel.spacing_balance.isHidden() else "",
                self._sync_information()) if text)
            self.geometry_status.setText(status)
            self.geometry_status.setVisible(bool(status))
            for role,(button,label) in self.role_buttons.items():
                source=self.panel.role_buttons[role]
                button.setText(source.text())
                button.setIcon(source.icon())
                button.setToolTip(source.toolTip())
                button.setVisible(not source.isHidden())
                label.setVisible(not source.isHidden())
        finally:
            self._syncing=False

    def _sync_information(self):
        candidate=self.panel.session.validated_candidate if self.panel._valid else None
        self.information_box.setEnabled(candidate is not None)
        values={key:"—" for key in self.information_values}
        angle_message=""
        if candidate is not None:
            result=candidate.config.get("panelization_result",{})
            count=result.get("panel_count")
            spacing=result.get("spacing")
            if count is not None and count>0:
                values["panels"]=str(count)
            if spacing is not None and math.isfinite(spacing) and spacing>0:
                from .truss_units import length_text
                values["spacing"]=length_text(spacing,self.geometry_page.locale())
            values["nodes"]=str(len(candidate.graph.nodes))
            values["bars"]=str(len(candidate.graph.edges))
            if "angle" in result:
                angle_message=(f"Ângulo médio efetivo {result['angle']:.2f}° "
                    f"({result['minimum_angle']:.2f}–{result['maximum_angle']:.2f}°)")
        self._sync_mass(candidate,values)
        # A calculation/session diagnostic must remain reachable by tooltip.
        self.information_box.setEnabled(candidate is not None or values.get("mass")=="Indisponível")
        for key,label in self.information_values.items():
            label.setText(values[key])
        return angle_message

    def _sync_mass(self, candidate, values):
        from ..trusses.physical_mass import read_physical_mass
        from ..trusses.physical_changes import same_physical_definition, materialization_pending
        from .truss_units import length_text
        session=self.panel.session
        owner=session.owner
        status="Aguardando aplicação"
        tooltip=("Densidade convencional do aço: 7850 kg/m³. Soma dos volumes das peças físicas finais. "
                 "kg/m = peso total dividido pela distância reta entre os apoios P0–P1, em metros. "
                 "O rascunho não gera sólidos para pesagem.")
        unavailable=""
        if not session.valid:
            unavailable=session.conflict_reason or "Sessão indisponível. Reabra a treliça."
        elif owner is not None:
            try:
                if owner.AppliedState == session.applied_state:
                    if materialization_pending(owner):
                        result=None
                    else:
                        result=read_physical_mass(owner)
                    if result is not None and not result.available:
                        unavailable="\n".join(result.diagnostics)
                    elif (result is not None and candidate is not None
                            and same_physical_definition(candidate,session.realized_state["candidate"])):
                        status=""
                        locale=self.geometry_page.locale()
                        values["mass"]=locale.toString(result.mass_kg,"f",2)+" kg"
                        values["linear_mass"]=locale.toString(result.linear_mass_kg_m,"f",2)+" kg/m"
                        tooltip+=("\nDistância física entre apoios P0–P1: "
                                  +length_text(result.support_distance_mm,locale)
                                  +". Vão nominal derivado: "+length_text(result.nominal_span_mm,locale)+".")
                else:
                    unavailable="A treliça foi alterada fora desta sessão. Cancele e reabra o painel."
            except (AttributeError, ValueError, KeyError, TypeError, RuntimeError, ReferenceError) as exc:
                unavailable=str(exc)
        if unavailable:
            values["mass"]=values["linear_mass"]="Indisponível"
            status=""
            tooltip+="\n"+unavailable
        self.mass_status.setText(status)
        self.mass_information.set_pending(bool(status))
        self.mass_status.setToolTip(tooltip)
        for key in ("mass","linear_mass"):
            self.information_values[key].setToolTip(tooltip)
