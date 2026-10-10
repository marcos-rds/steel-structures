# SPDX-License-Identifier: LGPL-2.1-or-later
"""Draft Polyline acquisition; only an explicitly closed contour creates a plate."""
import math

import FreeCAD as App
from draftguitools import gui_lines
from draftutils import gui_utils, utils

from ..paths import PLATE_ICON
from ..plate_geometry import PlateContour2D
from .draft_plate_rectangle_tool import _PlateDraftTool


class StructuralPlatePolygonTool(_PlateDraftTool, gui_lines.Line):
    feature_name = "Polyline"
    source_mode = "InteractivePolygon"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.mode = "wire"

    def _input_ui(self):
        self.ui.wireUi(title="Criar Chapa Estrutural", icon=PLATE_ICON,
                       extra=self.options)
        self.ui.finishButton.hide()
        self.ui.orientWPButton.hide()
        self.ui.undoButton.setText("Desfazer ponto")
        self.ui.wipeButton.setText("Limpar pontos")
        self.ui.wipeButton.setToolTip("Descartar todos os pontos confirmados e reiniciar o traçado.")
        self.ui.closeButton.setText("Fechar contorno")

    def _init_preview(self):
        # This is Line's transient Part preview, never a Draft Wire.
        self.obj = self.doc.addObject("Part::Feature", "PlateContourPreview")
        gui_utils.format_object(self.obj)
        self.obj.ViewObject.ShowInTree = False
        self.options.status.setText("Selecione o primeiro ponto.")

    def _remove_preview(self):
        obj, self.obj = self.obj, None
        if obj is not None and App.listDocuments().get(self._document_name) is self.doc:
            if self.doc.getObject(obj.Name) is obj:
                self.doc.removeObject(obj.Name)

    def _local_point(self, point):
        local = self.placement.inverse().multVec(App.Vector(point))
        if not all(math.isfinite(value) for value in local):
            raise ValueError("As coordenadas devem ser finitas.")
        if abs(local.z) > 1e-5:
            raise ValueError("O ponto está fora do plano da chapa.")
        return local

    def _contour(self):
        local = [self._local_point(point) for point in self.node]
        return PlateContour2D.from_points([(p.x, p.y) for p in local], closed=True)

    def drawUpdate(self, point):
        # Line.action/numericInput append directly; validate before Part sees it.
        try:
            self._local_point(point)
            if len(self.node) > 1 and point.sub(self.node[-2]).Length < 1e-7:
                raise ValueError("Vértices consecutivos devem ser diferentes.")
        except ValueError as exc:
            self.node.pop()
            self.pos = []
            self.options.status.setText(str(exc))
            return
        gui_lines.Line.drawUpdate(self, point)
        self.options.status.setText("Adicione vértices ou feche o contorno.")
        self._update_point_actions()

    def _update_point_actions(self):
        self.ui.undoButton.setEnabled(bool(self.node))
        self.ui.wipeButton.setEnabled(bool(self.node))
        self.ui.closeButton.setEnabled(len(self.node) >= 3)

    def update_hints(self):
        super().update_hints()
        if self.is_active():
            self._update_point_actions()

    def action(self, arg):
        if self.is_active() and (not self._owner_alive() or gui_utils.get_3d_view() != self.view):
            self.finish()
            return
        if (self.is_active()
                and arg.get("Type") == "SoMouseButtonEvent"
                and arg.get("State") == "DOWN" and arg.get("Button") == "BUTTON1"
                and self.node and self.point is not None
                and (self.point - self.node[0]).Length < utils.tolerance()):
            self.finish(closed=True)
            return
        return super().action(arg)

    def numericInput(self, numx, numy, numz):
        if not self.is_active():
            return
        if not self._owner_alive() or gui_utils.get_3d_view() != self.view:
            self.finish()
            return
        point = App.Vector(numx, numy, numz)
        if self.node and point.sub(self.node[0]).Length < utils.tolerance():
            self.finish(closed=True)
            return
        return super().numericInput(numx, numy, numz)

    def finish(self, cont=False, closed=False):
        if closed and self.is_active():
            try:
                self._contour()
            except ValueError as exc:
                self.options.status.setText(str(exc))
                return
            self.createObject()
            return
        # Esc, Cancel and an open contour never call Line.finish.
        return _PlateDraftTool.finish(self, cont)

    def undolast(self):
        if not self.is_active():
            return
        if len(self.node) <= 1:
            self.reset_trace()
        else:
            gui_lines.Line.undolast(self)
            self.pos = []
            self.options.status.setText("Adicione vértices ou feche o contorno.")
        self._update_point_actions()

    def wipe(self):
        if self.is_active():
            self.reset_trace()

    def reset_trace(self):
        super().reset_trace()
        self.options.status.setText("Selecione o primeiro ponto.")
        if self.obj is not None:
            self.obj.ViewObject.hide()
