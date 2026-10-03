"""Focused C6-N compact multi-web outline and contextual UI regressions."""

import math
import unittest

from freecad.SteelStructures.trusses.connections import connection_participants
from freecad.SteelStructures.trusses.editing import materialize
from freecad.SteelStructures.trusses.gussets import _corridors
from freecad.SteelStructures.trusses.models import TopologyGraph
from freecad.SteelStructures.trusses.realization import build_candidate, reference_frame
from tests.test_connections_c5b_polish import three_web_config
from tests.test_gusset_c6f import _outline
from tests.test_gusset_c6j import _chord_candidates, _production
from tests.test_gusset_plate_c6a import configured
from tests.test_gusset_ui_c6m import regions_for
from tests.test_gusset_families_round1 import compute
from tests.test_gusset_w_c6q import choice, physical_extrusion
from freecad.SteelStructures.connections import gusset_families
from tests.test_ridge_fitting import ridge_config


CHORD_ROLES = {"TOP_CHORD", "BOTTOM_CHORD"}


def assert_physical_outline(test, value, node):
    """Validate physical requirements and the same candidate in manual mode.

    C6-Q removed the automatic-only compact contour: both paths must use
    the resolved candidate's C6-L outline_band, including exposed margins.
    """
    _candidate, captured, outlines, diagnostics = compute(configured(value, node))
    test.assertFalse(diagnostics)
    outline = outlines[node]
    gusset_families.validate_family(
        outline.points, gusset_families.requirements(*captured[node]))
    manual = _outline(value, node, transverse_placement=choice(outline).stable_key)
    test.assertEqual(outline.attachment, manual.attachment)
    test.assertEqual(outline.points, manual.points)
    test.assertEqual(outline.semantic_edges, manual.semantic_edges)
    test.assertEqual(physical_extrusion(outline), physical_extrusion(manual))
    return outline


def _point_segment_distance(point, start, end):
    dx, dy = end[0]-start[0], end[1]-start[1]
    length2 = dx*dx+dy*dy
    parameter = max(0., min(1., ((point[0]-start[0])*dx
                                 +(point[1]-start[1])*dy)/length2))
    return math.hypot(point[0]-start[0]-parameter*dx,
                      point[1]-start[1]-parameter*dy)


def _overlap_corners(value, node, overlap=150.):
    candidate = build_candidate(configured(value, node))
    frame = reference_frame(candidate.config)
    participants = connection_participants(candidate, node)
    runs = {run.key: run for run in candidate.runs}
    result = []
    for participant in participants:
        if participant.role in CHORD_ROLES:
            continue
        for run_key in participant.physical_run_keys:
            for corridor in _corridors(candidate, participant, runs[run_key], frame):
                length = math.hypot(*corridor.direction)
                direction = (corridor.direction[0]/length,
                             corridor.direction[1]/length)
                perpendicular = (-direction[1], direction[0])
                result.extend((
                    overlap*direction[0]+transverse*perpendicular[0],
                    overlap*direction[1]+transverse*perpendicular[1])
                    for transverse in (corridor.transverse_low,
                                       corridor.transverse_high))
    return tuple(result)


class MultiWebOutlineTests(unittest.TestCase):
    def test_two_diagonals_gain_exposed_sides_without_losing_chord_contact(self):
        value, node = three_web_config()
        base = build_candidate(value)
        graph = TopologyGraph(base.graph.nodes, tuple(
            edge for edge in base.graph.edges
            if not (edge.role == "VERTICAL"
                    and node in (edge.start_node_key, edge.end_node_key))))
        value.update(topology_mode="Custom", topology_preset="Custom",
                     base_preset="Pratt",
                     custom_topology=materialize(graph, base.config))
        outline = _outline(value, node)
        kinds = [edge.kind for edge in outline.semantic_edges]
        self.assertEqual(len(outline.points), 6)
        self.assertEqual(kinds.count("FREE_MARGIN"), 2)
        self.assertEqual(kinds.count("WEB_END_CAP"), 2)
        self.assertEqual(kinds.count("WEB_SECTOR_BRIDGE"), 1)
        self.assertEqual(kinds.count("CHORD_BOUNDARY"), 1)

    def test_two_diagonals_and_vertical_keep_physical_candidate_envelope(self):
        value, node = three_web_config()
        outline = assert_physical_outline(self, value, node)
        kinds = [edge.kind for edge in outline.semantic_edges]

        self.assertEqual(len(outline.points), 6)
        self.assertEqual(kinds.count("WEB_END_CAP"), 3)
        self.assertEqual(kinds.count("FREE_MARGIN"), 2)
        self.assertEqual(kinds.count("CHORD_BOUNDARY"), 1)
        self.assertAlmostEqual(outline.area, 68605.3636695187, places=6)
        self.assertTrue(all(math.dist(edge.start, edge.end) > 70.
                            for edge in outline.semantic_edges
                            if edge.kind == "WEB_END_CAP"))

        for point in _overlap_corners(value, node):
            distance = min(_point_segment_distance(point, edge.start, edge.end)
                           for edge in outline.semantic_edges)
            self.assertGreaterEqual(distance, 25.-1e-6)

    def test_asymmetric_apex_keeps_physical_candidate_cap_envelope(self):
        outline = assert_physical_outline(self, ridge_config(.37, 1100.), "T_S_APEX")
        caps = [edge for edge in outline.semantic_edges
                if edge.kind == "WEB_END_CAP"]
        self.assertEqual(len(outline.points), 7)
        self.assertEqual(sum(edge.kind == "FREE_MARGIN"
                             for edge in outline.semantic_edges), 2)
        self.assertEqual(len(caps), 3)
        # Cap length is not the edge-margin requirement. Coverage/margins
        # are checked above; the first active cap is legitimately < 25 mm.
        for edge, length in zip(caps, (22.301566581282422, 60.4074285449,
                                      93.14454809445299)):
            self.assertAlmostEqual(math.dist(edge.start, edge.end), length, places=6)
        self.assertEqual(sum(edge.kind == "CHORD_BOUNDARY"
                             for edge in outline.semantic_edges), 2)

    def test_diagonal_vertical_uses_physical_candidate_with_direct_caps(self):
        outline = assert_physical_outline(self, ridge_config(.37, 1100.), "T_S_LEFT_1_3")
        self.assertEqual(sum(edge.kind == "WEB_END_CAP"
                             for edge in outline.semantic_edges), 2)
        self.assertEqual(sum(edge.kind == "WEB_SECTOR_BRIDGE"
                             for edge in outline.semantic_edges), 0)
        self.assertEqual(len(outline.points), 5)
        self.assertAlmostEqual(outline.area, 39829.703810723564, places=6)

    def test_explicit_external_ue_still_reaches_its_c6l_chord_boundary(self):
        base = _production("Ue 150 × 60 × 20 × 3,00")
        for candidate in _chord_candidates(base, "OuterExposed"):
            with self.subTest(placement=candidate.placement.value):
                outline = _production(
                    "Ue 150 × 60 × 20 × 3,00",
                    placement=candidate.stable_key)
                self.assertIn("CHORD_BOUNDARY",
                              {edge.kind for edge in outline.semantic_edges})
                self.assertAlmostEqual(candidate.outline_band,
                                       -candidate.contact_band, places=6)


class ContextualCandidateTests(unittest.TestCase):
    def test_simple_ue_keeps_three_main_internal_positions(self):
        regions = regions_for(_production("Ue 150 × 60 × 20 × 3,00"))
        self.assertEqual(tuple(label for _key, label, _positions in regions),
                         ("Externa", "Interna"))
        self.assertEqual(tuple(label for _key, label in regions[1][2]),
                         ("Lado A", "Central", "Lado B"))

    def test_rotated_ue_reserves_stiffener_groups_for_additional_positions(self):
        regions = regions_for(_production(
            "Ue 150 × 60 × 20 × 3,00", rotation=90.))
        self.assertEqual(tuple(label for _key, label, _positions in regions),
                         ("Externa", "Interna", "Enrijecedor A",
                          "Enrijecedor B"))
        self.assertEqual(tuple(label for _key, label in regions[1][2]),
                         ("Lado A", "Central", "Lado B"))

    def test_double_angle_uses_angle_names_not_stiffener_names(self):
        regions = regions_for(_production("L 40 x 4", assembly="DoubleAngle"))
        self.assertEqual(tuple(label for _key, label, _positions in regions),
                         ("Externa", "Entre componentes",
                          "Cantoneira A", "Cantoneira B"))
        for _key, label, positions in regions[2:]:
            self.assertNotIn("Enrijecedor", label)
            self.assertEqual(tuple(value for _stable, value in positions),
                             ("Face interna", "Face externa"))

    def test_inward_double_ue_separates_gap_from_component_interiors(self):
        regions = regions_for(_production(
            "Ue 150 × 60 × 20 × 3,00", assembly="DoubleChannelInward"))
        self.assertEqual(tuple(label for _key, label, _positions in regions),
                         ("Externa", "Entre componentes",
                          "Interna — componente A", "Interna — componente B"))
        between = regions[1][2]
        self.assertEqual(tuple(label for _key, label in between), ("Central",))
        visible = [key for _region, _label, positions in regions
                   for key, _position in positions]
        self.assertEqual(len(visible), len(set(visible)))


if __name__ == "__main__":
    unittest.main()
