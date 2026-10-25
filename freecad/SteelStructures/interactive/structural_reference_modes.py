# SPDX-License-Identifier: LGPL-2.1-or-later
"""Viewport-owned presentation only; never writes ViewProvider properties.

Keep FreeCAD's ObjectGroup and its children intact. Native add/remove operations
continue to target that group. The wrapper belongs to one view, not to a VP.
"""
from dataclasses import dataclass

MODES = ("physical", "structural", "xray")
MODE_LABELS = ("Físico", "Estrutural", "Raio X")
MODE_COMMANDS = {
    "physical": "SteelStructures_DisplayPhysical",
    "structural": "SteelStructures_DisplayStructural",
    "xray": "SteelStructures_DisplayXRay",
}
MODE_TOOLTIPS = {
    "physical": "Preserva a aparência original e os toggles independentes de eixos e extremidades.",
    "structural": "Mostra somente referências nominais elegíveis em primeiro plano. Selecione objetos pela árvore.",
    "xray": "Torna translúcidos os objetos físicos visíveis, com referências nominais em primeiro plano e seleção física nativa.",
}
XRAY_TRANSPARENCY = .78


def _nodes(root):
    yield root
    if hasattr(root, "getNumChildren"):
        for index in range(root.getNumChildren()):
            yield from _nodes(root.getChild(index))


def _translucent_copy(source):
    """Copy native graphics, including switches/transforms/material arrays.

    copy() returns an unowned node in Pivy. Keep an explicit native reference
    until the presentation releases it, even when it is removed from a parent.
    """
    clone = source.copy()
    clone.ref()
    try:
        for node in _nodes(clone):
            field = node.getField("transparency")
            if field is not None:
                values = [max(XRAY_TRANSPARENCY, float(field[i]))
                          for i in range(field.getNum())] or [XRAY_TRANSPARENCY]
                field.setValues(0, len(values), values)
            # Mesh/custom Coin geometry may carry alpha in packed vertex colors.
            for name in ("orderedRGBA", "rgba"):
                colors = node.getField(name)
                if colors is not None:
                    alpha = round(255 * (1-XRAY_TRANSPARENCY))
                    values = [(int(colors[i]) & 0xFFFFFF00) | min(int(colors[i]) & 255, alpha)
                              for i in range(colors.getNum())]
                    if values:
                        colors.setValues(0, len(values), values)
        return clone
    except Exception:
        clone.unref()
        raise


@dataclass
class _Wrapper:
    original: object
    wrapper: object


class ViewportPresentation:
    """One reversible mode for one native FreeCAD 1.1.4 scene.

    Structural has no physical viewport picking; tree selection is preserved.
    X-Ray keeps invisible native geometry for picking and native selection feedback.
    Reference overlays and their render priority are managed by ReferenceLayer.
    """

    def __init__(self, view):
        self.view = view
        self.scene = view.getSceneGraph()
        self.scene.ref()
        self.mode = "physical"
        self.wrappers = []
        self.source = self.copy_branch = self.clone = None
        self.revision = None
        self.copy_updates = 0

    def _find(self, name):
        matches = [self.scene.getChild(i) for i in range(self.scene.getNumChildren())
                   if str(self.scene.getChild(i).getName()) == name]
        if len(matches) != 1:
            raise RuntimeError("Scenegraph sem ramo nativo único: " + name)
        return matches[0]

    def _wrap(self, original, wrapper):
        # Pin before replacement: the original can otherwise reach refcount 0.
        original.ref()
        wrapper.ref()
        try:
            wrapper.addChild(original)
            self.scene.replaceChild(original, wrapper)
        except Exception:
            original.unref()
            wrapper.unref()
            raise
        self.wrappers.append(_Wrapper(original, wrapper))

    def update(self, mode, revision=None):
        from pivy import coin
        if mode not in MODES:
            raise ValueError("Modo de visualização desconhecido.")
        if any(self.scene.findChild(lease.wrapper) < 0 for lease in self.wrappers):
            self.clear()
            raise RuntimeError("Outro recurso alterou a apresentação desta vista.")
        if mode != self.mode:
            self.clear()
            if mode == "physical":
                return
            source = self._find("ObjectGroup")
            front = self._find("GroupOnTop") if mode == "structural" else None
            try:
                if mode == "structural":
                    for node in (source, front):
                        switch = coin.SoSwitch()
                        switch.whichChild = coin.SO_SWITCH_NONE
                        self._wrap(node, switch)
                else:
                    wrapper = coin.SoSeparator()
                    native = coin.SoSeparator()
                    invisible = coin.SoDrawStyle()
                    invisible.style = coin.SoDrawStyle.INVISIBLE
                    invisible.setOverride(True)
                    native.addChild(invisible)
                    wrapper.addChild(native)
                    self.copy_branch = coin.SoSeparator()
                    pick = coin.SoPickStyle()
                    pick.style = coin.SoPickStyle.UNPICKABLE
                    pick.setOverride(True)
                    self.copy_branch.addChild(pick)
                    base = coin.SoMaterial()
                    base.transparency = XRAY_TRANSPARENCY
                    self.copy_branch.addChild(base)
                    wrapper.addChild(self.copy_branch)
                    source.ref()
                    wrapper.ref()
                    try:
                        native.addChild(source)
                        self.scene.replaceChild(source, wrapper)
                    except Exception:
                        source.unref()
                        wrapper.unref()
                        raise
                    self.wrappers.append(_Wrapper(source, wrapper))
                self.source = source
                self.mode = mode
            except Exception:
                self.clear()
                raise
        if mode == "xray":
            # The service supplies a revision from actual data/GUI properties.
            # Native node IDs also change on hover/selection; do not use those
            # as a rebuild trigger in a live workbench session.
            revision = self.source.getNodeId() if revision is None else revision
            if revision != self.revision:
                clone = None
                try:
                    clone = _translucent_copy(self.source)
                    self.copy_branch.addChild(clone)
                    self._drop_clone()
                    self.clone = clone
                    self.revision = revision
                    self.copy_updates += 1
                except Exception:
                    if clone is not None:
                        if self.copy_branch.findChild(clone) >= 0:
                            self.copy_branch.removeChild(clone)
                        clone.unref()
                    self.clear()
                    raise

    def _drop_clone(self):
        clone, self.clone = self.clone, None
        if clone is not None:
            try:
                self.copy_branch.removeChild(clone)
            finally:
                clone.unref()

    def clear(self):
        try:
            self._drop_clone()
        finally:
            for lease in reversed(self.wrappers):
                try:
                    # Restore only a branch still owned by this instance. Never
                    # rebuild a scene or replace another tool's branch.
                    if self.scene.findChild(lease.wrapper) >= 0:
                        self.scene.replaceChild(lease.wrapper, lease.original)
                    else:
                        # A third party can reparent our wrapper. Neutralize
                        # only its contents, without rewriting that party's tree.
                        lease.wrapper.removeAllChildren()
                        lease.wrapper.addChild(lease.original)
                        selector = lease.wrapper.getField("whichChild")
                        if selector is not None:
                            from pivy import coin
                            selector.setValue(coin.SO_SWITCH_ALL)
                except (ReferenceError, RuntimeError):
                    pass  # Native viewport may already be closed.
                finally:
                    lease.original.unref()
                    lease.wrapper.unref()
            self.wrappers.clear()
            self.source = self.copy_branch = None
            self.revision = None
            self.mode = "physical"

    def close(self):
        self.clear()
        scene, self.scene = self.scene, None
        self.view = None
        if scene is not None:
            scene.unref()
