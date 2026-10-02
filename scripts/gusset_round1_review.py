"""Reproduce round-one comparison/fixtures from read-only XML, never FreeCAD."""
from dataclasses import asdict, replace
import hashlib
import html
import json
from pathlib import Path
import sys
from unittest.mock import patch
import xml.etree.ElementTree as ET
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import gusset_family_review as review
from freecad.SteelStructures.trusses import gussets as g
from freecad.SteelStructures.trusses.realization import build_candidate


def selected(case):
    if case['family'] in ('F02', 'F03', 'F07'):
        return next((p for p in case['proposals'] if p['name'].startswith('L ')), None)
    if case['family'] == 'F05':
        return next(p for p in case['proposals'] if p['name'].startswith('C '))
    return None


def drawing(case, gid, occurrences, study=False):
    result = review.svg(case, gid, occurrences)
    return (result.replace('Atual C6-P', 'Anterior recalculado')
            .replace('Sem violação na triagem 2D', 'Cobertura, contato, margem, limites e vizinhos: OK 2D')
            .replace('Atual / comparação com persistido', 'Anterior C6-P / persistido FCStd')
            .replace('Proposta</text>', ('Estudo NÃO implementado' if study else 'Novo / mantido')+'</text>')
            .replace('Margem proximal global NÃO adicionada. Regiões de margem lateral exigem aprovação do contrato. Ver relatório; não é validação de sólidos.',
                     'Sem margem proximal global. Margem terminal e laterais aplicáveis preservadas. Triagem 2D não valida sólidos ou fitting.'))


def main(source):
    original_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    baseline = json.loads((ROOT/'Documentation/gusset_family_review/inventario.json').read_text(encoding='utf8'))
    assert original_hash == baseline['source_sha256']
    with zipfile.ZipFile(source, 'r') as archive:
        xml = ET.fromstring(archive.read('Document.xml'))
    owners = {}
    for obj in xml.findall('./ObjectData/Object'):
        props = {p.get('name'): p[0].get('value') for p in obj.findall('./Properties/Property') if len(p)}
        if 'AppliedState' in props:
            owners[obj.get('name')] = json.loads(props['AppliedState'])['candidate']['config']
    cases, fixture, results = [], [], []
    for owner, config in owners.items():
        candidate = build_candidate(config)
        captured = {}
        original = g.build_gusset_outline
        def capture(spec, corridors, supports):
            old = original(spec, corridors, supports)
            captured[spec.node_key] = (spec, corridors, supports, old)
            return old
        with patch.object(g, 'build_gusset_outline', capture):
            outlines, diagnostics = g.preliminary_gusset_outlines(candidate)
        outlines = {o.spec.node_key: o for o in outlines}
        for saved in baseline['cases']:
            if saved['owner'] != owner:
                continue
            node = saved['node']
            new = outlines[node]
            spec, corridors, supports, old = captured[node]
            old = replace(old, attachment=new.attachment)
            assert review.same_polygon(old.points, saved['current']), (owner, node, 'baseline changed')
            assert json.loads(json.dumps(asdict(new.attachment))) == saved['attachment'], (owner, node, 'attachment changed')
            case = review.make_case(owner, config, candidate,
                dict(name=saved['plate'], signature=dict(points=saved['saved'])), old,
                (spec, corridors, supports))
            case['group'] = saved['group']
            preference = selected(saved)
            expected = preference['points'] if preference else saved['current']
            issues = [asdict(d) for d in diagnostics if d.node_key == node]
            status = review.validation(case, list(new.points))
            variant = preference['name'].split(' ')[0] if preference else 'Mantida'
            matches = review.same_polygon(new.points, expected)
            case['proposals'] = [dict(name=variant+' — código atualizado', points=list(new.points),
                                     validation=status, retained=not preference)]
            cases.append(case)
            record = dict(owner=owner, node=node, plate=saved['plate'], group=saved['group'],
                          variant=variant, before=saved['current'], saved=saved['saved'],
                          expected=expected, after=new.points, matches_approval=matches,
                          validation=status, diagnostics=issues)
            results.append(record)
            fixture.append({k: record[k] for k in ('owner','node','group','variant','before','saved','expected')})
    assert len(cases) == 41
    out = ROOT/'Documentation/gusset_round1'
    out.mkdir(exist_ok=True)
    groups = {}
    for c in cases:
        groups.setdefault(c['group'], []).append(c)
    assert len(groups) == 30
    page = ['<!doctype html><html lang="pt-BR"><meta charset="utf-8"><title>Gussets — rodada 1</title>',
            '<style>body{font:16px Arial;background:#f1f5f9;color:#172b42;margin:24px}img{width:100%;background:white}article{margin:24px 0}a{color:#185abc}</style>',
            '<h1>Rodada 1 — 41 chapas / 30 configurações</h1>',
            '<p>Azul: anterior recalculado C6-P. Cinza: persistido no FCStd. Verde: resultado do código atualizado. Amarelo: cobertura e margem terminal. Não houve execução do FreeCAD.</p>',
            '<p><a href="RELATORIO.md">Regras, validação e limites</a> · <a href="resultados.json">Coordenadas e medições</a> · <a href="estudos/index.html">Três estudos da rodada 2 (NÃO implementados)</a></p>']
    for gid, occurrences in sorted(groups.items()):
        (out/(gid+'.svg')).write_text(drawing(occurrences[0], gid, occurrences), encoding='utf8')
        page.append(f'<article><h2><a href="{gid}.svg">{gid}</a></h2><img src="{gid}.svg" alt="{gid}" loading="lazy"></article>')
    (out/'index.html').write_text('\n'.join(page)+ '</html>', encoding='utf8')
    studies = out/'estudos'
    studies.mkdir(exist_ok=True)
    study_page = ['<!doctype html><html lang="pt-BR"><meta charset="utf-8"><title>Rodada 2 — estudos</title>',
                  '<h1>Estudos apenas — não implementados</h1><p>Os contatos existentes são conservados; fechamentos perpendiculares podem aumentar a área.</p>']
    for gid in ('F04_03', 'F04_04', 'F08_01'):
        case = dict(groups[gid][0])
        if gid == 'F08_01':
            baseline_case = next(c for c in baseline['cases'] if c['group'] == gid)
            proposal = next(p for p in baseline_case['proposals'] if p['name'].startswith('K '))
            points = proposal['points']
            name = 'K — banda passante e caps terminais'
        else:
            n = case['chord'][0][0]
            tangent = review.perp(n)
            if tangent[0] < 0:
                tangent = review.neg(tangent)
            lines = review.halfplanes(case['current'])
            # Keep top closure and untouched left closure; replace the exposed
            # side(s) by normals tangent to the real bottom chord.
            kept = [(a,h) for a,h in lines if abs(review.dot(a,tangent)) < .1
                    or (gid == 'F04_03' and review.dot(a,tangent) < 0)]
            normals = [tangent] if gid == 'F04_03' else [tangent, review.neg(tangent)]
            points = review.clean(review.polygon(case['hard']+kept+[(a,case['demand'](a)) for a in normals]))
            name = 'Estudo — fechamento direito perpendicular' if gid == 'F04_03' else 'Estudo — dois fechamentos perpendiculares'
        case['proposals'] = [dict(name=name, points=points, validation=review.validation(case,points), retained=False)]
        if gid != 'F08_01':
            # A second, explicitly conditional study does not assume the full
            # old contact length is mandatory. It keeps real chord contact,
            # bare coverage and terminal margin, but visibly reports the
            # shortened legacy interval instead of silently approving it.
            def physical_demand(a):
                return max(max(review.dot(a,p) for p in case['raw']),
                           max(review.dot(a,p) for p in case['tips'])+case['margin'])
            compact = review.clean(review.polygon(case['hard']+kept+
                                   [(a,physical_demand(a)) for a in normals]))
            audit = review.validation(case,compact)
            audit['issues'] = [s.replace('Contato atual encurtado',
                'Contato legado encurtado: requer aprovação do intervalo') for s in audit['issues']]
            case['proposals'].append(dict(name='Alternativa — menor intervalo de contato (decidir)',
                points=compact,validation=audit,retained=False))
        (studies/(gid+'.svg')).write_text(drawing(case,gid,groups[gid],study=True),encoding='utf8')
        (studies/(gid+'.json')).write_text(json.dumps(case['proposals'],ensure_ascii=False,indent=2),encoding='utf8')
        study_page.append(f'<h2><a href="{gid}.svg">{gid}</a></h2><img style="width:100%" src="{gid}.svg" alt="{html.escape(name)}">')
    (studies/'index.html').write_text('\n'.join(study_page)+'</html>',encoding='utf8')
    (out/'resultados.json').write_text(json.dumps(dict(source_sha256=original_hash,cases=results),ensure_ascii=False,indent=2),encoding='utf8')
    fixture_path = ROOT/'tests/fixtures/gusset_round1.json'
    fixture_path.parent.mkdir(exist_ok=True)
    fixture_path.write_text(json.dumps(dict(source_sha256=original_hash,owners=owners,cases=fixture),ensure_ascii=False,indent=2),encoding='utf8')
    assert hashlib.sha256(source.read_bytes()).hexdigest() == original_hash
    print(json.dumps(dict(plates=len(cases),groups=len(groups),
        changed=sum(not review.same_polygon(r['before'],r['after']) for r in results),
        mismatches=[r['group'] for r in results if not r['matches_approval']],
        invalid=[r['group'] for r in results if not r['validation']['ok']],
        diagnostics=[(r['group'],r['diagnostics']) for r in results if r['diagnostics']]),ensure_ascii=True))


if __name__ == '__main__':
    main(Path(sys.argv[1]))
