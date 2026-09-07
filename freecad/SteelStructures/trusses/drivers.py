"""One active station driver. Targets are discrete approximations, never advice."""
import math
from functools import lru_cache
from .models import Station, StationPlan, EnvelopeDefinition
from .panelization import panelize
from .envelope import validate_envelope
from .preset_contracts import PRESETS, validate_preset

DRIVERS = ("ByPanelCount", "ByTargetSpacing", "ByTargetDiagonalAngle", "CustomSpacingList")


def diagonal_angles(definition, plan, preset, connection):
    from .patterns import generate_topology
    graph=generate_topology(definition,plan,preset,connection)
    positions={node.key:node.position_local for node in graph.nodes}
    values=[]
    for edge in graph.edges:
        if edge.role!="DIAGONAL": continue
        a,b=positions[edge.start_node_key],positions[edge.end_node_key]
        values.append(math.degrees(math.atan2(abs(b[1]-a[1]),abs(b[0]-a[0]))))
    if not values: raise ValueError("O padrão não possui diagonais avaliáveis.")
    return sum(values)/len(values), min(values), max(values)


def spacing_plan(definition, spacings):
    if not isinstance(spacings,(list,tuple)) or len(spacings)<4 or len(spacings)>200:
        raise ValueError("Informe de 4 a 200 espaçamentos absolutos.")
    if any(isinstance(s,bool) or not isinstance(s,(int,float)) or not math.isfinite(s) or s<=1e-7 for s in spacings):
        raise ValueError("Todos os espaçamentos devem ser positivos e finitos.")
    total=math.fsum(spacings)
    if abs(total-definition.span)>1e-6:
        raise ValueError(f"Soma dos espaçamentos: {total:g} mm; vão da referência: {definition.span:g} mm.")
    positions=[0.]+[math.fsum(spacings[:i]) for i in range(1,len(spacings)+1)]
    apex=definition.span*definition.apex_position
    apex_index=next((i for i,x in enumerate(positions) if abs(x-apex)<=1e-6),None)
    if definition.kind=="DuoPitch" and apex_index is None:
        raise ValueError("A lista não contém a estação obrigatória da cumeeira.")
    stations=[]
    for i,x in enumerate(positions):
        key="S_START" if i==0 else "S_END" if i==len(spacings) else "S_APEX" if definition.kind=="DuoPitch" and i==apex_index else f"S_LIST_{i}"
        stations.append(Station(key,x,key in ("S_START","S_END","S_APEX")))
    return StationPlan(tuple(stations),len(spacings),apex_index if definition.kind=="DuoPitch" else 0,
                       len(spacings)-apex_index if definition.kind=="DuoPitch" else 0)


@lru_cache(maxsize=128)
def _solve(kind,span,height,apex,preset,connection,mode,target):
    definition=EnvelopeDefinition(kind,span,height,apex)
    options=[]
    for count in range(PRESETS[preset].minimum_panels,201):
        try:
            plan=panelize(definition,count)
            validate_preset(definition,plan,preset)
            actual=span/count if mode=="ByTargetSpacing" else diagonal_angles(definition,plan,preset,connection)[0]
            options.append((abs(actual-target),count,plan))
        except ValueError:
            continue
    if not options: raise ValueError("Nenhuma distribuição compatível até 200 painéis.")
    return min(options,key=lambda value:(value[0],value[1]))[2]


def resolve_panelization(config, definition, allocation=None):
    validate_envelope(definition)
    mode=config.get("panelization_mode","ByPanelCount")
    if mode not in DRIVERS: raise ValueError("Driver de panelização desconhecido.")
    preset=config["topology_preset"]
    if preset not in PRESETS: raise ValueError("Padrão de treliça desconhecido.")
    custom=config.get("topology_mode","Preset")=="Custom"
    if mode=="ByPanelCount":
        if config["panel_count"]>200: raise ValueError("Máximo de 200 painéis.")
        plan=panelize(definition,config["panel_count"],allocation)
    elif mode=="CustomSpacingList":
        plan=spacing_plan(definition,config.get("custom_spacings",[]))
    else:
        target=config.get("target_spacing",1000.) if mode=="ByTargetSpacing" else config.get("target_angle",45.)
        if not math.isfinite(target) or target<=0 or (mode=="ByTargetDiagonalAngle" and target>=90):
            raise ValueError("Alvo inválido; espaçamento > 0 e ângulo entre 0 e 90 graus.")
        if mode=="ByTargetDiagonalAngle" and (custom or not PRESETS[preset].angle_family):
            raise ValueError("Ângulo-alvo indisponível: este grafo não define uma família inequívoca de diagonais.")
        plan=_solve(definition.kind,definition.span,definition.height,definition.apex_position,"Custom" if custom else preset,
                    config.get("x_connection","Disconnected"),mode,float(target))
    if not custom: validate_preset(definition,plan,preset)
    values=[b.x-a.x for a,b in zip(plan.stations,plan.stations[1:])]
    result=dict(panel_count=plan.panel_count,spacing=definition.span/plan.panel_count,
                minimum_spacing=min(values),maximum_spacing=max(values),total=math.fsum(values))
    if mode=="ByTargetDiagonalAngle":
        result["angle"],result["minimum_angle"],result["maximum_angle"]=diagonal_angles(
            definition,plan,preset,config.get("x_connection","Disconnected"))
    return plan,result
