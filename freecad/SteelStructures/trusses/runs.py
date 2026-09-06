"""Logical chord chains collapse to straight physical pieces, never bent members."""
from .models import PhysicalRun, CONTINUITIES


def _validate_straight_chain(chain, nodes):
    if not chain:
        return
    origin = nodes[chain[0].start_node_key].position_local
    end = nodes[chain[-1].end_node_key].position_local
    direction = tuple(b-a for a,b in zip(origin,end))
    length2 = sum(v*v for v in direction)
    if length2 <= 1e-14:
        raise ValueError("Cadeia física degenerada.")
    previous = chain[0].start_node_key
    for edge in chain:
        if edge.start_node_key != previous:
            raise ValueError("Cadeia física descontínua.")
        point = nodes[edge.end_node_key].position_local
        fraction = sum((p-a)*v for p,a,v in zip(point,origin,direction))/length2
        distance2 = sum((p-a-fraction*v)**2 for p,a,v in zip(point,origin,direction))
        if distance2 > 1e-14:
            raise ValueError("Uma peça física não pode atravessar mudança de direção.")
        previous = edge.end_node_key


def physical_runs(graph, definition, top_continuity, bottom_continuity):
    if top_continuity not in CONTINUITIES or bottom_continuity not in CONTINUITIES:
        raise ValueError("Continuidade não suportada no C1.")
    nodes = {n.key: n for n in graph.nodes}
    result = []
    for role, mode, prefix in (("TOP_CHORD", top_continuity, "TC"),
                               ("BOTTOM_CHORD", bottom_continuity, "BC")):
        chord = sorted((e for e in graph.edges if e.role == role),
                       key=lambda e: nodes[e.start_node_key].position_local[0])
        if mode == "SegmentAtEveryNode":
            result.extend(PhysicalRun(prefix+":"+e.key, role, (e.key,), e.start_node_key,
                                      e.end_node_key) for e in chord)
        else:
            if role == "TOP_CHORD" and definition.kind == "DuoPitch":
                apex = definition.span*definition.apex_position
                chains = [(prefix+"_LEFT", [e for e in chord if nodes[e.end_node_key].position_local[0] <= apex]),
                          (prefix+"_RIGHT", [e for e in chord if nodes[e.start_node_key].position_local[0] >= apex])]
            else:
                chains = [(prefix+"_MAIN", chord)]
            for key, chain in chains:
                if chain:
                    _validate_straight_chain(chain, nodes)
                    result.append(PhysicalRun(key, role, tuple(e.key for e in chain),
                                              chain[0].start_node_key, chain[-1].end_node_key))
    for e in graph.edges:
        if e.role not in ("TOP_CHORD", "BOTTOM_CHORD"):
            result.append(PhysicalRun(e.key, e.role, (e.key,), e.start_node_key, e.end_node_key))
    return tuple(sorted(result, key=lambda run: run.key))
