"""Geometric regressions for additive DuoPitch support heights."""
import math
import unittest

from freecad.SteelStructures.trusses.envelope import definition_from_config, paths
from freecad.SteelStructures.trusses.realization import build_candidate
from freecad.SteelStructures.trusses.preset_contracts import PRESETS, compatible_presets
from freecad.SteelStructures.trusses.serialization import encode_state, decode_state
from freecad.SteelStructures.trusses.validation import validate_graph
from tests.test_truss_qa import config


class DuoPitchHeightTests(unittest.TestCase):
    def candidate(self, **changes):
        return build_candidate(config(envelope_type="DuoPitch", **changes))

    def test_legacy_zero_geometry_and_identities(self):
        old = self.candidate()
        explicit = self.candidate(left_end_height=0., right_end_height=0.,
                                  link_end_heights=False, reference_alignment="BottomChord")
        self.assertEqual(old.graph, explicit.graph)
        self.assertEqual(old.items, explicit.items)
        self.assertEqual(len([n for n in old.graph.nodes if n.optional_station_key == "S_START"]), 1)

    def test_all_presets_end_closures_and_valid_members(self):
        for preset in compatible_presets("DuoPitch"):
            for left, right in ((0., 0.), (150., 150.), (100., 300.), (0., 200.)):
                with self.subTest(preset=preset, heights=(left,right)):
                    candidate = self.candidate(topology_preset=preset, panel_count=12,
                        left_end_height=left, right_end_height=right, link_end_heights=False)
                    self.assertEqual(validate_graph(candidate.graph)[0], ())
                    for station, height in (("S_START",left),("S_END",right)):
                        nodes = [n for n in candidate.graph.nodes if n.optional_station_key == station]
                        self.assertEqual(len(nodes), 2 if height else 1)
                        top = next(n for n in nodes if "TOP_CHORD" in n.affiliations)
                        self.assertAlmostEqual(top.position_local[1], height)
                        if height:
                            bottom = next(n for n in nodes if "BOTTOM_CHORD" in n.affiliations)
                            self.assertTrue(any(e.role == "END_POST" and
                                {e.start_node_key,e.end_node_key} == {top.key,bottom.key}
                                for e in candidate.graph.edges))
                    for item in candidate.items:
                        self.assertGreater(math.dist(item.start_global,item.end_global), 1e-7)

    def test_link_left_authoritative_and_apex_retained(self):
        candidate = self.candidate(left_end_height=250., right_end_height=450., apex_position=.37)
        self.assertEqual(candidate.config["right_end_height"], 250.)
        self.assertEqual(paths(definition_from_config(candidate.config))["top"],
                         ((0.,250.,0.),(2220.,1200.,0.),(6000.,250.,0.)))

    def test_branch_lengths_slopes_and_persistence(self):
        candidate = self.candidate(left_end_height=100.,right_end_height=350.,
                                   link_end_heights=False,apex_position=.4)
        top = [i for i in candidate.items if i.role == "TOP_CHORD"]
        self.assertAlmostEqual(sum(math.dist(i.start_local,i.end_local) for i in top),
            math.hypot(2400.,1100.)+math.hypot(3600.,850.))
        slopes = [(i.end_local[1]-i.start_local[1])/(i.end_local[0]-i.start_local[0]) for i in top]
        self.assertAlmostEqual(max(slopes),1100/2400)
        self.assertAlmostEqual(min(slopes),-850/3600)
        restored=decode_state(encode_state(candidate,{i.key:i.key for i in candidate.items}))
        self.assertEqual(build_candidate(restored["candidate"]["config"]).graph,candidate.graph)

    def test_invalid_height_or_ridge_slope(self):
        for value in (-1.,math.nan,math.inf,1200.,1400.):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.candidate(left_end_height=value)
            with self.subTest(right=value), self.assertRaises(ValueError):
                self.candidate(right_end_height=value,link_end_heights=False)

    def test_support_intent_never_silently_disappears(self):
        from tests.test_truss_assemblies import config as physical_config
        c=physical_config()
        c.update(envelope_type="DuoPitch",connection_intents={"N_S_START":dict(form="Direct")})
        old=build_candidate(c)
        raised=build_candidate(dict(old.config,left_end_height=150.),old)
        self.assertEqual(raised.config["connection_intents"],old.config["connection_intents"])
        restored=build_candidate(dict(raised.config,left_end_height=0.),raised)
        self.assertEqual(restored.config["connection_intents"],old.config["connection_intents"])

    def test_upper_node_intent_cannot_be_deleted_on_merge(self):
        from tests.test_truss_assemblies import config as physical_config
        c=physical_config()
        c.update(envelope_type="DuoPitch",left_end_height=150.,
                 connection_intents={"T_S_START":dict(form="Direct")})
        raised=build_candidate(c)
        with self.assertRaisesRegex(ValueError,"ligações"):
            build_candidate(dict(raised.config,left_end_height=0.),raised)


if __name__ == "__main__":
    unittest.main()
