"""Offline depth calibration; FCStd hash checked, no FreeCAD or dependencies."""
from dataclasses import asdict, replace
import hashlib
import html
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts import gusset_family_review as review
from freecad.SteelStructures.connections import gusset_families as f
from freecad.SteelStructures import profile_catalog
from tests.test_gusset_families_round1 import compute
from tests.test_connections_c5b_polish import three_web_config
from tests.test_gusset_plate_c6a import configured


def render(case, studies, maxima):
    geometry = case['current']+case['envelope']
    geometry += [p for c in case['corridors'] for p in review.corners(c,case['overlap']+20)]
    lo = [min(p[i] for p in geometry)-20 for i in range(2)]
    hi = [max(p[i] for p in geometry)+20 for i in range(2)]
    scale = min(530/(hi[0]-lo[0]),330/(hi[1]-lo[1]))
    out = ['<svg xmlns="http://www.w3.org/2000/svg" width="1800" height="840" viewBox="0 0 1800 840">',
        '<rect width="100%" height="100%" fill="#f8fafc"/><g font-family="Arial" fill="#172b42">']
    def text(x,y,line,size=16,color='#172b42'):
        out.append(f'<text x="{x}" y="{y}" font-size="{size}" fill="{color}">{html.escape(line)}</text>')
    text(24,32,case['group']+' — calibração da profundidade local',24)
    text(24,60,case['owner']+' / '+case['node'])
    text(24,88,'Azul tracejado: original recalculado • Amarelo: envelope obrigatório • Verde: admissível • Magenta: corte perpendicular')
    for col,entry in enumerate(studies):
        x0=600*col
        out.append(f'<rect x="{x0+12}" y="108" width="576" height="596" fill="white" stroke="#cbd5e1"/>')
        color = '#15803d' if entry['accepted'] else '#be123c'
        text(x0+26,137,f'{entry["fraction"]:.0%} H — '+('ACEITO' if entry['accepted'] else 'REJEITADO')+
             (' / SELECIONADO' if entry['fraction']==.4 and entry['accepted'] else ''),20,color)
        if not entry['accepted']:
            text(x0+26,161,'Verde pontilhado: maior alternativa física, NÃO aplicada',14,'#15803d')
        out.append(f'<defs><clipPath id="panel{col}"><rect x="{x0+14}" y="174" width="572" height="325"/></clipPath></defs><g clip-path="url(#panel{col})">')
        def tr(p):
            return (x0+300+(p[0]-(lo[0]+hi[0])/2)*scale,335-(p[1]-(lo[1]+hi[1])/2)*scale)
        def poly(points,stroke,fill='none',dash='',width=2):
            pts=' '.join(f'{x:.3f},{y:.3f}' for x,y in map(tr,points))
            out.append(f'<polygon points="{pts}" fill="{fill}" fill-opacity=".25" stroke="{stroke}" stroke-width="{width}" stroke-dasharray="{dash}"/>')
        for corridor in case['corridors']:
            poly(review.corners(corridor,case['overlap']+20),'#94a3b8','#cbd5e1',width=.8)
        poly(case['envelope'],'#d97706','#fbbf24',width=1)
        poly(case['current'],'#2563eb',dash='6 4')
        poly(entry['candidate'],color,width=3)
        if not entry['accepted']:
            poly(case['maximum_candidate'],'#15803d',dash='3 3',width=3)
        for cut in entry['cuts']:
            a,b=tr(cut['cut_point']),tr(cut['contact_point'])
            out.append(f'<path d="M{a[0]},{a[1]}L{b[0]},{b[1]}" stroke="#a21caf" stroke-width="4"/>')
        out.append('</g>')
        cuts=entry['cuts']
        text(x0+26,535,f'H = {cuts[0]["local_height"]:.3f} mm; corte = {cuts[0]["perpendicular_length"]:.3f} mm')
        for i,c in enumerate(cuts):
            text(x0+26,561+i*48,f'Ponta {i+1}: inclinada preservada {c["preserved_side_length"]:.3f} mm ({1-entry["fraction"]:.0%})',14)
            text(x0+26,581+i*48,f'Folga perpendicular {c["terminal_clearance"]:.3f} mm / exigida {case["margin"]:.3f} mm',14,color)
        val=entry['validation']
        text(x0+26,672,'Cobertura, contato, limites e margem: '+('OK' if val['ok'] else 'FALHA — ver relatório'),14,color)
    text(24,737,'Limites físicos das pontas: '+', '.join(f'{c["max_depth"]:.3f} mm ({c["max_depth"]/c["local_height"]:.2%} H)' for c in maxima))
    text(24,770,'O limite é auditado separadamente; não é aplicado automaticamente quando 40% falha. Laterais superiores mantidas.')
    text(24,803,'Envelope regional vigente, sem margem proximal global nova. Recorte contido no original; validação de sólidos no FreeCAD pendente.',14)
    return '\n'.join(out+['</g></svg>'])


def study(group, owner, node, config, saved):
    candidate,captured,outlines,_diagnostics=compute(config)
    data=captured[node]
    spec,parts,corridors,supports,old=data
    case=review.make_case(owner,config,candidate,dict(name=group,signature=dict(points=saved)),
        replace(old,attachment=outlines[node].attachment),(spec,corridors,supports))
    case['group']=group
    case['contact_points']=[]  # Only the selected tips may shorten chord contact.
    axes=[(math.cos(i*math.pi/180),math.sin(i*math.pi/180)) for i in range(360)]
    axes += [s.normal for s in supports]
    axes += [n for n,h in review.halfplanes(review.clean(case['raw']))]
    def demand(n):
        return max(max(review.dot(n,p) for p in case['raw']),max(review.dot(n,p) for p in case['tips'])+case['margin'])
    case['envelope']=review.polygon(case['hard']+[(n,demand(n)) for n in axes])
    studies=[]
    for fraction in (.25,.4,.55):
        result,cuts=f.truncate_sharp_fan(*data,depth_fraction=fraction)
        # Show the attempted contour even when production returns the fallback.
        points=old.points
        chord=next(s for s in supports if s.kind=='CHORD_BOUNDARY')
        for cut,(_idx,n,_angle) in zip(cuts,f._sharp_chord_ends(old.points,chord,spec.member_overlap)):
            support=f.GussetSupportLine('audit',f.perp(n),n,f.dot(n,cut.cut_point),'FREE_MARGIN')
            points=f._hull(f._clip_support(points,support))
        studies.append(dict(fraction=fraction,accepted=all(c.accepted for c in cuts),
            cuts=[asdict(c) for c in cuts],candidate=points,applied=result.points,
            validation=review.validation(case,points)))
    maxima=[]
    for c in cuts:
        # Every maximum is verified by the complete production validator too.
        _result,bound=f.truncate_sharp_fan(*data,depth_fraction=c.max_depth/c.local_height)
        audit=next(b for b in bound if b.original_tip==c.original_tip)
        maxima.append(asdict(audit))
        assert audit.accepted, audit
    alternative,_cuts=f.truncate_sharp_fan(*data,depth_fraction=min(
        c['max_depth']/c['local_height'] for c in maxima))
    case['maximum_candidate']=alternative.points
    assert review.validation(case,alternative.points)['ok']
    return case,studies,maxima


def main():
    fixture=json.loads((ROOT/'tests/fixtures/gusset_round1.json').read_text(encoding='utf8'))
    source=ROOT.parent/'testeC6.FCStd'
    digest=hashlib.sha256(source.read_bytes()).hexdigest()
    assert digest==fixture['source_sha256']
    output=ROOT/'Documentation/gusset_tip_depth'
    output.mkdir(exist_ok=True)
    inputs=[]
    for group in ('F04_03','F04_04'):
        c=next(c for c in fixture['cases'] if c['group']==group)
        inputs.append((group,c['owner'],c['node'],fixture['owners'][c['owner']],c['saved']))
    value,node=three_web_config()
    value['role_specs']['DIAGONAL']['profile_ref']=asdict(profile_catalog.ref_for_designation('HP 310 x 132,0'))
    value=configured(value,node)
    inputs.append(('HP_limite','Sintético HP 310 x 132,0',node,value,[]))
    records=[]
    page=['<!doctype html><html lang="pt-BR"><meta charset="utf-8"><title>Profundidade F04</title>',
          '<style>body{font:16px Arial;margin:24px;background:#f8fafc}img{width:100%}</style>',
          '<h1>Calibração local F04 — 25%, 40% e 55%</h1>',
          '<p>40% selecionado onde admissível. F04_05, F08 e demais famílias mantidas. Azul é recalculado, não a forma persistida no FCStd.</p>',
          '<p><a href="CRITERIO.md">Critério, medidas e roteiro manual</a> · <a href="coordenadas.json">Coordenadas e auditorias completas</a></p>']
    for args in inputs:
        case,studies,maxima=study(*args)
        group=args[0]
        (output/(group+'.svg')).write_text(render(case,studies,maxima),encoding='utf8')
        page.append(f'<h2>{group}</h2><a href="{group}.svg"><img src="{group}.svg" alt="{group}"></a>')
        records.append(dict(group=group,owner=args[1],node=args[2],persisted=args[4],
            original_recomputed=case['current'],studies=studies,physical_maxima=maxima,
            maximum_candidate=case['maximum_candidate']))
    (output/'index.html').write_text('\n'.join(page)+'</html>',encoding='utf8')
    (output/'coordenadas.json').write_text(json.dumps(records,ensure_ascii=False,indent=2),encoding='utf8')
    assert hashlib.sha256(source.read_bytes()).hexdigest()==digest
    print(json.dumps([dict(group=r['group'],accepted=[s['accepted'] for s in r['studies']],
        max_depth=[c['max_depth'] for c in r['physical_maxima']]) for r in records]))


if __name__=='__main__':
    main()
