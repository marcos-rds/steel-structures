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


def reference_presentation(model, envelope):
    """Use computed physical support points; never guess a profile offset."""
    if model.get("envelope_type") not in ("Parallel", "DuoPitch") and not model.get("reference_base"):
        return None
    alignment = model.get("reference_alignment", "BottomChord")
    if alignment == "TopChordSupports":
        values = model.get("support_reference_local")
        if values is None:
            return None
        if len(values) != 2 or any(len(value) != 3 for value in values):
            raise ValueError("A referência dos apoios deve conter dois pontos locais.")
        points = tuple(tuple(float(component) for component in value) for value in values)
        if any(not all(math.isfinite(component) for component in value) for value in points):
            raise ValueError("Coordenada inválida na referência dos apoios.")
        start, end = ((value[0], -value[1]) for value in points)
        return start, end
    start, end = envelope[1][0], envelope[1][-1]
    return start, end


def end_height_presentation(model, envelope):
    """Dimensions are nominal local heights, independent of profile insertion."""
    kind = model.get("envelope_type")
    if kind not in ("Parallel", "DuoPitch"):
        return ()
    result = []
    # A parallel envelope has a single constant nominal height.
    ends = ((0, ""),) if kind == "Parallel" else ((0, "E: "), (-1, "D: "))
    for index, prefix in ends:
        top, bottom = envelope[0][index], envelope[1][index]
        height = bottom[1] - top[1]
        if height > 1e-9:
            result.append((top, bottom, f"{prefix}{height:g} mm"))
    return tuple(result)


def dimension_layout(top, bottom, side, text_width, viewport_height):
    """Compact technical dimension in viewport pixels, at every preview size.

    Extension/tick positions retain the actual nominal endpoints. Only the
    label is clamped to the viewport when the dimension is very short.
    """
    x = top[0] + side*12.
    y1, y2 = top[1], bottom[1]
    short = y2-y1 < 12.
    lines = [(top[0]+side*4., y1, x+side*4., y1),
             (bottom[0]+side*4., y2, x+side*4., y2),
             (x, y1-(7. if short else 0.), x, y2+(7. if short else 0.))]
    for y in (y1, y2):
        lines.append((x-3., y+3., x+3., y-3.))
    half = text_width/2.+5.
    center = max(half, min(viewport_height-half, (y1+y2)/2.))
    return tuple(lines), (x+side*13., center)


class TrussPreview2D(QtWidgets.QGraphicsView):
    """Show nominal axes only; the controller owns all physical 3D geometry."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setScene(QtWidgets.QGraphicsScene(self))
        self.setRenderHint(QtGui.QPainter.Antialiasing, True)
        self.setBackgroundBrush(QtGui.QBrush(QtGui.QColor(250, 250, 250)))
        self.setMinimumHeight(170)
        self.setMaximumHeight(250)
        self.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.setToolTip("Eixos nominais: X é o vão, Y é a altura; Z sai do plano.")
        self._has_geometry = False
        self._dimensions = ()

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
        reference = reference_presentation(model, envelope)
        dimensions = end_height_presentation(model, envelope)
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
        if reference:
            start, end = reference
            item = scene.addLine(*start, *end, self._pen((80, 155, 140), 1.2, True))
            item.setData(0, "reference")
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
        self._geometry_bounds = scene.itemsBoundingRect()
        self._dimensions = dimensions
        self._fit()

    def _fit(self):
        if self._has_geometry:
            bounds = self._geometry_bounds
            # Fixed screen margins: labels never become CAD-sized scene items
            # and cannot consume increasing fractions of a large span.
            left = 40. if self._dimensions else 12.
            right = 40. if len(self._dimensions) > 1 else 12.
            width, height = self.viewport().width(), self.viewport().height()
            scale = min(max(1., width-left-right)/max(bounds.width(), 1.),
                        max(1., height-24.)/max(bounds.height(), 1.))
            self.setSceneRect(bounds.adjusted(-left/scale, -12./scale,
                                             right/scale, 12./scale))
            self.setTransform(QtGui.QTransform.fromScale(scale, scale))
            self.centerOn(self.sceneRect().center())
            self.viewport().update()

    def drawForeground(self, painter, rect):
        super().drawForeground(painter, rect)
        painter.save()
        painter.resetTransform()
        painter.setPen(self._pen((90, 95, 100), 1.))
        font = painter.font()
        font.setPointSizeF(8.5)
        painter.setFont(font)
        metrics = QtGui.QFontMetricsF(font)
        for index, (top, bottom, caption) in enumerate(self._dimensions):
            a = self.mapFromScene(QtCore.QPointF(*top))
            b = self.mapFromScene(QtCore.QPointF(*bottom))
            text_width = metrics.horizontalAdvance(caption)
            lines, label = dimension_layout((a.x(), a.y()), (b.x(), b.y()),
                                             -1 if index == 0 else 1,
                                             text_width, self.viewport().height())
            for line in lines:
                painter.drawLine(QtCore.QLineF(*line))
            painter.save()
            painter.translate(*label)
            painter.rotate(-90.)
            painter.drawText(QtCore.QPointF(-text_width/2.,
                                          (metrics.ascent()-metrics.descent())/2.), caption)
            painter.restore()
        painter.restore()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._fit()


__all__ = ["TrussPreview2D", "graph_presentation", "reference_presentation",
           "end_height_presentation", "dimension_layout"]
