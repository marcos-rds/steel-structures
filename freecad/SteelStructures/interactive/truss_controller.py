"""Document boundary for the C1 panel; disposable lightweight preview and batch apply."""
from dataclasses import asdict
from time import perf_counter
import FreeCAD as App
import FreeCADGui as Gui
import Part
from ..truss import (apply_truss, default_config, config_from_object, prepare_batch, bound_children,
                     resynchronize_accepted_snapshots)
from ..trusses.models import EnvelopeDefinition
from ..trusses.envelope import paths
from ..trusses.realization import build_candidate
from ..trusses.serialization import decode_state, dumps
from ..truss_reference import resolve_linked_reference, selection_reference, source_geometry

_active_panel = None


class TrussScenePreview:
    """View-only Coin branch. It cannot dirty a document or enter its undo stack."""
    def __init__(self, scene_graph):
        from pivy import coin
        self.scene_graph = scene_graph
        self.node = coin.SoSeparator()
        self.shape = None
        self.colors = []
        scene_graph.addChild(self.node)

    def update(self, shapes, colors, compound):
        from pivy import coin
        candidate = coin.SoSeparator()
        style = coin.SoPickStyle()
        style.style = coin.SoPickStyle.UNPICKABLE
        candidate.addChild(style)
        for shape,color in zip(shapes, colors):
            component = coin.SoSeparator()
            material = coin.SoMaterial()
            material.diffuseColor.setValue(*color)
            material.transparency = .65
            material.setOverride(True)
            component.addChild(material)
            data = coin.SoInput()
            data.setBuffer(shape.writeInventor())
            geometry = coin.SoDB.readAll(data)
            if geometry is None:
                raise ValueError("Falha ao preparar representação 3D temporária.")
            component.addChild(geometry)
            candidate.addChild(component)
        self.node.removeAllChildren()
        self.node.addChild(candidate)
        self.shape, self.colors = compound, list(colors)

    def frame(self, view):
        """Frame only this preview branch while preserving camera orientation."""
        viewport = view.getViewer().getSoRenderManager().getViewportRegion()
        view.getCameraNode().viewAll(self.node, viewport, 1.1)

    def remove(self):
        if self.scene_graph.findChild(self.node) >= 0:
            self.scene_graph.removeChild(self.node)


class TrussController:
    def __init__(self, document, obj=None):
        self.document = document
        self.object = obj
        self.opening_warnings = []
        if obj is not None:
            try:
                resynchronize_accepted_snapshots(obj)
            except (ValueError, RuntimeError, ReferenceError) as exc:
                # Snapshot repair is useful after Undo/Redo, but it is not a
                # prerequisite for editing the truss definition. In particular,
                # a temporarily unresolved associative manual override belongs
                # to the generated child and must not prevent opening its owner.
                message = "Override manual preservado: " + str(exc)
                self.opening_warnings.append(message)
                App.Console.PrintWarning("Steel Structures: "+message+"\n")
        self._preview = None
        self._preview_signature = None
        self._initial_frame_pending = obj is None
        self._point_callbacks = []
        self._view = None
        self.timings = {}
        self.closed = False
        self.last_candidate = None

    def candidate(self, config):
        config = resolve_linked_reference(self.document, config, self.object)
        if self.object is not None:
            applied_config = decode_state(self.object.AppliedState)["candidate"]["config"]
            applied = build_candidate(applied_config)
        else:
            applied = self.last_candidate
        candidate = build_candidate(config, applied)
        self.last_candidate = candidate
        return candidate

    def preview(self, config):
        started = perf_counter()
        candidate = self.candidate(config)
        self.timings["pure_seconds"] = perf_counter()-started
        config = candidate.config
        definition = EnvelopeDefinition(config["envelope_type"], config["span"], config["height"], config["apex_position"])
        from ..trusses.connections import resolve_truss_connections
        resolutions, orphan_diagnostics, _canonical = resolve_truss_connections(
            candidate, (0., 0., 1.))
        connections = [dict(node_key=value.intent.node_key,
                            form=value.intent.form.value,
                            participants=[dict(run_key=p.run_key, role=p.role, end=p.end)
                                          for p in value.participants],
                            diagnostics=[d.message for d in value.diagnostics])
                       for value in resolutions]
        return dict(nodes=[asdict(n) for n in candidate.graph.nodes],
                    edges=[asdict(e) for e in candidate.graph.edges],
                    stations=[asdict(s) for s in candidate.stations.stations],
                    envelope=paths(definition), warnings=list(candidate.warnings),
                    effective=candidate.config["panelization_result"], topology_mode=candidate.config["topology_mode"],
                    left_panels=candidate.stations.left_panels, right_panels=candidate.stations.right_panels,
                    reference_base=config.get("reference_edge","") if config.get("reference_mode")=="DraftRectangle" else "",
                    connections=connections,
                    connection_diagnostics=[d.message for d in orphan_diagnostics])

    def preview3d(self, config, enabled=True):
        if not enabled:
            self.remove_preview()
            return
        if self.closed:
            return
        candidate = self.candidate(config)
        key = dumps(candidate)
        if key == self._preview_signature:
            return
        started = perf_counter()
        children = bound_children(self.object, decode_state(self.object.AppliedState)) if self.object else {}
        prepared = prepare_batch(candidate, children)
        # Disposable view branch, no document objects/transactions/recompute.
        shapes = []
        colors = []
        for item in candidate.items:
            result = prepared[item.key]
            shape = result.Shape.copy()
            shape.Placement = result.Placement
            shapes.append(shape)
            colors.append(tuple(item.spec.color))
        compound = Part.makeCompound(shapes)
        view = Gui.activeDocument().activeView()
        if self._preview is None:
            self._preview = TrussScenePreview(view.getSceneGraph())
        self._preview.update(shapes, colors, compound)
        if self._initial_frame_pending:
            self._initial_frame_pending = False
            try:
                self._preview.frame(view)
            except (AttributeError, RuntimeError) as exc:
                App.Console.PrintWarning(
                    "Steel Structures: nÃ£o foi possÃ­vel enquadrar a preview inicial: "
                    +str(exc)+"\n")
        self._preview_signature = key
        self.timings["preview_seconds"] = perf_counter()-started

    def remove_preview(self):
        if self._preview is not None:
            self._preview.remove()
            self._preview = None
        self._preview_signature = None

    def pick_points(self, callback, count=2):
        """Native Draft snapping, without replacing the truss task dialog."""
        self.cancel_picker()
        import WorkingPlane
        normal = list(WorkingPlane.get_working_plane().axis)
        view = Gui.activeDocument().activeView()
        self._view = view
        points = []

        def finish(start=None, end=None):
            self.cancel_picker()
            if count==3:
                callback(points if len(points)==3 else None)
            else:
                callback(start, end, normal)

        def move(event):
            if not self.closed:
                Gui.Snapper.snap(event["Position"], lastpoint=points[-1] if points else None, active=True)

        def click(event):
            if self.closed or event.get("State") != "DOWN" or event.get("Button") != "BUTTON1":
                return
            position = event["Position"]
            point = Gui.Snapper.snap(position, lastpoint=points[-1] if points else None, active=True)
            if point is None:
                return
            points.append(App.Vector(point))
            if len(points) == count:
                finish(points[0], points[1])

        def key(event):
            if event.get("Key") == "ESCAPE" and event.get("State") == "DOWN":
                finish()

        try:
            Gui.Snapper.show()
            for kind,handler in (("SoLocation2Event", move), ("SoMouseButtonEvent", click), ("SoKeyboardEvent", key)):
                self._point_callbacks.append((kind, view.addEventCallback(kind, handler)))
        except Exception:
            self.cancel_picker()
            raise

    def selected_reference(self):
        source,mode,edge=selection_reference(Gui.Selection.getSelectionEx())
        if source.Document!=self.document:
            raise ValueError("Selecione uma fonte no documento da treliça.")
        return dict(reference_mode=mode,reference_source=source.Name,reference_edge=edge,reference_linked=False)

    def reference_geometry(self, config):
        source=self.document.getObject(config.get("reference_source",""))
        if source is None: raise ValueError("Selecione uma fonte Draft válida.")
        import WorkingPlane
        up=list(WorkingPlane.get_working_plane().v)
        return source_geometry(source,config["reference_mode"],config.get("reference_edge",""),config["plane_normal"],up)

    def cancel_picker(self):
        if self._view is not None:
            for kind,token in self._point_callbacks:
                self._view.removeEventCallback(kind, token)
            self._point_callbacks = []
            self._view = None
            Gui.Snapper.off()

    def accept(self, config):
        candidate = self.candidate(config)
        # Remove preview outside the creation transaction so Undo/Redo never restores it.
        self.remove_preview()
        self.cancel_picker()
        started = perf_counter()
        self.object = apply_truss(self.document, candidate.config, self.object)
        self.timings["create_seconds"] = perf_counter()-started
        self.closed = True
        Gui.Selection.clearSelection()
        Gui.Selection.addSelection(self.object)
        return self.object

    def cancel(self):
        self.closed = True
        self.cancel_picker()
        self.remove_preview()


def open_truss_panel(document, obj=None):
    global _active_panel
    if _active_panel is not None:
        return _active_panel
    if Gui.Control.activeDialog():
        raise ValueError("Conclua ou cancele o painel atual antes de abrir Criar Treliça.")
    from .truss_task_panel import TrussTaskPanel
    controller = TrussController(document, obj)

    def closed():
        global _active_panel
        _active_panel = None
        Gui.Control.closeDialog()

    config = config_from_object(obj, resolve_reference=False) if obj is not None else default_config()
    if obj is None:
        import WorkingPlane
        plane = WorkingPlane.get_working_plane()
        config.update(start=list(plane.position),
                      end=list(plane.position.add(plane.u * config["span"])),
                      plane_normal=list(plane.axis))
        if Gui.Selection.getSelectionEx():
            try:
                config.update(controller.selected_reference())
                if config.get("reference_edge"):
                    config.update(controller.reference_geometry(config))
                else:
                    config["reference_defined"]=False
            except ValueError as exc:
                if config.get("reference_mode") in ("DraftLine","DraftRectangle"):
                    config["reference_defined"]=False
                App.Console.PrintWarning(str(exc)+"\n")
    try:
        panel = TrussTaskPanel(document, controller, config, on_close=closed,
                               point_picker=controller.pick_points)
        _active_panel = panel
        Gui.Control.showDialog(panel)
    except Exception:
        controller.cancel()
        _active_panel = None
        raise
    return panel


def close_truss_panel():
    if _active_panel is not None:
        _active_panel.reject()
