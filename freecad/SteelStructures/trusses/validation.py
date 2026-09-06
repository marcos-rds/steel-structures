"""Geometric graph checks, deliberately without structural analysis."""
import math

TOLERANCE = 1e-7


def validate_graph(graph):
    errors, warnings = [], []
    nodes = {n.key: n for n in graph.nodes}
    if len(nodes) != len(graph.nodes):
        errors.append("Node key duplicada.")
    if len({e.key for e in graph.edges}) != len(graph.edges):
        errors.append("Edge key duplicada.")
    for node in graph.nodes:
        if len(node.position_local) != 3 or not all(math.isfinite(x) for x in node.position_local):
            errors.append("Coordenada não finita/3D: "+node.key)
    if errors:
        return tuple(errors), ()
    pairs = set()
    for edge in graph.edges:
        if edge.start_node_key not in nodes or edge.end_node_key not in nodes:
            errors.append("Referência inexistente: "+edge.key)
            continue
        pair = tuple(sorted((edge.start_node_key, edge.end_node_key)))
        if pair in pairs:
            errors.append("Edge duplicada: "+edge.key)
        pairs.add(pair)
        if math.dist(nodes[pair[0]].position_local, nodes[pair[1]].position_local) <= TOLERANCE:
            errors.append("Edge sem comprimento: "+edge.key)
    if errors:
        return tuple(errors), ()
    incident = {key for edge in graph.edges for key in (edge.start_node_key, edge.end_node_key)}
    for edge in graph.edges:
        a = nodes[edge.start_node_key].position_local
        b = nodes[edge.end_node_key].position_local
        ab = tuple(y-x for x,y in zip(a,b))
        length2 = sum(x*x for x in ab)
        for key in incident - {edge.start_node_key, edge.end_node_key}:
            point = nodes[key].position_local
            fraction = sum((p-x)*d for p,x,d in zip(point,a,ab))/length2
            projected = tuple(x+fraction*d for x,d in zip(a,ab))
            if 0 < fraction < 1 and math.dist(point, projected) <= TOLERANCE:
                errors.append("Edge atravessa nó conectado intermediário: {} / {}.".format(edge.key,key))
    if errors:
        return tuple(errors), ()
    remaining = set(nodes)
    components = 0
    adjacency = graph.adjacency
    while remaining:
        components += 1
        queue = [min(remaining)]
        while queue:
            key = queue.pop()
            if key in remaining:
                remaining.remove(key)
                queue.extend(adjacency[key])
    if components > 1:
        warnings.append("Componentes desconectados: {}.".format(components))
    for i, a in enumerate(graph.nodes):
        for b in graph.nodes[i+1:]:
            if math.dist(a.position_local, b.position_local) <= TOLERANCE:
                warnings.append("Nós coincidentes sem identidade compartilhada: {} / {}.".format(a.key, b.key))
    # C1 planar proper intersections. Shared endpoints are connections, not warnings.
    def cross(a, b, c):
        return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
    for i, edge in enumerate(graph.edges):
        a, b = nodes[edge.start_node_key].position_local, nodes[edge.end_node_key].position_local
        for other in graph.edges[i+1:]:
            if {edge.start_node_key, edge.end_node_key} & {other.start_node_key, other.end_node_key}:
                continue
            c, d = nodes[other.start_node_key].position_local, nodes[other.end_node_key].position_local
            if (cross(a,b,c)*cross(a,b,d) < -TOLERANCE and
                    cross(c,d,a)*cross(c,d,b) < -TOLERANCE):
                warnings.append("Cruzamento sem conexão: {} / {}.".format(edge.key, other.key))
    return (), tuple(warnings)
