# SPDX-License-Identifier: LGPL-2.1-or-later
"""Shared transient 3D preview for member and column creation tools."""

from dataclasses import dataclass

import FreeCAD as App
from draftutils import gui_utils

from .. import profile_catalog
from ..member import _insertion_translation, _member_frame_rotation, _section_face


PREVIEW_TRANSPARENCY = 65


@dataclass(frozen=True)
class PreviewState:
    shape_signature: tuple | None = None
    placement_signature: tuple | None = None
    color: tuple | None = None


def configure_preview_object(obj):
    """Apply the established non-tree, translucent, unsnappable appearance."""
    gui_utils.format_object(obj)
    obj.ViewObject.ShowInTree = False
    obj.ViewObject.Transparency = PREVIEW_TRANSPARENCY
    obj.ViewObject.Selectable = False


def update_member_preview(obj, state, profile_designation, start, end,
                          insertion, rotation, color, offset_x=0.0,
                          offset_y=0.0, section_geometry_mode="Detailed"):
    """Update a temporary object through the same section/frame pipeline."""
    profile = profile_catalog.get(profile_designation)
    start = App.Vector(start)
    axis = App.Vector(end).sub(start)
    length = axis.Length
    if length <= 1e-7:
        raise ValueError("Eixo degenerado")
    direction = App.Vector(axis)
    direction.normalize()

    shape_signature = (
        profile_designation, length, insertion, float(offset_x), float(offset_y),
        str(section_geometry_mode),
    )
    shape_changed = shape_signature != state.shape_signature
    if shape_changed:
        face = _section_face(profile, section_geometry_mode)
        tx, ty = _insertion_translation(profile, insertion, section_geometry_mode)
        face.translate(App.Vector(tx + float(offset_x), ty + float(offset_y), 0.0))
        obj.Shape = face.extrude(App.Vector(0.0, 0.0, length))

    placement_signature = (
        start.x, start.y, start.z, direction.x, direction.y, direction.z,
        float(rotation),
    )
    if shape_changed or placement_signature != state.placement_signature:
        roll = App.Rotation(App.Vector(0.0, 0.0, 1.0), float(rotation))
        alignment = _member_frame_rotation(direction)
        obj.Placement = App.Placement(start, alignment.multiply(roll))

    color = tuple(color)
    if color != state.color:
        obj.ViewObject.ShapeColor = color
    obj.ViewObject.Visibility = True
    obj.ViewObject.Selectable = False
    return PreviewState(shape_signature, placement_signature, color)


__all__ = [
    "PREVIEW_TRANSPARENCY", "PreviewState", "configure_preview_object",
    "update_member_preview",
]
