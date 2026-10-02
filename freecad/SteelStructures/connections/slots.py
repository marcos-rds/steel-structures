"""Pure attachment-slot and plate-slab collision geometry."""

from __future__ import annotations

from dataclasses import replace

from .models import (GussetAttachmentSlot, GussetAttachmentSlotKind,
                     GussetContactWindow, GussetSectionMaterial2D,
                     GussetSlotPlacement, GussetSurfaceClass)

TOLERANCE = 1e-7


def _inside_path(point, path):
    x, y = point
    inside = False
    previous = path[-1]
    for current in path:
        x1, y1 = previous
        x2, y2 = current
        if ((y1 > y) != (y2 > y)):
            crossing = x1+(y-y1)*(x2-x1)/(y2-y1)
            if crossing > x:
                inside = not inside
        previous = current
    return inside


def _inside_material(point, material):
    return (_inside_path(point, material.outer)
            and not any(_inside_path(point, path) for path in material.holes))


def _line_intersections(path, ordinate):
    result = []
    previous = path[-1]
    for current in path:
        n1, q1 = previous
        n2, q2 = current
        # Half-open rule gives one deterministic hit at polygon vertices.
        if (q1 <= ordinate < q2) or (q2 <= ordinate < q1):
            result.append(n1+(ordinate-q1)*(n2-n1)/(q2-q1))
        previous = current
    return result


def material_intervals(materials, ordinate):
    """Return the union of positive material intervals on one scan line."""
    cuts = []
    for material in materials:
        cuts.extend(_line_intersections(material.outer, ordinate))
        for path in material.holes:
            cuts.extend(_line_intersections(path, ordinate))
    cuts = sorted(set(round(value, 10) for value in cuts))
    occupied = []
    for low, high in zip(cuts, cuts[1:]):
        if high-low <= TOLERANCE:
            continue
        middle = (low+high)/2.
        if any(_inside_material((middle, ordinate), value)
               for value in materials):
            if occupied and low <= occupied[-1][1]+TOLERANCE:
                occupied[-1] = (occupied[-1][0], high)
            else:
                occupied.append((low, high))
    return tuple(occupied)


def contact_band_support(materials, plate_low, plate_high, direction=1,
                         include_tangent=True):
    """Extreme material boundary reached by a complete transverse plate slab.

    Section contours have already been transformed to (truss normal, local
    in-plane axis).  Clipping every contour edge by the slab catches sloping
    flanges, lips and sampled circular transitions, including extrema between
    the plate faces.  ``direction`` is the sign of the desired in-plane axis.
    """
    if plate_high <= plate_low or direction not in (-1, 1):
        raise ValueError("Faixa de contato inválida.")
    ordinates = []
    # A plate beside a flange/lip is allowed to touch it transversely.  Such
    # planned tangency must not turn the end of that flange/lip into an
    # artificial in-plane chord boundary.  Sampling an infinitesimally open
    # slab keeps every positive intersection (including tapered faces and
    # radii), while excluding material that exists only on a plate face.
    inset = 0. if include_tangent else min(1e-6, (plate_high-plate_low)/4.)
    sample_low, sample_high = plate_low+inset, plate_high-inset
    for material in materials:
        for path in (material.outer,):
            previous = path[-1]
            for current in path:
                n0, q0 = previous
                n1, q1 = current
                if sample_low-TOLERANCE <= n0 <= sample_high+TOLERANCE:
                    ordinates.append(direction*q0)
                for boundary in (sample_low, sample_high):
                    if abs(n1-n0) > TOLERANCE and min(n0, n1)-TOLERANCE <= boundary <= max(n0, n1)+TOLERANCE:
                        t = (boundary-n0)/(n1-n0)
                        if -TOLERANCE <= t <= 1.+TOLERANCE:
                            ordinates.append(direction*(q0+t*(q1-q0)))
                previous = current
    return max(ordinates) if ordinates else None


def material_envelope_support(materials, direction=1):
    """Extreme accessible section ordinate, independent of slot boundaries."""
    if direction not in (-1, 1):
        raise ValueError("Direção do envelope de contato inválida.")
    values = [direction*q for material in materials
              for _n, q in material.outer]
    return max(values) if values else None


def flat_contact_intervals(materials, access_sign):
    """Return transverse intervals of the extreme *flat* accessible face."""
    materials = tuple(materials)
    if not materials or access_sign not in (-1, 1):
        return ()
    extreme = max(access_sign*q for material in materials
                  for n, q in material.outer)
    intervals = []
    for material in materials:
        previous = material.outer[-1]
        for current in material.outer:
            n0, q0 = previous
            n1, q1 = current
            if (abs(access_sign*q0-extreme) <= TOLERANCE
                    and abs(access_sign*q1-extreme) <= TOLERANCE
                    and abs(n1-n0) > TOLERANCE):
                intervals.append((min(n0, n1), max(n0, n1)))
            previous = current
    merged = []
    for low, high in sorted(intervals):
        if merged and low <= merged[-1][1]+TOLERANCE:
            merged[-1] = (merged[-1][0], max(merged[-1][1], high))
        else:
            merged.append((low, high))
    return tuple(merged)


def derive_surface_band_slots(participant_key, normal, materials, access_sign):
    """Return chord-face bands reachable from the incident web region.

    Unlike a recess slot, this band lies across the section width.  Its plate
    stops at the first real material boundary along ``access_sign``; therefore
    a closed tube offers its exterior face, never its enclosed void.
    """
    materials = tuple(value for value in materials
                      if value.participant_key == participant_key)
    if not materials or access_sign not in (-1, 1):
        return None
    intervals = flat_contact_intervals(materials, access_sign)
    result = []
    for index, (low, high) in enumerate(intervals):
        result.append(GussetAttachmentSlot(
            participant_key+":SurfaceBand:"+str(index), participant_key,
            tuple(sorted(value.component_key for value in materials)),
            GussetAttachmentSlotKind.SURFACE_BAND, normal,
            free_low=low, free_high=high, available_clear_width=high-low,
            open_accessibility=True,
            allowed_placements=(GussetSlotPlacement.NEAR_A,
                                GussetSlotPlacement.CENTER,
                                GussetSlotPlacement.NEAR_B),
            local_axis=materials[0].local_axis, access_sign=access_sign,
            diagnostics=(("Faixa de superfície de seção fechada.",)
                         if any(value.holes for value in materials) else ())))
    return tuple(result)


def derive_surface_band_slot(participant_key, normal, materials, access_sign):
    """Backward-compatible singular access to the widest flat face band."""
    values = derive_surface_band_slots(participant_key, normal, materials,
                                       access_sign)
    return max(values, key=lambda value: value.available_clear_width,
               default=None)


def recess_is_open(materials, low, high, access_sign):
    """A ray must reach inside the section from the requested open side.

    The member axis may be occupied by a web. Accessibility concerns the
    open recess beyond that web, not a free interval containing q=0.
    """
    materials = tuple(materials)
    middle = (low+high)/2.
    extent = material_envelope_support(materials, access_sign)
    contact = contact_band_support(materials, middle-1e-5, middle+1e-5,
                                   access_sign, include_tangent=False)
    return (contact is not None and extent is not None
            and contact < extent-TOLERANCE)


def derive_open_recess_slots(participant_key, normal, materials, access_sign,
                             plate_thickness=0.):
    """Derive missing recess throats without requiring parallel flange faces.

    Use the deepest fitting free cell visible from the requested side. Its
    actual polygon boundaries include tapered flanges and sampled fillets.
    Existing planar/axis-gap slots take precedence at the caller.
    """
    materials = tuple(value for value in materials
                      if value.participant_key == participant_key)
    # Through chords can contribute the same component at both incident runs.
    sections = {(value.component_key,
                 tuple((round(n, 7), round(q, 7)) for n, q in value.outer))
                for value in materials}
    if len(sections) != 1 or any(value.holes for value in materials):
        return ()
    stations = sorted(set(access_sign*q for n, q in materials[0].outer))
    result = []
    for start, end in zip(stations, stations[1:]):
        if end-start <= TOLERANCE:
            continue
        # Approach the deeper end from within this free-space cell; unlike
        # a midpoint sample this retains the limiting width of tapered faces.
        ordinate = access_sign*(start+min(1e-6, (end-start)/4.))
        occupied = material_intervals(materials, ordinate)
        for before, after in zip(occupied, occupied[1:]):
            low, high = before[1], after[0]
            if (high-low <= TOLERANCE or high-low < plate_thickness-TOLERANCE
                    or not recess_is_open(
                        materials, low, high, access_sign)):
                continue
            middle = (low+high)/2.
            contact = contact_band_support(
                materials, middle-1e-5, middle+1e-5, access_sign,
                include_tangent=False)
            if contact > access_sign*ordinate+TOLERANCE:
                continue  # free cell on the other side of an intervening web
            if any(slot.free_low < middle < slot.free_high for slot in result):
                continue
            result.append(GussetAttachmentSlot(
                participant_key+":OpenRecess:throat:"+str(access_sign)+":"+str(len(result)),
                participant_key, (materials[0].component_key,),
                GussetAttachmentSlotKind.OPEN_RECESS, normal,
                free_low=low, free_high=high, available_clear_width=high-low,
                open_accessibility=True,
                allowed_placements=(GussetSlotPlacement.NEAR_A,
                                    GussetSlotPlacement.CENTER,
                                    GussetSlotPlacement.NEAR_B),
                local_axis=materials[0].local_axis, access_sign=access_sign))
    return tuple(result)


def _surface_at(surfaces, offset, component_keys, sign):
    values = [value for value in surfaces
              if value.component_key in component_keys
              and value.outward_sign == sign
              and abs(value.signed_offset-offset) <= .1]
    return min(values, key=lambda value: (-value.contact_extent,
                                          value.component_key,
                                          value.surface_id)) if values else None


def _access_sign(materials, low, high, axis, stable):
    middle = (low+high)/2.
    probe = slab_contact_window(stable+":access", materials,
                                middle-1e-4, middle+1e-4, axis,
                                tolerance=0.)
    for window_low, window_high in probe.intervals:
        if ((window_low is None or window_low <= TOLERANCE)
                and (window_high is None or window_high >= -TOLERANCE)):
            if window_low is None and window_high is not None:
                return -1
            if window_high is None and window_low is not None:
                return 1
    return 0


def derive_attachment_slots(participant_key, normal, materials, surfaces):
    """Derive slots from scan-line free-space cells of transformed material.

    The algorithm knows no profile family.  Webs, flanges, lips, closed holes
    and assembly gaps participate through their actual nominal polygons.
    """
    materials = tuple(value for value in materials
                      if value.participant_key == participant_key)
    surfaces = tuple(value for value in surfaces
                     if value.participant_key == participant_key)
    if not materials:
        return ()
    stations = sorted(set(q for value in materials
                          for path in (value.outer,)+value.holes
                          for _n, q in path))
    if len(stations) < 2:
        return ()
    records = {}
    component_keys = tuple(sorted(value.component_key for value in materials))
    normal_values = [n for value in materials
                     for path in (value.outer,)+value.holes
                     for n, _q in path]
    material_low, material_high = min(normal_values), max(normal_values)
    for q_low, q_high in zip(stations, stations[1:]):
        if q_high-q_low <= TOLERANCE:
            continue
        q = (q_low+q_high)/2.
        occupied = material_intervals(materials, q)
        free = []
        previous = None
        for low, high in occupied:
            free.append((previous, low))
            previous = high
        free.append((previous, None))
        for low, high in free:
            a = _surface_at(surfaces, low, component_keys, 1) if low is not None else None
            b = _surface_at(surfaces, high, component_keys, -1) if high is not None else None
            if a is None and b is None:
                continue
            # An inner face opening to the exterior has one material boundary
            # and one geometric mouth.  Close that slot at the transformed
            # section support so NearA/Center/NearB describe positions inside
            # the recess, while a genuinely outer face remains a half-space.
            if (low is None and b is not None
                    and b.surface_class == GussetSurfaceClass.INNER):
                low = material_low
            if (high is None and a is not None
                    and a.surface_class == GussetSurfaceClass.INNER):
                high = material_high
            # A compatible longitudinal surface is planar; retain its exact
            # semantic offset instead of the sampled arc station nearby.
            low = a.signed_offset if a is not None else low
            high = b.signed_offset if b is not None else high
            bounded = low is not None and high is not None
            boundary_components = {value.component_key for value in (a, b)
                                   if value is not None}
            if bounded and len(boundary_components) > 1:
                kind = GussetAttachmentSlotKind.BETWEEN_COMPONENTS
            elif any(value is not None and value.surface_class == GussetSurfaceClass.INNER
                     for value in (a, b)):
                kind = GussetAttachmentSlotKind.OPEN_RECESS
            else:
                kind = GussetAttachmentSlotKind.OUTER_HALFSPACE
            a_id = a.surface_id if a else ""
            b_id = b.surface_id if b else ""
            width = high-low if bounded else None
            key = (kind.value, round(low, 6) if low is not None else None,
                   round(high, 6) if high is not None else None, a_id, b_id)
            record = records.setdefault(key, [q_low, q_high, a, b, kind, width])
            record[0] = min(record[0], q_low)
            record[1] = max(record[1], q_high)
    result = []
    for key, (q_low, q_high, a, b, kind, width) in sorted(records.items(),
                                                           key=lambda item: str(item[0])):
        low, high = key[1], key[2]
        boundary_ids = tuple(value.surface_id for value in (a, b)
                             if value is not None)
        placements = ([GussetSlotPlacement.NEAR_A] if low is not None else [])
        # Center is meaningful only for a continuous recess spanning the
        # nominal plane.  This keeps the two W/I web recesses independent.
        if (low is not None and high is not None
                and (kind == GussetAttachmentSlotKind.BETWEEN_COMPONENTS
                     or low-TOLERANCE <= 0. <= high+TOLERANCE)):
            placements.append(GussetSlotPlacement.CENTER)
        if high is not None:
            placements.append(GussetSlotPlacement.NEAR_B)
        stable = participant_key+":"+kind.value+":"+("|".join(boundary_ids) or "open")
        axis = materials[0].local_axis
        access_sign = 0
        if (kind == GussetAttachmentSlotKind.OPEN_RECESS
                and low is not None and high is not None):
            # Determine the mouth from the free-space component containing
            # the nominal member axis.  Its open end, rather than the section
            # bounding box, is the actual direction of access.
            access_sign = _access_sign(materials, low, high, axis, stable)
        result.append(GussetAttachmentSlot(
            stable, participant_key, component_keys, kind, normal,
            a.surface_id if a else "", b.surface_id if b else "",
            low, high, width,
            kind != GussetAttachmentSlotKind.OPEN_RECESS or access_sign != 0,
            tuple(placements), boundary_ids, axis,
            access_sign=access_sign))
    # Inclined flange faces may have no longitudinal planar surface at the
    # nominal axis.  Their bounded free cell still defines a real recess.
    axis_gaps = material_intervals(materials, 0.)
    for index, (before, after) in enumerate(zip(axis_gaps, axis_gaps[1:])):
        low, high = before[1], after[0]
        if high-low <= TOLERANCE or any(
                slot.free_low is not None and slot.free_high is not None
                and slot.free_low-TOLERANCE <= low
                and slot.free_high+TOLERANCE >= high for slot in result):
            continue
        stable = participant_key+":OpenRecess:axis-gap:"+str(index)
        axis = materials[0].local_axis
        access_sign = _access_sign(materials, low, high, axis, stable)
        if access_sign == 0:
            continue
        result.append(GussetAttachmentSlot(
            stable, participant_key, component_keys,
            GussetAttachmentSlotKind.OPEN_RECESS, normal,
            free_low=low, free_high=high,
            available_clear_width=high-low, open_accessibility=True,
            allowed_placements=(GussetSlotPlacement.NEAR_A,
                                GussetSlotPlacement.CENTER,
                                GussetSlotPlacement.NEAR_B),
            local_axis=axis, access_sign=access_sign))
    # Inner paths are topologically closed regardless of profile family.  They
    # remain observable for diagnostics but never offer a simple Gusset.
    for material in materials:
        for index, path in enumerate(material.holes):
            ns = [point[0] for point in path]
            stable = (participant_key+":EnclosedVoid:"+material.component_key
                      +":"+str(index))
            result.append(GussetAttachmentSlot(
                stable, participant_key, (material.component_key,),
                GussetAttachmentSlotKind.ENCLOSED_VOID, normal,
                free_low=min(ns), free_high=max(ns),
                available_clear_width=max(ns)-min(ns),
                open_accessibility=False, local_axis=material.local_axis,
                diagnostics=("Vazio fechado não é acessível para uma chapa simples.",)))
    return tuple(result)


def slab_contact_window(stable_key, materials, low, high, local_axis,
                        contact_surface_ids=(), tolerance=.1):
    """Return q intervals where the slab has no positive material overlap."""
    materials = tuple(materials)
    stations = sorted(set(q for value in materials
                          for path in (value.outer,)+value.holes
                          for _n, q in path))
    if not stations:
        return GussetContactWindow(stable_key, local_axis, ((None, None),),
                                   tuple(contact_surface_ids))
    allowed = [(None, stations[0])]
    for q0, q1 in zip(stations, stations[1:]):
        if q1-q0 <= TOLERANCE:
            continue
        occupied = material_intervals(materials, (q0+q1)/2.)
        collision = any(min(high, b)-max(low, a) > tolerance
                        for a, b in occupied)
        if not collision:
            allowed.append((q0, q1))
    allowed.append((stations[-1], None))
    merged = []
    for interval in allowed:
        if (merged and merged[-1][1] is not None
                and interval[0] is not None
                and abs(merged[-1][1]-interval[0]) <= TOLERANCE):
            merged[-1] = (merged[-1][0], interval[1])
        else:
            merged.append(interval)
    return GussetContactWindow(stable_key, local_axis, tuple(merged),
                               tuple(contact_surface_ids))


def slot_placements(slot, thickness, materials):
    """Materialize only full-thickness placements that fit and do not collide."""
    if thickness <= 0.:
        raise ValueError("Espessura da chapa deve ser maior que zero.")
    if not slot.open_accessibility:
        return ()
    materials = tuple(materials)
    low, high = slot.free_low, slot.free_high
    if (slot.available_clear_width is not None
            and slot.available_clear_width+.1 < thickness):
        return ()
    values = []
    for placement in slot.allowed_placements:
        if placement == GussetSlotPlacement.NEAR_A and low is not None:
            slab = (low, low+thickness)
        elif placement == GussetSlotPlacement.NEAR_B and high is not None:
            slab = (high-thickness, high)
        elif (placement == GussetSlotPlacement.CENTER
              and low is not None and high is not None):
            middle = (low+high)/2.
            slab = (middle-thickness/2., middle+thickness/2.)
        else:
            continue
        if ((low is not None and slab[0] < low-.1)
                or (high is not None and slab[1] > high+.1)):
            continue
        window = slab_contact_window(slot.stable_key+":"+placement.value,
                                     materials, slab[0], slab[1],
                                     slot.local_axis, slot.contact_surface_ids)
        at_axis = any((low is None or low <= TOLERANCE)
                      and (high is None or high >= -TOLERANCE)
                      for low, high in window.intervals)
        if slot.kind in (GussetAttachmentSlotKind.SURFACE_BAND,
                          GussetAttachmentSlotKind.OPEN_RECESS) and slot.access_sign:
            usable = any((slot.access_sign < 0 and low is None)
                         or (slot.access_sign > 0 and high is None)
                         for low, high in window.intervals)
            if (usable and not at_axis
                    and slot.kind == GussetAttachmentSlotKind.OPEN_RECESS):
                contact = contact_band_support(
                    materials, slab[0], slab[1], slot.access_sign,
                    include_tangent=False)
                extent = material_envelope_support(materials, slot.access_sign)
                usable = (contact is not None and extent is not None
                          and contact < extent-TOLERANCE)
                if usable:
                    # On tapered recesses the exact full-slab contact can
                    # lie between scan stations. Retain only its reachable
                    # open ray, with the same boundary used by contact_band.
                    intervals = (((contact, None),) if slot.access_sign > 0
                                 else ((None, -contact),))
                    window = replace(window, intervals=intervals)
        else:
            usable = at_axis
        if usable:
            values.append((placement, slab[0], slab[1], window))
    return tuple(values)


__all__ = ["contact_band_support", "derive_attachment_slots", "derive_open_recess_slots",
           "derive_surface_band_slot", "recess_is_open",
           "derive_surface_band_slots", "flat_contact_intervals", "material_intervals",
           "material_envelope_support", "slab_contact_window", "slot_placements"]
