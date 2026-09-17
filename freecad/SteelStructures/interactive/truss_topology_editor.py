"""Graph gestures on the Task Panel candidate; no second editable definition."""
from PySide import QtCore, QtGui, QtWidgets
from .truss_preview import TrussPreview2D


class TopologyCanvas(TrussPreview2D):
    def __init__(self, editor):
        super().__init__(editor)
        # Help belongs to the dialog status line, not a tooltip over the drawing.
        self.setToolTip("")
        self.editor=editor
        self.setMaximumHeight(16777215)
        self.setMinimumSize(650,350)
        self.setMouseTracking(True)
        self.pending=None
        self.selected=None
        self.rubber=None
        self.snap_marker=None

    def cancel_gesture(self):
        active=self.pending is not None
        self.pending=None
        if self.rubber is not None:
            self.scene().removeItem(self.rubber)
            self.rubber=None
        self.editor.message.setText("Gesto cancelado." if active else "Selecione uma entidade.")
        return active

    def refresh_candidate(self):
        self.rubber=None
        self.snap_marker=None
        model=self.editor.panel.controller.preview(self.editor.panel.get_config())
        self.set_model(model)
        from ..trusses.validation import connected_components
        graph=self.editor.panel.controller.last_candidate.graph
        selected_node=getattr(self.editor,"_connection_node",None)
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

    def update_selection_halo(self):
        for item in self.scene().items():
            if item.data(0) == "selection_halo":
                self.scene().removeItem(item)
        key = getattr(self.editor, "_connection_node", None)
        graph = self.editor.panel.controller.last_candidate.graph
        node = next((n for n in graph.nodes if n.key == key), None)
        if node is None:
            return
        marker = self.scene().addEllipse(-9,-9,18,18,self._pen((0,190,215),3))
        marker.setData(0, "selection_halo")
        marker.setFlag(QtWidgets.QGraphicsItem.ItemIgnoresTransformations)
        marker.setPos(node.position_local[0], -node.position_local[1])
        marker.setZValue(20)

    def mousePressEvent(self, event):
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
                self.editor.message.setText("Candidato Custom atualizado; OK no Gerador aplica ao documento.")
        except (ValueError,KeyError,StopIteration) as exc:
            self.editor.message.setText(str(exc))

    def snap_at(self, position):
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
        if self.pending is not None:
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
    def __init__(self,panel):
        super().__init__(panel.form)
        self.panel=panel
        self.setWindowTitle("Editar alma da treliça")
        layout=QtWidgets.QVBoxLayout(self)
        toolbar=QtWidgets.QHBoxLayout()
        self.mode_group=QtWidgets.QButtonGroup(self)
        self.mode_group.setExclusive(True)
        self.mode_buttons={}
        for label,key in (("Selecionar","select"),("Criar barra","create"),("Remover barra","remove"),
                          ("Adicionar nó","add_node"),("Remover nó","remove_node"),("Mover nó","move_node")):
            button=QtWidgets.QPushButton(label)
            button.setCheckable(True)
            button.setChecked(key=="select")
            self.mode_group.addButton(button)
            self.mode_buttons[key]=button
            toolbar.addWidget(button)
        layout.addLayout(toolbar)
        mirror_bar=QtWidgets.QHBoxLayout()
        invert=QtWidgets.QPushButton("Inverter alma")
        invert.clicked.connect(lambda *_:self.transform_web("mirror"))
        mirror_bar.addWidget(invert)
        self.copy_button=QtWidgets.QToolButton()
        self.copy_button.setText("Copiar espelhado")
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
        mirror_bar.addWidget(self.copy_button)
        mirror_bar.addStretch(1)
        layout.addLayout(mirror_bar)
        self.allow_free=QtWidgets.QCheckBox("Permitir nó livre")
        self.allow_free.setChecked(False)
        layout.addWidget(self.allow_free)
        self.canvas=TopologyCanvas(self)
        layout.addWidget(self.canvas,1)
        self.message=QtWidgets.QLabel("Edite a alma. Cruzamentos não criam ligação. Cancelar no Gerador descarta o candidato.")
        self.message.setWordWrap(True)
        layout.addWidget(self.message)
        self.diagnostic_legend=QtWidgets.QLabel("Componentes separados do maior componente destacados em magenta.")
        self.diagnostic_legend.setWordWrap(True)
        layout.addWidget(self.diagnostic_legend)
        self.connection_box=QtWidgets.QGroupBox("Ligação do nó")
        form=QtWidgets.QFormLayout(self.connection_box)
        self.connection_type=QtWidgets.QComboBox()
        for label,value in (("Sem ajuste entre barras","GeometricOnly"),("Ligação direta","Direct"),("Chapa de ligação","Gusset")):
            self.connection_type.addItem(label,value)
        self._connection_tooltips = {
            "GeometricOnly": "Não adiciona recortes entre participantes; ajustes ao banzo continuam ativos.",
            "Direct": "Cria contato físico entre barras por meia-esquadria ou prioridade.",
            "Gusset": "Reserva geometricamente espaço para uma futura chapa; a chapa ainda não é criada."}
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
        self.participants=QtWidgets.QLabel("Selecione um nó.")
        self.participants.setWordWrap(True)
        form.addRow("Tipo:",self.connection_type)
        form.addRow("Fixação:",self.fastening)
        form.addRow("Tipo de encontro:",self.direct_policy)
        form.addRow("Prioridade:",self.priority_member)
        form.addRow("Espessura da chapa:",self.gusset_plate)
        form.addRow("Folga normal:",self.gusset_normal)
        form.addRow("Folga axial:",self.gusset_axial)
        self.gusset_plate.setToolTip("Espessura da futura chapa, em mm.")
        self.gusset_normal.setToolTip("Distância adicional perpendicular ao plano da futura chapa, em mm.")
        self.gusset_axial.setToolTip("Recuo adicional ao longo do eixo da barra, em mm; separado do gap axial.")
        form.addRow("Participantes:",self.participants)
        self._connection_form = form
        layout.addWidget(self.connection_box)
        self.connection_box.setEnabled(False)
        self._connection_node=None
        for widget in (self.connection_type,self.fastening,self.direct_policy,self.priority_member):
            widget.currentIndexChanged.connect(self._connection_changed)
        for widget in (self.gusset_plate,self.gusset_normal,self.gusset_axial):
            widget.valueChanged.connect(self._connection_changed)
        buttons=QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.mode_group.buttonClicked.connect(lambda *_:self.canvas.cancel_gesture())
        self.canvas.refresh_candidate()
        self.resize(900,600)

    @staticmethod
    def _length_spin():
        widget=QtWidgets.QDoubleSpinBox()
        widget.setRange(0.,100000.)
        widget.setDecimals(2)
        widget.setSuffix(" mm")
        widget.setKeyboardTracking(False)
        return widget

    def select_node(self,node_key):
        self._connection_node=node_key
        if hasattr(self, "canvas"):
            self.canvas.update_selection_halo()
        self.connection_box.setEnabled(node_key is not None)
        if node_key is None:
            self.participants.setText("Selecione um nó.")
            return
        from ..trusses.connections import default_intent, intent_from_data
        configured=self.panel.get_config().get("connection_intents",{}).get(node_key)
        intent=intent_from_data(node_key,configured or default_intent(node_key))
        widgets=(self.connection_type,self.fastening,self.direct_policy,self.priority_member,
                 self.gusset_plate,self.gusset_normal,self.gusset_axial)
        blocked=[widget.blockSignals(True) for widget in widgets]
        self.connection_type.setCurrentIndex(self.connection_type.findData(intent.form.value))
        self.fastening.setCurrentIndex(self.fastening.findData(intent.fastening.value))
        self.direct_policy.setCurrentIndex(self.direct_policy.findData(intent.direct_policy.value))
        self.priority_member.setCurrentIndex(self.priority_member.findData(intent.priority_member.value))
        for widget,value in ((self.gusset_plate,intent.gusset.plate_thickness),
                             (self.gusset_normal,intent.gusset.normal_clearance),
                             (self.gusset_axial,intent.gusset.axial_clearance)):
            widget.setMaximum(max(widget.maximum(),value))
            widget.setValue(value)
            widget._connection_exact_value=value
            widget._connection_display_value=widget.value()
        for widget,state in zip(widgets,blocked): widget.blockSignals(state)
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
            self.message.setText(self.direct_policy.toolTip())
        self._update_connection_visibility()

    def _update_connection_visibility(self):
        direct=self.connection_type.currentData()=="Direct"
        gusset=self.connection_type.currentData()=="Gusset"
        self.connection_type.setToolTip(self._connection_tooltips[self.connection_type.currentData()])
        for widget, visible in ((self.direct_policy, direct),
                (self.priority_member, direct and self.direct_policy.currentData()=="Priority"),
                (self.gusset_plate, gusset), (self.gusset_normal, gusset), (self.gusset_axial, gusset)):
            widget.setVisible(visible)
            self._connection_form.labelForField(widget).setVisible(visible)

    def _connection_changed(self,*_args):
        if self._connection_node is None:
            return
        self._update_connection_visibility()
        value=dict(form=self.connection_type.currentData(),fastening=self.fastening.currentData(),
                   direct_policy=self.direct_policy.currentData(),
                   priority_member="Automatic",
                   priority_run_key=(self.priority_member.currentData()
                                     if self.priority_member.currentData() != "Automatic" else ""),
                   gusset=dict(plate_thickness=self._gusset_value(self.gusset_plate),
                               normal_clearance=self._gusset_value(self.gusset_normal),
                               axial_clearance=self._gusset_value(self.gusset_axial),side="Center"))
        try:
            self.panel.set_connection_intent(self._connection_node,value)
            self.canvas.refresh_candidate()
            candidate = self.panel.controller.last_candidate
            messages = [d["message"] for item in candidate.items
                        if self._connection_node in (item.start_node_key,item.end_node_key)
                        for d in (item.physical_fit_plan or {}).get("diagnostics", ())]
            self.message.setText(" ".join(dict.fromkeys(messages)) or "Ligação atualizada no candidato.")
        except (ValueError, KeyError) as exc:
            self.message.setText(str(exc))

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
            self.message.setText(str(exc))

    def keyPressEvent(self,event):
        if event.key()==QtCore.Qt.Key_Escape and self.canvas.cancel_gesture():
            event.accept()
            return
        super().keyPressEvent(event)
