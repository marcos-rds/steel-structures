# SPDX-License-Identifier: LGPL-2.1-or-later
"""Exclusive, temporary planar-face selection between point sessions.

No Coin callback or Draft snapper belongs to this panel. The session owner
must finish point acquisition before starting it.
"""
import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtCore, QtGui, QtWidgets
from shiboken6 import isValid
from draftutils import gui_utils

from ..plate_planes import selected_plane_face, placement_from_face


class PlateFaceSelection(QtCore.QObject):
    def __init__(self, document, view, on_closed):
        super().__init__()
        self.document = document
        self._document_name = document.Name
        self.view = view
        self.on_closed = on_closed
        self._closed = False
        self._finishing = False
        self._selection_observer = False
        self._document_observer = False
        self._escape_shortcut = None
        self._mdi = self._owner_window = self._task_box = None
        self.form = QtWidgets.QWidget()
        self.form.setWindowTitle("Selecionar face — Chapa Estrutural")
        layout = QtWidgets.QVBoxLayout(self.form)
        self.form.setToolTip("A face plana será usada somente como plano, sem vínculo.")
        self.status = QtWidgets.QLabel("Selecione uma face.")
        self.status.setWordWrap(True)
        self.status.setStyleSheet("color: palette(mid);")
        layout.addStretch(1)
        layout.addWidget(self.status)

    def getStandardButtons(self):
        buttons = getattr(QtWidgets.QDialogButtonBox, "StandardButton",
                          QtWidgets.QDialogButtonBox)
        flag = buttons.Cancel
        return int(getattr(flag, "value", flag))

    def reject(self):
        self._schedule_finish()
        return True

    def _owner_alive(self):
        if App.listDocuments().get(self._document_name) is not self.document:
            return False
        try:
            return self.view in Gui.getDocument(self._document_name).mdiViewsOfType(
                "Gui::View3DInventor")
        except (RuntimeError, ReferenceError, NameError):
            return False

    def start(self):
        if self._closed or self._finishing or self._selection_observer:
            return
        if (not self._owner_alive() or gui_utils.get_3d_view() != self.view
                or getattr(App, "activeDraftCommand", None) or Gui.Control.activeDialog()):
            self.finish()
            return
        try:
            App.addDocumentObserver(self)
            self._document_observer = True
            self.form.destroyed.connect(self._form_destroyed)
            self._mdi = Gui.getMainWindow().findChild(QtWidgets.QMdiArea)
            if self._mdi is not None:
                self._owner_window = self._mdi.activeSubWindow()
                if self._owner_window is not None:
                    self._owner_window.installEventFilter(self)
                self._mdi.subWindowActivated.connect(self._view_changed)
            Gui.Control.showDialog(self)
            self._attach_task_guard()
            # A TaskPanel's standard Cancel button does not receive Esc while
            # the 3D viewport has focus. Scope this shortcut to the panel's
            # containing window and lifetime, without a keyboard event filter.
            self._escape_shortcut = QtGui.QShortcut(QtGui.QKeySequence("Escape"), self.form)
            self._escape_shortcut.setContext(QtCore.Qt.WindowShortcut)
            self._escape_shortcut.activated.connect(self._schedule_finish)
            # Clear earlier preselection/selection before observing new clicks.
            Gui.Selection.clearSelection()
            Gui.Selection.addObserver(self)
            self._selection_observer = True
        except Exception:
            self.finish()
            raise

    def _attach_task_guard(self):
        widget = self.form
        while widget is not None and not widget.inherits("Gui::TaskView::TaskBox"):
            widget = widget.parentWidget()
        self._task_box = widget
        if widget is not None:
            widget.installEventFilter(self)

    def addSelection(self, document_name, _object_name, _subelement="", _point=None):
        if self._closed or self._finishing:
            return
        if not self._owner_alive() or gui_utils.get_3d_view() != self.view:
            self._schedule_finish()
            return
        if document_name != self._document_name:
            self.status.setText("Selecione uma face plana no documento da chapa.")
            return
        try:
            reference = selected_plane_face(Gui.Selection.getSelectionEx(), self.document)
            if reference is None:
                raise ValueError("Selecione somente uma face plana, explicitamente.")
            placement = placement_from_face(reference)
            snapshot = App.Placement(placement.Base, placement.Rotation)
        except (ValueError, RuntimeError, ReferenceError, TypeError) as exc:
            self.status.setText(str(exc))
            return
        self.status.setText("Plano definido.")
        self._schedule_finish(reference, snapshot)

    def _schedule_finish(self, reference=None, placement=None):
        if self._closed or self._finishing:
            return
        # Late observer notifications become inert before the native selection
        # dispatch returns. UI close and point-session restart happen afterward.
        self._finishing = True
        QtCore.QTimer.singleShot(0, lambda: self._finish_now(reference, placement))

    def _view_changed(self, *_args):
        if gui_utils.get_3d_view() != self.view:
            self._schedule_finish()

    def slotDeletedDocument(self, document):
        if document is self.document:
            self._schedule_finish()

    def eventFilter(self, watched, event):
        if (event.type() == QtCore.QEvent.Close
                or (watched is self._task_box and event.type() == QtCore.QEvent.Hide)):
            self._schedule_finish()
        return False

    def _form_destroyed(self, *_args):
        self.form = None
        self._schedule_finish()

    def _owns_dialog(self):
        widget = self._task_box
        if widget is None or not isValid(widget):
            return False
        parent = widget.parentWidget()
        return (parent is not None and parent.inherits("Gui::TaskView::TaskPanel")
                and parent.layout() is not None and parent.layout().indexOf(widget) >= 0
                and widget.isVisibleTo(parent))

    def finish(self):
        """Cancel immediately when invoked by the outer session owner."""
        self._finish_now(None, None)

    def _finish_now(self, reference, placement):
        if self._closed:
            return
        self._closed = self._finishing = True
        shortcut, self._escape_shortcut = self._escape_shortcut, None
        if shortcut is not None and isValid(shortcut):
            shortcut.setEnabled(False)
            try:
                shortcut.activated.disconnect(self._schedule_finish)
            except (RuntimeError, TypeError):
                pass
            shortcut.deleteLater()
        if self._selection_observer:
            Gui.Selection.removeObserver(self)
            self._selection_observer = False
        if self._document_observer:
            App.removeDocumentObserver(self)
            self._document_observer = False
        if self._mdi is not None and isValid(self._mdi):
            try:
                self._mdi.subWindowActivated.disconnect(self._view_changed)
            except (RuntimeError, TypeError):
                pass
        for widget in (self._owner_window, self._task_box):
            if widget is not None and isValid(widget):
                widget.removeEventFilter(self)
        if self.form is not None and isValid(self.form):
            try:
                self.form.destroyed.disconnect(self._form_destroyed)
            except (RuntimeError, TypeError):
                pass
        # Never close a replacement task dialog or dereference a dead 3D view.
        if self._owns_dialog():
            Gui.Control.closeDialog()
        self._mdi = self._owner_window = self._task_box = None
        callback, self.on_closed = self.on_closed, None
        if callback is not None:
            callback(self, reference, placement)
