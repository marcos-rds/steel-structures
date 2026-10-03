"""Approved family rules: physical covariance plus all 41 reference plates."""
import copy
from dataclasses import replace
import json
import math
from pathlib import Path
import unittest
from unittest.mock import patch

from freecad.SteelStructures.connections import gusset_families as f
from freecad.SteelStructures.connections.gusset import _hull, polygon_area
from freecad.SteelStructures.trusses import gussets as g
from freecad.SteelStructures.trusses.connections import connection_participants
from freecad.SteelStructures.trusses.realization import build_candidate
from scripts import gusset_family_review as review

FIXTURE = Path(__file__).parent/'fixtures/gusset_round1.json'
TIP_FIXTURE = json.loads((Path(__file__).parent/'fixtures/gusset_tip_round2.json').read_text(encoding='utf8'))


def compute(config):
    candidate = build_candidate(config)
    captured = {}
    original = g.build_gusset_outline
    def capture(spec, corridors, supports):
        legacy = original(spec, corridors, supports)
        captured[spec.node_key] = (spec, connection_participants(candidate,spec.node_key),
                                   tuple(corridors), supports, legacy)
        return legacy
    with patch.object(g, 'build_gusset_outline', capture):
        outlines, diagnostics = g.preliminary_gusset_outlines(candidate)
    return candidate, captured, {o.spec.node_key:o for o in outlines}, diagnostics


class ApprovedFamilyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = json.loads(FIXTURE.read_text(encoding='utf8'))
        cls.computed = {owner: compute(config) for owner,config in cls.fixture['owners'].items()}

    def assertPolygon(self, actual, expected, tolerance=1e-6):
        self.assertEqual(len(actual), len(expected))
        self.assertLess(max(min(math.dist(p,q) for q in actual) for p in expected), tolerance)

    def test_all_41_plates_and_30_approved_configurations(self):
        groups, changed, refined, persisted_changed = set(), 0, 0, 0
        for case in self.fixture['cases']:
            with self.subTest(plate=case['group'],owner=case['owner'],node=case['node']):
                candidate, captured, outlines, diagnostics = self.computed[case['owner']]
                self.assertFalse(diagnostics)
                outline = outlines[case['node']]
                data = captured[case['node']]
                legacy = data[-1]
                self.assertPolygon(legacy.points,case['before'])
                self.assertPolygon(outline.points,TIP_FIXTURE.get(case['group'],case['expected']))
                if case['group'] in TIP_FIXTURE:
                    self.assertNotEqual(outline.points, legacy.points)
                    req = replace(f.requirements(*data),contacts=())
                    f.validate_family(outline.points, req)
                    refined += 1
                elif case['variant'] == 'Mantida':
                    self.assertEqual(outline.points, legacy.points)
                    self.assertEqual(outline.semantic_edges, legacy.semantic_edges)
                else:
                    f.validate_family(outline.points, f.requirements(*data))
                    changed += 1
                # Independent audit, including nominal nonparticipant overlap.
                physical = review.make_case(case['owner'], candidate.config, candidate,
                    dict(name=case['group'],signature=dict(points=case['saved'])),
                    replace(legacy,attachment=outline.attachment),(data[0],data[2],data[3]))
                if case['group'] in TIP_FIXTURE:
                    physical['contact_points'] = []
                self.assertTrue(review.validation(physical,list(outline.points))['ok'])
                persisted_changed += not review.same_polygon(case['saved'],case['before'])
                groups.add(case['group'])
        self.assertEqual((len(self.fixture['cases']),len(groups),changed,refined,persisted_changed),(41,30,24,3,9))

    def test_five_terminal_margin_violations_are_fixed_and_single_terminal_unchanged(self):
        fixed = 0
        for case in self.fixture['cases']:
            if not case['group'].startswith('F07'):
                continue
            data = self.computed[case['owner']][1][case['node']]
            outline = self.computed[case['owner']][2][case['node']]
            req = f.requirements(*data)
            if case['variant'] == 'Mantida':
                f.validate_family(data[-1].points,req)
                self.assertEqual(outline.points,data[-1].points)
            else:
                with self.assertRaisesRegex(ValueError,'Margem terminal'):
                    f.validate_family(data[-1].points,req)
                f.validate_family(outline.points,req)
                fixed += 1
        self.assertEqual(fixed,5)

    def test_covariance_reflection_rotation_scaling_and_input_order(self):
        # Transform complete physical sections, including handed transverse
        # bounds. Never reflect just axes while leaving an angle insertion fixed.
        seen = set()
        for case in self.fixture['cases']:
            if case['group'] in seen or (case['variant'] == 'Mantida' and case['group'] not in TIP_FIXTURE):
                continue
            seen.add(case['group'])
            spec, parts, corridors, supports, legacy = self.computed[case['owner']][1][case['node']]
            expected = self.computed[case['owner']][2][case['node']]
            for angle, mirror, scale in ((.63,1,1), (0,-1,1), (.4,-1,1.1), (0,1,.4)):
                with self.subTest(group=case['group'],angle=angle,mirror=mirror,scale=scale):
                    def direction(p):
                        return (math.cos(angle)*mirror*p[0]-math.sin(angle)*p[1],
                                math.sin(angle)*mirror*p[0]+math.cos(angle)*p[1])
                    def point(p): return tuple(scale*v for v in direction(p))
                    cr = tuple(replace(c,direction=direction(c.direction),
                        transverse_low=scale*(c.transverse_low if mirror==1 else -c.transverse_high),
                        transverse_high=scale*(c.transverse_high if mirror==1 else -c.transverse_low))
                        for c in reversed(corridors))
                    su = tuple(replace(s,normal=direction(s.normal),direction=direction(s.direction),
                                       offset=scale*s.offset) for s in reversed(supports))
                    sp = replace(spec,plate_thickness=spec.plate_thickness*scale,
                                 member_overlap=spec.member_overlap*scale,edge_margin=spec.edge_margin*scale,
                                 node_key='arbitrary_node',stable_key='arbitrary_plate')
                    po = _hull([point(p) for p in legacy.points])
                    old = replace(legacy,spec=sp,points=po,area=polygon_area(po),semantic_edges=tuple(
                        replace(e,start=point(e.start),end=point(e.end)) for e in legacy.semantic_edges))
                    actual, reason = f.apply_approved_family(sp,tuple(reversed(parts)),cr,su,old)
                    self.assertFalse(reason)
                    self.assertPolygon(actual.points,[point(p) for p in expected.points])

    def test_small_dimension_changes_are_continuous_in_complete_pipeline(self):
        for owner, config in self.fixture['owners'].items():
            before = self.computed[owner][2]
            for factor in (.99999,1.00001):
                value = copy.deepcopy(config)
                value['height'] *= factor
                _, captured, outlines, diagnostics = compute(value)
                self.assertFalse(diagnostics,(owner,diagnostics))
                self.assertEqual(set(before),set(outlines))
                for node, outline in outlines.items():
                    distance = max(min(math.dist(p,q) for q in outline.points) for p in before[node].points)
                    self.assertLess(distance,.1,(owner,node,distance))
                    if f.approved_family(captured[node][1],captured[node][3]):
                        f.validate_family(outline.points,f.requirements(*captured[node]))

    def test_parametric_overlap_margin_and_thickness(self):
        visited = set()
        for case in self.fixture['cases']:
            if case['variant'] == 'Mantida' or case['group'][:3] in visited:
                continue
            visited.add(case['group'][:3])
            for overlap, margin, thickness in ((100.,0.,8.),(220.,12.,10.),(180.,40.,12.)):
                value = copy.deepcopy(self.fixture['owners'][case['owner']])
                # Persisted canonical intents are a mapping keyed by node.
                for intent in value['connection_intents'].values():
                    intent['gusset'].update(member_overlap=overlap,edge_margin=margin,plate_thickness=thickness)
                _,captured,outlines,diagnostics = compute(value)
                with self.subTest(family=case['group'][:3],overlap=overlap,margin=margin):
                    self.assertFalse(diagnostics)
                    self.assertIn(case['node'],outlines)
                    f.validate_family(outlines[case['node']].points,f.requirements(*captured[case['node']]))

    def test_fallback_audits_legacy_and_never_hides_invalid_terminal(self):
        for group, valid in (('F02_01',True),('F07_01',False)):
            case = next(c for c in self.fixture['cases'] if c['group']==group)
            data = self.computed[case['owner']][1][case['node']]
            with patch.object(f,'family_normals',side_effect=ValueError('synthetic physical conflict')):
                if valid:
                    actual, reason = f.apply_approved_family(*data)
                    self.assertIs(actual,data[-1])
                    self.assertIn('synthetic physical conflict',reason)
                else:
                    with self.assertRaisesRegex(ValueError,'Margem terminal'):
                        f.apply_approved_family(*data)

    def test_dominant_tie_is_explicit_not_key_dependent(self):
        case = next(c for c in self.fixture['cases'] if c['group']=='F02_01')
        _, parts, corridors, supports, _ = self.computed[case['owner']][1][case['node']]
        web_keys = [p.participant_key for p in parts if p.role not in f.CHORDS]
        changed = tuple(replace(c,direction=((-.6,.8) if c.participant_key==web_keys[0] else (.6,.8)))
                        if c.participant_key in web_keys else c for c in corridors)
        with self.assertRaisesRegex(ValueError,'Empate físico'):
            f.family_normals('F02_L',parts,changed,supports)

    def test_world_frame_and_asymmetric_section_rotations(self):
        visited = set()
        for case in self.fixture['cases']:
            if case['variant'] == 'Mantida' or case['group'][:3] in visited:
                continue
            visited.add(case['group'][:3])
            value = copy.deepcopy(self.fixture['owners'][case['owner']])
            value.update(start=[100.,200.,300.],end=[100.,10200.,300.],plane_normal=[1.,0.,0.])
            _,_,outlines,diagnostics = compute(value)
            self.assertFalse(diagnostics)
            before = self.computed[case['owner']][2][case['node']]
            self.assertPolygon(outlines[case['node']].points,before.points)
            for rotation in (-12., 12.):
                varied = copy.deepcopy(value)
                varied['role_specs']['DIAGONAL']['rotation'] = rotation
                _,captured,outlines,diagnostics = compute(varied)
                self.assertFalse(diagnostics)
                f.validate_family(outlines[case['node']].points,f.requirements(*captured[case['node']]))

    def test_collinear_chord_break_is_not_a_physical_ridge(self):
        case = next(c for c in self.fixture['cases'] if c['group']=='F03_01')
        _,parts,_,supports,_ = self.computed[case['owner']][1][case['node']]
        parts = tuple(replace(p,end='ChordBreak') if p.role in f.CHORDS else p for p in parts)
        self.assertEqual(f.approved_family(parts,supports),'F03_L')

    def test_degenerate_or_unbounded_supports_fail_explicitly(self):
        case = next(c for c in self.fixture['cases'] if c['group']=='F02_01')
        support = self.computed[case['owner']][1][case['node']][3][0]
        with self.assertRaises(ValueError):
            f.intersect_supports((replace(support,normal=(1.,0.)),
                                  replace(support,normal=(0.,1.))))


if __name__ == '__main__':
    unittest.main()
