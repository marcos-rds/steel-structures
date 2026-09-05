# SPDX-License-Identifier: LGPL-2.1-or-later
"""Native Qt renderer for pure SectionGeometry2D contours."""

from dataclasses import dataclass
from html import escape
import math

from PySide import QtCore, QtGui, QtWidgets

from ..profiles import (
    SectionGeometry2D, insertion_reference,
    section_insertion_references,
)
from ..profiles.preview_geometry import SchematicCubic2D, preview_segments_for_path


DIMENSIONS_MODE = "dimensions"
PROPERTIES_MODE = "properties"
NEUTRAL_MODE = "neutral"
PREVIEW_MODES = (DIMENSIONS_MODE, PROPERTIES_MODE, NEUTRAL_MODE)
TEXT_LINE_GAP = 2.0
SYMBOL_VALUE_SEPARATOR = "&nbsp;"
GEOMETRY_CLEARANCE_PIXELS = 4.0
MIN_LABEL_CLEARANCE = 5.0
TW_TEXT_OFFSET = 18.0
TF_TEXT_OFFSET = 8.0
LINE_END_PADDING = 8.0
D_OFFSET_PIXELS = 38.0
D_MAX_COMPENSATION_PIXELS = 18.0
BF_OFFSET_PIXELS = 30.0
ANGLE_B_OFFSET_PIXELS = 20.0
ANGLE_VERTICAL_B_OFFSET_PIXELS = 32.0
ANGLE_T_EXTENSION_OVERHANG_PIXELS = 4.0
CANVAS_MARGIN_PIXELS = 12.0
TICK_PIXELS = 4.5
SMALL_EXTENSION_HALF_PIXELS = 7.0
TF_LINE_OFFSET_PIXELS = 14.0
TEE_TW_OFFSET_PIXELS = 18.0
TF_WITNESS_RADIUS_PIXELS = 1.8
EXTENSION_OVERSHOOT_PIXELS = 4.0
UE_D_OFFSET_PIXELS = 18.0
UE_D_TEXT_OFFSET_PIXELS = 8.0
UE_T_LEADER_X_PIXELS = 22.0
UE_T_LEADER_Y_PIXELS = 20.0
HOLLOW_WIDTH_OFFSET_PIXELS = 26.0
HOLLOW_HEIGHT_OFFSET_PIXELS = 30.0
HOLLOW_T_LEADER_X_PIXELS = 24.0
HOLLOW_T_LEADER_Y_PIXELS = 16.0
CHS_WIDTH_OFFSET_PIXELS = 18.0
CHS_T_LEADER_X_PIXELS = 18.0
CHS_T_LEADER_Y_PIXELS = 12.0
CHS_T_TARGET_ANGLE_DEGREES = 35.0
HOLLOW_HORIZONTAL_RESERVE_PIXELS = 82.0
HOLLOW_VERTICAL_RESERVE_PIXELS = 48.0
DIMENSION_COLOR = (128, 32, 48)
INSERTION_MARKER_COLOR = (0, 112, 132)
INSERTION_MARKER_RADIUS_PIXELS = 5.0
INSERTION_MARKER_CROSSHAIR_PIXELS = 8.0
INSERTION_MARKER_CENTER_PIXELS = 1.4


@dataclass
class _DimensionLabel:
    item: object
    width: float
    height: float


def _clamp(value, minimum, maximum):
    return max(minimum, min(float(value), maximum))


def _fit_units_per_pixel(bounds, viewport_width, viewport_height,
                         width_fraction=0.58, height_fraction=0.66):
    """Return a continuous model-to-screen fit without an absolute-size floor."""
    width = max(float(viewport_width), 1.0)
    height = max(float(viewport_height), 1.0)
    return max(
        bounds.width / (width * float(width_fraction)),
        bounds.height / (height * float(height_fraction)),
        1.0e-9,
    )


def _balanced_section_envelope(bounds, visual_bounds, padding):
    """Return a section-centred rect large enough for every annotation."""
    left, right = bounds.min_x, bounds.max_x
    top, bottom = -bounds.max_y, -bounds.min_y
    horizontal = max(
        left - visual_bounds.left(), visual_bounds.right() - right, padding,
    )
    vertical = max(
        top - visual_bounds.top(), visual_bounds.bottom() - bottom, padding,
    )
    return (
        left - horizontal, top - vertical,
        bounds.width + 2.0 * horizontal, bounds.height + 2.0 * vertical,
    )


def _hollow_section_envelope(bounds, units_per_pixel):
    """Return a section-centred viewport independent of annotation item bounds."""
    horizontal = HOLLOW_HORIZONTAL_RESERVE_PIXELS * float(units_per_pixel)
    vertical = HOLLOW_VERTICAL_RESERVE_PIXELS * float(units_per_pixel)
    left = bounds.min_x - horizontal
    top = -bounds.max_y - vertical
    return (
        left, top,
        bounds.width + 2.0 * horizontal,
        bounds.height + 2.0 * vertical,
    )


def _ue_section_envelope(bounds, visual_bounds, padding):
    """Keep the Ue section horizontally centred without wasting vertical room."""
    left, right = bounds.min_x, bounds.max_x
    horizontal = max(
        left - visual_bounds.left(), visual_bounds.right() - right, padding,
    )
    top = min(-bounds.max_y, visual_bounds.top()) - padding
    bottom = max(-bounds.min_y, visual_bounds.bottom()) + padding
    return left - horizontal, top, bounds.width + 2.0 * horizontal, bottom - top


def _channel_tf_measurement(geometry):
    """Return the catalog tf station and its two vertical measurement points."""
    bounds = geometry.bounds
    web_inner_x = geometry.outer_path.segments[5].start.x
    web_thickness = web_inner_x - bounds.min_x
    x_tf = bounds.min_x + (bounds.width + web_thickness) / 2.0
    slope = geometry.outer_path.segments[7]
    ratio = (x_tf - slope.start.x) / (slope.end.x - slope.start.x)
    inner_y = slope.start.y + ratio * (slope.end.y - slope.start.y)
    return x_tf, bounds.max_y, inner_y


def _tapered_i_tf_measurement(geometry):
    """Return the explicit BIM tf station and upper vertical measurement."""
    stations = dict(geometry.dimension_stations)
    x_tf = stations["tf_right"]
    slope = geometry.outer_path.segments[7]
    ratio = (x_tf - slope.start.x) / (slope.end.x - slope.start.x)
    inner_y = slope.start.y + ratio * (slope.end.y - slope.start.y)
    return x_tf, geometry.bounds.max_y, inner_y


def _tee_dimension_stations(geometry):
    """Return real-contour stations for the T flange and web tip."""
    segments = geometry.outer_path.segments
    bottom_edge = segments[0]
    flange_side = segments[3]
    return {
        "tw_left": bottom_edge.start.x,
        "tw_right": bottom_edge.end.x,
        "tw_section_bottom": -bottom_edge.start.y,
        "tf_right": geometry.bounds.max_x,
        "tf_top": -flange_side.end.y,
        "tf_bottom": -flange_side.start.y,
    }


def _ignores_transformations_flag():
    graphics_item = QtWidgets.QGraphicsItem
    flag = getattr(graphics_item, "ItemIgnoresTransformations", None)
    if flag is not None:
        return flag
    return graphics_item.GraphicsItemFlag.ItemIgnoresTransformations


class SectionPreviewView(QtWidgets.QGraphicsView):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setScene(QtWidgets.QGraphicsScene(self))
        self.setRenderHint(QtGui.QPainter.Antialiasing, True)
        self.setAlignment(QtCore.Qt.AlignCenter)
        self.setBackgroundBrush(QtGui.QBrush(QtGui.QColor(255, 255, 255)))
        self.setFrameShape(QtWidgets.QFrame.StyledPanel)
        self.setMinimumHeight(190)
        self.setMaximumHeight(260)

    def set_geometry(self, geometry, dimension_rows=(), mode=DIMENSIONS_MODE,
                     insertion=None):
        if not isinstance(geometry, SectionGeometry2D):
            raise TypeError("geometry deve ser SectionGeometry2D")
        if mode not in PREVIEW_MODES:
            raise ValueError("modo de preview inválido")
        self.scene().clear()
        path = QtGui.QPainterPath()
        path.setFillRule(QtCore.Qt.OddEvenFill)
        for contour in (geometry.outer_path,) + geometry.inner_paths:
            segments = preview_segments_for_path(contour)
            first = segments[0].start
            path.moveTo(first.x, -first.y)
            for segment in segments:
                if isinstance(segment, SchematicCubic2D):
                    path.cubicTo(
                        segment.control1.x, -segment.control1.y,
                        segment.control2.x, -segment.control2.y,
                        segment.end.x, -segment.end.y,
                    )
                else:
                    path.lineTo(segment.end.x, -segment.end.y)
            path.closeSubpath()

        outline = QtGui.QPen(QtGui.QColor(28, 28, 28))
        outline.setCosmetic(True)
        outline.setWidthF(1.35)
        fill = QtGui.QColor(216, 219, 223)
        self.scene().addPath(path, outline, QtGui.QBrush(fill))

        dimensions = {row.label: row.value for row in dimension_rows}
        if mode == DIMENSIONS_MODE and dimensions:
            self._add_dimensions(geometry, dimensions, insertion)
        elif mode == PROPERTIES_MODE:
            self._add_axes(geometry)
        if (insertion and
                (geometry.geometry_type, geometry.geometry_variant) in (
                    ("channel_section", "tapered_flange"),
                    ("cold_formed_channel", "stiffened_u"),
                )):
            self._add_insertion_marker(geometry, insertion)

        visual_bounds = self.scene().itemsBoundingRect()
        dimension_key = (geometry.geometry_type, geometry.geometry_variant)
        if dimension_key[0] == "hollow_section":
            scene_units_per_pixel = self._hollow_units_per_pixel(geometry.bounds)
        else:
            scene_units_per_pixel = self._scene_units_per_pixel(geometry.bounds)
        margin_x = CANVAS_MARGIN_PIXELS * scene_units_per_pixel
        margin_y = CANVAS_MARGIN_PIXELS * scene_units_per_pixel
        if mode == DIMENSIONS_MODE and dimension_key[0] == "hollow_section":
            rect = _hollow_section_envelope(
                geometry.bounds, scene_units_per_pixel,
            )
            self.scene().setSceneRect(QtCore.QRectF(*rect))
        elif mode == DIMENSIONS_MODE and dimension_key == ("equal_angle", "equal_leg"):
            rect = _balanced_section_envelope(
                geometry.bounds, visual_bounds, max(margin_x, margin_y)
            )
            self.scene().setSceneRect(QtCore.QRectF(*rect))
        elif mode == DIMENSIONS_MODE and dimension_key == (
                "cold_formed_channel", "stiffened_u"):
            rect = _ue_section_envelope(
                geometry.bounds, visual_bounds, max(margin_x, margin_y)
            )
            self.scene().setSceneRect(QtCore.QRectF(*rect))
        else:
            self.scene().setSceneRect(
                visual_bounds.adjusted(-margin_x, -margin_y, margin_x, margin_y)
            )
        self._fit()

    def _annotation_pen(self, line_style=None):
        pen = QtGui.QPen(QtGui.QColor(*DIMENSION_COLOR))
        pen.setCosmetic(True)
        pen.setWidthF(0.65)
        if line_style is not None:
            pen.setStyle(line_style)
        return pen

    def _scene_units_per_pixel(self, bounds):
        """Estimate model units per visible pixel before fitInView."""
        viewport_getter = getattr(self, "viewport", None)
        viewport = viewport_getter() if callable(viewport_getter) else None
        width = max(float(viewport.width()), 1.0) if viewport is not None else 500.0
        height = max(float(viewport.height()), 1.0) if viewport is not None else 240.0
        return max(bounds.width / (width * 0.58), bounds.height / (height * 0.66), 0.75)

    def _hollow_units_per_pixel(self, bounds):
        """Fit every hollow independently; catalog previews do not share a scale."""
        viewport_getter = getattr(self, "viewport", None)
        viewport = viewport_getter() if callable(viewport_getter) else None
        width = float(viewport.width()) if viewport is not None else 500.0
        height = float(viewport.height()) if viewport is not None else 240.0
        return _fit_units_per_pixel(bounds, width, height)

    @staticmethod
    def _d_offset_pixels(bounds):
        """Compensate the final fit compression without changing small profiles."""
        growth = _clamp((bounds.height - 180.0) / 448.0, 0.0, 1.0)
        return D_OFFSET_PIXELS + growth * D_MAX_COMPENSATION_PIXELS

    def _add_dimensions(self, geometry, dimensions, insertion=None, _palette=None):
        """Dispatch annotations by section typology without rebuilding contours."""
        key = (geometry.geometry_type, geometry.geometry_variant)
        if key == ("i_section", "parallel_flange"):
            self._add_i_section_dimensions(geometry, dimensions)
        elif key == ("i_section", "tapered_flange"):
            self._add_tapered_i_dimensions(geometry, dimensions)
        elif key == ("channel_section", "tapered_flange"):
            self._add_channel_dimensions(geometry, dimensions, insertion)
        elif key == ("equal_angle", "equal_leg"):
            self._add_equal_angle_dimensions(geometry, dimensions)
        elif key == ("tee_section", "standard_tee"):
            self._add_tee_dimensions(geometry, dimensions)
        elif key == ("cold_formed_channel", "stiffened_u"):
            self._add_ue_dimensions(geometry, dimensions)
        elif key in (
                ("hollow_section", "square"),
                ("hollow_section", "rectangular"),
                ("hollow_section", "circular")):
            self._add_hollow_dimensions(geometry, dimensions)

    def _add_hollow_dimensions(self, geometry, dimensions):
        """Annotate nominal hollow dimensions without deriving values from contours."""
        pen = self._annotation_pen()
        bounds = geometry.bounds
        left, right = bounds.min_x, bounds.max_x
        top, bottom = -bounds.max_y, -bounds.min_y
        units = self._hollow_units_per_pixel(bounds)
        clearance = GEOMETRY_CLEARANCE_PIXELS * units
        circular = geometry.geometry_variant == "circular"
        catalog_width_symbol = "ØD" if circular else "B"
        display_width_symbol = "Ø" if circular else "b"
        width_value = dimensions[catalog_width_symbol]
        self._add_hollow_width_dimension(
            display_width_symbol, left, right, top,
            (CHS_WIDTH_OFFSET_PIXELS if circular else HOLLOW_WIDTH_OFFSET_PIXELS) * units,
            clearance, units, width_value, pen, parenthesize=not circular,
        )
        if geometry.geometry_variant == "rectangular":
            self._add_vertical_dimension(
                "h", left, top, bottom, HOLLOW_HEIGHT_OFFSET_PIXELS * units,
                clearance, units, dimensions["H"], pen,
            )
        self._add_hollow_thickness_note(geometry, dimensions["t"], pen, units)

    def _add_hollow_width_dimension(self, symbol, left, right, top, offset,
                                    clearance, units, value, pen,
                                    parenthesize=True):
        line_y = top - offset
        parts = (
            self._dimension_parts(symbol, value) if parenthesize
            else (symbol, value.removesuffix(" mm"))
        )
        label = self._create_dimension_label(
            parts, pen.color()
        )
        self._position_label(
            label, (left + right) / 2.0, line_y,
            -label.width / 2.0, -TEXT_LINE_GAP - label.height,
        )
        overshoot = EXTENSION_OVERSHOOT_PIXELS * units
        self._line(left, top - clearance, left, line_y - overshoot, pen)
        self._line(right, top - clearance, right, line_y - overshoot, pen)
        self._line(left, line_y, right, line_y, pen)
        self._terminator(left, line_y, pen)
        self._terminator(right, line_y, pen)

    def _add_hollow_thickness_note(self, geometry, value, pen, units):
        """Use a short external leader; the displayed value remains catalog nominal."""
        bounds = geometry.bounds
        if geometry.geometry_variant == "circular":
            stations = dict(geometry.dimension_stations)
            outer_radius = stations["diameter"] / 2.0
            inner_radius = stations["inner_diameter"] / 2.0
            mid_radius = (outer_radius + inner_radius) / 2.0
            angle = math.radians(CHS_T_TARGET_ANGLE_DEGREES)
            target_x = mid_radius * math.cos(angle)
            target_y = mid_radius * math.sin(angle)
            leader_x = CHS_T_LEADER_X_PIXELS
            leader_y = CHS_T_LEADER_Y_PIXELS
        else:
            target_x = bounds.max_x
            target_y = -(bounds.min_y + bounds.height * 0.30)
            leader_x = HOLLOW_T_LEADER_X_PIXELS
            leader_y = -HOLLOW_T_LEADER_Y_PIXELS
        anchor_x = target_x + leader_x * units
        anchor_y = target_y + leader_y * units
        label = self._create_dimension_label(
            self._dimension_parts("t", value), pen.color()
        )
        self._position_label(label, anchor_x, anchor_y, 6.0, -label.height / 2.0)
        self._line(target_x, target_y, anchor_x, anchor_y, pen)
        self._device_ellipse(
            target_x, target_y, TF_WITNESS_RADIUS_PIXELS, pen,
            QtGui.QBrush(QtGui.QColor(*DIMENSION_COLOR)),
        )

    def _add_ue_dimensions(self, geometry, dimensions):
        """Annotate the real Ue contour from its geometric stations."""
        pen = self._annotation_pen()
        bounds = geometry.bounds
        stations = dict(geometry.dimension_stations)
        left, right = bounds.min_x, stations["nominal_flange_tip_x"]
        top, bottom = -stations["nominal_top_y"], -stations["nominal_bottom_y"]
        units = self._scene_units_per_pixel(bounds)
        clearance = GEOMETRY_CLEARANCE_PIXELS * units
        self._add_bf_dimension(
            left, right, top, BF_OFFSET_PIXELS * units, clearance, units,
            dimensions["bf"], pen,
        )
        self._add_vertical_dimension(
            "bw", left, top, bottom, self._d_offset_pixels(bounds) * units,
            clearance, units, dimensions["bw"], pen,
        )
        self._add_ue_lip_dimension(
            right, bottom, -stations["lower_lip_tip_y"], units,
            dimensions["D"], pen,
        )
        self._add_ue_thickness_note(geometry, dimensions["t"], pen, units)

    def _add_ue_lip_dimension(self, lip_x, nominal_bottom, lip_tip_y,
                              units, value, pen):
        """Dimension the nominal lower lip beside the physical stiffener."""
        line_x = lip_x + UE_D_OFFSET_PIXELS * units
        center_y = (nominal_bottom + lip_tip_y) / 2.0
        label = self._create_dimension_label(self._dimension_parts("D", value), pen.color())
        self._position_label(
            label, line_x, center_y, UE_D_TEXT_OFFSET_PIXELS,
            -label.height / 2.0,
        )
        clearance = GEOMETRY_CLEARANCE_PIXELS * units
        overshoot = EXTENSION_OVERSHOOT_PIXELS * units
        self._line(lip_x + clearance, lip_tip_y, line_x + overshoot, lip_tip_y, pen)
        self._line(
            lip_x + clearance, nominal_bottom,
            line_x + overshoot, nominal_bottom, pen,
        )
        self._line(line_x, lip_tip_y, line_x, nominal_bottom, pen)
        self._terminator(line_x, lip_tip_y, pen)
        self._terminator(line_x, nominal_bottom, pen)

    def _add_ue_thickness_note(self, geometry, value, pen, units):
        """Point to the straight inner face of the upper flange."""
        inner_flange = geometry.outer_path.segments[2]
        fraction = 0.62
        target_x = inner_flange.start.x + fraction * (
            inner_flange.end.x - inner_flange.start.x
        )
        target_y = -(inner_flange.start.y + fraction * (
            inner_flange.end.y - inner_flange.start.y
        ))
        anchor_x = target_x + UE_T_LEADER_X_PIXELS * units
        anchor_y = target_y + UE_T_LEADER_Y_PIXELS * units
        label = self._create_dimension_label(self._dimension_parts("t", value), pen.color())
        self._position_label(
            label, anchor_x, anchor_y, UE_D_TEXT_OFFSET_PIXELS,
            -label.height / 2.0,
        )
        self._line(target_x, target_y, anchor_x, anchor_y, pen)
        self._device_ellipse(
            target_x, target_y, TF_WITNESS_RADIUS_PIXELS, pen,
            QtGui.QBrush(QtGui.QColor(*DIMENSION_COLOR)),
        )

    def _add_vertical_dimension(self, symbol, edge_x, top, bottom, offset,
                                clearance, units, value, pen, right_side=False):
        line_x = edge_x + offset if right_side else edge_x - offset
        center_y = (top + bottom) / 2.0
        group = self._create_dimension_label(self._dimension_parts(symbol, value), pen.color())
        self._position_label(group, line_x, center_y, -group.width / 2.0, -group.height / 2.0)
        direction = 1.0 if right_side else -1.0
        overshoot = EXTENSION_OVERSHOOT_PIXELS * units
        start_x = edge_x + direction * clearance
        end_x = line_x + direction * overshoot
        self._line(start_x, top, end_x, top, pen)
        self._line(start_x, bottom, end_x, bottom, pen)
        break_half = (group.height / 2.0 + MIN_LABEL_CLEARANCE) * units
        self._line(line_x, top, line_x, center_y - break_half, pen)
        self._line(line_x, center_y + break_half, line_x, bottom, pen)
        self._terminator(line_x, top, pen)
        self._terminator(line_x, bottom, pen)

    def _add_tee_dimensions(self, geometry, dimensions):
        """Dimension the real centroidal nominal T contour."""
        pen = self._annotation_pen()
        bounds = geometry.bounds
        left, right = bounds.min_x, bounds.max_x
        top, bottom = -bounds.max_y, -bounds.min_y
        units = self._scene_units_per_pixel(bounds)
        clearance = GEOMETRY_CLEARANCE_PIXELS * units
        self._add_bf_dimension(
            left, right, top, BF_OFFSET_PIXELS * units, clearance, units,
            dimensions["bf"], pen,
        )
        self._add_d_dimension(
            left, top, bottom, self._d_offset_pixels(bounds) * units,
            clearance, units, dimensions["d"], pen,
        )
        stations = _tee_dimension_stations(geometry)
        self._add_tee_tw_dimension(
            stations["tw_left"], stations["tw_right"], dimensions["tw"], pen,
            section_bottom=stations["tw_section_bottom"], clearance=clearance,
            scene_units_per_pixel=units,
        )
        self._add_tf_dimension(
            stations["tf_right"], stations["tf_top"], stations["tf_bottom"],
            clearance, units, dimensions["tf"], pen,
        )

    def _add_channel_dimensions(self, geometry, dimensions, insertion=None):
        """Reuse the approved four-dimension language for a right-opening U."""
        pen = self._annotation_pen()
        bounds = geometry.bounds
        left, right = bounds.min_x, bounds.max_x
        top, bottom = -bounds.max_y, -bounds.min_y
        units = self._scene_units_per_pixel(bounds)
        clearance = GEOMETRY_CLEARANCE_PIXELS * units
        self._add_bf_dimension(
            left, right, top, BF_OFFSET_PIXELS * units, clearance, units,
            dimensions["bf"], pen,
        )
        self._add_d_dimension(
            left, top, bottom, self._d_offset_pixels(bounds) * units,
            clearance, units, dimensions["d"], pen,
        )
        web_inner_x = geometry.outer_path.segments[5].start.x
        self._add_tw_dimension(left, web_inner_x, dimensions["tw"], pen)
        x_tf, outer_y, inner_y = _channel_tf_measurement(geometry)
        marker_point = None
        references = section_insertion_references(geometry)
        if insertion and any(
            insertion in (reference.id, reference.label) for reference in references
        ):
            point = insertion_reference(geometry, insertion).point
            marker_point = (point.x, -point.y)
        self._add_channel_tf_dimension(
            x_tf, right, -outer_y, -inner_y, clearance, units,
            dimensions["tf"], pen, marker_point,
        )

    def _add_i_section_dimensions(self, geometry, dimensions):
        """Add the four principal dimensions of a parallel-flange I section."""
        pen = self._annotation_pen()
        bounds = geometry.bounds
        left, right = bounds.min_x, bounds.max_x
        top, bottom = -bounds.max_y, -bounds.min_y
        scene_units_per_pixel = self._scene_units_per_pixel(bounds)
        offset_x = self._d_offset_pixels(bounds) * scene_units_per_pixel
        offset_y = BF_OFFSET_PIXELS * scene_units_per_pixel
        clearance = GEOMETRY_CLEARANCE_PIXELS * scene_units_per_pixel

        self._add_bf_dimension(
            left, right, top, offset_y, clearance, scene_units_per_pixel,
            dimensions["bf"], pen,
        )
        self._add_d_dimension(
            left, top, bottom, offset_x, clearance, scene_units_per_pixel,
            dimensions["d"], pen,
        )

        web_left = geometry.outer_path.segments[8].end.x
        web_right = geometry.outer_path.segments[3].end.x
        self._add_tw_dimension(
            web_left, web_right, dimensions["tw"], pen
        )

        bottom_flange = geometry.outer_path.segments[1]
        flange_top = -bottom_flange.end.y
        flange_bottom = -bottom_flange.start.y
        self._add_tf_dimension(
            right, flange_top, flange_bottom, clearance, scene_units_per_pixel,
            dimensions["tf"], pen,
        )

    def _add_tapered_i_dimensions(self, geometry, dimensions):
        """Dimension the real symmetric tapered I, including tf at BIM TL."""
        pen = self._annotation_pen()
        bounds = geometry.bounds
        left, right = bounds.min_x, bounds.max_x
        top, bottom = -bounds.max_y, -bounds.min_y
        units = self._scene_units_per_pixel(bounds)
        clearance = GEOMETRY_CLEARANCE_PIXELS * units
        self._add_bf_dimension(
            left, right, top, BF_OFFSET_PIXELS * units, clearance, units,
            dimensions["bf"], pen,
        )
        self._add_d_dimension(
            left, top, bottom, self._d_offset_pixels(bounds) * units,
            clearance, units, dimensions["d"], pen,
        )
        web_right = geometry.outer_path.segments[5].start.x
        self._add_tw_dimension(-web_right, web_right, dimensions["tw"], pen)
        x_tf, outer_y, inner_y = _tapered_i_tf_measurement(geometry)
        self._add_channel_tf_dimension(
            x_tf, right, -outer_y, -inner_y, clearance, units,
            dimensions["tf"], pen,
        )

    def _add_equal_angle_dimensions(self, geometry, dimensions):
        """Add equal-leg length and thickness dimensions to an L contour."""
        pen = self._annotation_pen()
        bounds = geometry.bounds
        left, right = bounds.min_x, bounds.max_x
        bottom = -bounds.min_y
        scene_units_per_pixel = self._scene_units_per_pixel(bounds)
        clearance = GEOMETRY_CLEARANCE_PIXELS * scene_units_per_pixel

        self._add_b_dimension(
            left, right, bottom, ANGLE_B_OFFSET_PIXELS * scene_units_per_pixel,
            clearance, scene_units_per_pixel, dimensions["b"], pen,
        )
        self._add_angle_b_vertical_dimension(
            left, -bounds.max_y, -bounds.min_y,
            ANGLE_VERTICAL_B_OFFSET_PIXELS * scene_units_per_pixel,
            clearance, scene_units_per_pixel, dimensions["b"], pen,
        )

        horizontal_leg = geometry.outer_path.segments[1]
        leg_top = -horizontal_leg.end.y
        leg_bottom = -horizontal_leg.start.y
        self._add_angle_t_dimension(
            right, leg_top, leg_bottom, clearance, scene_units_per_pixel,
            dimensions["t"], pen,
        )

    def _add_b_dimension(self, left, right, bottom, offset, clearance,
                         scene_units_per_pixel, value, pen):
        line_y = bottom + offset
        group = self._create_dimension_label(self._dimension_parts("b", value), pen.color())
        self._position_label(
            group, (left + right) / 2.0, line_y,
            -group.width / 2.0, TEXT_LINE_GAP,
        )
        overshoot = EXTENSION_OVERSHOOT_PIXELS * scene_units_per_pixel
        self._line(left, bottom + clearance, left, line_y + overshoot, pen)
        self._line(right, bottom + clearance, right, line_y + overshoot, pen)
        self._line(left, line_y, right, line_y, pen)
        self._terminator(left, line_y, pen)
        self._terminator(right, line_y, pen)

    def _add_angle_b_vertical_dimension(self, left, top, bottom, offset,
                                        clearance, scene_units_per_pixel,
                                        value, pen):
        line_x = left - offset
        center_y = (top + bottom) / 2.0
        group = self._create_dimension_label(self._dimension_parts("b", value), pen.color())
        self._position_label(
            group, line_x, center_y, -group.width / 2.0, -group.height / 2.0
        )
        break_half = (
            group.height / 2.0 + MIN_LABEL_CLEARANCE
        ) * scene_units_per_pixel
        overshoot = EXTENSION_OVERSHOOT_PIXELS * scene_units_per_pixel
        self._line(left - clearance, top, line_x - overshoot, top, pen)
        self._line(left - clearance, bottom, line_x - overshoot, bottom, pen)
        self._line(line_x, top, line_x, center_y - break_half, pen)
        self._line(line_x, center_y + break_half, line_x, bottom, pen)
        self._terminator(line_x, top, pen)
        self._terminator(line_x, bottom, pen)

    def _add_angle_t_dimension(self, right, leg_top, leg_bottom, clearance,
                               scene_units_per_pixel, value, pen):
        line_x = right + TF_LINE_OFFSET_PIXELS * scene_units_per_pixel
        group = self._create_dimension_label(self._dimension_parts("t", value), pen.color())
        self._position_label(
            group, line_x, (leg_top + leg_bottom) / 2.0,
            TF_TEXT_OFFSET, -group.height / 2.0,
        )
        self._line(right + clearance, leg_top, line_x, leg_top, pen)
        self._line(right + clearance, leg_bottom, line_x, leg_bottom, pen)
        self._device_line(
            line_x, leg_top, 0.0, 0.0,
            ANGLE_T_EXTENSION_OVERHANG_PIXELS, 0.0, pen,
        )
        self._device_line(
            line_x, leg_bottom, 0.0, 0.0,
            ANGLE_T_EXTENSION_OVERHANG_PIXELS, 0.0, pen,
        )
        self._line(line_x, leg_top, line_x, leg_bottom, pen)
        self._terminator(line_x, leg_top, pen)
        self._terminator(line_x, leg_bottom, pen)

    @staticmethod
    def _dimension_parts(symbol, value):
        return f"({symbol})", value.removesuffix(" mm")

    def _add_bf_dimension(self, left, right, top, offset, clearance,
                          scene_units_per_pixel, value, pen):
        line_y = top - offset
        group = self._create_dimension_label(self._dimension_parts("bf", value), pen.color())
        self._position_label(
            group, (left + right) / 2.0, line_y,
            -group.width / 2.0, -TEXT_LINE_GAP - group.height,
        )
        overshoot = EXTENSION_OVERSHOOT_PIXELS * scene_units_per_pixel
        self._line(left, top - clearance, left, line_y - overshoot, pen)
        self._line(right, top - clearance, right, line_y - overshoot, pen)
        self._line(left, line_y, right, line_y, pen)
        self._terminator(left, line_y, pen)
        self._terminator(right, line_y, pen)

    def _add_d_dimension(self, left, top, bottom, offset, clearance,
                         scene_units_per_pixel, value, pen):
        line_x = left - offset
        center_y = (top + bottom) / 2.0
        group = self._create_dimension_label(self._dimension_parts("d", value), pen.color())
        self._position_label(
            group, line_x, center_y, -group.width / 2.0, -group.height / 2.0
        )
        break_half = (
            group.height / 2.0 + MIN_LABEL_CLEARANCE
        ) * scene_units_per_pixel
        overshoot = EXTENSION_OVERSHOOT_PIXELS * scene_units_per_pixel
        self._line(left - clearance, top, line_x - overshoot, top, pen)
        self._line(left - clearance, bottom, line_x - overshoot, bottom, pen)
        self._line(line_x, top, line_x, center_y - break_half, pen)
        self._line(line_x, center_y + break_half, line_x, bottom, pen)
        self._terminator(line_x, top, pen)
        self._terminator(line_x, bottom, pen)

    def _add_tw_dimension(self, web_left, web_right, value, pen, line_y=0.0):
        group = self._create_dimension_label(self._dimension_parts("tw", value), pen.color())
        self._position_label(
            group, web_right, line_y,
            TW_TEXT_OFFSET, -TEXT_LINE_GAP - group.height,
        )
        self._device_line(
            web_left, line_y, 0.0, -SMALL_EXTENSION_HALF_PIXELS,
            0.0, SMALL_EXTENSION_HALF_PIXELS, pen,
        )
        self._device_line(
            web_right, line_y, 0.0, -SMALL_EXTENSION_HALF_PIXELS,
            0.0, SMALL_EXTENSION_HALF_PIXELS, pen,
        )
        self._line(web_left, line_y, web_right, line_y, pen)
        self._terminator(web_left, line_y, pen)
        self._terminator(web_right, line_y, pen)
        self._device_line(
            web_right, line_y, 0.0, 0.0,
            TW_TEXT_OFFSET + group.width + LINE_END_PADDING + EXTENSION_OVERSHOOT_PIXELS,
            0.0, pen,
        )

    def _add_tee_tw_dimension(self, web_left, web_right, value, pen,
                              section_bottom, clearance,
                              scene_units_per_pixel):
        """Place horizontal web thickness below the T web tip."""
        line_y = section_bottom + TEE_TW_OFFSET_PIXELS * scene_units_per_pixel
        group = self._create_dimension_label(self._dimension_parts("tw", value), pen.color())
        self._position_label(
            group, (web_left + web_right) / 2.0, line_y,
            -group.width / 2.0, TEXT_LINE_GAP,
        )
        overshoot = EXTENSION_OVERSHOOT_PIXELS * scene_units_per_pixel
        self._line(
            web_left, section_bottom + clearance,
            web_left, line_y + overshoot, pen,
        )
        self._line(
            web_right, section_bottom + clearance,
            web_right, line_y + overshoot, pen,
        )
        self._line(web_left, line_y, web_right, line_y, pen)
        self._terminator(web_left, line_y, pen)
        self._terminator(web_right, line_y, pen)

    def _add_tf_dimension(self, right, flange_top, flange_bottom, clearance,
                          scene_units_per_pixel, value, pen):
        line_x = right + TF_LINE_OFFSET_PIXELS * scene_units_per_pixel
        group = self._create_dimension_label(self._dimension_parts("tf", value), pen.color())
        self._position_label(
            group, line_x, (flange_top + flange_bottom) / 2.0,
            TF_TEXT_OFFSET, -group.height / 2.0,
        )
        self._line(right + clearance, flange_top, line_x, flange_top, pen)
        self._line(right + clearance, flange_bottom, line_x, flange_bottom, pen)
        self._device_line(
            line_x, flange_top, 0.0, 0.0, EXTENSION_OVERSHOOT_PIXELS, 0.0, pen
        )
        self._device_line(
            line_x, flange_bottom, 0.0, 0.0, EXTENSION_OVERSHOOT_PIXELS, 0.0, pen
        )
        self._line(line_x, flange_top, line_x, flange_bottom, pen)
        self._terminator(line_x, flange_top, pen)
        self._terminator(line_x, flange_bottom, pen)

    def _add_channel_tf_dimension(self, x_tf, section_right, flange_top,
                                  flange_bottom, clearance,
                                  scene_units_per_pixel, value, pen,
                                  marker_point=None):
        """Dimension vertical tf at its station, with the line outside the U."""
        line_x = section_right + TF_LINE_OFFSET_PIXELS * scene_units_per_pixel
        group = self._create_dimension_label(self._dimension_parts("tf", value), pen.color())
        self._position_label(
            group, line_x, (flange_top + flange_bottom) / 2.0,
            TF_TEXT_OFFSET, -group.height / 2.0,
        )
        start_x = x_tf + clearance
        marker_gap = (
            INSERTION_MARKER_CROSSHAIR_PIXELS + 2.0
        ) * scene_units_per_pixel
        for y in (flange_top, flange_bottom):
            if (marker_point is not None
                    and abs(marker_point[1] - y) <= 1e-9
                    and start_x < marker_point[0] < line_x):
                self._line(start_x, y, marker_point[0] - marker_gap, y, pen)
                self._line(marker_point[0] + marker_gap, y, line_x, y, pen)
            else:
                self._line(start_x, y, line_x, y, pen)
        self._line(line_x, flange_top, line_x, flange_bottom, pen)
        self._terminator(line_x, flange_top, pen)
        self._terminator(line_x, flange_bottom, pen)
        for y in (flange_top, flange_bottom):
            self._device_ellipse(
                x_tf, y, TF_WITNESS_RADIUS_PIXELS, pen,
                QtGui.QBrush(QtGui.QColor(*DIMENSION_COLOR)),
            )

    def _add_insertion_marker(self, geometry, value):
        """Draw the shared insertion reference as a scale-independent target."""
        if not any(
            value in (reference.id, reference.label)
            for reference in section_insertion_references(geometry)
        ):
            return False
        point = insertion_reference(geometry, value).point
        x, y = point.x, -point.y
        pen = QtGui.QPen(QtGui.QColor(*INSERTION_MARKER_COLOR))
        pen.setCosmetic(True)
        pen.setWidthF(1.25)
        self._device_ellipse(
            x, y, INSERTION_MARKER_RADIUS_PIXELS, pen,
            QtGui.QBrush(QtGui.QColor(255, 255, 255)),
        )
        arm = INSERTION_MARKER_CROSSHAIR_PIXELS
        self._device_line(x, y, -arm, 0.0, arm, 0.0, pen)
        self._device_line(x, y, 0.0, -arm, 0.0, arm, pen)
        self._device_ellipse(
            x, y, INSERTION_MARKER_CENTER_PIXELS, pen,
            QtGui.QBrush(QtGui.QColor(*INSERTION_MARKER_COLOR)),
        )
        return True

    def _add_axes(self, geometry):
        bounds = geometry.bounds
        extension = _clamp(max(bounds.width, bounds.height) * 0.10, 18.0, 48.0)
        x_pen = QtGui.QPen(QtGui.QColor(205, 45, 45))
        y_pen = QtGui.QPen(QtGui.QColor(38, 145, 72))
        for pen in (x_pen, y_pen):
            pen.setCosmetic(True)
            pen.setWidthF(1.05)
            pen.setDashPattern([9.0, 3.0, 2.0, 3.0])
        left, right = bounds.min_x - extension, bounds.max_x + extension
        top, bottom = -bounds.max_y - extension, -bounds.min_y + extension
        self._line(left, 0.0, right, 0.0, x_pen)
        self._line(0.0, top, 0.0, bottom, y_pen)
        self._label_lines(("X",), left, 0.0, x_pen.color(), x_offset=-8.0, bold=True)
        self._label_lines(("X",), right, 0.0, x_pen.color(), x_offset=8.0, bold=True)
        self._label_lines(("Y",), 0.0, top, y_pen.color(), y_offset=-9.0, bold=True)
        self._label_lines(("Y",), 0.0, bottom, y_pen.color(), y_offset=9.0, bold=True)
        radius = _clamp(min(bounds.width, bounds.height) * 0.018, 2.5, 5.0)
        self.scene().addEllipse(
            -radius, -radius, radius * 2.0, radius * 2.0,
            self._annotation_pen(), QtGui.QBrush(QtGui.QColor(255, 255, 255)),
        )

    def _line(self, x1, y1, x2, y2, pen):
        return self.scene().addLine(x1, y1, x2, y2, pen)

    def _device_line(self, anchor_x, anchor_y, x1, y1, x2, y2, pen):
        item = self.scene().addLine(x1, y1, x2, y2, pen)
        item.setPos(anchor_x, anchor_y)
        item.setFlag(_ignores_transformations_flag(), True)
        return item

    def _device_ellipse(self, anchor_x, anchor_y, radius, pen, brush):
        item = self.scene().addEllipse(
            -radius, -radius, radius * 2.0, radius * 2.0, pen, brush
        )
        item.setPos(anchor_x, anchor_y)
        item.setFlag(_ignores_transformations_flag(), True)
        return item

    def _label_lines(self, lines, center_x, center_y, color, above=False,
                     x_offset=0.0, y_offset=0.0, bold=False):
        """Center every line independently and keep text size in screen pixels."""
        items = []
        total_height = 0.0
        for text in lines:
            item = self.scene().addText(text)
            item.setDefaultTextColor(color)
            if bold:
                font = item.font()
                font.setBold(True)
                item.setFont(font)
            item.setFlag(_ignores_transformations_flag(), True)
            rect = item.boundingRect()
            items.append((item, rect))
            total_height += rect.height()
        start_y = center_y - total_height if above else center_y - total_height / 2.0
        start_y += y_offset
        for item, rect in items:
            item.setPos(center_x + x_offset - rect.width() / 2.0, start_y)
            start_y += rect.height()

    def _create_dimension_label(self, parts, color):
        """Create one scale-independent rich label with invariant internal spacing."""
        item = self.scene().addText("")
        item.setDefaultTextColor(color)
        item.setHtml(
            "<span style='background-color:#ffffff'>"
            f"<b>{escape(parts[0])}</b>{SYMBOL_VALUE_SEPARATOR}{escape(parts[1])}</span>"
        )
        item.setFlag(_ignores_transformations_flag(), True)
        rect = item.boundingRect()
        return _DimensionLabel(item, rect.width(), rect.height())

    def _position_label(self, group, anchor_x, anchor_y, local_x, local_y):
        group.item.setPos(anchor_x, anchor_y)
        group.item.setTransform(
            QtGui.QTransform.fromTranslate(local_x, local_y)
        )

    def _terminator(self, x, y, pen):
        self._device_line(
            x, y, -TICK_PIXELS, TICK_PIXELS, TICK_PIXELS, -TICK_PIXELS, pen
        )

    def clear_geometry(self):
        self.scene().clear()

    def _fit(self):
        rect = self.scene().sceneRect()
        if not rect.isEmpty():
            margin = max(rect.width(), rect.height()) * 0.08
            self.fitInView(
                rect.adjusted(-margin, -margin, margin, margin),
                QtCore.Qt.KeepAspectRatio,
            )

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._fit()


__all__ = [
    "DIMENSIONS_MODE", "NEUTRAL_MODE", "PREVIEW_MODES", "PROPERTIES_MODE",
    "SectionPreviewView", "_balanced_section_envelope", "_fit_units_per_pixel",
    "_hollow_section_envelope",
    "_channel_tf_measurement",
    "_tapered_i_tf_measurement", "_tee_dimension_stations", "_ue_section_envelope",
]
