"""Pure transverse preview using the exact C3-A section and insertion transform."""
import math
from ..profiles.geometry import build_section_geometry, Point2D, ArcSegment2D
from ..assemblies.transforms import SectionTransform, transform_section
from .assemblies import role_assembly_spec, role_profile


def transverse_preview(role):
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
    points = [p for c in components for path in c["paths"] for p in path]+[Point2D(0, 0)]
    return dict(components=tuple(components), spacing=assembly.component_spacing,
                bounds=(min(p.x for p in points), min(p.y for p in points),
                        max(p.x for p in points), max(p.y for p in points)))
