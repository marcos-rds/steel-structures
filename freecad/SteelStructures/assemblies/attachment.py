"""Exact section supports and physical attachment, independent of CAD/GUI.

d points from component A to B; n=w cross d (d=u implies n=v). Face A is
+n, Face B is -n. Supports use the transformed contour relative to insertion.
This is envelope attachment, not flange selection, overlap or connection fitting.
"""
from dataclasses import dataclass, replace
from functools import lru_cache
import math
from ..profiles.geometry import ArcSegment2D, build_section_geometry
from ..profiles.validation import ProfileNotFoundError
from .transforms import transform_section
from .validation import unit, cross, finite

ATTACHMENT_TOLERANCE = 1e-6  # mm, geometric coincidence, not manufacturing clearance.


def dot(a, b):
    return sum(x*y for x, y in zip(a, b))


def support(section, direction):
    """Min/max projection; circular-arc extrema are analytical, never sampled."""
    if len(direction) != 2 or not all(finite(v) for v in direction) or math.hypot(*direction) <= 1e-14:
        raise ValueError("Direção de projeção da seção inválida.")
    dx, dy = direction
    values = []
    for path in (section.outer_path,)+section.inner_paths:
        for segment in path.segments:
            values.extend(p.x*dx+p.y*dy for p in (segment.start, segment.end))
            if isinstance(segment, ArcSegment2D):
                angle = math.atan2(dy, dx)
                for theta in (angle, angle+math.pi):
                    travel = ((segment.start_angle-theta) if segment.clockwise else
                              (theta-segment.start_angle)) % math.tau
                    if travel <= abs(segment.sweep)+1e-12:
                        values.append((segment.center.x+segment.radius*math.cos(theta))*dx+
                                      (segment.center.y+segment.radius*math.sin(theta))*dy)
    return min(values), max(values)


def section_at_insertion(element):
    return _section_at_insertion(element.profile_ref, element.section_geometry_mode,
                                 element.section_transform, element.insertion_reference)


@lru_cache(maxsize=256)
def _section_at_insertion(profile_ref, geometry_mode, transform, insertion):
    from .. import profile_catalog
    try:
        designation = profile_catalog.selection_for_ref(profile_ref)[2]
        definition = profile_catalog.get(designation).definition
    except (ProfileNotFoundError, KeyError) as exc:
        raise ValueError("Perfil da ligação não está disponível no catálogo.") from exc
    geometry = build_section_geometry(definition, geometry_mode)
    section, refs = transform_section(geometry, transform)
    reference = next((r.point for r in refs if insertion in (r.id, r.label)), None)
    if reference is None:
        raise ValueError("Referência de inserção incompatível com a seção da ligação.")
    return section, reference


def section_support(element, direction):
    """Support relative to the physical insertion axis, in a world direction."""
    section, reference = section_at_insertion(element)
    projected = (dot(direction, element.orientation.u), dot(direction, element.orientation.v))
    if math.hypot(*projected) <= 1e-14:
        return 0., 0.
    low, high = support(section, projected)
    shift = reference.x*projected[0]+reference.y*projected[1]
    return low-shift, high-shift


def section_band_support(element, origin, direction, normal, band):
    """Exact contour support inside the connector's occupied lateral strip.

    Unlike a whole-section envelope, this reaches recessed faces as well.
    Arc/strip intersections and directional extrema are evaluated analytically.
    """
    section, reference = section_at_insertion(element)
    def coordinates(p):
        relative = tuple(x-o+(p.x-reference.x)*u+(p.y-reference.y)*v
                         for x, o, u, v in zip(element.start_global, origin,
                                              element.orientation.u, element.orientation.v))
        return dot(relative, direction), dot(relative, normal)
    values = []
    for path in (section.outer_path,)+section.inner_paths:
        for segment in path.segments:
            candidates = [segment.start, segment.end]
            if isinstance(segment, ArcSegment2D):
                from ..profiles.geometry import Point2D
                dx, dy = dot(direction, element.orientation.u), dot(direction, element.orientation.v)
                nx, ny = dot(normal, element.orientation.u), dot(normal, element.orientation.v)
                angles = [math.atan2(dy, dx), math.atan2(dy, dx)+math.pi]
                center_n = coordinates(segment.center)[1]
                radius_n = segment.radius*math.hypot(nx, ny)
                if radius_n > 1e-14:
                    for boundary in band:
                        ratio = (boundary-center_n)/radius_n
                        if abs(ratio) <= 1.+1e-12:
                            angle = math.acos(max(-1., min(1., ratio)))
                            angles.extend((math.atan2(ny, nx)+angle, math.atan2(ny, nx)-angle))
                for theta in angles:
                    travel = ((segment.start_angle-theta) if segment.clockwise else
                              (theta-segment.start_angle)) % math.tau
                    if travel <= abs(segment.sweep)+1e-12:
                        candidates.append(Point2D(segment.center.x+segment.radius*math.cos(theta),
                                                  segment.center.y+segment.radius*math.sin(theta)))
            else:
                from ..profiles.geometry import Point2D
                start_n, end_n = coordinates(segment.start)[1], coordinates(segment.end)[1]
                if abs(end_n-start_n) > 1e-14:
                    for boundary in band:
                        t = (boundary-start_n)/(end_n-start_n)
                        if 0. <= t <= 1.:
                            candidates.append(Point2D(segment.start.x+t*(segment.end.x-segment.start.x),
                                                      segment.start.y+t*(segment.end.y-segment.start.y)))
            for p in candidates:
                d, n = coordinates(p)
                if band[0]-ATTACHMENT_TOLERANCE <= n <= band[1]+ATTACHMENT_TOLERANCE:
                    values.append(d)
    if not values:
        raise ValueError("A faixa da chapa não alcança as faces internas dos componentes.")
    return min(values), max(values)


def inner_face_limits(pair, components, component_pair, element, lateral=0.):
    by_key = {c.component_key: c for c in components}
    band = tuple(lateral+s for s in section_support(element, pair.n))
    a = section_band_support(by_key[component_pair[0]], pair.origin, pair.d, pair.n, band)[1]
    b = section_band_support(by_key[component_pair[1]], pair.origin, pair.d, pair.n, band)[0]
    if b-a <= ATTACHMENT_TOLERANCE:
        raise ValueError("Não há espaço livre entre as faces internas para a chapa espaçadora.")
    return a, b


@dataclass(frozen=True)
class PairAttachment:
    origin: tuple
    d: tuple
    n: tuple
    w: tuple
    a_d: tuple
    b_d: tuple
    a_n: tuple
    b_n: tuple

    @property
    def inner_gap(self):
        return self.b_d[0]-self.a_d[1]

    @property
    def outer_span(self):
        return self.b_d[1]-self.a_d[0]

    def spacer_center(self):
        """Center of the common transverse support of the physical sections."""
        low, high = max(self.a_n[0], self.b_n[0]), min(self.a_n[1], self.b_n[1])
        if high-low <= ATTACHMENT_TOLERANCE:
            raise ValueError("Não há sobreposição transversal válida entre as faces internas "
                             "para a chapa espaçadora. Revise a posição dos componentes.")
        return (low+high)/2

    def face_plane(self, face):
        index = 1 if face == "FaceA" else 0
        if face not in ("FaceA", "FaceB"):
            raise ValueError("Selecione Face A ou Face B.")
        if abs(self.a_n[index]-self.b_n[index]) > ATTACHMENT_TOLERANCE:
            raise ValueError("As superfícies selecionadas dos componentes não são coplanares.")
        return self.a_n[index]


def resolve_pair_attachment(nominal_axis, components, component_pair):
    from .interconnectors import validate_pair
    a, b, w, _, _ = validate_pair(components, component_pair, nominal_axis)
    d = unit(tuple(y-x for x, y in zip(a.start_global, b.start_global)))
    n = cross(w, d)
    origin = a.start_global
    def physical(element, direction):
        offset = dot(tuple(x-y for x, y in zip(element.start_global, origin)), direction)
        return tuple(offset+s for s in section_support(element, direction))
    return PairAttachment(origin, d, n, w, physical(a, d), physical(b, d), physical(a, n), physical(b, n))


def attach_elements(nominal_axis, components, spec, elements):
    """Keep primary C4-A identity; Both adds only a SECONDARY identity branch."""
    if spec.attachment_plane == "AxisToAxis" or not elements:
        return tuple(elements)
    pair = resolve_pair_attachment(nominal_axis, components, spec.component_pair)
    faces = ("FaceA", "FaceB") if spec.attachment_plane == "Both" else (spec.attachment_plane,)
    output = []
    for face_index, face in enumerate(faces):
        plane = pair.face_plane(face) if face != "InnerFaces" else 0.
        for element in elements:
            # Frame is preserved from the axis resolver. n is orthogonal to
            # every connector axis, including inclined longitudinal lacing.
            low, high = section_support(element, pair.n)
            lateral = plane-(low if face == "FaceA" else high) if face != "InnerFaces" else plane
            inner = None
            if spec.kind == "SpacerPlate":
                lateral = pair.spacer_center()-(low+high)/2
                inner = inner_face_limits(pair, components, spec.component_pair, element, lateral)
            def attached(point, at_start):
                relative = tuple(x-y for x, y in zip(point, pair.origin))
                separation = dot(relative, pair.d)
                if spec.kind == "SpacerPlate":
                    separation = inner[0] if at_start else inner[1]
                elif spec.kind == "Battens":
                    separation = pair.a_d[0] if at_start else pair.b_d[1]
                longitudinal = dot(relative, pair.w)
                return tuple(o+separation*d+lateral*n+longitudinal*w
                             for o, d, n, w in zip(pair.origin, pair.d, pair.n, pair.w))
            output.append(replace(element,
                start_global=attached(element.start_global, True), end_global=attached(element.end_global, False),
                stable_identity=element.stable_identity+(("SECONDARY",) if face_index else ()),
                generated_element_key=element.generated_element_key+("_SECONDARY" if face_index else ""),
                attachment_plane=face,
                label=element.label+(" / Face A" if face == "FaceA" else " / Face B" if face == "FaceB" else "")))
    return tuple(output)
