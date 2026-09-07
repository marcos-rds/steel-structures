"""Draft adapters. Line coordinates use the existing AxisSource resolver."""
import math
from .member_axis_source import resolve_axis_source, is_draft_line, _parent_placement
from .member_adjustment_reference import would_create_adjustment_cycle
from .trusses.realization import reference_frame, _unit, cross


def _tuple(vector):
    return (float(vector.x),float(vector.y),float(vector.z))


def _number(value):
    return float(getattr(value,"Value",value))


def is_draft_rectangle(source):
    try:
        return (source.TypeId in ("Part::FeaturePython","Part::Part2DObjectPython") and source.Proxy.__class__.__name__=="Rectangle"
                and source.Proxy.__class__.__module__.startswith("draftobjects.")
                and all(hasattr(source,k) for k in ("Length","Height","Shape","Placement")))
    except (AttributeError,ReferenceError,RuntimeError):
        return False


def rectangle_geometry(source, edge_name):
    if not is_draft_rectangle(source) or edge_name not in ("Edge1","Edge2","Edge3","Edge4"):
        raise ValueError("Selecione um Retângulo Draft simples e indique o lado de base (Edge1–Edge4).")
    length,height=_number(source.Length),_number(source.Height)
    if not all(math.isfinite(v) and v>1e-7 for v in (length,height)):
        raise ValueError("Retângulo com Length/Height inválidos; último estado preservado.")
    for name in ("FilletRadius","ChamferSize"):
        if _number(getattr(source,name,0))!=0: raise ValueError("Retângulo com arredondamentos/chanfros não suportado.")
    if any(_number(getattr(source,n,1))!=1 for n in ("Rows","Columns")):
        raise ValueError("Retângulo subdividido não suportado.")
    shape=source.Shape
    if shape.isNull() or not shape.isValid() or len(shape.Edges)!=4:
        raise ValueError("Retângulo deve possuir quatro arestas retas coerentes com suas dimensões.")
    vector_type=type(source.Placement.Base)
    placement=source.getGlobalPlacement()
    parent=_parent_placement(source)
    corners=[placement.multVec(vector_type(*p)) for p in ((0,0,0),(length,0,0),(length,height,0),(0,height,0))]
    expected={frozenset((i,(i+1)%4)) for i in range(4)}
    actual=set()
    selected=None
    for index in range(1,5):
        edge=source.getSubObject(f"Edge{index}")
        if edge is None or len(edge.Vertexes)!=2 or not edge.Curve.isDerivedFrom("Part::GeomLine"):
            raise ValueError("Arestas do retângulo devem ser lineares.")
        endpoints=[parent.multVec(v.Point) for v in edge.Vertexes]
        matched=[]
        for point in endpoints:
            matches=[i for i,p in enumerate(corners) if point.sub(p).Length<=1e-6]
            if len(matches)!=1: raise ValueError("Shape do retângulo não corresponde a Length/Height/Placement; recompute a fonte.")
            matched.append(matches[0])
        actual.add(frozenset(matched))
        if edge_name==f"Edge{index}": selected=endpoints
    if actual!=expected: raise ValueError("Contorno do retângulo inconsistente.")
    start,end=selected
    x=end.sub(start); span=x.Length; x.normalize()
    center=corners[0].add(corners[2])*0.5
    inward=center.sub(start)
    y=inward.sub(x*inward.dot(x)); derived_height=2*y.Length; y.normalize()
    normal=x.cross(y)
    return dict(start=list(_tuple(start)),end=list(_tuple(end)),span=span,height=derived_height,
                plane_normal=list(_tuple(normal)),envelope_type="Parallel")


def source_geometry(source, mode, edge, plane_normal, plane_up=None):
    if mode=="DraftRectangle":
        return rectangle_geometry(source,edge)
    if mode!="DraftLine": raise ValueError("Modo da fonte inválido.")
    axis=resolve_axis_source((source,["Edge1"]))
    if axis is None: raise ValueError("Linha Draft ausente, inválida ou degenerada; último estado preservado.")
    x=_unit(_tuple(axis.end.sub(axis.start)))
    normal=_unit(plane_normal)
    dot=sum(a*b for a,b in zip(x,normal))
    projected=tuple(n-dot*v for n,v in zip(normal,x))
    if sum(v*v for v in projected)<1e-14:
        if plane_up is None:
            raise ValueError("Linha perpendicular ao plano persistido; selecione novamente a referência no plano desejado.")
        projected=cross(x,_unit(plane_up))
    value=dict(start=list(_tuple(axis.start)),end=list(_tuple(axis.end)),
               span=axis.end.sub(axis.start).Length,plane_normal=list(_unit(projected)))
    reference_frame(value)
    return value


def reference_containers(source):
    """Native placement dependencies: an App::Part move does not touch its child."""
    result=[]
    current=source
    while hasattr(current,"getParentGeoFeatureGroup"):
        current=current.getParentGeoFeatureGroup()
        if current is None: break
        if current in result: raise ValueError("Ciclo nos containers da referência.")
        result.append(current)
    return result


def resolve_linked_reference(document, config, owner=None):
    if not config.get("reference_linked",False): return dict(config)
    if config.get("reference_mode") not in ("DraftLine","DraftRectangle"):
        raise ValueError("Vínculo somente para Linha ou Retângulo Draft.")
    source=document.getObject(config.get("reference_source",""))
    if source is None: raise ValueError("Fonte vinculada removida; último estado aplicado preservado.")
    if owner is not None and (source==owner or would_create_adjustment_cycle(owner,source)):
        raise ValueError("A referência criaria ciclo com a treliça.")
    if owner is not None and any(parent==owner or would_create_adjustment_cycle(owner,parent)
                                 for parent in reference_containers(source)):
        raise ValueError("O container da referência depende da treliça; use uma referência Snapshot.")
    result=dict(config)
    result.update(source_geometry(source,config["reference_mode"],config.get("reference_edge","Edge1"),config["plane_normal"]))
    return result


def rectangle_initial_base(source):
    """Measure validated real edges. Equal sides have no preferred direction."""
    lengths=[(f"Edge{i}",rectangle_geometry(source,f"Edge{i}")["span"]) for i in range(1,5)]
    longest=max(length for _,length in lengths)
    tolerance=1e-6
    if longest-min(length for _,length in lengths)<=tolerance: return ""
    return next(name for name,length in lengths if longest-length<=tolerance)


def selection_reference(selection):
    if len(selection)!=1: raise ValueError("Selecione uma única Linha ou Retângulo Draft.")
    item=selection[0]; source=item.Object
    names=tuple(name for name in (item.SubElementNames or ()) if name)
    if len(names)>1: raise ValueError("Selecione somente uma aresta base.")
    if is_draft_line(source):
        if names not in ((),("Edge1",)): raise ValueError("Selecione a Edge1 da Linha Draft.")
        return source,"DraftLine","Edge1"
    if is_draft_rectangle(source):
        if names and names[0] not in ("Edge1","Edge2","Edge3","Edge4"):
            raise ValueError("Selecione uma aresta do retângulo ou o objeto inteiro.")
        return source,"DraftRectangle",names[0] if names else rectangle_initial_base(source)
    raise ValueError("Referência deve ser Linha ou Retângulo Draft simples.")
