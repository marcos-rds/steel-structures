# SPDX-License-Identifier: LGPL-2.1-or-later
"""Command-owned shortcuts; editable fields retain their normal text input."""

from PySide import QtCore, QtGui, QtWidgets


def draft_shortcut_keys():
    """Read Draft preferences instead of hardcoding its in-command letters."""
    from draftutils import params
    actions = ("Relative", "Global", "Continue", "Undo", "Close", "Wipe",
               "Length", "RestrictX", "RestrictY", "RestrictZ", "MakeFace",
               "Exit", "AddHold", "CycleSnap", "Recenter", "Snap", "Copy",
               "SetWP", "SelectEdge", "SubelementMode", "IncreaseRadius", "DecreaseRadius")
    return {action: str(params.get_param("inCommandShortcut" + action) or "").upper()
            for action in actions}


def editable_focus(widget):
    while widget is not None:
        if (isinstance(widget, (QtWidgets.QLineEdit, QtWidgets.QAbstractSpinBox,
                                QtWidgets.QTextEdit, QtWidgets.QPlainTextEdit))
                or (isinstance(widget, QtWidgets.QComboBox) and widget.isEditable())):
            return True
        widget = widget.parentWidget()
    return False


def point_shortcut_key(keys):
    """Choose an unused vertex key without overriding Draft preferences."""
    return next((key for key in ("P", "V") if key not in keys.values()), "")


class DraftCoordinateFocus(QtCore.QObject):
    """Distinguish explicit editing from Draft's displayPoint focus changes.

    These filters belong only to this command's native coordinate fields. Only
    bound action letters in graphical mode are consumed; numeric input and
    Draft's mouse acquisition contract remain native.
    """

    def __init__(self, fields, changed, run_key=lambda key, repeat=False: False):
        super().__init__()
        self.fields = tuple(fields)
        self.changed = changed
        self.run_key = run_key
        self.editing = False
        self.disposed = False
        for field in self.fields:
            field.installEventFilter(self)

    def set_editing(self, editing):
        if not self.disposed and self.editing != editing:
            self.editing = editing
            self.changed()

    def protects(self, widget):
        current = widget
        while current is not None:
            if current in self.fields:
                return self.editing
            current = current.parentWidget()
        return editable_focus(widget)

    def eventFilter(self, watched, event):
        if not self.disposed:
            if (event.type() == QtCore.QEvent.KeyPress and not self.editing
                    and event.modifiers() in (QtCore.Qt.NoModifier, QtCore.Qt.KeypadModifier)):
                # InputField can accept ShortcutOverride before QShortcut sees
                # a letter. Dispatch through the SAME guarded binding only if
                # Qt delivered KeyPress here. A successful QShortcut consumes
                # its event first, so these paths cannot execute twice.
                if self.run_key(event.text().upper(), event.isAutoRepeat()):
                    return True
            elif event.type() == QtCore.QEvent.MouseButtonPress:
                self.set_editing(True)
            elif event.type() == QtCore.QEvent.FocusIn and event.reason() in (
                    QtCore.Qt.MouseFocusReason, QtCore.Qt.TabFocusReason,
                    QtCore.Qt.BacktabFocusReason):
                self.set_editing(True)
        return False

    def dispose(self):
        self.disposed = True
        for field in self.fields:
            try:
                field.removeEventFilter(self)
            except RuntimeError:
                pass
        self.fields = ()


class PanelShortcuts:
    """Window shortcuts parented to a task widget, disabled while typing."""

    def __init__(self, parent, is_active=lambda: True, is_editing=editable_focus):
        self.parent = parent
        self.is_active = is_active
        self.is_editing = is_editing
        self._bindings = []
        self._disposed = False
        self._app = QtWidgets.QApplication.instance()
        self._app.focusChanged.connect(self._focus_changed)
        self.parent.destroyed.connect(self.dispose)

    def bind(self, control, key, callback=None, label=None):
        if label is not None:
            control.setText(label)
        if not key or any(existing[2] == key for existing in self._bindings):
            return False
        shortcut = QtGui.QShortcut(QtGui.QKeySequence(key), self.parent)
        shortcut.setContext(QtCore.Qt.WindowShortcut)
        shortcut.setAutoRepeat(False)
        callback = callback or control.click

        def activate():
            if (not self._disposed and self.is_active() and control.isEnabled()
                    and control.isVisible() and not self.is_editing(self._app.focusWidget())):
                callback()

        shortcut.activated.connect(activate)
        self._bindings.append((shortcut, activate, key))
        if label is not None:
            control.setText("%s (%s)" % (label, key))
        self._focus_changed(None, self._app.focusWidget())
        return True

    def run_key(self, key, repeat=False):
        """Fallback for native InputField's accepted ShortcutOverride events."""
        for _shortcut, activate, bound_key in self._bindings:
            if key == bound_key:
                if not repeat:
                    activate()
                return True
        return False

    def _focus_changed(self, _old, current):
        enabled = not self._disposed and not self.is_editing(current)
        for shortcut, _callback, _key in self._bindings:
            shortcut.setEnabled(enabled)

    def refresh(self):
        self._focus_changed(None, self._app.focusWidget())

    def dispose(self, *_args):
        if self._disposed:
            return
        self._disposed = True
        try:
            self._app.focusChanged.disconnect(self._focus_changed)
        except (RuntimeError, TypeError):
            pass
        try:
            self.parent.destroyed.disconnect(self.dispose)
        except (RuntimeError, TypeError):
            pass
        for shortcut, callback, _key in self._bindings:
            try:
                shortcut.setEnabled(False)
                shortcut.activated.disconnect(callback)
                shortcut.deleteLater()
            except RuntimeError:
                pass  # Parent destruction already disconnected its children.
        self._bindings.clear()
