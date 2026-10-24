# SPDX-License-Identifier: LGPL-2.1-or-later
"""Bilateral view-only preview using the existing exact member renderer."""

import math
from types import SimpleNamespace

import FreeCAD as App

from ..member_plane_cut import orthonormal_plane_basis
from .member_adjustment_preview import MemberAdjustmentPreview


class MemberMiterPreview:
    """Own both candidate branches and the transient meeting-plane outline."""

    COLORS = ((.12, .62, .82), (.94, .58, .16))

    def __init__(self, scene_graph):
        self.scene_graph = scene_graph
        self.previews = tuple(MemberAdjustmentPreview(scene_graph, color) for color in self.COLORS)
        self.node = None

    def _meeting_marker(self, candidate):
        from pivy import coin

        point = App.Vector(*candidate.plan.point)
        e1, e2, _normal = orthonormal_plane_basis(candidate.plan.normal)
        e1, e2 = App.Vector(*e1), App.Vector(*e2)
        # Marker scale follows the section-sized transverse envelope, not the
        # member length. It adds no section envelope to the geometric preview.
        sizes = []
        for item in candidate.candidates:
            box = item.result.Shape.BoundBox
            sizes.append(math.hypot(box.XLength, box.YLength))
        radius = max(max(sizes) * .65, .5)
        corners = [point + e1*x + e2*y for x, y in (
            (-radius, -radius), (radius, -radius), (radius, radius),
            (-radius, radius), (-radius, -radius))]
        # Cross at the actual axis meeting makes the proposed encounter clear.
        cross = (point-e1*radius*.15, point+e1*radius*.15,
                 point-e2*radius*.15, point+e2*radius*.15)
        node = coin.SoSeparator()
        pick = coin.SoPickStyle()
        pick.style = coin.SoPickStyle.UNPICKABLE
        node.addChild(pick)
        light = coin.SoLightModel()
        light.model = coin.SoLightModel.BASE_COLOR
        node.addChild(light)
        material = coin.SoBaseColor()
        material.rgb.setValue(.95, .25, .25)
        node.addChild(material)
        style = coin.SoDrawStyle()
        style.lineWidth = 2.
        node.addChild(style)
        coordinates = coin.SoCoordinate3()
        coordinates.point.setValues(0, len(corners)+len(cross),
                                    [tuple(p) for p in (*corners, *cross)])
        node.addChild(coordinates)
        lines = coin.SoLineSet()
        lines.numVertices.setValues(0, 3, (5, 2, 2))
        node.addChild(lines)
        return node

    def update(self, candidate):
        self.clear()
        try:
            marker = self._meeting_marker(candidate)
            for preview, member, shape in zip(self.previews, candidate.members, candidate.global_shapes):
                # The application result remains in the member's parent frame.
                # Scene-root branches require the exact candidate in world space.
                presentation = SimpleNamespace(Shape=shape, Placement=shape.Placement)
                preview.update(member, presentation)
            self.node = marker
            self.scene_graph.addChild(marker)
        except Exception:
            self.clear()
            raise

    def clear(self):
        for preview in self.previews:
            preview.clear()
        node, self.node = self.node, None
        if node is not None:
            try:
                if self.scene_graph.findChild(node) >= 0:
                    self.scene_graph.removeChild(node)
            except (RuntimeError, ReferenceError):
                pass

    remove = clear
