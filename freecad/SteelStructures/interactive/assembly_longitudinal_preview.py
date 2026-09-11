"""Compact longitudinal projection of the shared physical realization."""
from PySide import QtCore, QtGui, QtWidgets
from ..trusses.assembly_preview import longitudinal_preview


class AssemblyLongitudinalPreview(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.model = None
        self.setMinimumHeight(145)
        self.setToolTip("Vista longitudinal · tracejado: Face B · pontos: estações dos interconectores")

    def set_role(self, role, length):
        self.model = longitudinal_preview(role, length)
        self.update()

    def clear(self):
        self.model = None
        self.update()

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        painter.fillRect(self.rect(), self.palette().color(QtGui.QPalette.Base))
        text = self.palette().color(QtGui.QPalette.Text)
        painter.setPen(text)
        if not self.model or not self.model["lines"]:
            painter.drawText(self.rect(), QtCore.Qt.AlignCenter, "Prévia longitudinal indisponível")
            return
        model = self.model
        points = [p for line in model["lines"] for p in (line["start"], line["end"])]
        points += [p for line in model["lines"] for p in line.get("outline", ())]
        low, high = min(p[1] for p in points), max(p[1] for p in points)
        def screen(p):
            return QtCore.QPointF(20+p[0]/model["length"]*(self.width()-40),
                                 28+(high-p[1])/max(high-low, 1.)*(self.height()-65))
        for line in model["lines"]:
            pen = QtGui.QPen(QtGui.QColor.fromRgbF(*line["color"]), 3. if line["component"] else 1.7)
            if line["secondary"]:
                pen.setStyle(QtCore.Qt.DashLine)
            painter.setPen(pen)
            if line.get("outline"):
                painter.drawPolygon(QtGui.QPolygonF([screen(p) for p in line["outline"]]))
            else:
                painter.drawLine(screen(line["start"]), screen(line["end"]))
        painter.setPen(text)
        for station in model["stations"]:
            painter.drawEllipse(screen((station, 0.)), 2.5, 2.5)
        painter.drawText(QtCore.QPointF(20, 17), "Vista longitudinal")
