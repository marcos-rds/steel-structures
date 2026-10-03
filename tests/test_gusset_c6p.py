"""Post-validation C6-O regressions distilled from testeC6.FCStd."""

import copy
import unittest

from freecad.SteelStructures.trusses.connections import connection_participants
from freecad.SteelStructures.trusses.editing import materialize
from freecad.SteelStructures.trusses.gussets import preliminary_gusset_outlines
from freecad.SteelStructures.trusses.models import TopologyGraph, TopologyNode
from freecad.SteelStructures.trusses.realization import build_candidate
from freecad.SteelStructures.trusses.serialization import decode_state, encode_state
from tests.test_gusset_c6f import _outline
from tests.test_gusset_c6n import _overlap_corners, _point_segment_distance
from tests.test_truss_assemblies import config


def real_config(envelope, preset):
    """Minimal persisted parameters shared by the investigated real trusses."""
    value = config()
    value.update(
        envelope_type=envelope, span=10000., height=2000., apex_position=.5,
        panel_count=6, left_panels=None, right_panels=None,
        start=[0., 0., 0.], end=[10000., 0., 0.],
        topology_preset=preset, top_continuity="Continuous",
        bottom_continuity="Continuous",
    )
    value["role_specs"]["TOP_CHORD"]["rotation"] = -90.
    value["role_specs"]["BOTTOM_CHORD"]["rotation"] = 90.
    value["role_specs"]["END_POST_LEFT"]["rotation"] = 180.
    for role, spec in value["role_specs"].items():
        spec["physical_fit"] = (
            "None" if role in ("TOP_CHORD", "BOTTOM_CHORD") else "ToChord")
    return value


def real_outline(value, node):
    probe = _outline(value, node, chord_contact="TrussInterior")
    selected = next(
        candidate for candidate in probe.attachment.candidates
        if candidate.governing_participant_key
        == probe.attachment.governing_participant_key
        and candidate.accessibility.value == "OuterExposed"
        and candidate.placement.value == "NearA")
    return _outline(value, node, chord_contact="TrussInterior",
                    transverse_placement=selected.stable_key)


class RealOutlineTests(unittest.TestCase):
    def assert_overlap_margin(self, value, node, outline):
        for point in _overlap_corners(value, node):
            distance = min(_point_segment_distance(
                point, edge.start, edge.end) for edge in outline.semantic_edges)
            self.assertGreaterEqual(distance, 25.-1e-6)

    def test_parallel_pratt_simple_nodes_use_approved_l_signatures(self):
        value = real_config("Parallel", "Pratt")
        expected = {
            "T_S_MAIN_1_3": (
                (-53.5, -175.0), (63.3587386567, -175.0),
                (142.9219664182, -108.6973101988),
                (142.9219664182, 11.59), (-53.5, 11.59)),
            "B_S_MAIN_1_6": (
                (-129.862204665, -11.59), (36.5, -11.59),
                (36.5, 175.0), (-63.3587386567, 175.0),
                (-129.862204665, 119.5804449931)),
        }
        for node, points in expected.items():
            with self.subTest(node=node):
                outline = real_outline(value, node)
                self.assertEqual(outline.points, points)
                self.assert_overlap_margin(value, node, outline)

    def test_parallel_warren_verticals_approved_fan_is_unchanged(self):
        value = real_config("Parallel", "WarrenVerticals")
        expected = {
            "B_S_MAIN_1_3": (
                (175.0, -11.59), (175.0, 81.9656155473),
                (63.3587386567, 175.0), (-63.3587386567, 175.0),
                (-175.0, 81.9656155473), (-175.0, -11.59)),
            "T_S_MAIN_1_2": (
                (63.3587386567, -175.0), (175.0, -81.9656155472),
                (175.0, 11.59), (-175.0, 11.59),
                (-175.0, -81.9656155472), (-63.3587386567, -175.0)),
        }
        for node, points in expected.items():
            with self.subTest(node=node):
                self.assertEqual(real_outline(value, node).points, points)

    def test_parallel_warren_terminal_nodes_keep_physical_boundaries(self):
        value = real_config("Parallel", "Warren")
        expected = {
            "B_S_START": (
                (0.0, -11.59), (129.862204665, -11.59),
                (129.862204665, 119.5804449931), (63.3587386567, 175.0),
                (-0.0, 175.0)),
            "B_S_END": (
                (-129.862204665, -11.59), (0.0, -11.59),
                (0.0, 175.0), (-63.3587386567, 175.0),
                (-129.862204665, 119.5804449931)),
        }
        for node, points in expected.items():
            with self.subTest(node=node):
                self.assertEqual(real_outline(value, node).points, points)

    def test_duopitch_simple_nodes_end_with_direct_caps(self):
        cases = {
            "Warren": ("T_S_LEFT_1_3",),
            "WarrenVerticals": ("T_S_LEFT_1_3",),
            "QueenPost": ("T_S_LEFT_2_3", "T_S_RIGHT_1_3"),
        }
        for preset, nodes in cases.items():
            value = real_config("DuoPitch", preset)
            for node in nodes:
                with self.subTest(preset=preset, node=node):
                    outline = real_outline(value, node)
                    kinds = tuple(edge.kind for edge in outline.semantic_edges)
                    # Approved L gives four faces when QueenPost's nominal
                    # diagonal is horizontal; both physical caps remain.
                    self.assertEqual(len(outline.points), 4 if preset == "QueenPost" else 5)
                    self.assertEqual(kinds.count("WEB_END_CAP"), 2)
                    self.assertNotIn("WEB_SECTOR_BRIDGE", kinds)
                    self.assertEqual(min(point[1] for point in outline.points),
                                     -175.)
                    self.assert_overlap_margin(value, node, outline)

    def test_warren_apex_gains_straight_lower_edge_only_without_vertical(self):
        warren = real_outline(real_config("DuoPitch", "Warren"), "T_S_APEX")
        vertical = real_outline(
            real_config("DuoPitch", "WarrenVerticals"), "T_S_APEX")
        bridge = next(edge for edge in warren.semantic_edges
                      if edge.kind == "WEB_SECTOR_BRIDGE")
        self.assertAlmostEqual(bridge.start[1], bridge.end[1], places=7)
        self.assertEqual((bridge.start[1], bridge.end[1]),
                         (-147.5953125357, -147.5953125357))
        self.assertNotIn("WEB_SECTOR_BRIDGE",
                         {edge.kind for edge in vertical.semantic_edges})
        self.assertEqual(vertical.points, (
            (63.3587386568, -175.0),
            (146.0417830462, -106.0974630087),
            (166.7878388439, -54.2323235146),
            (0.0, 12.4828120229),
            (-166.7878388439, -54.2323235146),
            (-146.0417830462, -106.0974630087),
            (-63.3587386568, -175.0),
        ))


class TopologyIntentCleanupTests(unittest.TestCase):
    @staticmethod
    def participant_signature(candidate, node):
        return tuple(sorted((participant.role, participant.end,
                             tuple(sorted(participant.physical_run_keys)))
                            for participant in connection_participants(
                                candidate, node)))

    def test_changed_participants_keep_valid_intent_and_new_candidate_edit(self):
        value = real_config("Parallel", "WarrenVerticals")
        value["connection_intents"] = {
            "B_S_MAIN_1_3": {"form": "Gusset", "gusset": {
                "plate_thickness": 10., "edge_margin": 25.,
                "member_overlap": 150.}},
        }
        accepted = build_candidate(value)
        changed = copy.deepcopy(accepted.config)
        changed["topology_preset"] = "Pratt"
        changed["connection_intents"]["T_S_MAIN_1_3"] = {
            "form": "Direct", "direct_policy": "Independent"}
        candidate = build_candidate(changed, accepted)

        self.assertEqual(candidate.config["connection_intents"]["B_S_MAIN_1_3"],
                         accepted.config["connection_intents"]["B_S_MAIN_1_3"])
        self.assertIn("T_S_MAIN_1_3", candidate.config["connection_intents"])
        self.assertNotEqual(
            self.participant_signature(accepted, "B_S_MAIN_1_3"),
            self.participant_signature(candidate, "B_S_MAIN_1_3"))

        returned = copy.deepcopy(candidate.config)
        returned["topology_preset"] = "WarrenVerticals"
        restored = build_candidate(returned, candidate)
        self.assertIn("T_S_MAIN_1_3", restored.config["connection_intents"])
        self.assertIn("B_S_MAIN_1_3", restored.config["connection_intents"])

    def test_unrelated_custom_topology_change_preserves_compatible_intent(self):
        value = real_config("Parallel", "WarrenVerticals")
        value["connection_intents"] = {
            "B_S_MAIN_1_3": {"form": "Direct",
                              "direct_policy": "Independent"}}
        accepted = build_candidate(value)
        isolated = TopologyNode("N_MANUAL_C6P", (5100., 500., 0.), (),
                                "INTERNAL_NODE")
        graph = TopologyGraph(accepted.graph.nodes+(isolated,),
                              accepted.graph.edges)
        changed = copy.deepcopy(accepted.config)
        changed.update(topology_mode="Custom", topology_preset="Custom",
                       base_preset="WarrenVerticals",
                       custom_topology=materialize(graph, accepted.config))
        candidate = build_candidate(changed, accepted)

        self.assertEqual(candidate.config["connection_intents"],
                         accepted.config["connection_intents"])
        restored = build_candidate(
            decode_state(encode_state(candidate))["candidate"]["config"])
        self.assertEqual(candidate.config["connection_intents"],
                         restored.config["connection_intents"])
        self.assertEqual(candidate.graph.node("B_S_MAIN_1_3").key,
                         "B_S_MAIN_1_3")

    def test_disappeared_node_is_removed_without_removing_automatic_fit(self):
        value = real_config("Parallel", "Pratt")
        value["connection_intents"] = {
            "B_S_MAIN_1_6": {"form": "Gusset", "gusset": {
                "plate_thickness": 10., "edge_margin": 25.,
                "member_overlap": 150.}},
        }
        accepted = build_candidate(value)
        changed = copy.deepcopy(accepted.config)
        changed["panel_count"] = 4
        candidate = build_candidate(changed, accepted)

        self.assertNotIn("B_S_MAIN_1_6",
                         {node.key for node in candidate.graph.nodes})
        self.assertFalse(candidate.config["connection_intents"])
        outlines, diagnostics = preliminary_gusset_outlines(candidate)
        self.assertEqual(outlines, ())
        self.assertEqual(diagnostics, ())
        web_items = [item for item in candidate.items
                     if item.role in ("DIAGONAL", "VERTICAL", "END_POST")]
        self.assertTrue(any(
            action.get("source") == "AutoFit"
            for item in web_items
            for action in ((item.physical_fit_plan or {}).get("start_action"),
                           (item.physical_fit_plan or {}).get("end_action"))
            if action))

    def test_dimensional_recompute_does_not_clean_compatible_intent(self):
        value = real_config("DuoPitch", "WarrenVerticals")
        value["connection_intents"] = {
            "T_S_LEFT_1_3": {"form": "Direct",
                              "direct_policy": "Independent"}}
        accepted = build_candidate(value)
        changed = copy.deepcopy(accepted.config)
        changed["height"] = 2150.
        candidate = build_candidate(changed, accepted)

        self.assertEqual(candidate.config["connection_intents"],
                         accepted.config["connection_intents"])


if __name__ == "__main__":
    unittest.main()
