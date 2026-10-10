# SPDX-License-Identifier: LGPL-2.1-or-later
"""One command owner; sequential native sessions, or isolated advanced capture."""
import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtCore, QtWidgets
from shiboken6 import isValid
from draftutils import gui_utils


class PlateCreationSession(QtCore.QObject):
    def __init__(self, document, plane_face=None, on_closed=None):
        super().__init__()
        self.document = document
        self._document_name = document.Name
        self.view = gui_utils.get_3d_view()
        self.plane_face = plane_face
        self.on_closed = on_closed
        self.shape = "Rectangle"
        self.plane = "Face" if plane_face is not None else "WorkPlane"
        self.thickness, self.offset = 10.0, 0.0
        self.reverse_extrusion = False
        self._plane_placement = None
        self._picking_face = False
        self.face_picker = None
        self.tool = None
        self.panel = None
        self._closed = False
        self._pending = None
        self._advanced = False
        self._mdi = None
        self._owner_window = None
        self._advanced_observer = False
        self._advanced_box = None

    def _owner_alive(self):
        if App.listDocuments().get(self._document_name) is not self.document:
            return False
        try:
            return self.view in Gui.getDocument(self._document_name).mdiViewsOfType("Gui::View3DInventor")
        except (RuntimeError, ReferenceError, NameError):
            return False

    def start(self):
        if self._closed:
            return
        if (not self._owner_alive() or gui_utils.get_3d_view() != self.view
                or getattr(App, "activeDraftCommand", None) or Gui.Control.activeDialog()):
            self.finish()
            return
        if self._picking_face:
            from .plate_face_selection import PlateFaceSelection
            self.face_picker = PlateFaceSelection(self.document, self.view, self._face_closed)
            self.face_picker.start()
            return
        if self._advanced or self.plane == "Auto":
            self._start_advanced()
            return
        from .draft_plate_rectangle_tool import StructuralPlateRectangleTool
        from .draft_plate_polygon_tool import StructuralPlatePolygonTool
        cls = StructuralPlateRectangleTool if self.shape == "Rectangle" else StructuralPlatePolygonTool
        self.tool = cls(on_closed=self._tool_closed, session=self)
        try:
            arguments = {"plane_face": self.plane_face if self.plane == "Face" else None}
            if self.plane == "Face" and self._plane_placement is not None:
                arguments["plane_placement"] = self._plane_placement
            self.tool.Activated(**arguments)
        except Exception:
            self._pending = None
            self.finish()
            raise

    def configure(self, tool):
        options = tool.options
        options.setWindowTitle("Propriedades da chapa")
        layout = options.layout()
        layout.removeRow(0)  # old fixed pilot shape/plane labels
        layout.removeRow(0)
        options.thickness.setValue(self.thickness)
        options.offset.setValue(self.offset)
        options.reverse.setChecked(self.reverse_extrusion)
        header = QtWidgets.QWidget(tool._base_widget)
        row = QtWidgets.QVBoxLayout(header)
        row.setContentsMargins(0, 0, 0, 6)
        shape = QtWidgets.QComboBox()
        shape.addItem("Polígono", "Polygon")
        shape.addItem("Retângulo", "Rectangle")
        shape.setCurrentIndex(shape.findData(self.shape))
        shape.setToolTip("Altere sem pontos confirmados. Use %s para descartar pontos." % self.reset_action())
        row.addWidget(QtWidgets.QLabel("Forma"))
        row.addWidget(shape)
        tool._base_widget.layout().insertWidget(0, header)
        tool.shape_selector = header
        tool.shape_combo = shape
        plane = QtWidgets.QComboBox()
        self.configure_plane_combo(plane)
        row.addWidget(QtWidgets.QLabel("Plano de criação"))
        row.addWidget(plane)
        if self.plane == "Face" and self.plane_face is not None:
            face_row = QtWidgets.QWidget(header)
            face_layout = QtWidgets.QHBoxLayout(face_row)
            face_layout.setContentsMargins(0, 0, 0, 0)
            tool.face_label = QtWidgets.QLabel(self.face_description())
            tool.face_label.setWordWrap(True)
            face_layout.addWidget(tool.face_label, 1)
            tool.change_face_button = QtWidgets.QPushButton("Alterar face")
            tool.change_face_button.clicked.connect(lambda: self.select_face(tool))
            face_layout.addWidget(tool.change_face_button)
            row.addWidget(face_row)
        row.addWidget(QtWidgets.QLabel("Entrada de pontos"))
        tool.plane_combo = plane
        if self.shape == "Rectangle":
            restart = QtWidgets.QPushButton("Reiniciar traçado")
            restart.setToolTip("Remover o primeiro canto para iniciar outro retângulo.")
            restart.setVisible(bool(tool.node))
            layout.addRow(restart)
            tool.restart_button = restart
            restart.clicked.connect(lambda: tool.reset_trace() if tool.is_active() else None)
        else:
            tool.restart_button = tool.ui.wipeButton
        if self.shape == "Rectangle":
            group = QtWidgets.QGroupBox("Opções avançadas")
            advanced_layout = QtWidgets.QVBoxLayout(group)
            advanced = QtWidgets.QPushButton("Retângulo orientado — 3 pontos")
            advanced.setToolTip("Define um plano 3D pelos pontos, usando a aquisição avançada anterior.")
            advanced_layout.addWidget(advanced)
            layout.addRow(group)
            tool.advanced_button = advanced
            advanced.clicked.connect(lambda: self._change(tool, advanced=True))
        shape.currentIndexChanged.connect(lambda index: self._change(tool, shape=shape.itemData(index)))
        plane.currentIndexChanged.connect(lambda index: self._change(tool, plane=plane.itemData(index)))
        # Relayout only widgets already owned by this native TaskPanel. Their
        # signals, event filters, fields and acquisition controller stay native.
        self._arrange_native_points(tool)
        layout.takeRow(options.status)
        layout.addRow(options.status)

    def _arrange_native_points(self, tool):
        ui, root = tool.ui, tool._base_widget.layout()
        root.setSpacing(6)
        axes = QtWidgets.QHBoxLayout()
        for check in (ui.isRelative, ui.isGlobal):
            root.removeWidget(check)
            axes.addWidget(check)
        root.insertLayout(1, axes)
        buttons = (ui.pointButton, ui.undoButton, ui.closeButton, ui.wipeButton)
        for button in buttons:
            for index in range(root.count() - 1, -1, -1):
                item = root.itemAt(index)
                child = item.layout()
                if child is not None and child.indexOf(button) >= 0:
                    child.removeWidget(button)
                    if not child.count():
                        root.takeAt(index)
                        child.deleteLater()
                    break
        actions = QtWidgets.QGridLayout()
        actions.setSpacing(6)
        actions.addWidget(ui.pointButton, 0, 0)
        if self.shape == "Polygon":
            actions.addWidget(ui.undoButton, 0, 1)
            actions.addWidget(ui.closeButton, 1, 0)
            actions.addWidget(ui.wipeButton, 1, 1)
        position = 2
        for index in range(root.count()):
            child = root.itemAt(index).layout()
            if child is not None and any(child.indexOf(field) >= 0 and not field.isHidden()
                                         for field in (ui.xValue, ui.yValue, ui.zValue,
                                                       ui.lengthValue, ui.angleValue)):
                position = index + 1
        root.insertLayout(position, actions)
        tool.point_actions = actions
        for label in (ui.labelx, ui.labely, ui.labelz):
            label.setMinimumWidth(75)
        for field in (ui.xValue, ui.yValue, ui.zValue):
            field.setMinimumWidth(110)
        for button, tooltip in ((ui.pointButton, "Confirmar o ponto candidato ou as coordenadas completas."),
                                (ui.undoButton, "Remover o último ponto confirmado."),
                                (ui.closeButton, "Unir o último vértice ao primeiro e fechar o contorno."),
                                (ui.wipeButton, "Remover todos os pontos e começar o contorno novamente.")):
            button.setToolTip(tooltip)

    def face_description(self):
        reference = self.plane_face
        if reference is None:
            return ""
        try:
            return "%s — %s" % (reference.parent.Label, reference.subelement)
        except (RuntimeError, ReferenceError):
            return "Face capturada"

    def reset_action(self):
        return "Reiniciar traçado" if self.shape == "Rectangle" and not self._advanced else "Limpar pontos"

    def configure_plane_combo(self, combo):
        combo.addItem("Plano de trabalho", "WorkPlane")
        combo.addItem("Face do modelo", "Face")
        # The common rectangle remains a two-corner Draft operation.
        if self.shape == "Polygon" or self._advanced:
            combo.addItem("Automático — pelos pontos 3D", "Auto")
        combo.setCurrentIndex(combo.findData(self.plane))
        combo.setToolTip("Altere sem pontos confirmados. Use %s antes de mudar o plano." % self.reset_action())

    def remember(self, tool):
        if tool.options is not None and isValid(tool.options):
            self.thickness, self.offset = tool.options.thickness.value(), tool.options.offset.value()
            self.reverse_extrusion = tool.options.reverse.isChecked()

    def _change(self, tool, shape=None, plane=None, advanced=False):
        if self._closed or self.tool is not tool or not tool.is_active():
            return
        if tool.node:
            tool.options.status.setText("Use %s antes de alterar a forma ou o plano." % self.reset_action())
            for combo, value in ((tool.shape_combo, self.shape), (tool.plane_combo, self.plane)):
                blocked = combo.blockSignals(True)
                combo.setCurrentIndex(combo.findData(value))
                combo.blockSignals(blocked)
            return
        self.remember(tool)
        if plane == "Face" and self.plane_face is None:
            self.select_face(tool)
            return
        self.shape, self.plane = shape or self.shape, plane or self.plane
        self._advanced = advanced
        if advanced:
            self.plane = "Auto"
        self._pending = True
        tool.finish()

    def _tool_closed(self, tool):
        if self.tool is not tool:
            return
        self.tool = None
        if self._pending and not self._closed:
            self._pending = None
            # Native ToDo cleanup was queued before this timer.
            QtCore.QTimer.singleShot(0, self._restart)
        else:
            self._done()

    def _restart(self):
        if self._closed:
            return
        try:
            self.start()
        except Exception as exc:
            App.Console.PrintError("Steel Structures: " + str(exc) + "\n")
            self.finish()

    def _start_advanced(self):
        import WorkingPlane
        from .plate_controller import PlateController
        from .plate_task_panel import PlateTaskPanel
        controller = PlateController(self.document, view=self.view, plane_mode="Auto", plane_face=None,
                                     placement=WorkingPlane.get_working_plane(update=False).get_placement())
        controller.set_mode("InteractiveRectangle" if self.shape == "Rectangle" else "InteractivePolygon")
        self.panel = panel = PlateTaskPanel(controller, self._legacy_closed, advanced=True,
                                            session=self)
        panel.thickness.setValue(self.thickness)
        panel.offset.setValue(self.offset)
        panel.reverse.setChecked(self.reverse_extrusion)
        panel.restart_button = panel.clear_button
        App.addDocumentObserver(self)
        self._advanced_observer = True
        panel.input_form.destroyed.connect(self._advanced_destroyed)
        self._mdi = Gui.getMainWindow().findChild(QtWidgets.QMdiArea)
        if self._mdi is not None:
            self._owner_window = self._mdi.activeSubWindow()
            if self._owner_window is not None:
                self._owner_window.installEventFilter(self)
            self._mdi.subWindowActivated.connect(self._advanced_view_changed)
        Gui.Control.showDialog(panel)
        widget = panel.input_form
        while widget is not None and not widget.inherits("Gui::TaskView::TaskBox"):
            widget = widget.parentWidget()
        self._advanced_box = widget
        if widget is not None:
            widget.installEventFilter(self)

    def _change_panel(self, shape=None, plane=None, restart=False):
        panel = self.panel
        if (self._closed or panel is None or panel._closed
                or getattr(panel, "_closing", False) or panel.controller.closed):
            return
        if not restart and (panel.controller.point_count or panel.controller.contour is not None):
            panel._show_error("Use %s antes de alterar a forma ou o plano." % self.reset_action())
            for combo, value in ((panel.mode, "Interactive" + self.shape),
                                 (panel.plane_mode, self.plane)):
                blocked = combo.blockSignals(True)
                combo.setCurrentIndex(combo.findData(value))
                combo.blockSignals(blocked)
            return
        self.thickness, self.offset = panel.thickness.value(), panel.offset.value()
        self.reverse_extrusion = panel.reverse.isChecked()
        if plane == "Face" and self.plane_face is None:
            self.select_face(panel)
            return
        if shape is not None:
            self.shape = shape
            self._advanced = False
            if shape == "Rectangle" and self.plane == "Auto":
                self.plane = "WorkPlane"
        if plane is not None:
            self.plane = plane
            self._advanced = self.shape == "Rectangle" and plane == "Auto"
        self._pending = True
        panel.reject()

    def _restart_panel_trace(self, owner=None):
        if owner is not None and owner is not self.panel:
            return
        self._change_panel(restart=True)

    def select_face(self, owner=None):
        if self._closed or (owner is not None and owner is not self.tool and owner is not self.panel):
            return
        if self.tool is not None:
            if not self.tool.is_active():
                return
            if self.tool.node:
                self.tool.options.status.setText("Use %s antes de selecionar uma face." % self.reset_action())
                return
            self._picking_face = True
            self._change(self.tool)
        elif self.panel is not None:
            if (self.panel._closed or self.panel._closing or self.panel.controller.closed):
                return
            if self.panel.controller.point_count or self.panel.controller.contour is not None:
                self.panel._show_error("Use %s antes de selecionar uma face." % self.reset_action())
                return
            self._picking_face = True
            self._change_panel()

    def _face_closed(self, picker, reference, placement):
        if picker is not self.face_picker:
            return
        self.face_picker = None
        self._picking_face = False
        if self._closed:
            self._done()
        elif reference is None:
            # The previous creation plane was never replaced while choosing.
            QtCore.QTimer.singleShot(0, self._restart)
        else:
            self.plane_face = reference
            self._plane_placement = App.Placement(placement)
            self.plane = "Face"
            self._advanced = False
            QtCore.QTimer.singleShot(0, self._restart)

    def _detach_advanced(self):
        if self._advanced_observer:
            App.removeDocumentObserver(self)
            self._advanced_observer = False
        if self._mdi is not None and isValid(self._mdi):
            try:
                self._mdi.subWindowActivated.disconnect(self._advanced_view_changed)
            except (RuntimeError, TypeError):
                pass
        if self._owner_window is not None and isValid(self._owner_window):
            self._owner_window.removeEventFilter(self)
        if self._advanced_box is not None and isValid(self._advanced_box):
            self._advanced_box.removeEventFilter(self)
        self._advanced_box = None
        self._mdi = self._owner_window = None

    def _legacy_closed(self, panel, accepted):
        if panel is not self.panel:
            return
        form = getattr(panel, "input_form", None)
        if form is not None and isValid(form):
            try:
                form.destroyed.disconnect(self._advanced_destroyed)
            except (RuntimeError, TypeError):
                pass
        self._detach_advanced()
        self.panel = None
        # Only close if this form is still attached to the live TaskPanel.
        widget = form if form is not None and isValid(form) else None
        while widget is not None and not widget.inherits("Gui::TaskView::TaskBox"):
            widget = widget.parentWidget()
        if widget is not None:
            parent = widget.parentWidget()
            if (parent is not None and parent.inherits("Gui::TaskView::TaskPanel")
                    and parent.layout() is not None and parent.layout().indexOf(widget) >= 0
                    and widget.isVisibleTo(parent)):
                Gui.Control.closeDialog()
        if self._pending and not self._closed:
            self._pending = None
            QtCore.QTimer.singleShot(0, self._restart)
        else:
            self._done()

    def _advanced_view_changed(self, *_args):
        if self.panel is not None and gui_utils.get_3d_view() != self.view:
            self._defer_advanced_cancel()

    def slotDeletedDocument(self, document):
        if document is self.document:
            self._defer_advanced_cancel()

    def eventFilter(self, watched, event):
        if (event.type() == QtCore.QEvent.Close
                or (watched is self._advanced_box and event.type() == QtCore.QEvent.Hide)):
            self._defer_advanced_cancel()
        return False

    def _defer_advanced_cancel(self):
        if self.panel is not None:
            self.panel.controller.closed = True  # late native callbacks become inert now
            QtCore.QTimer.singleShot(0, self.finish)

    def _advanced_destroyed(self, *_args):
        self._defer_advanced_cancel()

    def finish(self):
        self._closed = True
        self._pending = None
        if self.face_picker is not None:
            self.face_picker.finish()
        elif self.tool is not None:
            self.tool.finish()
        elif self.panel is not None:
            controller = self.panel.controller
            if not self._owner_alive():
                controller._capturing = False
                controller._callbacks = []
                controller.preview._scene = None
            elif getattr(App, "activeDraftCommand", None) is not None:
                # A replacement Draft tool owns the global Snapper now.
                callbacks, controller._callbacks = controller._callbacks, []
                controller._capturing = False
                for kind, token in callbacks:
                    self.view.removeEventCallback(kind, token)
            form = getattr(self.panel, "input_form", None)
            if form is not None and isValid(form):
                self.panel.reject()
            else:
                panel = self.panel
                panel.controller.on_change = panel.controller.on_error = panel.controller.on_cancel = None
                panel.controller.numeric_editing = None
                panel.controller.on_candidate = None
                panel.controller.cancel()
                self._legacy_closed(panel, False)
        else:
            self._done()

    def _done(self):
        self._closed = True
        callback, self.on_closed = self.on_closed, None
        if callback is not None:
            callback(self)
