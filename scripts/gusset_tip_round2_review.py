"""Render the five real three-web configurations from the offline fixture."""
from dataclasses import asdict, replace
import hashlib
import html
import json
import math
from pathlib import Path
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts import gusset_family_review as review
from freecad.SteelStructures.trusses import gussets as g
from freecad.SteelStructures.trusses.realization import build_candidate
from freecad.SteelStructures.connections.gusset_families import truncate_sharp_fan


def local_comparison(case, group, incorrect):
    """Three actual contours at one scale, with magnified triangle details."""
    new = case['proposals'][0]['points']
    cuts = case['cuts']
    geometry = case['current']+incorrect+new+case['envelope']
    lo = [min(p[i] for p in geometry)-20 for i in range(2)]
    hi = [max(p[i] for p in geometry)+20 for i in range(2)]
    scale = min(535/(hi[0]-lo[0]),355/(hi[1]-lo[1]))
    out = ['<svg xmlns="http://www.w3.org/2000/svg" width="1800" height="920" viewBox="0 0 1800 920">',
           '<rect width="100%" height="100%" fill="#f8fafc"/>',
           '<g font-family="Arial, sans-serif" fill="#172b42">',
           f'<text x="24" y="32" font-size="24" font-weight="bold">{group} — truncamento LOCAL da ponta</text>',
           f'<text x="24" y="60" font-size="16">{case["owner"]} / {case["node"]} · dados físicos do FCStd, pipeline Python recalculado</text>']
    for i,(color,label) in enumerate((('#2563eb','Original inclinado'),('#be123c','Resultado anterior incorreto'),
            ('#15803d','Truncamento local'),('#f59e0b','Envelope obrigatório'),('#a21caf','Trecho perpendicular'))):
        x=24+i*350
        out.append(f'<path d="M{x} 86h24" stroke="{color}" stroke-width="3"/><text x="{x+31}" y="91" font-size="14">{label}</text>')
    def polygon(points, transform, color, fill='none', opacity=1., width=2., dash=''):
        value=' '.join(f'{x:.3f},{y:.3f}' for x,y in map(transform,points))
        out.append(f'<polygon points="{value}" fill="{fill}" fill-opacity="{opacity}" stroke="{color}" stroke-width="{width}" stroke-dasharray="{dash}"/>')
    def segment(a,b,transform,color,width=3.,dash=''):
        a,b=transform(a),transform(b)
        out.append(f'<path d="M{a[0]:.3f},{a[1]:.3f}L{b[0]:.3f},{b[1]:.3f}" stroke="{color}" stroke-width="{width}" stroke-dasharray="{dash}"/>')
    panels = [('Original — laterais inclinadas',case['current'],'#2563eb'),
              ('Anterior incorreto — lateral integral substituída',incorrect,'#be123c'),
              ('Corrigido — só o triângulo da ponta é removido',new,'#15803d')]
    for col,(title,points,color) in enumerate(panels):
        x0=col*600
        out.append(f'<rect x="{x0+12}" y="112" width="576" height="485" rx="8" fill="white" stroke="#cbd5e1"/>')
        out.append(f'<text x="{x0+26}" y="140" font-size="17" font-weight="bold">{title}</text>')
        def tr(p): return (x0+300+(p[0]-(lo[0]+hi[0])/2)*scale,355-(p[1]-(lo[1]+hi[1])/2)*scale)
        for corridor in case['corridors']:
            polygon(review.corners(corridor,case['overlap']+20),tr,'#94a3b8','#cbd5e1',.22,.8)
        polygon(case['envelope'],tr,'#d97706','#fbbf24',.32,1.)
        if col:
            polygon(case['current'],tr,'#2563eb',width=1.5,dash='5 4')
        polygon(points,tr,color,width=3.)
        for n,h in case['hard']:
            endpoints=[p for p in points if abs(review.dot(n,p)-h)<1e-5]
            if len(endpoints)>=2:
                segment(endpoints[0],endpoints[-1],tr,'#172b42')
        if col==2:
            for i,cut in enumerate(cuts):
                polygon([cut['original_tip'],cut['cut_point'],cut['contact_point']],tr,'#a21caf','#f5d0fe',.6,1.)
                segment(cut['cut_point'],cut['contact_point'],tr,'#a21caf',4.)
                x,y=tr(cut['cut_point'])
                out.append(f'<circle cx="{x}" cy="{y}" r="3" fill="#a21caf"/><text x="{x+6}" y="{y-8}" font-size="14">{i+1}</text>')
        out.append(f'<text x="{x0+26}" y="557" font-size="14">{len(points)} faces · área {review.polygon_area(points):.2f} mm²</text>')
        message = 'Forma substituída indevidamente; exibida apenas para comparação.' if col==1 else 'Cobertura, margem terminal e contato físico: OK na auditoria 2D.'
        out.append(f'<text x="{x0+26}" y="580" font-size="12" fill="{color}">{message}</text>')
    out.append('<text x="24" y="635" font-size="19" font-weight="bold">Dimensões recalculadas — preservação da lateral</text>')
    for i,cut in enumerate(cuts):
        kept=cut['preserved_side_length']; original=cut['original_side_length']; height=cut['perpendicular_length']
        lines=[f'Ponta {i+1}: perpendicular {height:.3f} mm / lateral preservada {kept:.3f} mm = {100*height/kept:.2f}%.',
               f'Lateral original {original:.3f} mm; mantidos {100*kept/original:.2f}% do seu comprimento.']
        for j,line in enumerate(lines):
            out.append(f'<text x="24" y="{667+i*72+j*25}" font-size="16">{line}</text>')
        zx=1060+i*360
        out.append(f'<rect x="{zx}" y="625" width="345" height="250" fill="white" stroke="#cbd5e1"/>')
        out.append(f'<text x="{zx+12}" y="649" font-size="15" font-weight="bold">Ampliação da ponta {i+1} · h = {height:.3f} mm</text>')
        tip,cutp,foot=cut['original_tip'],cut['cut_point'],cut['contact_point']
        extend=tuple(cutp[k]+.6*(cutp[k]-tip[k]) for k in range(2))
        detail=[tip,cutp,foot,extend]
        bounds=[[min(p[k] for p in detail),max(p[k] for p in detail)] for k in range(2)]
        zoom=min(265/max(bounds[0][1]-bounds[0][0],1e-6),175/max(bounds[1][1]-bounds[1][0],1e-6))
        def tr(p): return (zx+172+(p[0]-sum(bounds[0])/2)*zoom,762-(p[1]-sum(bounds[1])/2)*zoom)
        polygon([tip,cutp,foot],tr,'#a21caf','#f5d0fe',.65,1.)
        segment(tip,extend,tr,'#2563eb',2.,'4 4')
        segment(foot,tip,tr,'#172b42',2.)
        segment(foot,cutp,tr,'#a21caf',4.)
        segment(cutp,extend,tr,'#15803d',4.)
    out.append('<text x="24" y="856" font-size="14">A chapa corrigida está inteiramente dentro do contorno original. Apenas pequenos triângulos são removidos.</text>')
    out.append('<text x="24" y="896" font-size="14">Envelope amarelo: corredores + margem nos extremos, recortado pelos limites físicos. Sem nova margem proximal global. Validação manual no FreeCAD pendente.</text>')
    return '\n'.join(out+['</g></svg>'])


def main():
    fixture = json.loads((ROOT/'tests/fixtures/gusset_round1.json').read_text(encoding='utf8'))
    source = ROOT.parent/'testeC6.FCStd'
    source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    assert source_hash == fixture['source_sha256']
    incorrect = json.loads((ROOT/'tests/fixtures/gusset_tip_previous_incorrect.json').read_text(encoding='utf8'))
    cases = [c for c in fixture['cases'] if c['group'].startswith('F04')]
    output = ROOT/'Documentation/gusset_tip_round2'
    output.mkdir(exist_ok=True)
    groups = {}
    for owner, config in fixture['owners'].items():
        if not any(c['owner']==owner for c in cases):
            continue
        candidate = build_candidate(config)
        captured = {}
        original = g.build_gusset_outline
        def capture(spec, corridors, supports):
            old = original(spec,corridors,supports)
            captured[spec.node_key] = (spec,corridors,supports,old)
            return old
        with patch.object(g,'build_gusset_outline',capture):
            outlines, diagnostics = g.preliminary_gusset_outlines(candidate)
        if diagnostics:
            raise AssertionError((owner,diagnostics))
        by_node = {o.spec.node_key:o for o in outlines}
        for saved in cases:
            if saved['owner'] != owner:
                continue
            node = saved['node']
            spec,corridors,supports,old = captured[node]
            new = by_node[node]
            group = saved['group']
            case = review.make_case(owner,config,candidate,
                dict(name=group, signature=dict(points=saved['saved'])),
                replace(old,attachment=new.attachment),(spec,corridors,supports))
            case['group'] = group
            _result, cuts = truncate_sharp_fan(spec,case['participants'],corridors,supports,old)
            case['cuts'] = [asdict(c) for c in cuts]
            # Mandatory physical coverage, independent of a chosen contour's
            # contact length. Show the actual contact separately in black.
            contacts = [p for e in new.semantic_edges if e.kind=='CHORD_BOUNDARY'
                        for p in (e.start,e.end)]
            def demand(n):
                return max(max(review.dot(n,p) for p in case['raw']),
                           max(review.dot(n,p) for p in case['tips'])+case['margin'])
            axes = [(math.cos(i*math.pi/180),math.sin(i*math.pi/180)) for i in range(360)]
            axes += [s.normal for s in supports]+[n for n,h in review.halfplanes(review.clean(case['raw']))]
            case['envelope'] = review.polygon(case['hard']+[(n,demand(n)) for n in axes])
            case['contact_points'] = contacts
            case['proposals'] = [dict(name='Após correção — '+(
                'truncamento local' if group in ('F04_03','F04_04') else 'mantida'),
                points=list(new.points),validation=review.validation(case,list(new.points)),
                retained=group not in ('F04_03','F04_04'))]
            groups.setdefault(group,[]).append(case)
    if len(groups)!=5 or sum(map(len,groups.values()))!=9:
        raise AssertionError('Inventário F04 incompleto')
    review.FAMILIES['F04'] = 'Duas diagonais + montante / fechamento condicional'
    page = ['<!doctype html><html lang="pt-BR"><meta charset="utf-8">',
            '<title>Gussets — refinamento condicional</title>',
            '<style>body{font:16px Arial;background:#f1f5f9;color:#172b42;margin:24px}img{width:100%}article{margin:24px 0}</style>',
            '<h1>Gussets — truncamento local corrigido</h1>',
            '<p>F04_03/F04_04: original inclinado (azul), resultado anterior incorreto (vermelho) e truncamento local recalculado (verde). Magenta: trecho perpendicular curto e triângulo removido. As ampliações e medidas mostram a lateral preservada.</p>',
            '<p>F04_01/02/05 são mantidas. F08_01 permanece com sua geometria atual; variante K não implementada.</p>',
            '<p><a href="CRITERIO.md">Critério, medições e validação</a></p>']
    records = []
    for group, occurrences in sorted(groups.items()):
        case = occurrences[0]
        svg = review.svg(case,group,occurrences)
        svg = (svg.replace('Atual C6-P','Rodada 1 recalculada')
                  .replace('Atual / comparação com persistido','Rodada 1 / persistido FCStd')
                  .replace('Proposta</text>','Recalculado atual</text>')
                  .replace('Margem proximal global NÃO adicionada. Regiões de margem lateral exigem aprovação do contrato. Ver relatório; não é validação de sólidos.',
                           'Somente os cortes selecionados encurtam o contato. Triagem 2D; sólidos pendentes no FreeCAD.'))
        if group in incorrect:
            svg = local_comparison(case,group,incorrect[group])
        (output/(group+'.svg')).write_text(svg,encoding='utf8')
        page.append(f'<article><h2><a href="{group}.svg">{group}</a></h2><img src="{group}.svg" alt="{html.escape(group)}"></article>')
        records.append(dict(group=group,occurrences=[c['owner']+'/'+c['node'] for c in occurrences],
            before=case['current'],after=case['proposals'][0]['points'],
            previous_incorrect=incorrect.get(group),cuts=case['cuts'],
            validation=case['proposals'][0]['validation']))
    (output/'index.html').write_text('\n'.join(page)+'</html>',encoding='utf8')
    (output/'coordenadas.json').write_text(json.dumps(records,ensure_ascii=False,indent=2),encoding='utf8')
    assert hashlib.sha256(source.read_bytes()).hexdigest() == source_hash
    print(json.dumps(dict(groups=len(groups),plates=sum(map(len,groups.values())),
        changed=[r['group'] for r in records if not review.same_polygon(r['before'],r['after'])],
        conflicts=[r['group'] for r in records if not r['validation']['ok']],
        refused=[(r['group'],c['reason']) for r in records for c in r['cuts'] if not c['accepted']]),ensure_ascii=True))


if __name__=='__main__':
    main()
