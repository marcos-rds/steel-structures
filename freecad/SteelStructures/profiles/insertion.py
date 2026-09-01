# SPDX-License-Identifier: LGPL-2.1-or-later
"""Insertion references derived from the shared section geometry."""

from __future__ import annotations

from dataclasses import dataclass

from .geometry import Point2D, SectionGeometry2D


@dataclass(frozen=True)
class InsertionReference:
    id: str
    label: str
    point: Point2D


_I_LABELS = (
    ("centroid", "Centroide"),
    ("left", "Face esquerda"),
    ("right", "Face direita"),
    ("top", "Face superior"),
    ("bottom", "Face inferior"),
    ("top_left", "Canto superior esquerdo"),
    ("top_right", "Canto superior direito"),
    ("bottom_left", "Canto inferior esquerdo"),
    ("bottom_right", "Canto inferior direito"),
)


def section_insertion_references(geometry: SectionGeometry2D):
    """Return stable references supported by one section typology."""
    bounds = geometry.bounds
    key = (geometry.geometry_type, geometry.geometry_variant)
    if key == ("equal_angle", "equal_leg"):
        # Segment 3 starts at the re-entrant corner in the canonical L contour.
        inner = geometry.outer_path.segments[3].start
        values = (
            ("centroid", "Centroide", geometry.origin),
            ("outer_corner", "Quina externa", Point2D(bounds.min_x, bounds.min_y)),
            ("top_tip", "Ponta superior", Point2D(bounds.min_x, bounds.max_y)),
            ("right_tip", "Ponta direita", Point2D(bounds.max_x, bounds.min_y)),
            ("inner_corner", "Quina interna", inner),
        )
    elif key in (("i_section", "parallel_flange"),
                 ("i_section", "tapered_flange")):
        x0, y0 = geometry.origin.x, geometry.origin.y
        points = {
            "centroid": Point2D(x0, y0),
            "left": Point2D(bounds.min_x, y0),
            "right": Point2D(bounds.max_x, y0),
            "top": Point2D(x0, bounds.max_y),
            "bottom": Point2D(x0, bounds.min_y),
            "top_left": Point2D(bounds.min_x, bounds.max_y),
            "top_right": Point2D(bounds.max_x, bounds.max_y),
            "bottom_left": Point2D(bounds.min_x, bounds.min_y),
            "bottom_right": Point2D(bounds.max_x, bounds.min_y),
        }
        values = tuple((identifier, label, points[identifier]) for identifier, label in _I_LABELS)
    elif key == ("channel_section", "tapered_flange"):
        stations = dict(geometry.dimension_stations)
        rear_x = stations["web_back_x"]
        inner_x = stations["web_inner_x"]
        tip_x = stations["flange_tip_x"]
        web_mid_x = (rear_x + inner_x) / 2.0
        values = (
            ("centroid", "Centroide", geometry.origin),
            ("web_center", "Centro da alma", Point2D(web_mid_x, 0.0)),
            ("web_back", "Face externa da alma", Point2D(rear_x, 0.0)),
            ("rear_top", "Canto superior traseiro", Point2D(rear_x, bounds.max_y)),
            ("rear_bottom", "Canto inferior traseiro", Point2D(rear_x, bounds.min_y)),
            ("flange_top_tip", "Ponta superior da mesa", Point2D(tip_x, bounds.max_y)),
            ("flange_bottom_tip", "Ponta inferior da mesa", Point2D(tip_x, bounds.min_y)),
        )
    elif key == ("cold_formed_channel", "stiffened_u"):
        stations = dict(geometry.dimension_stations)
        upper_tip = Point2D(stations["nominal_flange_tip_x"] - 0.5 * stations["thickness"],
                            stations["upper_lip_tip_y"])
        lower_tip = Point2D(stations["nominal_flange_tip_x"] - 0.5 * stations["thickness"],
                            stations["lower_lip_tip_y"])
        outer_flange_mid_x = (
            stations["flange_web_tangent_x"]
            + stations["flange_lip_tangent_x"]
        ) / 2.0
        values = (
            ("centroid", "Centroide", geometry.origin),
            ("web_center", "Centro da alma", Point2D(stations["web_mean_x"], 0.0)),
            ("web_back", "Face externa da alma", Point2D(stations["external_web_x"], 0.0)),
            ("rear_top", "Canto externo superior", Point2D(
                stations["external_web_x"], stations["nominal_top_y"],
            )),
            ("rear_bottom", "Canto externo inferior", Point2D(
                stations["external_web_x"], stations["nominal_bottom_y"],
            )),
            ("lip_top_tip", "Ponta do enrijecedor superior", upper_tip),
            ("lip_bottom_tip", "Ponta do enrijecedor inferior", lower_tip),
            ("outer_top_mid", "Centro externo superior", Point2D(
                outer_flange_mid_x, stations["nominal_top_y"],
            )),
            ("outer_bottom_mid", "Centro externo inferior", Point2D(
                outer_flange_mid_x, stations["nominal_bottom_y"],
            )),
            ("outer_lip_top_corner", "Canto externo do enrijecedor superior", Point2D(
                stations["nominal_flange_tip_x"], stations["nominal_top_y"],
            )),
            ("outer_lip_bottom_corner", "Canto externo do enrijecedor inferior", Point2D(
                stations["nominal_flange_tip_x"], stations["nominal_bottom_y"],
            )),
        )
    elif key == ("tee_section", "standard_tee"):
        values = (
            ("centroid", "Centroide", geometry.origin),
            ("top", "Face superior", Point2D(geometry.origin.x, bounds.max_y)),
            ("bottom", "Ponta inferior da alma", Point2D(geometry.origin.x, bounds.min_y)),
            ("top_left", "Canto superior esquerdo", Point2D(bounds.min_x, bounds.max_y)),
            ("top_right", "Canto superior direito", Point2D(bounds.max_x, bounds.max_y)),
        )
    else:
        values = (("centroid", "Centroide", geometry.origin),)
    return tuple(InsertionReference(*value) for value in values)


def insertion_reference(geometry: SectionGeometry2D, value: str):
    """Resolve a stable id or current label, falling back to the centroid."""
    references = section_insertion_references(geometry)
    return next(
        (item for item in references if value in (item.id, item.label)), references[0]
    )


def insertion_translation(geometry: SectionGeometry2D, value: str):
    point = insertion_reference(geometry, value).point
    return -point.x, -point.y


__all__ = [
    "InsertionReference", "insertion_reference", "insertion_translation",
    "section_insertion_references",
]
