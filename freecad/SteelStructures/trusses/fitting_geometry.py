"""Pure profile-geometry adapter for chord contact planes."""

import math

from .. import profile_catalog
from ..assemblies.transforms import SectionTransform, transform_section
from ..assemblies.attachment import support
from ..profiles.geometry import ArcSegment2D, LineSegment2D, Point2D, build_section_geometry
from ..profiles.insertion import insertion_translation
from ..profiles.models import ProfileRef
from ..profiles.cold_formed import segment_arc_intersections, segment_segment_intersections
from ..fitting import GeometryReference
from .assemblies import assembly_frame


TOLERANCE = 1e-7


def _dot(a, b):
    return sum(x*y for x, y in zip(a, b))


def _sub(a, b):
    return tuple(x-y for x, y in zip(a, b))


def _unit(value):
    length = math.sqrt(_dot(value, value))
    if length <= TOLERANCE:
        raise ValueError("Direção de contato degenerada.")
    return tuple(component/length for component in value)


def _section_at_insertion(item):
    ref = ProfileRef(**item.spec.profile_ref)
    designation = profile_catalog.selection_for_ref(ref)[2]
    profile = profile_catalog.get(designation)
    geometry = build_section_geometry(profile.definition, item.spec.section_geometry_mode)
    tx, ty = insertion_translation(geometry, item.spec.insertion)
    if item.section_transform is not None:
        transform = SectionTransform(**item.section_transform)
        geometry, _references = transform_section(geometry, transform)
        translated = transform.point(Point2D(tx, ty))
        tx, ty = translated.x, translated.y
    return geometry, (tx, ty)


def _line_path_parameters(origin, direction, path, extent):
    """Return exact parameters where an infinite line meets a section path."""
    start = Point2D(origin[0]-extent*direction[0], origin[1]-extent*direction[1])
    end = Point2D(origin[0]+extent*direction[0], origin[1]+extent*direction[1])
    ray = LineSegment2D(start, end)
    parameters = []
    for segment in path.segments:
        if isinstance(segment, LineSegment2D):
            result = segment_segment_intersections(ray, segment, TOLERANCE)
        elif isinstance(segment, ArcSegment2D):
            result = segment_arc_intersections(ray, segment, TOLERANCE)
        else:
            raise ValueError("Contorno de perfil não suportado pelo fitting.")
        if result.overlap:
            raise ValueError("Linha de encontro coincidente com o contorno do banzo.")
        for point in result.points:
            delta = (point.x-origin[0], point.y-origin[1])
            parameters.append(_dot(delta, direction))
    return tuple(sorted({round(value, 10) for value in parameters}))


def chord_contact_reference(member_item, chord_item, node_global, truss_plane_normal, end):
    """Resolve the first physical chord boundary reached from the web interior."""
    member_direction = _unit(_sub(member_item.end_global, member_item.start_global))
    outward = tuple(-value for value in member_direction) if end == "Start" else member_direction
    chord_direction = _unit(_sub(chord_item.end_global, chord_item.start_global))
    frame = assembly_frame(
        (chord_item.start_global, chord_item.end_global),
        chord_item.section_u_global, chord_item.spec.rotation,
    )
    geometry, translation = _section_at_insertion(chord_item)
    relative = _sub(node_global, chord_item.start_global)
    section_origin = (_dot(relative, frame.u)-translation[0],
                      _dot(relative, frame.v)-translation[1])
    section_direction = (_dot(outward, frame.u), _dot(outward, frame.v))
    projected_length = math.hypot(*section_direction)
    if projected_length <= TOLERANCE:
        raise ValueError("A web é paralela ao eixo do banzo; contato físico indeterminado.")
    section_direction = tuple(value/projected_length for value in section_direction)
    bounds = geometry.bounds
    radius = max(abs(bounds.min_x-section_origin[0]), abs(bounds.max_x-section_origin[0]),
                 abs(bounds.min_y-section_origin[1]), abs(bounds.max_y-section_origin[1]), 1.)
    parameters = _line_path_parameters(section_origin, section_direction,
                                       geometry.outer_path, radius*3.)
    if not parameters:
        raise ValueError("O eixo físico da web não encontra o contorno do banzo.")
    # The first outer-contour crossing seen while travelling from the member
    # interior toward/beyond its topology node is the contact face.
    axial_parameter = min(parameters)/projected_length
    contact = tuple(point+axial_parameter*direction
                    for point, direction in zip(node_global, outward))
    normal = (
        chord_direction[1]*truss_plane_normal[2]-chord_direction[2]*truss_plane_normal[1],
        chord_direction[2]*truss_plane_normal[0]-chord_direction[0]*truss_plane_normal[2],
        chord_direction[0]*truss_plane_normal[1]-chord_direction[1]*truss_plane_normal[0],
    )
    return GeometryReference(chord_item.key, "Plane", contact, normal=normal), axial_parameter


def chord_envelope_reference(member_item, chord_item, node_global,
                             truss_plane_normal, end):
    """Return the chord's outermost plane on the member-interior side.

    Web contact may use a recessed face of an open section. Interconnectors
    occupy a different transverse band, so their distribution uses the full
    chord envelope rather than assuming that recessed contact plane separates
    the complete chord shape.
    """
    member_direction = _unit(_sub(member_item.end_global, member_item.start_global))
    outward = tuple(-value for value in member_direction) if end == "Start" else member_direction
    interior = tuple(-value for value in outward)
    chord_direction = _unit(_sub(chord_item.end_global, chord_item.start_global))
    frame = assembly_frame(
        (chord_item.start_global, chord_item.end_global),
        chord_item.section_u_global, chord_item.spec.rotation,
    )
    normal = _unit((
        chord_direction[1]*truss_plane_normal[2]-chord_direction[2]*truss_plane_normal[1],
        chord_direction[2]*truss_plane_normal[0]-chord_direction[0]*truss_plane_normal[2],
        chord_direction[0]*truss_plane_normal[1]-chord_direction[1]*truss_plane_normal[0],
    ))
    geometry, translation = _section_at_insertion(chord_item)
    projected = (_dot(normal, frame.u), _dot(normal, frame.v))
    low, high = support(geometry, projected)
    insertion_shift = translation[0]*projected[0]+translation[1]*projected[1]
    axis_offset = _dot(_sub(chord_item.start_global, node_global), normal)
    low, high = axis_offset+low-insertion_shift, axis_offset+high-insertion_shift
    boundary = high if _dot(interior, normal) > 0. else low
    origin = tuple(point+boundary*axis for point, axis in zip(node_global, normal))
    return GeometryReference(chord_item.key, "Plane", origin, normal=normal)
