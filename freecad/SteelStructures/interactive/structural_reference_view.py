# SPDX-License-Identifier: LGPL-2.1-or-later
"""Additive, unpickable nominal axes. All state belongs to the GUI session.

The resolver never executes a member. Observers only invalidate cached values;
Coin changes are coalesced on the Qt queue, never made during event traversal.
"""

from dataclasses import dataclass, field

import FreeCAD as App
from FreeCAD import Gui
from PySide import QtCore, QtWidgets

from ..structural_reference import AxisReadContext, axis_state_signature, resolve_member_axis
from .structural_reference_modes import MODES, MODE_LABELS, MODE_COMMANDS, MODE_TOOLTIPS, ViewportPresentation


COMMANDS = {"axes": "SteelStructures_ToggleMemberAxes",
            "endpoints": "SteelStructures_ToggleMemberEndpoints"}
REFERENCE_COLOR = (85/255, 200/255, 208/255)  # #55C8D0
OUTLINE_COLOR = (.035, .045, .055)
ENDPOINT_COLOR = (1.0, .28, .08)
ENDPOINT_OUTLINE_COLOR = (1.0, 1.0, 1.0)
AXIS_WIDTH = 2.5
AXIS_OUTLINE_WIDTH = 4.5
AXIS_PATTERN = 0x03FF  # Ten on/six off: 20/12 pixels at base scale.
AXIS_PATTERN_SCALE = 2
ENDPOINT_DIAMETERS = (15, 13, 9)  # dark guard, white contour, orange fill
_CIRCLE_MARKERS = {}
# Object properties that can affect nominal data, eligibility or its freshness.
_PRESENTATION_ONLY = frozenset(("Label", "Label2", "DisplayName", "Color"))


def _is_member_source(obj):
    # Asking for arbitrary attributes on native containers may resolve virtual
    # subobjects/shapes. Inspect their declared property names instead.
    return (obj.TypeId == "Part::FeaturePython"
            and {"StartPoint", "EndPoint"}.issubset(obj.PropertiesList))


def _member_visible(member):
    """Respect explicit object/container visibility without touching switches."""
    try:
        view = member.ViewObject
        if not view.Visibility:
            return False
        parent = member.getParentGeoFeatureGroup()
        seen = set()
        while parent is not None:
            if parent.Name in seen or not parent.ViewObject.Visibility:
                return False
            seen.add(parent.Name)
            parent = parent.getParentGeoFeatureGroup()
        return True
    except (AttributeError, ReferenceError, RuntimeError):
        return False


def _circle_bitmap(diameter):
    """ASCII character map for Pivy's addMarker overload (space = off)."""
    radius = (diameter - 1) / 2
    return "".join("#" if (x-radius)**2 + (y-radius)**2 <= radius**2 else " "
                   for y in range(diameter) for x in range(diameter))


def _circle_marker(coin, diameter):
    # Coin's public registry is shared with other tools. Append, never replace
    # a built-in or another tool's entry; reuse the tiny bitmaps across layers.
    if diameter not in _CIRCLE_MARKERS:
        index = coin.SoMarkerSet.getNumDefinedMarkers()
        bitmap = _circle_bitmap(diameter)
        # Pivy packs the character map MSB-first; do not pass packed C++ bytes.
        coin.SoMarkerSet.addMarker(index, coin.SbVec2s(diameter, diameter), bitmap, False, True)
        _CIRCLE_MARKERS[diameter] = index
    return _CIRCLE_MARKERS[diameter]


def _display_scale():
    try:
        return max(1.0, float(Gui.getMainWindow().devicePixelRatioF()))
    except (AttributeError, ReferenceError, RuntimeError):
        return 1.0


class ReferenceLayer:
    """One scene-owned batch. No native ViewProvider is masked or restyled."""

    def __init__(self, view):
        from pivy import coin
        self.view = view
        self.scene_graph = view.getSceneGraph()
        self.root = self.node = coin.SoSeparator()
        self.root.setName("SteelStructuresNominalReferences")
        self.geometry_updates = 0
        self.on_top = False
        self._points = None
        self._display_scale = None
        pick = coin.SoPickStyle()
        pick.style = coin.SoPickStyle.UNPICKABLE
        self.root.addChild(pick)
        light = coin.SoLightModel()
        light.model = coin.SoLightModel.BASE_COLOR
        self.root.addChild(light)
        # Physical mode uses normal LEQUAL depth; priority modes disable testing
        # only in this batch, inside an annotation's delayed render pass.
        depth = self.depth = coin.SoDepthBuffer()
        depth.test = True
        # "write" is also an SoNode method in Pivy; address the field directly.
        depth.getField("write").setValue(False)
        depth.function = coin.SoDepthBuffer.LEQUAL
        self.root.addChild(depth)
        self.coordinates = coin.SoCoordinate3()
        self.root.addChild(self.coordinates)
        self.line_switch = coin.SoSwitch()
        self.point_switch = coin.SoSwitch()
        self.root.addChild(self.line_switch)
        self.root.addChild(self.point_switch)
        self._lines = []
        self._markers = []
        self._line_styles = []
        for color in (OUTLINE_COLOR, REFERENCE_COLOR):
            branch = coin.SoSeparator()
            rgb = coin.SoBaseColor()
            rgb.rgb.setValue(*color)
            branch.addChild(rgb)
            style = coin.SoDrawStyle()
            style.linePattern = AXIS_PATTERN
            self._line_styles.append(style)
            branch.addChild(style)
            line = coin.SoLineSet()
            branch.addChild(line)
            self._lines.append(line)
            self.line_switch.addChild(branch)
        for color in (OUTLINE_COLOR, ENDPOINT_OUTLINE_COLOR, ENDPOINT_COLOR):
            branch = coin.SoSeparator()
            rgb = coin.SoBaseColor()
            rgb.rgb.setValue(*color)
            branch.addChild(rgb)
            markers = coin.SoMarkerSet()
            branch.addChild(markers)
            self._markers.append(markers)
            self.point_switch.addChild(branch)
        self.line_switch.whichChild = coin.SO_SWITCH_NONE
        self.point_switch.whichChild = coin.SO_SWITCH_NONE
        self.refresh_style()
        self._annotation = coin.SoAnnotation()
        self._annotation.setName("SteelStructuresNominalReferencesOnTop")
        # Keep both nodes alive across replacement/removal of their parents.
        self._annotation.ref()
        self.root.ref()
        try:
            self.scene_graph.addChild(self.root)
            self.presentation = ViewportPresentation(view)
        except Exception:
            try:
                if self.scene_graph.findChild(self.root) >= 0:
                    self.scene_graph.removeChild(self.root)
            finally:
                self._annotation.unref()
                self.root.unref()
            raise

    def set_on_top(self, enabled):
        """Change only the attachment/pass; reuse the same geometry batch.

        Annotation delays rendering until after transparent/native geometry.
        Merely disabling depth in the normal pass would still permit tinting.
        """
        enabled = bool(enabled)
        if enabled == self.on_top:
            return
        if self.scene_graph.findChild(self.node) < 0:
            raise RuntimeError("Ramo das referências ausente da vista.")
        if enabled:
            self._annotation.addChild(self.root)
            self.scene_graph.replaceChild(self.root, self._annotation)
            self.node = self._annotation
        else:
            self.scene_graph.replaceChild(self._annotation, self.root)
            self._annotation.removeChild(self.root)
            self.node = self.root
        self.depth.test = not enabled
        self.on_top = enabled

    def refresh_style(self):
        """Only screen style changes with DPI; never resolve member geometry."""
        from pivy import coin
        scale = _display_scale()
        if scale == self._display_scale:
            return
        self._display_scale = scale
        for style, width in zip(self._line_styles, (AXIS_OUTLINE_WIDTH, AXIS_WIDTH)):
            style.lineWidth = width * scale
            style.linePatternScaleFactor = max(1, round(AXIS_PATTERN_SCALE * scale))
        for markers, logical_diameter in zip(self._markers, ENDPOINT_DIAMETERS):
            diameter = int(round(logical_diameter * scale)) | 1
            # A single index repeats for every coordinate in SoMarkerSet.
            markers.markerIndex.setValue(_circle_marker(coin, diameter))

    def update(self, axes, show_axes, show_endpoints):
        from pivy import coin
        points = tuple(point for axis in axes for point in (axis.start, axis.end))
        if points != self._points:
            self.coordinates.point.setValues(0, len(points), points)
            # Shrinking the batch must discard the old tail as well.
            self.coordinates.point.setNum(len(points))
            for line in self._lines:
                line.numVertices.setValues(0, len(axes), [2] * len(axes))
                line.numVertices.setNum(len(axes))
            for markers in self._markers:
                markers.numPoints = len(points)
            self._points = points
            self.geometry_updates += 1
        self.line_switch.whichChild = coin.SO_SWITCH_ALL if show_axes else coin.SO_SWITCH_NONE
        self.point_switch.whichChild = coin.SO_SWITCH_ALL if show_endpoints else coin.SO_SWITCH_NONE

    def clear(self):
        try:
            # Detach while the presentation still pins the native scene graph.
            self._clear_references()
        finally:
            self.presentation.close()

    def _clear_references(self):
        root, self.root = self.root, None
        node, self.node = self.node, None
        annotation, self._annotation = self._annotation, None
        try:
            if node is not None and self.scene_graph.findChild(node) >= 0:
                self.scene_graph.removeChild(node)
        except (ReferenceError, RuntimeError):
            pass  # The native view can already have been destroyed.
        finally:
            if annotation is not None:
                annotation.removeAllChildren()
                annotation.unref()
            if root is not None:
                # Also neutralize our batch if a third party reparented it.
                root.removeAllChildren()
                root.unref()
        self.on_top = False
        self.depth = None
        self.view = self.scene_graph = None


@dataclass
class _DocumentSession:
    document: object
    show_axes: bool = False
    show_endpoints: bool = False
    mode: str = "physical"
    physical_flags: tuple = (False, False)
    preset_flags: tuple = (True, True)
    axes: dict = field(default_factory=dict)
    rejected: dict = field(default_factory=dict)
    layers: list = field(default_factory=list)
    dirty: set = field(default_factory=set)
    full: bool = True
    presentation_dirty: bool = True
    geometry_reads: int = 0
    trusted: dict = field(default_factory=dict)
    replay: bool = False
    diagnostic_summary: tuple = ()
    graph_revision: int = 0

    def clear(self):
        for layer in self.layers:
            layer.clear()
        self.layers.clear()
        self.axes.clear()
        self.rejected.clear()
        self.trusted.clear()


class _GuiObserver:
    def __init__(self, owner):
        self.owner = owner

    def slotChangedObject(self, view, prop):
        # Native material/display changes must reach the view-copy cache too.
        try:
            obj = view.Object
        except Exception:
            return  # Native providers can emit a last event during destruction.
        self.owner._presentation_changed(obj)

    def slotDeletedDocument(self, document):
        # GUI's signalDeleteDocument precedes destruction of views and VPs.
        # Release copied native nodes while their document metadata is alive.
        self.owner._gui_document_closing(document)


class StructuralReferenceService:
    """Session flags per live document, cached axes and one layer per 3D view."""

    def __init__(self):
        self._active = False
        self._sessions = {}
        self._observing = False
        self._gui_observer = _GuiObserver(self)
        self._flush_timer = self._view_timer = None
        self._mdi = None
        self._flushing = False

    def activate(self):
        self._active = True
        self.sync_actions()

    def deactivate(self):
        self._active = False
        self._stop_watchers()
        for session in self._sessions.values():
            session.clear()
        self._sessions.clear()
        self.sync_actions()

    def state(self, document=None):
        document = document if document is not None else App.ActiveDocument
        if document is None:
            return False, False
        session = self._sessions.get(document.Name)
        if session is None or session.document is not document:
            return False, False
        return session.show_axes, session.show_endpoints

    def toggle(self, kind, checked=None):
        if kind not in COMMANDS:
            raise ValueError("Camada estrutural desconhecida.")
        document = App.ActiveDocument
        if not self._active or document is None:
            return
        session = self._sessions.get(document.Name)
        if session is None or session.document is not document:
            if session is not None:
                session.clear()
            session = _DocumentSession(document)
            self._sessions[document.Name] = session
        prop = "show_axes" if kind == "axes" else "show_endpoints"
        setattr(session, prop, not getattr(session, prop) if checked is None else bool(checked))
        if session.mode == "physical":
            session.physical_flags = (session.show_axes, session.show_endpoints)
        else:
            session.preset_flags = (session.show_axes, session.show_endpoints)
        session.presentation_dirty = True
        if not (session.show_axes or session.show_endpoints) and session.mode == "physical":
            session.clear()
            del self._sessions[document.Name]
        if self._sessions:
            self._start_watchers()
            self._schedule()
        else:
            self._stop_watchers()
        self.sync_actions()

    def mode(self, document=None):
        document = document if document is not None else App.ActiveDocument
        session = self._sessions.get(document.Name) if document is not None else None
        return session.mode if session is not None and session.document is document else "physical"

    def set_mode(self, mode):
        if mode not in MODES:
            raise ValueError("Modo de visualização desconhecido.")
        document = App.ActiveDocument
        if not self._active or document is None or mode == self.mode(document):
            return
        session = self._sessions.get(document.Name)
        if session is None or session.document is not document:
            if session is not None:
                session.clear()
            session = _DocumentSession(document)
            self._sessions[document.Name] = session
        if session.mode == "physical":
            session.physical_flags = (session.show_axes, session.show_endpoints)
            session.preset_flags = (True, True)
        else:
            session.preset_flags = (session.show_axes, session.show_endpoints)
        session.mode = mode
        session.show_axes, session.show_endpoints = (
            session.physical_flags if mode == "physical" else session.preset_flags)
        session.presentation_dirty = True
        if mode == "physical" and not any(session.physical_flags):
            session.clear()
            del self._sessions[document.Name]
        if self._sessions:
            self._start_watchers()
            self._schedule()
        else:
            self._stop_watchers()
        self.sync_actions()

    def sync_actions(self):
        values = self.state() if self._active else (False, False)
        for command, value in zip(COMMANDS.values(), values):
            try:
                for action in Gui.Command.get(command).getAction():
                    previous = action.blockSignals(True)
                    try:
                        action.setCheckable(True)
                        action.setChecked(value)
                    finally:
                        action.blockSignals(previous)
            except (AttributeError, ReferenceError, RuntimeError):
                pass  # Workbench registration/actions may not exist yet.
        doc = App.ActiveDocument
        available = self._active and doc is not None and bool(self._views(doc))
        current = self._sessions.get(doc.Name) if doc is not None else None
        paused = (self.mode() != "physical" and current is not None and bool(current.layers)
                  and all(layer.presentation.mode == "physical" for layer in current.layers))
        for (mode, command), label in zip(MODE_COMMANDS.items(), MODE_LABELS):
            try:
                for action in Gui.Command.get(command).getAction():
                    previous = action.blockSignals(True)
                    try:
                        action.setCheckable(True)
                        action.setChecked(bool(available and self.mode() == mode))
                        action.setText(label)
                        action.setToolTip(MODE_TOOLTIPS[mode] + (
                            " Modo pausado durante tarefa ou edição."
                            if paused and self.mode() == mode else ""))
                    finally:
                        action.blockSignals(previous)
            except (AttributeError, ReferenceError, RuntimeError):
                pass

    def _start_watchers(self):
        if self._observing:
            return
        App.addDocumentObserver(self)
        try:
            Gui.addDocumentObserver(self._gui_observer)
            self._observing = True
            self._flush_timer = QtCore.QTimer()
            self._flush_timer.setSingleShot(True)
            self._flush_timer.timeout.connect(self._flush)
            self._view_timer = QtCore.QTimer()
            self._view_timer.setInterval(500)
            self._view_timer.timeout.connect(self._reconcile_views)
            self._view_timer.start()
            self._mdi = Gui.getMainWindow().findChild(QtWidgets.QMdiArea)
            if self._mdi is not None:
                self._mdi.subWindowActivated.connect(self._view_changed)
        except Exception:
            # Roll back partially attached resources before propagating errors.
            self._observing = True
            self._stop_watchers()
            raise

    def _stop_watchers(self):
        if self._observing:
            App.removeDocumentObserver(self)
            Gui.removeDocumentObserver(self._gui_observer)
            self._observing = False
        if self._mdi is not None:
            try:
                self._mdi.subWindowActivated.disconnect(self._view_changed)
            except (ReferenceError, RuntimeError):
                pass
        self._mdi = None
        for name in ("_flush_timer", "_view_timer"):
            timer = getattr(self, name)
            setattr(self, name, None)
            if timer is not None:
                timer.stop()
                timer.timeout.disconnect()
                timer.deleteLater()

    def _schedule(self):
        if self._active and self._flush_timer is not None:
            if not self._flush_timer.isActive():
                self._flush_timer.start(0)

    def _view_changed(self, *_args):
        self._schedule()

    def _session_for(self, obj):
        try:
            doc = obj.Document
            session = self._sessions.get(doc.Name)
            return session if session is not None and session.document is doc else None
        except (AttributeError, ReferenceError, RuntimeError):
            return None

    def _presentation_changed(self, obj):
        session = self._session_for(obj)
        if session is not None:
            session.presentation_dirty = True
            session.graph_revision += 1
            self._schedule()

    def _gui_document_closing(self, document):
        session = self._session_for(document)
        if session is not None:
            session.clear()
            self._sessions.pop(session.document.Name, None)
            self._schedule()

    def slotChangedObject(self, obj, prop):
        session = self._session_for(obj)
        if session is not None and session.mode != "physical":
            session.graph_revision += 1
            self._schedule()  # Includes native solids from other workbenches.
        if session is None or prop in _PRESENTATION_ONLY:
            return
        if prop == "Visibility":
            self._presentation_changed(obj)  # Native data/view visibility mirror.
            return
        try:
            if not getattr(session.document, "Transacting", False):
                session.replay = False
            if _is_member_source(obj):
                session.dirty.add(obj.Name)
            elif prop in ("Placement", "Group", "AppliedState", "GenerationState",
                          "NeedsRegeneration", "GeneratedMembers"):
                # Parent/owner updates can invalidate children without touching
                # them. A real hierarchy change warrants a fresh document scan.
                session.full = True
            else:
                return
            self._schedule()
        except (ReferenceError, RuntimeError):
            pass

    def slotCreatedObject(self, obj):
        session = self._session_for(obj)
        if session is not None:
            session.dirty.add(obj.Name)
            session.graph_revision += 1
            self._schedule()

    def slotDeletedObject(self, obj):
        self.slotCreatedObject(obj)  # Flush readquires by Name, never keeps obj.

    def slotRecomputedObject(self, obj):
        self.slotChangedObject(obj, "Shape")

    def slotRecomputedDocument(self, document):
        session = self._sessions.get(document.Name)
        if session is not None and session.document is document:
            session.graph_revision += 1
            # Recompute can clear Touched without emitting a value change.
            session.dirty.update(session.rejected)
            self._schedule()

    def _history_changed(self, document):
        session = self._sessions.get(document.Name)
        if session is not None and session.document is document:
            session.graph_revision += 1
            session.full = True
            session.replay = True
            self._schedule()

    slotUndoDocument = slotRedoDocument = _history_changed

    def slotFinishRestoreDocument(self, document):
        session = self._sessions.get(document.Name)
        if session is not None and session.document is document:
            session.trusted.clear()
            session.replay = False
            session.full = True
            self._schedule()

    def slotActivateDocument(self, _document):
        self._schedule()

    def slotDeletedDocument(self, document):
        # Drop later, after FreeCAD has finished closing native view resources.
        self._schedule()

    def _views(self, document):
        try:
            return list(Gui.getDocument(document.Name).mdiViewsOfType("Gui::View3DInventor"))
        except (ReferenceError, RuntimeError, NameError):
            return []

    def _update_layers(self, session, force=False):
        views = self._views(session.document)
        for layer in list(session.layers):
            if layer.view not in views:
                layer.clear()
                session.layers.remove(layer)
        for view in views:
            if not any(layer.view == view for layer in session.layers):
                session.layers.append(ReferenceLayer(view))
                force = True
        for layer in session.layers:
            layer.refresh_style()
            target = session.mode if session.document is App.ActiveDocument else "physical"
            try:
                dialog = Gui.Control.activeDialog()
                editing = Gui.getDocument(session.document.Name).getInEdit()
                if dialog or editing or getattr(App, "activeDraftCommand", None) is not None:
                    target = "physical"
                layer.presentation.update(target, revision=session.graph_revision)
            except Exception as exc:
                # Never fall back to modifying shared ViewObject properties.
                for owned in session.layers:
                    owned.presentation.clear()
                session.mode = "physical"
                session.show_axes, session.show_endpoints = session.physical_flags
                force = True
                App.Console.PrintWarning("Modo estrutural indisponível; Físico restaurado: " + str(exc) + "\n")
        # Use the effective presentation, including pause/inactive docs/fallback.
        # Priority changes do not require resolving or rebuilding any axes.
        for layer in session.layers:
            layer.set_on_top(layer.presentation.mode in ("structural", "xray"))
        if not force:
            return
        axes = tuple(axis for name, axis in sorted(session.axes.items())
                     if _member_visible(session.document.getObject(name)))
        for layer in session.layers:
            layer.update(axes, session.show_axes, session.show_endpoints)

    def _reconcile_views(self):
        """View-only fallback also detects closing an inactive MDI view.

        No object enumeration, axis resolution or camera/mouse callback occurs
        on this timer. All actual geometry work is driven by document events.
        """
        if not self._active:
            return
        self._schedule()

    def _flush(self):
        if not self._active or self._flushing:
            return
        self._flushing = True
        try:
            documents = App.listDocuments()
            for name, session in list(self._sessions.items()):
                if documents.get(name) is not session.document:
                    session.clear()
                    del self._sessions[name]
                    continue
                changed = session.presentation_dirty
                if session.full:
                    names = {obj.Name for obj in session.document.Objects
                             if _is_member_source(obj)}
                    for removed in set(session.axes).union(session.rejected, session.trusted) - names:
                        session.axes.pop(removed, None)
                        session.rejected.pop(removed, None)
                        if session.document.getObject(removed) is not None:
                            session.trusted.pop(removed, None)
                    session.dirty.update(names)
                    session.full = False
                    changed = True
                names, session.dirty = session.dirty, set()
                # No copying or traversal of replay history on the view timer.
                # A batch never survives return to the event loop. Touched replay
                # is accepted only for previously validated exact values.
                context = (AxisReadContext(trusted_replay=session.trusted if session.replay else None)
                           if names else None)
                for member_name in names:
                    obj = session.document.getObject(member_name)
                    previous = session.axes.get(member_name)
                    if obj is None or not _is_member_source(obj):
                        # A deleted Name can already belong to a foreign object
                        # when the queued batch runs. Never retain its old axis.
                        session.axes.pop(member_name, None)
                        session.rejected.pop(member_name, None)
                        # Missing members may return Touched on Undo deletion:
                        # retain exact validated replay values for that case.
                        # A foreign replacement must never inherit this evidence.
                        if obj is not None:
                            session.trusted.pop(member_name, None)
                    else:
                        result = resolve_member_axis(obj, context=context)
                        session.geometry_reads += 1
                        if result.axis is not None:
                            if result.axis != previous:
                                session.axes[member_name] = result.axis
                            session.rejected.pop(member_name, None)
                            if not set(getattr(obj, "State", ())).intersection(("Touched", "Recompute", "Invalid")):
                                fingerprint = axis_state_signature(obj, context=context)
                                if fingerprint is not None:
                                    values = session.trusted.setdefault(member_name, [])
                                    if fingerprint not in values:
                                        values.append(fingerprint)
                                        del values[:-32]  # Bounded, session-only replay evidence.
                        else:
                            session.axes.pop(member_name, None)
                            session.rejected[member_name] = result.reason
                    changed |= previous != session.axes.get(member_name)
                self._update_layers(session, changed)
                if session.mode == "physical" and not (session.show_axes or session.show_endpoints):
                    session.clear()
                    del self._sessions[name]
                    continue
                session.presentation_dirty = False
                summary = (len(session.rejected), tuple(sorted(set(session.rejected.values()))))
                if session.rejected and summary != session.diagnostic_summary:
                    App.Console.PrintWarning(
                        "Referências estruturais: " + str(len(session.rejected))
                        + " membro(s) omitido(s). " + " ".join(summary[1]) + "\n")
                session.diagnostic_summary = summary
            self.sync_actions()
            if not self._sessions:
                self._stop_watchers()
        except (ReferenceError, RuntimeError) as exc:
            # A native view can disappear between enumeration and scene update.
            # Discard our resources, retaining flags for the next live view.
            for session in self._sessions.values():
                for layer in session.layers:
                    layer.clear()
                session.layers.clear()
            App.Console.PrintWarning("Eixos estruturais: apresentação indisponível: " + str(exc) + "\n")
        finally:
            self._flushing = False

    def refresh_now(self):
        """Drain pending presentation work, useful for native gates; no recompute."""
        if self._flush_timer is not None:
            self._flush_timer.stop()
        self._flush()


service = StructuralReferenceService()
activate = service.activate
deactivate = service.deactivate
toggle = service.toggle
state = service.state
set_mode = service.set_mode
mode = service.mode
refresh_now = service.refresh_now
