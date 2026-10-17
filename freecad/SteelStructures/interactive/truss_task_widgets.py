# SPDX-License-Identifier: LGPL-2.1-or-later
"""Small presentation widgets for the truss task form; no numeric/model logic."""
from PySide import QtCore, QtGui, QtWidgets


class TrussReferenceActions(QtWidgets.QWidget):
    """Keep both native actions side by side; wrap captions at narrow widths."""
    def __init__(self, parent=None):
        super().__init__(parent)
        row = QtWidgets.QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)
        self.setSizePolicy(QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Preferred)
        self.buttons = []
        self.captions = []

    def add_button(self, button):
        self.buttons.append(button)
        self.captions.append(button.text())
        if not button.accessibleName():
            button.setAccessibleName(button.text())
        # Limit only horizontal padding; theme colors/states and vertical
        # metrics remain native, including OpenDark's otherwise wide padding.
        button.setStyleSheet("QPushButton { padding-left: 4px; padding-right: 4px; }")
        button.setSizePolicy(QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Fixed)
        self.layout().addWidget(button, 1)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if not self.buttons:
            return
        width = (self.width()-self.layout().spacing())//len(self.buttons)
        wrap = False
        for button, caption in zip(self.buttons, self.captions):
            option = QtWidgets.QStyleOptionButton()
            button.initStyleOption(option)
            option.rect.setWidth(width)
            contents = button.style().subElementRect(QtWidgets.QStyle.SE_PushButtonContents, option, button)
            available = contents.width()-button.iconSize().width()-4
            wrap |= available < button.fontMetrics().horizontalAdvance(caption)
        for button, caption in zip(self.buttons, self.captions):
            text = caption.replace(' ', '\n') if wrap else caption
            if button.text()!=text:
                button.setText(text)
            # Some native styles retain the first polished caption's minimum.
            button.setMinimumWidth(0)


def _paint_outline(widget, color):
    painter = QtGui.QPainter(widget)
    painter.setRenderHint(QtGui.QPainter.Antialiasing)
    painter.setPen(QtGui.QPen(color, 1.))
    painter.setBrush(QtCore.Qt.NoBrush)
    painter.drawRoundedRect(QtCore.QRectF(widget.rect()).adjusted(.5, .5, -.5, -.5), 3., 3.)


class TrussEditorButton(QtWidgets.QPushButton):
    """Retain native button states and add only a palette-aware hairline."""
    def paintEvent(self, event):
        super().paintEvent(event)
        palette = self.palette()
        color = palette.color(QtGui.QPalette.Link)
        if not 180 <= color.hue() <= 250:
            color = palette.color(QtGui.QPalette.Highlight)
        if not 180 <= color.hue() <= 250:
            color = QtGui.QColor("#4c96b7")  # Existing truss accent when theme links/highlight are red.
        if not self.isEnabled():
            color = palette.color(QtGui.QPalette.Disabled,QtGui.QPalette.Mid)
        _paint_outline(self,color)


class TrussInformationFrame(QtWidgets.QFrame):
    """Neutral hairline even in themes which remove native QFrame borders."""
    def paintEvent(self, event):
        super().paintEvent(event)
        _paint_outline(self,self.palette().color(QtGui.QPalette.Mid))


class _PendingClock(QtWidgets.QLabel):
    """Small palette-aware clock, drawn in logical pixels for native DPI."""
    def sizeHint(self):
        size=self.fontMetrics().height()
        return QtCore.QSize(size,size)

    def paintEvent(self,event):
        painter=QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        # Some QSS themes leave PlaceholderText black on a dark surface.
        # Derive the icon from the effective foreground instead.
        color=self.palette().color(QtGui.QPalette.WindowText)
        color.setAlphaF(.65)
        painter.setPen(QtGui.QPen(color,1.2))
        side=min(self.width(),self.height())-4
        rect=QtCore.QRectF((self.width()-side)/2,(self.height()-side)/2,side,side)
        painter.drawEllipse(rect)
        center=rect.center()
        painter.drawLine(center,center+QtCore.QPointF(0,-side*.3))
        painter.drawLine(center,center+QtCore.QPointF(side*.23,side*.12))


class TrussMassInformation(QtWidgets.QWidget):
    """Two mass rows with a shared pending status and native narrow reflow."""
    def __init__(self,parent=None):
        super().__init__(parent)
        self.grid=QtWidgets.QGridLayout(self)
        self.grid.setSizeConstraint(QtWidgets.QLayout.SetNoConstraint)
        self.grid.setContentsMargins(0,0,0,0)
        self.grid.setVerticalSpacing(3)
        self.labels={}
        self.values={}
        for row,(key,text) in enumerate((("mass","Peso total:"),("linear_mass","Peso linear:"))):
            label=QtWidgets.QLabel(text)
            font=label.font()
            font.setBold(True)
            label.setFont(font)
            value=QtWidgets.QLabel("—")
            font=value.font()
            font.setBold(False)
            value.setFont(font)
            value.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)
            self.labels[key],self.values[key]=label,value
            self.grid.addWidget(label,row,0)
            self.grid.addWidget(value,row,1)
        self.status_box=QtWidgets.QWidget()
        status_layout=QtWidgets.QHBoxLayout(self.status_box)
        status_layout.setContentsMargins(8,0,0,0)
        status_layout.setSpacing(4)
        self.clock=_PendingClock()
        self.clock.setFixedSize(self.clock.sizeHint())
        self.status=QtWidgets.QLabel("Aguardando aplicação")
        self.status.setForegroundRole(QtGui.QPalette.PlaceholderText)
        status_layout.addWidget(self.clock)
        status_layout.addWidget(self.status)
        self.grid.setColumnStretch(1,1)
        self._below=None
        self.set_pending(False)

    def set_pending(self,pending):
        self.status.setVisible(pending)
        self.status_box.setVisible(pending)
        self._arrange()

    def minimumSizeHint(self):
        width=sum(max(widget.minimumSizeHint().width() for widget in group.values())
                  for group in (self.labels,self.values))+self.grid.horizontalSpacing()
        return QtCore.QSize(width,self.grid.minimumSize().height())

    def _arrange(self):
        width=sum(max(widget.minimumSizeHint().width() for widget in group.values())
                  for group in (self.labels,self.values))
        threshold=width+self.status_box.sizeHint().width()+2*self.grid.horizontalSpacing()+16
        below=self.width()<threshold
        if below!=self._below:
            self._below=below
            self.grid.removeWidget(self.status_box)
            self.grid.addWidget(self.status_box,2 if below else 0,0 if below else 2,
                                1 if below else 2,2 if below else 1,QtCore.Qt.AlignVCenter)

    def resizeEvent(self,event):
        super().resizeEvent(event)
        self._arrange()


class TrussAdvancedLayout(QtWidgets.QWidget):
    """Reflow existing coordinate widgets without reparenting/recreating fields."""
    def __init__(self, start, end, normal, parent=None):
        super().__init__(parent)
        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(6, 0, 6, 0)
        root.setSpacing(4)
        root.setSizeConstraint(QtWidgets.QLayout.SetNoConstraint)
        self.points_layout = QtWidgets.QBoxLayout(QtWidgets.QBoxLayout.TopToBottom)
        self.points_layout.setSpacing(8)
        root.addLayout(self.points_layout)
        self.point_groups = []
        for title, widget in (("Ponto inicial", start), ("Ponto final", end)):
            group = self._group(title, widget)
            self.point_groups.append(group)
            self.points_layout.addWidget(group)
        self.normal_group = self._group("Normal do plano", normal)
        root.addWidget(self.normal_group)
        self.normal_widget = normal
        self.normal_pairs = [(normal.layout().itemAtPosition(i,0).widget(),
                              normal.layout().itemAtPosition(i,1).widget())
                             for i in range(normal.layout().rowCount())]
        self.normal_layout = normal.layout()
        self._normal_horizontal = None
        self._arrange_normal(False)

    def _group(self, title, widget):
        group = QtWidgets.QGroupBox(title, self)
        layout = QtWidgets.QVBoxLayout(group)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.addWidget(widget)
        return group

    def _arrange_normal(self, horizontal):
        if horizontal == self._normal_horizontal:
            return
        self._normal_horizontal = horizontal
        for index, (label, field) in enumerate(self.normal_pairs):
            self.normal_layout.addWidget(label, 0 if horizontal else index, 2*index if horizontal else 0)
            self.normal_layout.addWidget(field, 0 if horizontal else index, 2*index+1 if horizontal else 1)

    def minimumSizeHint(self):
        # A wide arrangement must not prevent the parent from becoming narrow.
        width = max(group.minimumSizeHint().width() for group in self.point_groups)
        margins = self.layout().contentsMargins()
        return QtCore.QSize(width + margins.left() + margins.right(), self.layout().minimumSize().height())

    def resizeEvent(self, event):
        super().resizeEvent(event)
        margins = self.layout().contentsMargins()
        width = self.width() - margins.left() - margins.right()
        threshold = sum(group.minimumSizeHint().width() for group in self.point_groups) + self.points_layout.spacing() + 24
        direction = (QtWidgets.QBoxLayout.LeftToRight if width >= threshold
                     else QtWidgets.QBoxLayout.TopToBottom)
        changed = direction != self.points_layout.direction()
        if changed:
            self.points_layout.setDirection(direction)
        normal_width = sum(label.sizeHint().width()+field.minimumWidth()+8 for label, field in self.normal_pairs)+16
        normal_horizontal = width >= normal_width
        changed |= normal_horizontal != self._normal_horizontal
        self._arrange_normal(normal_horizontal)
        # Derive height from the controls, not the previous arrangement's
        # cached grid hint (TaskView can still be hidden during its reflow).
        point_heights=[max(group.sizeHint().height(),group.minimumSizeHint().height())
                       for group in self.point_groups]
        points_height=(max(point_heights) if direction==QtWidgets.QBoxLayout.LeftToRight
                       else sum(point_heights)+self.points_layout.spacing())
        row_heights=[max(label.sizeHint().height(),field.sizeHint().height(),field.minimumHeight())
                     for label,field in self.normal_pairs]
        normal_height=(max(row_heights) if normal_horizontal else
                       sum(row_heights)+(len(row_heights)-1)*self.normal_layout.verticalSpacing())
        for item in (self.normal_group,self.normal_group.layout(),self.normal_widget,self.normal_layout):
            margin=item.contentsMargins()
            normal_height+=margin.top()+margin.bottom()
        height=points_height+normal_height+self.layout().spacing()+margins.top()+margins.bottom()
        if self.minimumHeight()!=height:
            self.setMinimumHeight(height)
            changed=True
        if changed:
            self.updateGeometry()
