# SPDX-License-Identifier: LGPL-2.1-or-later
"""Exact, view-only adjustment preview. No document objects or visibility edits."""
import FreeCAD as App


class MemberAdjustmentPreview:
    def __init__(self, scene_graph):
        self.scene_graph = scene_graph
        self.node = None
        self.shape = None
        self._hidden_switch = None
        self._previous_child = None
        self._hidden_view = None
        self._previous_visibility = None
        self._previous_display_mode = None

    def update(self, member, result):
        from pivy import coin
        # Prepare fully before replacing the visible branch or hiding the source.
        shape = result.Shape.copy()
        shape.Placement = App.Placement(result.Placement)
        data = coin.SoInput()
        data.setBuffer(shape.writeInventor())
        geometry = coin.SoDB.readAll(data)
        if geometry is None:
            raise ValueError("Não foi possível desenhar a geometria candidata.")
        node = coin.SoSeparator()
        pick = coin.SoPickStyle()
        pick.style = coin.SoPickStyle.UNPICKABLE
        node.addChild(pick)
        material = coin.SoMaterial()
        material.diffuseColor.setValue(.12, .62, .82)
        material.transparency = .15
        material.setOverride(True)
        node.addChild(material)
        node.addChild(geometry)
        self.clear()
        try:
            self.scene_graph.addChild(node)
            self.node, self.shape = node, shape
            view = member.ViewObject
            switch = view.SwitchNode
            self._previous_visibility = bool(view.Visibility)
            self._previous_display_mode = str(view.DisplayMode)
            self._hidden_view = view
            self._previous_child = int(switch.whichChild.getValue())
            self._hidden_switch = switch
            switch.whichChild.setValue(coin.SO_SWITCH_NONE)
        except Exception:
            self.clear()
            raise

    def clear(self):
        switch, self._hidden_switch = self._hidden_switch, None
        previous, self._previous_child = self._previous_child, None
        view, self._hidden_view = self._hidden_view, None
        visibility, self._previous_visibility = self._previous_visibility, None
        mode, self._previous_display_mode = self._previous_display_mode, None
        try:
            # Respect a visibility change explicitly made by the user while
            # the source was masked. Never write the persistent property.
            if (switch is not None and bool(view.Visibility) == visibility
                    and str(view.DisplayMode) == mode):
                switch.whichChild.setValue(previous)
        except (RuntimeError, ReferenceError):
            pass  # View/document may already have closed.
        node, self.node = self.node, None
        self.shape = None
        if node is not None:
            try:
                if self.scene_graph.findChild(node) >= 0:
                    self.scene_graph.removeChild(node)
            except (RuntimeError, ReferenceError):
                pass

    remove = clear
