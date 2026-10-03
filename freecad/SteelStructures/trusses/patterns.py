"""Explicit C1 variants: alternating Warren with end closures; inward Pratt.

Parallel: end posts close the vertical ends. DuoPitch: shared support nodes;
the first and last interior verticals close the support triangles. Warren has
no other verticals. Pratt has every interior vertical, and diagonals from the
outer top node to the inner bottom node, switching at the apex (midspan for
Parallel). A Parallel panel straddling midspan follows the left orientation.
"""
from .envelope import top_height
from .models import TopologyNode, TopologyEdge, TopologyGraph


def _c1_topology(definition, station_plan, preset):
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


def generate_topology(definition, station_plan, preset, x_connection="Disconnected"):
    from .preset_contracts import validate_preset
    from .editing import split_connected_edges
    validate_preset(definition, station_plan, preset)
    if preset in ("Warren", "Pratt"):
        return _c1_topology(definition, station_plan, preset)
    base = _c1_topology(definition, station_plan, "Pratt")
    nodes = list(base.nodes)
    edges = [e for e in base.edges if e.role in ("TOP_CHORD", "BOTTOM_CHORD")
             or (e.role == "END_POST" and preset != "Custom")]
    stations = station_plan.stations
    top = [next(n.key for n in nodes if n.optional_station_key == s.key and "TOP_CHORD" in n.affiliations) for s in stations]
    bottom = [next(n.key for n in nodes if n.optional_station_key == s.key and "BOTTOM_CHORD" in n.affiliations) for s in stations]
    count = station_plan.panel_count

    positions = {node.key:node.position_local for node in nodes}
    pairs = {frozenset((edge.start_node_key,edge.end_node_key)) for edge in edges}

    def point(key):
        return positions[key]

    def add(a, b, role="DIAGONAL"):
        if a == b or frozenset((a,b)) in pairs:
            return
        pairs.add(frozenset((a,b)))
        if point(a)[0] > point(b)[0] or (point(a)[0] == point(b)[0] and point(a)[1] > point(b)[1]):
            a, b = b, a
        edges.append(TopologyEdge(role + ":" + a + ">" + b, a, b, role))

    def internal(key, x, y):
        nodes.append(TopologyNode(key, (x, y, 0.), (), "INTERNAL_NODE"))
        positions[key]=(x,y,0.)
        return key

    def vertical(i):
        add(bottom[i], top[i], "VERTICAL")

    if preset == "WarrenVerticals":
        edges.extend(e for e in _c1_topology(definition, station_plan, "Warren").edges if e.role == "DIAGONAL")
        for i in range(1, count): vertical(i)
    elif preset in ("Howe", "X"):
        for i in range(1, count): vertical(i)
        pivot = definition.span * (definition.apex_position if definition.kind == "DuoPitch" else .5)
        for i in range(count):
            if definition.kind == "DuoPitch" and i in (0, count-1): continue
            if preset == "Howe":
                add(*( (bottom[i], top[i+1]) if stations[i].x < pivot else (top[i], bottom[i+1]) ))
            elif x_connection == "Disconnected":
                add(bottom[i], top[i+1]); add(top[i], bottom[i+1])
            elif x_connection == "Connected":
                h0, h1 = point(top[i])[1], point(top[i+1])[1]
                t = h0 / (h0 + h1)
                mid = internal("I_X_" + stations[i].key + "_" + stations[i+1].key,
                               stations[i].x + t*(stations[i+1].x-stations[i].x), t*h1)
                for end in (bottom[i], top[i], bottom[i+1], top[i+1]): add(end, mid)
            else:
                raise ValueError("Escolha X conectado ou sem conexão central.")
    elif preset == "K":
        for i in range(1, count):
            mid = internal("I_K_" + stations[i].key, stations[i].x, point(top[i])[1]/2)
            add(bottom[i], mid, "VERTICAL"); add(mid, top[i], "VERTICAL")
            outer = i-1 if i <= count/2 else i+1
            add(bottom[outer], mid); add(top[outer], mid)
    elif preset in ("Fink", "Fan", "KingPost", "QueenPost"):
        pivot = definition.span * definition.apex_position
        center = next(i for i,s in enumerate(stations) if abs(s.x-pivot) < 1e-7)

        def chord_node(key, x, role):
            y = top_height(definition,x) if role == "TOP_CHORD" else 0.
            existing = next((n for n in nodes if abs(n.position_local[0]-x)<1e-7
                             and abs(n.position_local[1]-y)<1e-7), None)
            if existing: return existing.key
            nodes.append(TopologyNode(key,(x,y,0.),(role,),"CHORD_NODE"))
            positions[key]=(x,y,0.)
            return key

        if preset == "QueenPost":
            # Equal post heights make the straining beam horizontal even for
            # an offset apex; both posts stay on their respective rafters.
            left=chord_node("Q_TOP_LEFT",pivot*2/3,"TOP_CHORD")
            right=chord_node("Q_TOP_RIGHT",pivot+(definition.span-pivot)/3,"TOP_CHORD")
            for top_key in (left,right):
                foot=chord_node("Q_BOTTOM_"+top_key,point(top_key)[0],"BOTTOM_CHORD")
                add(foot,top_key,"VERTICAL")
            add(left,right)
        elif preset == "Fan":
            for i in range(1,count):
                add(bottom[center],top[i],"VERTICAL" if i==center else "DIAGONAL")
        elif preset == "KingPost":
            vertical(center)
            for key,x in (("KING_LEFT",pivot/2),("KING_RIGHT",(pivot+definition.span)/2)):
                add(bottom[center],chord_node(key,x,"TOP_CHORD"))
        else:
            # Four web legs form the basic W between rafter midpoints and apex.
            left_top=chord_node("FINK_TOP_LEFT",pivot/2,"TOP_CHORD")
            right_top=chord_node("FINK_TOP_RIGHT",(pivot+definition.span)/2,"TOP_CHORD")
            left_bottom=chord_node("FINK_BOTTOM_LEFT",pivot*2/3,"BOTTOM_CHORD")
            right_bottom=chord_node("FINK_BOTTOM_RIGHT",pivot+(definition.span-pivot)/3,"BOTTOM_CHORD")
            # W: rafter midpoint -> lower third -> apex -> lower third -> rafter midpoint.
            for a,b in ((left_top,left_bottom),(left_bottom,top[center]),
                        (top[center],right_bottom),(right_bottom,right_top)):
                add(a,b,"VERTICAL" if point(a)[0]==point(b)[0] else "DIAGONAL")
    # Explicit preset nodes are actual graph connections; crossings alone never split.
    graph=TopologyGraph(tuple(sorted(nodes,key=lambda n:n.key)),tuple(sorted(edges,key=lambda e:e.key)))
    # These families connect only adjacent stations (and explicit X centers).
    # They already have every connection split by construction.
    return graph if preset in ("WarrenVerticals","Howe","X","Custom") else split_connected_edges(graph)
