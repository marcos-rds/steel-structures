# SPDX-License-Identifier: LGPL-2.1-or-later
"""Interactive schematic family diagram for structural member creation."""

from __future__ import annotations

from PySide import QtCore, QtGui, QtWidgets

from ..profiles.preview_geometry import (
    background_needs_dark_outline_halo, nearest_reference,
    preview_screen_point, profile_presentation_radius, schematic_section_for_geometry,
    SchematicCubic2D,
)


HOTSPOT_AVAILABLE_COLOR = (47, 128, 237)
HOTSPOT_HOVER_COLOR = (66, 145, 245)
HOTSPOT_SELECTED_COLOR = (205, 45, 45)


def _mouse_position(event):
    position = getattr(event, "position", None)
    return position() if callable(position) else event.pos()


class SectionOrientationPreview(QtWidgets.QWidget):
    """Paint and interact with one normalized section-family diagram."""

    referenceSelected = QtCore.Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._schematic = None
        self._outline = ()
        self._references = ()
        self._radius = 1.0
        self._presentation_reference = None
        self._insertion = "Centroide"
        self._rotation = 0.0
        self._hovered = None
        line = self.fontMetrics().lineSpacing()
        self.setMinimumHeight(line * 9)
        self.setMaximumHeight(line * 12)
        self.setMouseTracking(True)
        self.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred)
        self.setToolTip("Selecione graficamente o ponto de inserção")

    def sizeHint(self):
        line = self.fontMetrics().lineSpacing()
        return QtCore.QSize(line * 14, line * 10)

    def minimumSizeHint(self):
        line = self.fontMetrics().lineSpacing()
        return QtCore.QSize(line * 11, line * 9)

    def set_geometry(self, geometry, insertion="Centroide", rotation=0.0):
        self._schematic = schematic_section_for_geometry(geometry) if geometry is not None else None
        self._insertion = str(insertion)
        self._rotation = float(rotation)
        self._hovered = None
        if self._schematic is None:
            self._outline = ()
            self._references = ()
            self._radius = 1.0
            self._presentation_reference = None
        else:
            self._outline = self._schematic.outline
            self._references = self._schematic.references
            self._presentation_reference = self._schematic.center
            self._radius = profile_presentation_radius(
                self._outline, self._presentation_reference
            )
        self.update()

    def set_insertion(self, value):
        self._insertion = str(value)
        self._hovered = None
        self.update()

    def set_rotation(self, value):
        self._rotation = float(value)
        self._hovered = None
        self.update()

    def _layout(self):
        metrics = self.fontMetrics()
        margin = max(metrics.lineSpacing() * 1.05, 10.0)
        rect = QtCore.QRectF(self.rect()).adjusted(margin, margin, -margin, -margin)
        target = rect.center()
        scale = max(min(rect.width(), rect.height()) / (2.0 * self._radius), 1e-9)
        return target, scale

    def _selected_reference(self):
        return next(
            (
                reference for reference in self._references
                if self._insertion in (reference.id, reference.label)
            ),
            self._references[0],
        )

    def reference_label(self, identifier):
        """Return the real infrastructure label associated with a hotspot id."""
        return next(
            (
                reference.label for reference in self._references
                if reference.id == identifier
            ),
            str(identifier),
        )

    def _screen_point(self, point, target, scale):
        return preview_screen_point(
            point, self._presentation_reference, self._rotation,
            target.x(), target.y(), scale,
        )

    def _schematic_path(self, target, scale):
        path = QtGui.QPainterPath()
        path.setFillRule(QtCore.Qt.OddEvenFill)
        for segments in (self._schematic.segments,) + self._schematic.inner_segments:
            first_x, first_y = self._screen_point(segments[0].start, target, scale)
            path.moveTo(first_x, first_y)
            for segment in segments:
                end_x, end_y = self._screen_point(segment.end, target, scale)
                if isinstance(segment, SchematicCubic2D):
                    control1_x, control1_y = self._screen_point(segment.control1, target, scale)
                    control2_x, control2_y = self._screen_point(segment.control2, target, scale)
                    path.cubicTo(control1_x, control1_y, control2_x, control2_y, end_x, end_y)
                else:
                    path.lineTo(end_x, end_y)
            path.closeSubpath()
        return path

    def paintEvent(self, _event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing, True)
        palette = self.palette()
        painter.fillRect(self.rect(), palette.brush(QtGui.QPalette.Base))
        frame_pen = QtGui.QPen(palette.color(QtGui.QPalette.Mid))
        frame_pen.setWidthF(1.0)
        painter.setPen(frame_pen)
        painter.setBrush(QtCore.Qt.NoBrush)
        painter.drawRect(QtCore.QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5))
        if self._schematic is None:
            painter.setPen(palette.color(QtGui.QPalette.Mid))
            painter.drawText(self.rect(), QtCore.Qt.AlignCenter, "Prévia indisponível")
            return

        target, scale = self._layout()
        selected = self._selected_reference()
        path = self._schematic_path(target, scale)

        outline_color = QtGui.QColor(38, 40, 43)
        fill_color = QtGui.QColor(244, 244, 241)
        painter.setPen(QtCore.Qt.NoPen)
        painter.setBrush(fill_color)
        painter.drawPath(path)

        background = palette.color(QtGui.QPalette.Base)
        if background_needs_dark_outline_halo(
            background.redF(), background.greenF(), background.blueF()
        ):
            halo_pen = QtGui.QPen(fill_color)
            halo_pen.setWidthF(3.6)
            painter.setPen(halo_pen)
            painter.setBrush(QtCore.Qt.NoBrush)
            painter.drawPath(path)

        outline_pen = QtGui.QPen(outline_color)
        outline_pen.setWidthF(2.0)
        painter.setPen(outline_pen)
        painter.setBrush(QtCore.Qt.NoBrush)
        painter.drawPath(path)

        # Available references sit above the section contour as clean blue rings.
        normal_radius = max(self.fontMetrics().lineSpacing() * 0.28, 4.0)
        hover_radius = max(self.fontMetrics().lineSpacing() * 0.43, 6.3)
        available_color = QtGui.QColor(*HOTSPOT_AVAILABLE_COLOR)
        point_pen = QtGui.QPen(available_color)
        point_pen.setWidthF(1.9)
        for reference in self._references:
            if reference.id == selected.id or reference.id == self._hovered:
                continue
            x, y = self._screen_point(reference.point, target, scale)
            painter.setPen(point_pen)
            painter.setBrush(QtCore.Qt.NoBrush)
            painter.drawEllipse(QtCore.QPointF(x, y), normal_radius, normal_radius)

        if self._hovered is not None and self._hovered != selected.id:
            hovered = next(
                reference for reference in self._references
                if reference.id == self._hovered
            )
            x, y = self._screen_point(hovered.point, target, scale)
            hover_pen = QtGui.QPen(QtGui.QColor(*HOTSPOT_HOVER_COLOR))
            hover_pen.setWidthF(2.7)
            painter.setPen(hover_pen)
            painter.setBrush(QtCore.Qt.NoBrush)
            painter.drawEllipse(QtCore.QPointF(x, y), hover_radius, hover_radius)

        # The real insertion id is highlighted at its mapped schematic location.
        selected_x, selected_y = self._screen_point(selected.point, target, scale)
        selected_target = QtCore.QPointF(selected_x, selected_y)
        radius = max(self.fontMetrics().lineSpacing() * 0.40, 5.5)
        arm = radius * 1.5
        selected_color = QtGui.QColor(*HOTSPOT_SELECTED_COLOR)
        target_pen = QtGui.QPen(selected_color)
        target_pen.setWidthF(2.0)
        painter.setPen(target_pen)
        painter.setBrush(palette.brush(QtGui.QPalette.Base))
        painter.drawEllipse(selected_target, radius, radius)
        painter.drawLine(selected_x - arm, selected_y, selected_x + arm, selected_y)
        painter.drawLine(selected_x, selected_y - arm, selected_x, selected_y + arm)
        painter.setBrush(selected_color)
        painter.drawEllipse(
            selected_target, max(radius * 0.22, 1.2), max(radius * 0.22, 1.2)
        )

    def _reference_at(self, position):
        if self._schematic is None:
            return None
        target, scale = self._layout()
        hit_radius = max(self.fontMetrics().lineSpacing() * 0.65, 9.0)
        return nearest_reference(
            self._references, self._presentation_reference, self._rotation,
            target.x(), target.y(), scale, position.x(), position.y(), hit_radius,
        )

    def mouseMoveEvent(self, event):
        reference = self._reference_at(_mouse_position(event))
        identifier = reference.id if reference is not None else None
        if identifier != self._hovered:
            self._hovered = identifier
            self.setCursor(
                QtCore.Qt.PointingHandCursor if reference is not None
                else QtCore.Qt.ArrowCursor
            )
            self.setToolTip(reference.label if reference is not None else "")
            self.update()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event):
        self._hovered = None
        self.setCursor(QtCore.Qt.ArrowCursor)
        self.setToolTip("")
        self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            reference = self._reference_at(_mouse_position(event))
            if reference is not None:
                self.referenceSelected.emit(reference.id)
                event.accept()
                return
        super().mousePressEvent(event)


__all__ = [
    "HOTSPOT_AVAILABLE_COLOR", "HOTSPOT_HOVER_COLOR", "HOTSPOT_SELECTED_COLOR",
    "SectionOrientationPreview",
]
