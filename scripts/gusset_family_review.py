"""Read-only FCStd inventory and offline family proposals; not a production generator."""
from collections import Counter, defaultdict
from dataclasses import asdict, replace
import hashlib
import html
import json
import math
from pathlib import Path
import sys
import textwrap
from types import SimpleNamespace
from unittest.mock import patch
import xml.etree.ElementTree as ET
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from freecad.SteelStructures.trusses import gussets as g
from freecad.SteelStructures.trusses.connections import connection_participants
from freecad.SteelStructures.trusses.realization import build_candidate, reference_frame
from freecad.SteelStructures.connections.gusset import polygon_area, _hull
from scripts.gusset_phase1_proposals import dot, neg, corners, halfplanes, polygon, clip

FAMILIES = {
    'F01': 'Uma barra da alma + banzo passante',
    'F02': 'Diagonal + montante / dois terminais distintos',
    'F03': 'Duas diagonais + banzo passante',
    'F04': 'Duas diagonais + montante — preservar',
    'F05': 'Cumeeira / duas diagonais sem montante',
    'F06': 'Cumeeira / duas diagonais + montante — preservar',
    'F07': 'Fechamento terminal',
    'F08': 'Alma passante / encontro K',
    'F09': 'Leque com mais de três barras da alma',
}


def unit(v):
    size = math.hypot(*v)
    return tuple(x/size for x in v)


def perp(v):
    return (-v[1], v[0])


def clean(poly):
    return list(_hull(poly)) if len(poly) >= 3 else []


def classify(participants, supports):
    webs = [p for p in participants if p.role not in g.CHORD_ROLES]
    roles = Counter(p.role for p in webs)
    ridge = any(p.end == 'ChordBreak' for p in participants if p.role in g.CHORD_ROLES)
    terminal = any(s.kind == 'TERMINAL_BOUNDARY' for s in supports)
    if ridge:
        return 'F06' if roles == {'DIAGONAL': 2, 'VERTICAL': 1} else 'F05'
    if terminal:
        return 'F07'
    if any(p.end == 'Through' for p in webs):
        return 'F08'
    if roles == {'DIAGONAL': 2, 'VERTICAL': 1}:
        return 'F04'
    if len(webs) > 3:
        return 'F09'
    if len(webs) == 1:
        return 'F01'
    if roles == {'DIAGONAL': 2}:
        return 'F03'
    if len(webs) == 2:
        return 'F02'
    raise ValueError('Unclassified physical configuration: '+str(roles))


def validation(case, points):
    if len(points) < 3:
        return dict(ok=False, issues=['Contorno não fechado'], min_margin=None)
    lines = halfplanes(points)
    # Coverage is clipped only by physical chord/terminal limits.
    missing = [p for p in case['coverage'] if any(dot(n,p)>h+1e-6 for n,h in lines)]
    margins, hard_violation, lost_contact, measurements = [], [], [], []
    for n,h in lines:
        physical = any(math.dist(n,hn)<1e-6 and abs(h-hh)<1e-5 for hn,hh in case['hard'])
        if not physical:
            governing=max(case['tips'],key=lambda p:dot(n,p))
            value=h-dot(n,governing)
            margins.append(value)
            measurements.append(dict(normal=n,offset=h,margin=value,governing=governing))
    for n,h in case['hard']:
        if any(dot(n,p)>h+1e-6 for p in points):
            hard_violation.append((n,h))
        if sum(abs(dot(n,p)-h)<1e-5 for p in points)<2:
            lost_contact.append((n,h))
    contact_shortened = any(any(dot(n,p)>h+1e-6 for n,h in lines) for p in case['contact_points'])
    intersecting = []
    for key, member in case['foreign']:
        result = member
        for n,h in lines:
            result = clip(result,n,h)
        if len(result)>=3 and polygon_area(result)>1e-5:
            intersecting.append(key)
    issues = []
    if missing: issues.append('Cobertura fora: '+str(len(missing))+' pontos')
    if margins and min(margins)<case['margin']-1e-6: issues.append('Margem terminal inferior à configurada')
    if hard_violation: issues.append('Ultrapassa limite físico')
    if lost_contact: issues.append('Limite físico sem aresta ativa')
    if contact_shortened: issues.append('Contato atual encurtado')
    if intersecting: issues.append('Interseção projetada com não participante')
    return dict(ok=not issues, issues=issues, min_margin=min(margins) if margins else None,
                uncovered_points=missing, margin_measurements=measurements,
                nonparticipant_intersections=sorted(set(intersecting)))


def make_case(owner, config, candidate, saved, outline, data):
    spec, corridors, supports = data
    node = spec.node_key
    participants = connection_participants(candidate,node)
    roles = {p.participant_key:p.role for p in participants}
    hard = [(s.normal,s.offset) for s in supports if s.kind in ('CHORD_BOUNDARY','TERMINAL_BOUNDARY')]
    chord = [(s.normal,s.offset) for s in supports if s.kind=='CHORD_BOUNDARY']
    webs = [c for c in corridors if roles[c.participant_key] not in g.CHORD_ROLES]
    raw = [p for c in webs for p in corners(c,spec.member_overlap)]
    tips = [p for c in webs for p in corners(c,spec.member_overlap)[1:3]]
    contact_points = [p for e in outline.semantic_edges if e.kind=='CHORD_BOUNDARY' for p in (e.start,e.end)]
    coverage = list(_hull(raw))
    for n,h in hard:
        coverage = clip(coverage,n,h)
    # Minimum auditable envelope: raw coverage + configured terminal margin.
    # No new global margin on proximal rectangles. Existing lateral contract is
    # recorded separately in supports and must be approved before replacement.
    def demand(n):
        return max(max(dot(n,p) for p in raw), max(dot(n,p) for p in tips)+spec.edge_margin,
                   max((dot(n,p) for p in contact_points), default=-float('inf')))
    axes = [(math.cos(i*math.pi/180),math.sin(i*math.pi/180)) for i in range(360)]
    axes += [s.normal for s in supports]+[n for n,h in halfplanes(list(_hull(raw))) ]
    envelope = polygon(hard+[(n,demand(n)) for n in axes])
    participating = {k for p in participants for k in p.physical_run_keys}
    origin = candidate.graph.node(node).position_local
    foreign = []
    for run in candidate.runs:
        if run.key in participating: continue
        start = candidate.graph.node(run.start_node_key).position_local
        end = candidate.graph.node(run.end_node_key).position_local
        desc = SimpleNamespace(node_key=run.start_node_key,participant_key=run.key)
        for c in g._corridors(candidate,desc,run,reference_frame(config)):
            points = [tuple(p[i]+start[i]-origin[i] for i in range(2))
                      for p in corners(c,math.dist(start,end))]
            foreign.append((run.key,points))
    result = dict(owner=owner, envelope_type=config['envelope_type'], preset=config['topology_preset'],
        node=node, plate=saved['name'], saved=saved['signature']['points'], current=list(outline.points),
        participants=participants, corridors=corridors, supports=supports, roles=roles,
        raw=raw, tips=tips, hard=hard, chord=chord, coverage=coverage, envelope=envelope,
        margin=spec.edge_margin, overlap=spec.member_overlap, thickness=spec.plate_thickness,
        demand=demand, contact_points=contact_points, foreign=foreign,
        attachment=asdict(outline.attachment), spec=asdict(spec), proposals=[])
    result['semantic_edges']=[asdict(e) for e in outline.semantic_edges]
    result['family'] = classify(participants,supports)
    result['current_validation'] = validation(result,result['current'])
    result['saved_equals_current'] = same_polygon(result['saved'],result['current'])
    return result


def same_polygon(a,b):
    return len(a)==len(b) and all(min(math.dist(p,q) for q in b)<1e-6 for p in a)


def propose(case):
    family = case['family']
    if family in ('F01','F04','F06'):
        case['proposals'] = [dict(name='Manter contorno atual', points=case['current'],
            validation=case['current_validation'], retained=True)]
        return
    def add(name,normals):
        pts = clean(polygon(case['hard']+[(n,case['demand'](n)) for n in normals]))
        case['proposals'].append(dict(name=name,points=pts,validation=validation(case,pts),retained=False))
    directions = {}
    for c in case['corridors']:
        if case['roles'][c.participant_key] not in g.CHORD_ROLES:
            directions.setdefault(c.participant_key,c.direction)
    if case['chord']:
        inward = unit(neg(tuple(sum(n[i] for n,h in case['chord']) for i in range(2))))
        tangent = perp(inward)
    else:
        through = next(p for p in case['participants'] if p.end=='Through')
        inward = directions[through.participant_key]
        tangent = perp(inward)
    if family=='F02':
        # Distinguished transverse participant is chosen geometrically, not by NodeKey.
        ordered = sorted(directions.values(),key=lambda d:dot(d,inward),reverse=True)
        anchor, other = ordered
        lateral = perp(anchor)
        add('S — fechamento pelo banzo (B2 generalizado)',[lateral,neg(lateral),anchor,inward])
        add('L — caps limitados lateralmente (A1 generalizado)',[lateral,neg(lateral),anchor,other])
    elif family=='F03':
        add('S — faixa de quatro lados',[tangent,neg(tangent),inward])
        add('L — leque com caps limitados',[tangent,neg(tangent),inward]+list(directions.values()))
    elif family=='F05':
        add('C — dois contatos e fechamento reto (C1)',[tangent,neg(tangent),inward])
    elif family=='F07':
        if len(directions)==1:
            case['proposals']=[dict(name='Manter terminal simples',points=case['current'],
                validation=case['current_validation'],retained=True)]
        else:
            add('S — terminal com fechamento reto',[tangent,neg(tangent),inward])
            oblique = min(directions.values(),key=lambda d:dot(d,inward))
            add('L — terminal chanfrado por direção física',[tangent,neg(tangent),inward,oblique])
    elif family=='F08':
        case['proposals'].append(dict(name='Manter K atual — opção de referência',points=case['current'],
            validation=case['current_validation'],retained=True))
        ending=[p for p in case['participants'] if p.end!='Through']
        add('K — banda passante e caps dos terminais',
            [inward,neg(inward),tangent,neg(tangent)]+[directions[p.participant_key] for p in ending])
    elif family=='F09':
        case['proposals'].append(dict(name='Manter leque atual — opção de referência',points=case['current'],
            validation=case['current_validation'],retained=True))
        ordered=sorted(directions.values(),key=lambda d:math.atan2(dot(d,tangent),dot(d,inward)))
        add('F — leque por direções extremas',[tangent,neg(tangent),inward,ordered[0],ordered[-1]])


def fingerprint(case):
    # Exact geometry in the local truss plane: translation ignored, mirrors kept visible.
    records = sorted((case['roles'][c.participant_key],
        next(p.end for p in case['participants'] if p.participant_key==c.participant_key),
        next((p.assembly,p.geometry_key) for p in case['participants'] if p.participant_key==c.participant_key),
        tuple(round(v,7) for v in c.direction), round(c.transverse_low,7),round(c.transverse_high,7))
        for c in case['corridors'])
    physical = sorted((tuple(round(v,7) for v in n),round(h,7)) for n,h in case['hard'])
    return json.dumps((case['family'],records,physical,case['margin'],case['overlap'],case['thickness'],
        round(case['attachment']['plate_low'],7),round(case['attachment']['plate_high'],7),
        case['attachment']['kind'],case['attachment']['placement_kind'],case['attachment']['governing_surface_class']))


def covariance_checks(case):
    """Check the review rules on transformed extracted physical data, not FCStd objects."""
    angle=math.radians(37)
    transforms=[('reflection_x',((-1.,0.),(0.,1.)),1.),
                ('rotation_37deg',((math.cos(angle),-math.sin(angle)),(math.sin(angle),math.cos(angle))),1.),
                ('scale_1_1',((1.,0.),(0.,1.)),1.1)]
    results=[]
    for name,matrix,scale in transforms:
        def direction(v): return tuple(dot(row,v) for row in matrix)
        def point(p): return tuple(scale*v for v in direction(p))
        changed=dict(case)
        for key in ('current','saved','raw','tips','coverage','envelope','contact_points'):
            changed[key]=[point(p) for p in case[key]]
        for key in ('current','saved','coverage','envelope'):
            changed[key]=clean(changed[key])
        for key in ('hard','chord'):
            changed[key]=[(direction(n),scale*h) for n,h in case[key]]
        changed['margin']=scale*case['margin']
        changed['foreign']=[(key,clean([point(p) for p in member])) for key,member in case['foreign']]
        changed['corridors']=[replace(c,direction=direction(c.direction)) for c in case['corridors']]
        changed['demand']=lambda n:max(max(dot(n,p) for p in changed['raw']),
            max(dot(n,p) for p in changed['tips'])+changed['margin'],
            max((dot(n,p) for p in changed['contact_points']),default=-float('inf')))
        changed['current_validation']=validation(changed,changed['current'])
        changed['proposals']=[]
        propose(changed)
        errors=[]
        for initial,actual in zip(case['proposals'],changed['proposals']):
            expected=[point(p) for p in initial['points']]
            error=max(min(math.dist(p,q) for q in actual['points']) for p in expected)
            assert len(expected)==len(actual['points']) and error<1e-6,(name,case['node'],error)
            assert actual['validation']['ok'],(name,case['node'],actual['validation'])
            errors.append(error)
        results.append(dict(transform=name,max_vertex_error_mm=max(errors)))
    return results


def svg(case, group_id, occurrences):
    proposals=case['proposals']
    count=1+len(proposals)
    width=650*count
    out=[f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="740" viewBox="0 0 {width} 740">',
         '<rect width="100%" height="100%" fill="#f8fafc"/>',
         '<g font-family="Arial, sans-serif" fill="#172b42">',
         f'<text x="24" y="30" font-size="22" font-weight="bold">{group_id} · {html.escape(FAMILIES[case["family"]])}</text>',
         f'<text x="24" y="55" font-size="15">{case["owner"]} / {case["node"]} · {case["envelope_type"]} {case["preset"]}</text>']
    legend=[('#2563eb','Atual C6-P'),('#94a3b8','Persistido FCStd'),('#15803d','Proposta'),('#f59e0b','Cobertura + margem terminal'),('#dc2626','Violação / extremos'),('#172b42','Limite físico')]
    for i,(color,label) in enumerate(legend):
        x=24+i*min((width-50)/6,255)
        out.append(f'<path d="M{x} 81h22" stroke="{color}" stroke-width="3"/><text x="{x+28}" y="86" font-size="13">{label}</text>')
    geometry=case['current']+case['saved']+case['envelope']+[p for a in proposals for p in a['points']]
    lo=[min(p[i] for p in geometry)-30 for i in range(2)]
    hi=[max(p[i] for p in geometry)+30 for i in range(2)]
    scale=min(540/(hi[0]-lo[0]),360/(hi[1]-lo[1]))
    allpanels=[dict(name='Atual / comparação com persistido',points=case['current'],validation=case['current_validation'],retained=True)]+proposals
    roletext=', '.join(f'{n} {r}' for r,n in sorted(Counter(p.role for p in case['participants']).items()))
    for col,entry in enumerate(allpanels):
        x0=col*650+15
        out.append(f'<rect x="{x0}" y="104" width="620" height="535" fill="white" stroke="#d6e0eb" rx="8"/>')
        out.append(f'<text x="{x0+15}" y="132" font-size="17" font-weight="bold">{html.escape(entry["name"])}</text>')
        out.append(f'<text x="{x0+15}" y="154" font-size="12">{roletext}</text>')
        def transform(p):
            return (x0+310+(p[0]-(lo[0]+hi[0])/2)*scale,360-(p[1]-(lo[1]+hi[1])/2)*scale)
        def draw(points,stroke,fill='none',dash='',sw=2,opacity=1):
            pts=' '.join(f'{x:.3f},{y:.3f}' for x,y in map(transform,points))
            out.append(f'<polygon points="{pts}" stroke="{stroke}" stroke-width="{sw}" fill="{fill}" fill-opacity="{opacity}" stroke-dasharray="{dash}"/>')
        for c in case['corridors']:
            draw(corners(c,case['overlap']+20),'#94a3b8','#cbd5e1',sw=.8,opacity=.25)
        draw(case['envelope'],'#d97706','#fbbf24',sw=1,opacity=.32)
        draw(case['saved'],'#94a3b8',dash='5 5',sw=1.4)
        draw(case['current'],'#2563eb',sw=2.5)
        if col:
            draw(entry['points'],'#15803d' if entry['validation']['ok'] else '#dc2626',dash='7 3' if entry['retained'] else '',sw=3)
        for measurement in entry['validation'].get('margin_measurements',()):
            if measurement['margin'] >= case['margin']-1e-6: continue
            n,h=measurement['normal'],measurement['offset']
            ends=[p for p in entry['points'] if abs(dot(n,p)-h)<1e-5]
            if len(ends)>=2:
                a,b=transform(ends[0]),transform(ends[-1])
                out.append(f'<path d="M{a[0]},{a[1]}L{b[0]},{b[1]}" stroke="#dc2626" stroke-width="4"/>')
        for n,h in case['hard']:
            pts=[p for p in entry['points'] if abs(dot(n,p)-h)<1e-5]
            if len(pts)>=2:
                a,b=transform(pts[0]),transform(pts[-1])
                out.append(f'<path d="M{a[0]},{a[1]}L{b[0]},{b[1]}" stroke="#172b42" stroke-width="3.5"/>')
        for p in case['tips']:
            x,y=transform(p)
            out.append(f'<circle cx="{x}" cy="{y}" r="3" fill="#dc2626"/>')
        x,y=transform((0,0))
        out.append(f'<path d="M{x-4},{y}h8 M{x},{y-4}v8" stroke="#172b42"/>')
        val=entry['validation']
        color='#166534' if val['ok'] else '#b91c1c'
        status='Sem violação na triagem 2D' if val['ok'] else '; '.join(val['issues'])
        for row,line in enumerate(textwrap.wrap(status,80)):
            out.append(f'<text x="{x0+15}" y="{568+row*17}" font-size="13" fill="{color}">{html.escape(line)}</text>')
        margin='n/a' if val['min_margin'] is None else f'{val["min_margin"]:.3f}'
        info=f'{len(entry["points"])} faces · área {polygon_area(entry["points"]):.0f} mm² · margem terminal {margin} mm'
        out.append(f'<text x="{x0+15}" y="622" font-size="12">{info}</text>')
    refs='; '.join(c['owner'].replace('StructuralTruss','T')+'/'+c['node'] for c in occurrences)
    for i,line in enumerate(textwrap.wrap('Ocorrências: '+refs,max(95,int(width/7.5)))):
        out.append(f'<text x="24" y="{665+i*18}" font-size="13">{html.escape(line)}</text>')
    out.append(f'<text x="24" y="720" font-size="13">Margem proximal global NÃO adicionada. Regiões de margem lateral exigem aprovação do contrato. Ver relatório; não é validação de sólidos.</text>')
    return '\n'.join(out+['</g></svg>'])


def hashes():
    return {str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()
            for folder in ('freecad','tests') for p in (ROOT/folder).rglob('*.py')}


def main(source):
    source_hash=hashlib.sha256(source.read_bytes()).hexdigest()
    before=hashes()
    with zipfile.ZipFile(source,'r') as archive:
        root=ET.fromstring(archive.read('Document.xml'))
    owners,plates=[],[]
    for obj in root.findall('./ObjectData/Object'):
        props={p.get('name'):p[0].get('value') for p in obj.findall('./Properties/Property') if len(p)}
        if 'AppliedState' in props:
            owners.append((obj.get('name'),json.loads(props['AppliedState'])['candidate']['config']))
        if 'NodeKey' in props and 'ParentTruss' in props:
            plates.append(dict(name=obj.get('name'),owner=props['ParentTruss'],node=props['NodeKey'],
                               signature=json.loads(props['SourceSignature'])))
    cases=[]
    failures=[]
    for owner,config in owners:
        candidate=build_candidate(config)
        captured={}
        original=g.build_gusset_outline
        def capture(spec,corridors,supports):
            captured[spec.node_key]=(spec,corridors,supports)
            return original(spec,corridors,supports)
        with patch.object(g,'build_gusset_outline',capture):
            outlines,diagnostics=g.preliminary_gusset_outlines(candidate)
        bynode={o.spec.node_key:o for o in outlines}
        for saved in plates:
            if saved['owner']!=owner: continue
            node=saved['node']
            if node not in bynode:
                failures.append(dict(plate=saved['name'],owner=owner,node=node,diagnostics=[asdict(d) for d in diagnostics]))
                continue
            case=make_case(owner,config,candidate,saved,bynode[node],captured[node])
            propose(case)
            cases.append(case)
    grouped=defaultdict(list)
    for case in cases: grouped[fingerprint(case)].append(case)
    output=ROOT/'Documentation'/'gusset_family_review'
    output.mkdir(exist_ok=True)
    groups=defaultdict(list)
    counters=Counter()
    for key,occurrences in sorted(grouped.items(),key=lambda item:(item[1][0]['family'],item[1][0]['owner'],item[1][0]['node'])):
        case=occurrences[0]
        family=case['family']
        counters[family]+=1
        gid=f'{family}_{counters[family]:02}'
        checks=covariance_checks(case)
        (output/(gid+'.svg')).write_text(svg(case,gid,occurrences),encoding='utf8')
        for c in occurrences:
            c['group']=gid
            c['covariance_checks']=checks
        groups[family].append((gid,occurrences))
    report=[]
    for case in cases:
        report.append({k:v for k,v in case.items() if k not in ('demand','foreign','roles')})
    data=dict(source=str(source.resolve()),source_sha256=source_hash,trusses=len(owners),
              persistent_plates=len(plates),recomputed=len(cases),failures=failures,
              configurations=len(grouped),cases=report)
    def encode(obj):
        if hasattr(obj,'__dataclass_fields__'): return asdict(obj)
        if hasattr(obj,'value'): return obj.value
        raise TypeError(type(obj).__name__)
    (output/'inventario.json').write_text(json.dumps(data,ensure_ascii=False,indent=2,default=encode),encoding='utf8')
    md=['# Inventário completo e matriz por objeto','',
        f'{len(owners)} treliças; {len(plates)} chapas persistentes; {len(cases)} recalculadas; {len(grouped)} configurações geométricas distintas.','',
        'Equivalência usada: mesmas seções projetadas, direções, extremidades, limites físicos, parâmetros e faixa transversal. Translações não diferenciam casos; espelhos e inclinações distintos permanecem visíveis.','',
        '| Treliça | Envelope / padrão | Chapa | NodeKey | Família / desenho | Persistido = atual | Triagem atual |',
        '|---|---|---|---|---|---|---|']
    for c in cases:
        md.append(f'| {c["owner"]} | {c["envelope_type"]} / {c["preset"]} | {c["plate"]} | {c["node"]} | [{c["group"]}]({c["group"]}.svg) | {"sim" if c["saved_equals_current"] else "não"} | {"OK 2D" if c["current_validation"]["ok"] else "; ".join(c["current_validation"]["issues"])} |')
    md+=['','## Matriz resumida: quantidade de chapas por regra','',
         '| Treliça / padrão | '+' | '.join(FAMILIES)+' |','|---|'+'---:|'*len(FAMILIES)]
    for owner,config in owners:
        counts=Counter(c['family'] for c in cases if c['owner']==owner)
        md.append(f'| {owner} / {config["topology_preset"]} | '+' | '.join(str(counts[f]) for f in FAMILIES)+' |')
    (output/'MATRIZ.md').write_text('\n'.join(md)+'\n',encoding='utf8')
    details=['# Configurações físicas distintas','',
        'Ângulos em graus no plano local da treliça, eixo x positivo. As duas direções de uma barra passante aparecem separadas.','',
        '| Configuração | Participantes (papel, extremidade; ângulos dos corredores) | Normais e offsets dos limites físicos (mm) | Estado |','|---|---|---|---|']
    for family,items in groups.items():
        for gid,occurrences in items:
            c=occurrences[0]
            parts=[]
            for p in c['participants']:
                angles=sorted({round(math.degrees(math.atan2(cr.direction[1],cr.direction[0])),3)
                               for cr in c['corridors'] if cr.participant_key==p.participant_key})
                parts.append(f'{p.role} / {p.end}: {angles}')
            limits='; '.join(f'{s.kind}: ({s.normal[0]:.4f}, {s.normal[1]:.4f}) · p ≤ {s.offset:.4f}'
                            for s in c['supports'] if s.kind in ('CHORD_BOUNDARY','TERMINAL_BOUNDARY'))
            state=('Protegida' if family in ('F04','F06') else 'Diferença métrica reproduzida' if not c['current_validation']['ok'] else 'Sem violação na triagem; avaliar forma')
            details.append(f'| [{gid}]({gid}.svg) | '+ '; '.join(parts)+' | '+(limits or 'Sem banzo; alma passante')+' | '+state+' |')
    details+=['','## Distâncias insuficientes medidas','',
        '| Chapa | Nó | Borda | Distância livre medida (mm) | EdgeMargin (mm) |','|---|---|---|---:|---:|']
    for c in cases:
        for m in c['current_validation']['margin_measurements']:
            if m['margin']>=c['margin']-1e-6: continue
            provenance=[e['kind'] for e in c['semantic_edges']
                        if max(abs(dot(m['normal'],e[p])-m['offset']) for p in ('start','end'))<1e-5]
            details.append(f'| {c["plate"]} | {c["owner"]}/{c["node"]} | {", ".join(provenance)} | {m["margin"]:.6f} | {c["margin"]:.3f} |')
    (output/'CONFIGURACOES.md').write_text('\n'.join(details)+'\n',encoding='utf8')
    page=['<!doctype html><html lang="pt-BR"><meta charset="utf-8"><title>Gussets — revisão por famílias</title>',
          '<style>body{font:16px Arial;background:#f1f5f9;color:#172b42;margin:28px;max-width:1800px}a{color:#185abc}img{width:100%;height:auto;background:white;border:1px solid #cbd5e1}article{background:white;padding:18px;margin:18px 0}h2{margin-top:42px}p{line-height:1.5}nav a{display:inline-block;margin:7px}</style>',
          '<h1>Gussets — inventário completo e propostas por família</h1>',
          f'<p>{len(owners)} treliças · {len(plates)} chapas · {len(grouped)} configurações. Estudo offline, gerador intacto.</p>',
          '<p><a href="ESTRATEGIA.md">Estratégia e decisões pendentes</a> · <a href="MATRIZ.md">Matriz completa</a> · <a href="CONFIGURACOES.md">Geometria e medições</a> · <a href="inventario.json">Coordenadas, parâmetros e diagnósticos</a></p>',
          '<p>Azul: atual; cinza: persistido; verde: proposta ou manutenção. Amarelo: cobertura física + margem nos extremos; margem proximal global não adicionada. Vermelho: proposta reprovada na triagem ou pontos governantes. OK 2D não significa aprovação estética ou validação de sólidos.</p><nav>']
    for family in groups: page.append(f'<a href="#{family}">{family} · {html.escape(FAMILIES[family])}</a>')
    page.append('</nav>')
    for family,items in groups.items():
        page.append(f'<h2 id="{family}">{family} — {html.escape(FAMILIES[family])}</h2>')
        for gid,occurrences in items:
            refs='; '.join(c['owner']+'/'+c['node'] for c in occurrences)
            page.append(f'<article><h3><a href="{gid}.svg">{gid} — abrir SVG</a></h3><p>{html.escape(refs)}</p><img src="{gid}.svg" alt="Comparação {gid}" loading="lazy"></article>')
    page.append('</html>')
    (output/'index.html').write_text('\n'.join(page),encoding='utf8')
    assert source_hash==hashlib.sha256(source.read_bytes()).hexdigest()
    assert before==hashes(), 'Production or tests changed during review'
    assert len(cases)+len(failures)==len(plates)
    print(json.dumps(dict(trusses=len(owners),plates=len(plates),recomputed=len(cases),groups=len(grouped),
        families=Counter(c['family'] for c in cases),changed=sum(not c['saved_equals_current'] for c in cases),
        failures=failures,current_issues=[(c['plate'],c['current_validation']['issues']) for c in cases if not c['current_validation']['ok']],
        proposal_issues=[(c['plate'],a['name'],a['validation']['issues']) for c in cases for a in c['proposals'] if not a['validation']['ok']]),ensure_ascii=True))


if __name__=='__main__':
    main(Path(sys.argv[1]))
