# SPDX-License-Identifier: LGPL-2.1-or-later
"""FreeCAD BRep adapter for the pure, arbitrary 2D plate contour."""

import math

import FreeCAD as App
import Part


def build_plate_shape(contour, thickness, offset=0.0):
    """Extrude a local XY polygon along local +Z, starting at ``offset``."""
    thickness = float(getattr(thickness, "Value", thickness))
    offset = float(getattr(offset, "Value", offset))
    if not math.isfinite(thickness) or thickness <= 0.0:
        raise ValueError("Espessura da chapa deve ser maior que zero.")
    if not math.isfinite(offset):
        raise ValueError("Offset da chapa deve ser finito.")
    vertices = contour.vertices
    # Force the face's geometric normal to +Z without changing the persisted
    # contour order or losing the orientation chosen by the user.
    ordered = vertices if contour.signed_area > 0 else tuple(reversed(vertices))
    points = [App.Vector(x, y, offset) for x, y in ordered]
    wire = Part.makePolygon(points + [points[0]])
    face = Part.Face(wire)
    shape = face.extrude(App.Vector(0, 0, thickness))
    if shape.isNull() or not shape.isValid() or len(shape.Solids) != 1:
        raise ValueError("Não foi possível construir um sólido válido para a chapa.")
    return shape


__all__ = ["build_plate_shape"]
