"""Pure bridge from truss topology/configuration to connection contracts."""

from dataclasses import asdict, replace
import json

from ..connections import (CONNECTION_INTENT_SCHEMA_VERSION, ConnectionDiagnostic,
                           ConnectionForm, ConnectionIntent, DirectFitPolicy,
                           FasteningIntent, GussetAttachmentMode, GussetChordContact,
                           GussetFitSpec,
                           GussetSide, PriorityMember,
                           resolve_chord_joints, resolve_connection,
                           resolve_connection_participants)
from .serialization import dumps


def intent_from_data(node_key, value):
    value = dict(value or {})
    schema_version = value.get("schema_version", CONNECTION_INTENT_SCHEMA_VERSION)
    if schema_version not in (1, 2, 3, CONNECTION_INTENT_SCHEMA_VERSION):
        raise ValueError("Versão de ConnectionIntent não suportada.")
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
            side=GussetSide(gusset.get("side", "Center")),
            edge_margin=float(gusset.get("edge_margin", 25.)),
            member_overlap=float(gusset.get("member_overlap", 150.)),
            attachment_mode=GussetAttachmentMode(
                gusset.get("attachment_mode", "Auto")),
            chord_contact=GussetChordContact(
                gusset.get("chord_contact", "Auto")),
            transverse_placement=gusset.get("transverse_placement", "")),
        schema_version=CONNECTION_INTENT_SCHEMA_VERSION)
    from ..connections.validation import validate_intent
    return validate_intent(intent)


def intent_data(intent):
    return json.loads(dumps(asdict(intent)))


def default_intent(node_key):
    return intent_data(ConnectionIntent(node_key+":connection", node_key))


def gusset_thickness_for_transition(node_key, configured=None,
                                    default_gusset_thickness=10.):
    """Preserve prior intent values; initialize a genuinely new Gusset at 10 mm."""
    intent = intent_from_data(node_key, configured or default_intent(node_key))
    if (not isinstance(default_gusset_thickness, (int, float))
            or isinstance(default_gusset_thickness, bool)
            or default_gusset_thickness <= 0.):
        raise ValueError("Espessura padrão de Gusset deve ser maior que zero.")
    return (intent.gusset.plate_thickness if intent.gusset.plate_thickness > 0.
            else float(default_gusset_thickness))


def gusset_default_after_edit(node_key, configured, edited,
                              current_default=10.):
    """Update the per-truss default only after an actual thickness edit."""
    if (not isinstance(current_default, (int, float))
            or isinstance(current_default, bool) or current_default <= 0.):
        raise ValueError("Espessura padrão de Gusset deve ser maior que zero.")
    previous = intent_from_data(node_key, configured or default_intent(node_key))
    thickness = float(edited.get("gusset", {}).get("plate_thickness", 0.))
    if (edited.get("form") == "Gusset" and thickness > 0.
            and abs(thickness-previous.gusset.plate_thickness) > 1e-9):
        return thickness
    return float(current_default)


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


def _topology_identity(candidate):
    """Identity of connectivity only; ordinary dimensional edits are excluded."""
    return (
        tuple(sorted((node.key, tuple(node.affiliations), node.classification)
                     for node in candidate.graph.nodes)),
        tuple(sorted((edge.key, edge.start_node_key, edge.end_node_key,
                      edge.role, edge.chord_affiliation)
                     for edge in candidate.graph.edges)),
    )


def _participant_identity(candidate, node_key):
    """Stable semantic membership at a NodeKey, never a coordinate match."""
    return tuple(sorted(
        (participant.role, participant.end,
         tuple(sorted(participant.physical_run_keys)))
        for participant in connection_participants(candidate, node_key)))


def reconcile_topology_connection_intents(candidate, applied):
    """Reconcile surviving semantic nodes, selection and fit policy separately.

    Coordinates never establish identity. A shared node and affiliation plus
    incident connectivity establish continuity even when physical runs change.
    Ordinary dimensional edits retain their configuration unchanged.
    """
    configured = candidate.config.get("connection_intents", {}) or {}
    if applied is None or _topology_identity(candidate) == _topology_identity(applied):
        return configured
    accepted = applied.config.get("connection_intents", {}) or {}
    new_nodes = {node.key for node in candidate.graph.nodes}
    old_nodes = {node.key for node in applied.graph.nodes}
    result = {}
    for node_key, value in configured.items():
        if node_key not in new_nodes:
            continue
        # An intent created after the topology edit belongs to the candidate,
        # not to the accepted topology, so it is validated by normal resolution.
        if node_key not in accepted:
            result[node_key] = value
            continue
        if node_key not in old_nodes:
            continue
        old_node, new_node = applied.graph.node(node_key), candidate.graph.node(node_key)
        def incident(graph):
            return {(edge.role, edge.chord_affiliation,
                     edge.end_node_key if edge.start_node_key == node_key
                     else edge.start_node_key)
                    for edge in graph.edges
                    if node_key in (edge.start_node_key, edge.end_node_key)}
        shared_participants = set(_participant_identity(applied, node_key)).intersection(
            _participant_identity(candidate, node_key))
        if (set(old_node.affiliations) != set(new_node.affiliations)
                or not (shared_participants
                        or incident(applied.graph).intersection(incident(candidate.graph)))):
            continue
        participants = connection_participants(candidate, node_key)
        intent = intent_from_data(node_key, value)
        if (intent.form == ConnectionForm.DIRECT
                and intent.direct_policy == DirectFitPolicy.PRIORITY
                and not intent.priority_run_key
                and intent.priority_member != PriorityMember.AUTOMATIC):
            previous = resolve_connection(intent, connection_participants(applied, node_key),
                                          old_node.position_local, (0., 0., 1.))
            targets = {d.target_run_key for d in previous.directives if d.target_run_key}
            if len(targets) == 1:
                intent = replace(intent, priority_run_key=targets.pop())
            else:
                intent = replace(intent, direct_policy=DirectFitPolicy.INDEPENDENT,
                                 priority_member=PriorityMember.AUTOMATIC)
        available = {key for p in participants for key in p.physical_run_keys}
        priority_uses_node = (intent.form == ConnectionForm.DIRECT
                             and intent.direct_policy == DirectFitPolicy.PRIORITY
                             and (intent.priority_run_key
                                  or intent.priority_member == PriorityMember.AUTOMATIC))
        if intent.participant_run_keys:
            remaining = tuple(key for key in intent.participant_run_keys if key in available)
            # Empty means "all" in the resolver, not an empty explicit selection.
            if not remaining and not priority_uses_node:
                continue
            intent = replace(intent, participant_run_keys=remaining)
        selected = tuple(p for p in participants if priority_uses_node or not intent.participant_run_keys
                         or set(p.physical_run_keys).intersection(intent.participant_run_keys))
        if len(selected) < 2:
            continue
        if intent.form == ConnectionForm.DIRECT:
            # Resolve against the actual candidate; count, section equivalence,
            # through members and primary eligibility are policy-specific.
            resolution = resolve_connection(intent, participants, new_node.position_local,
                                            (0., 0., 1.))
            if resolution.diagnostics:
                intent = replace(intent, direct_policy=DirectFitPolicy.INDEPENDENT,
                                 priority_member=PriorityMember.AUTOMATIC,
                                 priority_run_key="")
        result[node_key] = intent_data(intent)
    return result


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


def _gusset_reserved_interval(plane):
    if plane.side == GussetSide.CENTER:
        return (-plane.plate_thickness/2.-plane.normal_clearance,
                plane.plate_thickness/2.+plane.normal_clearance)
    if plane.side == GussetSide.FACE_A:
        return (-plane.normal_clearance, plane.plate_thickness+plane.normal_clearance)
    return (-plane.plate_thickness-plane.normal_clearance, plane.normal_clearance)


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
    reserved = _gusset_reserved_interval(plane)
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
            if low+shift < reserved[1]-1e-7 and high+shift > reserved[0]+1e-7:
                diagnostics.append(ConnectionDiagnostic(
                    "GUSSET_CENTER_SPACE_INVALID", "Warning",
                    "Atenção: participante interfere no espaço reservado da chapa."))
    return tuple(dict.fromkeys(diagnostics))
