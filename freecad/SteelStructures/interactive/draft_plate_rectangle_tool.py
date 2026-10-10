# SPDX-License-Identifier: LGPL-2.1-or-later
"""Two-point StructuralPlate acquisition using the installed Draft Rectangle."""

import math

import FreeCAD as App
import FreeCADGui as Gui
import WorkingPlane
from PySide import QtCore, QtGui, QtWidgets
from shiboken6 import isValid
from draftguitools import gui_base_original, gui_rectangles, gui_trackers
from draftutils import gui_utils, todo

from ..paths import PLATE_ICON
from ..plate import create_plate
from ..plate_geometry import PlateContour2D
from ..plate_planes import placement_from_face


NEW, ACTIVE, FINISHING, FINISHED = "NEW", "ACTIVE", "FINISHING", "FINISHED"


def rectangle_contour(points, placement):
    """Keep geometry local; reject off-plane input rather than project it."""
    if len(points) != 2:
        raise ValueError("Selecione dois cantos para criar o retângulo.")
    inverse = placement.inverse()
    local = [inverse.multVec(App.Vector(point)) for point in points]
    for point in local:
        if not all(math.isfinite(value) for value in point):
            raise ValueError("As coordenadas devem ser finitas.")
        if abs(point.z) > 1e-5:
            raise ValueError("O ponto está fora do plano da chapa.")
    first, opposite = local
    return PlateContour2D.from_points((
        (first.x, first.y), (opposite.x, first.y),
        (opposite.x, opposite.y), (first.x, opposite.y)), closed=True)


class _WorkingPlaneSession:
    """Restore data on the owner WP, refresh only the currently live view."""

    def __init__(self, plane):
        self.plane = plane
        self.parameters = plane.get_parameters()
        self.stored = dict(plane._stored)
        history = getattr(plane, "_history", {})
        self.history = dict(history)
        if "data_list" in history:
            self.history["data_list"] = [dict(data) for data in history["data_list"]]
        self.restored = False

    def restore_data(self):
        if not self.restored:
            self.plane.set_parameters(self.parameters)
            self.plane._stored = self.stored
            if hasattr(self.plane, "_history"):
                self.plane._history = self.history
            self.restored = True

    def _restore(self):
        # Creator.finish calls this hook. It must not refresh an inactive WP.
        self.restore_data()
        if gui_utils.get_3d_view() is not None:
            active = WorkingPlane.get_working_plane(update=False)
            active._update_all(_hist_add=False)

    def __getattr__(self, name):
        return getattr(self.plane, name)


class PlateRectangleOptions(QtWidgets.QWidget):
    """Plate properties only; all coordinate widgets belong to Draft."""

    def __init__(self, face_plane):
        super().__init__()
        self.setWindowTitle("Chapa")
        self.setWindowIcon(QtGui.QIcon(PLATE_ICON))
        layout = QtWidgets.QFormLayout(self)
        shape = QtWidgets.QLabel("Retângulo comum — 2 pontos")
        shape.setToolTip("Dois cantos opostos no plano de criação.")
        layout.addRow("Forma", shape)
        plane = QtWidgets.QLabel("Face selecionada" if face_plane else "Plano de trabalho atual")
        plane.setToolTip("Plano capturado ao iniciar; permanece fixo durante a criação.")
        layout.addRow("Plano", plane)
        self.thickness = QtWidgets.QDoubleSpinBox()
        self.thickness.setRange(0.001, 1000000.0)
        self.thickness.setDecimals(3)
        self.thickness.setValue(10.0)
        self.thickness.setSuffix(" mm")
        self.offset = QtWidgets.QDoubleSpinBox()
        self.offset.setRange(-1000000.0, 1000000.0)
        self.offset.setDecimals(3)
        self.offset.setValue(0.0)
        self.offset.setSuffix(" mm")
        layout.addRow("Espessura", self.thickness)
        layout.addRow("Offset", self.offset)
        self.reverse = QtWidgets.QCheckBox("Inverter sentido da extrusão")
        layout.addRow(self.reverse)
        self.thickness.valueChanged.connect(self._extrusion_changed)
        self.offset.valueChanged.connect(self._extrusion_changed)
        self.reverse.toggled.connect(self._extrusion_changed)
        self._extrusion_changed()
        self.status = QtWidgets.QLabel("Selecione o primeiro ponto.")
        self.status.setWordWrap(True)
        self.status.setStyleSheet("color: palette(mid);")
        layout.addRow(self.status)

    def _extrusion_changed(self, *_args):
        thickness, offset = self.thickness.value(), self.offset.value()
        low, high = (offset - thickness, offset) if self.reverse.isChecked() else (offset, offset + thickness)
        self.reverse.setToolTip("Face de referência em Offset. Extrusão em Z local: %g até %g mm." % (low, high))


class _SessionEvents(QtCore.QObject):
    """One lifecycle guard, without another point/event acquisition engine."""

    def __init__(self, tool):
        super().__init__()
        self.tool = tool

    def eventFilter(self, watched, event):
        if event.type() == QtCore.QEvent.Close:
            self.tool.finish()
        return False

    def slotDeletedDocument(self, document):
        if document is self.tool.doc:
            self.tool.finish()


class _PlateDraftTool(gui_base_original.Creator):
    """Shared pilot lifecycle; the next MRO class owns native point acquisition."""

    feature_name = "Rectangle"
    source_mode = "InteractiveRectangle"

    def __init__(self, on_closed=None, factory=None, session=None):
        super().__init__()
        self._state = NEW
        self._on_closed = on_closed
        self._factory = factory or create_plate
        self._wp_session = None
        self._events = None
        self._mdi = None
        self._owner_window = None
        self._panel = None
        self._base_widget = None
        self.options = None
        self.rect = None
        self.call = None
        self._observer_installed = False
        self.last_created = None
        self.session = session
        self._shortcuts = None
        self._coordinate_focus = None
        self._numeric_shortcut_connections = []

    def _input_ui(self):
        self.ui.pointUi(title="Criar Chapa Estrutural", icon=PLATE_ICON,
                        extra=self.options)
        self.ui.extUi()

    def _init_preview(self):
        from .plate_rectangle_tracker import PlateRectangleTracker
        self.rect = PlateRectangleTracker()
        self.rect.get_scene_graph = self._owner_scene
        if self.rect.coords.point.getNum() != 5:
            raise RuntimeError("Tracker de retângulo inválido: esperados cinco vetores.")

    def _remove_preview(self):
        pass

    def is_active(self):
        return self._state == ACTIVE and App.activeDraftCommand is self

    def _owner_alive(self):
        # Enumerate native live views before invoking anything on the old wrapper.
        if App.listDocuments().get(self._document_name) is not self.doc:
            return False
        try:
            return self.view in Gui.getDocument(self._document_name).mdiViewsOfType("Gui::View3DInventor")
        except (RuntimeError, ReferenceError, NameError):
            return False

    def _owner_scene(self):
        return self.view.getSceneGraph() if self._owner_alive() else None

    def Activated(self, plane_face=None, plane_placement=None):
        if self._state != NEW:
            raise RuntimeError("Esta sessão de chapa já foi iniciada.")
        if App.activeDraftCommand is not None:
            raise RuntimeError("Encerre a ferramenta Draft atual antes de criar a chapa.")
        self._state = ACTIVE
        self.doc = App.ActiveDocument
        self.view = gui_utils.get_3d_view()
        if self.doc is None or self.view is None:
            self.finish()
            raise ValueError("Abra uma vista 3D para criar a chapa.")
        self._document_name = self.doc.Name
        try:
            plane = WorkingPlane.get_working_plane(update=False)
            self._wp_session = _WorkingPlaneSession(plane)
            self.placement = (plane_placement if plane_placement is not None else
                              placement_from_face(plane_face) if plane_face is not None
                              else plane.get_placement())
            self.placement = App.Placement(self.placement.Base, self.placement.Rotation)
            # Freeze BEFORE Creator asks for update=True or derives support.
            plane.align_to_placement(self.placement, _hist_add=False)
            gui_base_original.Creator.Activated(self, self.feature_name)
            self.wp = self._wp_session
            self.support = None
            if self.planetrack is not None:
                self.planetrack.get_scene_graph = self._owner_scene
            self.options = PlateRectangleOptions(plane_face is not None)
            self.refpoint = None
            queue_start = len(todo.ToDo.itinerary)
            self._input_ui()
            self._panel = self.ui.panel
            # DraftTaskPanel.reject resets the active document's edit state.
            # This creation tool does not enter document edit mode, and a late
            # resetEdit can close a replacement non-Draft task dialog.
            self._panel.reject = self._reject_panel
            self._base_widget = self.ui.baseWidget
            self._guard_panel_tasks(queue_start)
            self._base_widget.setWindowTitle("Criar Chapa Estrutural")
            self._base_widget.setWindowIcon(QtGui.QIcon(PLATE_ICON))
            self.ui.pointButton.setText("Adicionar ponto")
            for label in (self.ui.labelx, self.ui.labely, self.ui.labelz):
                label.setMinimumWidth(95)
            self.ui.isRelative.setToolTip("Coordenadas relativas ao último ponto; antes do primeiro, à origem.")
            self.ui.isGlobal.setToolTip("Usar eixos globais. Desmarcado: eixos locais do plano da chapa.")
            self.ui.makeFace.hide()
            self.ui.continueCmd.setText("Continuar criando")
            if self.session is not None:
                self.session.configure(self)
            self._install_panel_shortcuts()
            self._base_widget.destroyed.connect(self._panel_destroyed)
            # Native constructor reads the already aligned WP.
            self._init_preview()
            if plane_face is not None or plane_placement is not None:
                self.options.status.setText("Plano definido.")
            self.call = self.view.addEventCallback("SoEvent", self.action)
            self._events = _SessionEvents(self)
            App.addDocumentObserver(self._events)
            self._observer_installed = True
            self._mdi = Gui.getMainWindow().findChild(QtWidgets.QMdiArea)
            if self._mdi is not None:
                self._owner_window = self._mdi.activeSubWindow()
                if self._owner_window is not None:
                    self._owner_window.installEventFilter(self._events)
                self._mdi.subWindowActivated.connect(self._view_changed)
            self.update_hints()
        except Exception:
            self.finish()
            raise

    def _guard_panel_tasks(self, start):
        # Scope only this activation's native show/close/focus jobs. An aborted
        # activation must not show its stale panel or close a replacement tool.
        for index in range(start, len(todo.ToDo.itinerary)):
            task = todo.ToDo.itinerary[index]
            todo.ToDo.itinerary[index] = (self._run_panel_task, task)

    def _run_panel_task(self, task):
        if self.is_active() and self._owner_alive() and self.ui.panel is self._panel:
            callback, argument = task
            if argument or argument is False:
                callback(argument)
            else:
                callback()

    def _view_changed(self, *_args):
        if self._state == ACTIVE and gui_utils.get_3d_view() != self.view:
            self.finish()

    def _panel_destroyed(self, *_args):
        self._base_widget = None
        self.options = None
        self.finish()

    def _reject_panel(self):
        if self.ui.sourceCmd is self:
            self.ui.isTaskOn = False
        self.finish()
        return True

    def update_hints(self):
        if self.is_active():
            super().update_hints()
            restart = getattr(self, "restart_button", None)
            if restart is not None and self.source_mode == "InteractiveRectangle":
                restart.setVisible(bool(self.node))

    def _install_panel_shortcuts(self):
        from .plate_panel_shortcuts import (PanelShortcuts, DraftCoordinateFocus,
                                            draft_shortcut_keys, editable_focus, point_shortcut_key)
        keys = draft_shortcut_keys()
        names = ("xValue", "yValue", "zValue", "lengthValue", "radiusValue", "angleValue")
        self._coordinate_focus = DraftCoordinateFocus(
            [getattr(self.ui, name) for name in names], self._refresh_shortcuts,
            lambda key, repeat=False: self._shortcuts.run_key(key, repeat)
            if self._shortcuts is not None else False)
        self._shortcuts = PanelShortcuts(self._base_widget, self.is_active,
                                         self._coordinate_focus.protects)
        for name, action, label in (("isRelative", "Relative", "Relativo"),
                                    ("isGlobal", "Global", "Global"),
                                    ("continueCmd", "Continue", "Continuar criando")):
            self._shortcuts.bind(getattr(self.ui, name), keys[action], label=label)
        # Draft reserves A for Exit. P is an additional point action, provided
        # that the user's native shortcut preferences have not reserved it.
        self._shortcuts.bind(self.ui.pointButton, point_shortcut_key(keys), label="Adicionar ponto")
        if self.source_mode == "InteractivePolygon":
            for name, action, label in (("undoButton", "Undo", "Desfazer ponto"),
                                        ("closeButton", "Close", "Fechar contorno"),
                                        ("wipeButton", "Wipe", "Limpar pontos")):
                self._shortcuts.bind(getattr(self.ui, name), keys[action], label=label)
        for axis in ("x", "y", "z"):
            def constrain(axis=axis):
                self.ui.constrain(axis)
                self.ui.displayPoint(self.ui.new_point, self.ui.get_last_point())
            self._shortcuts.bind(getattr(self.ui, "label" + axis),
                                 keys["Restrict" + axis.upper()], callback=constrain)
        def constrain_angle():
            self.ui.constrain("angle")
            self.ui.displayPoint(self.ui.new_point, self.ui.get_last_point())
        self._shortcuts.bind(self.ui.angleLock, keys["Length"], callback=constrain_angle)
        original = self.ui.checkSpecialChars

        def numeric_text(text):
            if not self.is_active():
                return
            self._coordinate_focus.set_editing(True)
            # Draft normally treats a leading letter as an action. Within this
            # command editable fields must retain text (including unit names).
            if text and text[0] not in "0123456789.,-+" and editable_focus(QtWidgets.QApplication.focusWidget()):
                return
            original(text)

        for name in names:
            field = getattr(self.ui, name)
            field.textEdited.disconnect(original)
            field.textEdited.connect(numeric_text)
            self._numeric_shortcut_connections.append((field, original, numeric_text))

    def _refresh_shortcuts(self):
        if self._shortcuts is not None:
            self._shortcuts.refresh()

    def _remove_panel_shortcuts(self):
        if self._shortcuts is not None:
            self._shortcuts.dispose()
            self._shortcuts = None
        if self._coordinate_focus is not None:
            self._coordinate_focus.dispose()
            self._coordinate_focus = None
        for field, original, guarded in self._numeric_shortcut_connections:
            try:
                field.textEdited.disconnect(guarded)
                field.textEdited.connect(original)
            except RuntimeError:
                pass
        self._numeric_shortcut_connections.clear()

    def action(self, arg):
        if not self.is_active():
            return
        if not self._owner_alive() or gui_utils.get_3d_view() != self.view:
            self.finish()
            return
        try:
            if arg.get("Type") == "SoLocation2Event" and self.ui.mouse:
                # Native displayPoint focuses InputField on every move. That
                # programmatic focus is not an editing session. Respect the
                # native MouseDelay before releasing actual numeric editing.
                if self._coordinate_focus is not None:
                    self._coordinate_focus.set_editing(False)
            return super().action(arg)
        except Exception as exc:
            App.Console.PrintError(f"Steel Structures: erro na aquisição da chapa: {exc}\n")
            self.finish()

    def numericInput(self, numx, numy, numz):
        if not self.is_active():
            return
        if not self._owner_alive() or gui_utils.get_3d_view() != self.view:
            self.finish()
            return
        try:
            return super().numericInput(numx, numy, numz)
        except Exception as exc:
            App.Console.PrintError(f"Steel Structures: erro na entrada da chapa: {exc}\n")
            self.finish()

    def _rectangle_append(self, point):
        if not self.is_active():
            return
        local = self.placement.inverse().multVec(App.Vector(point))
        if not all(math.isfinite(value) for value in local) or abs(local.z) > 1e-5:
            self.options.status.setText("O ponto deve pertencer ao plano da chapa.")
            return
        if self.node:
            try:
                rectangle_contour([self.node[0], point], self.placement)
            except ValueError as exc:
                self.options.status.setText(str(exc))
                return
        result = gui_rectangles.Rectangle.appendPoint(self, point)
        if self.is_active() and self.options is not None:
            self.options.status.setText("Selecione o canto oposto." if self.node
                                        else "Selecione o primeiro ponto.")
            self.update_hints()
        return result

    def createObject(self):
        if not self.is_active():
            return
        try:
            contour = self._contour()
            self.doc.openTransaction("Criar Chapa Estrutural")
            try:
                plate = self._factory(self.doc, contour, placement=self.placement,
                                      thickness=self.options.thickness.value(),
                                      offset=self.options.offset.value(),
                                      reverse_extrusion=self.options.reverse.isChecked(),
                                      source_mode=self.source_mode)
                self.doc.commitTransaction()
            except Exception:
                self.doc.abortTransaction()
                raise
            self.last_created = plate
            Gui.Selection.clearSelection()
            Gui.Selection.addSelection(plate)
            if self.ui.continueMode:
                self.reset_trace()
            else:
                self.finish()
        except Exception as exc:
            App.Console.PrintError(f"Steel Structures: erro ao criar chapa: {exc}\n")
            self.finish()

    def reset_trace(self):
        # Continue retains one panel/callback/tracker and the original snapshot.
        if self.rect is not None:
            self.rect.off()
        self.node = []
        self.point = None
        self.pos = []
        self.support = None
        self.constrain = None
        self.ui.mouse = True
        self.ui.mask = None
        self.ui.alock = False
        Gui.Snapper.mask = None
        self.ui.reset_ui_values()
        self.ui.setRelative(-2)
        self.options.status.setText("Selecione o primeiro ponto.")
        self.update_hints()

    def end_callbacks(self, call):
        # No processEvents/end_all_events inside a Coin callback or teardown.
        if call is not None and self._owner_alive():
            self.view.removeEventCallback("SoEvent", call)

    def finish(self, cont=False):
        if self._state in (FINISHING, FINISHED):
            return
        self._state = FINISHING
        self._remove_panel_shortcuts()
        if self.session is not None:
            self.session.remember(self)
        # Restore data now: a replacement tool must snapshot the original WP.
        call, self.call = self.call, None
        try:
            try:
                if self._wp_session is not None:
                    self._wp_session.restore_data()
            finally:
                self.end_callbacks(call)
        finally:
            QtCore.QTimer.singleShot(0, self._teardown)

    def _close_owned_panel(self):
        if (self.ui.panel is self._panel and self.ui.sourceCmd is None
                and self._panel_is_attached()):
            Gui.Control.closeDialog()

    def _panel_is_attached(self):
        # activeDialog() is only bool in FreeCAD 1.1.x. Verify the original
        # TaskBox is still in the TaskPanel layout, even if it is collapsed.
        # External non-Draft panels do not replace draftToolBar.panel.
        widget = self._base_widget
        if widget is None or not isValid(widget):
            return False
        while widget is not None:
            if widget.inherits("Gui::TaskView::TaskBox"):
                parent = widget.parentWidget()
                if parent is None or not parent.inherits("Gui::TaskView::TaskPanel"):
                    return False
                layout = parent.layout()
                return (layout is not None and layout.indexOf(widget) >= 0
                        and widget.isVisibleTo(parent))
            widget = widget.parentWidget()
        return False

    def _teardown(self):
        if self._state != FINISHING:
            return
        try:
            header = getattr(self, "shape_selector", None)
            if header is not None and isValid(header):
                header.deleteLater()
            self._cleanup(self._remove_preview)
            if self._observer_installed:
                self._cleanup(lambda: App.removeDocumentObserver(self._events))
                self._observer_installed = False
            if self._mdi is not None:
                self._detach(lambda: self._mdi.subWindowActivated.disconnect(self._view_changed))
            if self._owner_window is not None:
                # QObject destruction auto-removes event filters.
                try:
                    self._owner_window.removeEventFilter(self._events)
                except RuntimeError:
                    pass
            if self._base_widget is not None:
                self._detach(lambda: self._base_widget.destroyed.disconnect(self._panel_destroyed))
            if self.rect is not None:
                self._cleanup(self.rect.off)
                self._cleanup(self.rect.finalize)
                self.rect = None
            planetrack, self.planetrack = getattr(self, "planetrack", None), None
            if planetrack is not None:
                self._cleanup(planetrack.finalize)
            ui = getattr(self, "ui", None)
            if ui is not None and ui.sourceCmd is self:
                # Preserve native cleanup, adapting WP restore and queued close.
                old_queue = len(todo.ToDo.itinerary)
                self._cleanup(lambda: gui_base_original.Creator.finish(self))
                for index in range(old_queue, len(todo.ToDo.itinerary)):
                    callback, argument = todo.ToDo.itinerary[index]
                    # Control's native bound methods are fresh wrappers;
                    # equality is not a reliable identity test in FreeCAD.
                    if (callback == Gui.Control.closeDialog
                            or getattr(callback, "__name__", None) == "closeDialog"):
                        todo.ToDo.itinerary[index] = (self._close_owned_panel, None)
                self.planetrack = None
                if ui.sourceCmd is self:
                    # Partial native cleanup must release only our own UI.
                    ui.sourceCmd = None
                    ui.pointcallback = None
                    ui.cancel = None
                    ui.mask = None
                    ui.isTaskOn = False
                    self._cleanup(Gui.Snapper.off)
                    QtCore.QTimer.singleShot(0, self._close_owned_panel)
            else:
                if self._wp_session is not None:
                    self._wp_session._restore()
                if App.activeDraftCommand is self:
                    App.activeDraftCommand = None
        finally:
            try:
                if self._wp_session is not None:
                    self._wp_session._restore()
            finally:
                if App.activeDraftCommand is self:
                    App.activeDraftCommand = None
                self._state = FINISHED
                self.node = []
                callback, self._on_closed = self._on_closed, None
                if callback is not None:
                    callback(self)

    @staticmethod
    def _cleanup(callback):
        try:
            callback()
        except Exception as exc:
            # Each cleanup phase must run even if a previous resource failed.
            App.Console.PrintError(f"Steel Structures: erro ao encerrar chapa: {exc}\n")

    @staticmethod
    def _detach(callback):
        try:
            callback()
        except (RuntimeError, TypeError):
            # Qt already disconnected signals/filters on QObject destruction.
            pass


class StructuralPlateRectangleTool(_PlateDraftTool, gui_rectangles.Rectangle):
    """Native Rectangle acquisition with the local five-vector tracker."""

    def appendPoint(self, point):
        return self._rectangle_append(point)

    def _contour(self):
        return rectangle_contour(self.node, self.placement)
