"""Ownership and rollback of the bilateral renderer, without a Qt session."""

import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch


SOURCE = (Path(__file__).resolve().parents[1] / "freecad/SteelStructures"
          / "interactive/member_miter_preview.py")


class Scene:
    def __init__(self):
        self.children = []
        self.fail_after_attach = None

    def addChild(self, node):
        self.children.append(node)
        if node is self.fail_after_attach:
            raise RuntimeError("Marker attachment failed")

    def findChild(self, node):
        return self.children.index(node) if node in self.children else -1

    def removeChild(self, node):
        self.children.remove(node)


class ExactRenderer:
    def __init__(self, scene, color):
        self.scene_graph = scene
        self.color = color
        self.node = None
        self.shape = None
        self.received = []

    def update(self, member, result):
        if getattr(member, "fail", False):
            raise RuntimeError("Second candidate export failed")
        self.received.append((member, result))
        self.node = object()
        self.shape = result.Shape
        self.scene_graph.addChild(self.node)

    def clear(self):
        if self.node is not None and self.scene_graph.findChild(self.node) >= 0:
            self.scene_graph.removeChild(self.node)
        self.node = self.shape = None


class MiterPreviewTests(unittest.TestCase):
    def setUp(self):
        package = types.ModuleType("_miter_preview")
        package.__path__ = []
        interactive = types.ModuleType("_miter_preview.interactive")
        interactive.__path__ = []
        shared = types.ModuleType("_miter_preview.interactive.member_adjustment_preview")
        shared.MemberAdjustmentPreview = ExactRenderer
        cuts = types.ModuleType("_miter_preview.member_plane_cut")
        cuts.orthonormal_plane_basis = lambda _: None
        modules = patch.dict(sys.modules, {
            "FreeCAD": types.ModuleType("FreeCAD"), "_miter_preview": package,
            "_miter_preview.interactive": interactive,
            shared.__name__: shared, cuts.__name__: cuts,
        })
        modules.start()
        self.addCleanup(modules.stop)
        spec = importlib.util.spec_from_file_location("_miter_preview.interactive.member_miter_preview", SOURCE)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.scene = Scene()
        self.preview = module.MemberMiterPreview(self.scene)
        self.marker = object()
        self.preview._meeting_marker = lambda _: self.marker
        self.candidate = types.SimpleNamespace(
            members=(types.SimpleNamespace(), types.SimpleNamespace()),
            candidates=tuple(types.SimpleNamespace(result=types.SimpleNamespace(Shape=object())) for _ in range(2)),
            global_shapes=tuple(types.SimpleNamespace(Placement=object()) for _ in range(2)))

    def test_delegates_exact_world_candidates_to_two_shared_renderers(self):
        self.preview.update(self.candidate)
        self.assertEqual(len(self.scene.children), 3)
        self.assertNotEqual(self.preview.previews[0].color, self.preview.previews[1].color)
        for index, renderer in enumerate(self.preview.previews):
            member, presentation = renderer.received[0]
            self.assertIs(member, self.candidate.members[index])
            self.assertIs(presentation.Shape, self.candidate.global_shapes[index])
            self.assertIs(presentation.Placement, self.candidate.global_shapes[index].Placement)
            self.assertIsNot(presentation, self.candidate.candidates[index].result)
        self.assertIn(self.marker, self.scene.children)

    def test_second_failure_removes_first_preview_and_marker(self):
        self.candidate.members[1].fail = True
        with self.assertRaisesRegex(RuntimeError, "Second candidate"):
            self.preview.update(self.candidate)
        self.assertEqual(self.scene.children, [])
        self.assertIsNone(self.preview.node)
        self.assertTrue(all(p.node is None for p in self.preview.previews))

    def test_marker_attachment_failure_rolls_back_both_candidates(self):
        self.scene.fail_after_attach = self.marker
        with self.assertRaisesRegex(RuntimeError, "Marker attachment"):
            self.preview.update(self.candidate)
        self.assertEqual(self.scene.children, [])
        self.assertIsNone(self.preview.node)

    def test_replacement_failure_removes_previous_complete_pair(self):
        self.preview.update(self.candidate)
        self.candidate.members[1].fail = True
        with self.assertRaises(RuntimeError):
            self.preview.update(self.candidate)
        self.assertEqual(self.scene.children, [])

    def test_clear_is_idempotent_and_preserves_unrelated_scene_content(self):
        other = object()
        self.scene.addChild(other)
        self.preview.update(self.candidate)
        self.preview.clear()
        self.preview.clear()
        self.assertEqual(self.scene.children, [other])


if __name__ == "__main__":
    unittest.main()
