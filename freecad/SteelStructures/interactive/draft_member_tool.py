# SPDX-License-Identifier: LGPL-2.1-or-later
"""Structural member acquisition based directly on FreeCAD Draft Line."""

import FreeCAD as App
from FreeCAD import Gui
from PySide import QtCore, QtGui
from draftguitools import gui_base_original, gui_lines
from draftutils import gui_utils, todo
from draftutils.messages import _toolmsg

from .member_controller import CreationGeometryMode, MemberController
from .member_creation_preview import (
    PreviewState, configure_preview_object, update_member_preview,
)
from .axis_source_widget import (
    AxisSourceWidget, configure_source_axis_draft_ui,
    install_source_axis_create_button, remove_source_axis_create_button,
)
from .profile_options_widget import ProfileOptionsWidget
from ..member_axis_source import resolve_axis_source
from ..paths import MEMBER_ICON
from ..preferences import load_member_creation_settings, save_member_creation_settings


TOOL_NEW = "NEW"
TOOL_ACTIVE = "ACTIVE"
TOOL_FINISHING = "FINISHING"
TOOL_FINISHED = "FINISHED"


class StructuralMemberDraftTool(gui_lines.Line):
    """Use Draft Line's UI/events/preview and replace only final creation."""

    def __init__(self, on_closed=None):
        super().__init__(mode="line")
        self._on_closed = on_closed
        self.profile_options = None
        self.controller = None
        self._task_icon = MEMBER_ICON
        self._last_input_stage = None
        self._stage_update_pending = False
        self._stage_generation = 0
        self._tool_active = False
        self._lifecycle_state = TOOL_NEW
        self._closed_notified = False
        self.axis_source = None
        self.axis_source_controls = None
        self._source_axis_button_binding = None
        self._preview_state = PreviewState()

    def is_active(self):
        """Return whether this exact native Line instance owns the session."""
        return self._lifecycle_state == TOOL_ACTIVE and self._tool_active

    def Activated(self, name="StructuralMember", icon=None, task_title=None,
                  axis_source=None):
        if self._lifecycle_state != TOOL_NEW:
            raise RuntimeError(
                f"StructuralMemberDraftTool cannot activate from {self._lifecycle_state}"
            )
        self._lifecycle_state = TOOL_ACTIVE
        # Line.Activated has no `extra` argument. Creator performs the native
        # command setup; lineUi below remains the installed Draft implementation.
        # "Line" is the registered key expected by Draft's ContinueMode table.
        gui_base_original.Creator.Activated(self, "Line")
        self._stage_generation += 1
        self._stage_update_pending = False
        self._tool_active = True
        self.controller = MemberController(self.doc)
        self.controller.start()
        self.profile_options = ProfileOptionsWidget(self.doc)
        self.axis_source = axis_source if resolve_axis_source(axis_source) else None
        self.axis_source_controls = AxisSourceWidget(self.axis_source)
        self.axis_source_controls.linkChanged.connect(self._axis_link_changed)
        self.profile_options.layout().insertWidget(0, self.axis_source_controls)
        self.axis_source_controls.setVisible(self.axis_source is not None)
        self.profile_options.apply_creation_settings(load_member_creation_settings())
        self.ui.lineUi(title="Criar elemento estrutural", icon="Draft_Draft",
                       extra=self.profile_options)
        self._task_icon = icon or MEMBER_ICON
        self.ui.baseWidget.setWindowTitle("Criar elemento estrutural")
        self.ui.baseWidget.setWindowIcon(QtGui.QIcon(self._task_icon))
        self._last_input_stage = None
        self._update_point_input_stage()
        self._schedule_stage_update()
        if self.axis_source is not None:
            configure_source_axis_draft_ui(self.ui)
            QtCore.QTimer.singleShot(100, self._install_source_axis_create_button)
            self.obj = self.doc.addObject(
                "Part::Feature", "SteelStructuresMemberPreview"
            )
            configure_preview_object(self.obj)
            self._connect_source_axis_preview()
            self._update_source_axis_preview()
            self.call = None
            _toolmsg("Eixo definido pela linha selecionada")
        else:
            self.ui.continueMode = True
            self.ui.continueCmd.setChecked(self.ui.continueMode)
            self.obj = self.doc.addObject("Part::Feature", "SteelStructuresDraftPreview")
            gui_utils.format_object(self.obj)
            self.obj.ViewObject.ShowInTree = False
            self.call = self.view.addEventCallback("SoEvent", self.action)
            _toolmsg("Selecione o primeiro ponto")

    def _axis_link_changed(self, linked):
        # In SourceAxis this choice controls only future associativity.
        self._update_source_axis_preview()

    def _connect_source_axis_preview(self):
        for signal in (
                self.profile_options.category.currentTextChanged,
                self.profile_options.series.currentTextChanged,
                self.profile_options.profile.currentIndexChanged,
                self.profile_options.insertion.currentIndexChanged,
                self.profile_options.rotation.valueChanged,
                self.profile_options.colorChanged):
            signal.connect(self._preview_options_changed)

    def _preview_options_changed(self, *_args):
        self._update_source_axis_preview()

    def _update_source_axis_preview(self):
        if not self.is_active() or self.axis_source is None or self.obj is None:
            return False
        resolved = resolve_axis_source(self.axis_source)
        if resolved is None:
            self.removeTemporaryObject()
            return False
        try:
            self._preview_state = update_member_preview(
                self.obj, self._preview_state,
                self.profile_options.profile_designation,
                resolved.start, resolved.end,
                self.profile_options.insertion.currentText(),
                float(self.profile_options.rotation.value()),
                self.profile_options.rgb,
            )
        except (KeyError, RuntimeError, ValueError):
            self.removeTemporaryObject()
            return False
        return True

    def _install_source_axis_create_button(self):
        if not self.is_active() or self._source_axis_button_binding is not None:
            return
        self._source_axis_button_binding = install_source_axis_create_button(
            self.ui, self._confirm_axis_source
        )

    def _confirm_axis_source(self):
        resolved = resolve_axis_source(self.axis_source)
        if resolved is None:
            App.Console.PrintError("Steel Structures: a linha de origem está inválida.\n")
            self._terminate_native_session()
            return False
        linked = self.axis_source_controls.linked
        try:
            options = self.profile_options.creation_options(
                resolved.start, resolved.end, self.axis_source, linked,
                CreationGeometryMode.SOURCE_AXIS,
            )
            result = self.controller.create(options)
        except Exception as exc:
            App.Console.PrintError(f"Steel Structures: erro ao criar elemento: {exc}\n")
            self._terminate_native_session()
            return False
        save_member_creation_settings(self.profile_options.creation_settings())
        self.profile_options.creation_succeeded(result.next_default_name)
        self._terminate_native_session()
        return True

    def _apply_point_stage_ui(self):
        """Apply one coherent title/icon/control state to Draft's own widgets."""
        if App.activeDraftCommand is not self or self.ui is None:
            return
        first = len(self.node) == 0
        stage = "first" if first else "next"
        if first:
            _toolmsg("Selecione o primeiro ponto")
        else:
            _toolmsg("Selecione o próximo ponto")

        for name in ("labellength", "lengthValue", "labelangle", "angleValue", "angleLock"):
            widget = getattr(self.ui, name, None)
            if widget is not None:
                widget.setVisible(not first)
        self._last_input_stage = stage

    def _update_point_input_stage(self):
        """Synchronize the native point-entry presentation with Line.node."""
        if App.activeDraftCommand is not self or self.ui is None:
            return
        first = len(self.node) == 0
        stage = "first" if first else "next"
        if stage == self._last_input_stage:
            return
        self._apply_point_stage_ui()

    def _schedule_stage_update(self):
        """Consolidate stage synchronization after Draft finishes its event."""
        if not self._tool_active or self._stage_update_pending:
            return
        self._stage_update_pending = True
        generation = self._stage_generation
        QtCore.QTimer.singleShot(0, lambda: self._run_stage_update(generation))

    def _run_stage_update(self, generation):
        if generation != self._stage_generation:
            return
        self._stage_update_pending = False
        if not self._tool_active or App.activeDraftCommand is not self:
            return
        self._last_input_stage = None
        self._update_point_input_stage()

    def action(self, arg):
        result = super().action(arg)
        self._schedule_stage_update()
        return result

    def numericInput(self, numx, numy, numz):
        result = super().numericInput(numx, numy, numz)
        self._schedule_stage_update()
        return result

    def drawUpdate(self, point):
        super().drawUpdate(point)
        self._schedule_stage_update()

    def finish(self, cont=False, closed=False):
        if self._lifecycle_state in (TOOL_FINISHING, TOOL_FINISHED):
            return
        if self._lifecycle_state != TOOL_ACTIVE:
            raise RuntimeError(
                f"StructuralMemberDraftTool cannot finish from {self._lifecycle_state}"
            )
        continue_requested = bool(cont or (cont is None and self.ui and self.ui.continueMode))
        points = list(self.node)
        controls = getattr(self, "axis_source_controls", None)
        linked = bool(controls and controls.linked)
        if linked:
            resolved = resolve_axis_source(self.axis_source)
            if resolved is not None:
                points = [App.Vector(resolved.start), App.Vector(resolved.end)]
        created = False
        if len(points) == 2 and self.profile_options is not None:
            try:
                source = getattr(self, "axis_source", None)
                if source is None:
                    options = self.profile_options.creation_options(points[0], points[1])
                else:
                    options = self.profile_options.creation_options(
                        points[0], points[1], source, linked
                    )
                result = self.controller.create(options)
            except Exception as exc:
                App.Console.PrintError(f"Steel Structures: erro ao criar elemento: {exc}\n")
            else:
                save_member_creation_settings(self.profile_options.creation_settings())
                self.profile_options.creation_succeeded(result.next_default_name)
                created = True
        if created and continue_requested:
            self._reset_segment_for_continue()
            return
        self._terminate_native_session()

    def _reset_segment_for_continue(self):
        """Acquire another member without closing or rebuilding Draft's UI."""
        self.node = []
        self.point = None
        self.pos = []
        self.support = None
        self.constrain = None
        self.axis_source = None
        if self.axis_source_controls is not None:
            self.axis_source_controls.clear_source()
        for name in ("xValue", "yValue", "zValue"):
            widget = getattr(self.ui, name, None)
            if widget is not None and hasattr(widget, "setReadOnly"):
                widget.setReadOnly(False)

        accept_point_input = getattr(self.ui, "acceptPointInput", None)
        if callable(accept_point_input):
            accept_point_input()
        else:
            # FreeCAD 1.1.3 exposes the input-ready state directly.
            self.ui.mouse = True
        self.ui.mask = None
        self.ui.alock = False
        if hasattr(Gui, "Snapper"):
            Gui.Snapper.mask = None
        angle_lock = getattr(self.ui, "angleLock", None)
        if angle_lock is not None:
            angle_lock.setChecked(False)
        self.ui.reset_ui_values()

        zero_length = App.Units.Quantity(0, App.Units.Length).UserString
        zero_angle = App.Units.Quantity(0, App.Units.Angle).UserString
        for name in ("xValue", "yValue", "zValue", "lengthValue"):
            widget = getattr(self.ui, name, None)
            if widget is not None:
                blocked = widget.blockSignals(True)
                try:
                    if name in ("xValue", "yValue", "zValue"):
                        widget.setEnabled(True)
                    widget.setText(zero_length)
                finally:
                    widget.blockSignals(blocked)
        angle_value = getattr(self.ui, "angleValue", None)
        if angle_value is not None:
            blocked = angle_value.blockSignals(True)
            try:
                angle_value.setText(zero_angle)
            finally:
                angle_value.blockSignals(blocked)

        if self.obj is not None:
            self.obj.ViewObject.Visibility = False
        self._stage_generation += 1
        self._stage_update_pending = False
        self._last_input_stage = None
        self._apply_point_stage_ui()
        _toolmsg("Selecione o primeiro ponto")
        self.update_hints()

    def _terminate_native_session(self):
        """Perform the terminal Draft cleanup exactly once."""
        self._lifecycle_state = TOOL_FINISHING
        self._tool_active = False
        self._stage_generation += 1
        self._stage_update_pending = False
        try:
            remove_source_axis_create_button(self._source_axis_button_binding)
            self._source_axis_button_binding = None
            self.end_callbacks(self.call)
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
        """Release a partially initialized native session without fallback."""
        if self._lifecycle_state == TOOL_FINISHED:
            self._notify_closed()
            return
        self._lifecycle_state = TOOL_FINISHING
        self._tool_active = False
        self._stage_generation += 1
        self._stage_update_pending = False
        try:
            remove_source_axis_create_button(self._source_axis_button_binding)
            self._source_axis_button_binding = None
            call = getattr(self, "call", None)
            if call is not None:
                self.end_callbacks(call)
                self.call = None
            self.removeTemporaryObject()
            if (not skip_native_ui_cleanup and App.activeDraftCommand is self
                    and getattr(self, "ui", None) is not None):
                gui_base_original.Creator.finish(self)
            elif App.activeDraftCommand is self:
                App.activeDraftCommand = None
        finally:
            controller = getattr(self, "controller", None)
            if controller is not None:
                controller.stop()
            self._lifecycle_state = TOOL_FINISHED
            self._notify_closed()

    def _notify_closed(self):
        if self._closed_notified:
            return
        self._closed_notified = True
        if self._on_closed is not None:
            self._on_closed(self)

    def removeTemporaryObject(self):
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
