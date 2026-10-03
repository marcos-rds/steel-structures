"""Conditional sharp-corner closure with the real C6 fan configurations."""
from dataclasses import replace
import copy
import json
import math
from pathlib import Path
import unittest
from unittest.mock import patch

from freecad.SteelStructures.connections import gusset_families as f
from freecad.SteelStructures.connections.models import GussetSupportLine
from tests.test_gusset_families_round1 import compute

ROOT = Path(__file__).parent
REFERENCE = json.loads((ROOT/'fixtures/gusset_round1.json').read_text(encoding='utf8'))
APPROVED = json.loads((ROOT/'fixtures/gusset_tip_round2.json').read_text(encoding='utf8'))


class ConditionalFanTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.computed = {owner:compute(value) for owner,value in REFERENCE['owners'].items()}
        cls.cases = {case['group']:case for case in REFERENCE['cases']}

    def data(self, group):
        case = self.cases[group]
        owner = self.computed[case['owner']]
        return owner[1][case['node']], owner[2][case['node']], owner[3]

    def test_only_local_triangles_are_removed_and_slopes_are_preserved(self):
        for group, cut_count in (('F04_03',1),('F04_04',2)):
            with self.subTest(group=group):
                data, actual, diagnostics = self.data(group)
                spec, participants, corridors, supports, legacy = data
                self.assertFalse(diagnostics)
                self.assertTrue(f._three_web_fan(participants,supports))
                chord = next(s for s in supports if s.kind == 'CHORD_BOUNDARY')
                selected = f._sharp_chord_ends(legacy.points,chord,spec.member_overlap)
                self.assertEqual(len(selected),cut_count)
                self.assertTrue(all(a < f.SHARP_CHORD_ANGLE_DEG for _i,_n,a in selected))
                self.assertEqual(actual.points,tuple(tuple(p) for p in APPROVED[group]))
                self.assertLess(actual.area,legacy.area)
                self.assertEqual(actual.spec,legacy.spec)
                f.validate_family(actual.points,replace(f.requirements(*data),contacts=()))
                self.assertEqual(sum(e.kind=='CHORD_BOUNDARY' for e in actual.semantic_edges),1)
                self.assertEqual(len(actual.points),len(legacy.points)+cut_count)
                _outline, cuts = f.truncate_sharp_fan(*data)
                self.assertEqual(len(cuts),cut_count)
                for cut in cuts:
                    self.assertTrue(cut.accepted,cut.reason)
                    self.assertAlmostEqual(cut.perpendicular_length,.4*cut.local_height)
                    self.assertAlmostEqual(cut.preserved_side_length,.6*cut.original_side_length)
                    self.assertLess(cut.perpendicular_length,cut.preserved_side_length)
                    self.assertLess(cut.perpendicular_length,cut.max_depth)
                    for p in (cut.cut_point,cut.contact_point,cut.side_end):
                        self.assertLess(min(math.dist(p,q) for q in actual.points),1e-6)
                    # The long inclined edge must still exist with its cap provenance.
                    self.assertTrue(any(e.kind=='WEB_END_CAP' and
                        min(math.dist(e.start,cut.cut_point)+math.dist(e.end,cut.side_end),
                            math.dist(e.end,cut.cut_point)+math.dist(e.start,cut.side_end))<1e-6
                        for e in actual.semantic_edges))
                # No new material anywhere, hence no new collision envelope.
                for n,h in f._outline_halfplanes(legacy.points):
                    self.assertTrue(all(f.dot(n,p)<=h+1e-6 for p in actual.points))
                expected_removed = sum(.5*c.perpendicular_length*math.dist(
                    c.original_tip,c.contact_point) for c in cuts)
                self.assertAlmostEqual(legacy.area-actual.area,expected_removed,places=6)
                if group == 'F04_03':
                    # The unselected 68.2-degree left slope is identical.
                    self.assertEqual(actual.points[0],legacy.points[0])
                    self.assertEqual(actual.points[-1],legacy.points[-1])

    def test_nonsharp_and_protected_fans_keep_exact_signature(self):
        for group in ('F04_01','F04_02','F04_05'):
            with self.subTest(group=group):
                data, actual, diagnostics = self.data(group)
                self.assertFalse(diagnostics)
                chord = next(s for s in data[3] if s.kind=='CHORD_BOUNDARY')
                self.assertEqual(f._sharp_chord_ends(data[-1].points,chord,data[0].member_overlap),())
                self.assertEqual(actual.points,data[-1].points)
                self.assertEqual(actual.semantic_edges,data[-1].semantic_edges)

    def test_angle_and_overlap_guards_are_dimensionless(self):
        chord = GussetSupportLine('chord',(1.,0.),(0.,-1.),0.,'CHORD_BOUNDARY')
        sharp = ((-200.,0.),(200.,0.),(100.,150.),(-100.,150.))
        one_side_steep = ((-200.,0.),(200.,0.),(125.,150.),(-100.,150.))
        self.assertEqual(len(f._sharp_chord_ends(sharp,chord,120.)),2)
        self.assertEqual(len(f._sharp_chord_ends(one_side_steep,chord,120.)),1)
        self.assertEqual(f._sharp_chord_ends(sharp,chord,150.),())
        scaled = tuple((1.7*x,1.7*y) for x,y in sharp)
        self.assertEqual(len(f._sharp_chord_ends(scaled,chord,204.)),2)

    def test_analogous_two_web_and_intermediate_families_stay_approved(self):
        for group,case in self.cases.items():
            if not group.startswith(('F02','F03')):
                continue
            data, actual, diagnostics = self.data(group)
            with self.subTest(group=group):
                self.assertFalse(diagnostics)
                self.assertFalse(f._three_web_fan(data[1],data[3]))
                chord = next(s for s in data[3] if s.kind=='CHORD_BOUNDARY')
                self.assertEqual(f._sharp_chord_ends(actual.points,chord,data[0].member_overlap),())
                self.assertEqual(tuple(map(tuple,case['expected'])),actual.points)

    def test_failed_short_cut_keeps_legacy_and_records_reason(self):
        data, _actual, _diagnostics = self.data('F04_03')
        with patch.object(f,'validate_family',side_effect=ValueError('margem física indisponível')):
            outline, reason = f.apply_approved_family(*data)
        self.assertIs(outline,data[-1])
        self.assertIn('Truncamento local recusado',reason)
        self.assertIn('margem física indisponível',reason)

    def test_lateral_constraint_refuses_cut_without_growing_it(self):
        data, _actual, _diagnostics = self.data('F04_03')
        spec,parts,corridors,supports,legacy = data
        limit = max(p[0] for p in legacy.points)
        protected_side = GussetSupportLine('required_lateral',(0.,1.),(1.,0.),limit,'FREE_MARGIN')
        actual,cuts = f.truncate_sharp_fan(spec,parts,corridors,supports+(protected_side,),legacy)
        self.assertIs(actual,legacy)
        self.assertEqual(len(cuts),1)
        self.assertFalse(cuts[0].accepted)
        self.assertIn('Margem lateral',cuts[0].reason)
        self.assertAlmostEqual(cuts[0].perpendicular_length,.4*cuts[0].local_height)
        self.assertAlmostEqual(cuts[0].max_depth,0.)

    def test_depth_scales_with_local_height_not_width_or_selection_angle(self):
        for group in ('F04_03','F04_04'):
            case = self.cases[group]
            for overlap in (50.,100.,200.):
                value = copy.deepcopy(REFERENCE['owners'][case['owner']])
                for intent in value['connection_intents'].values():
                    intent['gusset']['member_overlap']=overlap
                _candidate,captured,outlines,diagnostics = compute(value)
                self.assertFalse(diagnostics)
                actual,cuts = f.truncate_sharp_fan(*captured[case['node']])
                self.assertTrue(cuts)
                self.assertEqual(actual.points,outlines[case['node']].points)
                for cut in cuts:
                    self.assertTrue(cut.accepted,cut.reason)
                    self.assertAlmostEqual(cut.perpendicular_length,.4*cut.local_height)
        # Width constrains feasibility, not the visual target on the same side.
        data,_actual,_diagnostics = self.data('F04_03')
        spec,parts,corridors,supports,legacy = data
        keys = {p.participant_key for p in parts if p.role not in f.CHORDS}
        narrow = tuple(replace(c,transverse_low=-4.,transverse_high=4.)
                       if c.participant_key in keys else c for c in corridors)
        _actual,cuts = f.truncate_sharp_fan(spec,parts,narrow,supports,legacy)
        self.assertTrue(cuts[0].accepted,cuts[0].reason)
        self.assertAlmostEqual(cuts[0].perpendicular_length,74.636)

    def test_candidates_and_exact_physical_limit(self):
        for group in ('F04_03','F04_04'):
            data,_actual,_diagnostics = self.data(group)
            for fraction in (.25,.4,.55):
                outline,cuts = f.truncate_sharp_fan(*data,depth_fraction=fraction)
                self.assertTrue(all(c.accepted for c in cuts),cuts)
                f.validate_family(outline.points,replace(f.requirements(*data),contacts=()))
                for cut in cuts:
                    self.assertAlmostEqual(cut.perpendicular_length,fraction*cut.local_height)
                    self.assertGreaterEqual(cut.terminal_clearance,data[0].edge_margin)
            fraction = min(c.max_depth/c.local_height for c in cuts)
            _outline,limit_cuts = f.truncate_sharp_fan(*data,depth_fraction=fraction)
            self.assertTrue(all(c.accepted for c in limit_cuts),limit_cuts)
            self.assertAlmostEqual(min(c.terminal_clearance for c in limit_cuts),data[0].edge_margin)
            outline,rejected = f.truncate_sharp_fan(*data,depth_fraction=fraction+1e-4)
            self.assertIs(outline,data[-1])
            self.assertTrue(all(not c.accepted for c in rejected))
            self.assertTrue(all('Margem terminal' in c.reason for c in rejected))

    def test_full_side_removal_is_never_accepted(self):
        data,_actual,_diagnostics = self.data('F04_04')
        for fraction in (0.,1.,1.1):
            outline,cuts = f.truncate_sharp_fan(*data,depth_fraction=fraction)
            self.assertIs(outline,data[-1])
            self.assertTrue(all(not c.accepted for c in cuts))

    def test_one_refused_corner_does_not_remove_the_other_valid_local_cut(self):
        data,_actual,_diagnostics = self.data('F04_04')
        spec,parts,corridors,supports,legacy = data
        limit = -min(p[0] for p in legacy.points)
        protect_left = GussetSupportLine('left',(0.,1.),(-1.,0.),limit,'FREE_MARGIN')
        actual,cuts = f.truncate_sharp_fan(spec,parts,corridors,supports+(protect_left,),legacy)
        self.assertEqual(sum(c.accepted for c in cuts),1)
        refused = next(c for c in cuts if not c.accepted)
        self.assertLess(refused.original_tip[0],0.)
        self.assertIn('Margem lateral',refused.reason)
        self.assertIn(refused.original_tip,actual.points)
        self.assertEqual(len(actual.points),len(legacy.points)+1)

    def test_f08_keeps_current_shape_and_never_selects_variant_k(self):
        data,actual,diagnostics = self.data('F08_01')
        self.assertFalse(diagnostics)
        self.assertEqual(actual.points,data[-1].points)
        self.assertEqual(actual.semantic_edges,data[-1].semantic_edges)


if __name__=='__main__':
    unittest.main()
