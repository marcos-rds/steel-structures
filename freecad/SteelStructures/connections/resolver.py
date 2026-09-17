"""Pure participant and connection-geometry resolution."""

import math

from .models import (ConnectionDiagnostic, ConnectionFitDirective, ConnectionForm,
                     ConnectionParticipant, EndParticipant, ThroughParticipant,
                     ChordBreakParticipant, ChordClosureParticipant,
                     ChordJointParticipant, ConnectionResolution, DirectFitPolicy,
                     GussetSide, GussetPlane, PriorityMember)
from .validation import validate_intent


TOLERANCE = 1e-7
CHORD_ROLES = frozenset(("TOP_CHORD", "BOTTOM_CHORD"))
WEB_ROLES = frozenset(("DIAGONAL", "VERTICAL", "END_POST"))
ROLE_PRIORITY = {"TOP_CHORD": 100, "BOTTOM_CHORD": 100,
                 "VERTICAL": 30, "END_POST": 20, "DIAGONAL": 10}


def _sub(a, b):
    return tuple(x-y for x, y in zip(a, b))


def _dot(a, b):
    return sum(x*y for x, y in zip(a, b))


def _unit(value):
    length = math.sqrt(_dot(value, value))
    return None if length <= TOLERANCE else tuple(component/length for component in value)


def _canonical(value):
    result = _unit(value)
    if result is None:
        return None
    first = next((component for component in result if abs(component) > TOLERANCE), 1.)
    return tuple(-component for component in result) if first < 0 else result


def resolve_connection_participants(node, topology, runs, run_data=None):
    """Return stable logical run participants for one declared topology node."""
    run_data = run_data or {}
    incident_edges = set(topology.incidence.get(node.key, ()))
    participants = []
    for run in runs:
        if not incident_edges.intersection(run.edge_keys):
            continue
        if node.key == run.start_node_key:
            end = "Start"
        elif node.key == run.end_node_key:
            end = "End"
        else:
            end = "Through"
        start = topology.node(run.start_node_key).position_local
        finish = topology.node(run.end_node_key).position_local
        data = run_data.get(run.key, {})
        participants.append((ThroughParticipant if end == "Through" else EndParticipant)(
            participant_key=f"{node.key}:{run.key}", node_key=node.key,
            run_key=run.key, role=run.role, end=end, axis=(tuple(start), tuple(finish)),
            assembly=data.get("assembly", "Single"),
            component_keys=tuple(data.get("component_keys", ())),
            geometry_key=data.get("geometry_key", ""), continuous_through=end == "Through"))
    # Pair only unambiguous, opposed endpoints of identical physical sections.
    # Incidence is determined by NodeKey, never by a coordinate lookup.
    def compatible(a, b):
        if a.end == "Through" or b.end == "Through":
            return False
        if (a.role, a.assembly, a.geometry_key) != (b.role, b.assembly, b.geometry_key):
            return False
        if run_data.get(a.run_key, {}).get("continuity_key") != run_data.get(b.run_key, {}).get("continuity_key"):
            return False
        da, db = _inward(a), _inward(b)
        return da is not None and db is not None and math.sqrt(sum(
            (x+y)**2 for x,y in zip(da,db))) <= TOLERANCE

    partners = {p.run_key: [q for q in participants if q != p and compatible(p,q)]
                for p in participants}
    result, used = [], set()
    for p in sorted(participants, key=lambda p: p.run_key):
        if p.run_key in used:
            continue
        matches = partners[p.run_key]
        if len(matches) == 1 and len(partners[matches[0].run_key]) == 1:
            q = matches[0]
            pair = sorted((p,q), key=lambda p: p.run_key)
            keys = tuple(p.run_key for p in pair)
            outer = lambda p: p.axis[1] if p.end == "Start" else p.axis[0]
            result.append(ThroughParticipant(
                participant_key=f"{node.key}:through:"+"|".join(keys),
                node_key=node.key, run_key=keys[0], role=p.role, end="Through",
                axis=(outer(pair[0]),outer(pair[1])), assembly=p.assembly,
                component_keys=tuple(k for p in pair for k in p.component_keys),
                geometry_key=p.geometry_key, continuous_through=True,
                run_keys=keys, run_ends=tuple((p.run_key,p.end) for p in pair)))
            used.update(keys)
        else:
            result.append(p)
    for role in sorted(CHORD_ROLES):
        branches = tuple(p for p in result if p.role == role)
        if len(branches) != 2 or any(p.end == "Through" for p in branches):
            continue
        directions = tuple(_inward(p) for p in branches)
        if any(d is None for d in directions) or abs(_dot(*directions)) >= 1.-TOLERANCE:
            continue
        keys = tuple(p.run_key for p in branches)
        result = [p for p in result if p not in branches]
        result.append(ChordBreakParticipant(
            participant_key=f"{node.key}:chord-break:"+"|".join(keys),
            node_key=node.key, run_key=keys[0], role=role, end="ChordBreak",
            axis=branches[0].axis, assembly=branches[0].assembly,
            run_keys=keys, run_ends=tuple((p.run_key,p.end) for p in branches),
            branches=branches))
    return tuple(sorted(result, key=lambda p: p.run_key))


def resolve_chord_joints(node, topology, runs, run_data=None):
    """Return physical chord joints without changing the public node participants."""
    participants = resolve_connection_participants(node, topology, runs, run_data)
    existing = tuple(p for p in participants if isinstance(p, ChordJointParticipant))
    if existing:
        return existing
    chords = tuple(p for p in participants if p.role in CHORD_ROLES)
    if (len(chords) != 2 or {p.role for p in chords} != CHORD_ROLES
            or any(not isinstance(p, EndParticipant) or p.end == "Through" for p in chords)):
        return ()
    directions = tuple(_inward(p) for p in chords)
    if (any(direction is None for direction in directions)
            or abs(_dot(*directions)) >= 1.-TOLERANCE):
        raise ValueError(
            "Encontro terminal de banzos degenerado; Ãºltimo estado vÃ¡lido preservado.")
    keys = tuple(p.run_key for p in chords)
    return (ChordClosureParticipant(
        participant_key=f"{node.key}:chord-closure:"+"|".join(keys),
        node_key=node.key, run_key=keys[0], role="CHORD_JOINT",
        end="ChordClosure", axis=chords[0].axis,
        assembly="Joint", run_keys=keys,
        run_ends=tuple((p.run_key,p.end) for p in chords),
        branches=chords),)


def chord_joint_plane(participant):
    """Common bisector plane in the topology frame for two incident chords."""
    branches = participant.branches
    if len(branches) != 2:
        raise ValueError("Encontro de banzos requer exatamente dois ramos fÃ­sicos.")
    if (isinstance(participant, ChordBreakParticipant)
            and (branches[0].geometry_key, branches[0].assembly) != (
                branches[1].geometry_key, branches[1].assembly)):
        raise ValueError("Quebra de banzo com seções ou transformações incompatíveis; estado anterior preservado.")
    normal = _canonical(_sub(_inward(branches[0]), _inward(branches[1])))
    if normal is None:
        raise ValueError("Não foi possível resolver o plano da quebra de banzo.")
    return normal


def chord_break_plane(participant):
    """Backward-compatible name for the generic chord-joint plane resolver."""
    if not isinstance(participant, ChordJointParticipant):
        raise ValueError("Participante nÃ£o representa encontro fÃ­sico de banzos.")
    return chord_joint_plane(participant)


def _selected(intent, participants):
    by_key = {key: participant for participant in participants for key in participant.physical_run_keys}
    if not intent.participant_run_keys:
        return tuple(participants), ()
    missing = [key for key in intent.participant_run_keys if key not in by_key]
    if missing:
        return (), (ConnectionDiagnostic(
            "MISSING_PARTICIPANT", "Warning",
            "Um participante configurado não pertence mais ao nó; ligação adicional não aplicada."),)
    return tuple(dict.fromkeys(by_key[key] for key in intent.participant_run_keys)), ()


def _inward(participant):
    start, end = participant.axis
    if participant.end == "Start":
        return _unit(_sub(end, start))
    if participant.end == "End":
        return _unit(_sub(start, end))
    return None


def priority_participants(participants):
    """Eligible node members, shared by core resolution and normal UI."""
    webs = tuple(p for p in participants if p.role in WEB_ROLES)
    return webs if len(webs) >= 2 else tuple(participants)


def priority_options(participants):
    eligible = priority_participants(participants)
    through = tuple(p for p in eligible if p.end == "Through")
    return through if len(through) == 1 else eligible


def _balanced(intent, participants, node_position, truss_plane_normal):
    if any(p.role in WEB_ROLES and p.end == "Through" for p in participants):
        return (), (ConnectionDiagnostic(
            "BALANCED_MITER_WITH_THROUGH_UNSUPPORTED", "Warning",
            "Meia-esquadria com participante passante da alma não é suportada; use Prioridade."),)
    webs = tuple(item for item in participants if item.role in WEB_ROLES and item.end != "Through")
    if len(webs) != 2:
        return (), (ConnectionDiagnostic(
            "BALANCED_MITER_REQUIRES_TWO_WEBS", "Warning",
            "Meia-esquadria equilibrada requer exatamente duas barras da alma equivalentes."),)
    if webs[0].geometry_key != webs[1].geometry_key:
        return (), (ConnectionDiagnostic(
            "BALANCED_MITER_GEOMETRY_MISMATCH", "Warning",
            "Meia-esquadria equilibrada requer exatamente duas barras da alma equivalentes."),)
    directions = tuple(_inward(item) for item in webs)
    if any(direction is None for direction in directions) or any(
            abs(_dot(direction, truss_plane_normal)) > TOLERANCE for direction in directions):
        return (), (ConnectionDiagnostic(
            "BALANCED_MITER_INVALID_AXES", "Warning",
            "Participantes degenerados ou não coplanares; mantido encontro independente."),)
    normal = _canonical(_sub(directions[0], directions[1]))
    if normal is None or any(abs(_dot(direction, normal)) <= TOLERANCE for direction in directions):
        return (), (ConnectionDiagnostic(
            "BALANCED_MITER_DEGENERATE", "Warning",
            "Não foi possível resolver um plano equilibrado estável; mantido encontro independente."),)
    directives = tuple(ConnectionFitDirective(
        item.run_key, item.end, "PlaneCut", intent.intent_key,
        plane_origin=tuple(node_position), plane_normal=normal) for item in webs)
    return directives, ()


def _priority(intent, participants):
    eligible = priority_participants(participants)
    if len(eligible) < 2:
        return (), (ConnectionDiagnostic(
            "PRIORITY_REQUIRES_PARTICIPANTS", "Warning",
            "Ligação por prioridade requer ao menos dois participantes; mantido encontro independente."),)
    if intent.priority_run_key:
        primary = next((p for p in eligible if intent.priority_run_key in p.physical_run_keys), None)
        if primary is None:
            return (), (ConnectionDiagnostic("PRIORITY_PARTICIPANT_MISSING", "Warning",
                "Participante prioritário não está disponível; mantido encontro independente."),)
    elif intent.priority_member == PriorityMember.AUTOMATIC:
        through = [p for p in eligible if p.end == "Through"]
        verticals = [p for p in eligible if p.role == "VERTICAL"]
        pool = verticals if len(verticals) == 1 else [p for p in eligible if p.role == "DIAGONAL"]
        pool = through if len(through) == 1 else pool
        primary = min(pool or eligible, key=lambda item: (
            (_inward(item) or (0., 0., 0.))[0], item.run_key))
    else:
        index = 0 if intent.priority_member == PriorityMember.PARTICIPANT_A else 1
        legacy = [p for key in intent.participant_run_keys for p in eligible if p.run_key == key] or eligible
        if len(legacy) <= index:
            return (), (ConnectionDiagnostic(
                "PRIORITY_PARTICIPANT_MISSING", "Warning",
                "Participante prioritário não está disponível; mantido encontro independente."),)
        primary = legacy[index]
    directives = tuple(ConnectionFitDirective(
        item.run_key, item.end, "FitToParticipant", intent.intent_key,
        target_run_key=primary.run_key, target_run_keys=primary.physical_run_keys)
        for item in sorted(eligible, key=lambda p: p.run_key)
        if item.run_key != primary.run_key and item.role in WEB_ROLES and item.end != "Through")
    return directives, ()


def resolve_connection(intent, participants, node_position, truss_plane_normal):
    """Resolve semantic intent to pure fitting directives, never document objects."""
    validate_intent(intent)
    if (intent.form == ConnectionForm.DIRECT and intent.direct_policy == DirectFitPolicy.PRIORITY
            and (intent.priority_run_key or intent.priority_member == PriorityMember.AUTOMATIC)):
        # Legacy UI snapshots listed only A/B. They do not limit today's node
        # membership; the explicit primary (if any) is validated by _priority.
        selected, diagnostics = tuple(participants), ()
    else:
        selected, diagnostics = _selected(intent, participants)
    if diagnostics:
        return ConnectionResolution(intent, tuple(participants), diagnostics=diagnostics)
    if intent.form == ConnectionForm.GEOMETRIC_ONLY:
        return ConnectionResolution(intent, tuple(participants))
    if intent.form == ConnectionForm.DIRECT:
        if intent.direct_policy == DirectFitPolicy.INDEPENDENT:
            directives, extra = (), ()
        elif intent.direct_policy == DirectFitPolicy.BALANCED_MITER:
            directives, extra = _balanced(intent, participants, node_position, truss_plane_normal)
        else:
            directives, extra = _priority(intent, participants)
        return ConnectionResolution(intent, tuple(participants), directives,
                                    tuple(diagnostics)+tuple(extra))
    if intent.gusset.side != GussetSide.CENTER:
        return ConnectionResolution(intent, tuple(participants), diagnostics=(ConnectionDiagnostic(
            "GUSSET_SIDE_NOT_IMPLEMENTED", "Warning",
            "Somente Gusset Center está implementado nesta etapa; último fitting válido preservado."),))
    directives = tuple(ConnectionFitDirective(
        item.run_key, item.end, "GussetSetback", intent.intent_key,
        reference_offset=intent.gusset.axial_clearance)
        for item in selected if item.role in WEB_ROLES and item.end != "Through")
    normal = _unit(truss_plane_normal)
    if normal is None:
        return ConnectionResolution(intent, tuple(participants), diagnostics=(ConnectionDiagnostic(
            "GUSSET_PLANE_INVALID", "Warning", "O plano central da chapa é degenerado."),))
    return ConnectionResolution(intent, tuple(participants), directives, gusset_plane=GussetPlane(
        tuple(node_position), normal, intent.gusset.plate_thickness, intent.gusset.normal_clearance))
