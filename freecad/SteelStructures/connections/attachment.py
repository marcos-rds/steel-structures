"""Pure selection of a physical gusset attachment plane and residuals."""

from dataclasses import replace
import math

from .models import (GussetAccessibility, GussetAttachmentCandidate,
                     GussetAttachmentPlane, GussetAttachmentResidual,
                     GussetAttachmentMode, GussetAttachmentSlotKind,
                     GussetResidualStatus, GussetSide, GussetSlotPlacement,
                     GussetSurfaceClass)
from .slots import (contact_band_support, material_envelope_support,
                    slot_placements)

# CAD dimensions are stored in millimetres.  A tenth of a millimetre avoids
# classifying harmless catalogue/transform rounding as loss of contact while
# still exposing physically meaningful offsets.
CONTACT_TOLERANCE = 0.1
SYMMETRY_TOLERANCE = 0.1

ROLE_LABELS = {
    "TOP_CHORD": "Banzo superior",
    "BOTTOM_CHORD": "Banzo inferior",
    "VERTICAL": "Montante",
    "DIAGONAL": "Diagonal",
    "END_POST": "Fechamento",
}


def _semantic_rank(surface):
    if surface.role in ("TOP_CHORD", "BOTTOM_CHORD"):
        rank = 0
    elif surface.participant_end == "Through":
        rank = 1
    else:
        rank = {"VERTICAL": 2, "END_POST": 3, "DIAGONAL": 4}.get(surface.role, 5)
    return rank


def _surface_candidate(spec, surface):
    mode = (GussetAttachmentMode.OUTER
            if surface.surface_class == GussetSurfaceClass.OUTER
            else GussetAttachmentMode.INNER)
    accessible = (surface.free_space is None
                  or surface.free_space+CONTACT_TOLERANCE >= spec.plate_thickness)
    accessibility = (GussetAccessibility.UNSUPPORTED if not accessible else
                     GussetAccessibility.OUTER_EXPOSED
                     if mode == GussetAttachmentMode.OUTER
                     else GussetAccessibility.OPEN_RECESS)
    diagnostics = (() if accessible else (
        "Espaço livre %.1f mm menor que a espessura %.1f mm."
        % (surface.free_space, spec.plate_thickness),))
    stable_key = ":".join((surface.participant_key, surface.component_key,
                           surface.surface_id, mode.value,
                           "A" if surface.outward_sign > 0 else "B"))
    return GussetAttachmentCandidate(
        stable_key, mode, spec.frame.normal, surface.signed_offset,
        accessibility, surface.outward_sign,
        ((GussetSide.CENTER, surface.side)
         if mode == GussetAttachmentMode.INNER else (surface.side,)),
        surface.surface_id, surface.surface_class,
        surface.participant_key, surface.component_key,
        surface.free_space, diagnostics)


def _assembly_gap_candidates(spec, participants, surfaces):
    assemblies = {item.participant_key: item.assembly for item in participants}
    result = []
    for participant_key in sorted(assemblies):
        if assemblies[participant_key] == "Single":
            continue
        values = [value for value in surfaces if value.participant_key == participant_key]
        bands = {}
        for value in values:
            current = bands.setdefault(value.component_key,
                                       [value.component_band_low,
                                        value.component_band_high])
            current[0] = min(current[0], value.component_band_low)
            current[1] = max(current[1], value.component_band_high)
        if len(bands) < 2:
            continue
        ordered = sorted(bands.items(), key=lambda value: (
            sum(value[1])/2., value[0]))
        lower, upper = ordered[0], ordered[-1]
        gap_low, gap_high = lower[1][1], upper[1][0]
        # The useful plane is the middle of the *physical* gap.  It need not
        # coincide with the nominal truss plane: asymmetric section insertion
        # can translate both component envelopes without moving their axes.
        middle = (gap_low+gap_high)/2.
        gap = gap_high-gap_low
        half_gap = max(0., gap/2.)
        allowed = []
        if gap > CONTACT_TOLERANCE and spec.plate_thickness/2. <= half_gap+CONTACT_TOLERANCE:
            allowed.append(GussetSide.CENTER)
        if gap > CONTACT_TOLERANCE and spec.plate_thickness <= gap_high-middle+CONTACT_TOLERANCE:
            allowed.append(GussetSide.FACE_A)
        if gap > CONTACT_TOLERANCE and spec.plate_thickness <= middle-gap_low+CONTACT_TOLERANCE:
            allowed.append(GussetSide.FACE_B)
        accessibility = (GussetAccessibility.ASSEMBLY_GAP if allowed
                         else GussetAccessibility.UNSUPPORTED)
        diagnostics = (() if allowed else (
            "Vazio central %.1f mm incompatível com chapa de %.1f mm."
            % (max(0., gap), spec.plate_thickness),))
        key = participant_key+":assembly-gap:"+lower[0]+"|"+upper[0]
        result.append(GussetAttachmentCandidate(
            key, GussetAttachmentMode.CENTER, spec.frame.normal, middle,
            accessibility, 0,
            tuple(allowed or (GussetSide.CENTER,)),
            "central:axis:"+lower[0]+"|axis:"+upper[0], None,
            participant_key, lower[0]+"|"+upper[0], half_gap, diagnostics))
    return tuple(result)


def _slot_candidates(spec, slots, materials, surfaces=()):
    result = []
    material_by_participant = {}
    for value in materials:
        material_by_participant.setdefault(value.participant_key, []).append(value)
    surface_by_key = {(value.participant_key, value.surface_id): value
                      for value in surfaces}
    for slot in slots:
        if slot.kind in (GussetAttachmentSlotKind.ENCLOSED_VOID,
                         GussetAttachmentSlotKind.UNSUPPORTED):
            continue
        mode = {GussetAttachmentSlotKind.OUTER_HALFSPACE: GussetAttachmentMode.OUTER,
                GussetAttachmentSlotKind.OPEN_RECESS: GussetAttachmentMode.INNER,
                GussetAttachmentSlotKind.BETWEEN_COMPONENTS: GussetAttachmentMode.CENTER,
                GussetAttachmentSlotKind.SURFACE_BAND: GussetAttachmentMode.AUTO}[slot.kind]
        accessibility = {
            GussetAttachmentSlotKind.OUTER_HALFSPACE: GussetAccessibility.OUTER_EXPOSED,
            GussetAttachmentSlotKind.OPEN_RECESS: GussetAccessibility.OPEN_RECESS,
            GussetAttachmentSlotKind.BETWEEN_COMPONENTS: GussetAccessibility.ASSEMBLY_GAP,
            GussetAttachmentSlotKind.SURFACE_BAND: GussetAccessibility.SURFACE_BAND,
        }[slot.kind]
        participant_materials = tuple(material_by_participant.get(
            slot.participant_key, ()))
        for placement, low, high, window in slot_placements(
                slot, spec.plate_thickness, participant_materials):
            side = {GussetSlotPlacement.NEAR_A: GussetSide.FACE_A,
                    GussetSlotPlacement.CENTER: GussetSide.CENTER,
                    GussetSlotPlacement.NEAR_B: GussetSide.FACE_B}[placement]
            if placement == GussetSlotPlacement.NEAR_A:
                offset, sign, surface_id = low, 1, slot.boundary_a_surface_id
            elif placement == GussetSlotPlacement.NEAR_B:
                offset, sign, surface_id = high, -1, slot.boundary_b_surface_id
            else:
                offset, sign, surface_id = (low+high)/2., 0, (
                    slot.boundary_a_surface_id+"|"+slot.boundary_b_surface_id)
            if (slot.kind == GussetAttachmentSlotKind.BETWEEN_COMPONENTS
                    and placement != GussetSlotPlacement.CENTER):
                boundary = surface_by_key.get((slot.participant_key, surface_id))
                if (boundary is not None
                        and boundary.surface_class == GussetSurfaceClass.INNER):
                    # A lateral slab beside an inward-facing channel enters
                    # that component's open recess.  It is not a useful
                    # between-components connection plane; the central gap
                    # and the independently derived surface bands remain.
                    continue
            key = slot.stable_key+":"+placement.value
            include_tangent = slot.kind in (
                GussetAttachmentSlotKind.OUTER_HALFSPACE,
                GussetAttachmentSlotKind.BETWEEN_COMPONENTS)
            outline_band = None
            if (slot.access_sign
                    and (slot.kind == GussetAttachmentSlotKind.OUTER_HALFSPACE
                         or (slot.kind == GussetAttachmentSlotKind.BETWEEN_COMPONENTS
                             and placement != GussetSlotPlacement.CENTER))):
                # Outside the section, or laterally beside one component in a
                # real assembly gap, a lip/flange tangent to the slab is not
                # the in-plane termination.  The collision-free window lets
                # the plate continue alongside it to the accessible extreme
                # of the transformed section material.
                contact_band = material_envelope_support(
                    participant_materials, slot.access_sign)
                # An external/lateral slab first meets the web-facing band,
                # but remains collision-free beside the section through to
                # its opposite exterior frontier.  These are distinct 2D
                # boundaries; using the first encounter to clip the outline
                # truncated the plate at the inner flange face.
                opposite = material_envelope_support(
                    participant_materials, -slot.access_sign)
                outline_band = (-opposite if opposite is not None
                                else contact_band)
            else:
                contact_band = (contact_band_support(
                    participant_materials, low, high, slot.access_sign,
                    include_tangent=include_tangent)
                                if slot.access_sign else None)
                outline_band = contact_band
            result.append(GussetAttachmentCandidate(
                key, mode, spec.frame.normal, offset, accessibility, sign,
                (side,), surface_id,
                (GussetSurfaceClass.OUTER if mode in (GussetAttachmentMode.OUTER,
                                                      GussetAttachmentMode.AUTO)
                 else GussetSurfaceClass.INNER if mode == GussetAttachmentMode.INNER
                 else None), slot.participant_key, "|".join(slot.component_keys),
                slot.available_clear_width, slot.diagnostics, slot.stable_key,
                placement, low, high, window,
                slot.access_sign, contact_band, outline_band))
    return tuple(result)


def gusset_attachment_candidates(spec, participants, surfaces, slots=(), materials=()):
    """Return stable physical placements derived only from pre-fitting geometry.

    Inner loops/holes are deliberately not surfaced by connection_surfaces(),
    so enclosed RHS/SHS voids cannot become automatic simple-plate supports.
    """
    if slots:
        result = list(_slot_candidates(spec, slots, materials, surfaces))
    else:
        result = [_surface_candidate(spec, value) for value in surfaces]
        result.extend(_assembly_gap_candidates(spec, participants, surfaces))
    return tuple(sorted(result, key=lambda value: (
        value.attachment_mode.value, value.governing_participant_key,
        value.governing_component_key, value.surface_semantic_id,
        value.stable_key)))


def attachment_side_options(candidates, mode):
    """Return only physical Side choices supported by an attachment mode."""
    mode = GussetAttachmentMode(mode)
    usable = tuple(value for value in candidates
                   if value.accessibility not in (
                       GussetAccessibility.UNSUPPORTED,
                       GussetAccessibility.ENCLOSED_VOID))
    relevant = usable if mode == GussetAttachmentMode.AUTO else tuple(
        value for value in usable if value.attachment_mode == mode)
    present = {side for value in relevant for side in value.allowed_sides}
    return tuple(side for side in (GussetSide.CENTER, GussetSide.FACE_A,
                                   GussetSide.FACE_B) if side in present)


def _central_assembly_plane(spec, participants, surfaces, candidates):
    gaps = [value for value in candidates
            if value.attachment_mode == GussetAttachmentMode.CENTER
            and value.accessibility == GussetAccessibility.ASSEMBLY_GAP
            and spec.side in value.allowed_sides]
    if not gaps:
        return None
    surface_by_participant = {}
    for surface in surfaces:
        surface_by_participant.setdefault(surface.participant_key, surface)
    candidate = min(gaps, key=lambda value: (
        _semantic_rank(surface_by_participant[value.governing_participant_key]),
        abs(value.signed_offset), value.stable_key))
    offset = candidate.signed_offset
    if candidate.plate_low is not None:
        low, high = candidate.plate_low, candidate.plate_high
    elif spec.side == GussetSide.CENTER:
        low, high = (offset-spec.plate_thickness/2.,
                     offset+spec.plate_thickness/2.)
    elif spec.side == GussetSide.FACE_A:
        low, high = offset, offset+spec.plate_thickness
    else:
        low, high = offset-spec.plate_thickness, offset
    return GussetAttachmentPlane(
        spec.frame.normal, offset, low, high,
        governing_participant_key=candidate.governing_participant_key,
        governing_component_key=candidate.governing_component_key,
        governing_surface_id=candidate.surface_semantic_id,
        attachment_side=spec.side, contact_sign=0,
        kind="AssemblyMidPlane", status="Resolved",
        requested_mode=spec.attachment_mode, candidates=tuple(candidates))


def _fallback(spec, message):
    if spec.side == GussetSide.CENTER:
        low, high = -spec.plate_thickness/2., spec.plate_thickness/2.
    elif spec.side == GussetSide.FACE_A:
        low, high = 0., spec.plate_thickness
    else:
        low, high = -spec.plate_thickness, 0.
    return GussetAttachmentPlane(
        spec.frame.normal, 0., low, high, attachment_side=spec.side,
        contact_sign=0, kind="NominalFallback", status="Warning",
        diagnostics=(message,), requested_mode=spec.attachment_mode)


def _residuals(plane, participants, surfaces):
    result, diagnostics = [], list(plane.diagnostics)
    for participant in sorted(participants, key=lambda value: value.participant_key):
        values = [value for value in surfaces
                  if value.participant_key == participant.participant_key]
        label = ROLE_LABELS.get(participant.role, participant.role.title())
        if participant.participant_key == plane.governing_participant_key:
            result.append(GussetAttachmentResidual(
                participant.participant_key, participant.role,
                GussetResidualStatus.CONTACT, 0.,
                plane.governing_surface_id,
                label+": contato com o slot selecionado."))
            continue
        if plane.governing_surface_class is not None:
            values = [value for value in values
                      if value.surface_class == plane.governing_surface_class]
        if plane.contact_sign:
            values = [value for value in values
                      if value.outward_sign == plane.contact_sign]
        if not values:
            message = label+": sem superfície plana compatível."
            result.append(GussetAttachmentResidual(
                participant.participant_key, participant.role,
                GussetResidualStatus.NO_COMPATIBLE_SURFACE, None, message=message))
            diagnostics.append(message)
            continue
        measured = []
        for surface in values:
            residual = ((plane.plate_low-surface.signed_offset)
                        if surface.outward_sign > 0
                        else (surface.signed_offset-plane.plate_high))
            measured.append((abs(residual), -surface.contact_extent, surface.surface_id,
                             surface.component_key, residual, surface))
        (_absolute, _extent, _surface_id, _component,
         residual, surface) = min(measured, key=lambda value: value[:-1])
        if abs(residual) <= CONTACT_TOLERANCE:
            status = GussetResidualStatus.CONTACT
            residual = 0.
            message = label+": contato com o plano da chapa."
        elif residual > 0.:
            status = GussetResidualStatus.GAP
            value = ("%.1f" % abs(residual)).replace(".", ",")
            message = label+": face de ligação "+value+" mm afastada do plano da chapa."
            diagnostics.append(message)
        else:
            status = GussetResidualStatus.INTERFERENCE
            value = ("%.1f" % abs(residual)).replace(".", ",")
            message = label+": interferência transversal de "+value+" mm."
            diagnostics.append(message)
        result.append(GussetAttachmentResidual(
            participant.participant_key, participant.role, status, residual,
            surface.surface_id, message))
    status = ("Resolved" if all(value.status == GussetResidualStatus.CONTACT
                                for value in result) else "Warning")
    return replace(plane, status=status, residuals=tuple(result),
                   diagnostics=tuple(dict.fromkeys(diagnostics)))


def resolve_gusset_attachment(spec, participants, surfaces, slots=(), materials=()):
    """Select one deterministic physical plane without moving participants."""
    participants, surfaces = tuple(participants), tuple(surfaces)
    candidates = gusset_attachment_candidates(spec, participants, surfaces,
                                               slots, materials)
    chord_keys = {value.participant_key for value in participants
                  if value.role in ("TOP_CHORD", "BOTTOM_CHORD")}
    if chord_keys:
        # Outer/Inner describe the chord support when a chord participates.
        # Web recesses must not leak impossible Side choices into the UI for
        # W/I chords whose web separates the two physical recesses.
        candidates = tuple(value for value in candidates
                           if value.attachment_mode not in (
                               GussetAttachmentMode.OUTER,
                               GussetAttachmentMode.INNER)
                           or value.governing_participant_key in chord_keys)
    mode = GussetAttachmentMode(spec.attachment_mode)
    if slots:
        selected_key = getattr(spec, "transverse_placement", "")
        selected_invalid = False
        if selected_key:
            usable = [value for value in candidates
                      if value.stable_key == selected_key]
            if not usable:
                selected_invalid = True
                usable = list(candidates)
        elif mode == GussetAttachmentMode.AUTO:
            usable = (list(candidates) if spec.side == GussetSide.CENTER else
                      [value for value in candidates
                       if spec.side in value.allowed_sides])
            if not usable:
                usable = list(candidates)
        else:
            usable = [value for value in candidates
                      if value.attachment_mode == mode
                      and spec.side in value.allowed_sides]
        if usable:
            surface_by_key = {(value.participant_key, value.surface_id): value
                              for value in surfaces}
            participant_by_key = {value.participant_key: value
                                  for value in participants}
            def slot_priority(value):
                surface = surface_by_key.get((value.governing_participant_key,
                                              value.surface_semantic_id))
                if surface is not None:
                    rank = _semantic_rank(surface)
                else:
                    participant = participant_by_key.get(
                        value.governing_participant_key)
                    role = getattr(participant, "role", "")
                    rank = (0 if role in ("TOP_CHORD", "BOTTOM_CHORD")
                            else 1 if getattr(participant, "end", "") == "Through"
                            else {"VERTICAL": 2, "END_POST": 3,
                                  "DIAGONAL": 4}.get(role, 5))
                placement_rank = {
                    GussetAccessibility.ASSEMBLY_GAP: 0,
                    GussetAccessibility.OPEN_RECESS: 1,
                    GussetAccessibility.SURFACE_BAND: (
                        2 if any("seção fechada" in message
                                 for message in value.diagnostics) else 4),
                    GussetAccessibility.OUTER_EXPOSED: 3,
                }.get(value.accessibility, 4)
                if (value.accessibility == GussetAccessibility.ASSEMBLY_GAP
                        and spec.side != GussetSide.CENTER):
                    placement_rank = 3
                return (placement_rank, rank, abs(value.signed_offset),
                        value.stable_key)
            candidate = min(usable, key=slot_priority)
            plane_kind = ("AssemblyMidPlane"
                          if candidate.attachment_mode == GussetAttachmentMode.CENTER
                          else "SurfaceBand"
                          if candidate.accessibility == GussetAccessibility.SURFACE_BAND
                          else "PhysicalSurface")
            plane = GussetAttachmentPlane(
                spec.frame.normal, candidate.signed_offset,
                candidate.plate_low, candidate.plate_high,
                candidate.governing_participant_key,
                candidate.governing_component_key,
                candidate.surface_semantic_id, candidate.allowed_sides[0],
                candidate.extrusion_sign, plane_kind, "Resolved",
                diagnostics=(("A posição anterior ficou indisponível; usada Automática.",)
                             if selected_invalid else ()),
                requested_mode=mode,
                governing_surface_class=candidate.surface_class,
                candidates=candidates,
                governing_slot_id=candidate.slot_id,
                placement_kind=candidate.placement,
                contact_window=candidate.contact_window)
            return _residuals(plane, participants, surfaces)
        return _residuals(replace(_fallback(
            spec, "Posição solicitada indisponível nos slots físicos da seção."),
            candidates=candidates), participants, surfaces)
    if mode in (GussetAttachmentMode.AUTO, GussetAttachmentMode.CENTER):
        central = _central_assembly_plane(spec, participants, surfaces, candidates)
        if central is not None:
            return _residuals(replace(central, candidates=candidates),
                              participants, surfaces)
        if mode == GussetAttachmentMode.CENTER:
            return _residuals(replace(_fallback(
                spec, "Plano central físico indisponível; usado plano nominal."),
                candidates=candidates),
                participants, surfaces)
    usable_surface_keys = {
        (value.governing_participant_key, value.governing_component_key,
         value.surface_semantic_id)
        for value in candidates
        if value.accessibility in (GussetAccessibility.OUTER_EXPOSED,
                                   GussetAccessibility.OPEN_RECESS)
        and spec.side in value.allowed_sides
    }
    eligible = tuple(value for value in surfaces if (
        value.participant_key, value.component_key, value.surface_id)
        in usable_surface_keys)
    if mode == GussetAttachmentMode.OUTER:
        eligible = tuple(value for value in eligible
                         if value.surface_class == GussetSurfaceClass.OUTER)
    elif mode == GussetAttachmentMode.INNER:
        eligible = tuple(value for value in eligible
                         if value.surface_class == GussetSurfaceClass.INNER)
    if mode in (GussetAttachmentMode.OUTER, GussetAttachmentMode.INNER):
        chord_surfaces = tuple(value for value in surfaces
                               if value.role in ("TOP_CHORD", "BOTTOM_CHORD"))
        if chord_surfaces:
            eligible = tuple(value for value in eligible
                             if value.role in ("TOP_CHORD", "BOTTOM_CHORD"))
    if spec.side != GussetSide.CENTER:
        sign = 1 if spec.side == GussetSide.FACE_A else -1
        eligible = tuple(value for value in eligible if value.outward_sign == sign)
    if not eligible:
        label = {GussetSide.CENTER: "Centrada", GussetSide.FACE_A: "Lado A",
                 GussetSide.FACE_B: "Lado B"}[spec.side]
        mode_label = {GussetAttachmentMode.AUTO: "automática",
                      GussetAttachmentMode.OUTER: "externa",
                      GussetAttachmentMode.INNER: "interna",
                      GussetAttachmentMode.CENTER: "central"}[mode]
        return _residuals(replace(_fallback(
            spec, label+": nenhuma superfície "+mode_label
            +" compatível; usado plano nominal."), candidates=candidates),
            participants, surfaces)
    def priority(surface):
        coverage = len({value.participant_key for value in eligible
                        if value.outward_sign == surface.outward_sign
                        and abs(value.signed_offset-surface.signed_offset)
                        <= CONTACT_TOLERANCE})
        return (_semantic_rank(surface), -coverage, -surface.contact_extent,
                abs(surface.signed_offset), surface.participant_key,
                surface.component_key, surface.surface_id)
    surface = min(eligible, key=priority)
    if surface.outward_sign > 0:
        low, high = surface.signed_offset, surface.signed_offset+spec.plate_thickness
    else:
        low, high = surface.signed_offset-spec.plate_thickness, surface.signed_offset
    label = ROLE_LABELS.get(surface.role, surface.role.title())
    side_label = ("lado A" if surface.outward_sign > 0 else "lado B")
    plane = GussetAttachmentPlane(
        spec.frame.normal, surface.signed_offset, low, high,
        surface.participant_key, surface.component_key, surface.surface_id,
        spec.side, surface.outward_sign, "PhysicalSurface", "Resolved",
        diagnostics=("Plano da chapa governado por "+label+" — "+side_label+".",),
        requested_mode=mode, governing_surface_class=surface.surface_class,
        candidates=candidates)
    return _residuals(plane, participants, surfaces)


def attachment_warning_messages(outlines, maximum=3):
    """Compact actionable UI warnings; full diagnostics remain in contracts."""
    messages = []
    for outline in outlines:
        attachment = outline.attachment
        if attachment is None:
            continue
        for residual in attachment.residuals:
            if residual.status != GussetResidualStatus.CONTACT and residual.message:
                messages.append("Atenção: "+residual.message)
        if attachment.kind == "NominalFallback":
            messages.extend("Atenção: "+message for message in attachment.diagnostics)
            for candidate in attachment.candidates:
                if candidate.attachment_mode == attachment.requested_mode:
                    messages.extend("Atenção: "+message
                                    for message in candidate.diagnostics)
    return compact_connection_messages(messages, maximum)


def compact_connection_messages(messages, maximum=3):
    """Return every distinct message in deterministic order."""
    del maximum  # retained for source compatibility with older callers
    return tuple(sorted(set(message for message in messages if message)))


__all__ = ["CONTACT_TOLERANCE", "attachment_side_options",
           "attachment_warning_messages", "gusset_attachment_candidates",
           "compact_connection_messages",
           "resolve_gusset_attachment"]
