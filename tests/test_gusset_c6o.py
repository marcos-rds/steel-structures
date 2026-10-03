"""Focused C6-O conventional-outline and inward double-Ue regressions."""

import unittest

from freecad.SteelStructures.trusses.editing import materialize
from freecad.SteelStructures.trusses.models import TopologyGraph
from freecad.SteelStructures.trusses.realization import build_candidate
from tests.test_connections_c5b_polish import three_web_config
from tests.test_gusset_c6f import _outline
from tests.test_gusset_c6j import _production
from tests.test_gusset_c6n import (
    _overlap_corners, _point_segment_distance, assert_physical_outline,
)
from tests.test_gusset_ui_c6m import regions_for
from tests.test_ridge_fitting import ridge_config


class ConventionalOutlineTests(unittest.TestCase):
    def test_upper_two_diagonals_and_vertical_use_resolved_candidate_signature(self):
        outline = assert_physical_outline(self, ridge_config(.37, 1100.), "T_S_APEX")

        self.assertEqual(outline.points, (
            (-9.1793678118, 69.4869956325),
            (-149.4441501291, -104.2644239047),
            (-66.2883915694, -171.3937999057),
            (-44.7528915166, -177.1888071926),
            (15.6545370283, -177.1888071926),
            (105.4670997411, -152.4985172251),
            (171.3923245734, -61.8812990922),
        ))
        self.assertEqual(
            tuple(edge.kind for edge in outline.semantic_edges),
            ("CHORD_BOUNDARY", "FREE_MARGIN", "WEB_END_CAP", "WEB_END_CAP",
             "WEB_END_CAP", "FREE_MARGIN", "CHORD_BOUNDARY"))

    def test_two_diagonals_and_vertical_use_resolved_candidate_signature(self):
        value, node = three_web_config()
        outline = assert_physical_outline(self, value, node)

        self.assertEqual(outline.points, (
            (175.0, -50.79),
            (175.0, 80.4886114324),
            (64.7367133377, 175.0),
            (-64.7367133377, 175.0),
            (-175.0, 80.4886114324),
            (-175.0, -50.79),
        ))
        self.assertEqual(
            tuple(edge.kind for edge in outline.semantic_edges),
            ("FREE_MARGIN", "WEB_END_CAP", "WEB_END_CAP", "WEB_END_CAP",
             "FREE_MARGIN", "CHORD_BOUNDARY"))
        for point in _overlap_corners(value, node):
            distance = min(_point_segment_distance(point, edge.start, edge.end)
                           for edge in outline.semantic_edges)
            self.assertGreaterEqual(distance, 25.-1e-6)

    def test_diagonal_and_vertical_use_direct_cap_transition(self):
        value, node = three_web_config()
        base = build_candidate(value)
        diagonal = next(edge for edge in base.graph.edges
                        if edge.role == "DIAGONAL"
                        and node in (edge.start_node_key, edge.end_node_key))
        graph = TopologyGraph(base.graph.nodes, tuple(
            edge for edge in base.graph.edges if edge.key != diagonal.key))
        value.update(topology_mode="Custom", topology_preset="Custom",
                     base_preset="Pratt",
                     custom_topology=materialize(graph, base.config))

        outline = _outline(value, node)
        kinds = tuple(edge.kind for edge in outline.semantic_edges)
        self.assertEqual(len(outline.points), 5)
        self.assertEqual(kinds.count("WEB_END_CAP"), 2)
        self.assertNotIn("WEB_SECTOR_BRIDGE", kinds)
        for point in _overlap_corners(value, node):
            distance = min(_point_segment_distance(point, edge.start, edge.end)
                           for edge in outline.semantic_edges)
            self.assertGreaterEqual(distance, 25.-1e-6)

    def test_duopitch_diagonal_and_vertical_use_direct_cap_transition(self):
        outline = _outline(ridge_config(.37, 1100.), "T_S_LEFT_1_3")
        kinds = tuple(edge.kind for edge in outline.semantic_edges)
        self.assertEqual(len(outline.points), 5)
        self.assertNotIn("WEB_SECTOR_BRIDGE", kinds)
        self.assertEqual(kinds.count("WEB_END_CAP"), 2)


class InwardDoubleChannelTests(unittest.TestCase):
    def test_inner_surface_lateral_gap_is_not_offered_as_component_face(self):
        outline = _production(
            "Ue 150 × 60 × 20 × 3,00", assembly="DoubleChannelInward")
        regions = regions_for(outline)
        component_regions = [value for value in regions
                             if value[0] in ("component_internal_a",
                                             "component_internal_b")]

        self.assertEqual(len(component_regions), 2)
        self.assertEqual(
            {value.participant_key for value in outline.attachment.residuals},
            set(outline.spec.participant_keys))
        for _region, _label, positions in component_regions:
            self.assertNotIn("Face interna",
                             tuple(label for _key, label in positions))
            self.assertTrue(all(label.startswith("Apoio ")
                                for _key, label in positions))
        gaps = [candidate for candidate in outline.attachment.candidates
                if candidate.accessibility.value == "AssemblyGap"]
        self.assertEqual(tuple(candidate.placement.value for candidate in gaps),
                         ("Center",))


if __name__ == "__main__":
    unittest.main()
