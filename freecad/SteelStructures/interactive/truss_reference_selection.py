"""Scoped native selection acquisition; no document writes or session copies."""
from types import SimpleNamespace

import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtCore, QtGui
from shiboken6 import isValid


class TrussReferenceSelection:
    def __init__(self, panel, *, line_only=False):
        self.panel = panel
        self.document = panel.document
        self.line_only = line_only
        self.closed = False
        self.pending = False
        self.shortcut = None
        self.observing = False
        self.observing_document = False
        self.prompt = ("Clique em uma Linha Draft na vista. Esc cancela a seleção."
                       if line_only else
                       "Clique em uma Linha Draft ou aresta de Retângulo Draft. Esc cancela a seleção.")

    def start(self):
        # A valid preselection is still a shortcut, never a prerequisite.
        selection = Gui.Selection.getSelectionEx()
        if selection:
            try:
                self._adopt(selection)
            except (ValueError, RuntimeError, ReferenceError):
                pass
            else:
                self.close()
                return
        Gui.Selection.clearSelection()
        self.shortcut = QtGui.QShortcut(QtGui.QKeySequence("Escape"), self.panel.form)
        self.shortcut.setContext(QtCore.Qt.WindowShortcut)
        self.shortcut.activated.connect(self.cancel)
        Gui.Selection.addObserver(self)
        self.observing = True
        App.addDocumentObserver(self)
        self.observing_document = True
        self.panel._sync_reference_source()

    def _adopt(self, selection):
        panel = self.panel
        panel.session.assert_context(self.document, panel.controller.object)
        panel.controller._assert_active_document()
        panel.controller.bind_session(panel.session.config)
        selected = panel.controller.selected_reference(selection)
        if self.line_only and selected["reference_mode"] != "DraftLine":
            raise ValueError("Selecione uma Linha Draft simples; arestas de sólidos e perfis ainda não são suportadas.")
        # The legacy rectangle mode derives an envelope, not a generic line.
        # Acquisition must nevertheless require the user to choose its base.
        if selected["reference_mode"] == "DraftRectangle" and not selection[0].SubElementNames:
            raise ValueError("Clique explicitamente na aresta de base do Retângulo Draft.")
        panel._adopt_selected_reference(selected)

    def addSelection(self, document_name, object_name, subelement="", _point=None):
        if self.closed or self.pending:
            return
        if document_name != self.document.Name:
            self._message("Selecione uma fonte no documento da treliça. Esc cancela a seleção.")
            return
        # Use the exact event's SelectionEx entry, not every previously selected
        # object. Invalid clicks may remain selected in the native viewport.
        for item in Gui.Selection.getSelectionEx():
            if (item.Object.Document is self.document and item.Object.Name == object_name
                    and (not subelement or subelement in item.SubElementNames)):
                selected = SimpleNamespace(Object=item.Object,
                                           SubElementNames=(subelement,) if subelement else ())
                self.pending = True
                # Never change panel widgets/previews during native selection dispatch.
                QtCore.QTimer.singleShot(0, lambda: self._receive([selected]))
                return

    def _receive(self, selection):
        if self.closed:
            return
        self.pending = False
        try:
            self._adopt(selection)
        except (ValueError, RuntimeError, ReferenceError) as exc:
            self._message(str(exc) + " Esc cancela a seleção.")
            return
        self.close()

    def _message(self, text):
        self.prompt = text
        self.panel._sync_reference_source()

    def cancel(self):
        self.close()

    def slotActivateDocument(self, document):
        if document is not self.document:
            self.close()

    def slotDeletedDocument(self, document):
        if document is self.document:
            self.close(refresh=False)

    def close(self, *, refresh=True):
        if self.closed:
            return
        self.closed = True
        if self.observing:
            Gui.Selection.removeObserver(self)
            self.observing = False
        if self.observing_document:
            App.removeDocumentObserver(self)
            self.observing_document = False
        shortcut, self.shortcut = self.shortcut, None
        if shortcut is not None and isValid(shortcut):
            shortcut.setEnabled(False)
            shortcut.activated.disconnect(self.cancel)
            shortcut.deleteLater()
        panel, self.panel = self.panel, None
        if getattr(panel, "_reference_selection", None) is self:
            panel._reference_selection = None
        if refresh and not panel._closed and not panel._suspended and panel.form is not None:
            panel._sync_reference_source()
