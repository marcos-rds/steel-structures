"""Explicit, transient contour families; independent of document/node identities.

Physical half-planes are inviolable. Free supports are design choices, not
material boundaries. Clearance is regional: overlap tips, existing applicable
lateral offsets, and bare proximal coverage (never a new global proximal disk).
The legacy contact spans are lower bounds, not sources of free-edge directions.
"""

from dataclasses import dataclass, replace
import math

from .gusset import (_clip_support, _hull, _semantic_edges, _validated_supports,
                     polygon_area)
from .models import GussetSupportLine

CHORDS = ("TOP_CHORD", "BOTTOM_CHORD")
PHYSICAL = ("CHORD_BOUNDARY", "TERMINAL_BOUNDARY")
EPS = 1e-6
SHARP_CHORD_ANGLE_DEG = 60.
TIP_DEPTH_FRACTION = .40


def dot(a, b):
    return a[0]*b[0]+a[1]*b[1]


def unit(v):
    length = math.hypot(*v)
    if length < EPS:
        raise ValueError("Família sem direção física unívoca.")
    return v[0]/length, v[1]/length


def perp(v):
    return -v[1], v[0]


def negative(v):
    return -v[0], -v[1]


def approved_family(participants, supports):
    """Select only approved physical classes; all other classes retain legacy."""
    webs = [p for p in participants if p.role not in CHORDS]
    chords = [p for p in participants if p.role in CHORDS]
    if len(webs) != 2 or any(p.end == "Through" for p in webs):
        return ""
    roles = sorted(p.role for p in webs)
    normals = [s.normal for s in supports if s.kind == "CHORD_BOUNDARY"]
    broken = any(abs(a[0]*b[1]-a[1]*b[0]) > EPS
                 for a in normals for b in normals)
    if any(p.end == "ChordBreak" for p in chords) and broken:
        return "F05_C" if roles == ["DIAGONAL", "DIAGONAL"] else ""
    if any(s.kind == "TERMINAL_BOUNDARY" for s in supports):
        return "F07_L"
    if not any(s.kind == "CHORD_BOUNDARY" for s in supports):
        return ""
    if roles == ["DIAGONAL", "DIAGONAL"]:
        return "F03_L"
    if roles == ["DIAGONAL", "VERTICAL"]:
        return "F02_L"
    return ""


@dataclass(frozen=True)
class FamilyRequirements:
    raw: tuple
    tips: tuple
    coverage: tuple
    contacts: tuple
    hard: tuple
    lateral: tuple
    margin: float

    def demand(self, normal):
        # Keep an existing lateral offset when the new edge has that normal.
        # Other orientations protect the complete terminal region, not an
        # invented clearance around the shared proximal section.
        applicable = [s.offset for s in self.lateral
                      if math.dist(s.normal, normal) < EPS]
        return max([dot(normal, p) for p in self.raw+self.contacts]
                   +[dot(normal, p)+self.margin for p in self.tips]
                   +applicable)


def requirements(spec, participants, corridors, supports, legacy):
    keys = {p.participant_key for p in participants if p.role not in CHORDS}
    raw, tips = [], []
    for c in corridors:
        if c.participant_key not in keys:
            continue
        direction = unit(c.direction)
        lateral = perp(direction)
        for station in (0., spec.member_overlap):
            for width in (c.transverse_low, c.transverse_high):
                point = tuple(station*direction[i]+width*lateral[i] for i in range(2))
                raw.append(point)
                if station:
                    tips.append(point)
    hard = tuple(s for s in supports if s.kind in PHYSICAL)
    coverage = _hull(raw)
    for support in hard:
        coverage = _clip_support(coverage, support)
    contacts = tuple(p for e in legacy.semantic_edges if e.kind == "CHORD_BOUNDARY"
                     for p in (e.start, e.end))
    return FamilyRequirements(tuple(raw), tuple(tips), coverage, contacts, hard,
                              tuple(s for s in supports if s.kind == "FREE_MARGIN"),
                              spec.edge_margin)


def family_normals(family, participants, corridors, supports):
    chord = [s.normal for s in supports if s.kind == "CHORD_BOUNDARY"]
    inward = unit(negative(tuple(sum(n[i] for n in chord) for i in range(2))))
    tangent = perp(inward)
    keys = {p.participant_key for p in participants if p.role not in CHORDS}
    by_key = {}
    for c in corridors:
        if c.participant_key not in keys:
            continue
        direction = unit(c.direction)
        if c.participant_key in by_key and math.dist(by_key[c.participant_key], direction) > EPS:
            raise ValueError("Ramos não colineares no mesmo participante terminal.")
        by_key[c.participant_key] = direction
    if len(by_key) != 2:
        raise ValueError("A família requer dois ramos terminais físicos.")
    directions = tuple(by_key.values())
    if min(dot(d, inward) for d in directions) < -EPS:
        raise ValueError("Ramos em setores opostos ao contato do banzo.")
    if family == "F02_L":
        first, second = sorted(directions, key=lambda d: dot(d, inward), reverse=True)
        if abs(dot(first, inward)-dot(second, inward)) < EPS and math.dist(first, second) > EPS:
            raise ValueError("Empate físico entre ramos dominantes; preferência lateral ambígua.")
        return (perp(first), negative(perp(first)), first, second)
    if family == "F03_L":
        return (tangent, negative(tangent), inward)+directions
    if family == "F05_C":
        return tangent, negative(tangent), inward
    if family == "F07_L":
        ordered = sorted(directions, key=lambda d: dot(d, inward))
        # Equal obliquity cannot be resolved by participant key or input order.
        if abs(dot(ordered[0], inward)-dot(ordered[1], inward)) < EPS:
            raise ValueError("Terminal com obliquidade empatada; família chanfrada ambígua.")
        return tangent, negative(tangent), inward, ordered[0]
    raise ValueError("Família não aprovada.")


def intersect_supports(supports):
    """Intersect a bounded convex half-plane family, without a guessed box."""
    angles = sorted(math.atan2(s.normal[1], s.normal[0]) for s in supports)
    gaps = [(angles[(i+1) % len(angles)]-a) % (2*math.pi) for i, a in enumerate(angles)]
    if max(gaps) >= math.pi-1e-9:
        raise ValueError("Família de suportes não limita uma região fechada.")
    vertices = []
    for i, a in enumerate(supports):
        for b in supports[i+1:]:
            determinant = a.normal[0]*b.normal[1]-a.normal[1]*b.normal[0]
            if abs(determinant) < 1e-9:
                continue
            p = ((a.offset*b.normal[1]-a.normal[1]*b.offset)/determinant,
                 (a.normal[0]*b.offset-a.offset*b.normal[0])/determinant)
            if all(dot(s.normal, p) <= s.offset+EPS for s in supports):
                vertices.append(p)
    return _hull(vertices)


def validate_family(points, req):
    """Audit convex coverage, free-tip margins, hard limits and contact spans."""
    if len(points) < 3 or polygon_area(points) <= EPS:
        raise ValueError("Contorno de família degenerado.")
    edges = []
    for a, b in zip(points, points[1:]+points[:1]):
        n = unit((b[1]-a[1], a[0]-b[0]))
        h = dot(n, a)
        if any(dot(n, p) > h+EPS for p in points):
            raise ValueError("Contorno não convexo ou descontínuo.")
        edges.append((n, h))
        if any(dot(n, p) > h+EPS for p in req.coverage+req.contacts):
            raise ValueError("Perda de cobertura/sobreposição ou de contato existente.")
        physical = any(math.dist(n, s.normal) < EPS and abs(h-s.offset) < EPS for s in req.hard)
        if not physical and any(dot(n, p)+req.margin > h+EPS for p in req.tips):
            raise ValueError("Margem terminal livre inferior a EdgeMargin.")
        for s in req.lateral:
            if not physical and math.dist(n, s.normal) < EPS and h < s.offset-EPS:
                raise ValueError("Margem lateral existente reduzida.")
    for s in req.hard:
        if any(dot(s.normal, p) > s.offset+EPS for p in points):
            raise ValueError("Contorno ultrapassa fronteira física.")
        if s.kind == "CHORD_BOUNDARY" and not any(
                math.dist(n, s.normal) < EPS and abs(h-s.offset) < EPS for n, h in edges):
            raise ValueError("Banzo sem segmento de contato físico.")


def _three_web_fan(participants, supports):
    """The compact D/D/V fan on one continuous chord, irrespective of keys."""
    webs = [p for p in participants if p.role not in CHORDS]
    chords = [p for p in participants if p.role in CHORDS]
    chord_lines = [s for s in supports if s.kind == "CHORD_BOUNDARY"]
    return (sorted(p.role for p in webs) == ["DIAGONAL", "DIAGONAL", "VERTICAL"]
            and all(p.end != "Through" for p in webs)
            and len(chords) == 1 and chords[0].end == "Through"
            and len(chord_lines) == 1
            and not any(s.kind == "TERMINAL_BOUNDARY" for s in supports))


def _outline_halfplanes(points):
    result = []
    for a, b in zip(points, points[1:]+points[:1]):
        normal = unit((b[1]-a[1], a[0]-b[0]))
        result.append((normal, dot(normal, a)))
    return tuple(result)


def _sharp_chord_ends(points, chord, member_overlap):
    """Return exposed facets incident to a chord with acute approach angle.

    The acute angle is measured to the chord tangent. The two endpoints must
    belong to an actual chord-contact edge. This excludes remote cap corners.
    """
    edges = _outline_halfplanes(points)
    contact = [i for i, (n, h) in enumerate(edges)
               if math.dist(n, chord.normal) <= EPS and abs(h-chord.offset) <= EPS]
    if len(contact) != 1:
        return ()
    tangent = perp(chord.normal)
    selected = []
    index = contact[0]
    # CCW polygon: the previous facet enters the first chord endpoint and the
    # next facet leaves its second endpoint.
    for free_index, endpoint, other in (
            ((index-1) % len(points), points[index], points[(index-1) % len(points)]),
            ((index+1) % len(points), points[(index+1) % len(points)],
             points[(index+2) % len(points)])):
        approach = (other[0]-endpoint[0], other[1]-endpoint[1])
        along = abs(dot(tangent, approach))
        depth = abs(dot(chord.normal, approach))
        angle = math.degrees(math.atan2(depth, along))
        # A steep-looking facet entirely inside the configured overlap band
        # is a useful compact fan closure (the approved C6-N/C6-O case), not
        # a remote wedge requiring a new perpendicular edge.
        if angle >= SHARP_CHORD_ANGLE_DEG-EPS or depth <= member_overlap+EPS:
            continue
        # Outward along the chord is determined by the existing contact
        # interval, not by world X or a participant's semantic name.
        opposite = points[(index+1) % len(points)] if free_index == (index-1) % len(points) else points[index]
        outward = tangent if dot(tangent, endpoint) > dot(tangent, opposite) else negative(tangent)
        selected.append((free_index, outward, angle))
    return tuple(selected)


@dataclass(frozen=True)
class TipTruncation:
    """Transient audit of one local triangle cut; never persisted in the model."""
    original_tip: tuple
    side_end: tuple
    cut_point: tuple
    contact_point: tuple
    max_depth: float
    original_side_length: float
    preserved_side_length: float
    perpendicular_length: float
    accepted: bool
    reason: str = ""
    local_height: float = 0.
    terminal_clearance: float = 0.


def truncate_sharp_fan(spec, participants, corridors, supports, legacy, *,
                       depth_fraction=TIP_DEPTH_FRACTION):
    """Clip only a small triangle off each eligible original chord endpoint.

    Depth targets 40% of the original side's normal height, independently of
    selection angle. The optional fraction is for offline candidate studies.
    All original sloping half-planes remain. Thus every accepted result
    is a subset of the original plate, preserving its collision envelope.
    An infeasible target is recorded, never silently capped or enlarged.
    """
    chord = next(s for s in supports if s.kind == "CHORD_BOUNDARY")
    changes = _sharp_chord_ends(legacy.points, chord, spec.member_overlap)
    if not changes:
        return legacy, ()
    req = requirements(spec, participants, corridors, supports, legacy)
    compact_req = replace(req, contacts=())
    web_keys = {p.participant_key for p in participants if p.role not in CHORDS}
    points, new_lines, audits = legacy.points, [], []
    for index, outward, _angle in changes:
        ends = (legacy.points[index], legacy.points[(index+1) % len(legacy.points)])
        tip, other = sorted(ends, key=lambda p: abs(dot(chord.normal, p)-chord.offset))
        side = (other[0]-tip[0], other[1]-tip[1])
        depth = abs(dot(chord.normal, side))
        ratio = depth_fraction
        cut_depth = ratio*depth
        # Exact bound for the moving perpendicular support. Coverage is already
        # clipped to hard limits; clearance remains terminal/regional, not global.
        demand = max([dot(outward,p) for p in req.coverage]
                     +[dot(outward,p)+req.margin for p in req.tips]
                     +[s.offset for s in req.lateral
                       if math.dist(s.normal,outward)<EPS])
        retreat = dot(outward,tip)-dot(outward,other)
        max_depth = max(0.,min(depth,depth*(dot(outward,tip)-demand)/retreat)) if retreat>EPS else 0.
        cut = tuple(tip[i]+ratio*side[i] for i in range(2))
        contact = tuple(cut[i]+cut_depth*chord.normal[i] for i in range(2))
        original_length = math.dist(tip, other)
        preserved_length = math.dist(cut, other)
        audit = TipTruncation(tip, other, cut, contact, max_depth,
                              original_length, preserved_length, cut_depth, False,
                              local_height=depth,
                              terminal_clearance=dot(outward,cut)-max(dot(outward,p) for p in req.tips))
        try:
            if cut_depth <= EPS or not 0. < ratio < 1.:
                raise ValueError("Corte sem profundidade útil ou sem lateral superior preservada.")
            if dot(outward, tip) <= dot(outward, other)+EPS:
                raise ValueError("A lateral não recua da ponta para o interior da chapa.")
            support = GussetSupportLine("|".join(sorted(web_keys)), perp(outward),
                                         outward, dot(outward, cut), "FREE_MARGIN")
            # Keep the original polygon and its inclined sides: clipping adds
            # one small free facet rather than replacing any previous support.
            candidate = _hull(_clip_support(points, support))
            validate_family(candidate, compact_req)
            if len(candidate) != len(points)+1 or any(
                    min(math.dist(p,q) for q in candidate) > EPS
                    for p in (cut, contact, other)):
                raise ValueError("O corte não preserva a lateral inclinada e seu vértice superior.")
            triangle_area = .5*cut_depth*math.dist(tip, contact)
            removed_area = polygon_area(points)-polygon_area(candidate)
            if removed_area <= EPS or abs(removed_area-triangle_area) > EPS*max(1.,triangle_area):
                raise ValueError("A remoção não se limita ao triângulo externo da ponta.")
            points = candidate
            new_lines.append(support)
            audits.append(replace(audit, accepted=True))
        except ValueError as exc:
            audits.append(replace(audit, reason=str(exc)+
                f" Alvo {cut_depth:.6f} mm; limite físico do suporte {max_depth:.6f} mm."))
    if not new_lines:
        return legacy, tuple(audits)
    provenance = _validated_supports(tuple(supports)+tuple(new_lines))
    return replace(legacy, points=points, area=polygon_area(points),
                   semantic_edges=_semantic_edges(points, provenance)), tuple(audits)


def apply_approved_family(spec, participants, corridors, supports, legacy):
    """Return (outline, fallback reason). Protected families are exact no-ops.

    Invalid approved proposals may only fall back to an audited valid legacy
    outline. If both are invalid, propagate a diagnostic rather than hide loss
    of coverage or silently reduce a configured parameter.
    """
    if _three_web_fan(participants, supports):
        outline, cuts = truncate_sharp_fan(spec, participants, corridors, supports, legacy)
        refusals = [f"Truncamento local recusado na ponta {c.original_tip}: {c.reason}"
                    for c in cuts if not c.accepted]
        return outline, "; ".join(refusals)
    family = approved_family(participants, supports)
    if not family:
        return legacy, ""
    req = requirements(spec, participants, corridors, supports, legacy)
    try:
        normals = family_normals(family, participants, corridors, supports)
        keys = "|".join(sorted(p.participant_key for p in participants if p.role not in CHORDS))
        free = tuple(GussetSupportLine(keys, perp(n), n, req.demand(n), "FREE_MARGIN")
                     for n in normals)
        lines = _validated_supports(req.hard+free)
        points = intersect_supports(lines)
        validate_family(points, req)
        # Old semantic provenance is reusable only on coincident new edges.
        provenance = _validated_supports(tuple(supports)+free)
        return replace(legacy, points=points, area=polygon_area(points),
                       semantic_edges=_semantic_edges(points, provenance)), ""
    except ValueError as exc:
        validate_family(legacy.points, req)
        return legacy, family+": "+str(exc)
