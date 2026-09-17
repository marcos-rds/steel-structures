"""Truss topology adapter for the generic pure physical-fitting core."""

from dataclasses import asdict, replace
import math

from ..fitting import (
    FitAction, FitActionMode, FitDiagnostic, FitEnd, FitSource, FittingPolicy,
    NominalMember,
    PhysicalFitMode, PhysicalFitPlan, resolve_physical_fit,
)


FIT_CANDIDATE_ROLES = frozenset(("DIAGONAL", "VERTICAL", "END_POST"))
CHORD_ROLES = frozenset(("TOP_CHORD", "BOTTOM_CHORD"))


def _target_runs(candidate, node_key):
    incident_chord_edges = {
        edge.key for edge in candidate.graph.edges
        if edge.role in CHORD_ROLES and node_key in (edge.start_node_key, edge.end_node_key)
    }
    return tuple(run for run in candidate.runs
                 if run.role in CHORD_ROLES and incident_chord_edges.intersection(run.edge_keys))


def _merge(plan, addition):
    result = replace(plan, diagnostics=plan.diagnostics+addition.diagnostics,
                     additional_actions=plan.additional_actions+addition.additional_actions)
    for action in (addition.start_action, addition.end_action):
        if action is not None:
            result = _set_action(result, action, plan.mode)
    return result


def _chord_joints(candidate):
    from .connections import chord_joints
    return {node.key: chord_joints(candidate, node.key)
            for node in candidate.graph.nodes}


def _ridge_targets(candidate, item, node_key, targets, breaks):
    """Select local left/right branch for diagonals; axial webs see both."""
    keys = {key for p in breaks for key in p.physical_run_keys}
    if item.role != "DIAGONAL":
        return targets
    node = candidate.graph.node(node_key).position_local
    other_key = item.end_node_key if node_key == item.start_node_key else item.start_node_key
    dx = candidate.graph.node(other_key).position_local[0]-node[0]
    if abs(dx) <= 1e-7:
        return targets
    selected = []
    for run in targets:
        other = run.end_node_key if node_key == run.start_node_key else run.start_node_key
        branch_dx = candidate.graph.node(other).position_local[0]-node[0]
        if run.key not in keys or dx*branch_dx > 0.:
            selected.append(run)
    if not selected:
        raise ValueError("Não há ramo de banzo no lado local da diagonal incidente.")
    return tuple(selected)


def _chord_miter_plan(candidate, item, frame, joints):
    from ..connections.resolver import chord_joint_plane
    from ..fitting import GeometryReference
    from .realization import transform_point
    member = NominalMember(item.key, item.run_key, item.role,
                           item.start_node_key, item.end_node_key,
                           tuple(item.start_global), tuple(item.end_global), item.element_kind)
    plan = resolve_physical_fit(member, None, FittingPolicy(mode=PhysicalFitMode.NONE))
    for node_key in (item.start_node_key, item.end_node_key):
        for participant in joints.get(node_key, ()):
            if item.run_key not in participant.physical_run_keys:
                continue
            normal_local = chord_joint_plane(participant)
            normal = tuple(sum(normal_local[j]*frame[j+1][i] for j in range(3)) for i in range(3))
            reference = GeometryReference(
                participant.participant_key, "Plane",
                transform_point(candidate.graph.node(node_key).position_local, frame), normal=normal)
            addition = resolve_physical_fit(member, reference, FittingPolicy(
                mode=PhysicalFitMode.TO_CHORD, gap=0.), node_key)
            plan = _merge(replace(plan, mode=PhysicalFitMode.TO_CHORD), addition)
    return asdict(plan)


def _connection_action(item, directive, frame):
    """Convert a pure connection directive into the existing end-action contract."""
    end = FitEnd(directive.end)
    gap = float(item.spec.physical_fit_gap)
    if directive.kind == "GussetSetback":
        return FitAction(end, FitActionMode.LENGTH_LIMIT, directive.reference_key,
                         gap=gap, reference_offset=float(directive.reference_offset),
                         source=FitSource.CONNECTION_INTENT)
    origin_local, normal_local = directive.plane_origin, directive.plane_normal
    origin = tuple(frame[0][i] + sum(origin_local[j]*frame[j+1][i] for j in range(3))
                   for i in range(3))
    normal = tuple(sum(normal_local[j]*frame[j+1][i] for j in range(3))
                   for i in range(3))
    axis = tuple(b-a for a, b in zip(item.start_global, item.end_global))
    length = math.sqrt(sum(value*value for value in axis))
    direction = tuple(value/length for value in axis)
    denominator = sum(a*b for a, b in zip(normal, direction))
    if abs(denominator) <= 1e-7:
        raise ValueError("O membro é paralelo ao plano compartilhado.")
    parameter = sum(n*(o-s) for n, o, s in zip(normal, origin, item.start_global))/denominator
    offset = parameter if end == FitEnd.START else length-parameter
    return FitAction(end, FitActionMode.PLANE_CUT, directive.reference_key,
                     gap=gap, reference_offset=offset, plane_origin=origin,
                     plane_normal=normal, source=FitSource.CONNECTION_INTENT)


def _set_action(plan, action, mode, diagnostics=()):
    previous = plan.start_action if action.end == FitEnd.START else plan.end_action
    additional = plan.additional_actions
    if previous is not None and previous != action:
        additional += (previous,)
    return replace(plan, mode=mode,
                   start_action=action if action.end == FitEnd.START else plan.start_action,
                   end_action=action if action.end == FitEnd.END else plan.end_action,
                   diagnostics=plan.diagnostics+tuple(diagnostics), additional_actions=additional)


def _connection_diagnostics(values):
    return tuple(FitDiagnostic(value.code, value.severity, value.message) for value in values)


def _previous_connection_action(applied, item, end):
    if applied is None:
        return None
    previous = next((value for value in applied.items if value.key == item.key), None)
    if previous is None or not previous.physical_fit_plan:
        return None
    value = previous.physical_fit_plan.get("start_action" if end == "Start" else "end_action")
    if not value or value.get("source") != FitSource.CONNECTION_INTENT.value:
        return None
    return FitAction(end=FitEnd(value["end"]), mode=FitActionMode(value["mode"]),
                     reference_key=value["reference_key"], gap=float(value.get("gap", 0.)),
                     reference_offset=float(value.get("reference_offset", 0.)),
                     plane_origin=tuple(value["plane_origin"]) if value.get("plane_origin") else None,
                     plane_normal=tuple(value["plane_normal"]) if value.get("plane_normal") else None,
                     source=FitSource.CONNECTION_INTENT)


def _effective_axis(item):
    start, end = tuple(item.start_global), tuple(item.end_global)
    delta = tuple(b-a for a, b in zip(start, end))
    length = math.sqrt(sum(value*value for value in delta))
    direction = tuple(value/length for value in delta)
    plan = item.physical_fit_plan or {}
    actions = [a for a in (plan.get("start_action"), plan.get("end_action")) if a]
    actions += list(plan.get("additional_actions", ()))
    most_inward = lambda end: max((a for a in actions if a["end"] == end),
                                  key=lambda a: float(a["reference_offset"])+float(a["gap"]), default=None)
    start_action, end_action = most_inward("Start"), most_inward("End")
    start_station = ((float(start_action["reference_offset"])+float(start_action["gap"]))
                     if start_action else 0.)
    end_station = (length-float(end_action["reference_offset"])-float(end_action["gap"])
                   if end_action else length)
    if end_station-start_station <= 1e-7:
        raise ValueError("O fitting não deixa comprimento físico para a assembly.")
    point = lambda station: tuple(origin+station*axis for origin, axis in zip(start, direction))
    return (point(start_station), point(end_station)), start_station, end_station


def _refit_interconnectors(candidate, fitted_items, frame):
    """Regenerate C4 elements over the fitted host envelope, without node fitting."""
    from ..assemblies.interconnectors import resolve_interconnectors
    from ..assemblies.models import ComponentRealization
    from .assemblies import assembly_frame, interconnector_items, role_assembly_spec
    from .fitting_geometry import chord_envelope_reference
    from .realization import transform_point
    from ..assemblies.attachment import dot, section_support
    output = []
    for run in candidate.runs:
        run_items = [item for item in fitted_items if item.run_key == run.key]
        components = [item for item in run_items if item.element_kind == "Component"]
        connectors = [item for item in run_items if item.element_kind == "Interconnector"]
        output.extend(components)
        if not connectors:
            continue
        if not any(item.physical_fit_plan and (
                item.physical_fit_plan.get("start_action") or item.physical_fit_plan.get("end_action"))
                for item in components):
            output.extend(connectors)
            continue
        base = next(item for item in components if item.component_key == "A")
        assembly = role_assembly_spec(asdict(base.spec))
        component_specs = {component.component_key: component for component in assembly.components}
        realized = []
        stations = []
        for item in sorted(components, key=lambda value: value.component_key):
            effective, start_station, end_station = _effective_axis(item)
            stations.append((start_station, end_station))
            component = component_specs[item.component_key]
            member_frame = assembly_frame(
                (item.start_global, item.end_global), item.section_u_global, item.spec.rotation)
            realized.append(ComponentRealization(
                (assembly.assembly_key, item.component_key), item.component_key,
                component.profile_ref, effective[0], effective[1], member_frame,
                component.insertion_reference, component.section_transform,
                component.section_geometry_mode, component.color,
            ))
        nominal_start = transform_point(candidate.graph.node(run.start_node_key).position_local, frame)
        nominal_end = transform_point(candidate.graph.node(run.end_node_key).position_local, frame)
        direction = tuple(b-a for a, b in zip(nominal_start, nominal_end))
        length = math.sqrt(sum(value*value for value in direction))
        direction = tuple(value/length for value in direction)
        start_station = max(pair[0] for pair in stations)
        end_station = min(pair[1] for pair in stations)
        if end_station-start_station <= 1e-7:
            raise ValueError("Os componentes não deixam envelope comum para interconectores.")
        effective_axis = (
            tuple(value+start_station*axis for value, axis in zip(nominal_start, direction)),
            tuple(value+end_station*axis for value, axis in zip(nominal_start, direction)),
        )
        resolved, _distributions = resolve_interconnectors(
            effective_axis, tuple(realized), assembly)
        # A connector can be inside the fitted axial envelope and still cross
        # an oblique cut plane. Measure its final, face-attached section against
        # the same planes used by A/B, then move the distribution inward.
        clearance = {"Start": 0., "End": 0.}
        constraints = {"Start": [], "End": []}
        from ..fitting import GeometryReference
        for component in components:
            plan = component.physical_fit_plan or {}
            actions = [a for a in (plan.get("start_action"), plan.get("end_action")) if a]
            actions += list(plan.get("additional_actions", ()))
            for action in actions:
                if action["mode"] != "PlaneCut":
                    continue
                sign = 1. if action["end"] == "Start" else -1.
                origin = tuple(p+sign*float(action["gap"])*v
                               for p,v in zip(action["plane_origin"],direction))
                constraints[action["end"]].append(GeometryReference(
                    action["reference_key"], "Face", origin, normal=tuple(action["plane_normal"])))
        for node_key, end_name in ((run.start_node_key, "Start"),
                                   (run.end_node_key, "End")):
            node_global = transform_point(candidate.graph.node(node_key).position_local, frame)
            targets = _target_runs(candidate, node_key)
            target_items = [item for item in fitted_items
                            if item.element_kind == "Component"
                            and any(item.run_key == target.key for target in targets)]
            for target in target_items:
                constraints[end_name].append(chord_envelope_reference(
                    base, target, node_global, tuple(frame[3]), end_name))
        for end_name, references in constraints.items():
            inward = direction if end_name == "Start" else tuple(-v for v in direction)
            action = (base.physical_fit_plan or {}).get(
                "start_action" if end_name == "Start" else "end_action") or {}
            for reference in references:
                normal = tuple(reference.normal)
                axial_projection = dot(inward, normal)
                if abs(axial_projection) <= 1e-12:
                    continue
                origin = tuple(float(v) + (0. if reference.kind == "Face" else float(action.get("gap", 0.)))*axis
                               for v, axis in zip(reference.origin, inward))
                inside_sign = 1. if axial_projection > 0. else -1.
                for connector in resolved:
                    low, high = section_support(connector, normal)
                    axial = [dot(tuple(p-o for p, o in zip(point, origin)), normal)
                             for point in (connector.start_global, connector.end_global)]
                    extrema = (min(axial)+low, max(axial)+high)
                    inside = (extrema[0] if inside_sign > 0. else -extrema[1])
                    clearance[end_name] = max(
                        clearance[end_name], max(0., -inside)/abs(axial_projection))
        if clearance["Start"] > 1e-7 or clearance["End"] > 1e-7:
            assembly = replace(assembly, interconnectors=tuple(
                replace(spec,
                        start_offset=spec.start_offset+clearance["Start"],
                        end_offset=spec.end_offset+clearance["End"])
                for spec in assembly.interconnectors))
            resolved, _distributions = resolve_interconnectors(
                effective_axis, tuple(realized), assembly)
        template = replace(base, key=run.key, physical_fit_plan=None)
        output.extend(interconnector_items(template, resolved, assembly.assembly_key))
    return tuple(output)


def apply_physical_fits(candidate, frame, applied=None):
    """Return items carrying plans; nominal item endpoints remain untouched."""
    items = []
    joints = _chord_joints(candidate)
    from ..connections import ChordBreakParticipant
    breaks = {node_key: tuple(p for p in participants
                              if isinstance(p, ChordBreakParticipant))
              for node_key, participants in joints.items()}
    for item in candidate.items:
        if item.element_kind == "Component" and item.role in CHORD_ROLES:
            affected = any(item.run_key in p.physical_run_keys
                           for node in (item.start_node_key, item.end_node_key)
                           for p in joints.get(node, ()))
            previous = next((i for i in applied.items if i.key == item.key), None) if applied else None
            if affected or (previous is not None and previous.physical_fit_plan):
                item = replace(item, physical_fit_plan=_chord_miter_plan(candidate, item, frame, joints))
            items.append(item)
            continue
        if item.element_kind != "Component" or item.role not in FIT_CANDIDATE_ROLES:
            items.append(item)
            continue
        mode = PhysicalFitMode(item.spec.physical_fit)
        policy = FittingPolicy(mode=mode, gap=float(item.spec.physical_fit_gap))
        member = NominalMember(
            item.key, item.run_key, item.role, item.start_node_key, item.end_node_key,
            tuple(item.start_global), tuple(item.end_global), item.element_kind,
        )
        plan = resolve_physical_fit(member, None, FittingPolicy(mode=PhysicalFitMode.NONE))
        plan = replace(plan, mode=mode)
        if mode == PhysicalFitMode.TO_CHORD:
            for node_key in (item.start_node_key, item.end_node_key):
                targets = _target_runs(candidate, node_key)
                ridge = breaks.get(node_key, ())
                if ridge:
                    targets = _ridge_targets(candidate, item, node_key, targets, ridge)
                if not targets:
                    missing = resolve_physical_fit(member, None, policy, node_key)
                    plan = _merge(plan, missing)
                    continue
                directions = set()
                for target in targets:
                    a = candidate.graph.node(target.start_node_key).position_local
                    b = candidate.graph.node(target.end_node_key).position_local
                    delta = tuple(y-x for x, y in zip(a, b))
                    length = math.sqrt(sum(value*value for value in delta))
                    directions.add(tuple(round(abs(value/length), 9) for value in delta))
                if len(directions) > 1 and not ridge:
                    plan = replace(plan, diagnostics=plan.diagnostics + (FitDiagnostic(
                        "AMBIGUOUS_CHORD", "Warning",
                        "Mais de um banzo não colinear chega ao nó; ajuste físico não aplicado nesta ponta."),))
                    continue
                from .realization import transform_point
                from .fitting_geometry import chord_contact_reference
                node_global = transform_point(candidate.graph.node(node_key).position_local, frame)
                end = "Start" if node_key == item.start_node_key else "End"
                references = []
                for target in targets:
                    for target_item in candidate.items:
                        if (target_item.run_key != target.key
                                or target_item.element_kind != "Component"):
                            continue
                        try:
                            references.append(chord_contact_reference(
                                item, target_item, node_global, tuple(frame[3]), end))
                        except ValueError:
                            continue
                if not references:
                    plan = replace(plan, diagnostics=plan.diagnostics + (FitDiagnostic(
                        "INVALID_CHORD_GEOMETRY", "Warning",
                        "A geometria física do banzo não fornece uma face de contato estável."),))
                    continue
                chosen = references if ridge else [min(references, key=lambda value: value[1])]
                if ridge and item.role == "DIAGONAL":
                    from .fitting_geometry import cut_needs_clearance
                    other_keys = {k for p in ridge for k in p.physical_run_keys}-{t.key for t in targets}
                    protections = []
                    for target in candidate.items:
                        if target.run_key not in other_keys or target.element_kind != "Component":
                            continue
                        clearance, _parameter = chord_contact_reference(
                            item, target, node_global, tuple(frame[3]), end)
                        if any(cut_needs_clearance(item,end,contact,clearance) for contact,_ in chosen):
                            protections.append((clearance,0.))
                    # Keep the corresponding local branch as the principal
                    # reference; safety planes compose through the same v2 end.
                    chosen = protections+chosen
                for target_reference, _parameter in chosen:
                    addition = resolve_physical_fit(member, target_reference, policy, node_key)
                    plan = _merge(plan, addition)
        elif mode in (PhysicalFitMode.GUSSET_AWARE, PhysicalFitMode.CUSTOM):
            plan = resolve_physical_fit(member, None, policy)
        items.append(replace(item, physical_fit_plan=asdict(plan)))
    base_candidate = replace(candidate, items=tuple(items))
    from .connections import resolve_truss_connections, validate_center_gusset
    resolutions, _orphan_diagnostics, canonical = resolve_truss_connections(
        base_candidate, (0., 0., 1.))
    if "connection_intents" in candidate.config:
        candidate.config["connection_intents"] = canonical
    by_run = {}
    for item in items:
        if item.element_kind == "Component":
            by_run.setdefault(item.run_key, []).append(item)
    from ..fitting.serialization import loads as load_fit_plan
    from .serialization import dumps, loads
    plans = {item.key: load_fit_plan(dumps(item.physical_fit_plan))
             for item in items
             if item.element_kind == "Component" and item.physical_fit_plan}
    for resolution in resolutions:
        gusset_diagnostics = tuple(validate_center_gusset(base_candidate, resolution))
        extra = tuple(resolution.diagnostics) + gusset_diagnostics
        directives = resolution.directives
        affected = {key for participant in resolution.participants for key in participant.physical_run_keys}
        for run_key in affected:
            for item in by_run.get(run_key, ()):
                if item.key not in plans:
                    continue
                plans[item.key] = replace(plans[item.key],
                    diagnostics=plans[item.key].diagnostics+_connection_diagnostics(extra))
        if extra and not directives:
            preserved = False
            for participant in resolution.participants:
                if participant.end == "Through":
                    continue
                for item in by_run.get(participant.run_key, ()):
                    previous = _previous_connection_action(applied, item, participant.end)
                    if previous is not None:
                        preserved = True
                        plans[item.key] = _set_action(
                            plans[item.key], previous, PhysicalFitMode.CUSTOM,
                            (FitDiagnostic("PREVIOUS_CONNECTION_FIT_PRESERVED", "Warning",
                                           "Último fitting de ligação válido preservado."),))
            previous_intents = (applied.config.get("connection_intents", {})
                                if applied is not None else {})
            if (preserved and resolution.intent.node_key in previous_intents
                    and any(d.code == "MISSING_PARTICIPANT" for d in extra)):
                candidate.config["connection_intents"][resolution.intent.node_key] = loads(
                    dumps(previous_intents[resolution.intent.node_key]))
        for directive in directives:
            for item in by_run.get(directive.run_key, ()):
                try:
                    if directive.kind == "FitToParticipant":
                        from .realization import transform_point
                        from .fitting_geometry import chord_envelope_reference
                        node_key = item.start_node_key if directive.end == "Start" else item.end_node_key
                        node_global = transform_point(candidate.graph.node(node_key).position_local, frame)
                        references = []
                        for target in (target for key in (directive.target_run_keys or (directive.target_run_key,))
                                       for target in by_run.get(key, ())):
                            reference = chord_envelope_reference(
                                item, target, node_global, tuple(frame[3]), directive.end)
                            direction = tuple(b-a for a,b in zip(item.start_global,item.end_global))
                            inward = direction if directive.end == "Start" else tuple(-v for v in direction)
                            denominator = sum(a*b for a,b in zip(inward,reference.normal))
                            if abs(denominator) <= 1e-9:
                                raise ValueError("Participantes paralelos; contato prioritário indeterminado.")
                            station = sum((a-b)*n for a,b,n in zip(
                                reference.origin,node_global,reference.normal))/denominator
                            references.append((reference, station))
                        if not references:
                            raise ValueError("Participante prioritário sem face de contato estável.")
                        # A single separating plane must clear the entire primary
                        # section/assembly, including legs missed by an axis ray.
                        reference, _ = max(references, key=lambda value: value[1])
                        member = NominalMember(item.key, item.run_key, item.role,
                                               item.start_node_key, item.end_node_key,
                                               tuple(item.start_global), tuple(item.end_global),
                                               item.element_kind)
                        addition = resolve_physical_fit(member, reference, FittingPolicy(
                            mode=PhysicalFitMode.TO_CHORD,
                            gap=float(item.spec.physical_fit_gap),
                            source=FitSource.CONNECTION_INTENT), node_key)
                        action = addition.start_action or addition.end_action
                        if action is None:
                            raise ValueError(" ".join(d.message for d in addition.diagnostics)
                                             or "Contato prioritário degenerado.")
                    else:
                        action = _connection_action(item, directive, frame)
                        if directive.kind == "GussetSetback":
                            # Additional axial clearance follows the physical chord
                            # contact, while the transverse slab is resolved separately.
                            base = plans[item.key].start_action if directive.end == "Start" else plans[item.key].end_action
                            if base is not None:
                                action = replace(action, reference_offset=(
                                    max(0., base.reference_offset)+directive.reference_offset))
                    plans[item.key] = _set_action(
                        plans[item.key], action,
                        PhysicalFitMode.GUSSET_AWARE if directive.kind == "GussetSetback"
                        else PhysicalFitMode.CUSTOM)
                except ValueError as exc:
                    if applied is not None:
                        raise ValueError("Ligação inválida; estado aplicado preservado. "+str(exc)) from exc
                    plans[item.key] = replace(plans[item.key], diagnostics=plans[item.key].diagnostics + (
                        FitDiagnostic("CONNECTION_GEOMETRY_INVALID", "Warning", str(exc)),))
    fitted = tuple(replace(item, physical_fit_plan=asdict(plans[item.key]))
                   if item.key in plans else item for item in items)
    return _refit_interconnectors(candidate, fitted, frame)
