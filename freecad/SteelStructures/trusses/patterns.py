"""Explicit C1 variants: alternating Warren with end closures; inward Pratt.

Parallel: end posts close the vertical ends. DuoPitch: shared support nodes;
the first and last interior verticals close the support triangles. Warren has
no other verticals. Pratt has every interior vertical, and diagonals from the
outer top node to the inner bottom node, switching at the apex (midspan for
Parallel). A Parallel panel straddling midspan follows the left orientation.
"""
from .envelope import top_height
from .models import TopologyNode, TopologyEdge, TopologyGraph


def generate_topology(definition, station_plan, preset):
    if preset not in ("Warren", "Pratt"):
        raise ValueError("Padrão não suportado no C1.")
    nodes, edges, top, bottom = [], [], [], []
    stations = station_plan.stations
    for i, station in enumerate(stations):
        shared = definition.kind == "DuoPitch" and i in (0, len(stations)-1)
        bk = "N_"+station.key if shared else "B_"+station.key
        tk = bk if shared else "T_"+station.key
        bottom.append(bk)
        top.append(tk)
        nodes.append(TopologyNode(bk, (station.x, 0., 0.),
                                 ("BOTTOM_CHORD", "TOP_CHORD") if shared else ("BOTTOM_CHORD",),
                                 "CHORD_NODE", station.key))
        if not shared:
            nodes.append(TopologyNode(tk, (station.x, top_height(definition, station.x), 0.),
                                     ("TOP_CHORD",), "CHORD_NODE", station.key))

    def add(a, b, role, affiliation=""):
        if a == b:
            return
        key = role+":"+a+">"+b
        edges.append(TopologyEdge(key, a, b, role, affiliation))

    count = station_plan.panel_count
    for i in range(count):
        add(bottom[i], bottom[i+1], "BOTTOM_CHORD", "BOTTOM_CHORD")
        add(top[i], top[i+1], "TOP_CHORD", "TOP_CHORD")
    if definition.kind == "Parallel":
        add(bottom[0], top[0], "END_POST")
        add(bottom[-1], top[-1], "END_POST")
    vertical_indices = (range(1, count) if preset == "Pratt" else
                        sorted({1, count-1}) if definition.kind == "DuoPitch" else ())
    for i in vertical_indices:
        add(bottom[i], top[i], "VERTICAL")
    pivot = (definition.span*definition.apex_position if definition.kind == "DuoPitch"
             else definition.span*0.5)
    for i in range(count):
        if definition.kind == "DuoPitch" and i in (0, count-1):
            continue  # The shared support/chords already close these triangles.
        if preset == "Warren":
            a, b = (bottom[i], top[i+1]) if i % 2 == 0 else (top[i], bottom[i+1])
        else:
            a, b = ((top[i], bottom[i+1]) if stations[i].x < pivot
                    else (bottom[i], top[i+1]))
        add(a, b, "DIAGONAL")
    return TopologyGraph(tuple(sorted(nodes, key=lambda n: n.key)),
                         tuple(sorted(edges, key=lambda e: e.key)))
