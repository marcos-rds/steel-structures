# SPDX-License-Identifier: LGPL-2.1-or-later
"""Compact controls for creation from one preselected Draft Line."""

from PySide import QtCore, QtWidgets


_SOURCE_AXIS_HIDDEN_CONTROLS = (
    "promptlabel", "cmdlabel", "labelx", "xValue", "labely", "yValue",
    "labelz", "zValue", "addButton", "textValue", "textButton",
    "labellength", "lengthValue", "labelangle", "angleLock", "angleValue",
    "numfaceslabel", "numFaces", "labelRadius", "radiusValue", "undoButton",
    "wipeButton", "orientWPButton", "selectButton", "isRelative", "isGlobal",
    "makeFace", "continueCmd", "chainedModeCmd", "occOffset", "isCopy",
    "isSubelementMode",
)


def configure_source_axis_draft_ui(ui):
    """Keep only Draft's standard confirm/cancel actions for a resolved axis."""
    base = ui.baseWidget
    for name in _SOURCE_AXIS_HIDDEN_CONTROLS:
        widget = getattr(ui, name, None) or base.findChild(QtWidgets.QWidget, name)
        if widget is not None:
            widget.setVisible(False)
    ui.continueMode = False


def install_source_axis_create_button(ui, callback):
    """Add Create beside the Task View's real standard Close button."""
    owner = ui.baseWidget
    while owner is not None and owner.objectName() != "Tasks":
        owner = owner.parent()
    button_box = owner.findChild(QtWidgets.QDialogButtonBox) if owner else None
    if button_box is None:
        for top_level in QtWidgets.QApplication.topLevelWidgets():
            for candidate in top_level.findChildren(QtWidgets.QDialogButtonBox):
                if candidate.isVisible() and any(
                        button.text() == "Close" for button in candidate.buttons()):
                    button_box = candidate
                    break
            if button_box is not None:
                break
    if button_box is None:
        return None
    button = QtWidgets.QPushButton("Criar", button_box)
    button.setObjectName("SteelStructuresSourceAxisCreate")
    button.clicked.connect(callback)
    button_box.addButton(button, QtWidgets.QDialogButtonBox.ActionRole)
    return button_box, button


def remove_source_axis_create_button(binding):
    if not binding:
        return
    button_box, button = binding
    try:
        button_box.removeButton(button)
        button.deleteLater()
    except RuntimeError:
        pass


class AxisSourceWidget(QtWidgets.QWidget):
    linkChanged = QtCore.Signal(bool)

    def __init__(self, source_link=None, parent=None):
        super().__init__(parent)
        self.source_link = source_link
        source = source_link[0] if source_link else None
        label = getattr(source, "Label", getattr(source, "Name", "Linha"))
        self.source_label = QtWidgets.QLabel("Eixo: %s" % label)
        self.keep_link = QtWidgets.QCheckBox("Manter vínculo com a linha")
        self.keep_link.setChecked(False)
        self.keep_link.toggled.connect(self.linkChanged.emit)
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(3)
        layout.addWidget(self.source_label)
        layout.addWidget(self.keep_link)
        self.setVisible(source is not None)

    @property
    def linked(self):
        return self.source_link is not None and self.keep_link.isChecked()

    def clear_source(self):
        self.source_link = None
        self.keep_link.setChecked(False)
        self.setVisible(False)


__all__ = [
    "AxisSourceWidget", "configure_source_axis_draft_ui",
    "install_source_axis_create_button", "remove_source_axis_create_button",
]
