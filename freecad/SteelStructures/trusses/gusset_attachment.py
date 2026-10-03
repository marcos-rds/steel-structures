"""Pure pre-fitting derivation of longitudinal gusset connection surfaces."""

import math
from dataclasses import replace

from ..assemblies.attachment import support
from ..connections import (GussetConnectionSurface, GussetSectionMaterial2D,
                           GussetSide, GussetSurfaceClass)
from ..connections.slots import derive_attachment_slots
from ..profiles.geometry import ArcSegment2D, LineSegment2D
from ..profiles.preview_geometry import section_path_points
from .assemblies import assembly_frame
from .fitting_geometry import _section_at_insertion

TOLERANCE = 1e-7
SURFACE_ANGLE_TOLERANCE_DEGREES = 2.0
SURFACE_OFFSET_VARIATION_TOLERANCE = 0.1


def _dot(a, b):
    return sum(x*y for x, y in zip(a, b))


def _cross(a, b):
    return (a[1]*b[2]-a[2]*b[1],
            a[2]*b[0]-a[0]*b[2],
            a[0]*b[1]-a[1]*b[0])


def _unit(value):
    length = math.sqrt(_dot(value, value))
    if length <= TOLERANCE:
        raise ValueError("Direção degenerada ao resolver superfície de ligação.")
    return tuple(component/length for component in value)


def _cross2(first, second):
    return first[0]*second[1]-first[1]*second[0]


def _surface_free_space(section, segment, outward):
    """Distance to the first material boundary along the surface free side.

    Three deterministic stations avoid endpoint adjacency artifacts.  Curved
    contour portions use the section module's canonical sampling; no OCC face
    or profile-family name participates in the decision.
    """
    polygon = section_path_points(section.outer_path)
    edges = tuple(zip(polygon, polygon[1:]))
    clearances = []
    for fraction in (.2, .5, .8):
        origin = (segment.start.x+fraction*(segment.end.x-segment.start.x),
                  segment.start.y+fraction*(segment.end.y-segment.start.y))
        hits = []
        for start, end in edges:
            edge = (end.x-start.x, end.y-start.y)
            determinant = _cross2(outward, edge)
            if abs(determinant) <= TOLERANCE:
                continue
            delta = (start.x-origin[0], start.y-origin[1])
            distance = _cross2(delta, edge)/determinant
            parameter = _cross2(delta, outward)/determinant
            if distance > 1e-5 and -TOLERANCE <= parameter <= 1.+TOLERANCE:
                hits.append(distance)
        if hits:
            clearances.append(min(hits))
    return min(clearances) if clearances else None


def component_connection_surfaces(item, participant, node_global, truss_normal,
                                  angle_tolerance_degrees=SURFACE_ANGLE_TOLERANCE_DEGREES):
    """Return accessible planar outer-contour faces parallel to the truss plane."""
    normal = _unit(truss_normal)
    frame = assembly_frame((item.start_global, item.end_global),
                           item.section_u_global, item.spec.rotation)
    section, insertion = _section_at_insertion(item)
    component_axis_offset = _dot(tuple(
        value-origin for value, origin in zip(item.start_global, node_global)), normal)
    cosine = math.cos(math.radians(angle_tolerance_degrees))
    # Section paths are normally counter-clockwise, but transformed or legacy
    # geometries are allowed to reverse their winding.  A candidate surface
    # must use the *outward* contour normal: the right-hand normal for CCW and
    # the left-hand normal for CW.  This remains purely SectionGeometry2D based.
    winding_area = section.outer_path.signed_area
    if abs(winding_area) <= TOLERANCE:
        raise ValueError("Contorno externo degenerado ao resolver superfície de ligação.")
    counter_clockwise = winding_area > 0.
    bounds = section.bounds
    section_scale = math.hypot(bounds.max_x-bounds.min_x,
                               bounds.max_y-bounds.min_y)
    classification_tolerance = max(1e-6, section_scale*1e-9)
    section_normal = (_dot(normal, frame.u), _dot(normal, frame.v))
    band_low, band_high = support(section, section_normal)
    insertion_normal = insertion[0]*section_normal[0]+insertion[1]*section_normal[1]
    band_low += component_axis_offset+insertion_normal
    band_high += component_axis_offset+insertion_normal
    surfaces = []
    for index, segment in enumerate(section.outer_path.segments):
        if not isinstance(segment, LineSegment2D):
            continue
        dx, dy = segment.end.x-segment.start.x, segment.end.y-segment.start.y
        length = math.hypot(dx, dy)
        if length <= TOLERANCE:
            continue
        tangent = tuple((dx/length)*u+(dy/length)*v
                        for u, v in zip(frame.u, frame.v))
        local_outward = ((dy/length, -dx/length) if counter_clockwise
                         else (-dy/length, dx/length))
        outward = _unit(_cross(tangent, frame.w) if counter_clockwise
                        else _cross(frame.w, tangent))
        alignment = _dot(outward, normal)
        if abs(alignment) < cosine:
            continue
        outward_sign = 1 if alignment > 0. else -1
        section_points = tuple((point.x+insertion[0], point.y+insertion[1])
                               for point in (segment.start, segment.end))
        physical_points = tuple(tuple(
            item.start_global[i]+point[0]*frame.u[i]+point[1]*frame.v[i]
            for i in range(3)) for point in section_points)
        endpoint_offsets = tuple(_dot(tuple(
            value-origin for value, origin in zip(point, node_global)), normal)
            for point in physical_points)
        if abs(endpoint_offsets[1]-endpoint_offsets[0]) > SURFACE_OFFSET_VARIATION_TOLERANCE:
            continue
        offset = sum(endpoint_offsets)/2.
        error = math.degrees(math.acos(max(-1., min(1., abs(alignment)))))
        _low_support, high_support = support(section, local_outward)
        middle_local = ((segment.start.x+segment.end.x)/2.,
                        (segment.start.y+segment.end.y)/2.)
        segment_support = _dot(middle_local, local_outward)
        recess_depth = max(0., high_support-segment_support)
        surface_class = (GussetSurfaceClass.OUTER
                         if recess_depth <= classification_tolerance
                         else GussetSurfaceClass.INNER)
        free_space = _surface_free_space(section, segment, local_outward)
        surface_role = ("Chord" if participant.role in ("TOP_CHORD", "BOTTOM_CHORD")
                        else "Through" if participant.end == "Through" else "Web")
        surfaces.append((length, GussetConnectionSurface(
            participant.participant_key, item.run_key, item.component_key,
            "outer:"+str(index), participant.role, participant.end,
            outward, offset,
            ((segment.start.x+insertion[0], segment.start.y+insertion[1]),
             (segment.end.x+insertion[0], segment.end.y+insertion[1])),
            GussetSide.FACE_A if outward_sign > 0 else GussetSide.FACE_B,
            outward_sign, error, length, surface_role,
            surface_class, recess_depth, component_axis_offset, free_space,
            band_low, band_high)))
    # Fillets or path partitioning can leave several collinear fragments of
    # the same physical face. Keep one stable, longest representative.
    grouped = {}
    for length, surface in surfaces:
        key = (surface.participant_key, surface.component_key, surface.outward_sign,
               surface.surface_class.value,
               round(surface.signed_offset, 6))
        current = grouped.get(key)
        if current is None or (-length, surface.surface_id) < (-current[0], current[1].surface_id):
            grouped[key] = (length, surface)
    ordered = [value[1] for _key, value in sorted(
        grouped.items(), key=lambda item: (
            item[1][1].surface_class.value,
            item[1][1].outward_sign,
            item[1][1].signed_offset,
            -item[1][1].contact_extent,
            item[1][1].surface_id))]
    counts, result = {}, []
    for surface in ordered:
        family = (surface.surface_class.value,
                  "A" if surface.outward_sign > 0 else "B")
        ordinal = counts.get(family, 0)
        counts[family] = ordinal+1
        result.append(replace(
            surface, surface_id="longitudinal:%s:%s:%d" % (
                family[0], family[1], ordinal)))
    return tuple(result)


def component_section_material(item, participant, node_global, truss_normal):
    """Return transformed nominal section material in a pure local 2D frame."""
    normal = _unit(truss_normal)
    axis = _unit(tuple(end-start for start, end in
                       zip(item.start_global, item.end_global)))
    local_axis = _unit(_cross(normal, axis))
    frame = assembly_frame((item.start_global, item.end_global),
                           item.section_u_global, item.spec.rotation)
    section, insertion = _section_at_insertion(item)

    def path_points(path):
        # Bound the chord error of curved section geometry to 0.01 mm.  The
        # historical preview sampling uses 12 points per arc irrespective of
        # radius and is not precise enough for collision/contact decisions.
        points = [path.segments[0].start]
        for segment in path.segments:
            if isinstance(segment, ArcSegment2D):
                radius = segment.radius
                angle = 2.*math.acos(max(-1., min(1., 1.-.01/radius)))
                count = max(1, int(math.ceil(abs(segment.sweep)/angle)))
                points.extend(segment.sampled_points(count))
            else:
                points.append(segment.end)
        if len(points) > 1 and points[0] == points[-1]:
            points = points[:-1]
        result = []
        for point in points:
            x, y = point.x+insertion[0], point.y+insertion[1]
            global_point = tuple(item.start_global[index]
                                 +x*frame.u[index]+y*frame.v[index]
                                 for index in range(3))
            relative = tuple(value-origin for value, origin in
                             zip(global_point, node_global))
            result.append((_dot(relative, normal),
                           _dot(relative, local_axis)))
        return tuple(result)

    return GussetSectionMaterial2D(
        participant.participant_key, item.component_key,
        path_points(section.outer_path),
        tuple(path_points(path) for path in section.inner_paths), local_axis)


def connection_surfaces(candidate, participants, local_frame):
    """Resolve all participant surfaces without reading generated member Shapes."""
    node_key = participants[0].node_key if participants else ""
    if not node_key:
        return ()
    node = candidate.graph.node(node_key)
    from .realization import transform_point
    node_global = transform_point(node.position_local, local_frame)
    items = [item for item in candidate.items if item.element_kind == "Component"]
    result = []
    for participant in sorted(participants, key=lambda value: value.participant_key):
        for item in sorted((value for value in items
                            if value.run_key in participant.physical_run_keys),
                           key=lambda value: (value.run_key, value.component_key, value.key)):
            result.extend(component_connection_surfaces(
                item, participant, node_global, local_frame[3]))
    return tuple(result)


def attachment_slot_geometry(candidate, participants, local_frame):
    """Return connection surfaces, transformed material and semantic slots."""
    node_key = participants[0].node_key if participants else ""
    if not node_key:
        return (), (), ()
    node = candidate.graph.node(node_key)
    from .realization import transform_point
    node_global = transform_point(node.position_local, local_frame)
    items = [item for item in candidate.items if item.element_kind == "Component"]
    surfaces, materials, slots = [], [], []
    for participant in sorted(participants, key=lambda value: value.participant_key):
        participant_items = sorted((value for value in items
                                    if value.run_key in participant.physical_run_keys),
                                   key=lambda value: (value.run_key,
                                                      value.component_key, value.key))
        participant_surfaces, participant_materials = [], []
        for item in participant_items:
            participant_surfaces.extend(component_connection_surfaces(
                item, participant, node_global, local_frame[3]))
            participant_materials.append(component_section_material(
                item, participant, node_global, local_frame[3]))
        surfaces.extend(participant_surfaces)
        materials.extend(participant_materials)
        slots.extend(derive_attachment_slots(
            participant.participant_key, tuple(local_frame[3]),
            participant_materials, participant_surfaces))
    return tuple(surfaces), tuple(materials), tuple(slots)


__all__ = ["SURFACE_ANGLE_TOLERANCE_DEGREES", "SURFACE_OFFSET_VARIATION_TOLERANCE",
           "component_connection_surfaces", "component_section_material",
           "connection_surfaces", "attachment_slot_geometry"]
