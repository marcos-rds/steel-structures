"""Capture one explicit finite edge. Returns coordinates, never a CAD link."""
import math

from .member_axis_source import AXIS_TOLERANCE, is_draft_line
from .member_adjustment_reference import would_create_adjustment_cycle
from .trusses.realization import _unit, cross, reference_frame


def selected_path(selection, document, owner=None):
    """Resolve a raw (resolve=0) selection without discarding its ancestors."""
    if len(selection) != 1:
        raise ValueError("Selecione uma única linha ou aresta reta.")
    item = selection[0]
    root = item.Object
    names = tuple(item.SubElementNames or ())
    if len(names) > 1:
        raise ValueError("Selecione uma única aresta.")
    if root.Document is not document or document.getObject(root.Name) is not root:
        raise ValueError("Selecione uma fonte no documento da treliça.")
    subname = names[0] if names else ""
    source = root.getSubObject(subname, 1) if subname else root
    if source is None or source.Document is not document:
        raise ValueError("A fonte selecionada não está disponível neste documento.")
    chain = root.getSubObjectList(subname) if subname else [root]
    for obj in (*chain, source):
        if (obj.Document is not document or obj.isDerivedFrom("App::Link")
                or hasattr(obj, "ArrayType")):
            raise ValueError("Ocorrências Link/array ainda não são suportadas; selecione a geometria original.")
        if owner is not None and would_create_adjustment_cycle(owner, obj):
            raise ValueError("A referência depende da própria treliça; selecione uma fonte independente.")
    if not subname:
        return root, source, "", ""
    _leaf, _mapped, indexed = root.resolveSubElement(subname)
    return root, source, subname, indexed.rsplit(".", 1)[-1]


def line_values(start, end, normal, up):
    """Use the established line-plane convention without changing the envelope."""
    start, end = tuple(start), tuple(end)
    axis = _unit(tuple(b-a for a,b in zip(start,end)))
    normal = _unit(normal)
    dot = sum(a*b for a,b in zip(axis,normal))
    projected = tuple(n-dot*x for n,x in zip(normal,axis))
    if sum(n*n for n in projected) < 1e-14:
        projected = cross(axis,_unit(up))
    values = dict(start=list(start),end=list(end),span=math.dist(start,end),
                  plane_normal=list(_unit(projected)))
    reference_frame(values)
    return values


def capture_edge(root, source, subname, indexed, normal, up):
    """Read the transformed subshape once; no source metadata enters config."""
    import Part
    if not subname or not indexed.startswith("Edge"):
        raise ValueError("Selecione explicitamente uma aresta, não uma face ou vértice.")
    if not hasattr(source,"Shape") or source.Shape.isNull() or not source.Shape.isValid():
        raise ValueError("O objeto não possui geometria válida para a referência.")
    edge = root.getSubObject(subname)
    if (edge is None or edge.isNull() or edge.ShapeType != "Edge" or not edge.isValid()
            or len(edge.Vertexes) != 2):
        raise ValueError("A aresta não define um segmento finito válido.")
    if not edge.Curve.isDerivedFrom("Part::GeomLine"):
        raise ValueError("A referência deve ser um segmento reto; curvas não são aceitas.")
    first,last = edge.FirstParameter,edge.LastParameter
    if any(not math.isfinite(v) or Part.Precision.isInfinite(v) for v in (first,last,edge.Length)):
        raise ValueError("A referência deve ser um segmento limitado.")
    start,end = edge.valueAt(first),edge.valueAt(last)
    points = [[float(p.x),float(p.y),float(p.z)] for p in (start,end)]
    if (not all(math.isfinite(v) for p in points for v in p)
            or math.dist(*points) <= AXIS_TOLERANCE
            or abs(math.dist(*points)-edge.Length) > max(1e-6,edge.Length*1e-10)):
        raise ValueError("A aresta é degenerada ou não possui extremos finitos coerentes.")
    values = line_values(*points,normal,up)
    config = dict(reference_mode="TwoPoints",reference_source="",reference_edge="",
                  reference_linked=False,reference_defined=True)
    origin = dict(name=source.Name,object_id=source.ID,edge=indexed)
    return config,values,origin
