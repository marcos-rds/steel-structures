"""Offline Phase 1 drawings only; no production geometry or FCStd writes.

Uses the standard library and the current pure pipeline. Output is a review
artifact, not an implementation of the future production contour families.
"""
import hashlib
from dataclasses import replace
from copy import deepcopy
import html
import json
import math
from pathlib import Path
import sys
from unittest.mock import patch
import xml.etree.ElementTree as ET
import zipfile
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from freecad.SteelStructures.trusses import gussets as pipeline
from freecad.SteelStructures.trusses.connections import connection_participants
from freecad.SteelStructures.trusses.realization import build_candidate, reference_frame
from freecad.SteelStructures.connections.gusset import _hull, polygon_area


def dot(a, b):
    return sum(x*y for x, y in zip(a, b))


def neg(a):
    return (-a[0], -a[1])


def clip(poly, normal, offset):
    result = []
    for a, b in zip(poly, poly[1:]+poly[:1]):
        da, db = dot(normal, a)-offset, dot(normal, b)-offset
        if da <= 1e-9:
            result.append(a)
        if (da < -1e-9 and db > 1e-9) or (da > 1e-9 and db < -1e-9):
            f = da/(da-db)
            result.append(tuple(a[i]+f*(b[i]-a[i]) for i in range(2)))
    return result


def polygon(lines):
    # Starting box is computational only, not a manufacturing dimension.
    size = 100*max(1., *(abs(h) for n, h in lines))
    result = [(-size, -size), (size, -size), (size, size), (-size, size)]
    for n, h in lines:
        result = clip(result, n, h)
    return result


def corners(corridor, length):
    d = corridor.direction
    p = (-d[1], d[0])
    return [tuple(s*d[i]+t*p[i] for i in range(2))
            for s, t in ((0., corridor.transverse_low), (length, corridor.transverse_low),
                         (length, corridor.transverse_high), (0., corridor.transverse_high))]


def halfplanes(poly):
    result = []
    for a, b in zip(poly, poly[1:]+poly[:1]):
        dx, dy = b[0]-a[0], b[1]-a[1]
        size = math.hypot(dx, dy)
        n = (dy/size, -dx/size)
        result.append((n, dot(n, a)))
    return result


def analyze(owner, node, config, persisted):
    candidate = build_candidate(config)
    collected = {}
    original = pipeline.build_gusset_outline
    def capture(spec, corridors, supports):
        if spec.node_key == node:
            collected.update(spec=spec, corridors=corridors, supports=supports)
        return original(spec, corridors, supports)
    with patch.object(pipeline, "build_gusset_outline", capture):
        outlines, diagnostics = pipeline.preliminary_gusset_outlines(candidate)
    assert not diagnostics, diagnostics
    outline = next(o for o in outlines if o.spec.node_key == node)
    roles = {p.participant_key: p.role for p in connection_participants(candidate, node)}
    webs = [c for c in collected["corridors"] if roles[c.participant_key] not in pipeline.CHORD_ROLES]
    raw = [p for c in webs for p in corners(c, outline.spec.member_overlap)]
    tips = [p for c in webs for p in corners(c, outline.spec.member_overlap)[1:3]]
    hard = [(s.normal, s.offset) for s in collected["supports"] if s.kind == "CHORD_BOUNDARY"]
    margin = outline.spec.edge_margin
    # Exact support of conv(web rectangles) Minkowski-summed with a margin disk.
    def support(n):
        return max(dot(n, p) for p in raw)+margin
    # Display approximation circumscribes the exact rounded envelope (not inscribed).
    normals = [(math.cos(i*math.pi/180), math.sin(i*math.pi/180)) for i in range(360)]
    normals += [s.normal for s in collected["supports"]]
    normals += [n for n, h in halfplanes(list(_hull(raw)))]
    normals += [(-n[1], n[0]) for n, h in hard]+[(n[1], -n[0]) for n, h in hard]
    normals += [neg(n) for n, h in hard]
    envelope = polygon(hard+[(n, support(n)) for n in normals])
    participating = {k for p in connection_participants(candidate, node) for k in p.physical_run_keys}
    foreign_members = []
    node_position = candidate.graph.node(node).position_local
    for run in candidate.runs:
        if run.key in participating:
            continue
        start = candidate.graph.node(run.start_node_key).position_local
        end = candidate.graph.node(run.end_node_key).position_local
        descriptor = SimpleNamespace(node_key=run.start_node_key, participant_key=run.key)
        for corridor in pipeline._corridors(candidate, descriptor, run, reference_frame(config)):
            footprint = [tuple(p[i]+start[i]-node_position[i] for i in range(2))
                         for p in corners(corridor, math.dist(start, end))]
            foreign_members.append((run.key, footprint))
    return dict(owner=owner, node=node, outline=outline, collected=collected,
                roles=roles, raw=raw, tips=tips, hard=hard, support=support,
                envelope=envelope, persisted=persisted, alternatives=[], foreign_members=foreign_members)


def alternative(case, name, lines):
    points = polygon(lines)
    # Exact analytic disk support against every free edge; no sampled clearance claim.
    clearances = []
    for n, h in halfplanes(points):
        is_contact = any(math.dist(n, hn) < 1e-7 and abs(h-hh) < 1e-6
                         for hn, hh in case["hard"])
        if not is_contact:
            gap = h-max(dot(n, p) for p in case["raw"])
            assert gap >= case["outline"].spec.edge_margin-1e-7, (name, gap)
            clearances.append(gap)
    for p in case["envelope"]:
        # Drawing envelope is an outer approximation; allow its 0.001 mm error.
        assert all(dot(n, p) <= h+.002 for n, h in halfplanes(points))
    for n, h in case["hard"]:
        assert all(dot(n, p) <= h+1e-7 for p in points)
        assert sum(abs(dot(n, p)-h) < 1e-6 for p in points) >= 2
    # Preserve the entire existing chord-contact segments, not just their lines.
    for e in case["outline"].semantic_edges:
        if e.kind == "CHORD_BOUNDARY":
            assert all(all(dot(n, p) <= h+1e-7 for n, h in halfplanes(points))
                       for p in (e.start, e.end)), (name, "contact shortened")
    entry = dict(name=name, points=points, lines=lines, area=polygon_area(points),
                 minimum_free_margin=min(clearances), vertices=len(points))
    intersections = []
    for key, member_poly in case["foreign_members"]:
        intersection = list(member_poly)
        for n, h in halfplanes(points):
            intersection = clip(intersection, n, h)
        if len(intersection) >= 3 and polygon_area(intersection) > 1e-6:
            intersections.append(key)
    entry["nonparticipant_nominal_projection_intersections"] = sorted(set(intersections))
    case["alternatives"].append(entry)
    return entry


def build_families(case, label):
    s, hard = case["support"], case["hard"]
    if label == "A":
        left, right, up = (-1., 0.), (1., 0.), (0., 1.)
        diag = next(c.direction for c in case["collected"]["corridors"]
                    if case["roles"][c.participant_key] == "DIAGONAL")
        alternative(case, "A1 • pentágono / lateral limitada", hard+[
            (left, s(left)), (right, s(right)), (up, s(up)), (diag, s(diag))])
        alternative(case, "A2 • quatro lados / retângulo", hard+[
            (left, s(left)), (right, s(right)), (up, s(up))])
    elif label == "B":
        inward = neg(hard[0][0])
        tangent = (-inward[1], inward[0])
        base = hard+[(tangent, s(tangent)), (neg(tangent), s(neg(tangent))),
                     (inward, s(inward))]
        alternative(case, "B1 • quatro lados / referencial do banzo", base)
        vertical = next(c.direction for c in case["collected"]["corridors"]
                        if case["roles"][c.participant_key] == "VERTICAL")
        alternative(case, "B2 • pentágono / laterais do montante", hard+[
            ((-1., 0.), s((-1., 0.))), ((1., 0.), s((1., 0.))),
            (inward, s(inward)), (vertical, s(vertical))])
        case["tangent"], case["inward"] = tangent, inward
    else:
        alternative(case, "C1 • pentágono / base reta", hard+[
            ((-1., 0.), s((-1., 0.))), ((1., 0.), s((1., 0.))),
            ((0., -1.), s((0., -1.)))])


def svg(case, label):
    panels = [("Persistido × recomputado", None)] + [(a["name"], a) for a in case["alternatives"]]
    if label == "B":
        panels.append(("B2 espelhado • dados físicos refletidos", case["alternatives"][-1]))
    if label == "A":
        panels.append(("Limite físico • reduzir mais perde margem", case["alternatives"][0]))
    cols = 2
    rows = math.ceil(len(panels)/cols)
    width, height = 1400, 180+rows*530+150
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
           '<rect width="100%" height="100%" fill="#f8fafc"/>',
           '<style>text{font-family:Arial,sans-serif;fill:#172b42}.small{font-size:15px}.title{font-size:26px;font-weight:bold}</style>',
           f'<text x="35" y="42" class="title">{label} · {case["owner"]} / {case["node"]}</text>',
           '<text x="35" y="72" font-size="18">FASE 1 — estudo vetorial para aprovação · coordenadas locais em mm</text>']
    legends = [("#94a3b8", "Persistido FCStd", "5 5"), ("#2563eb", "Atual C6-P", ""),
               ("#15803d", "Proposta / borda alterada", ""), ("#f59e0b", "Envelope obrigatório¹", ""),
               ("#dc2626", "Cantos de sobreposição", "")]
    for i, (color, text, dash) in enumerate(legends):
        x = 35+i*265
        out.append(f'<path d="M{x} 107h30" stroke="{color}" stroke-width="4" stroke-dasharray="{dash}"/>'
                   f'<text x="{x+37}" y="112" class="small">{text}</text>')
    combined = list(case["outline"].points)+list(case["persisted"])+case["envelope"]
    combined += [p for a in case["alternatives"] for p in a["points"]]
    xmin, xmax = min(p[0] for p in combined)-55, max(p[0] for p in combined)+55
    ymin, ymax = min(p[1] for p in combined)-55, max(p[1] for p in combined)+55
    scale = min(600/(xmax-xmin), 365/(ymax-ymin))
    for index, (title, proposal) in enumerate(panels):
        x0, y0 = 30+(index%2)*690, 140+(index//2)*530
        mirror = label == "B" and index == 3
        def point(p):
            x = -p[0] if mirror else p[0]
            midx = -(xmin+xmax)/2 if mirror else (xmin+xmax)/2
            return (x0+335+(x-midx)*scale, y0+260-(p[1]-(ymin+ymax)/2)*scale)
        def path(points, color, fill="none", stroke=2, dash="", opacity=1):
            pts = " ".join(f"{x:.3f},{y:.3f}" for x, y in map(point, points))
            out.append(f'<polygon points="{pts}" fill="{fill}" fill-opacity="{opacity}" stroke="{color}" stroke-width="{stroke}" stroke-dasharray="{dash}"/>')
        out.extend([f'<rect x="{x0}" y="{y0}" width="660" height="510" rx="8" fill="white" stroke="#d8e1eb"/>',
                    f'<text x="{x0+18}" y="{y0+32}" font-size="19" font-weight="bold">{html.escape(title)}</text>'])
        # Member projections: real corridor section, display length explicitly limited.
        for c in case["collected"]["corridors"]:
            pts = corners(c, case["outline"].spec.member_overlap+35.)
            path(pts, "#94a3b8", "#cbd5e1", 1, opacity=.35)
        path(case["envelope"], "#d97706", "#fbbf24", 1, opacity=.32)
        path(case["persisted"], "#94a3b8", dash="5 5")
        path(list(case["outline"].points), "#2563eb", stroke=2.5)
        if proposal:
            path(proposal["points"], "#15803d", stroke=3.3)
            for i, p in enumerate(proposal["points"]):
                x, y = point(p)
                out.append(f'<circle cx="{x:.3f}" cy="{y:.3f}" r="3.5" fill="#15803d"/>'
                           f'<text x="{x+7:.3f}" y="{y-7:.3f}" font-size="13">P{i+1}</text>')
        for p in case["tips"]:
            x, y = point(p)
            out.append(f'<circle cx="{x:.3f}" cy="{y:.3f}" r="4" fill="#dc2626"/>')
        if label == "A" and index == 3:
            limit = min(p[0] for p in case["tips"])
            a, b = point((limit, -11.59)), point((limit, 175.))
            out.append(f'<path d="M{a[0]},{a[1]}L{b[0]},{b[1]}" stroke="#dc2626" stroke-width="2" stroke-dasharray="7 4"/>')
        # Physical chord contact edges retained in bold dark ink.
        for e in case["outline"].semantic_edges:
            if e.kind == "CHORD_BOUNDARY":
                a, b = point(e.start), point(e.end)
                out.append(f'<path d="M{a[0]:.3f},{a[1]:.3f}L{b[0]:.3f},{b[1]:.3f}" stroke="#172b42" stroke-width="4"/>')
        x, y = point((0., 0.))
        out.append(f'<path d="M{x-5:.3f},{y:.3f}h10 M{x:.3f},{y-5:.3f}v10" stroke="#172b42"/>'
                   f'<text x="{x+8:.3f}" y="{y+16:.3f}" font-size="12">Nó</text>')
        member_names = {"TOP_CHORD": "Banzo superior", "BOTTOM_CHORD": "Banzo inferior",
                        "DIAGONAL": "Diagonal", "VERTICAL": "Montante"}
        out.append(f'<text x="{x0+18}" y="{y0+57}" class="small">'+
                   " + ".join(member_names[r] for r in sorted(set(case["roles"].values())))+'</text>')
        detail = (f'{proposal["vertices"]} lados · margem livre mínima {proposal["minimum_free_margin"]:.2f} mm'
                  if proposal else f'Persistido: {len(case["persisted"])} lados · recomputado: {len(case["outline"].points)} lados')
        if label == "A" and index == 3:
            detail = 'Vermelho: x = −104,862 → margem zero. Limite viável: x = −129,862.'
        out.append(f'<text x="{x0+18}" y="{y0+465}" class="small">{detail}</text>')
        out.append(f'<text x="{x0+18}" y="{y0+490}" class="small">Contato existente preservado: segmento preto. Verde: nova família.</text>')
    footer = 155+rows*530
    for i, text in enumerate([
        '¹ Envelope dos participantes da alma + margem de 25 mm, recortado apenas no contato físico dos banzos.',
        'Sobreposição = 150 mm · espessura = 10 mm · posições transversais e bandas C6-L inalteradas.',
        'Projeções dos membros truncadas para leitura. Ver coordenadas e limites físicos no relatório.',
        'Estudo 2D; os afastamentos transversais já persistidos não são corrigidos por estas propostas.']):
        out.append(f'<text x="35" y="{footer+i*25}" class="small">{text}</text>')
    out.append('</svg>')
    return "\n".join(out)


def main(source, output):
    before = hashlib.sha256(source.read_bytes()).hexdigest()
    with zipfile.ZipFile(source, "r") as archive:
        root = ET.fromstring(archive.read("Document.xml"))
    configs, saved = {}, {}
    for obj in root.findall("./ObjectData/Object"):
        props = {p.get("name"): p[0].get("value") for p in obj.findall("./Properties/Property") if len(p)}
        if "AppliedState" in props:
            configs[obj.get("name")] = json.loads(props["AppliedState"])["candidate"]["config"]
        if "SourceSignature" in props and "ParentTruss" in props:
            saved[(props["ParentTruss"], props["NodeKey"])] = json.loads(props["SourceSignature"])["points"]
    output.mkdir(parents=True, exist_ok=True)
    results = {}
    for label, owner, node in [("A", "StructuralTruss002", "B_S_MAIN_1_6"),
                               ("B", "StructuralTruss005", "T_S_LEFT_1_3"),
                               ("C", "StructuralTruss005", "T_S_APEX")]:
        case = analyze(owner, node, configs[owner], saved[(owner, node)])
        build_families(case, label)
        (output/f"{label}_propostas.svg").write_text(svg(case, label), encoding="utf-8")
        results[label] = dict(owner=owner, node=node, persisted=case["persisted"],
            current=case["outline"].points, required_corners=case["raw"],
            current_area=case["outline"].area,
            hard_contact_lines=case["hard"], alternatives=case["alternatives"],
            attachment_residuals=[str(r) for r in case["outline"].attachment.residuals])
        if label == "B":
            # Rebuild supports from reflected physical rectangles independently.
            reflect = lambda p: (-p[0], p[1])
            mirrored = dict(case)
            mirrored["raw"] = [reflect(p) for p in case["raw"]]
            mirrored["hard"] = [(reflect(n), h) for n, h in case["hard"]]
            mirrored["envelope"] = [reflect(p) for p in reversed(case["envelope"])]
            mirrored["foreign_members"] = [(key, [reflect(p) for p in reversed(poly)])
                                           for key, poly in case["foreign_members"]]
            mirrored["support"] = lambda n: max(dot(n, p) for p in mirrored["raw"])+case["outline"].spec.edge_margin
            mirrored["collected"] = dict(case["collected"], corridors=[
                replace(c, direction=reflect(c.direction), transverse_low=-c.transverse_high,
                        transverse_high=-c.transverse_low) for c in case["collected"]["corridors"]])
            mirrored["outline"] = replace(case["outline"], semantic_edges=tuple(
                replace(e, start=reflect(e.start), end=reflect(e.end)) for e in case["outline"].semantic_edges))
            mirrored["alternatives"] = []
            build_families(mirrored, label)
            for alt, reflected_alt in zip(case["alternatives"], mirrored["alternatives"]):
                reflected = reflected_alt["points"]
                expected = [reflect(p) for p in alt["points"]]
                error = max(min(math.dist(p, q) for q in reflected) for p in expected)
                assert error < 1e-7
                alt["mirror_error_mm"] = error
                alt["mirrored_points"] = reflected
            results[label].update(tangent=case["tangent"], inward=case["inward"])
        stability = []
        for factor in (.99, .999, 1.001, 1.01):
            varied_config = deepcopy(configs[owner])
            varied_config["height"] *= factor
            varied = analyze(owner, node, varied_config, saved[(owner, node)])
            build_families(varied, label)
            counts = [a["vertices"] for a in varied["alternatives"]]
            assert counts == [a["vertices"] for a in case["alternatives"]]
            stability.append(dict(height_factor=factor, vertices=counts,
                minimum_free_margins=[a["minimum_free_margin"] for a in varied["alternatives"]]))
        results[label]["height_stability"] = stability
        print(label, json.dumps(results[label], ensure_ascii=True))
    assert hashlib.sha256(source.read_bytes()).hexdigest() == before
    (output/"coordenadas.json").write_text(json.dumps(dict(reference_sha256=before, cases=results),
        ensure_ascii=False, indent=2), encoding="utf-8")
    text = ["# Coordenadas das propostas — Fase 1", "",
            "Milímetros no plano local da treliça, origem no nó. P1…Pn correspondem aos SVGs.",
            "Precisão de apresentação: 0,001 mm; JSON conserva os valores do cálculo.", ""]
    for label, result in results.items():
        text += [f'## {label} — {result["owner"]} / {result["node"]}', ""]
        variants = [("Persistido no FCStd", result["persisted"]), ("Recomputado C6-P", result["current"])]
        variants += [(a["name"], a["points"]) for a in result["alternatives"]]
        for name, points in variants:
            text += [f"### {name}", "", "| Ponto | x | y |", "|---|---:|---:|"]
            text += [f"| P{i+1} | {p[0]:.3f} | {p[1]:.3f} |" for i, p in enumerate(points)]
            text += [""]
        text += [f'Área atual: {result["current_area"]:.3f} mm².', ""]
        for a in result["alternatives"]:
            text += [f'- {a["name"]}: {a["area"]:.3f} mm²; margem livre mínima {a["minimum_free_margin"]:.3f} mm;',
                     f'  interseções com projeções nominais de membros não participantes: {a["nonparticipant_nominal_projection_intersections"]}.']
        text += [""]
        if label == "B":
            text += ["O espelhado do SVG usa Pᵢ′ = (−xᵢ, yᵢ) de B2. O cálculo independente",
                     "dos corredores refletidos está no JSON; erro de equivalência inferior a 10⁻⁷ mm.", ""]
    (output/"coordenadas.md").write_text("\n".join(text), encoding="utf-8")


if __name__ == "__main__":
    main(Path(sys.argv[1]), ROOT/"Documentation"/"gusset_phase1")
