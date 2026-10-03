"""Pure ThreePoints frame, measured from nominal reference axes."""
import math
from .realization import _unit, cross


def three_points(start, end, apex):
    start,end,apex=(tuple(float(v) for v in p) for p in (start,end,apex))
    if any(len(p)!=3 or not all(math.isfinite(v) for v in p) for p in (start,end,apex)):
        raise ValueError("Informe três pontos 3D finitos.")
    span=math.dist(start,end)
    x=_unit(tuple(b-a for a,b in zip(start,end)))
    offset=tuple(p-a for p,a in zip(apex,start))
    projection=sum(a*b for a,b in zip(offset,x))
    perpendicular=tuple(a-projection*b for a,b in zip(offset,x))
    height=math.sqrt(sum(v*v for v in perpendicular))
    if height<=1e-7 or not 1e-7<projection<span-1e-7:
        raise ValueError("Ápice deve estar fora da linha da base e projetado dentro do vão.")
    y=_unit(perpendicular)
    return dict(start=list(start),end=list(end),plane_normal=list(cross(x,y)),span=span,
                height=height,apex_position=projection/span,envelope_type="DuoPitch",
                reference_mode="ThreePoints",reference_linked=False)
