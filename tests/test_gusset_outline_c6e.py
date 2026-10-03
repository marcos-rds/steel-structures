"""Focused C6-E single semantic WEB_END_CAP regression tests."""

import math
import unittest
from dataclasses import asdict
from unittest.mock import patch

from freecad.SteelStructures import profile_catalog
from freecad.SteelStructures.trusses.connections import connection_participants
from freecad.SteelStructures.trusses.gussets import preliminary_gusset_outlines
from freecad.SteelStructures.trusses.realization import build_candidate
from tests.test_connections_c5b_polish import three_web_config
from tests.test_connections_c5b_through import k_config
from tests.test_gusset_plate_c6a import configured
from tests.test_gusset_c6n import assert_physical_outline
from tests.test_ridge_fitting import ridge_config


def _outline(value, node):
    candidate = build_candidate(configured(value, node))
    outlines, diagnostics = preliminary_gusset_outlines(candidate)
    if diagnostics:
        raise AssertionError([item.message for item in diagnostics])
    return candidate, next(item for item in outlines if item.spec.node_key == node)


class SingleWebEndCapTests(unittest.TestCase):
    def assert_single_caps(self, candidate, node, outline):
        participants = connection_participants(candidate, node)
        terminal_webs = {item.participant_key: item for item in participants
                        if item.role not in ("TOP_CHORD", "BOTTOM_CHORD")
                        and item.end != "Through"}
        caps = [edge for edge in outline.semantic_edges
                if edge.kind == "WEB_END_CAP"]
        by_participant = {}
        for edge in caps:
            by_participant.setdefault(edge.participant_key, []).append(edge)
        self.assertEqual(set(by_participant), set(terminal_webs))
        self.assertTrue(all(len(values) == 1 for values in by_participant.values()))
        through = {item.participant_key for item in participants if item.end == "Through"}
        self.assertFalse(through.intersection(by_participant))
        self.assertTrue(all(
            math.hypot(edge.end[0]-edge.start[0], edge.end[1]-edge.start[1]) > 1e-5
            for edge in caps))
        self.assertEqual(len(outline.semantic_edges), len(outline.points))
        self.assertTrue(all(edge.kind in {
            "CHORD_BOUNDARY", "WEB_END_CAP", "REQUIRED_CORRIDOR", "FREE_MARGIN"}
                            for edge in outline.semantic_edges))

    def test_pratt_warren_style_node_has_one_cap_per_terminal_web(self):
        value, node = three_web_config()
        candidate, outline = _outline(value, node)
        self.assert_single_caps(candidate, node, outline)
        self.assertEqual(sum(edge.kind == "WEB_END_CAP"
                             for edge in outline.semantic_edges), 3)
        self.assertLessEqual(len(outline.points), 6)

    def test_wide_hp_webs_keep_their_single_active_caps(self):
        value, node = three_web_config()
        value["role_specs"]["DIAGONAL"]["profile_ref"] = asdict(
            profile_catalog.ref_for_designation("HP 310 x 132,0"))
        candidate = build_candidate(configured(value, node))
        outlines, diagnostics = preliminary_gusset_outlines(candidate)
        outline = next(item for item in outlines if item.spec.node_key == node)
        self.assertFalse(diagnostics)
        self.assertEqual(outline, assert_physical_outline(self, value, node))
        # With the resolved outline_band there is no sharp local tip to reject.
        # The approved family keeps the complete envelope and its active caps.
        with patch('freecad.SteelStructures.trusses.gussets.apply_approved_family',
                   side_effect=lambda spec,parts,corridors,supports,legacy:(legacy,"")):
            original, original_diagnostics = preliminary_gusset_outlines(candidate)
        self.assertFalse(original_diagnostics)
        original = next(item for item in original if item.spec.node_key == node)
        self.assertEqual(outline,original)
        self.assert_single_caps(candidate, node, outline)
        self.assertEqual(sum(edge.kind == "WEB_END_CAP"
                             for edge in outline.semantic_edges), 3)

    def test_k_does_not_cap_through_and_caps_each_terminal_once(self):
        value, node = k_config(False)
        candidate, outline = _outline(value, node)
        self.assert_single_caps(candidate, node, outline)
        self.assertEqual(sum(edge.kind == "WEB_END_CAP"
                             for edge in outline.semantic_edges), 2)

    def test_duopitch_ridge_has_one_cap_per_web_without_residual_chamfers(self):
        for apex in (.5, .37):
            with self.subTest(apex=apex):
                value = ridge_config(apex, 1100., inclined=apex != .5)
                candidate, outline = _outline(value, "T_S_APEX")
                self.assertEqual(outline, assert_physical_outline(self, value, "T_S_APEX"))
                self.assert_single_caps(candidate, "T_S_APEX", outline)
                self.assertEqual(sum(edge.kind == "WEB_END_CAP"
                                     for edge in outline.semantic_edges), 3)
                self.assertEqual(len(outline.points), 7)
                self.assertEqual(sum(edge.kind == "FREE_MARGIN"
                                     for edge in outline.semantic_edges), 2)
                self.assertEqual(sum(edge.kind == "CHORD_BOUNDARY"
                                     for edge in outline.semantic_edges), 2)


if __name__ == "__main__":
    unittest.main()
