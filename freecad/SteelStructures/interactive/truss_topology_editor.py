"""Graph gestures on the Task Panel candidate; no second editable definition."""
from PySide import QtCore, QtGui, QtWidgets
from .truss_preview import TrussPreview2D


class _DiagnosticLabel(QtWidgets.QLabel):
    textChanged=QtCore.Signal(bool)

    def setText(self, text, severity="info"):
        self.severity=severity
        super().setText(text)
        self.textChanged.emit(bool(text))


class TopologyCanvas(TrussPreview2D):
    def __init__(self, editor):
        super().__init__(editor)
        # Help belongs to the dialog status line, not a tooltip over the drawing.
        self.setToolTip("")
        self.editor=editor
        self.setMaximumHeight(16777215)
        self.setMinimumSize(240,7*self.fontMetrics().height())
        policy=QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Expanding,
                                    QtWidgets.QSizePolicy.Preferred)
        policy.setHeightForWidth(True)
        self.setSizePolicy(policy)
        self.setMouseTracking(True)
        self.pending=None
        self.selected=None
        self.rubber=None
        self.snap_marker=None

    def heightForWidth(self, width):
        # Use the model bounds, not sceneRect (which includes viewport-dependent
        # dimension margins). This is layout only, never a candidate rebuild.
        bounds=getattr(self,"_geometry_bounds",QtCore.QRectF(0,0,5,1))
        unit=self.fontMetrics().height()
        useful=max(1,width-4*unit)
        ceiling=min(24*unit,getattr(self,"_layout_height_limit",24*unit))
        return round(max(9*unit,min(ceiling,
                     useful*bounds.height()/max(1.,bounds.width())+2*unit)))

    def sizeHint(self):
        return QtCore.QSize(900,self.heightForWidth(900))

    def set_model(self, model):
        super().set_model(model)
        self.updateGeometry()

    def cancel_gesture(self, notify=True):
        active=self.pending is not None
        self.pending=None
        if self.rubber is not None:
            self.scene().removeItem(self.rubber)
            self.rubber=None
        if self.snap_marker is not None:
            self.scene().removeItem(self.snap_marker)
            self.snap_marker=None
        if notify:
            self.editor.message.setText("Gesto cancelado." if active else "Selecione uma entidade.")
        return active

    def refresh_candidate(self):
        model=self.editor.panel.controller.preview(self.editor.panel.get_config())
        self.set_candidate_model(model)

    def set_candidate_model(self, model):
        self.rubber=None
        self.snap_marker=None
        # Publish reconciliation before another editor action reads panel state.
        from copy import deepcopy
        self.editor.panel.session.config["connection_intents"] = deepcopy(
            self.editor.panel.controller.last_candidate.config.get("connection_intents", {}))
        selected_node=getattr(self.editor,"_connection_node",None)
        previous_model = getattr(self, "_last_model", {})
        refresh_selection = selected_node is not None and any(
            previous_model.get(key) != model.get(key)
            for key in ("nodes", "edges", "connections"))
        if selected_node in model.get("gusset_diagnostic_nodes", ()):
            current = {item["node_key"] for item in model.get("gussets", ())}
            new_node = next((item for item in model.get("nodes", ())
                             if item["key"] == selected_node), None)
            old_node = next((item for item in getattr(self,"_last_model",{}).get("nodes", ())
                             if item["key"] == selected_node), None)
            previous = [item for item in getattr(self,"_last_model",{}).get("gussets", ())
                        if item["node_key"] == selected_node]
            if selected_node not in current and previous and new_node == old_node:
                model["gussets"] = list(model.get("gussets", ()))+previous
        self._last_model=model
        self.set_model(model)
        from ..trusses.validation import connected_components
        graph=self.editor.panel.controller.last_candidate.graph
        if self.pending is not None and self.pending not in {n.key for n in graph.nodes}:
            self.cancel_gesture()
        if selected_node is not None and selected_node not in {n.key for n in graph.nodes}:
            self.editor.select_node(None)
        components=connected_components(graph)
        self.editor.diagnostic_legend.setVisible(len(components)>1)
        isolated=set().union(*components[1:]) if len(components)>1 else set()
        for key in isolated:
            x,y,_=graph.node(key).position_local
            marker=self.scene().addEllipse(-5,-5,10,10,self._pen((200,45,150),2))
            marker.setFlag(QtWidgets.QGraphicsItem.ItemIgnoresTransformations)
            marker.setPos(x,-y)
        for item in self.scene().items():
            if item.data(0)=="edge":
                edge=graph.edge(item.data(1))
                if edge.start_node_key in isolated:
                    item.setPen(self._pen((200,45,150),2.5))
        for connection in model.get("connections", ()):
            if connection["form"]=="GeometricOnly":
                continue
            node=graph.node(connection["node_key"])
            x,y,_=node.position_local
            if connection["form"]=="Direct":
                marker=self.scene().addEllipse(-4,-4,8,8,self._pen((40,120,210),2))
            else:
                marker=self.scene().addRect(-6,-3,12,6,self._pen((120,70,180),2))
            marker.setFlag(QtWidgets.QGraphicsItem.ItemIgnoresTransformations)
            marker.setPos(x,-y)
            marker.setZValue(15)

        self.update_selection_halo()
        if refresh_selection and selected_node in {n.key for n in graph.nodes}:
            self.editor.select_node(selected_node)
        self.editor._refresh_transverse_preview()

    def update_selection_halo(self):
        for item in self.scene().items():
            if item.data(0) == "selection_halo":
                self.scene().removeItem(item)
        key = getattr(self.editor, "_connection_node", None)
        candidate = self.editor.panel.controller.last_candidate
        if candidate is None:
            return
        graph = candidate.graph
        node = next((n for n in graph.nodes if n.key == key), None)
        if node is None:
            return
        marker = self.scene().addEllipse(-9,-9,18,18,self._pen((0,190,215),3))
        marker.setData(0, "selection_halo")
        marker.setFlag(QtWidgets.QGraphicsItem.ItemIgnoresTransformations)
        marker.setPos(node.position_local[0], -node.position_local[1])
        marker.setZValue(20)

    def mousePressEvent(self, event):
        if not self.isEnabled():
            return
        if event.button()!=QtCore.Qt.LeftButton:
            return super().mousePressEvent(event)
        mode=self.editor.current_mode()
        area=QtCore.QRect(event.pos()-QtCore.QPoint(5,5),QtCore.QSize(11,11))
        nearby=[i for i in self.items(area,QtCore.Qt.IntersectsItemShape) if i.data(0) in ("node","edge")]
        # Screen-pixel tolerance remains usable at any fit scale. Nodes win at
        # endpoints, where creating a bar must not accidentally select its edge.
        hit=next((i for i in nearby if i.data(0)=="node"),nearby[0] if nearby else None)
        point=self.mapToScene(event.pos()); local=(point.x(),-point.y(),0.)
        try:
            if mode=="add_node":
                snap=self.snap_at(event.pos())
                if snap and snap["kind"]=="node":
                    raise ValueError("Já existe um nó nessa posição.")
                if not snap and not self.editor.allow_free.isChecked():
                    raise ValueError("Aproxime o cursor de uma barra ou habilite Permitir nó livre.")
                self.editor.panel.apply_topology_edit("add_node",point=snap["point"] if snap else local,
                                                     edge_key=snap["key"] if snap else None)
            elif mode=="move_node" and self.pending is not None:
                snap=self.snap_at(event.pos())
                self.editor.panel.apply_topology_edit("move_node",key=self.pending,point=snap["point"] if snap else local)
                self.cancel_gesture()
            elif hit is None:
                return
            elif mode=="select":
                self.selected=hit.data(1)
                self.editor.message.setText("Nó selecionado." if hit.data(0)=="node" else "Barra selecionada.")
                from .truss_preview import ROLE_COLORS
                roles={e.key:e.role for e in self.editor.panel.controller.last_candidate.graph.edges}
                for item in self.scene().items():
                    if item.data(0)=="edge":
                        item.setPen(self._pen(ROLE_COLORS.get(roles[item.data(1)],(75,75,75)),1.6))
                if hit.data(0)=="edge":
                    hit.setPen(self._pen((220,135,20),3))
                    self.editor.select_node(None)
                else:
                    self.editor.select_node(hit.data(1))
                    incident=set(self.editor.panel.controller.last_candidate.graph.incidence[hit.data(1)])
                    for item in self.scene().items():
                        if item.data(0)=="edge" and item.data(1) in incident:
                            item.setPen(self._pen((220,135,20),3))
            elif mode=="remove" and hit.data(0)=="edge":
                self.editor.panel.apply_topology_edit("remove_edge",key=hit.data(1))
            elif mode=="remove_node" and hit.data(0)=="node":
                self.editor.panel.apply_topology_edit("remove_node",key=hit.data(1))
            elif mode=="create" and hit.data(0)=="node":
                if self.pending is None:
                    self.pending=hit.data(1)
                    self.editor.message.setText("Selecione o segundo nó; Esc cancela o gesto.")
                    return
                self.editor.panel.apply_topology_edit("add_edge",start=self.pending,end=hit.data(1))
                self.cancel_gesture()
            elif mode=="move_node" and hit.data(0)=="node":
                node=self.editor.panel.controller.last_candidate.graph.node(hit.data(1))
                if node.classification!="INTERNAL_NODE":
                    raise ValueError("Nós dos banzos são controlados pela geometria/panelização.")
                self.pending=node.key
                self.editor.message.setText("Clique na nova posição; Esc cancela o gesto.")
                return
            else:
                return
            if mode!="select":
                self.refresh_candidate()
                self.editor.message.setText("Rascunho Custom atualizado; Aplicar ou OK no painel confirma as alterações.")
        except (ValueError,KeyError,StopIteration) as exc:
            self.editor.message.setText(str(exc),"error")

    def snap_at(self, position):
        if not self.isEnabled() or self.editor.panel.controller.last_candidate is None:
            return None
        from ..trusses.editor_snapping import snap_target
        p=self.mapToScene(position)
        q=self.mapToScene(position+QtCore.QPoint(8,0))
        tolerance=((q.x()-p.x())**2+(q.y()-p.y())**2)**.5
        return snap_target(self.editor.panel.controller.last_candidate.graph,
                           (p.x(),-p.y(),0.),tolerance, self.pending if self.editor.current_mode()=="move_node" else None)

    def add_snap_marker(self,kind):
        pen=self._pen((20,180,130),2)
        if kind=="midpoint":
            return self.scene().addPolygon(QtGui.QPolygonF([
                QtCore.QPointF(0,-5),QtCore.QPointF(5,4),QtCore.QPointF(-5,4)]),pen)
        if kind=="edge":
            return self.scene().addRect(-4,-4,8,8,pen)
        return self.scene().addEllipse(-5,-5,10,10,pen)

    def mouseMoveEvent(self,event):
        if not self.isEnabled():
            return
        snap=self.snap_at(event.pos())
        if self.snap_marker is not None:
            self.scene().removeItem(self.snap_marker)
            self.snap_marker=None
        if snap:
            x,y,_=snap["point"]
            self.snap_marker=self.add_snap_marker(snap["kind"])
            self.snap_marker.setFlag(QtWidgets.QGraphicsItem.ItemIgnoresTransformations)
            self.snap_marker.setPos(x,-y)
            self.snap_marker.setZValue(20)
        if self.pending is not None and self.editor.current_mode() in ("create","move_node"):
            graph=self.editor.panel.controller.last_candidate.graph
            a=graph.node(self.pending).position_local
            p=QtCore.QPointF(snap["point"][0],-snap["point"][1]) if snap else self.mapToScene(event.pos())
            if self.rubber is None:
                self.rubber=self.scene().addLine(a[0],-a[1],p.x(),p.y(),self._pen((220,135,20),1.5,True))
            else:
                self.rubber.setLine(a[0],-a[1],p.x(),p.y())
        super().mouseMoveEvent(event)

    def leaveEvent(self,event):
        if self.snap_marker is not None:
            self.scene().removeItem(self.snap_marker)
            self.snap_marker=None
        super().leaveEvent(event)


class TopologyEditor(QtWidgets.QDialog):
    """Expanded view of the panel's session; the panel still owns transactions."""

    @property
    def session(self):
        return self.panel.session

    def __init__(self,panel):
        super().__init__(panel.form)
        self.panel=panel
        self._panel_completion=None
        self._submitting=False
        self._qt_alive=True
        self.destroyed.connect(lambda *_:setattr(self,"_qt_alive",False))
        self.setWindowTitle("Editor de Treliças")
        self.setSizeGripEnabled(True)
        root=QtWidgets.QVBoxLayout(self)
        root.setSpacing(4)
        self.canvas=TopologyCanvas(self)
        self._build_toolbar(root)
        root.addWidget(self.canvas)
        self.message=_DiagnosticLabel("")
        self.message.setWordWrap(True)
        self.message.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)
        self.message_scroll=QtWidgets.QScrollArea()
        self.message_scroll.setWidgetResizable(True)
        self.message_scroll.setSizeAdjustPolicy(QtWidgets.QAbstractScrollArea.AdjustToContents)
        self.message_scroll.setMaximumHeight(6*self.fontMetrics().height())
        self.message_scroll.setSizePolicy(QtWidgets.QSizePolicy.Expanding,
                                          QtWidgets.QSizePolicy.Maximum)
        self.message_scroll.setFrameShape(QtWidgets.QFrame.NoFrame)
        self.message_scroll.setWidget(self.message)
        self.message_toggle=QtWidgets.QToolButton()
        self.message_toggle.setToolButtonStyle(QtCore.Qt.ToolButtonTextBesideIcon)
        self.message_toggle.setCheckable(True)
        self.message_toggle.setArrowType(QtCore.Qt.RightArrow)
        self.message_toggle.toggled.connect(self._toggle_messages)
        self.message.textChanged.connect(self._update_message_area)
        self.message_toggle.hide()
        self.message_scroll.setVisible(False)
        root.addWidget(self.message_toggle)
        root.addWidget(self.message_scroll)
        self.diagnostic_legend=QtWidgets.QLabel("Componentes separados do maior componente destacados em magenta.")
        self.diagnostic_legend.setWordWrap(True)
        root.addWidget(self.diagnostic_legend)
        self.tabs=QtWidgets.QTabWidget(self)
        root.addWidget(self.tabs,1)
        self.connections_page,self.connections_scroll=self._add_controls_tab("Ligações")
        connections_layout=QtWidgets.QVBoxLayout(self.connections_page)
        connections_layout.setAlignment(QtCore.Qt.AlignTop)
        self.connection_box=QtWidgets.QGroupBox("Ligação do nó")
        connection_row=QtWidgets.QHBoxLayout(self.connection_box)
        controls=QtWidgets.QWidget(self.connection_box)
        controls.setMaximumWidth(500)
        form=QtWidgets.QFormLayout(controls)
        connection_row.addWidget(controls, 1, QtCore.Qt.AlignTop)
        self.connection_type=QtWidgets.QComboBox()
        for label,value in (("Sem ajuste entre barras","GeometricOnly"),("Ligação direta","Direct"),("Chapa de ligação","Gusset")):
            self.connection_type.addItem(label,value)
        self._connection_tooltips = {
            "GeometricOnly": "Não adiciona recortes entre participantes; ajustes ao banzo continuam ativos.",
            "Direct": "Cria contato físico entre barras por meia-esquadria ou prioridade.",
            "Gusset": "Gera uma chapa preliminar paramétrica; durante a edição usa preview sem objeto temporário."}
        for index in range(self.connection_type.count()):
            self.connection_type.setItemData(index, self._connection_tooltips[
                self.connection_type.itemData(index)], QtCore.Qt.ToolTipRole)
        self.fastening=QtWidgets.QComboBox()
        for label,value in (("Não especificada","Unspecified"),("Soldada","Welded"),
                            ("Parafusada","Bolted"),("Mista","Mixed")):
            self.fastening.addItem(label,value)
        self.direct_policy=QtWidgets.QComboBox()
        for label,value in (("Meia-esquadria equilibrada","BalancedMiter"),("Prioridade","Priority")):
            self.direct_policy.addItem(label,value)
        self.priority_member=QtWidgets.QComboBox()
        for label,value in (("Automática","Automatic"),("Participante A","ParticipantA"),
                            ("Participante B","ParticipantB")):
            self.priority_member.addItem(label,value)
        self.gusset_plate=self._length_spin()
        self.gusset_normal=self._length_spin()
        self.gusset_axial=self._length_spin()
        self.gusset_margin=self._length_spin()
        self.gusset_overlap=self._length_spin()
        self.gusset_region=QtWidgets.QComboBox()
        self.gusset_region.addItem("Automática", "")
        self.gusset_region.setToolTip(
            "Escolhe uma região física disponível no corte transversal.")
        self.gusset_position=QtWidgets.QComboBox()
        self.gusset_position.addItem("Resolvida automaticamente", "")
        self.gusset_position.setEnabled(False)
        self.gusset_position.setToolTip(
            "Escolhe uma posição válida dentro da região selecionada.")
        self.participants=QtWidgets.QLabel("Selecione um nó.")
        self.participants.setWordWrap(True)
        form.addRow("Tipo:",self.connection_type)
        form.addRow("Fixação:",self.fastening)
        form.addRow("Tipo de encontro:",self.direct_policy)
        form.addRow("Prioridade:",self.priority_member)
        form.addRow("Espessura:",self.gusset_plate)
        form.addRow("Folga normal:",self.gusset_normal)
        form.addRow("Folga axial:",self.gusset_axial)
        form.addRow("Margem de borda:",self.gusset_margin)
        form.addRow("Sobreposição nos membros:",self.gusset_overlap)
        self.gusset_plate.setToolTip("Espessura da futura chapa, em mm.")
        self.gusset_normal.setToolTip("Distância adicional perpendicular ao plano da futura chapa, em mm.")
        self.gusset_axial.setToolTip("Recuo adicional ao longo do eixo da barra, em mm; separado do gap axial.")
        self.gusset_margin.setToolTip("Margem externa aplicada ao contorno físico dos participantes, em mm.")
        self.gusset_overlap.setToolTip("Comprimento coberto pela chapa a partir do nó, em mm.")
        form.addRow("Participantes:",self.participants)
        self._connection_form = form
        from .gusset_section_preview import GussetSectionPreview
        self.transverse_preview = GussetSectionPreview(self.connection_box)
        self._transverse_form = self.transverse_preview.add_position_controls(
            self.gusset_region, self.gusset_position)
        connection_row.addWidget(self.transverse_preview, 1, QtCore.Qt.AlignTop)
        connections_layout.addWidget(self.connection_box)
        self.connection_box.setEnabled(False)
        self._connection_node=None
        for widget in (self.connection_type,self.fastening,self.direct_policy,self.priority_member,
                       self.gusset_position):
            widget.currentIndexChanged.connect(self._connection_changed)
        self.gusset_region.currentIndexChanged.connect(self._gusset_region_changed)
        for widget in (self.gusset_plate,self.gusset_normal,self.gusset_axial,
                       self.gusset_margin,self.gusset_overlap):
            widget.valueChanged.connect(self._connection_changed)
        buttons=QtWidgets.QWidget()
        actions=QtWidgets.QHBoxLayout(buttons)
        actions.setContentsMargins(0,0,0,0)
        actions.addStretch(1)
        self.action_buttons=buttons
        self.cancel_button=QtWidgets.QPushButton("Cancelar")
        self.apply_button=QtWidgets.QPushButton("Aplicar")
        self.ok_button=QtWidgets.QPushButton("OK")
        for button,action in ((self.cancel_button,"cancel"),(self.apply_button,"apply"),(self.ok_button,"ok")):
            actions.addWidget(button)
            if action=="cancel":
                actions.addSpacing(max(8,self.fontMetrics().horizontalAdvance(" ")*2))
            button.setAutoDefault(False)
            button.setDefault(False)
            button.clicked.connect(lambda _checked=False,key=action:self._submit_action(key))
        root.addWidget(buttons)
        self.mode_group.buttonClicked.connect(lambda *_:self.canvas.cancel_gesture())
        self.tabs.currentChanged.connect(self._tab_changed)
        from .truss_editor_fields import TrussEditorFields
        self.fields=TrussEditorFields(self)
        for index,page in enumerate((self.fields.geometry_scroll,
                                     self.fields.profiles_scroll,self.connections_scroll)):
            self.tabs.tabBar().moveTab(self.tabs.indexOf(page),index)
        self.tabs.setCurrentWidget(self.fields.geometry_scroll)
        self.sync_from_panel()
        available=self.screen().availableGeometry()
        width=min(1200,available.width()-40)
        margins=root.contentsMargins()
        chrome=(margins.top()+margins.bottom()+(root.count()-1)*root.spacing()+self.topology_toolbar.sizeHint().height()
                +self.tabs.tabBar().sizeHint().height()+buttons.sizeHint().height())
        controls_height=max(page.sizeHint().height() for page in (
            self.fields.geometry_page,self.fields.profiles_page,self.connections_page))
        height=(self.canvas.heightForWidth(width-margins.left()-margins.right())
                +controls_height
                +2*self.fontMetrics().height()+chrome)
        self.resize(width,min(height,940,available.height()-60))

    def _build_toolbar(self, root):
        from ..paths import ICONS_DIR
        self.topology_toolbar=QtWidgets.QWidget(self)
        row=QtWidgets.QHBoxLayout(self.topology_toolbar)
        row.setContentsMargins(0,0,0,0)
        row.setSpacing(3)
        root.addWidget(self.topology_toolbar)

        def tool(label, icon):
            button=QtWidgets.QToolButton()
            button.setText(label)
            button.setAccessibleName(label)
            button.setToolTip(label)
            button.setIcon(QtGui.QIcon(str(ICONS_DIR/icon)))
            button.setIconSize(QtCore.QSize(24,24))
            button.setToolButtonStyle(QtCore.Qt.ToolButtonIconOnly)
            # The dialog keeps its Task View parent for lifecycle. OpenDark's
            # QSint content-descendant rules otherwise style these as wide push
            # buttons and override generic :checked. Override only this button.
            button.setStyleSheet("""
                QToolButton { margin: 0; padding: 3px; border: 1px solid transparent;
                    border-radius: 5px; background: transparent;
                    min-width: 24px; max-width: 24px; min-height: 24px; max-height: 24px; }
                QToolButton:hover { background: rgba(76, 150, 183, 20); border-color: rgba(76, 150, 183, 90); }
                QToolButton:focus { border-color: #4c96b7; }
                QToolButton:pressed { background: rgba(76, 150, 183, 55); border-color: #4c96b7; }
                QToolButton:checked, QToolButton:checked:hover, QToolButton:checked:focus {
                    background: rgba(76, 150, 183, 32); border-color: #4c96b7; }
                QToolButton:checked:hover { background: rgba(76, 150, 183, 48); }
                QToolButton:disabled { background: transparent; border-color: transparent; }
            """)
            button.setFixedSize(32,32)
            row.addWidget(button)
            return button

        def separator():
            line=QtWidgets.QFrame()
            line.setFrameShape(QtWidgets.QFrame.VLine)
            row.addWidget(line)

        self.mode_group=QtWidgets.QButtonGroup(self)
        self.mode_group.setExclusive(True)
        self.mode_buttons={}
        for label,key,icon in (("Selecionar","select","TrussSelect.svg"),
                ("Criar barra","create","TrussBarAdd.svg"),("Remover barra","remove","TrussBarRemove.svg"),
                ("Adicionar nó","add_node","TrussNodeAdd.svg"),("Remover nó","remove_node","TrussNodeRemove.svg"),
                ("Mover nó","move_node","TrussNodeMove.svg")):
            if key in ("create","add_node"): separator()
            button=tool(label,icon)
            button.setCheckable(True)
            button.setChecked(key=="select")
            self.mode_group.addButton(button)
            self.mode_buttons[key]=button
        separator()
        self.invert_button=tool("Inverter alma","TrussWebInvert.svg")
        self.invert_button.clicked.connect(lambda *_:self.transform_web("mirror"))
        self.copy_button=tool("Copiar espelhado","TrussWebMirrorCopy.svg")
        self.copy_button.setObjectName("trussMirrorCopy")
        self.copy_button.setStyleSheet(self.copy_button.styleSheet()+"""
            QToolButton#trussMirrorCopy { min-width: 36px; max-width: 36px; padding-right: 3px; }
            QToolButton::menu-button { width: 10px; margin: 0; padding: 0;
                subcontrol-origin: padding; subcontrol-position: right center; }
        """)
        self.copy_button.setFixedSize(44,32)
        self.copy_button.setPopupMode(QtWidgets.QToolButton.MenuButtonPopup)
        self.copy_button.clicked.connect(lambda *_:self.transform_web("copy_mirrored"))
        self.copy_direction="LeftToRight"
        self.copy_actions={}
        copy_menu=QtWidgets.QMenu(self.copy_button)
        for label,direction in (("Esquerda → Direita","LeftToRight"),("Direita → Esquerda","RightToLeft")):
            action=copy_menu.addAction(label)
            action.setCheckable(True)
            action.setChecked(direction==self.copy_direction)
            action.triggered.connect(lambda _checked=False,key=direction:self.copy_in_direction(key))
            self.copy_actions[direction]=action
        self.copy_button.setMenu(copy_menu)
        self.copy_button.setToolTip("Copiar espelhado: Esquerda → Direita")
        separator()
        self.allow_free=QtWidgets.QCheckBox("Permitir nó livre")
        self.allow_free.setToolTip("Permite adicionar nós fora das barras; não altera a ferramenta ativa.")
        row.addWidget(self.allow_free)
        row.addStretch(1)

    def _toggle_messages(self, expanded):
        self.message_toggle.setArrowType(QtCore.Qt.DownArrow if expanded else QtCore.Qt.RightArrow)
        self.message_scroll.setVisible(expanded and bool(self.message.text()))

    def _update_message_area(self, present):
        text=self.message.text()
        invalid=not self.panel._valid
        error=invalid or self.message.severity=="error"
        warning=self.message.severity=="warning"
        collapsible=error or warning or "\n" in text or len(text)>110
        self.message_scroll.setMaximumHeight((6 if collapsible else 1)*self.fontMetrics().height()+8)
        self.message_toggle.setVisible(present and collapsible)
        count=len(text.splitlines())
        self.message_toggle.setText("Entrada inválida — detalhes" if invalid else
            "Erro — detalhes" if error else
            ("Alertas e diagnósticos" if warning else "Mensagens")+f" ({count})")
        self.message_toggle.setIcon(self.style().standardIcon(
            QtWidgets.QStyle.SP_MessageBoxCritical if error else
            QtWidgets.QStyle.SP_MessageBoxWarning if warning else QtWidgets.QStyle.SP_MessageBoxInformation))
        self.message_toggle.setToolTip(text)
        if error and present:
            self.message_toggle.setChecked(True)
        self.message_scroll.setVisible(present and (not collapsible or self.message_toggle.isChecked()))

    def _add_controls_tab(self, label):
        scroll=QtWidgets.QScrollArea(self.tabs)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QtWidgets.QFrame.NoFrame)
        scroll.setMinimumHeight(max(104,6*self.fontMetrics().height())
                                +self.style().pixelMetric(QtWidgets.QStyle.PM_ScrollBarExtent))
        page=QtWidgets.QWidget(scroll)
        scroll.setWidget(page)
        self.tabs.addTab(scroll,label)
        return page,scroll

    def resizeEvent(self, event):
        super().resizeEvent(event)
        canvas=getattr(self,"canvas",None)
        if canvas is not None:
            # A tall truss must still leave usable controls on a short screen.
            limit=round(self.contentsRect().height()*.45)
            if getattr(canvas,"_layout_height_limit",None)!=limit:
                canvas._layout_height_limit=limit
                canvas.updateGeometry()

    def _tab_changed(self, *_args):
        # Navigation cancels only the gesture, never the selected entity or draft.
        self.canvas.cancel_gesture(notify=False)
        self.mode_buttons["select"].setChecked(True)
        if not hasattr(self,"_connection_node"):
            return  # Tabs are also ordered during construction.
        if not self.panel._valid:
            self.message.setText(self.panel.message.text(),"error")
        elif self._connection_node is not None:
            self.message.setText("\n".join(self._node_messages()),"warning")
        else:
            self.message.setText(self.panel.message.text(),"warning")

    def sync_from_panel(self):
        """Present the panel's validated result, without building another model."""
        self.fields.sync()
        valid=self.panel._valid
        for button in (self.apply_button,self.ok_button):
            button.setEnabled(valid and not self._submitting)
        self.canvas.setEnabled(valid)
        self.topology_toolbar.setEnabled(valid)
        self.connections_scroll.setEnabled(valid)
        if valid:
            self.canvas.set_candidate_model(self.panel._last_preview_model)
            self.connection_box.setEnabled(self._connection_node is not None)
            if self._connection_node is None:
                self.message.setText(self.panel.message.text(),"warning")
        else:
            self.diagnostic_legend.hide()
            self.message.setText(self.panel.message.text(),"error")
            self.transverse_preview.set_preview(caption="Prévia desatualizada; corrija os parâmetros do rascunho.")

    def exec(self):
        """Close only this modal view when the session document loses activation."""
        import FreeCAD as App
        self._panel_completion=None
        self._capture_checkpoint()
        editor=self
        alive=[True]
        def destroyed(*_args):
            alive[0]=False

        self.destroyed.connect(destroyed)

        class ActivationObserver:
            def slotActivateDocument(self,document):
                if alive[0] and document is not editor.panel.document:
                    editor.reject()

        observer=ActivationObserver()
        App.addDocumentObserver(observer)
        try:
            return super().exec()
        finally:
            App.removeDocumentObserver(observer)

    def reject(self):
        # A document switch can close this modal while AssemblyEditor (or its
        # catalog dialog) runs a nested exec. Release children before this view.
        for dialog in reversed(self.findChildren(QtWidgets.QDialog)):
            dialog.reject()
        self._panel_completion="cancel"
        super().reject()

    def _capture_checkpoint(self):
        from .truss_editor_checkpoint import TrussEditorCheckpoint
        self._checkpoint=TrussEditorCheckpoint(self.panel,self)

    def _commit_inputs(self):
        # Qt button.click() need not move focus. Confirm pending numeric text
        # through the existing widget handlers before reading the shared draft.
        for widget in self.findChildren(QtWidgets.QDoubleSpinBox):
            if not self._qt_alive or self.panel._closed:
                return False
            if widget.window() is not self:
                continue
            commit=getattr(widget,"_commit",None)
            if commit is not None:
                if not commit():
                    self.panel._show_error("Conclua ou corrija o comprimento em edição antes de aplicar.")
                    return False
            else:
                widget.interpretText()
        return True

    def _submit_action(self, action):
        if self._submitting or self.panel._closed:
            return
        if action=="cancel":
            self.reject()
            return
        self._submitting=True
        self.action_buttons.setEnabled(False)
        try:
            self.canvas.cancel_gesture(notify=False)
            if not self._commit_inputs():
                return
            if not self.panel.apply():
                if self._qt_alive and not self.panel._closed and not self.panel._valid and self.session.valid:
                    # A transaction can fail despite a valid draft. Revalidate
                    # without applying so the user can retry; retain the actual
                    # application error in the modal diagnostic area.
                    failure=self.panel.message.text()
                    self.panel._refresh()
                    self.message.setText(failure,"error")
                return
            if not self._qt_alive or self.panel._closed:
                return
            self._capture_checkpoint()
            self.sync_from_panel()
            if action=="ok":
                self._panel_completion="ok"
                for dialog in reversed(self.findChildren(QtWidgets.QDialog)):
                    dialog.reject()
                super().accept()
        finally:
            self._submitting=False
            if self._qt_alive and not self.panel._closed:
                self.action_buttons.setEnabled(True)
                for button in (self.apply_button,self.ok_button):
                    button.setEnabled(self.panel._valid)

    @staticmethod
    def _length_spin():
        from .truss_length_spinbox import TrussLengthSpinBox
        widget=TrussLengthSpinBox()
        widget.setRange(0.,100000.)
        return widget

    def select_node(self,node_key):
        if node_key is not None and not self.canvas.isEnabled():
            return
        self._connection_node=node_key
        self._refresh_transverse_preview()
        if hasattr(self, "canvas"):
            self.canvas.update_selection_halo()
        self.connection_box.setEnabled(node_key is not None)
        if node_key is None:
            self.participants.setText("Selecione um nó.")
            self.message.setText("")
            return
        # Node-specific diagnostics are rebuilt from the semantic candidate;
        # never leave the previous node's footer text visible.
        self.message.setText("")
        from ..trusses.connections import default_intent, intent_from_data
        configured=self.panel.get_config().get("connection_intents",{}).get(node_key)
        intent=intent_from_data(node_key,configured or default_intent(node_key))
        widgets=(self.connection_type,self.fastening,self.direct_policy,self.priority_member,
                 self.gusset_plate,self.gusset_normal,self.gusset_axial,
                 self.gusset_margin,self.gusset_overlap,
                 self.gusset_region,self.gusset_position)
        blocked=[widget.blockSignals(True) for widget in widgets]
        self.connection_type.setCurrentIndex(self.connection_type.findData(intent.form.value))
        self.fastening.setCurrentIndex(self.fastening.findData(intent.fastening.value))
        self.direct_policy.setCurrentIndex(self.direct_policy.findData(intent.direct_policy.value))
        self.priority_member.setCurrentIndex(self.priority_member.findData(intent.priority_member.value))
        preview = self._gusset_preview_options()
        placement = intent.gusset.transverse_placement
        if not placement and (intent.gusset.attachment_mode.value != "Auto"
                              or intent.gusset.side.value != "Center"):
            placement = preview.get("resolved_transverse_placement", "")
        placement_invalid = self._populate_gusset_options(placement)
        for widget,value in ((self.gusset_plate,intent.gusset.plate_thickness),
                             (self.gusset_normal,intent.gusset.normal_clearance),
                             (self.gusset_axial,intent.gusset.axial_clearance),
                             (self.gusset_margin,intent.gusset.edge_margin),
                             (self.gusset_overlap,intent.gusset.member_overlap)):
            widget.setMaximum(max(widget.maximum(),value))
            widget.setValue(value)
            widget._connection_exact_value=value
            widget._connection_display_value=widget.value()
        for widget,state in zip(widgets,blocked): widget.blockSignals(state)
        if placement_invalid and configured:
            normalized = dict(configured)
            normalized_gusset = dict(normalized.get("gusset", {}))
            normalized_gusset["transverse_placement"] = ""
            normalized_gusset["chord_contact"] = "TrussInterior"
            normalized["gusset"] = normalized_gusset
            self.panel.set_connection_intent(node_key, normalized)
            self.canvas.refresh_candidate()
        from ..trusses.connections import connection_participants
        values=connection_participants(self.panel.controller.last_candidate,node_key)
        from ..connections.presentation import participant_names
        from ..connections.resolver import WEB_ROLES, priority_options
        names = participant_names(values, self.panel.controller.last_candidate.config["span"])
        self.participants.setText(", ".join(names[p.run_key] for p in values))
        webs = [p for p in values if p.role in WEB_ROLES]
        self._priority_runs = [p.run_key for p in priority_options(values)]
        blocked = self.priority_member.blockSignals(True)
        self.priority_member.clear()
        self.priority_member.addItem("Automática", "Automatic")
        for key in self._priority_runs:
            self.priority_member.addItem(names[key], key)
        priority_key = intent.priority_run_key
        if not priority_key and intent.priority_member.value != "Automatic":
            legacy = intent.participant_run_keys or tuple(self._priority_runs)
            index = 0 if intent.priority_member.value == "ParticipantA" else 1
            priority_key = legacy[index] if len(legacy) > index else ""
        priority_key = next((p.run_key for p in values if priority_key in p.physical_run_keys), priority_key)
        self.priority_member.setCurrentIndex(max(0, self.priority_member.findData(priority_key or "Automatic")))
        self.priority_member.blockSignals(blocked)
        end_webs = [p for p in webs if p.end != "Through"]
        valid_miter = (len(end_webs) == len(webs) == 2
                       and end_webs[0].geometry_key == end_webs[1].geometry_key)
        blocked = self.direct_policy.blockSignals(True)
        self.direct_policy.clear()
        if configured and intent.form.value == "Direct" and intent.direct_policy.value == "Independent":
            self.direct_policy.addItem("Sem ajuste adicional (legado)", "Independent")
        if valid_miter:
            self.direct_policy.addItem("Meia-esquadria equilibrada", "BalancedMiter")
        self.direct_policy.addItem("Prioridade", "Priority")
        self.direct_policy.setCurrentIndex(max(0, self.direct_policy.findData(intent.direct_policy.value)))
        self.direct_policy.blockSignals(blocked)
        self.direct_policy.setToolTip(
            "O gap axial mantém o plano de meia-esquadria e recua cada barra ao longo do próprio eixo." if valid_miter else
            "Meia-esquadria equilibrada requer exatamente duas barras da alma equivalentes.")
        if not valid_miter and intent.direct_policy.value == "BalancedMiter":
            self.message.setText(self.direct_policy.toolTip(),"warning")
        self._update_connection_visibility()
        if intent.form.value == "Gusset":
            messages = getattr(self.canvas, "_last_model", {}).get(
                "connection_diagnostics_by_node", {}).get(node_key, ())
            if placement_invalid:
                messages = ("A posição anterior ficou indisponível; usada Automática.",)+tuple(messages)
            self.message.setText("\n".join(messages),"warning")

    def _refresh_transverse_preview(self):
        preview = getattr(self, "transverse_preview", None)
        if preview is None:
            return
        node = getattr(self, "_connection_node", None)
        if node is None:
            preview.set_preview()
            return
        model = getattr(self.canvas, "_last_model", {})
        connection = next((value for value in model.get("connections", ())
                           if value["node_key"] == node), {})
        if connection.get("form") != "Gusset":
            preview.set_preview(caption="Nó sem chapa Gusset.")
            return
        # This map is never populated from the schematic's last-valid outline
        # fallback: an invalid edit must not display stale physical placement.
        views = model.get("transverse_previews", {}).get(node, ())
        if not views:
            preview.set_preview(caption="Prévia indisponível para este nó.")
            return
        data = self._gusset_preview_options()
        if not data.get("materializable", True):
            preview.set_preview(views, "Posição física indisponível.")
            return
        resolved = data.get("resolved_transverse_placement", "")
        label = next((region+" · "+position
                      for _key, region, positions in data.get("transverse_regions", ())
                      for key, position in positions if key == resolved),
                     "Posição física resolvida")
        if not data.get("transverse_placement"):
            label = "Automática: "+label
        preview.set_preview(views, label)

    def _gusset_preview_options(self):
        values = getattr(getattr(self, "canvas", None), "_last_model", {}).get(
            "gussets", ())
        return next((value for value in values
                     if value.get("node_key") == self._connection_node), {})

    def _populate_gusset_options(self, placement, preserve_invalid=False):
        del preserve_invalid  # compatibility with focused C6-G callers
        data = self._gusset_preview_options()
        regions = list(data.get("transverse_regions", ()))
        self._gusset_regions = {
            region_id: (label, tuple(positions))
            for region_id, label, positions in regions}
        keys = {key for _region_id, _label, positions in regions
                for key, _position_label in positions}
        region_for_key = next((region_id for region_id, _label, positions in regions
                               if any(key == placement for key, _name in positions)), "")
        region_blocked = self.gusset_region.blockSignals(True)
        position_blocked = self.gusset_position.blockSignals(True)
        self.gusset_region.clear()
        self.gusset_region.addItem("Automática", "")
        for region_id, label, _positions in regions:
            self.gusset_region.addItem(label, region_id)
        invalid = bool(placement and placement not in keys)
        if invalid:
            placement, region_for_key = "", ""
        self.gusset_region.setCurrentIndex(max(
            0, self.gusset_region.findData(region_for_key)))
        self._populate_gusset_positions(region_for_key, placement,
                                        signals_already_blocked=True)
        self.gusset_position.blockSignals(position_blocked)
        self.gusset_region.blockSignals(region_blocked)
        return invalid

    def _populate_gusset_positions(self, region_id, placement="",
                                   signals_already_blocked=False):
        blocked = (False if signals_already_blocked
                   else self.gusset_position.blockSignals(True))
        self.gusset_position.clear()
        if not region_id:
            self.gusset_position.addItem("Resolvida automaticamente", "")
            self.gusset_position.setEnabled(False)
        else:
            positions = self._gusset_regions.get(region_id, ("", ()))[1]
            for key, label in positions:
                self.gusset_position.addItem(label, key)
            self.gusset_position.setEnabled(bool(positions))
            index = self.gusset_position.findData(placement)
            self.gusset_position.setCurrentIndex(max(0, index))
        if not signals_already_blocked:
            self.gusset_position.blockSignals(blocked)

    def _gusset_region_changed(self, *_args):
        if self._connection_node is None:
            return
        self._populate_gusset_positions(self.gusset_region.currentData())
        self._connection_changed()

    def _update_connection_visibility(self):
        direct=self.connection_type.currentData()=="Direct"
        gusset=self.connection_type.currentData()=="Gusset"
        self.connection_type.setToolTip(self._connection_tooltips[self.connection_type.currentData()])
        for widget, visible in ((self.direct_policy, direct),
                (self.priority_member, direct and self.direct_policy.currentData()=="Priority"),
                (self.gusset_plate, gusset), (self.gusset_normal, gusset),
                (self.gusset_axial, gusset), (self.gusset_margin, gusset),
                (self.gusset_overlap, gusset),
                (self.gusset_region, gusset),
                (self.gusset_position, gusset)):
            widget.setVisible(visible)
            form = (self._transverse_form if widget in (
                self.gusset_region, self.gusset_position) else self._connection_form)
            form.labelForField(widget).setVisible(visible)

    def _connection_changed(self,*_args):
        if self._connection_node is None:
            return
        self._update_connection_visibility()
        configured = self.panel.get_config().get("connection_intents",{}).get(
            self._connection_node)
        from ..trusses.connections import (gusset_thickness_for_transition,
                                            intent_from_data)
        previous = intent_from_data(self._connection_node, configured or {})
        if (self.connection_type.currentData() == "Gusset"
                and previous.form.value != "Gusset"
                and previous.gusset.plate_thickness <= 0.):
            blocked = self.gusset_plate.blockSignals(True)
            self.gusset_plate.setValue(gusset_thickness_for_transition(
                self._connection_node, configured,
                self.panel.get_config().get("default_gusset_thickness", 10.)))
            self.gusset_plate._connection_exact_value = float(self.gusset_plate.value())
            self.gusset_plate._connection_display_value = self.gusset_plate.value()
            self.gusset_plate.blockSignals(blocked)
        value=dict(form=self.connection_type.currentData(),fastening=self.fastening.currentData(),
                   direct_policy=self.direct_policy.currentData(),
                   priority_member="Automatic",
                   priority_run_key=(self.priority_member.currentData()
                                     if self.priority_member.currentData() != "Automatic" else ""),
                   gusset=dict(plate_thickness=self._gusset_value(self.gusset_plate),
                               normal_clearance=self._gusset_value(self.gusset_normal),
                               axial_clearance=self._gusset_value(self.gusset_axial),
                               edge_margin=self._gusset_value(self.gusset_margin),
                               member_overlap=self._gusset_value(self.gusset_overlap),
                               side="Center",
                               attachment_mode="Auto",
                               chord_contact="TrussInterior",
                               transverse_placement=(
                                   self.gusset_position.currentData() or "")))
        try:
            self.panel.set_connection_intent(self._connection_node,value)
            self.canvas.refresh_candidate()
            invalid = self._populate_gusset_options(
                value["gusset"]["transverse_placement"])
            if invalid:
                value["gusset"]["transverse_placement"] = ""
                self.panel.set_connection_intent(self._connection_node, value)
                self.canvas.refresh_candidate()
            messages = self._node_messages()
            if invalid:
                messages.insert(0, "A posição anterior ficou indisponível; usada Automática.")
            self.message.setText("\n".join(dict.fromkeys(
                message for message in messages if message)),"warning")
        except (ValueError, KeyError) as exc:
            self.message.setText(str(exc),"error")
            self.transverse_preview.set_preview(
                caption="Prévia indisponível para esta configuração.")

    def _node_messages(self):
        """Read current node diagnostics without reconciliation or a preview build."""
        candidate=self.panel.controller.last_candidate
        messages=[d["message"] for item in candidate.items
                  if self._connection_node in (item.start_node_key,item.end_node_key)
                  for d in (item.physical_fit_plan or {}).get("diagnostics",())]
        messages.extend(self.canvas._last_model.get("connection_diagnostics_by_node",{}).get(
            self._connection_node,()))
        return list(dict.fromkeys(message for message in messages if message))

    @staticmethod
    def _gusset_value(widget):
        value=float(widget.value())
        return (widget._connection_exact_value if value==getattr(widget,"_connection_display_value",None)
                else value)

    def current_mode(self):
        return next(key for key,button in self.mode_buttons.items() if button.isChecked())

    def copy_in_direction(self,direction):
        self.copy_direction=direction
        for key,action in self.copy_actions.items():
            action.setChecked(key==direction)
        self.copy_button.setToolTip("Copiar espelhado: "+self.copy_actions[direction].text())
        self.transform_web("copy_mirrored")

    def transform_web(self,action):
        self.canvas.cancel_gesture()
        try:
            args=dict(direction=self.copy_direction) if action=="copy_mirrored" else {}
            self.panel.apply_topology_edit(action,**args)
            self.canvas.refresh_candidate()
            self.message.setText("Topologia Custom atualizada.")
        except (ValueError,RuntimeError) as exc:
            self.message.setText(str(exc),"error")

    def keyPressEvent(self,event):
        if event.key()==QtCore.Qt.Key_Escape and self.canvas.cancel_gesture():
            event.accept()
            return
        super().keyPressEvent(event)
