"""Focused C6-G semantic bridge regressions."""

import unittest

from tests.test_gusset_c6f import _outline
from tests.test_ridge_fitting import ridge_config
from tests.test_connections_c5b_through import k_config


def _bridges(outline):
    return tuple(edge for edge in outline.semantic_edges
                 if edge.kind == "WEB_SECTOR_BRIDGE")


class WebSectorBridgeTests(unittest.TestCase):
    def test_duopitch_diagonal_vertical_and_mirrored_sector_use_caps_directly(self):
        for node in ("T_S_LEFT_1_3", "T_S_RIGHT_1_5"):
            with self.subTest(node=node):
                outline = _outline(ridge_config(.37, 1100.), node)
                bridges = _bridges(outline)
                self.assertFalse(bridges)
                chords = [edge for edge in outline.semantic_edges
                          if edge.kind == "CHORD_BOUNDARY"]
                self.assertTrue(chords)
                self.assertGreaterEqual(sum(edge.kind == "WEB_END_CAP"
                                            for edge in outline.semantic_edges), 2)

    def test_k_and_ridge_do_not_bridge_across_semantic_boundary(self):
        value, node = k_config(False)
        self.assertFalse(_bridges(_outline(value, node)))
        self.assertFalse(_bridges(_outline(
            ridge_config(.37, 1100.), "T_S_APEX")))

    def test_legacy_pair_role_is_absent(self):
        outline = _outline(ridge_config(.37, 1100.), "T_S_LEFT_1_3")
        self.assertNotIn("WEB_PAIR_BRIDGE",
                         {edge.kind for edge in outline.semantic_edges})


if __name__ == "__main__":
    unittest.main()
