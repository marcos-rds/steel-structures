"""Truss topology adapter for the generic pure physical-fitting core."""

from dataclasses import asdict, replace
import math

from ..fitting import (
    FitDiagnostic, FittingPolicy, NominalMember,
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
    return PhysicalFitPlan(
        plan_key=plan.plan_key, member_key=plan.member_key, run_key=plan.run_key,
        mode=plan.mode,
        start_action=addition.start_action or plan.start_action,
        end_action=addition.end_action or plan.end_action,
        diagnostics=plan.diagnostics + addition.diagnostics,
        schema_version=plan.schema_version,
    )


def _effective_axis(item):
    start, end = tuple(item.start_global), tuple(item.end_global)
    delta = tuple(b-a for a, b in zip(start, end))
    length = math.sqrt(sum(value*value for value in delta))
    direction = tuple(value/length for value in delta)
    plan = item.physical_fit_plan or {}
    start_action, end_action = plan.get("start_action"), plan.get("end_action")
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
        if any(abs(a-b) > 1e-7 for pair in zip(stations[0], stations[1]) for a, b in (pair,)):
            raise ValueError("Os componentes A/B possuem envelopes físicos incompatíveis para interconectores.")
        nominal_start = transform_point(candidate.graph.node(run.start_node_key).position_local, frame)
        nominal_end = transform_point(candidate.graph.node(run.end_node_key).position_local, frame)
        direction = tuple(b-a for a, b in zip(nominal_start, nominal_end))
        length = math.sqrt(sum(value*value for value in direction))
        direction = tuple(value/length for value in direction)
        start_station, end_station = stations[0]
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
                origin = tuple(float(v) + float(action.get("gap", 0.))*axis
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


def apply_physical_fits(candidate, frame):
    """Return items carrying plans; nominal item endpoints remain untouched."""
    items = []
    for item in candidate.items:
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
                if len(directions) > 1:
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
                target_reference, _parameter = min(references, key=lambda value: value[1])
                addition = resolve_physical_fit(
                    member, target_reference, policy, node_key)
                plan = _merge(plan, addition)
        elif mode in (PhysicalFitMode.GUSSET_AWARE, PhysicalFitMode.CUSTOM):
            plan = resolve_physical_fit(member, None, policy)
        items.append(replace(item, physical_fit_plan=asdict(plan)))
    return _refit_interconnectors(candidate, tuple(items), frame)
