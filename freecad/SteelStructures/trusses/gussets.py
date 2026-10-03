"""Bridge from nominal truss semantics to pure preliminary gusset outlines."""

import json
import math
from dataclasses import replace

from ..assemblies.attachment import support
from ..assemblies.serialization import loads as assembly_loads
from ..connections import (ConnectionDiagnostic, ConnectionForm, GussetCorridor,
                           GussetPlateFrame, GussetPlateSpec, GussetSupportLine,
                           build_gusset_outline, resolve_gusset_attachment)
from ..connections.slots import (contact_band_support, derive_surface_band_slots,
                                 derive_open_recess_slots, recess_is_open)
from ..connections.models import GussetAttachmentSlotKind
from ..connections.gusset_families import apply_approved_family
from .assemblies import assembly_frame
from .connections import resolve_truss_connections
from .fitting_geometry import _section_at_insertion
from .gusset_attachment import attachment_slot_geometry
from .realization import reference_frame, transform_point

TOLERANCE = 1e-7
CHORD_ROLES = frozenset(("TOP_CHORD", "BOTTOM_CHORD"))
MAX_WEB_CAP_EXTRA_MARGIN_FACTOR = 1.


def _dot(a, b):
    return sum(x*y for x, y in zip(a, b))


def _unit2(value):
    length = math.hypot(*value)
    if length <= TOLERANCE:
        raise ValueError("Direção nula em participante da chapa.")
    return value[0]/length, value[1]/length


def _selected_participants(intent, participants):
    if not intent.participant_run_keys:
        return tuple(participants)
    requested = set(intent.participant_run_keys)
    return tuple(participant for participant in participants
                 if requested.intersection(participant.physical_run_keys))


def _component_translation(item):
    if item.spec.assembly == "Single" or not item.spec.assembly_spec:
        return 0., 0.
    assembly = assembly_loads(json.dumps(item.spec.assembly_spec))
    component = next((value for value in assembly.components
                      if value.component_key == item.component_key), None)
    if component is None:
        raise ValueError("Componente da composição não está disponível.")
    return component.transverse_translation


def _run_directions(candidate, run, node_key):
    node = candidate.graph.node(node_key).position_local
    values = []
    for other_key in (run.start_node_key, run.end_node_key):
        if other_key == node_key:
            continue
        other = candidate.graph.node(other_key).position_local
        values.append(_unit2((other[0]-node[0], other[1]-node[1])))
    if node_key not in (run.start_node_key, run.end_node_key):
        start = candidate.graph.node(run.start_node_key).position_local
        end = candidate.graph.node(run.end_node_key).position_local
        values = [_unit2((start[0]-node[0], start[1]-node[1])),
                  _unit2((end[0]-node[0], end[1]-node[1]))]
    return tuple(dict.fromkeys(values))


def _corridors(candidate, participant, run, local_frame):
    origin, axis_x, axis_y, _normal = local_frame
    node = candidate.graph.node(participant.node_key).position_local
    node_global = transform_point(node, local_frame)
    start = transform_point(candidate.graph.node(run.start_node_key).position_local, local_frame)
    end = transform_point(candidate.graph.node(run.end_node_key).position_local, local_frame)
    items = [item for item in candidate.items
             if item.run_key == run.key and item.element_kind == "Component"]
    if not items:
        raise ValueError("SectionGeometry indisponível para participante da chapa.")
    result = []
    for direction in _run_directions(candidate, run, participant.node_key):
        perpendicular = (-direction[1], direction[0])
        perpendicular_global = tuple(perpendicular[0]*axis_x[index]+perpendicular[1]*axis_y[index]
                                     for index in range(3))
        for item in sorted(items, key=lambda value: value.component_key):
            member_frame = assembly_frame((start, end), item.section_u_global,
                                          item.spec.rotation)
            section, insertion = _section_at_insertion(item)
            projected = (_dot(perpendicular_global, member_frame.u),
                         _dot(perpendicular_global, member_frame.v))
            if math.hypot(*projected) <= TOLERANCE:
                raise ValueError("A seção não possui envelope projetável no plano da chapa.")
            low, high = support(section, projected)
            insertion_shift = insertion[0]*projected[0]+insertion[1]*projected[1]
            dx, dy = _component_translation(item)
            axis_shift = tuple(dx*u+dy*v for u, v in zip(member_frame.u, member_frame.v))
            center = _dot(tuple(value-base for value, base in zip(
                tuple(node_global[i]+axis_shift[i] for i in range(3)), node_global)),
                perpendicular_global)
            result.append(GussetCorridor(
                participant.participant_key, f"{run.key}:{item.component_key}", direction,
                center+low+insertion_shift, center+high+insertion_shift))
    return tuple(result)


def _chord_support_lines(participants, corridors, materials=(), attachment=None,
                         chord_contact="Auto", frame=None):
    """Derive chord limits at the material boundary occupying the plate slab.

    The useful/internal side is selected from incident web directions.  At a
    terminal containing only chords, the other chord provides the reference.
    Each returned half-plane keeps the full transformed chord envelope but
    prevents free EdgeMargin from growing beyond its external face.
    """
    roles = {participant.participant_key: participant.role for participant in participants}
    unique_directions = {}
    for corridor in corridors:
        direction = _unit2(corridor.direction)
        key = (corridor.participant_key, round(direction[0], 9), round(direction[1], 9))
        unique_directions[key] = direction
    web_references = tuple(direction for (key, _x, _y), direction in unique_directions.items()
                           if roles.get(key) not in CHORD_ROLES)
    selected_candidate = None
    if attachment is not None:
        selected_candidate = next((value for value in attachment.candidates
                                   if value.slot_id == attachment.governing_slot_id
                                   and value.placement == attachment.placement_kind
                                   and value.slot_id), None)
    candidates = []
    for corridor in corridors:
        if roles.get(corridor.participant_key) not in CHORD_ROLES:
            continue
        direction = _unit2(corridor.direction)
        perpendicular = (-direction[1], direction[0])
        references = web_references or tuple(
            other for (key, _x, _y), other in unique_directions.items()
            if key != corridor.participant_key)
        projections = [sum(a*b for a, b in zip(reference, perpendicular))
                       for reference in references]
        nonzero = [value for value in projections if abs(value) > TOLERANCE]
        if not nonzero:
            raise ValueError("Não foi possível identificar o lado interno do banzo para a chapa.")
        if any(value > 0. for value in nonzero) and any(value < 0. for value in nonzero):
            raise ValueError("Participantes ocupam ambos os lados do banzo; limite externo ambíguo.")
        score = sum(nonzero)
        inward = (perpendicular if score > 0. else
                  (-perpendicular[0], -perpendicular[1]))
        use_band = attachment is not None and frame is not None and materials
        if use_band:
            axis_global = tuple(inward[0]*frame[1][i]+inward[1]*frame[2][i]
                                for i in range(3))
            participant_materials = tuple(value for value in materials
                                          if value.participant_key == corridor.participant_key)
            if (selected_candidate is not None
                    and selected_candidate.governing_participant_key
                    == corridor.participant_key
                    and selected_candidate.contact_band is not None):
                # The resolved physical candidate owns both C6-L bands.
                # Selection provenance must never change its plate outline.
                offsets = [selected_candidate.outline_band
                           if selected_candidate.outline_band is not None
                           else selected_candidate.contact_band]
            else:
                offsets = []
                for material in participant_materials:
                    sign = 1 if _dot(axis_global, material.local_axis) >= 0. else -1
                    support = contact_band_support(
                        (material,), attachment.plate_low, attachment.plate_high,
                        sign, include_tangent=(
                            attachment.kind == "AssemblyMidPlane"
                            or (attachment.kind == "PhysicalSurface"
                                and attachment.governing_surface_class is not None
                                and attachment.governing_surface_class.value
                                == "Outer")))
                    if support is not None:
                        offsets.append(support)
            exterior = str(getattr(chord_contact, "value", chord_contact)) == "TrussExterior"
            if not offsets:
                # A placement governed by another participant can be outside
                # this chord's transverse material.  Its residual reports the
                # missing contact; keep the historical geometric envelope.
                normal = (-inward[0], -inward[1])
                offset = (-corridor.transverse_low if score > 0.
                          else corridor.transverse_high)
            elif exterior:
                # The outer face is the opposite extremum of the same band.
                outer_offsets = []
                for material in participant_materials:
                    sign = -1 if _dot(axis_global, material.local_axis) >= 0. else 1
                    support = contact_band_support((material,), attachment.plate_low,
                                                   attachment.plate_high, sign)
                    if support is not None:
                        outer_offsets.append(-support)
                normal, offset = inward, min(outer_offsets)-.01
            else:
                normal = (-inward[0], -inward[1])
                offset = -max(offsets)-.01
        elif score > 0.:
            normal = (-perpendicular[0], -perpendicular[1])
            offset = -corridor.transverse_low
        else:
            normal = perpendicular
            offset = corridor.transverse_high
        canonical_direction = direction
        if (canonical_direction[0] < -TOLERANCE
                or (abs(canonical_direction[0]) <= TOLERANCE
                    and canonical_direction[1] < 0.)):
            canonical_direction = (-canonical_direction[0], -canonical_direction[1])
        candidates.append((corridor.participant_key, canonical_direction, normal, offset))
    grouped = []
    for participant_key, direction, normal, offset in sorted(candidates):
        existing = next((value for value in grouped
                         if value[0] == participant_key
                         and sum(a*b for a, b in zip(value[2], normal)) >= 1.-TOLERANCE), None)
        if existing is None:
            grouped.append([participant_key, direction, normal, offset])
        else:
            # Multiple transformed assembly components govern by their
            # outermost physical support, never by a profile-family special case.
            existing[3] = (min(existing[3], offset) if attachment is not None
                           and materials else max(existing[3], offset))
    return tuple(GussetSupportLine(key, direction, normal, offset, "CHORD_BOUNDARY")
                 for key, direction, normal, offset in grouped)


def _accessible_recess_slots(participants, corridors, slots, materials, frame,
                             plate_thickness=0.):
    """Keep accessible recesses and add the web-facing chord surface band."""
    inward = {}
    for support_line in _chord_support_lines(participants, corridors):
        inward[support_line.participant_key] = tuple(
            -support_line.normal[0]*frame[1][i]
            -support_line.normal[1]*frame[2][i] for i in range(3))
    result = []
    for slot in slots:
        if (slot.kind == GussetAttachmentSlotKind.OPEN_RECESS
                and slot.participant_key in inward):
            projection = _dot(inward[slot.participant_key], slot.local_axis)
            if abs(projection) < 1.-1e-6:
                continue
            sign = 1 if projection > 0. else -1
            if slot.access_sign:
                if slot.access_sign != sign:
                    continue
            else:
                participant_materials = tuple(value for value in materials
                                              if value.participant_key == slot.participant_key)
                if (slot.free_low is None or slot.free_high is None
                        or not recess_is_open(participant_materials,
                                              slot.free_low, slot.free_high, sign)):
                    continue
                slot = replace(slot, open_accessibility=True, access_sign=sign)
        if slot.participant_key in inward:
            participant_material = next((value for value in materials
                                         if value.participant_key
                                         == slot.participant_key), None)
            if participant_material is not None:
                projection = _dot(inward[slot.participant_key],
                                  participant_material.local_axis)
                if abs(projection) > TOLERANCE:
                    slot = replace(slot, access_sign=(1 if projection > 0. else -1))
        result.append(slot)
    chord_keys = {value.participant_key for value in participants
                  if value.role in CHORD_ROLES}
    for participant_key in sorted(chord_keys.intersection(inward)):
        participant_materials = tuple(
            value for value in materials
            if value.participant_key == participant_key)
        if not participant_materials:
            continue
        projection = _dot(inward[participant_key],
                          participant_materials[0].local_axis)
        if abs(projection) <= TOLERANCE:
            continue
        if not any(slot.participant_key == participant_key
                   and slot.kind == GussetAttachmentSlotKind.OPEN_RECESS
                   for slot in result):
            result.extend(derive_open_recess_slots(
                participant_key, tuple(frame[3]), participant_materials,
                1 if projection > 0. else -1, plate_thickness))
        surface_bands = derive_surface_band_slots(
            participant_key, tuple(frame[3]), participant_materials,
            1 if projection > 0. else -1)
        result.extend(surface_bands)
    return tuple(result)


def _web_end_lines(participants, corridors, spec):
    """Return one meaningful transverse termination for each ending web.

    A cap is retained only when its half-plane preserves every participant's
    required overlap.  Through participants deliberately receive no terminal
    cap: they remain one continuous semantic participant at K nodes.
    """
    participant_by_key = {value.participant_key: value for value in participants}
    required = []
    for corridor in corridors:
        dx, dy = _unit2(corridor.direction)
        px, py = -dy, dx
        required.extend((spec.member_overlap*dx+corridor.transverse_low*px,
                         spec.member_overlap*dy+corridor.transverse_low*py))
        required.extend((spec.member_overlap*dx+corridor.transverse_high*px,
                         spec.member_overlap*dy+corridor.transverse_high*py))
    # Convert the flat list above to points without introducing a second
    # geometry representation.
    required_points = tuple(zip(required[::2], required[1::2]))
    terminal_keys = {value.participant_key for value in participants
                     if value.role not in CHORD_ROLES and value.end != "Through"}
    result, seen = [], set()
    for corridor in corridors:
        participant = participant_by_key.get(corridor.participant_key)
        if (participant is None or participant.role in CHORD_ROLES
                or participant.end == "Through"):
            continue
        direction = _unit2(corridor.direction)
        key = (participant.participant_key, round(direction[0], 9),
               round(direction[1], 9))
        if key in seen:
            continue
        seen.add(key)
        # MemberOverlap+EdgeMargin is the preferred terminal station.  For a
        # very wide crossing participant, move the cap only as far as required
        # to preserve every overlap corner.  This keeps one active semantic cap
        # without forcing a fragile concave boolean reconstruction.
        # A remote web corner is part of the required region too.  Preserve
        # its configured free margin, rather than merely keeping the bare
        # MemberOverlap corner inside this cap half-plane.  The former form
        # could shave a narrow wedge from asymmetric multi-web nodes.
        offset = max(spec.member_overlap+spec.edge_margin,
                     max(direction[0]*point[0]+direction[1]*point[1]
                         for point in required_points)+spec.edge_margin)
        max_offset = (spec.member_overlap+spec.edge_margin
                      +MAX_WEB_CAP_EXTRA_MARGIN_FACTOR*spec.edge_margin)
        if len(terminal_keys) == 2 and offset > max_offset+TOLERANCE:
            # A remote participant would force a long artificial cap.  Leave
            # that sector to its local corridor supports instead.
            continue
        result.append(GussetSupportLine(
            participant.participant_key, (-direction[1], direction[0]),
            direction, offset, "WEB_END_CAP"))
    return tuple(sorted(result, key=lambda value: (
        value.participant_key, value.normal, value.offset)))


def _web_side_lines(participants, corridors, spec):
    """Bound one/two ending webs by their compact physical outer sides.

    A through chord contributes two opposite axial corridors.  Letting those
    corridors alone build a convex k-DOP can collapse one side of the web cap
    into the remote chord corner.  The local cross-sections at the node define
    the useful width; EdgeMargin then supplies the two free lateral borders.
    """
    participant_by_key = {value.participant_key: value for value in participants}
    webs = [value for value in participants
            if value.role not in CHORD_ROLES and value.end != "Through"]
    if not webs or any(
            value.role not in CHORD_ROLES and value.end == "Through"
            for value in participants):
        return ()
    by_key = {value.participant_key: [] for value in webs}
    for corridor in corridors:
        if corridor.participant_key in by_key:
            by_key[corridor.participant_key].append(corridor)
    if any(not values for values in by_key.values()):
        return ()
    if len(webs) == 1:
        direction = _unit2(by_key[webs[0].participant_key][0].direction)
        lateral = (-direction[1], direction[0])
        node_points = []
        for corridor in corridors:
            dx, dy = _unit2(corridor.direction)
            px, py = -dy, dx
            for transverse in (corridor.transverse_low, corridor.transverse_high):
                node_points.append((transverse*px, transverse*py))
        high = max(_dot(lateral, point) for point in node_points)+spec.edge_margin
        low = min(_dot(lateral, point) for point in node_points)-spec.edge_margin
        return (GussetSupportLine(webs[0].participant_key, direction,
                                  lateral, high, "FREE_MARGIN"),
                GussetSupportLine(webs[0].participant_key, direction,
                                  (-lateral[0], -lateral[1]), -low,
                                  "FREE_MARGIN"))

    # Two ending webs own one exposed lateral border each.  A larger web fan
    # deliberately keeps the compact cap envelope established before C6-N:
    # adding the same two side supports there turns the approved four-corner
    # diagonal/vertical/diagonal plate into an unnecessary six-corner plate.
    ordered = sorted(webs, key=lambda value: (
        math.atan2(*reversed(_unit2(by_key[value.participant_key][0].direction))),
        value.participant_key))
    if len(ordered) > 2:
        return ()
    exposed = ((ordered[0], ordered[1]),
               (ordered[1], ordered[0]))

    result = []
    for web, other in exposed:
        values = by_key[web.participant_key]
        direction = _unit2(values[0].direction)
        other_direction = _unit2(by_key[other.participant_key][0].direction)
        lateral = (-direction[1], direction[0])
        # The other web identifies the sector interior.  The retained support
        # is the opposite, exterior side of this web's real corridor.
        if _dot(lateral, other_direction) > 0.:
            lateral = (-lateral[0], -lateral[1])
        node_points = []
        for corridor in values:
            current_direction = _unit2(corridor.direction)
            perpendicular = (-current_direction[1], current_direction[0])
            for transverse in (corridor.transverse_low, corridor.transverse_high):
                node_points.append((transverse*perpendicular[0],
                                    transverse*perpendicular[1]))
        offset = max(_dot(lateral, point) for point in node_points)+spec.edge_margin
        result.append(GussetSupportLine(web.participant_key, direction,
                                        lateral, offset, "FREE_MARGIN"))
    return tuple(result)


def _web_sector_bridge_lines(participants, corridors, spec):
    """Return the minimum valid bridge between adjacent terminal-web caps.

    The semantic operation is based on the exposed sector, not on role names:
    diagonal/diagonal, diagonal/vertical and vertical/diagonal use the same
    geometry.  Through webs are semantic boundaries and split the sector.
    """
    participant_by_key = {value.participant_key: value for value in participants}
    terminal = {}
    through = set()
    chord_directions = []
    for corridor in corridors:
        participant = participant_by_key.get(corridor.participant_key)
        if participant is None:
            continue
        direction = _unit2(corridor.direction)
        if participant.role in CHORD_ROLES:
            chord_directions.append(direction)
        elif participant.end == "Through":
            through.add(participant.participant_key)
        else:
            terminal.setdefault(participant.participant_key, direction)
    if len(terminal) != 2 or through or not chord_directions:
        return ()
    directions = tuple(terminal[key] for key in sorted(terminal))
    required = []
    for corridor in corridors:
        if corridor.participant_key not in terminal:
            continue
        direction = _unit2(corridor.direction)
        perpendicular = (-direction[1], direction[0])
        for transverse in (corridor.transverse_low, corridor.transverse_high):
            required.append((spec.member_overlap*direction[0]
                             +transverse*perpendicular[0],
                             spec.member_overlap*direction[1]
                             +transverse*perpendicular[1]))
    chord_break = any(value.role in CHORD_ROLES and value.end == "ChordBreak"
                      for value in participants)
    mean = (directions[0][0]+directions[1][0],
            directions[0][1]+directions[1][1])
    # At a real ridge without a central web, the two ending diagonals can
    # otherwise meet in a needless point.  Their inward bisector supplies a
    # straight lower fabrication edge while retaining overlap+EdgeMargin.
    if (chord_break and math.hypot(*mean) > TOLERANCE
            and _dot(directions[0], directions[1]) < .5):
        normal = _unit2(mean)
        offset = max(_dot(normal, point) for point in required)+spec.edge_margin
        return (GussetSupportLine(
            "|".join(sorted(terminal)), (-normal[1], normal[0]), normal,
            offset, "WEB_SECTOR_BRIDGE"),)
    chord = _unit2(chord_directions[0])
    if chord[0] < -TOLERANCE or (abs(chord[0]) <= TOLERANCE and chord[1] < 0.):
        chord = (-chord[0], -chord[1])
    if any(abs(_dot(chord, value)) < .999 for value in chord_directions[1:]):
        return ()
    if _dot(directions[0], directions[1]) <= -.5:
        return ()
    normal = (-chord[1], chord[0])
    mean = (directions[0][0]+directions[1][0],
            directions[0][1]+directions[1][1])
    if _dot(normal, mean) < 0.:
        normal = (-normal[0], -normal[1])
    if min(_dot(normal, value) for value in directions) <= TOLERANCE:
        return ()
    # A bridge is a free-margin support.  It preserves every required overlap
    # corner and adds the configured margin only toward the exposed sector.
    offset = max(_dot(normal, point) for point in required)+spec.edge_margin
    keys = tuple(sorted(terminal))
    parallel = GussetSupportLine("|".join(keys), chord, normal, offset,
                                 "WEB_SECTOR_BRIDGE")

    # Also evaluate the direct connection between the nearest physical cap
    # endpoints.  This avoids stretching one cap merely to keep the bridge
    # parallel to an inclined chord at an asymmetric DuoPitch node.
    caps = {value.participant_key: value for value in
            _web_end_lines(participants, corridors, spec)}
    endpoint_sets = []
    for key in keys:
        cap = caps.get(key)
        values = [value for value in corridors
                  if value.participant_key == key]
        if cap is None or not values:
            return (parallel,)
        endpoints = []
        for value in values:
            direction = _unit2(value.direction)
            perpendicular = (-direction[1], direction[0])
            for transverse in (value.transverse_low, value.transverse_high):
                endpoints.append((cap.offset*direction[0]+transverse*perpendicular[0],
                                  cap.offset*direction[1]+transverse*perpendicular[1]))
        endpoint_sets.append(tuple(endpoints))
    first, second = min(
        ((a, b) for a in endpoint_sets[0] for b in endpoint_sets[1]),
        key=lambda pair: math.dist(*pair))
    delta = (second[0]-first[0], second[1]-first[1])
    if math.hypot(*delta) <= TOLERANCE:
        return (parallel,)
    direct_direction = _unit2(delta)
    direct_normal = (-direct_direction[1], direct_direction[0])
    direct_offset = _dot(direct_normal, first)
    if direct_offset < -TOLERANCE:
        direct_normal = (-direct_normal[0], -direct_normal[1])
        direct_offset = -direct_offset
    if any(_dot(direct_normal, point) > direct_offset+TOLERANCE
           for point in required):
        return (parallel,)
    direct = GussetSupportLine("|".join(keys), direct_direction,
                               direct_normal, direct_offset,
                               "WEB_SECTOR_BRIDGE")

    def intersection(first_line, second_line):
        determinant = (first_line.normal[0]*second_line.normal[1]
                       -first_line.normal[1]*second_line.normal[0])
        if abs(determinant) <= TOLERANCE:
            return None
        return ((first_line.offset*second_line.normal[1]
                 -first_line.normal[1]*second_line.offset)/determinant,
                (first_line.normal[0]*second_line.offset
                 -first_line.offset*second_line.normal[0])/determinant)

    cap_values = tuple(caps[key] for key in keys)
    def span(line):
        points = tuple(intersection(line, cap) for cap in cap_values)
        return (math.dist(*points) if all(point is not None for point in points)
                else float("inf"))
    return (direct if span(direct)+TOLERANCE < span(parallel)
            else parallel,)


def _terminal_boundary_lines(participants, corridors):
    """Clip a ChordClosure at its nominal local terminal plane, without margin."""
    chords = [value for value in participants if value.role in CHORD_ROLES]
    has_end_post = any(value.role == "END_POST" for value in participants)
    is_parallel_closure = (len(chords) == 1 and has_end_post
                           and chords[0].end != "Through")
    if len(chords) < 2 and not is_parallel_closure:
        return ()
    chord_keys = {value.participant_key for value in chords}
    directions = [_unit2(value.direction) for value in corridors
                  if value.participant_key in chord_keys]
    nonzero = [value[0] for value in directions if abs(value[0]) > TOLERANCE]
    if not nonzero or (any(value > 0. for value in nonzero)
                       and any(value < 0. for value in nonzero)):
        raise ValueError("Não foi possível resolver o limite físico do nó terminal.")
    inward_sign = 1. if sum(nonzero) > 0. else -1.
    normal = (-inward_sign, 0.)
    direction = (0., 1.)
    return (GussetSupportLine("|".join(sorted(chord_keys)), direction,
                              normal, 0., "TERMINAL_BOUNDARY"),)


def preliminary_gusset_outlines(candidate, truss_plane_normal=None, *, transverse_previews=None):
    """Return outlines/diagnostics and optionally collect disposable section views.

    The optional mapping reuses material already calculated by the attachment
    resolver; it never changes outline generation or persistent contracts.
    """
    if transverse_previews is not None:
        transverse_previews.clear()
    local_frame = reference_frame(candidate.config)
    truss_plane_normal = (tuple(local_frame[3]) if truss_plane_normal is None
                          else tuple(truss_plane_normal))
    resolutions, orphan_diagnostics, _canonical = resolve_truss_connections(
        candidate, truss_plane_normal)
    outlines, diagnostics = [], list(orphan_diagnostics)
    runs = {run.key: run for run in candidate.runs}
    for resolution in resolutions:
        if resolution.intent.form != ConnectionForm.GUSSET:
            continue
        if resolution.diagnostics:
            diagnostics.extend(replace(value, node_key=resolution.intent.node_key)
                               for value in resolution.diagnostics)
            continue
        intent = resolution.intent
        participants = _selected_participants(intent, resolution.participants)
        try:
            corridors = []
            for participant in participants:
                for run_key in participant.physical_run_keys:
                    if run_key not in runs:
                        raise ValueError("Participante físico da chapa não está disponível.")
                    corridors.extend(_corridors(candidate, participant, runs[run_key], local_frame))
            node = candidate.graph.node(intent.node_key)
            frame = GussetPlateFrame(
                transform_point(node.position_local, local_frame),
                tuple(local_frame[1]), tuple(local_frame[2]), tuple(local_frame[3]))
            spec = GussetPlateSpec(
                stable_key=intent.node_key+":gusset-plate", node_key=intent.node_key,
                plate_thickness=intent.gusset.plate_thickness,
                edge_margin=intent.gusset.edge_margin,
                member_overlap=intent.gusset.member_overlap, side=intent.gusset.side,
                attachment_mode=intent.gusset.attachment_mode,
                chord_contact=intent.gusset.chord_contact,
                transverse_placement=intent.gusset.transverse_placement,
                participant_keys=tuple(sorted(p.participant_key for p in participants)),
                component_keys=tuple(sorted({c.component_key for c in corridors})),
                frame=frame)
            surfaces, materials, slots = attachment_slot_geometry(
                candidate, participants, local_frame)
            slots = _accessible_recess_slots(participants, corridors, slots,
                                             materials, local_frame,
                                             spec.plate_thickness)
            attachment = resolve_gusset_attachment(
                spec, participants, surfaces, slots, materials)
            chord_lines = _chord_support_lines(
                participants, corridors, materials, attachment,
                spec.chord_contact, local_frame)
            side_lines = _web_side_lines(participants, corridors, spec)
            ending_web_roles = sorted(
                value.role for value in participants
                if value.role not in CHORD_ROLES and value.end != "Through")
            # On an ordinary diagonal/vertical joint the two physical end
            # caps already form the compact straight transition.  The extra
            # sector bridge only introduces a short fabrication chamfer.
            direct_cap_transition = (
                ending_web_roles == ["DIAGONAL", "VERTICAL"])
            sector_lines = (() if direct_cap_transition else
                            _web_sector_bridge_lines(
                                participants, corridors, spec))
            supports = (chord_lines
                        +_web_end_lines(participants, corridors, spec)
                        +side_lines
                        +sector_lines
                        +_terminal_boundary_lines(participants, corridors))
            outline = build_gusset_outline(spec, corridors, supports)
            outline, fallback = apply_approved_family(
                spec, participants, corridors, supports, outline)
            if fallback:
                diagnostics.append(ConnectionDiagnostic(
                    "GUSSET_FAMILY_FALLBACK", "Warning", fallback, intent.node_key))
            outline = replace(outline, attachment=attachment)
            outlines.append(outline)
            if transverse_previews is not None:
                from .gusset_presentation import transverse_views
                transverse_previews[intent.node_key] = transverse_views(
                    outline, participants, materials)
        except (KeyError, StopIteration, TypeError, ValueError) as exc:
            diagnostics.append(ConnectionDiagnostic(
                "GUSSET_PLATE_INVALID", "Warning", str(exc), intent.node_key))
    return tuple(outlines), tuple(diagnostics)
