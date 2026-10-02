# SPDX-License-Identifier: LGPL-2.1-or-later
"""Lightweight, document-independent presentation of a generated truss graph."""

from __future__ import annotations

import math

from PySide import QtCore, QtGui, QtWidgets


ROLE_COLORS = {
    "TOP_CHORD": (41, 95, 153),
    "BOTTOM_CHORD": (41, 95, 153),
    "VERTICAL": (230, 125, 25),
    "DIAGONAL": (215, 175, 20),
    "END_POST": (167, 103, 42),
}


def graph_presentation(model):
    """Resolve drawing primitives before replacing the last valid Qt scene."""
    def point(value):
        x, y, z = (float(component) for component in value)
        if not all(math.isfinite(component) for component in (x, y, z)):
            raise ValueError("Coordenada inválida no preview da treliça.")
        return x, -y

    nodes = {item["key"]: point(item["position_local"]) for item in model["nodes"]}
    edges = tuple(
        (nodes[item["start_node_key"]], nodes[item["end_node_key"]],
         item["role"], item["key"])
        for item in model["edges"]
    )
    envelope = tuple(
        tuple(point(value) for value in model["envelope"][side])
        for side in ("top", "bottom")
    )
    return nodes, edges, envelope


class TrussPreview2D(QtWidgets.QGraphicsView):
    """Show nominal axes only; the controller owns all physical 3D geometry."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setScene(QtWidgets.QGraphicsScene(self))
        self.setRenderHint(QtGui.QPainter.Antialiasing, True)
        self.setBackgroundBrush(QtGui.QBrush(QtGui.QColor(250, 250, 250)))
        self.setMinimumHeight(170)
        self.setMaximumHeight(250)
        self.setToolTip("Eixos nominais: X é o vão, Y é a altura; Z sai do plano.")
        self._has_geometry = False

    @staticmethod
    def _pen(color, width, dashed=False):
        pen = QtGui.QPen(QtGui.QColor(*color))
        pen.setCosmetic(True)
        pen.setWidthF(width)
        if dashed:
            pen.setStyle(QtCore.Qt.DashLine)
        return pen

    def set_model(self, model):
        nodes, edges, envelope = graph_presentation(model)
        gussets = tuple(tuple((float(x), -float(y)) for x, y in item["points"])
                        for item in model.get("gussets", ())
                        if item.get("materializable", True))
        if any(not all(math.isfinite(value) for point in polygon for value in point)
               for polygon in gussets):
            raise ValueError("Contorno inválido no preview da chapa.")
        scene = self.scene()
        scene.clear()
        envelope_pen = self._pen((160, 165, 170), 3.4, True)
        for path in envelope:
            for start, end in zip(path, path[1:]):
                scene.addLine(*start, *end, envelope_pen)
        gusset_pen = self._pen((112, 65, 160), 1.4)
        gusset_brush = QtGui.QBrush(QtGui.QColor(142, 90, 190, 85))
        for polygon in gussets:
            item = scene.addPolygon(QtGui.QPolygonF(
                [QtCore.QPointF(*point) for point in polygon]), gusset_pen, gusset_brush)
            item.setData(0, "gusset")
            item.setZValue(-1)
        for start, end, role, key in edges:
            item = scene.addLine(
                *start, *end, self._pen(ROLE_COLORS.get(role, (75, 75, 75)), 1.6)
            )
            item.setToolTip(str(key))
            item.setData(0, "edge")
            item.setData(1, key)
        if model.get("reference_base"):
            start,end=envelope[1][0],envelope[1][-1]
            scene.addLine(*start,*end,self._pen((20,160,135),3))
            label=scene.addSimpleText("Base · "+model["reference_base"].replace("Edge","Lado "))
            label.setFlag(QtWidgets.QGraphicsItem.ItemIgnoresTransformations,True)
            label.setPos((start[0]+end[0])/2,start[1])
        for key, position in nodes.items():
            item = scene.addEllipse(
                -2.5, -2.5, 5.0, 5.0,
                self._pen((40, 45, 50), 0.7),
                QtGui.QBrush(QtGui.QColor(250, 250, 250)),
            )
            item.setPos(*position)
            item.setFlag(QtWidgets.QGraphicsItem.ItemIgnoresTransformations, True)
            item.setToolTip(str(key))
            item.setData(0, "node")
            item.setData(1, key)
        self._has_geometry = bool(nodes)
        bounds = scene.itemsBoundingRect()
        margin = max(bounds.width(), bounds.height(), 1.0) * 0.07
        scene.setSceneRect(bounds.adjusted(-margin, -margin, margin, margin))
        self._fit()

    def _fit(self):
        if self._has_geometry:
            self.fitInView(self.sceneRect(), QtCore.Qt.KeepAspectRatio)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._fit()


__all__ = ["TrussPreview2D", "graph_presentation"]
