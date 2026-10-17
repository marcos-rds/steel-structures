"""One native Draft Line operation over a suspended truss editing session.

No registered commands, preference changes or alternative point acquisition.
Draft owns creation/Undo; the existing controller still owns truss application.
"""
from copy import deepcopy
from uuid import uuid4

import FreeCAD as App
import FreeCADGui as Gui
from draftguitools.gui_lines import Line
from draftutils import params, todo

from ..member_axis_source import is_draft_line
from ..truss_reference import source_geometry


_operations = {}


def in_document(token):
    """Do not execute a queued native macro in a different/closed document."""
    operation = _operations.get(token)
    return bool(operation is not None and not operation.abandoned
                and App.ActiveDocument is operation.document
                and operation.controller._document_is_open())


def deliver(token, line):
    """Receive the exact result inside Draft's original creation transaction."""
    operation = _operations.get(token)
    if operation is not None:
        operation.result = line


class ReferenceLine(Line):
    def __init__(self, operation):
        super().__init__(mode="line")
        self.operation = operation
        self.finishing = False
        self.creation_queued = False

    def commit(self, name, commands):
        # 'line' is the result variable of Line.finish's native macro commands.
        # Deliver before its final recompute; do not inspect Selection/Objects.
        commands = list(commands)
        commands.insert(-1,
            "__import__('freecad.SteelStructures.interactive.truss_draft_reference', "
            "fromlist=['deliver']).deliver(" + repr(self.operation.token) + ", line)")
        guard = ("if __import__('freecad.SteelStructures.interactive.truss_draft_reference', "
                 "fromlist=['in_document']).in_document(" + repr(self.operation.token) + "):\n    ")
        commands = [guard + command for command in commands]
        self.creation_queued = True
        # Dispatch in the native itinerary before it opens any transaction.
        # A last-document close can otherwise make ToDo openTransaction(None)
        # before even our first guarded instruction is reached.
        todo.ToDo.delay(self._queue_creation, (name, commands))

    def _queue_creation(self, payload):
        name, commands = payload
        if in_document(self.operation.token):
            # Preserve Draft's transaction followed by its deferred recompute.
            todo.ToDo.delayCommit([(name, commands[:-1])])
            todo.ToDo.delayAfter(Gui.doCommand, commands[-1])
        todo.ToDo.delayAfter(self.operation.complete, None)

    def end_callbacks(self, call):
        if call is not None:
            super().end_callbacks(call)

    def removeTemporaryObject(self):
        # Draft queues a bound Document.removeObject; that document may close
        # before the queue executes. Keep the same deferred cleanup, scoped.
        obj, self.obj = self.obj, None
        if obj is not None:
            todo.ToDo.delay(self._remove_temporary, obj)

    def _remove_temporary(self, obj):
        if self.operation.controller._document_is_open():
            try:
                if self.operation.document.getObject(obj.Name) is obj:
                    self.operation.document.removeObject(obj.Name)
            except ReferenceError:
                pass  # The preview was already removed by document/Undo cleanup.

    def finish(self, cont=False, closed=False):
        if self.finishing:
            return
        self.finishing = True
        try:
            # This operation creates one reference, regardless of ContinueMode.
            super().finish(cont=False, closed=False)
        finally:
            # Native numericInput still accesses its UI after finish returns.
            # This queue runs after removal, creation and native recompute.
            if not self.creation_queued:
                todo.ToDo.delayAfter(self.operation.complete, None)


class ReferenceLineOperation:
    def __init__(self, panel):
        self.panel = panel
        self.controller = panel.controller
        self.document = panel.document
        self.session = panel.session
        self.config = deepcopy(panel.get_config())
        self.preview3d = panel.show_3d.isChecked()
        self.token = uuid4().hex
        self.result = None
        self.tool = ReferenceLine(self)
        self.abandoned = False
        self.completed = False
        self.failure = ""

    def start(self):
        self.controller._assert_active_document()
        self.controller.bind_session(self.config)
        self.session.replace_config(self.config)
        self.panel._preview_timer.stop()
        self.controller.cancel_picker()
        self.controller.remove_preview()
        self.panel._point_generation += 1
        self.panel._suspended = True
        _operations[self.token] = self
        App.addDocumentObserver(self)
        if App.activeDraftCommand is self.panel:
            App.activeDraftCommand = None
        # closeDialog destroys these widgets. Never retain/reparent/reuse them.
        Gui.Control.closeDialog()
        try:
            self.tool.Activated()
            Gui.draftToolBar.baseWidget.destroyed.connect(self._draft_form_destroyed)
        except Exception as exc:
            # Native setup can fail before installing callbacks/temporary object.
            # Finish only initialized resources, preserving the original error.
            self.failure = "Falha ao iniciar Linha Draft: " + str(exc)
            App.Console.PrintError(self.failure + "\n")
            if hasattr(self.tool, "ui"):
                self.tool.node = []
                self.tool.finish()
            else:
                todo.ToDo.delayAfter(self.complete, None)
            raise

    def _draft_form_destroyed(self, *_args):
        if not self.tool.finishing and not self.completed:
            # External Task View closure must not resurrect the generator.
            self.abandoned = True
            todo.ToDo.delayAfter(self._abort, None)

    def _abort(self):
        if self.completed:
            return
        self.abandoned = True
        if App.activeDraftCommand is self.tool:
            self.tool.node = []
            self.tool.finish()
        else:
            self.complete()

    def slotActivateDocument(self, document):
        if document is not self.document:
            self._abort()

    def slotDeletedDocument(self, document):
        if document is self.document:
            self.controller._document_deleted = True
            self._abort()

    def complete(self):
        if self.completed:
            return
        self.completed = True
        _operations.pop(self.token, None)
        App.removeDocumentObserver(self)
        panel = self.panel
        if (self.abandoned or panel._closed or self.session.closed
                or not self.controller._document_is_open()
                or App.ActiveDocument is not self.document
                or App.activeDraftCommand is not None or Gui.Control.activeDialog()):
            panel._finish(cancel=True, external=True)
            return
        try:
            self.session.assert_context(self.document, self.controller.object)
        except (ValueError, RuntimeError, ReferenceError):
            panel._finish(cancel=True, external=True)
            return

        config = deepcopy(self.config)
        diagnostic = self.failure
        line = self.result
        if line is not None:
            try:
                if (line.Document is not self.document
                        or self.document.getObject(line.Name) is not line or not is_draft_line(line)):
                    raise ValueError("A linha criada não está disponível como referência Draft.")
                import WorkingPlane
                plane = WorkingPlane.get_working_plane()
                values = source_geometry(line, "DraftLine", "Edge1", config["plane_normal"], list(plane.v))
                config.update(values)
                config.update(reference_mode="DraftLine", reference_source=line.Name,
                              reference_edge="Edge1", reference_linked=True, reference_defined=True)
            except (ValueError, RuntimeError, ReferenceError) as exc:
                diagnostic = str(exc)
        # Preserve baseline/AppliedState/last_candidate and persistence conflicts.
        # Only the candidate reference is changed; no controller.apply call here.
        self.session.replace_config(config)
        panel._closed = True
        panel._on_close = None
        from .truss_controller import _show_truss_panel
        try:
            restored = _show_truss_panel(self.controller, config, session=self.session)
            restored.show_3d.setChecked(self.preview3d)
            if diagnostic:
                restored._show_error(diagnostic)
        except Exception:
            self.controller.cancel()
            from . import truss_controller
            truss_controller._active_panel = None
            raise


def start_reference_line(panel):
    if params.get_param("UsePartPrimitives"):
        raise ValueError("Desative 'Usar primitivas Part' nas preferências Draft para criar uma linha associativa.")
    if panel._topology_editor is not None:
        raise ValueError("Feche o Editor de Treliças antes de desenhar a referência.")
    operation = ReferenceLineOperation(panel)
    operation.start()
    return operation
