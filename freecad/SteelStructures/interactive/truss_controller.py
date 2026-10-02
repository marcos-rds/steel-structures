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
from ..trusses.realization import build_candidate, reference_frame, transform_point
from ..trusses.gussets import preliminary_gusset_outlines
from ..trusses.gusset_freecad import build_gusset_shape
from ..trusses.serialization import decode_state, dumps
from ..truss_reference import resolve_linked_reference, selection_reference, source_geometry

_active_panel = None


def _candidate_center(candidate):
    low, high = (getattr(candidate, "plate_low", None),
                 getattr(candidate, "plate_high", None))
    return 0. if low is None or high is None else (low+high)/2.


def _deduplicated_transverse_candidates(candidates):
    """Keep one UI entry per physically equivalent resolved candidate."""
    priorities = {"AssemblyGap": 0, "OpenRecess": 1,
                  "SurfaceBand": 2, "OuterExposed": 3}
    grouped = {}
    for candidate in candidates:
        kind = candidate.accessibility.value
        if kind not in priorities:
            continue
        low, high = (getattr(candidate, "plate_low", None),
                     getattr(candidate, "plate_high", None))
        window = getattr(candidate, "contact_window", None)
        if low is None or high is None:
            signature = ("legacy", candidate.stable_key)
        else:
            signature = (
                getattr(candidate, "governing_participant_key", ""),
                round(low, 6), round(high, 6),
                getattr(candidate, "contact_direction", 0),
                (None if getattr(candidate, "contact_band", None) is None
                 else round(candidate.contact_band, 6)),
                (None if getattr(candidate, "outline_band", None) is None
                 else round(candidate.outline_band, 6)),
                tuple((None if a is None else round(a, 6),
                       None if b is None else round(b, 6))
                      for a, b in getattr(window, "intervals", ())))
        current = grouped.get(signature)
        if (current is None
                or (priorities[kind], candidate.stable_key)
                < (priorities[current.accessibility.value], current.stable_key)):
            grouped[signature] = candidate
    return tuple(grouped.values())


def _transverse_placement_regions(candidates):
    """Project physical candidates into contextual region/position choices."""
    raw_candidates = tuple(candidates)
    candidates = _deduplicated_transverse_candidates(raw_candidates)
    closed = lambda value: any("seção fechada" in message
                               for message in getattr(value, "diagnostics", ()))
    by_kind_slot = {}
    for candidate in raw_candidates:
        by_kind_slot.setdefault(
            (candidate.accessibility.value, getattr(candidate, "slot_id", "")),
            []).append(candidate)
    surface_slots = {}
    for candidate in raw_candidates:
        if (candidate.accessibility.value == "SurfaceBand"
                and not closed(candidate)):
            surface_slots.setdefault(getattr(candidate, "slot_id", ""), []).append(candidate)
    has_between = any(value.accessibility.value == "AssemblyGap"
                      for value in raw_candidates)
    stiffener_slots = ()
    if len(surface_slots) == 2 and not has_between:
        stiffener_slots = tuple(sorted(surface_slots, key=lambda slot: (
            sum(_candidate_center(value) for value in surface_slots[slot])
            /len(surface_slots[slot]), slot)))
    slot_centers = {slot: sum(_candidate_center(value)
                              for value in surface_slots[slot])/len(surface_slots[slot])
                    for slot in stiffener_slots}
    section_middle = ((min(slot_centers.values())+max(slot_centers.values()))/2.
                      if slot_centers else 0.)

    component_bands = ()
    if has_between and len(surface_slots) == 2:
        component_bands = tuple(sorted((
            (min(value.plate_low for value in values),
             max(value.plate_high for value in values), slot)
            for slot, values in surface_slots.items()),
            key=lambda value: ((value[0]+value[1])/2., value[2])))

    open_slots = {slot: values for (kind, slot), values in by_kind_slot.items()
                  if kind == "OpenRecess"}
    angle_centers = tuple(_candidate_center(value) for values in open_slots.values()
                          for value in values
                          if "|" not in getattr(value, "slot_id", "").split(
                              "OpenRecess:", 1)[-1])
    primary_open_slot = None
    if not has_between and open_slots:
        primary_open_slot = min(open_slots, key=lambda slot: (
            max(abs(_candidate_center(value)) for value in open_slots[slot]),
            slot))

    regions = {}
    def add(region_id, region_label, candidate, position_label, position_rank):
        regions.setdefault(region_id, [region_label, []])[1].append(
            (position_rank, _candidate_center(candidate), candidate.stable_key,
             position_label, candidate))

    standard = {
        "OuterExposed": ("external", "Externa",
                         {"NearA": "Lado A", "Center": "Central",
                          "NearB": "Lado B"}),
        "AssemblyGap": ("between", "Entre componentes",
                        {"NearA": "Junto ao componente A", "Center": "Central",
                         "NearB": "Junto ao componente B"}),
    }
    placement_rank = {"NearA": 0, "Center": 1, "NearB": 2}
    internal_labels = {"NearA": "Junto à aba A", "Center": "Central",
                       "NearB": "Junto à aba B"}
    stiffener_for_slot = {slot: ("stiffener_a", "Enrijecedor A")
                          if index == 0 else ("stiffener_b", "Enrijecedor B")
                          for index, slot in enumerate(stiffener_slots)}
    if len(open_slots) == 1:
        # One open recess bounded by two face bands describes its flanges,
        # not the separate return lips of a lipped section.
        stiffener_for_slot = {
            slot: (region_id, "Apoio na aba "+("A" if index == 0 else "B"))
            for index, (slot, (region_id, _label)) in enumerate(stiffener_for_slot.items())}

    def component_band(candidate):
        overlaps = []
        for index, (low, high, _slot) in enumerate(component_bands):
            overlap = min(candidate.plate_high, high)-max(candidate.plate_low, low)
            if overlap > 1e-7:
                overlaps.append((overlap, index))
        return max(overlaps)[1] if overlaps else None

    def add_component(candidate, index, prefix="component_internal"):
        suffix = "a" if index == 0 else "b"
        region_label = (("Cantoneira " if prefix == "angle"
                         else "Interna — componente ")+suffix.upper())
        center = _candidate_center(candidate)
        if prefix == "angle":
            same_side = [value for value in angle_centers
                         if (value < 0.) == (center < 0.)]
            external = abs(center) >= max(map(abs, same_side))-1e-7
            add(prefix+"_"+suffix, region_label, candidate,
                "Face externa" if external else "Face interna",
                1 if external else 0)
            return
        component_center = ((component_bands[index][0]+component_bands[index][1])/2.
                            if component_bands else center)
        assembly_center = (sum((low+high)/2. for low, high, _slot in component_bands)
                           /len(component_bands) if component_bands else 0.)
        delta = center-component_center
        outward = component_center-assembly_center
        # A bounded free cell can span the assembly gap and an inward-facing
        # channel recess.  Its near placement is physically inside the
        # component when governed by that inner face; distance from the
        # assembly axis alone would mislabel it as the external face.
        inner_surface = (candidate.accessibility.value == "AssemblyGap"
                         and ":Inner:" in candidate.surface_semantic_id)
        if inner_surface:
            position, rank = "Face interna", 0
        elif abs(delta) <= 1e-7:
            position, rank = "Central", 1
        elif delta*outward > 0.:
            position, rank = "Face externa", 2
        else:
            position, rank = "Face interna", 0
        if candidate.accessibility.value == "SurfaceBand":
            position = {"Face interna": "Apoio interno",
                        "Central": "Apoio central",
                        "Face externa": "Apoio externo"}[position]
        add(prefix+"_"+suffix, region_label, candidate, position, rank)

    for candidate in candidates:
        kind = candidate.accessibility.value
        placement = (candidate.placement.value
                     if candidate.placement is not None else "Center")
        if kind in standard:
            if kind == "AssemblyGap":
                component = component_band(candidate)
                if component is not None:
                    add_component(candidate, component)
                    continue
            region_id, region_label, labels = standard[kind]
            add(region_id, region_label, candidate, labels[placement],
                placement_rank[placement])
            continue
        if kind == "SurfaceBand" and closed(candidate):
            labels = {"NearA": "Lado A", "Center": "Central", "NearB": "Lado B"}
            add("supported", "Apoiada no banzo", candidate, labels[placement],
                placement_rank[placement])
            continue
        if kind == "SurfaceBand" and candidate.slot_id in stiffener_for_slot:
            region_id, region_label = stiffener_for_slot[candidate.slot_id]
            band_center = slot_centers[candidate.slot_id]
            delta = _candidate_center(candidate)-band_center
            outward = band_center-section_middle
            if abs(delta) <= 1e-7:
                label, rank = "Apoio central", 2
            elif delta*outward > 0.:
                label, rank = "Apoio — lado externo", 3
            else:
                label, rank = "Apoio — lado interno", 1
            add(region_id, region_label, candidate, label, rank)
            continue
        if kind == "SurfaceBand" and component_bands:
            component = component_band(candidate)
            if component is not None:
                add_component(candidate, component)
                continue
        if kind == "OpenRecess" and has_between:
            # A one-face pocket is characteristic of an angle leg.  A
            # bounded multi-face recess belongs to its assembly component.
            tail = candidate.slot_id.split("OpenRecess:", 1)[-1]
            single_face = "|" not in tail
            index = 0 if _candidate_center(candidate) < 0. else 1
            add_component(candidate, index,
                          "angle" if single_face else "component_internal")
            continue
        if kind == "OpenRecess" and stiffener_slots and placement != "Center":
            if candidate.slot_id == primary_open_slot:
                add("internal", "Interna", candidate,
                    ({"NearA": "Lado A", "NearB": "Lado B"}
                     if len(open_slots) > 1 else internal_labels)[placement],
                    placement_rank[placement])
                continue
            slot = min(stiffener_slots, key=lambda value: abs(
                _candidate_center(candidate)-slot_centers[value]))
            region_id, region_label = stiffener_for_slot[slot]
            outward = slot_centers[slot]-section_middle
            is_external = ((_candidate_center(candidate)-slot_centers[slot])
                           *outward > 0.)
            add(region_id, region_label, candidate,
                "Face externa" if is_external else "Face interna",
                4 if is_external else 0)
            continue
        if kind in ("OpenRecess", "SurfaceBand"):
            labels = ({"NearA": "Lado A", "Center": "Central", "NearB": "Lado B"}
                      if kind == "SurfaceBand" or stiffener_slots
                      else internal_labels)
            add("internal", "Interna", candidate, labels[placement],
                placement_rank[placement])

    # Assemblies may expose two separate internal recesses with repeated
    # NearA/NearB semantics.  Name them by their ordered local position rather
    # than inventing numbered ranges or relying on global left/right.
    internal = regions.get("internal")
    if internal is not None:
        labels = [value[3] for value in internal[1]]
        if len(set(labels)) != len(labels):
            ordered = sorted(internal[1], key=lambda value: (value[1], value[2]))
            middle = (ordered[0][1]+ordered[-1][1])/2.
            sides = {False: [], True: []}
            for value in ordered:
                sides[value[1] > middle].append(value)
            renamed = []
            for side_b, values in sides.items():
                values = sorted(values, key=lambda value: abs(value[1]-middle))
                for index, value in enumerate(values):
                    face = "interna" if index == 0 else "externa"
                    rank = ((1 if index == 0 else 0) if not side_b
                            else (2 if index == 0 else 3))
                    renamed.append((rank, value[1], value[2],
                                    "Lado %s — face %s" % (
                                        "B" if side_b else "A", face), value[4]))
            internal[1] = renamed

    order = {"external": 0, "internal": 1, "between": 2,
             "stiffener_a": 3, "stiffener_b": 4,
             "angle_a": 3, "angle_b": 4,
             "component_internal_a": 3, "component_internal_b": 4,
             "supported": 5}
    result = []
    for region_id, (label, positions) in sorted(
            regions.items(), key=lambda item: (order.get(item[0], 9), item[1][0])):
        positions = tuple((key, position_label) for _rank, _center, key,
                          position_label, _candidate in sorted(
                              positions, key=lambda value: (value[0], value[1], value[2])))
        result.append((region_id, label, positions))
    return tuple(result)


def _resolved_transverse_key(attachment):
    return next((candidate.stable_key for candidate in attachment.candidates
                 if candidate.slot_id == attachment.governing_slot_id
                 and candidate.placement == attachment.placement_kind
                 and candidate.slot_id), "")


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
        self._last_gusset_previews = {}
        self._gusset_visibility = {}
        self._initial_frame_pending = obj is None
        self._point_callbacks = []
        self._view = None
        self.timings = {}
        self.closed = False
        self.last_candidate = None

    def _hide_persistent_gussets(self):
        if self.object is None:
            return
        for plate in getattr(self.object, "GeneratedGussetPlates", ()):
            self._gusset_visibility.setdefault(plate.Name, bool(plate.ViewObject.Visibility))
            plate.ViewObject.Visibility = False

    def _restore_persistent_gussets(self):
        for name, visibility in self._gusset_visibility.items():
            plate = self.document.getObject(name)
            if plate is not None:
                plate.ViewObject.Visibility = visibility
        self._gusset_visibility = {}

    def candidate(self, config):
        config = resolve_linked_reference(self.document, config, self.object)
        if self.object is not None:
            if self.last_candidate is not None:
                # Candidate-to-candidate comparison is required for successive
                # preset/envelope changes: a newly edited intent must not be
                # mistaken for an accepted intent when the topology changes
                # again before Apply.
                applied = self.last_candidate
            else:
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
        from ..trusses.gussets import preliminary_gusset_outlines
        from ..connections import attachment_warning_messages
        resolutions, orphan_diagnostics, _canonical = resolve_truss_connections(
            candidate, reference_frame(candidate.config)[3])
        transverse_previews = {}
        gussets, gusset_diagnostics = preliminary_gusset_outlines(
            candidate, transverse_previews=transverse_previews)
        attachment_by_node = {
            value.spec.node_key: list(attachment_warning_messages((value,)))
            for value in gussets}
        for diagnostic in gusset_diagnostics:
            if diagnostic.node_key:
                attachment_by_node.setdefault(diagnostic.node_key, []).append(
                    diagnostic.message)
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
                    transverse_previews=transverse_previews,
                    gussets=[dict(stable_key=value.spec.stable_key,
                                  node_key=value.spec.node_key,
                                  points=tuple((candidate.graph.node(value.spec.node_key).position_local[0]+x,
                                                candidate.graph.node(value.spec.node_key).position_local[1]+y)
                                               for x, y in value.points),
                                  side=value.spec.side.value,
                                  chord_contact=value.spec.chord_contact.value,
                                  transverse_placement=value.spec.transverse_placement,
                                  resolved_transverse_placement=_resolved_transverse_key(
                                      value.attachment),
                                  plate_thickness=value.spec.plate_thickness,
                                  materializable=(value.attachment.kind
                                                  != "NominalFallback"),
                                  transverse_regions=_transverse_placement_regions(
                                      value.attachment.candidates))
                             for value in gussets],
                    # Gusset diagnostics are shown only for the selected node
                    # in the topology editor, never in the generator footer.
                    connection_diagnostics=list(dict.fromkeys(
                        [d.message for d in orphan_diagnostics]
                        +[d.message for value in resolutions
                          if value.intent.form.value != "Gusset"
                          for d in value.diagnostics])),
                    connection_diagnostics_by_node={
                        key: list(dict.fromkeys(messages))
                        for key, messages in attachment_by_node.items()},
                    gusset_diagnostic_nodes=[d.node_key for d in gusset_diagnostics
                                             if d.node_key])

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
        gussets, diagnostics = preliminary_gusset_outlines(candidate)
        valid_nodes = set()
        for outline in gussets:
            if (getattr(outline, "attachment", None) is not None
                    and outline.attachment.kind == "NominalFallback"):
                continue
            shape = build_gusset_shape(outline)
            shapes.append(shape)
            colors.append((.45, .20, .65))
            valid_nodes.add(outline.spec.node_key)
            self._last_gusset_previews[outline.spec.node_key] = (outline.spec.frame, shape.copy())
        diagnostic_nodes = {value.node_key for value in diagnostics if value.node_key}
        pending_nodes = diagnostic_nodes-valid_nodes
        if pending_nodes:
            local_frame = reference_frame(candidate.config)
            node_keys = {value.key for value in candidate.graph.nodes}
            close = lambda a, b: all(abs(x-y) <= 1e-7 for x, y in zip(a, b))
            for node_key in sorted(pending_nodes):
                previous = self._last_gusset_previews.get(node_key)
                if previous is None or node_key not in node_keys:
                    continue
                frame, shape = previous
                node = candidate.graph.node(node_key)
                current_origin = transform_point(node.position_local, local_frame)
                if (close(frame.origin, current_origin) and close(frame.x_axis, local_frame[1])
                        and close(frame.y_axis, local_frame[2]) and close(frame.normal, local_frame[3])):
                    shapes.append(shape.copy())
                    colors.append((.45, .20, .65))
        for node_key in set(self._last_gusset_previews)-(valid_nodes | diagnostic_nodes):
            del self._last_gusset_previews[node_key]
        compound = Part.makeCompound(shapes)
        view = Gui.activeDocument().activeView()
        if self._preview is None:
            self._preview = TrussScenePreview(view.getSceneGraph())
        self._preview.update(shapes, colors, compound)
        self._hide_persistent_gussets()
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
        self._restore_persistent_gussets()

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
