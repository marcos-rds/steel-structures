"""Read-only, parent-owned Qt painting of resolved transverse presentation data."""

from PySide import QtCore, QtGui, QtWidgets

from ..trusses.gusset_presentation import fit_transverse_bounds


def _visual_signature(view):
    """Only identical screen geometry may share one compact presentation."""
    def points(values):
        return tuple((round(x, 4), round(y, 4)) for x, y in values)
    return (tuple((component.key, points(component.outer),
                   tuple(points(hole) for hole in component.holes))
                  for component in view.components),
            points(view.plate), view.message)


class GussetSectionCanvas(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._views = ()
        self.setMinimumHeight(210)

    def set_views(self, views):
        self._views = tuple(views)
        self.setMinimumHeight(max(210, 210*len(self._views)))
        self.update()

    def paintEvent(self, event):
        del event
        painter = QtGui.QPainter(self)
        try:
            painter.setRenderHint(QtGui.QPainter.Antialiasing)
            palette = self.palette()
            background = palette.color(QtGui.QPalette.Base)
            dark = background.lightness() < 128
            foreground = QtGui.QColor(235, 235, 235) if dark else QtGui.QColor(38, 40, 43)
            plate_color = QtGui.QColor("#e6aa50" if dark else "#9a5100")
            profile_fill = QtGui.QColor("#527694" if dark else "#bed3e3")
            profile_outline = QtGui.QColor("#d2e5f2" if dark else "#365b78")
            painter.fillRect(self.rect(), background)
            painter.setPen(QtGui.QPen(palette.color(QtGui.QPalette.Mid), 1.))
            painter.setBrush(QtCore.Qt.NoBrush)
            painter.drawRect(self.rect().adjusted(0, 0, -1, -1))
            for index, view in enumerate(self._views):
                top = index*210
                painter.setPen(foreground)
                title = view.label
                if len(self._views) > 1:
                    title += " — %d/%d" % (index+1, len(self._views))
                painter.drawText(QtCore.QRectF(10, top+4, self.width()-20, 36),
                                 QtCore.Qt.AlignCenter | QtCore.Qt.TextWordWrap, title)
                if view.message:
                    painter.drawText(QtCore.QRectF(12, top+35, self.width()-24, 155),
                                     QtCore.Qt.AlignCenter | QtCore.Qt.TextWordWrap,
                                     view.message)
                    continue
                viewport = fit_transverse_bounds(view.bounds, self.width(), 160)
                if viewport is None:
                    continue

                def path_for(loops):
                    path = QtGui.QPainterPath()
                    path.setFillRule(QtCore.Qt.OddEvenFill)
                    for loop in loops:
                        for i, point in enumerate(loop):
                            x, y = viewport.point(point)
                            if i == 0:
                                path.moveTo(x, y+top+42)
                            else:
                                path.lineTo(x, y+top+42)
                        path.closeSubpath()
                    return path

                painter.setPen(QtGui.QPen(profile_outline, 1.4))
                painter.setBrush(QtGui.QBrush(profile_fill))
                for component in view.components:
                    painter.drawPath(path_for((component.outer,)+component.holes))
                painter.setPen(QtGui.QPen(plate_color, 1.5))
                painter.setBrush(QtGui.QBrush(plate_color, QtCore.Qt.BDiagPattern))
                painter.drawPath(path_for((view.plate,)))
        finally:
            painter.end()


class GussetSectionPreview(QtWidgets.QGroupBox):
    def __init__(self, parent=None):
        super().__init__("Vista transversal", parent)
        self.setMinimumWidth(290)
        self.setMaximumWidth(370)
        self._views = ()
        layout = QtWidgets.QVBoxLayout(self)
        self.caption = QtWidgets.QLabel(self)
        self.caption.setWordWrap(True)
        layout.addWidget(self.caption)
        self.section_selector = QtWidgets.QComboBox(self)
        self.section_selector.setToolTip(
            "Este nó possui seções transversais distintas. Escolha o banzo a visualizar.")
        self.section_selector.currentIndexChanged.connect(self._select_view)
        layout.addWidget(self.section_selector)
        self.canvas = GussetSectionCanvas(self)
        layout.addWidget(self.canvas, 1)
        self.set_preview()

    def add_position_controls(self, region, position):
        """Place the editor's existing selectors next to their visualization."""
        form = QtWidgets.QFormLayout()
        form.setContentsMargins(0, 0, 0, 0)
        for widget in (region, position):
            widget.setMinimumWidth(150)
            widget.setSizeAdjustPolicy(
                QtWidgets.QComboBox.AdjustToMinimumContentsLengthWithIcon)
            widget.setMinimumContentsLength(16)
            widget.setSizePolicy(QtWidgets.QSizePolicy.Expanding,
                                 QtWidgets.QSizePolicy.Fixed)
        form.addRow("Região da chapa:", region)
        form.addRow("Posição:", position)
        self.layout().addLayout(form)
        return form

    def _select_view(self, index):
        self.canvas.set_views((self._views[index],) if 0 <= index < len(self._views)
                              else ())

    def set_preview(self, views=(), caption="Selecione um nó."):
        # Only immutable Python data is retained. No scene items, callbacks,
        # document observers or timers can outlive the dialog's Qt parent.
        previous = self.section_selector.currentText()
        seen = set()
        distinct = []
        for view in views:
            signature = _visual_signature(view)
            if signature not in seen:
                seen.add(signature)
                distinct.append(view)
        self._views = tuple(distinct)
        blocked = self.section_selector.blockSignals(True)
        self.section_selector.clear()
        for view in self._views:
            self.section_selector.addItem(view.label)
        index = self.section_selector.findText(previous)
        self.section_selector.setCurrentIndex(max(0, index) if self._views else -1)
        self.section_selector.blockSignals(blocked)
        self.section_selector.setVisible(len(self._views) > 1)
        self._select_view(self.section_selector.currentIndex())
        self.canvas.setVisible(bool(self._views))
        self.caption.setText(caption)
