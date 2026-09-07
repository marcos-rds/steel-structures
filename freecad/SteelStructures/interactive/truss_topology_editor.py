"""Graph gestures on the Task Panel candidate; no second editable definition."""
from PySide import QtCore, QtGui, QtWidgets
from .truss_preview import TrussPreview2D


class TopologyCanvas(TrussPreview2D):
    def __init__(self, editor):
        super().__init__(editor)
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
                if hit.data(0)=="edge": hit.setPen(self._pen((220,135,20),3))
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
        buttons=QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.mode_group.buttonClicked.connect(lambda *_:self.canvas.cancel_gesture())
        self.canvas.refresh_candidate()
        self.resize(900,600)

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
