# SPDX-License-Identifier: LGPL-2.1-or-later
"""One-click global-Z column acquisition using Draft's native snap pipeline."""

import FreeCAD as App
from FreeCAD import Gui
from PySide import QtCore, QtGui
from draftguitools import gui_base_original, gui_lines
from draftutils import todo
from draftutils.messages import _toolmsg

from ..member_axis_source import resolve_axis_source
from ..paths import COLUMN_ICON
from ..preferences import load_column_creation_settings, save_column_creation_settings
from .column_task_panel import ColumnTaskPanel, column_top
from .member_controller import CreationGeometryMode, MemberController
from .member_creation_preview import (
    PreviewState, configure_preview_object, update_member_preview,
)
from .axis_source_widget import (
    configure_source_axis_draft_ui, install_source_axis_create_button,
    remove_source_axis_create_button,
)


TOOL_NEW = "NEW"
TOOL_ACTIVE = "ACTIVE"
TOOL_FINISHING = "FINISHING"
TOOL_FINISHED = "FINISHED"


class StructuralColumnDraftTool(gui_lines.Line):
    """Keep Draft's events and snapper, replacing its two-point result."""

    def __init__(self, on_closed=None):
        super().__init__(mode="line")
        self._on_closed = on_closed
        self._closed_notified = False
        self._lifecycle_state = TOOL_NEW
        self._tool_active = False
        self.controller = None
        self.column_panel = None
        self._current_hover_point = None
        self._preview_state = PreviewState()
        self.axis_source = None
        self._source_axis_button_binding = None

    def is_active(self):
        return self._lifecycle_state == TOOL_ACTIVE and self._tool_active

    def Activated(self, name="StructuralColumn", icon=None, task_title=None,
                  axis_source=None):
        if self._lifecycle_state != TOOL_NEW:
            raise RuntimeError("StructuralColumnDraftTool já foi ativada")
        self._lifecycle_state = TOOL_ACTIVE
        gui_base_original.Creator.Activated(self, "Line")
        self._tool_active = True
        self.controller = MemberController(self.doc)
        self.controller.start()
        self.axis_source = axis_source if resolve_axis_source(axis_source) else None
        self.column_panel = ColumnTaskPanel(
            self.doc, self._preview_options_changed, axis_source=self.axis_source
        )
        self.column_panel.axis_source_controls.linkChanged.connect(
            self._axis_link_changed
        )
        settings = load_column_creation_settings()
        self.column_panel.apply_creation_settings(settings)
        self.ui.lineUi(title="Criar Pilar", icon="Draft_Draft", extra=self.column_panel)
        self.ui.baseWidget.setWindowTitle("Criar Pilar")
        self.ui.baseWidget.setWindowIcon(QtGui.QIcon(icon or COLUMN_ICON))
        self.ui.continueMode = settings.continue_creating
        self.ui.continueCmd.setChecked(self.ui.continueMode)
        self.ui.continueCmd.setText("Continuar criando")
        for name in ("labellength", "lengthValue", "labelangle", "angleValue", "angleLock"):
            widget = getattr(self.ui, name, None)
            if widget is not None:
                widget.setVisible(False)
        self.obj = self.doc.addObject("Part::Feature", "SteelStructuresColumnPreview")
        configure_preview_object(self.obj)
        if self.axis_source is not None:
            self._prepare_axis_source_input()
            configure_source_axis_draft_ui(self.ui)
            QtCore.QTimer.singleShot(100, self._install_source_axis_create_button)
            self.call = None
        else:
            self.call = self.view.addEventCallback("SoEvent", self.action)
            _toolmsg("Selecione o ponto da base do pilar")

    def _axis_link_changed(self, linked):
        self._prepare_axis_source_input()

    def _install_source_axis_create_button(self):
        if not self.is_active() or self._source_axis_button_binding is not None:
            return
        self._source_axis_button_binding = install_source_axis_create_button(
            self.ui, self._confirm_axis_source
        )

    def _prepare_axis_source_input(self):
        resolved = resolve_axis_source(self.axis_source)
        if resolved is None:
            return False
        self.point = App.Vector(resolved.end)
        self._set_hover_point(self.point)
        for name, value in zip(
                ("xValue", "yValue", "zValue"),
                (self.point.x, self.point.y, self.point.z)):
            widget = getattr(self.ui, name, None)
            if widget is not None:
                widget.setText(App.Units.Quantity(value, App.Units.Length).UserString)
        self.column_panel.set_axis_length(resolved.end.sub(resolved.start).Length)
        _toolmsg("Eixo definido pela linha selecionada")
        return True

    def action(self, arg):
        if getattr(self, "axis_source", None) is not None:
            return None
        before = len(self.node)
        result = super().action(arg)
        # Draft Line makes its temporary object selectable again on every
        # mouse-button release. Snapper explicitly treats Selectable=False as
        # ineligible, so restore that preview-local invariant after all events.
        self._keep_preview_unsnappable()
        if self.is_active() and arg.get("Type") == "SoLocation2Event":
            # Line.action() has already passed this event through Draft's
            # getPoint/Snapper pipeline and stored the snapped result here.
            self._set_hover_point(self.point)
            return result
        if self.is_active() and before == 0 and len(self.node) == 1:
            self._confirm_base(self.node[0])
        return result

    def _keep_preview_unsnappable(self):
        obj = getattr(self, "obj", None)
        if obj is not None:
            obj.ViewObject.Selectable = False

    def numericInput(self, numx, numy, numz):
        if self.axis_source is not None:
            return None
        before = len(self.node)
        result = super().numericInput(numx, numy, numz)
        if self.is_active() and before == 0 and len(self.node) == 1:
            self._confirm_base(self.node[0])
        return result

    def drawUpdate(self, point):
        super().drawUpdate(point)
        self._set_hover_point(point)

    @staticmethod
    def _points_equal(first, second, tolerance=1e-7):
        if first is None or second is None:
            return first is second
        return first.sub(second).Length <= tolerance

    def _set_hover_point(self, point):
        if point is None:
            return False
        candidate = App.Vector(point)
        if self._points_equal(candidate, self._current_hover_point):
            return False
        self._current_hover_point = candidate
        self._update_preview()
        return True

    def _preview_options_changed(self, *_args):
        self._update_preview()

    def _update_preview(self):
        if not self.is_active() or self._current_hover_point is None or self.obj is None:
            return
        try:
            options = self.column_panel.profile_options
            source_geometry = resolve_axis_source(self.axis_source)
            if source_geometry is not None:
                start = App.Vector(source_geometry.start)
                end = App.Vector(source_geometry.end)
            else:
                point = self._current_hover_point
                start = App.Vector(point)
                end = start.add(App.Vector(0.0, 0.0, self.column_panel.height_value))
            self._preview_state = update_member_preview(
                self.obj, self._preview_state, options.profile_designation,
                start, end, options.insertion.currentText(),
                float(options.rotation.value()), options.rgb,
            )
        except (KeyError, RuntimeError, ValueError):
            self.obj.ViewObject.Visibility = False

    def _confirm_base(self, base):
        try:
            options = self.column_panel.creation_options(base)
        except Exception as exc:
            App.Console.PrintError(f"Steel Structures: erro ao criar pilar: {exc}\n")
            self.node = []
            return
        self._create_from_options(options)

    def _create_from_options(self, options):
        try:
            result = self.controller.create(options)
        except Exception as exc:
            App.Console.PrintError(f"Steel Structures: erro ao criar pilar: {exc}\n")
            self.node = []
            return False
        save_column_creation_settings(
            self.column_panel.creation_settings(self.ui.continueMode)
        )
        self.column_panel.creation_succeeded(result.next_default_name)
        if self.ui.continueMode:
            self._reset_for_continue()
        else:
            self._terminate_native_session()
        return True

    def _confirm_axis_source(self):
        resolved = resolve_axis_source(self.axis_source)
        if resolved is None:
            App.Console.PrintError("Steel Structures: a linha de origem está inválida.\n")
            self._terminate_native_session()
            return
        start = App.Vector(resolved.start)
        end = App.Vector(resolved.end)
        try:
            options = self.column_panel.axis_creation_options(
                start, end, CreationGeometryMode.SOURCE_AXIS
            )
        except Exception as exc:
            App.Console.PrintError(f"Steel Structures: erro ao criar pilar: {exc}\n")
            self._terminate_native_session()
            return
        if not self._create_from_options(options):
            self._terminate_native_session()

    def finish(self, cont=False, closed=False):
        if self._lifecycle_state in (TOOL_FINISHING, TOOL_FINISHED):
            return
        self._terminate_native_session()

    def _reset_for_continue(self):
        self.node = []
        self.point = None
        self.pos = []
        self.support = None
        self.constrain = None
        self.axis_source = None
        self.column_panel.clear_axis_source()
        for name in ("xValue", "yValue", "zValue"):
            widget = getattr(self.ui, name, None)
            if widget is not None and hasattr(widget, "setReadOnly"):
                widget.setReadOnly(False)
        accept = getattr(self.ui, "acceptPointInput", None)
        if callable(accept):
            accept()
        else:
            self.ui.mouse = True
        self.ui.mask = None
        if hasattr(Gui, "Snapper"):
            Gui.Snapper.mask = None
        self.ui.reset_ui_values()
        self._clear_hover_state()
        _toolmsg("Selecione o ponto da base do pilar")

    def _clear_hover_state(self):
        self._current_hover_point = None
        self._preview_state = PreviewState()
        obj = getattr(self, "obj", None)
        if obj is not None:
            obj.ViewObject.Visibility = False

    def _terminate_native_session(self):
        self._lifecycle_state = TOOL_FINISHING
        self._tool_active = False
        self._clear_hover_state()
        try:
            remove_source_axis_create_button(self._source_axis_button_binding)
            self._source_axis_button_binding = None
            call = getattr(self, "call", None)
            if call is not None:
                self.end_callbacks(call)
                self.call = None
            self.removeTemporaryObject()
            gui_base_original.Creator.finish(self)
            if App.activeDraftCommand is self:
                App.activeDraftCommand = None
            from ..init_gui import schedule_draft_snap_toolbar_visible
            schedule_draft_snap_toolbar_visible()
        finally:
            if self.controller is not None:
                self.controller.stop()
            self._lifecycle_state = TOOL_FINISHED
            self._notify_closed()

    def abort_activation(self, skip_native_ui_cleanup=False):
        if self._lifecycle_state == TOOL_FINISHED:
            self._notify_closed()
            return
        self._lifecycle_state = TOOL_FINISHING
        self._tool_active = False
        self._clear_hover_state()
        try:
            remove_source_axis_create_button(self._source_axis_button_binding)
            self._source_axis_button_binding = None
            call = getattr(self, "call", None)
            if call is not None:
                self.end_callbacks(call)
                self.call = None
            self.removeTemporaryObject()
            if not skip_native_ui_cleanup and App.activeDraftCommand is self:
                gui_base_original.Creator.finish(self)
            elif App.activeDraftCommand is self:
                App.activeDraftCommand = None
        finally:
            if self.controller is not None:
                self.controller.stop()
            self._lifecycle_state = TOOL_FINISHED
            self._notify_closed()

    def _notify_closed(self):
        if self._closed_notified:
            return
        self._closed_notified = True
        if self._on_closed is not None:
            self._on_closed(self)

    def removeTemporaryObject(self):
        self._current_hover_point = None
        self._preview_state = PreviewState()
        obj = getattr(self, "obj", None)
        if obj:
            try:
                name = obj.Name
            except ReferenceError:
                pass
            else:
                todo.ToDo.delay(self.doc.removeObject, name)
        self.obj = None


def draft_native_available():
    return bool(getattr(Gui, "draftToolBar", None))


__all__ = ["StructuralColumnDraftTool", "draft_native_available", "column_top"]
