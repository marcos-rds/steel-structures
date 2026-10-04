# SPDX-License-Identifier: LGPL-2.1-or-later
"""Transient Coin preview for an arbitrary StructuralPlate outline and solid."""

import FreeCAD as App
from pivy import coin

from ..plate_freecad_geometry import build_plate_shape


class PlatePreview:
    """Draw in the active view without adding an object to the document."""

    def __init__(self, view):
        self._scene = view.getSceneGraph()
        self._root = coin.SoSeparator()
        self._scene.addChild(self._root)
        self._solid_signature = None

    def _replace(self, children):
        self._root.removeAllChildren()
        style = coin.SoPickStyle()
        style.style = coin.SoPickStyle.UNPICKABLE
        self._root.addChild(style)
        for child in children:
            self._root.addChild(child)

    @staticmethod
    def _line(points, color, width=2):
        if len(points) < 2:
            return None
        branch = coin.SoSeparator()
        material = coin.SoMaterial()
        material.diffuseColor.setValue(*color)
        branch.addChild(material)
        draw = coin.SoDrawStyle()
        draw.lineWidth = width
        branch.addChild(draw)
        coords = coin.SoCoordinate3()
        coords.point.setValues(0, len(points), [(p.x, p.y, p.z) for p in points])
        branch.addChild(coords)
        lines = coin.SoLineSet()
        lines.numVertices.setValues(0, 1, [len(points)])
        branch.addChild(lines)
        return branch

    @staticmethod
    def _first_marker(point):
        branch = coin.SoSeparator()
        material = coin.SoMaterial()
        material.diffuseColor.setValue(0.12, 0.88, 0.28)
        branch.addChild(material)
        draw = coin.SoDrawStyle()
        draw.pointSize = 9
        branch.addChild(draw)
        coords = coin.SoCoordinate3()
        coords.point.setValues(0, 1, [(point.x, point.y, point.z)])
        branch.addChild(coords)
        branch.addChild(coin.SoPointSet())
        return branch

    def outline(self, points, cursor=None):
        points = [App.Vector(point) for point in points]
        self._solid_signature = None
        children = []
        confirmed = self._line(points, (0.15, 0.77, 0.98), 3)
        if confirmed is not None:
            children.append(confirmed)
        if points:
            children.append(self._first_marker(points[0]))
        if points and cursor is not None:
            moving = self._line((points[-1], App.Vector(cursor)), (0.99, 0.78, 0.15))
            if moving is not None:
                children.append(moving)
        self._replace(children)

    def solid(self, contour, placement, thickness, offset):
        """Build only on a closed contour or a changed parameter, never per mouse move."""
        vertices = tuple(tuple(point) for point in contour.vertices)
        signature = (vertices, str(placement), float(thickness), float(offset))
        if signature == self._solid_signature:
            return
        self._solid_signature = signature
        shape = build_plate_shape(contour, thickness, offset).copy()
        shape.Placement = placement.multiply(shape.Placement)
        data = coin.SoInput()
        data.setBuffer(shape.writeInventor())
        geometry = coin.SoDB.readAll(data)
        if geometry is None:
            raise ValueError("Falha ao criar preview da chapa.")
        branch = coin.SoSeparator()
        material = coin.SoMaterial()
        material.diffuseColor.setValue(0.24, 0.69, 0.87)
        material.transparency = 0.55
        branch.addChild(material)
        branch.addChild(geometry)
        self._replace((branch,))

    def clear(self):
        self._solid_signature = None
        self._root.removeAllChildren()

    def remove(self):
        scene, self._scene = self._scene, None
        root, self._root = self._root, None
        self._solid_signature = None
        if scene is not None and root is not None and scene.findChild(root) >= 0:
            # The scene graph owns its child; match the existing truss preview
            # lifecycle and do not add a second manual Coin ref/unref pair.
            scene.removeChild(root)
