"""Custom support migration preserves graph ownership and existing web edits."""
from copy import deepcopy
import unittest

from tests.test_truss_qa import config
from freecad.SteelStructures.trusses.editing import materialize, restore_graph, normalize_custom_graph
from freecad.SteelStructures.trusses.preset_contracts import compatible_presets
from freecad.SteelStructures.trusses.realization import build_candidate
from freecad.SteelStructures.trusses.serialization import dumps, loads
from freecad.SteelStructures.trusses.validation import validate_graph


def custom_seed(preset="Warren", left=0., right=0.):
    candidate = build_candidate(config(envelope_type="DuoPitch", topology_preset=preset,
                                       left_end_height=left, right_end_height=right,
                                       link_end_heights=False))
    result = deepcopy(candidate.config)
    result.update(topology_mode="Custom", base_preset=preset, topology_preset="Custom",
                  custom_topology=materialize(candidate.graph, candidate.config))
    return result, candidate.graph


class DuoPitchCustomTests(unittest.TestCase):
    def test_zero_legacy_shared_supports_split_for_all_presets(self):
        for preset in compatible_presets("DuoPitch"):
            with self.subTest(preset=preset):
                values, original = custom_seed(preset)
                values.update(left_end_height=240., right_end_height=510.)
                candidate = build_candidate(values)
                self.assertEqual(validate_graph(candidate.graph)[0], ())
                for x, height in ((0., 240.), (6000., 510.)):
                    shared = next(node for node in original.nodes if node.position_local==(x, 0., 0.))
                    bottom = candidate.graph.node(shared.key)
                    self.assertEqual(bottom.position_local, (x, 0., 0.))
                    self.assertEqual(bottom.affiliations, ("BOTTOM_CHORD",))
                    upper = next(node for node in candidate.graph.nodes if node.position_local==(x, height, 0.))
                    self.assertEqual(upper.affiliations, ("TOP_CHORD",))
                    self.assertTrue(any(edge.role=="END_POST" and
                                        {edge.start_node_key, edge.end_node_key}=={bottom.key, upper.key}
                                        for edge in candidate.graph.edges))
                    for edge in original.edges:
                        if edge.role=="TOP_CHORD":
                            continue
                        migrated = candidate.graph.edge(edge.key)
                        self.assertEqual((migrated.start_node_key, migrated.end_node_key),
                                         (edge.start_node_key, edge.end_node_key))

    def test_custom_web_removal_is_not_regenerated_as_a_preset(self):
        values, original = custom_seed("Pratt")
        removed = next(edge for edge in original.edges if edge.role=="DIAGONAL")
        values["custom_topology"]["edges"] = [edge for edge in values["custom_topology"]["edges"]
                                                if edge["key"]!=removed.key]
        values.update(left_end_height=250., right_end_height=450.)
        candidate = build_candidate(values)
        self.assertNotIn(removed.key, {edge.key for edge in candidate.graph.edges})
        self.assertEqual(candidate.config["base_preset"], "Pratt")

    def test_positive_zero_positive_roundtrip_and_semantic_top_binding(self):
        values, original = custom_seed("Fink")
        values.update(left_end_height=250., right_end_height=450.)
        raised = build_candidate(values)
        raised_values = deepcopy(raised.config)
        raised_values["custom_topology"] = materialize(raised.graph, raised_values)
        upper = next(node for node in raised.graph.nodes if node.position_local==(0., 250., 0.))
        self.assertEqual(raised_values["custom_topology"]["bindings"][upper.key]["y"], 1.)
        zero_values = loads(dumps(raised_values))
        zero_values.update(left_end_height=0., right_end_height=0.)
        collapsed = build_candidate(zero_values)
        self.assertEqual(collapsed.graph, original)
        self.assertFalse(any(edge.role=="END_POST" for edge in collapsed.graph.edges))
        self.assertEqual(len({node.position_local for node in collapsed.graph.nodes}), len(collapsed.graph.nodes))
        again_values = loads(dumps(collapsed.config))
        again_values.update(left_end_height=330., right_end_height=660.)
        again = build_candidate(again_values)
        self.assertTrue(any(node.position_local==(0., 330., 0.) for node in again.graph.nodes))
        self.assertTrue(any(node.position_local==(6000., 660., 0.) for node in again.graph.nodes))

    def test_one_zero_end_only_adds_one_closure(self):
        values, _ = custom_seed()
        values.update(left_end_height=0., right_end_height=200.)
        candidate = build_candidate(values)
        self.assertEqual(sum(edge.role=="END_POST" for edge in candidate.graph.edges), 1)
        self.assertEqual(sum(node.position_local==(0., 0., 0.) for node in candidate.graph.nodes), 1)

    def test_top_only_zero_binding_remains_semantically_upper(self):
        values, _ = custom_seed(left=100., right=200.)
        upper_key = next(node["key"] for node in values["custom_topology"]["nodes"]
                         if node["position_local"]==(0., 100., 0.))
        values.update(left_end_height=0., right_end_height=0.)
        restored = restore_graph(values["custom_topology"], values)
        self.assertEqual(materialize(restored, values)["bindings"][upper_key]["y"], 1.)

    def test_only_collapsed_end_posts_are_removed_before_normalization(self):
        values, _ = custom_seed(left=100., right=200.)
        end_post = next(edge for edge in values["custom_topology"]["edges"] if edge["role"]=="END_POST")
        bad = dict(end_post, key="MANUAL_COLLAPSED_DIAGONAL", role="DIAGONAL")
        values["custom_topology"]["edges"].append(bad)
        values.update(left_end_height=0., right_end_height=0.)
        restored = restore_graph(values["custom_topology"], values)
        self.assertTrue(any(edge.key==bad["key"] for edge in restored.edges))
        with self.assertRaises(ValueError):
            normalize_custom_graph(restored)

    def test_restore_is_detached_and_migration_is_repeatable(self):
        values, _ = custom_seed("Howe")
        values.update(left_end_height=200., right_end_height=400.)
        before = deepcopy(values["custom_topology"])
        first = restore_graph(values["custom_topology"], values)
        second = restore_graph(values["custom_topology"], values)
        self.assertEqual(first, second)
        self.assertEqual(values["custom_topology"], before)


if __name__ == "__main__":
    unittest.main()
