"""Pure transverse preview using the exact C3-A section and insertion transform."""
import math
from ..profiles.geometry import build_section_geometry, Point2D, ArcSegment2D
from ..assemblies.transforms import SectionTransform, transform_section
from .assemblies import role_assembly_spec, role_profile


def role_realization(role, nominal_length):
    from ..assemblies.resolver import resolve_member_assembly
    from .assemblies import assembly_frame
    axis = ((0., 0., 0.), (0., 0., nominal_length))
    frame = assembly_frame(axis, (1., 0., 0.), role["rotation"])
    return resolve_member_assembly(axis, frame, role_assembly_spec(role))


def _hull(points):
    points = sorted(set(points))
    def cross(a, b, c):
        return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
    lower, upper = [], []
    for sequence, chain in ((points, lower), (reversed(points), upper)):
        for p in sequence:
            while len(chain) > 1 and cross(chain[-2], chain[-1], p) <= 0:
                chain.pop()
            chain.append(p)
    return tuple(Point2D(*p) for p in lower[:-1]+upper[:-1])


def transverse_preview(role, nominal_length=1000.):
    assembly = role_assembly_spec(role)
    geometry = build_section_geometry(role_profile(role), role["section_geometry_mode"])
    roll = SectionTransform(role["rotation"])
    components = []
    for component in assembly.components:
        section, references = transform_section(geometry, component.section_transform)
        reference = next((r for r in references if component.insertion_reference in (r.id, r.label)), None)
        if reference is None:
            raise ValueError("Inserção incompatível com o perfil da composição.")
        dx, dy = component.transverse_translation

        def point(p):
            return roll.point(Point2D(p.x-reference.point.x+dx, p.y-reference.point.y+dy))

        paths = []
        for path in (section.outer_path,)+section.inner_paths:
            points = [point(path.segments[0].start)]
            for segment in path.segments:
                sampled = (segment.sampled_points(max(8, math.ceil(abs(segment.sweep)*12)))
                           if isinstance(segment, ArcSegment2D) else (segment.end,))
                points.extend(point(p) for p in sampled)
            paths.append(tuple(points))
        components.append(dict(key=component.component_key, paths=tuple(paths),
                               insertion=roll.point(Point2D(dx, dy)), color=component.color))
    attachments, faces = [], []
    if assembly.interconnectors:
        from ..assemblies.attachment import section_at_insertion, resolve_pair_attachment
        realization = role_realization(role, nominal_length)
        seen = set()
        for item in realization.interconnectors:
            identity = (item.interconnector_key, item.attachment_plane)
            if identity in seen:
                continue
            seen.add(identity)
            section, insertion = section_at_insertion(item)
            # Projection of one representative member per plane. Physical
            # endpoints/frame come from the same resolver as the document.
            points = []
            for segment in section.outer_path.segments:
                samples = (segment.start,)+ (segment.sampled_points(24) if isinstance(segment, ArcSegment2D) else (segment.end,))
                for p in samples:
                    for end in (item.start_global, item.end_global):
                        points.append(tuple(end[i]+(p.x-insertion.x)*item.orientation.u[i]+
                                            (p.y-insertion.y)*item.orientation.v[i] for i in (0, 1)))
            attachments.append(dict(paths=(_hull(points),), color=item.color))
        pair = resolve_pair_attachment(realization.nominal_axis, realization.components,
                                       assembly.interconnectors[0].component_pair)
        for face, label in (("FaceA", "A"), ("FaceB", "B")):
            try:
                plane = pair.face_plane(face)
            except ValueError:
                continue
            endpoints = tuple(Point2D(*(pair.origin[i]+d*pair.d[i]+plane*pair.n[i] for i in (0, 1)))
                              for d in (pair.a_d[0]-10, pair.b_d[1]+10))
            faces.append(dict(label=label, points=endpoints,
                selected=any(s.attachment_plane in (face, "Both") for s in assembly.interconnectors)))
    points = [p for c in components+attachments for path in c["paths"] for p in path]+[Point2D(0, 0)]
    points += [p for face in faces for p in face["points"]]
    return dict(components=tuple(components), spacing=assembly.component_spacing,
                attachments=tuple(attachments), faces=tuple(faces),
                bounds=(min(p.x for p in points), min(p.y for p in points),
                        max(p.x for p in points), max(p.y for p in points)))


def longitudinal_preview(role, nominal_length):
    from ..assemblies.attachment import dot, section_at_insertion, section_support
    from ..assemblies.validation import unit
    realized = role_realization(role, nominal_length)
    if len(realized.components) < 2:
        return dict(lines=(), stations=(), distributions=(), length=nominal_length)
    a, b = realized.components
    d = unit(tuple(y-x for x, y in zip(a.start_global, b.start_global)))
    def point(p):
        delta = tuple(x-y for x, y in zip(p, a.start_global))
        return dot(delta, realized.member_frame.w), dot(delta, d)
    lines = tuple(dict(start=point(c.start_global), end=point(c.end_global), color=c.color,
                       component=c in realized.components,
                       secondary=getattr(c, "attachment_plane", "") == "FaceB") for c in realized.elements)
    for c, line in zip(realized.elements, lines):
        if line["component"]:
            continue
        section, insertion = section_at_insertion(c)
        projected = []
        for segment in section.outer_path.segments:
            samples = (segment.start,)+(segment.sampled_points(32)
                       if isinstance(segment, ArcSegment2D) else (segment.end,))
            for p in samples:
                for end in (c.start_global, c.end_global):
                    projected.append(point(tuple(end[i]+(p.x-insertion.x)*c.orientation.u[i]+
                        (p.y-insertion.y)*c.orientation.v[i] for i in range(3))))
        line["outline"] = tuple((p.x, p.y) for p in _hull(projected))
        low, high = section_support(c, realized.member_frame.w)
        line["longitudinal_bounds"] = (min(line["start"][0], line["end"][0])+low,
                                        max(line["start"][0], line["end"][0])+high)
    stations = tuple(s.position for _, distribution in realized.distributions for s in distribution.stations)
    return dict(lines=lines, stations=stations, distributions=realized.distributions,
                length=nominal_length, width=math.dist(a.start_global, b.start_global))
