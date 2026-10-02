"""Pure deterministic preliminary gusset-plate geometry."""

import math

from .models import (GUSSET_PLATE_SCHEMA_VERSION, GussetOutline,
                     GussetOutlineEdge, GussetPlateSpec)

TOLERANCE = 1e-7


def _finite(values):
    return all(isinstance(value, (int, float)) and not isinstance(value, bool)
               and math.isfinite(value) for value in values)


def _cross(a, b, c):
    return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])


def _hull(points):
    points = sorted(set((round(float(x), 10), round(float(y), 10)) for x, y in points))
    if len(points) < 3:
        raise ValueError("O contorno da chapa é degenerado.")
    lower = []
    for point in points:
        while len(lower) >= 2 and _cross(lower[-2], lower[-1], point) <= TOLERANCE:
            lower.pop()
        lower.append(point)
    upper = []
    for point in reversed(points):
        while len(upper) >= 2 and _cross(upper[-2], upper[-1], point) <= TOLERANCE:
            upper.pop()
        upper.append(point)
    result = tuple(lower[:-1]+upper[:-1])
    if len(result) < 3:
        raise ValueError("O contorno da chapa é degenerado.")
    return result


def polygon_area(points):
    return .5*sum(a[0]*b[1]-a[1]*b[0]
                  for a, b in zip(points, points[1:]+points[:1]))


def _canonical_axis(value):
    length = math.hypot(*value)
    if length <= TOLERANCE:
        raise ValueError("Direção nula em participante da chapa.")
    result = value[0]/length, value[1]/length
    if result[0] < -TOLERANCE or (abs(result[0]) <= TOLERANCE and result[1] < 0.):
        result = -result[0], -result[1]
    return result


def _regularized_envelope(points, corridors, margin):
    """Convex k-DOP whose supports come only from participant frames."""
    axes = {}
    for corridor in corridors:
        direction = _canonical_axis(corridor.direction)
        perpendicular = _canonical_axis((-direction[1], direction[0]))
        for axis in (direction, perpendicular):
            axes[(round(axis[0], 9), round(axis[1], 9))] = axis
    constraints = []
    for axis in (axes[key] for key in sorted(axes)):
        projections = [axis[0]*point[0]+axis[1]*point[1] for point in points]
        low, high = min(projections)-margin, max(projections)+margin
        constraints.extend(((axis, high), ((-axis[0], -axis[1]), -low)))
    vertices = []
    for index, (first, first_offset) in enumerate(constraints):
        for second, second_offset in constraints[index+1:]:
            determinant = first[0]*second[1]-first[1]*second[0]
            if abs(determinant) <= TOLERANCE:
                continue
            point = ((first_offset*second[1]-first[1]*second_offset)/determinant,
                     (first[0]*second_offset-first_offset*second[0])/determinant)
            if all(normal[0]*point[0]+normal[1]*point[1] <= offset+TOLERANCE
                   for normal, offset in constraints):
                vertices.append(point)
    if len(vertices) < 3:
        raise ValueError("As linhas suporte dos participantes não formam região fechada.")
    return _clean_polygon(_hull(vertices))


def _clean_polygon(points):
    """Remove numerical duplicate/collinear vertices without changing the region."""
    result = []
    for point in points:
        point = (round(float(point[0]), 10), round(float(point[1]), 10))
        if not result or math.hypot(point[0]-result[-1][0], point[1]-result[-1][1]) > TOLERANCE:
            result.append(point)
    if len(result) > 1 and math.hypot(result[0][0]-result[-1][0],
                                      result[0][1]-result[-1][1]) <= TOLERANCE:
        result.pop()
    changed = True
    while changed and len(result) >= 3:
        changed = False
        cleaned = []
        count = len(result)
        for index, point in enumerate(result):
            previous, following = result[index-1], result[(index+1) % count]
            scale = max(1., math.hypot(point[0]-previous[0], point[1]-previous[1]),
                        math.hypot(following[0]-point[0], following[1]-point[1]))
            if abs(_cross(previous, point, following)) <= TOLERANCE*scale:
                changed = True
            else:
                cleaned.append(point)
        result = cleaned
    if len(result) < 3:
        raise ValueError("A reconstrução por linhas suporte produziu contorno degenerado.")
    return tuple(result)


def _clip_support(points, support):
    """Clip a convex CCW polygon by one physical half-plane."""
    nx, ny = support.normal
    signed = lambda point: nx*point[0]+ny*point[1]-support.offset
    result = []
    previous = points[-1]
    previous_distance = signed(previous)
    previous_inside = previous_distance <= TOLERANCE
    for current in points:
        current_distance = signed(current)
        current_inside = current_distance <= TOLERANCE
        if current_inside != previous_inside:
            denominator = previous_distance-current_distance
            if abs(denominator) <= TOLERANCE:
                raise ValueError("Interseção instável com linha suporte do banzo.")
            ratio = previous_distance/denominator
            result.append((previous[0]+ratio*(current[0]-previous[0]),
                           previous[1]+ratio*(current[1]-previous[1])))
        if current_inside:
            result.append(current)
        previous, previous_distance, previous_inside = (
            current, current_distance, current_inside)
    if len(result) < 3:
        raise ValueError("As linhas suporte do banzo eliminaram a região útil da chapa.")
    return _clean_polygon(result)


def _line_intersection(first_start, first_end, second_start, second_end):
    first = (first_end[0]-first_start[0], first_end[1]-first_start[1])
    second = (second_end[0]-second_start[0], second_end[1]-second_start[1])
    determinant = first[0]*second[1]-first[1]*second[0]
    if abs(determinant) <= TOLERANCE:
        return None
    delta = (second_start[0]-first_start[0], second_start[1]-first_start[1])
    parameter = (delta[0]*second[1]-delta[1]*second[0])/determinant
    return (first_start[0]+parameter*first[0],
            first_start[1]+parameter*first[1])


def _inside_convex(points, point):
    return all(_cross(first, second, point) >= -TOLERANCE
               for first, second in zip(points, points[1:]+points[:1]))


def _edge_on_semantic_support(first, second, supports):
    for support in supports:
        first_distance = (support.normal[0]*first[0]
                          +support.normal[1]*first[1]-support.offset)
        second_distance = (support.normal[0]*second[0]
                           +support.normal[1]*second[1]-support.offset)
        if max(abs(first_distance), abs(second_distance)) <= 2e-6:
            return True
    return False


def semantic_outline_regularization(points, supports=()):
    """Collapse short, non-semantic k-DOP chamfers into a direct corner.

    The operation is intentionally conservative and scale-relative.  Chord
    boundaries and web end caps are protected by provenance, while a free
    facet is removed only if both governing neighbours are substantially
    longer and their intersection contains the original polygon without
    violating any semantic half-plane.
    """
    result = list(_clean_polygon(points))
    supports = tuple(supports)
    changed = True
    while changed and len(result) > 3:
        changed = False
        count = len(result)
        for index in range(count):
            first, second = result[index], result[(index+1) % count]
            previous, following = result[index-1], result[(index+2) % count]
            length = math.hypot(second[0]-first[0], second[1]-first[1])
            previous_length = math.hypot(first[0]-previous[0], first[1]-previous[1])
            following_length = math.hypot(following[0]-second[0],
                                          following[1]-second[1])
            if (length > .18*max(previous_length, following_length)
                    or _edge_on_semantic_support(first, second, supports)):
                continue
            intersection = _line_intersection(previous, first, second, following)
            if intersection is None or not _finite(intersection):
                continue
            local_scale = max(previous_length, following_length, 1.)
            if max(math.hypot(intersection[0]-first[0], intersection[1]-first[1]),
                   math.hypot(intersection[0]-second[0], intersection[1]-second[1])) > local_scale:
                continue
            rotated = result[index:]+result[:index]
            candidate = _clean_polygon((intersection,)+tuple(rotated[2:]))
            if polygon_area(candidate) <= TOLERANCE:
                continue
            if any(not _inside_convex(candidate, point) for point in result):
                continue
            if any(support.normal[0]*intersection[0]
                   +support.normal[1]*intersection[1] > support.offset+TOLERANCE
                   for support in supports):
                continue
            result = list(candidate)
            changed = True
            break
    return _clean_polygon(result)


def _candidate_preserves_outline(candidate, previous, supports):
    return (polygon_area(candidate) > TOLERANCE
            and all(_inside_convex(candidate, point) for point in previous)
            and all(support.normal[0]*point[0]+support.normal[1]*point[1]
                    <= support.offset+TOLERANCE
                    for support in supports for point in candidate))


def _regularize_web_cap_chains(points, supports):
    """Extend each active web cap to its adjacent governing boundaries.

    k-DOP may leave one intermediary, non-semantic facet next to a cap.  The
    cap replaces that facet only when the direct intersection expands the old
    convex region safely and respects every chord/other-web support.
    """
    result = list(_clean_polygon(points))
    caps = tuple(value for value in supports if value.kind == "WEB_END_CAP")
    for cap in caps:
        for side in ("before", "after"):
            # One intermediary facet is the C6-E target.  Do not keep walking
            # through a legitimate corridor side toward a remote chord corner.
            for _attempt in range(1):
                count = len(result)
                cap_index = next((index for index in range(count)
                                  if _edge_on_semantic_support(
                                      result[index], result[(index+1) % count], (cap,))), None)
                if cap_index is None:
                    break
                if side == "before":
                    adjacent = (result[cap_index-1], result[cap_index])
                    if _edge_on_semantic_support(*adjacent, supports):
                        break
                    rotated = result[cap_index-2:]+result[:cap_index-2]
                    # q,p,a,b -> q,(q-p intersect cap),b
                    intersection = _line_intersection(
                        rotated[0], rotated[1], rotated[2], rotated[3])
                    candidate = ((rotated[0], intersection, rotated[3])
                                 +tuple(rotated[4:])) if intersection else ()
                    local_scale = (math.dist(rotated[0], rotated[1])
                                   +math.dist(rotated[1], rotated[2]))
                else:
                    adjacent = (result[(cap_index+1) % count],
                                result[(cap_index+2) % count])
                    if _edge_on_semantic_support(*adjacent, supports):
                        break
                    rotated = result[cap_index:]+result[:cap_index]
                    # a,b,p,q -> a,(cap intersect p-q),q
                    intersection = _line_intersection(
                        rotated[0], rotated[1], rotated[2], rotated[3])
                    candidate = ((rotated[0], intersection, rotated[3])
                                 +tuple(rotated[4:])) if intersection else ()
                    local_scale = (math.dist(rotated[1], rotated[2])
                                   +math.dist(rotated[2], rotated[3]))
                if (not candidate or not _finite(intersection)
                        or min(math.dist(intersection, adjacent[0]),
                               math.dist(intersection, adjacent[1])) > 3.*max(local_scale, 1.)):
                    break
                candidate = _clean_polygon(candidate)
                if not _candidate_preserves_outline(candidate, result, supports):
                    break
                result = list(candidate)
    return _clean_polygon(result)


def _semantic_edges(points, supports):
    result = []
    for first, second in zip(points, points[1:]+points[:1]):
        support = next((value for value in supports
                        if _edge_on_semantic_support(first, second, (value,))), None)
        if support is None:
            kind, participant_key, direction = "FREE_MARGIN", "", ()
        else:
            kind = support.kind
            participant_key = support.participant_key
            direction = support.direction
        result.append(GussetOutlineEdge(first, second, kind,
                                        participant_key, direction))
    return tuple(result)


def _validated_supports(supports):
    priorities = {"TERMINAL_BOUNDARY": 0, "CHORD_BOUNDARY": 1,
                  "WEB_END_CAP": 2, "WEB_SECTOR_BRIDGE": 3,
                  "REQUIRED_CORRIDOR": 4, "FREE_MARGIN": 5,
                  "ChordOuterBoundary": 0}
    result = {}
    for support in supports:
        if (not support.participant_key or len(support.direction) != 2
                or len(support.normal) != 2
                or not _finite(tuple(support.direction)+tuple(support.normal)+(support.offset,))):
            raise ValueError("Linha suporte semântica da chapa é inválida.")
        direction_length = math.hypot(*support.direction)
        normal_length = math.hypot(*support.normal)
        if (abs(direction_length-1.) > TOLERANCE or abs(normal_length-1.) > TOLERANCE
                or abs(sum(a*b for a, b in zip(support.direction, support.normal))) > TOLERANCE):
            raise ValueError("Linha suporte semântica da chapa deve possuir frame ortonormal.")
        key = (round(support.normal[0], 9), round(support.normal[1], 9),
               round(support.offset, 7))
        current = result.get(key)
        if current is None or priorities.get(support.kind, 99) < priorities.get(current.kind, 99):
            result[key] = support
    return tuple(result[key] for key in sorted(result))


def validate_gusset_spec(spec):
    if spec.schema_version != GUSSET_PLATE_SCHEMA_VERSION:
        raise ValueError("Versão de GussetPlateSpec não suportada.")
    if not spec.stable_key or not spec.node_key:
        raise ValueError("A chapa requer identidades semânticas estáveis.")
    if not _finite((spec.plate_thickness, spec.edge_margin, spec.member_overlap)):
        raise ValueError("As dimensões da chapa devem ser finitas.")
    if spec.plate_thickness <= 0:
        raise ValueError("Espessura da chapa deve ser maior que zero.")
    if spec.member_overlap <= 0:
        raise ValueError("Sobreposição nos membros deve ser maior que zero.")
    if spec.edge_margin < 0:
        raise ValueError("Margem de borda deve ser maior ou igual a zero.")
    if len(set(spec.participant_keys)) < 2:
        raise ValueError("A chapa requer ao menos dois participantes úteis.")
    if spec.frame is None:
        raise ValueError("O frame local da chapa não está disponível.")
    if len(spec.frame.origin) != 3 or not _finite(spec.frame.origin):
        raise ValueError("A origem do frame local da chapa é inválida.")
    axes = (spec.frame.x_axis, spec.frame.y_axis, spec.frame.normal)
    if any(len(axis) != 3 or not _finite(axis) for axis in axes):
        raise ValueError("O frame local da chapa é inválido.")
    dot = lambda a, b: sum(x*y for x, y in zip(a, b))
    if any(abs(dot(axis, axis)-1.) > TOLERANCE for axis in axes) or any(
            abs(dot(a, b)) > TOLERANCE for a, b in ((axes[0], axes[1]),
                                                     (axes[0], axes[2]),
                                                     (axes[1], axes[2]))):
        raise ValueError("O frame local da chapa deve ser ortonormal.")
    cross = (axes[0][1]*axes[1][2]-axes[0][2]*axes[1][1],
             axes[0][2]*axes[1][0]-axes[0][0]*axes[1][2],
             axes[0][0]*axes[1][1]-axes[0][1]*axes[1][0])
    if any(abs(a-b) > TOLERANCE for a, b in zip(cross, axes[2])):
        raise ValueError("O frame local da chapa deve ser destrógiro.")
    return spec


def build_gusset_outline(spec, corridors, support_lines=()):
    """Build the required corridor region and regularize it by chord boundaries.

    EdgeMargin remains a free clearance around participant corridors.  A chord
    outer-face support is then a governing physical limit: the free margin is
    clipped there instead of inflating the plate beyond that face.
    """
    validate_gusset_spec(spec)
    corridors = tuple(corridors)
    if len(corridors) < 2:
        raise ValueError("A chapa requer ao menos dois envelopes físicos úteis.")
    points = []
    for corridor in corridors:
        dx, dy = corridor.direction
        if not _finite((dx, dy, corridor.transverse_low, corridor.transverse_high)):
            raise ValueError("Envelope físico do participante é inválido.")
        length = math.hypot(dx, dy)
        if length <= TOLERANCE:
            raise ValueError("Direção nula em participante da chapa.")
        dx, dy = dx/length, dy/length
        px, py = -dy, dx
        for station in (0., spec.member_overlap):
            for transverse in (corridor.transverse_low, corridor.transverse_high):
                points.append((station*dx+transverse*px,
                               station*dy+transverse*py))
    hull = _regularized_envelope(points, corridors, spec.edge_margin)
    supports = _validated_supports(tuple(support_lines))
    for support in supports:
        nx, ny = support.normal
        for corridor in corridors:
            dx, dy = corridor.direction
            length = math.hypot(dx, dy)
            dx, dy = dx/length, dy/length
            px, py = -dy, dx
            for transverse in (corridor.transverse_low, corridor.transverse_high):
                required = (spec.member_overlap*dx+transverse*px,
                            spec.member_overlap*dy+transverse*py)
                if (support.kind not in ("TERMINAL_BOUNDARY", "CHORD_BOUNDARY",
                                         "FREE_MARGIN")
                        and nx*required[0]+ny*required[1] > support.offset+TOLERANCE):
                    raise ValueError(
                        "Linha suporte semântica não preserva a sobreposição requerida nos participantes.")
        hull = _clip_support(hull, support)
    hull = _regularize_web_cap_chains(hull, supports)
    hull = semantic_outline_regularization(hull, supports)
    area = polygon_area(hull)
    if not math.isfinite(area) or area <= TOLERANCE:
        raise ValueError("O contorno final da chapa é degenerado.")
    return GussetOutline(spec, hull, area,
                         semantic_edges=_semantic_edges(hull, supports))


def extrusion_limits(spec):
    """Signed distances from the nominal plate plane for the requested side."""
    validate_gusset_spec(spec)
    if spec.side.value == "Center":
        return -spec.plate_thickness/2., spec.plate_thickness/2.
    if spec.side.value == "FaceA":
        return 0., spec.plate_thickness
    return -spec.plate_thickness, 0.


def outline_extrusion_limits(outline):
    """Absolute limits along frame.normal, including physical attachment."""
    if outline.attachment is None:
        return extrusion_limits(outline.spec)
    return outline.attachment.plate_low, outline.attachment.plate_high
