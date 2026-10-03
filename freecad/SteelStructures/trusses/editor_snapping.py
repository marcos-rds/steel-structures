"""Local 2D graph snapping; caller converts pixel tolerance to model units."""
import math


def snap_target(graph, point, tolerance, exclude_node=None):
    choices=[]
    for node in graph.nodes:
        if node.key == exclude_node: continue
        distance=math.dist(point,node.position_local)
        if distance<=tolerance:
            choices.append((0,distance,node.key,dict(kind="node",key=node.key,point=node.position_local)))
    for edge in graph.edges:
        a,b=graph.node(edge.start_node_key).position_local,graph.node(edge.end_node_key).position_local
        d=tuple(y-x for x,y in zip(a,b))
        length2=sum(v*v for v in d)
        if not length2: continue
        midpoint=tuple((x+y)/2 for x,y in zip(a,b))
        distance=math.dist(point,midpoint)
        if distance<=tolerance:
            choices.append((1,distance,edge.key,dict(kind="midpoint",key=edge.key,point=midpoint)))
        t=max(0.,min(1.,sum((p-x)*v for p,x,v in zip(point,a,d))/length2))
        projected=tuple(x+t*v for x,v in zip(a,d))
        distance=math.dist(point,projected)
        if distance<=tolerance:
            choices.append((2,distance,edge.key,dict(kind="edge",key=edge.key,point=projected)))
    return min(choices,key=lambda value:value[:3])[3] if choices else None
