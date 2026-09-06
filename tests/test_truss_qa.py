"""Independent C1 adversarial checks: graph, physical runs and persistence.

Expected incidences below are defined independently of the preset generator.
This module does not import FreeCAD, Part or Qt.
"""
import copy
import json
import math
import unittest
from collections import Counter

from freecad.SteelStructures.trusses.models import (
    CONTINUITIES, ROLES, TopologyEdge, TopologyGraph, TopologyNode,
)
from freecad.SteelStructures.trusses.realization import (
    build_candidate, plan_regeneration, structural_signature,
)
from freecad.SteelStructures.trusses.serialization import (
    decode_state, dumps, encode_state,
)
from freecad.SteelStructures.trusses.validation import validate_graph


def config(**changes):
    result = {
        "envelope_type": "Parallel", "span": 6000.0, "height": 1200.0,
        "apex_position": 0.5, "panel_count": 6, "topology_preset": "Warren",
        "top_continuity": "Continuous", "bottom_continuity": "Continuous",
        "start": [0.0, 0.0, 0.0], "end": [6000.0, 0.0, 0.0],
        "plane_normal": [0.0, 0.0, 1.0],
        "role_specs": {role: {
            "profile_ref": {"catalog_id": "qa_catalog", "profile_id": "qa_section"},
            "insertion": "centroid", "rotation": 0.0,
            "section_geometry_mode": "Detailed", "color": [0.4, 0.5, 0.6],
            "assembly": "Single", "physical_fit": "None",
        } for role in ROLES},
    }
    result.update(changes)
    return result


def station_nodes(candidate):
    result = []
    for station in candidate.stations.stations:
        row = [n for n in candidate.graph.nodes if n.optional_station_key == station.key]
        bottom = next(n for n in row if "BOTTOM_CHORD" in n.affiliations)
        top = next(n for n in row if "TOP_CHORD" in n.affiliations)
        result.append((bottom.key, top.key))
    return result


def directed_role_edges(candidate, role):
    return {(e.start_node_key, e.end_node_key) for e in candidate.graph.edges if e.role == role}


class TrussPureIndependentTests(unittest.TestCase):
    def assert_graph_and_runs(self, candidate):
        graph = candidate.graph
        self.assertEqual(validate_graph(graph), ((), ()))
        self.assertEqual(len({n.key for n in graph.nodes}), len(graph.nodes))
        self.assertEqual(len({e.key for e in graph.edges}), len(graph.edges))
        unordered = {frozenset((e.start_node_key, e.end_node_key)) for e in graph.edges}
        self.assertEqual(len(unordered), len(graph.edges))
        for node in graph.nodes:
            self.assertEqual(node.position_local[2], 0.0)
            self.assertTrue(all(math.isfinite(v) for v in node.position_local))
            self.assertTrue(graph.incidence[node.key])
        coverage = Counter(key for run in candidate.runs for key in run.edge_keys)
        self.assertEqual(coverage, Counter({edge.key: 1 for edge in graph.edges}))
        self.assertEqual({run.key for run in candidate.runs}, {item.key for item in candidate.items})
        for run in candidate.runs:
            edges = [graph.edge(key) for key in run.edge_keys]
            self.assertEqual(edges[0].start_node_key, run.start_node_key)
            self.assertEqual(edges[-1].end_node_key, run.end_node_key)
            self.assertTrue(all(a.end_node_key == b.start_node_key for a, b in zip(edges, edges[1:])))
            start = graph.node(run.start_node_key).position_local
            end = graph.node(run.end_node_key).position_local
            self.assertGreater(math.dist(start, end), 1e-7)
            # Every intermediate logical node must lie on this physical segment.
            for edge in edges:
                point = graph.node(edge.end_node_key).position_local
                cross = (point[0]-start[0])*(end[1]-start[1]) - (point[1]-start[1])*(end[0]-start[0])
                self.assertAlmostEqual(cross, 0.0, delta=1e-6)

    def test_graph_run_invariants_across_supported_variants(self):
        for kind in ("Parallel", "DuoPitch"):
            for preset in ("Warren", "Pratt"):
                for count in (4, 5, 6, 7, 8, 11):
                    for apex in (0.08, 0.5, 0.73, 0.95):
                        with self.subTest(kind=kind, preset=preset, count=count, apex=apex):
                            candidate = build_candidate(config(envelope_type=kind,
                                topology_preset=preset, panel_count=count, apex_position=apex))
                            self.assert_graph_and_runs(candidate)
                            self.assertEqual(len(candidate.stations.stations), count + 1)
                            self.assertEqual(candidate.stations.panel_count, count)

    def test_parallel_warren_exact_diagonals_and_end_posts(self):
        candidate = build_candidate(config(panel_count=4))
        nodes = station_nodes(candidate)
        self.assertEqual(directed_role_edges(candidate, "DIAGONAL"), {
            (nodes[0][0], nodes[1][1]), (nodes[1][1], nodes[2][0]),
            (nodes[2][0], nodes[3][1]), (nodes[3][1], nodes[4][0]),
        })
        self.assertEqual(directed_role_edges(candidate, "END_POST"), {
            (nodes[0][0], nodes[0][1]), (nodes[-1][0], nodes[-1][1]),
        })
        self.assertFalse(directed_role_edges(candidate, "VERTICAL"))

    def test_triangular_warren_closures_are_interior_not_duplicate_chords(self):
        candidate = build_candidate(config(envelope_type="DuoPitch", panel_count=4))
        nodes = station_nodes(candidate)
        self.assertEqual(nodes[0][0], nodes[0][1])
        self.assertEqual(nodes[-1][0], nodes[-1][1])
        self.assertEqual(directed_role_edges(candidate, "VERTICAL"), {
            (nodes[1][0], nodes[1][1]), (nodes[3][0], nodes[3][1]),
        })
        self.assertEqual(directed_role_edges(candidate, "DIAGONAL"), {
            (nodes[1][1], nodes[2][0]), (nodes[2][0], nodes[3][1]),
        })
        self.assertFalse(directed_role_edges(candidate, "END_POST"))

    def test_parallel_odd_pratt_midspan_panel_explicitly_follows_left_orientation(self):
        candidate = build_candidate(config(topology_preset="Pratt", panel_count=5))
        nodes = station_nodes(candidate)
        self.assertEqual(directed_role_edges(candidate, "DIAGONAL"), {
            (nodes[0][1], nodes[1][0]), (nodes[1][1], nodes[2][0]),
            (nodes[2][1], nodes[3][0]), (nodes[3][0], nodes[4][1]),
            (nodes[4][0], nodes[5][1]),
        })

    def test_asymmetric_pratt_turns_at_mandatory_apex_not_index_midpoint(self):
        candidate = build_candidate(config(envelope_type="DuoPitch", topology_preset="Pratt",
                                           panel_count=7, apex_position=0.25))
        nodes = station_nodes(candidate)
        self.assertEqual(candidate.stations.left_panels, 2)
        self.assertEqual(directed_role_edges(candidate, "DIAGONAL"), {
            (nodes[1][1], nodes[2][0]), (nodes[2][0], nodes[3][1]),
            (nodes[3][0], nodes[4][1]), (nodes[4][0], nodes[5][1]),
            (nodes[5][0], nodes[6][1]),
        })

    def test_c1_rejects_two_and_three_panels_without_silent_rounding(self):
        for kind in ("Parallel", "DuoPitch"):
            for preset in ("Warren", "Pratt"):
                for count in (2, 3):
                    with self.subTest(kind=kind, preset=preset, count=count):
                        with self.assertRaises(ValueError):
                            build_candidate(config(envelope_type=kind, topology_preset=preset,
                                                   panel_count=count))

    def test_dimensional_edit_preserves_apex_allocation_and_all_graph_keys(self):
        old = build_candidate(config(envelope_type="DuoPitch", apex_position=0.25, panel_count=8))
        new = build_candidate(config(envelope_type="DuoPitch", apex_position=0.8,
                                     panel_count=8, height=900.0), applied=old)
        self.assertEqual((new.stations.left_panels, new.stations.right_panels), (2, 6))
        self.assertEqual(structural_signature(new), structural_signature(old))
        self.assertFalse(plan_regeneration(new, old).structural)
        self.assertFalse(any(action.action in ("CREATE_NEW", "REMOVE_EXISTING")
                             for action in plan_regeneration(new, old).actions))
        self.assertEqual(next(s.x for s in new.stations.stations if s.key == "S_APEX"), 4800.0)

    def test_six_to_eight_retains_only_actual_common_fraction_station_identities(self):
        old = build_candidate(config(envelope_type="DuoPitch", panel_count=6))
        new = build_candidate(config(envelope_type="DuoPitch", panel_count=8), old)
        old_stations = {s.key: s.x for s in old.stations.stations}
        new_stations = {s.key: s.x for s in new.stations.stations}
        self.assertEqual(set(old_stations) & set(new_stations), {"S_START", "S_APEX", "S_END"})
        self.assertTrue(plan_regeneration(new, old).structural)
        for key in set(old_stations) & set(new_stations):
            self.assertEqual(old_stations[key], new_stations[key])

    def test_continuities_never_create_bent_physical_top_member(self):
        for top_mode in CONTINUITIES:
            for bottom_mode in CONTINUITIES:
                candidate = build_candidate(config(envelope_type="DuoPitch", apex_position=0.35,
                    top_continuity=top_mode, bottom_continuity=bottom_mode))
                self.assert_graph_and_runs(candidate)
                top_runs = [r for r in candidate.runs if r.role == "TOP_CHORD"]
                self.assertEqual(len(top_runs), 6 if top_mode == "SegmentAtEveryNode" else 2)

    def test_continuous_and_break_modes_are_equivalent_for_c1_envelopes(self):
        for kind in ("Parallel", "DuoPitch"):
            continuous = build_candidate(config(envelope_type=kind))
            breaks = build_candidate(config(envelope_type=kind,
                top_continuity="SegmentAtBreaks", bottom_continuity="SegmentAtBreaks"))
            self.assertEqual(continuous.runs, breaks.runs)
            self.assertFalse(plan_regeneration(breaks, continuous).structural)

    def test_noop_regeneration_keeps_bindings_and_requires_no_structural_apply(self):
        old = build_candidate(config())
        bindings = {item.key: "Member_{}".format(i) for i, item in enumerate(old.items)}
        new = build_candidate(copy.deepcopy(old.config), old)
        plan = plan_regeneration(new, old, bindings)
        self.assertFalse(plan.structural)
        self.assertTrue(all(a.action == "UNCHANGED" for a in plan.actions))
        self.assertTrue(all(a.existing_binding == bindings[a.key] for a in plan.actions))

    def test_profile_edit_updates_only_role_and_preserves_run_identities(self):
        old = build_candidate(config())
        change = copy.deepcopy(old.config)
        change["role_specs"]["DIAGONAL"]["profile_ref"]["profile_id"] = "another_section"
        new = build_candidate(change, old)
        plan = plan_regeneration(new, old)
        self.assertFalse(plan.structural)
        diagonals = {item.key for item in old.items if item.role == "DIAGONAL"}
        self.assertEqual({a.key for a in plan.actions if a.action == "UPDATE_EXISTING"}, diagonals)
        self.assertTrue(all(a.action in ("UNCHANGED", "UPDATE_EXISTING") for a in plan.actions))

    def test_segmentation_change_does_not_reuse_continuous_chord_binding(self):
        old = build_candidate(config())
        new = build_candidate(config(top_continuity="SegmentAtEveryNode"), old)
        actions = {a.key: a.action for a in plan_regeneration(new, old).actions}
        self.assertEqual(actions["TC_MAIN"], "REMOVE_EXISTING")
        self.assertEqual(sum(action == "CREATE_NEW" for action in actions.values()), 6)
        self.assertEqual(actions["BC_MAIN"], "UNCHANGED")

    def test_removal_conflict_survives_planning_instead_of_becoming_delete(self):
        old = build_candidate(config())
        new = build_candidate(config(top_continuity="SegmentAtEveryNode"), old)
        plan = plan_regeneration(new, old, {"TC_MAIN": "Member1"},
                                 {"TC_MAIN": "external face reference"})
        self.assertEqual(len(plan.conflicts), 1)
        self.assertEqual(plan.conflicts[0].key, "TC_MAIN")
        self.assertEqual(plan.conflicts[0].existing_binding, "Member1")
        self.assertEqual(plan.conflicts[0].reason, "external face reference")

    def test_reference_frame_maps_planar_nodes_and_section_u_without_reflection(self):
        candidate = build_candidate(config(start=[10., 20., 30.], end=[10., 6020., 30.],
                                           plane_normal=[1., 0., 0.]))
        for item in candidate.items:
            for local, world in ((item.start_local, item.start_global), (item.end_local, item.end_global)):
                self.assertEqual(world, (10.0, 20.0 + local[0], 30.0 + local[1]))
            # The approved section frame uses -normal so +section Y points up
            # for a forward chord. +normal was the inverted U/L convention.
            self.assertEqual(item.section_u_global, (-1.0, 0.0, 0.0))
            length = math.dist(item.start_global, item.end_global)
            w = tuple((b - a) / length for a, b in zip(item.start_global, item.end_global))
            v = (0.0, -w[2], w[1])
            u = item.section_u_global
            handed = (u[1]*v[2]-u[2]*v[1], u[2]*v[0]-u[0]*v[2], u[0]*v[1]-u[1]*v[0])
            for actual, expected in zip(handed, w):
                self.assertAlmostEqual(actual, expected)
            if item.role in ("TOP_CHORD", "BOTTOM_CHORD"):
                self.assertGreater(v[2], 0.0)

    def test_invalid_reference_frames_and_nonfinite_dimensions_are_rejected(self):
        for changes in ({"plane_normal": [0., 0., 0.]}, {"plane_normal": [1., 0., 0.]},
                        {"end": [0., 0., 0.]}, {"span": 5999.}, {"height": 0.},
                        {"height": math.nan}, {"span": math.inf}, {"apex_position": 1.}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                build_candidate(config(**changes))

    def test_very_short_apex_panel_is_rejected_without_merging_distinct_nodes(self):
        with self.assertRaises(ValueError):
            build_candidate(config(envelope_type="DuoPitch", apex_position=1e-12))

    def test_candidate_does_not_retain_mutable_caller_data(self):
        original = config()
        candidate = build_candidate(original)
        before = encode_state(candidate)
        original["height"] = 2000.
        original["role_specs"]["DIAGONAL"]["profile_ref"]["profile_id"] = "changed"
        original["role_specs"]["TOP_CHORD"]["color"][0] = 0.0
        self.assertEqual(encode_state(candidate), before)

    def test_failed_candidate_build_leaves_applied_state_unchanged(self):
        old = build_candidate(config(envelope_type="DuoPitch"))
        before = encode_state(old, {"BC_MAIN": "Member1"})
        with self.assertRaises(ValueError):
            build_candidate(config(envelope_type="DuoPitch", height=0.), old)
        self.assertEqual(encode_state(old, {"BC_MAIN": "Member1"}), before)

    def test_persistence_roundtrip_preserves_realization_and_bindings(self):
        candidate = build_candidate(config(envelope_type="DuoPitch", panel_count=7, apex_position=0.3))
        state = encode_state(candidate, {"TC_LEFT": "Member42"})
        restored = decode_state(state)
        rebuilt = build_candidate(restored["candidate"]["config"])
        self.assertEqual(encode_state(rebuilt, restored["bindings"]), state)
        self.assertEqual(dumps(candidate), dumps(rebuilt))

    def test_unsupported_serialized_versions_are_rejected(self):
        state = json.loads(encode_state(build_candidate(config())))
        for key in ("schema_version", "generator_version"):
            for version in (0, 2, "1", None, True, 1.0):
                with self.subTest(key=key, version=version):
                    bad = copy.deepcopy(state)
                    bad[key] = version
                    with self.assertRaises(ValueError):
                        decode_state(json.dumps(bad))

    def test_duplicate_edges_are_invalid_even_for_different_roles_and_direction(self):
        graph = TopologyGraph((
            TopologyNode("A", (0., 0., 0.), (), "INTERNAL"),
            TopologyNode("B", (10., 0., 0.), (), "INTERNAL"),
        ), (
            TopologyEdge("one", "A", "B", "TOP_CHORD"),
            TopologyEdge("two", "B", "A", "DIAGONAL"),
        ))
        errors, _warnings = validate_graph(graph)
        self.assertTrue(any("duplicada" in error for error in errors))

    def test_crossing_edges_do_not_acquire_an_implicit_shared_node(self):
        nodes = tuple(TopologyNode(key, pos, (), "INTERNAL") for key, pos in (
            ("A", (0., 0., 0.)), ("B", (10., 10., 0.)),
            ("C", (0., 10., 0.)), ("D", (10., 0., 0.))))
        graph = TopologyGraph(nodes, (TopologyEdge("one", "A", "B", "DIAGONAL"),
                                     TopologyEdge("two", "C", "D", "DIAGONAL")))
        errors, warnings = validate_graph(graph)
        self.assertFalse(errors)
        self.assertTrue(any("Cruzamento" in warning for warning in warnings))
        self.assertTrue(any("desconectados" in warning for warning in warnings))
        self.assertEqual(len(graph.nodes), 4)


if __name__ == "__main__":
    unittest.main()
