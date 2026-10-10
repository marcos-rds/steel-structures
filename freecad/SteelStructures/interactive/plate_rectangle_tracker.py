# SPDX-License-Identifier: LGPL-2.1-or-later
"""Local specialization of Draft's rectangle constructor (FreeCAD 1.1.x).

Constructor adapted from FreeCAD Draft gui_trackers (Yorik van Havre et al.).
All updates, plane handling, insertion and teardown remain inherited Draft code.
Do not call rectangleTracker.__init__: its explicit count exceeds its source.
"""
from FreeCAD import Vector
from draftguitools import gui_trackers


class PlateRectangleTracker(gui_trackers.rectangleTracker):
    def __init__(self, dotted=False, scolor=None, swidth=None, face=False):
        coin = gui_trackers.coin
        self.origin = Vector(0, 0, 0)
        line = coin.SoLineSet()
        line.numVertices.setValue(5)
        self.coords = coin.SoCoordinate3()
        points = [[0, 0, 0], [2, 0, 0], [2, 2, 0], [0, 2, 0], [0, 0, 0]]
        self.coords.point.setValues(0, len(points), points)
        children = [self.coords, line]
        if face:
            material = coin.SoMaterial()
            material.transparency.setValue(0.5)
            material.diffuseColor.setValue([0.5, 0.5, 1.0])
            polygon = coin.SoIndexedFaceSet()
            polygon.coordIndex.setValues([0, 1, 2, 3])
            children.extend([material, polygon])
        gui_trackers.Tracker.__init__(self, dotted, scolor, swidth, children,
                                     name="rectangleTracker")
        wp = self._get_wp()
        self.u, self.v = wp.u, wp.v
