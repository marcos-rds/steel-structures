"""Focused C6-D semantic outline regularization tests."""

import math
import unittest
from types import SimpleNamespace

from freecad.SteelStructures.connections import (
    GussetCorridor, GussetPlateFrame, GussetPlateSpec, GussetSupportLine,
    build_gusset_outline, semantic_outline_regularization,
)
from freecad.SteelStructures.trusses.gussets import _web_end_lines


FRAME = GussetPlateFrame((0., 0., 0.), (1., 0., 0.),
                         (0., 1., 0.), (0., 0., 1.))


def _spec():
    return GussetPlateSpec(
        "N:gusset-plate", "N", 8., edge_margin=25., member_overlap=150.,
        participant_keys=("chord", "web"), component_keys=("A",), frame=FRAME)


def _edge_on(points, support, tolerance=2e-6):
    result = []
    for first, second in zip(points, points[1:]+points[:1]):
        distances = tuple(support.normal[0]*point[0]
                          +support.normal[1]*point[1]-support.offset
                          for point in (first, second))
        if max(abs(value) for value in distances) <= tolerance:
            result.append((first, second))
    return result


class SemanticOutlineTests(unittest.TestCase):
    def test_terminal_web_has_one_perpendicular_end_cap(self):
        participants = (
            SimpleNamespace(participant_key="chord", role="BOTTOM_CHORD", end="Through"),
            SimpleNamespace(participant_key="web", role="DIAGONAL", end="End"),
        )
        corridors = (
            GussetCorridor("chord", "chord:A", (1., 0.), -20., 20.),
            GussetCorridor("web", "web:A", (0., 1.), -10., 10.),
        )
        caps = _web_end_lines(participants, corridors, _spec())
        self.assertEqual(len(caps), 1)
        self.assertEqual(caps[0].kind, "WEB_END_CAP")
        self.assertEqual(caps[0].normal, (0., 1.))
        self.assertAlmostEqual(caps[0].offset, 175.)
        chord = GussetSupportLine(
            "chord", (1., 0.), (0., -1.), 20., "CHORD_BOUNDARY")
        outline = build_gusset_outline(_spec(), corridors, (chord,)+caps)
        edges = _edge_on(outline.points, caps[0])
        self.assertEqual(len(edges), 1)
        edge = (edges[0][1][0]-edges[0][0][0], edges[0][1][1]-edges[0][0][1])
        self.assertAlmostEqual(edge[0]*caps[0].normal[0]
                               +edge[1]*caps[0].normal[1], 0.)

    def test_through_participant_is_not_artificially_terminated(self):
        participants = (
            SimpleNamespace(participant_key="through", role="VERTICAL", end="Through"),
            SimpleNamespace(participant_key="web", role="DIAGONAL", end="End"),
        )
        corridors = (
            GussetCorridor("through", "through:A", (0., 1.), -10., 10.),
            GussetCorridor("through", "through:A", (0., -1.), -10., 10.),
            GussetCorridor("web", "web:A", (1., 1.), -8., 8.),
        )
        caps = _web_end_lines(participants, corridors, _spec())
        self.assertNotIn("through", {value.participant_key for value in caps})
        self.assertLessEqual(sum(value.participant_key == "web" for value in caps), 1)

    def test_two_short_free_chamfers_collapse_to_direct_corner(self):
        points = ((0., 0.), (10., 0.), (10., 8.8),
                  (9.8, 9.5), (9.2, 10.), (0., 10.))
        result = semantic_outline_regularization(points)
        self.assertEqual(len(result), 4)
        self.assertEqual(set(result), {(0., 0.), (10., 0.), (10., 10.), (0., 10.)})
        for previous, point, following in zip(result[-1:]+result[:-1], result,
                                               result[1:]+result[:1]):
            incoming = (point[0]-previous[0], point[1]-previous[1])
            outgoing = (following[0]-point[0], following[1]-point[1])
            self.assertAlmostEqual(incoming[0]*outgoing[0]
                                   +incoming[1]*outgoing[1], 0.)

    def test_semantic_chamfer_is_preserved(self):
        points = ((0., 0.), (10., 0.), (10., 9.), (9., 10.), (0., 10.))
        root = math.sqrt(2.)
        support = GussetSupportLine(
            "web", (-1./root, 1./root), (1./root, 1./root),
            19./root, "WEB_END_CAP")
        result = semantic_outline_regularization(points, (support,))
        self.assertEqual(result, points)
        self.assertEqual(len(_edge_on(result, support)), 1)

    def test_nearly_parallel_neighbours_cannot_create_a_remote_spike(self):
        points = ((0., 0.), (100., 0.), (100., 1.), (0., .9))
        result = semantic_outline_regularization(points)
        self.assertLessEqual(max(math.hypot(*point) for point in result),
                             max(math.hypot(*point) for point in points)+1e-7)
        self.assertLessEqual(abs(sum(a[0]*b[1]-a[1]*b[0]
                                     for a, b in zip(result, result[1:]+result[:1]))),
                             2.*100.)

    def test_chord_and_web_support_priority_remains_geometric(self):
        spec = _spec()
        corridors = (
            GussetCorridor("chord", "chord:A", (1., 0.), -20., 20.),
            GussetCorridor("web", "web:A", (1., 1.), -8., 8.),
        )
        participants = (
            SimpleNamespace(participant_key="chord", role="BOTTOM_CHORD", end="Through"),
            SimpleNamespace(participant_key="web", role="DIAGONAL", end="End"),
        )
        chord = GussetSupportLine(
            "chord", (1., 0.), (0., -1.), 20., "CHORD_BOUNDARY")
        caps = _web_end_lines(participants, corridors, spec)
        outline = build_gusset_outline(spec, corridors, (chord,)+caps)
        self.assertEqual(len(_edge_on(outline.points, chord)), 1)
        for cap in caps:
            self.assertEqual(len(_edge_on(outline.points, cap)), 1)
        self.assertGreater(outline.area, 0.)
        self.assertTrue(all(math.hypot(second[0]-first[0], second[1]-first[1]) > 1e-5
                            for first, second in zip(
                                outline.points, outline.points[1:]+outline.points[:1])))


if __name__ == "__main__":
    unittest.main()
