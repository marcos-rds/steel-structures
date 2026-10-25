# SPDX-License-Identifier: LGPL-2.1-or-later
"""Independent reference toggles and three exclusive display-mode actions."""

from FreeCAD import Gui

from ..paths import ICONS_DIR
from .structural_reference_view import COMMANDS, service
from .structural_reference_modes import MODES, MODE_LABELS, MODE_COMMANDS, MODE_TOOLTIPS


class StructuralReferenceCommand:
    def __init__(self, kind):
        self.kind = kind

    def GetResources(self):
        axes = self.kind == "axes"
        return {
            "Pixmap": str(ICONS_DIR / ("MemberAxes.svg" if axes else "MemberEndpoints.svg")),
            "MenuText": "Mostrar/Ocultar Eixos" if axes else "Mostrar/Ocultar Extremidades",
            "ToolTip": (
                "Exibe os eixos nominais dos membros independentes elegíveis deste documento. "
                "O eixo nominal não é o eixo centroidal ou analítico; sólidos podem ocultá-lo."
                if axes else
                "Exibe as extremidades nominais com marcadores circulares preenchidos. "
                "Podem diferir das faces cortadas e ficar ocultas pelos sólidos."
            ),
            "Checkable": True,
            "CmdType": "NoTransaction",
        }

    def IsActive(self):
        service.sync_actions()
        if not service._active:
            return False
        try:
            doc = Gui.activeDocument()
            return doc is not None and doc.activeView() in doc.mdiViewsOfType("Gui::View3DInventor")
        except (AttributeError, ReferenceError, RuntimeError):
            return False

    def Activated(self, _status=0):
        service.toggle(self.kind)


def register_commands():
    for mode, name in MODE_COMMANDS.items():
        Gui.addCommand(name, StructuralDisplayModeCommand(mode))
    for kind, name in COMMANDS.items():
        Gui.addCommand(name, StructuralReferenceCommand(kind))
    return [*MODE_COMMANDS.values(), *COMMANDS.values()]


class StructuralDisplayModeCommand:
    """Select one mode; clicking the selected action cannot turn the mode off."""

    def __init__(self, mode):
        if mode not in MODES:
            raise ValueError("Modo de visualização desconhecido.")
        self.mode = mode

    def GetResources(self):
        icon = {"physical": "StructuralDisplayMode.svg", "structural": "StructuralDisplayAxes.svg",
                "xray": "StructuralDisplayXray.svg"}[self.mode]
        return {"Pixmap": str(ICONS_DIR / icon),
                "MenuText": MODE_LABELS[MODES.index(self.mode)], "CmdType": "NoTransaction",
                "Checkable": True, "ToolTip": MODE_TOOLTIPS[self.mode]}

    def IsActive(self):
        return StructuralReferenceCommand("axes").IsActive()

    def Activated(self, _status=0):
        if self.IsActive():
            service.set_mode(self.mode)
        # Native checkable actions toggle before this callback. Reassert the
        # canonical state even when set_mode is a no-op for the current mode.
        service.sync_actions()
