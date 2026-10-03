"""Pure atomic graph edits and materialized Custom geometry bindings."""
from copy import deepcopy
from dataclasses import asdict, replace
import math
from uuid import uuid4
from hashlib import sha256
from .models import EnvelopeDefinition, TopologyNode, TopologyEdge, TopologyGraph
from .envelope import top_height
from .validation import validate_graph, TOLERANCE

CHORDS = ("TOP_CHORD", "BOTTOM_CHORD")


def on_segment(point, a, b):
    direction=tuple(y-x for x,y in zip(a,b))
    length2=sum(v*v for v in direction)
    if length2<=TOLERANCE**2: return False
    t=sum((p-x)*v for p,x,v in zip(point,a,direction))/length2
    return 0<=t<=1 and math.dist(point,tuple(x+t*v for x,v in zip(a,direction)))<=TOLERANCE


def _definition(config):
    return EnvelopeDefinition(config["envelope_type"], config["span"], config["height"], config["apex_position"])


def inside(definition, point, strict=False):
    x,y,z = point
    if not all(math.isfinite(v) for v in point) or abs(z) > TOLERANCE:
        return False
    epsilon = TOLERANCE if strict else -TOLERANCE
    return epsilon < x < definition.span-epsilon and epsilon < y < top_height(definition,x)-epsilon


def split_connected_edges(graph, origins=None, include_all=False):
    """Split only at explicit incident nodes. A geometric crossing is untouched."""
    incident = {k for e in graph.edges for k in (e.start_node_key,e.end_node_key)}
    edges = []
    # Preserve the envelope's chord ownership when a proposed web segment
    # coincides with part of an existing chord chain.
    for edge in sorted(graph.edges,key=lambda edge:(edge.role not in CHORDS,edge.key)):
        a,b = graph.node(edge.start_node_key).position_local, graph.node(edge.end_node_key).position_local
        d = tuple(y-x for x,y in zip(a,b)); length2 = sum(v*v for v in d)
        if length2 <= TOLERANCE**2:
            raise ValueError("Barra sem comprimento.")
        cuts = [(0.,edge.start_node_key),(1.,edge.end_node_key)]
        for node in graph.nodes:
            if (not include_all and node.key not in incident) or node.key in (edge.start_node_key,edge.end_node_key): continue
            t = sum((p-x)*v for p,x,v in zip(node.position_local,a,d))/length2
            if 0 < t < 1 and math.dist(node.position_local,tuple(x+t*v for x,v in zip(a,d))) <= TOLERANCE:
                cuts.append((t,node.key))
        cuts.sort()
        for (_,start),(_,end) in zip(cuts,cuts[1:]):
            key = edge.key if len(cuts)==2 else edge.key+":"+start+">"+end
            if not any({start,end}=={e.start_node_key,e.end_node_key} for e in edges):
                edges.append(replace(edge,key=key,start_node_key=start,end_node_key=end))
                if origins is not None:
                    origins[key]=deepcopy(origins.get(edge.key,asdict(edge)))
    return TopologyGraph(graph.nodes,tuple(sorted(edges,key=lambda e:e.key)))


def normalize_custom_graph(graph, origins=None):
    """Explicit Custom nodes are connections, including a free node snapped later.

    Coalesce old duplicate endpoint identities, then split at explicit nodes.
    Proper crossings without a node remain disconnected.
    """
    keys={n.key for n in graph.nodes}
    if len(keys)!=len(graph.nodes) or any(k not in keys for e in graph.edges for k in (e.start_node_key,e.end_node_key)):
        raise ValueError("A topologia contém referências de nós inválidas.")
    if any(len(n.position_local)!=3 or not all(math.isfinite(v) for v in n.position_local) for n in graph.nodes):
        raise ValueError("A topologia contém coordenadas inválidas.")
    enriched=[]
    for node in graph.nodes:
        affiliations=set(node.affiliations)
        affiliations.update(e.role for e in graph.edges if e.role in CHORDS and
            on_segment(node.position_local,graph.node(e.start_node_key).position_local,graph.node(e.end_node_key).position_local))
        enriched.append(replace(node,affiliations=tuple(sorted(affiliations)),
                        classification="CHORD_NODE" if affiliations else node.classification))
    nodes=[]; mapped={}
    for node in sorted(enriched,key=lambda n:(not bool(n.optional_station_key),not bool(n.affiliations),n.key)):
        existing=next((n for n in nodes if math.dist(n.position_local,node.position_local)<=TOLERANCE),None)
        if existing is None:
            nodes.append(node); mapped[node.key]=node.key
        else:
            mapped[node.key]=existing.key
            affiliations=tuple(sorted(set(existing.affiliations)|set(node.affiliations)))
            nodes[nodes.index(existing)]=replace(existing,affiliations=affiliations,
                classification="CHORD_NODE" if affiliations else existing.classification)
    edges=[]
    for edge in graph.edges:
        a,b=mapped[edge.start_node_key],mapped[edge.end_node_key]
        if a==b: raise ValueError("Há uma barra sem comprimento entre nós coincidentes.")
        edges.append(replace(edge,start_node_key=a,end_node_key=b))
    return split_connected_edges(TopologyGraph(tuple(sorted(nodes,key=lambda n:n.key)),tuple(edges)),origins,True)


def custom_state(config):
    """Additive JSON state; legacy Custom configs stored the seed as the preset."""
    config=deepcopy(config)
    if config.get("topology_mode")=="Custom":
        config.setdefault("base_preset",config.get("topology_preset","Custom"))
        config["topology_preset"]="Custom"
    return config


def reflected_graph(graph, definition, copy_direction=None, origins=None):
    """Reflect web geometry against the retained chord skeleton, independent of stations."""
    copying=copy_direction is not None
    source_origins=deepcopy(origins or {})
    center=definition.span/2
    def source_side(key):
        x=graph.node(key).position_local[0]
        return x<=center+TOLERANCE if copy_direction=="LeftToRight" else x>=center-TOLERANCE
    web=[e for e in graph.edges if e.role not in CHORDS
         and (not copying or all(source_side(k) for k in (e.start_node_key,e.end_node_key)))]
    required={k for e in web for k in (e.start_node_key,e.end_node_key)}
    required.update(n.key for n in graph.nodes if not graph.incidence[n.key] and
                    (not copying or source_side(n.key)))
    nodes=list(graph.nodes) if copying else [n for n in graph.nodes if n.affiliations]
    edges=list(graph.edges) if copying else [e for e in graph.edges if e.role in CHORDS]
    mapped={}
    def available_key(key,used,identity):
        return key if key not in used else key+":"+sha256(repr(identity).encode("utf-8")).hexdigest()[:16]
    for key in sorted(required):
        node=graph.node(key)
        x,y,z=node.position_local
        point=(definition.span-x,y,z)
        if not inside(definition,point):
            raise ValueError("A reflexão fica fora do envelope. Confira a geometria assimétrica.")
        existing=next((n for n in nodes if math.dist(n.position_local,point)<=TOLERANCE),None)
        if existing is None:
            # Reuse an old identity at the destination when inversion replaces
            # the web; newly required chord endpoints need no StationPlan entry.
            existing=next((n for n in graph.nodes if math.dist(n.position_local,point)<=TOLERANCE),None)
            if existing is None:
                affiliations=tuple(sorted({e.role for e in graph.edges if e.role in CHORDS and
                    on_segment(point,graph.node(e.start_node_key).position_local,graph.node(e.end_node_key).position_local)}))
                if node.affiliations and not set(node.affiliations).issubset(affiliations):
                    raise ValueError("O endpoint refletido não encontra o banzo correspondente neste envelope.")
                reflected_key=key[2:] if key.startswith("M_") else "M_"+key
                reflected_key=available_key(reflected_key,{n.key for n in nodes},point)
                existing=replace(node,key=reflected_key,position_local=point,optional_station_key=None,
                                 affiliations=affiliations,classification="CHORD_NODE" if affiliations else "INTERNAL_NODE")
            nodes.append(existing)
        if not set(node.affiliations).issubset(existing.affiliations):
            raise ValueError("O endpoint refletido não encontra o banzo correspondente neste envelope.")
        mapped[key]=existing.key
    positions={n.key:n.position_local for n in nodes}
    for edge in web:
        a,b=mapped[edge.start_node_key],mapped[edge.end_node_key]
        if positions[a]>positions[b]: a,b=b,a
        if any({a,b}=={e.start_node_key,e.end_node_key} for e in edges): continue
        existing=next((e for e in graph.edges if {a,b}=={e.start_node_key,e.end_node_key}
                       and e.role==edge.role and e.chord_affiliation==edge.chord_affiliation),None)
        key=existing.key if existing else edge.key[2:] if edge.key.startswith("M_") else "M_"+edge.key
        key=available_key(key,{e.key for e in edges},(a,b,edge.role,edge.chord_affiliation))
        edges.append(replace(edge,key=key,start_node_key=a,end_node_key=b))
        if origins is not None and not existing:
            original=deepcopy(source_origins.get(edge.key,asdict(edge)))
            original["key"]=original["key"][2:] if original["key"].startswith("M_") else "M_"+original["key"]
            for name in ("start_node_key","end_node_key"):
                original[name]=mapped.get(original[name],"M_"+original[name])
            if original["start_node_key"] in positions and original["end_node_key"] in positions:
                if positions[original["start_node_key"]]>positions[original["end_node_key"]]:
                    original["start_node_key"],original["end_node_key"]=original["end_node_key"],original["start_node_key"]
            origins[key]=original
    return TopologyGraph(tuple(nodes),tuple(edges))


def materialize(graph, config):
    definition = _definition(config)
    bindings = {}
    for node in graph.nodes:
        x,y,_ = node.position_local
        h = top_height(definition,x)
        pivot=definition.span*definition.apex_position
        branch="MAIN" if definition.kind=="Parallel" else "LEFT" if x<=pivot else "RIGHT"
        fraction=x/definition.span if branch=="MAIN" else x/pivot if branch=="LEFT" else (x-pivot)/(definition.span-pivot)
        bindings[node.key] = dict(x=fraction, branch=branch, y=y/h if h>TOLERANCE else 0.,
                                 apex=node.optional_station_key=="S_APEX")
    return dict(envelope_type=definition.kind, panel_count=config["panel_count"], nodes=[asdict(n) for n in graph.nodes],
                edges=[asdict(e) for e in graph.edges], bindings=bindings)


def restore_graph(data, config, stations=None):
    definition = _definition(config)
    if data["envelope_type"] != definition.kind:
        raise ValueError("Topologia Custom: restaure o padrão antes de trocar o envelope.")
    if data["panel_count"]!=config["panel_count"]:
        raise ValueError("Panelização incompatível com o grafo Custom; ajuste o driver ou use Restaurar padrão.")
    station_map={s.key:s.x for s in stations.stations} if stations else {}
    nodes = []
    for value in data["nodes"]:
        value = deepcopy(value)
        binding = data["bindings"][value["key"]]
        pivot=definition.span*definition.apex_position
        branch=binding.get("branch","MAIN")
        x = definition.span*binding["x"] if branch=="MAIN" else pivot*binding["x"] if branch=="LEFT" else pivot+(definition.span-pivot)*binding["x"]
        if binding["apex"]: x=pivot
        if value["optional_station_key"] and stations:
            if value["optional_station_key"] not in station_map:
                raise ValueError("Estações incompatíveis com os vínculos da topologia Custom.")
            x=station_map[value["optional_station_key"]]
        value["position_local"] = (x,top_height(definition,x)*binding["y"],0.)
        value["affiliations"] = tuple(value["affiliations"])
        nodes.append(TopologyNode(**value))
    return TopologyGraph(tuple(nodes),tuple(TopologyEdge(**e) for e in data["edges"]))


def edit_candidate(candidate, action, **args):
    """Return a detached config; the caller commits it only after full validation."""
    config = deepcopy(candidate.config)
    graph = candidate.graph
    nodes,edges = list(graph.nodes),list(graph.edges)
    definition = _definition(config)
    origins=deepcopy((config.get("custom_topology") or {}).get("edge_origins",{}))
    if action == "add_node":
        point = tuple(args["point"])
        edge = graph.edge(args["edge_key"]) if args.get("edge_key") else None
        if edge:
            a,b = graph.node(edge.start_node_key).position_local,graph.node(edge.end_node_key).position_local
            if not on_segment(point,a,b):
                raise ValueError("O ponto deve estar sobre a barra selecionada.")
        if not inside(definition,point,strict=edge is None):
            raise ValueError("O nó interno deve ficar dentro do envelope.")
        if any(math.dist(n.position_local,point)<=TOLERANCE for n in nodes):
            raise ValueError("Já existe um nó nessa posição.")
        key="N_MANUAL_"+uuid4().hex
        affiliations=(edge.role,) if edge and edge.role in CHORDS else ()
        nodes.append(TopologyNode(key,point,affiliations,"CHORD_NODE" if affiliations else "INTERNAL_NODE"))
        if edge:
            edges.remove(edge)
            parts=(replace(edge,key=edge.key+":A:"+key,end_node_key=key),
                   replace(edge,key=edge.key+":B:"+key,start_node_key=key))
            edges.extend(parts)
            for part in parts: origins[part.key]=deepcopy(origins.get(edge.key,asdict(edge)))
    elif action == "remove_node":
        node=graph.node(args["key"])
        incident=[e for e in edges if node.key in (e.start_node_key,e.end_node_key)]
        message="O nó possui barras conectadas. Remova as barras incidentes primeiro."
        if not incident:
            if node.affiliations: raise ValueError("Este nó pertence ao envelope e deve ser preservado.")
        elif len(incident)==2:
            first,second=incident
            original=origins.get(first.key)
            # Read the explicit A/B split format written by earlier C2 builds.
            if original is None or origins.get(second.key)!=original:
                suffix_a=":A:"+node.key; suffix_b=":B:"+node.key
                if first.key.endswith(suffix_b): first,second=second,first
                if (first.key.endswith(suffix_a) and second.key.endswith(suffix_b)
                        and first.key[:-len(suffix_a)]==second.key[:-len(suffix_b)]):
                    original=asdict(replace(first,key=first.key[:-len(suffix_a)],end_node_key=second.end_node_key))
                    origins[first.key]=origins[second.key]=original
            if (not original or origins.get(second.key)!=original or
                    (first.role,first.chord_affiliation)!=(second.role,second.chord_affiliation)):
                raise ValueError(message)
            a=first.end_node_key if first.start_node_key==node.key else first.start_node_key
            b=second.end_node_key if second.start_node_key==node.key else second.start_node_key
            pa,pb=graph.node(a).position_local,graph.node(b).position_local
            if a==b or not on_segment(node.position_local,pa,pb):
                raise ValueError(message)
            if pa>pb: a,b=b,a
            original_pair={original["start_node_key"],original["end_node_key"]}
            merged_key=original["key"] if {a,b}==original_pair else original["key"]+":"+a+">"+b
            edges=[e for e in edges if e not in incident]
            if any({a,b}=={e.start_node_key,e.end_node_key} for e in edges): raise ValueError(message)
            edges.append(replace(first,key=merged_key,start_node_key=a,end_node_key=b))
            origins[merged_key]=original
        else:
            raise ValueError(message)
        nodes=[n for n in nodes if n.key!=node.key]
    elif action == "move_node":
        node = graph.node(args["key"])
        point = tuple(args["point"])
        if node.classification != "INTERNAL_NODE" or not inside(definition,point,strict=True):
            raise ValueError("Somente nós internos podem ser movidos dentro do envelope.")
        if any(n.key!=node.key and math.dist(n.position_local,point)<=TOLERANCE for n in nodes):
            raise ValueError("Mover criaria nós coincidentes.")
        nodes = [replace(n,position_local=point) if n.key==node.key else n for n in nodes]
    elif action == "add_edge":
        a,b = args["start"],args["end"]
        if a==b or a not in graph.adjacency or b not in graph.adjacency:
            raise ValueError("Selecione dois nós existentes e distintos.")
        if any({a,b}=={e.start_node_key,e.end_node_key} for e in edges):
            raise ValueError("Essa barra já existe.")
        pa,pb=graph.node(a).position_local,graph.node(b).position_local
        if pa[0]>pb[0] or (pa[0]==pb[0] and pa[1]>pb[1]): a,b=b,a
        role="VERTICAL" if abs(pa[0]-pb[0])<=TOLERANCE else "DIAGONAL"
        edges.append(TopologyEdge("E_MANUAL_"+uuid4().hex,a,b,role))
    elif action == "remove_edge":
        edge = graph.edge(args["key"])
        if edge.role in CHORDS:
            raise ValueError("Este editor altera somente a alma; os banzos são preservados.")
        edges = [e for e in edges if e.key!=edge.key]
    elif action in ("mirror","copy_mirrored"):
        direction=args.get("direction","LeftToRight") if action=="copy_mirrored" else None
        if direction is not None and direction not in ("LeftToRight","RightToLeft"):
            raise ValueError("Escolha o sentido da cópia.")
        reflected=reflected_graph(graph,definition,direction,origins)
        nodes,edges=list(reflected.nodes),list(reflected.edges)
    else:
        raise ValueError("Operação de topologia desconhecida.")
    graph=normalize_custom_graph(TopologyGraph(tuple(sorted(nodes,key=lambda n:n.key)),tuple(edges)),origins)
    errors,_=validate_graph(graph)
    if errors: raise ValueError(" ".join(errors))
    config.setdefault("base_preset",config["topology_preset"])
    config.update(topology_mode="Custom", topology_preset="Custom", custom_topology=materialize(graph,config))
    config["custom_topology"]["edge_origins"]={e.key:origins[e.key] for e in graph.edges if e.key in origins}
    if config.get("panelization_mode")=="ByTargetDiagonalAngle":
        # A manually edited web no longer has the preset's declared family.
        # Freeze the resolved count rather than imposing a new angle rule.
        config["panelization_mode"]="ByPanelCount"
    return config


def restore_preset(config):
    config=deepcopy(config)
    config.update(topology_mode="Preset",topology_preset=config.pop("base_preset",config["topology_preset"]),custom_topology=None)
    return config
