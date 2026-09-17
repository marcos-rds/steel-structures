"""Pure bridge from truss topology/configuration to connection contracts."""

from dataclasses import asdict
import json

from ..connections import (CONNECTION_INTENT_SCHEMA_VERSION, ConnectionDiagnostic,
                           ConnectionForm, ConnectionIntent, DirectFitPolicy,
                           FasteningIntent, GussetFitSpec, GussetSide, PriorityMember,
                           resolve_chord_joints, resolve_connection,
                           resolve_connection_participants)
from .serialization import dumps


def intent_from_data(node_key, value):
    value = dict(value or {})
    gusset = dict(value.get("gusset", {}))
    intent = ConnectionIntent(
        intent_key=value.get("intent_key", node_key+":connection"), node_key=node_key,
        form=ConnectionForm(value.get("form", "GeometricOnly")),
        fastening=FasteningIntent(value.get("fastening", "Unspecified")),
        direct_policy=DirectFitPolicy(value.get("direct_policy", "Independent")),
        participant_run_keys=tuple(value.get("participant_run_keys", ())),
        priority_member=PriorityMember(value.get("priority_member", "Automatic")),
        priority_run_key=value.get("priority_run_key", ""),
        gusset=GussetFitSpec(
            plate_thickness=float(gusset.get("plate_thickness", 0.)),
            normal_clearance=float(gusset.get("normal_clearance", 0.)),
            axial_clearance=float(gusset.get("axial_clearance", 0.)),
            side=GussetSide(gusset.get("side", "Center"))),
        schema_version=value.get("schema_version", CONNECTION_INTENT_SCHEMA_VERSION))
    from ..connections.validation import validate_intent
    return validate_intent(intent)


def intent_data(intent):
    return json.loads(dumps(asdict(intent)))


def default_intent(node_key):
    return intent_data(ConnectionIntent(node_key+":connection", node_key))


def _run_data(candidate):
    result = {}
    for run in candidate.runs:
        components = sorted((item for item in candidate.items
                             if item.run_key == run.key and item.element_kind == "Component"),
                            key=lambda item: item.component_key)
        if not components:
            continue
        base = components[0]
        geometry = tuple((item.spec.profile_ref, item.spec.insertion,
                          item.spec.section_geometry_mode, item.spec.rotation, item.section_transform)
                         for item in components)
        result[run.key] = dict(
            assembly=base.spec.assembly,
            component_keys=tuple(item.component_key for item in components),
            geometry_key=dumps(geometry),
            # Compare physical section frames too: equal profile names alone
            # cannot establish continuity of rotated asymmetric sections.
            continuity_key=tuple(tuple(round(v, 7) for v in item.section_u_global)
                                 for item in components),
        )
    return result


def connection_participants(candidate, node_key):
    """Public stable participant view used by the node editor."""
    node = candidate.graph.node(node_key)
    return resolve_connection_participants(
        node, candidate.graph, candidate.runs, _run_data(candidate))


def chord_joints(candidate, node_key):
    """Physical chord joints used by fitting, separate from editor participants."""
    node = candidate.graph.node(node_key)
    return resolve_chord_joints(
        node, candidate.graph, candidate.runs, _run_data(candidate))


def resolve_truss_connections(candidate, truss_plane_normal):
    """Return resolutions and orphan diagnostics without mutating topology."""
    configured = candidate.config.get("connection_intents", {}) or {}
    nodes = {node.key: node for node in candidate.graph.nodes}
    resolutions, diagnostics, canonical = [], [], {}
    run_data = _run_data(candidate)
    for node_key in sorted(configured):
        intent = intent_from_data(node_key, configured[node_key])
        node = nodes.get(node_key)
        if node is None:
            diagnostics.append(ConnectionDiagnostic(
                "ORPHAN_CONNECTION_NODE", "Warning",
                "Intenção de ligação removida do candidato porque o nó deixou de existir."))
            continue
        canonical[node_key] = intent_data(intent)
        participants = resolve_connection_participants(
            node, candidate.graph, candidate.runs, run_data)
        resolutions.append(resolve_connection(
            intent, participants, node.position_local, tuple(truss_plane_normal)))
    return tuple(resolutions), tuple(diagnostics), canonical


def validate_center_gusset(candidate, resolution):
    """Project every physical section onto the preliminary slab normal.

    An axis parallel to the slab cannot acquire transverse clearance through
    axial shortening. Diagnose that incompatibility without changing either
    the requested dimensions or the nominal/component axes.
    """
    if resolution.gusset_plane is None:
        return ()
    from .realization import reference_frame, transform_point
    from .assemblies import assembly_frame
    from .fitting_geometry import _section_at_insertion
    from ..assemblies.attachment import support
    frame = reference_frame(candidate.config)
    plane = resolution.gusset_plane
    origin = transform_point(plane.origin, frame)
    normal = tuple(sum(plane.normal[j]*frame[j+1][i] for j in range(3)) for i in range(3))
    half_width = plane.plate_thickness/2.+plane.normal_clearance
    dot = lambda a,b: sum(x*y for x,y in zip(a,b))
    diagnostics = []
    for participant in resolution.participants:
        if participant.role not in ("DIAGONAL", "VERTICAL", "END_POST"):
            continue
        components = [item for item in candidate.items
                      if item.run_key in participant.physical_run_keys
                      and item.element_kind == "Component"]
        for item in components:
            member_frame = assembly_frame((item.start_global,item.end_global),item.section_u_global,item.spec.rotation)
            section, translation = _section_at_insertion(item)
            projected = (dot(normal,member_frame.u),dot(normal,member_frame.v))
            low, high = support(section,projected)
            shift = dot(tuple(a-b for a,b in zip(item.start_global,origin)),normal)+dot(translation,projected)
            if low+shift < half_width-1e-7 and high+shift > -half_width+1e-7:
                diagnostics.append(ConnectionDiagnostic(
                    "GUSSET_CENTER_SPACE_INVALID", "Warning",
                    "A seção intercepta o espaço central da chapa e das folgas normais. "
                    "Parâmetros e recuo axial preservados; ajuste a posição transversal ou o espaçamento da composição."))
    return tuple(dict.fromkeys(diagnostics))
