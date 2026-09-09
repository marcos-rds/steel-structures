"""Palette-aware transverse assembly view; consumes pure preview primitives."""
from PySide import QtCore, QtGui, QtWidgets
from ..trusses.assembly_preview import transverse_preview
from ..profiles.preview_geometry import background_needs_dark_outline_halo


class AssemblyPreview(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.model = None
        self.error = ""
        self.setMinimumHeight(175)
        self.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred)
        self.setToolTip("Seção transversal · cruz vermelha: eixo nominal · círculos: eixos de inserção")

    def sizeHint(self):
        return QtCore.QSize(320, 220)

    def minimumSizeHint(self):
        return QtCore.QSize(180, 175)

    def set_role(self, role):
        self.model = transverse_preview(role)
        self.error = ""
        self.update()

    def set_error(self, message):
        self.model = None
        self.error = message
        self.update()

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        palette = self.palette()
        background = palette.color(QtGui.QPalette.Base)
        dark = background_needs_dark_outline_halo(background.redF(), background.greenF(), background.blueF())
        text_color = QtGui.QColor(235, 235, 235) if dark else QtGui.QColor(38, 40, 43)
        painter.fillRect(self.rect(), background)
        painter.setPen(palette.color(QtGui.QPalette.Mid))
        painter.drawRect(self.rect().adjusted(0, 0, -1, -1))
        if self.model is None:
            painter.setPen(text_color)
            painter.drawText(self.rect().adjusted(12, 12, -12, -12), QtCore.Qt.AlignCenter | QtCore.Qt.TextWordWrap,
                             self.error or "Prévia indisponível")
            return
        minx, miny, maxx, maxy = self.model["bounds"]
        margin = 32.
        scale = max(1e-6, min((self.width()-2*margin)/max(maxx-minx, 1.),
                             (self.height()-2*margin-20)/max(maxy-miny, 1.)))
        def screen(p):
            return QtCore.QPointF(self.width()/2+(p.x-(minx+maxx)/2)*scale,
                                 (self.height()-20)/2-(p.y-(miny+maxy)/2)*scale)
        for component in self.model["components"]:
            path = QtGui.QPainterPath()
            path.setFillRule(QtCore.Qt.OddEvenFill)
            for points in component["paths"]:
                path.moveTo(screen(points[0]))
                for p in points[1:]:
                    path.lineTo(screen(p))
                path.closeSubpath()
            fill = QtGui.QColor.fromRgbF(*component["color"])
            painter.fillPath(path, fill)
            if dark:
                painter.setPen(QtGui.QPen(QtGui.QColor(244, 244, 241), 3.6))
                painter.setBrush(QtCore.Qt.NoBrush)
                painter.drawPath(path)
            painter.setPen(QtGui.QPen(QtGui.QColor(38, 40, 43), 1.6))
            painter.setBrush(QtCore.Qt.NoBrush)
            painter.drawPath(path)
            p = screen(component["insertion"])
            painter.setPen(QtGui.QPen(QtGui.QColor(47, 128, 237), 1.8))
            painter.drawEllipse(p, 4, 4)
            painter.setPen(text_color)
            painter.drawText(p+QtCore.QPointF(7, -7), component["key"])
        from ..profiles.geometry import Point2D
        center = screen(Point2D(0, 0))
        painter.setPen(QtGui.QPen(QtGui.QColor(220, 65, 65), 1.8))
        painter.drawLine(center+QtCore.QPointF(-6, 0), center+QtCore.QPointF(6, 0))
        painter.drawLine(center+QtCore.QPointF(0, -6), center+QtCore.QPointF(0, 6))
        spacing = self.model["spacing"]
        if spacing is not None:
            a, b = (screen(c["insertion"]) for c in self.model["components"])
            pen = QtGui.QPen(text_color, 1.)
            pen.setStyle(QtCore.Qt.DashLine)
            painter.setPen(pen)
            painter.drawLine(a, b)
            painter.drawText(self.rect().adjusted(8, self.height()-25, -8, -4),
                             QtCore.Qt.AlignCenter, f"Distância entre eixos: {spacing:g} mm")
