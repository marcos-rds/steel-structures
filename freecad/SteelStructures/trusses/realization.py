"""Pure candidate construction, local frame and accepted/candidate comparison."""
from dataclasses import asdict, replace
import math
from .models import (EnvelopeDefinition, MemberSpec, Candidate, RealizationItem,
                     RegenerationAction, RegenerationPlan, ROLES)
from .drivers import resolve_panelization
from .patterns import generate_topology
from .runs import physical_runs
from .validation import validate_graph
from .serialization import dumps, loads


def _unit(vector):
    if len(vector) != 3 or not all(math.isfinite(x) for x in vector):
        raise ValueError("Vetor deve ter três coordenadas finitas.")
    length = math.sqrt(sum(v*v for v in vector))
    if length <= 1e-8:
        raise ValueError("Direção de referência degenerada.")
    return tuple(v/length for v in vector)


def cross(a, b):
    return (a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0])


def reference_frame(config):
    origin, end = tuple(config["start"]), tuple(config["end"])
    if not all(math.isfinite(v) for v in origin+end):
        raise ValueError("Pontos de referência não finitos.")
    x = _unit(tuple(b-a for a,b in zip(origin,end)))
    z = _unit(tuple(config["plane_normal"]))
    if abs(sum(a*b for a,b in zip(x,z))) > 1e-7:
        raise ValueError("A normal do plano deve ser perpendicular ao eixo P0–P1.")
    return origin, x, cross(z, x), z


def transform_point(point, frame):
    origin, x, y, z = frame
    return tuple(origin[i]+point[0]*x[i]+point[1]*y[i]+point[2]*z[i] for i in range(3))


def build_candidate(config, applied=None):
    config = loads(dumps(config))  # no caller-owned mutable data retained
    config.setdefault("topology_mode", "Preset")
    config.setdefault("panelization_mode", "ByPanelCount")
    config.setdefault("reference_mode", "TwoPoints")
    config.setdefault("reference_linked", False)
    from .editing import custom_state
    config=custom_state(config)
    if config.get("reference_defined", True) is not True:
        raise ValueError("Defina a referência; para um retângulo indique explicitamente o lado da base.")
    if config["topology_mode"] not in ("Preset", "Custom"):
        raise ValueError("Modo de topologia inválido.")
    definition = EnvelopeDefinition(config["envelope_type"], float(config["span"]),
                                    float(config["height"]), float(config.get("apex_position", .5)))
    count = config["panel_count"]
    allocation = None
    if definition.kind == "DuoPitch":
        old = applied.config if isinstance(applied, Candidate) else applied
        if old and old.get("envelope_type") == "DuoPitch" and old.get("panel_count") == count:
            allocation = (old["left_panels"], old["right_panels"])
        elif config.get("left_panels") and config.get("right_panels") and sum(
                (config["left_panels"], config["right_panels"])) == count:
            allocation = (config["left_panels"], config["right_panels"])
    stations, effective = resolve_panelization(config, definition, allocation)
    config.update(panel_count=stations.panel_count, panelization_result=effective,
                  left_panels=stations.left_panels, right_panels=stations.right_panels)
    if config["topology_mode"] == "Custom":
        from .editing import restore_graph, normalize_custom_graph, materialize
        if not config.get("custom_topology"):
            raise ValueError("Topologia Custom sem grafo materializado.")
        graph = restore_graph(config["custom_topology"], config, stations)
        origins=config["custom_topology"].get("edge_origins",{}).copy()
        normalized=normalize_custom_graph(graph,origins)
        if normalized!=graph:
            config["custom_topology"]=materialize(normalized,config)
        config["custom_topology"]["edge_origins"]={e.key:origins[e.key] for e in normalized.edges if e.key in origins}
        graph=normalized
    else:
        graph = generate_topology(definition, stations, config["topology_preset"], config.get("x_connection", "Disconnected"))
        if config["topology_preset"]=="Custom":
            from .editing import materialize
            config.update(topology_mode="Custom",custom_topology=materialize(graph,config))
    errors, warnings = validate_graph(graph)
    if errors:
        raise ValueError(" ".join(errors))
    if (config["topology_mode"] == "Preset" and config["topology_preset"] == "X"
            and config.get("x_connection", "Disconnected") == "Disconnected"):
        warnings = tuple(w for w in warnings if not w.startswith("Cruzamento sem conexão:"))
    runs = physical_runs(graph, definition, config["top_continuity"], config["bottom_continuity"])
    frame = reference_frame(config)
    if abs(math.dist(config["start"], config["end"])-definition.span) > 1e-6:
        raise ValueError("Vão deve coincidir com a distância P0–P1.")
    # Additive C1 compatibility: old END_POST supplies both physical sides.
    for side in ("END_POST_LEFT", "END_POST_RIGHT"):
        if side not in config["role_specs"]:
            config["role_specs"][side] = loads(dumps(config["role_specs"]["END_POST"]))
    specs = {}
    for role in ROLES + ("END_POST_LEFT", "END_POST_RIGHT"):
        spec = MemberSpec(**config["role_specs"][role])
        if (spec.physical_fit != "None"
                or spec.section_geometry_mode not in ("Detailed", "Simplified")
                or not math.isfinite(spec.rotation) or len(spec.color) != 3
                or not all(math.isfinite(v) and 0 <= v <= 1 for v in spec.color)
                or set(spec.profile_ref) != {"catalog_id", "profile_id"}
                or not all(isinstance(v, str) and v for v in spec.profile_ref.values())):
            raise ValueError("Especificação de membro inválida: "+role)
        # FreeCAD persists view colors as 8-bit channels. Canonicalize once so
        # restoring a document never looks like a manual color override.
        spec = replace(spec, color=tuple(math.floor(v*255+.5)/255 for v in spec.color))
        from .assemblies import role_assembly_spec
        from ..assemblies.serialization import dumps as assembly_dumps
        assembly = role_assembly_spec(asdict(spec))
        if spec.assembly != "Single":
            spec = replace(spec, assembly_spec=loads(assembly_dumps(assembly)))
            config["role_specs"][role]["assembly_spec"] = spec.assembly_spec
        config["role_specs"][role]["color"] = list(spec.color)
        specs[role] = spec
    items = []
    for run in runs:
        a, b = graph.node(run.start_node_key).position_local, graph.node(run.end_node_key).position_local
        spec_key = run.role
        if run.role == "END_POST":
            spec_key += "_LEFT" if (a[0] + b[0]) / 2 < definition.span / 2 else "_RIGHT"
        # X x Y = longitudinal: -normal gives Y = normal x longitudinal.
        # Thus positive section Y is up for a forward horizontal chord.
        section_u = tuple(-v for v in frame[3])
        from .assemblies import expand_run
        items.extend(expand_run(RealizationItem(run.key, run.role, run.start_node_key, run.end_node_key,
                                     a, b, transform_point(a, frame), transform_point(b, frame),
                                     section_u, specs[spec_key])))
    return Candidate(config, stations, graph, runs, tuple(items), warnings)


def structural_signature(candidate):
    return (candidate.config["envelope_type"], "Custom" if candidate.config.get("topology_mode")=="Custom" else candidate.config["topology_preset"],
            candidate.stations.panel_count,
            tuple((n.key, n.affiliations) for n in candidate.graph.nodes),
            tuple((e.key, e.start_node_key, e.end_node_key) for e in candidate.graph.edges),
            tuple((r.key, r.start_node_key, r.end_node_key, r.edge_keys) for r in candidate.runs),
            tuple(sorted((i.run_key, i.assembly_key, i.component_key) for i in candidate.items)))


def plan_regeneration(candidate, applied=None, bindings=None, conflicts=None):
    bindings, conflicts = bindings or {}, conflicts or {}
    before = {i.key: i for i in applied.items} if applied else {}
    after = {i.key: i for i in candidate.items}
    actions = []
    for key in sorted(set(before) | set(after)):
        if key in conflicts:
            action, reason = "CONFLICT", conflicts[key]
        elif key not in after:
            action, reason = "REMOVE_EXISTING", ""
        elif key not in before:
            action, reason = "CREATE_NEW", ""
        else:
            action = "UNCHANGED" if equivalent(asdict(before[key]), asdict(after[key])) else "UPDATE_EXISTING"
            reason = ""
        actions.append(RegenerationAction(key, action, bindings.get(key, ""), reason))
    structural = applied is None or structural_signature(candidate) != structural_signature(applied)
    return RegenerationPlan(tuple(actions), structural)


def equivalent(a, b):
    """Ignore only floating-point frame roundoff, never semantic identity changes."""
    if isinstance(a, dict) and isinstance(b, dict):
        return set(a) == set(b) and all(equivalent(a[key], b[key]) for key in a)
    if isinstance(a, (list, tuple)) and isinstance(b, (list, tuple)):
        return len(a) == len(b) and all(equivalent(x,y) for x,y in zip(a,b))
    if isinstance(a, (int,float)) and isinstance(b, (int,float)):
        return math.isclose(a,b,abs_tol=1e-8,rel_tol=1e-12)
    return a == b
