"""Headless lifecycle checks for the transient member-adjustment Coin preview.

The doubles exercise ownership and cleanup of the scene branch; native gates
remain responsible for FreeCAD/Pivy rendering and Qt task-panel integration.
"""

import ast
import importlib.util
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch


SOURCE = (Path(__file__).resolve().parents[1] / "freecad/SteelStructures"
          / "interactive/member_adjustment_preview.py")
PANEL_SOURCE = SOURCE.with_name("member_adjustment_task_panel.py")


class ReferencePollingTests(unittest.TestCase):
    """Run the real polling methods with equal hashes and global supports."""

    def setUp(self):
        tree = ast.parse(PANEL_SOURCE.read_text(encoding="utf-8"))
        panel_class = next(n for n in tree.body if isinstance(n, ast.ClassDef)
                           and n.name == "MemberAdjustmentTaskPanel")
        methods = [n for n in panel_class.body if isinstance(n, ast.FunctionDef)
                   and n.name in ("_reference_signature", "_poll_reference")]
        self.document = types.SimpleNamespace(Name="PollingDocument")
        gui_doc = types.SimpleNamespace(Document=self.document)
        namespace = dict(__package__="freecad.SteelStructures.interactive",
                         App=types.SimpleNamespace(listDocuments=lambda: {self.document.Name: self.document}),
                         Gui=types.SimpleNamespace(activeDocument=lambda: gui_doc))
        exec(compile(ast.Module(body=methods, type_ignores=[]), str(PANEL_SOURCE), "exec"), namespace)
        panel_type = type("PollingPanel", (), {n.name: namespace[n.name] for n in methods})
        member = types.SimpleNamespace(
            Placement=types.SimpleNamespace(toMatrix=lambda: types.SimpleNamespace(A=(1., 0., 0., 1.))),
            ViewObject=types.SimpleNamespace(Visibility=True, DisplayMode="Flat Lines"))
        self.member = member
        self.panel = panel_type()
        self.panel.controller = types.SimpleNamespace(member=member)
        self.panel.document = self.document
        self.panel._closed = False
        self.panel._preview = None
        self.panel.reference = None
        batch = types.ModuleType("freecad.SteelStructures.member_batch")
        batch.signature = lambda obj: ("unchanged-member-inputs",)
        modules = patch.dict(sys.modules, {batch.__name__: batch})
        modules.start()
        self.addCleanup(modules.stop)
        self.panel._refresh = Mock(side_effect=lambda: setattr(
            self.panel, "_watch_state", self.panel._reference_signature()))

    def source(self, kind="Face"):
        def vector(values):
            return types.SimpleNamespace(x=values[0], y=values[1], z=values[2],
                                         Length=sum(v*v for v in values)**.5)
        source = types.SimpleNamespace(Name="Reference", origin=(0., 0., 100.), direction=(0., 0., 1.),
                                       valid=True, Placement="unchanged-local-placement")
        shape = types.SimpleNamespace(
            ShapeType=kind, isNull=lambda: False, isValid=lambda: source.valid,
            hashCode=lambda: 12345, ParameterRange=(0., 1., 0., 1.),
            Surface=types.SimpleNamespace(TypeId="Part::GeomPlane"),
            Curve=types.SimpleNamespace(TypeId="Part::GeomLine"), FirstParameter=0., LastParameter=1.,
            valueAt=lambda t, *args: vector(source.origin if kind == "Face" else
                tuple(a + t*b for a, b in zip(source.origin, source.direction))),
            normalAt=lambda *_: vector(source.direction))
        source.Shape = shape
        source.getSubObject = lambda _: shape
        return source, (source, [kind + "1"])

    def watch(self, link):
        self.panel.reference = link
        self.panel._watch_state = self.panel._reference_signature()
        self.panel._poll_reference()
        self.panel._refresh.assert_not_called()

    def test_face_translation_with_equal_hash_triggers_one_refresh(self):
        source, link = self.source()
        self.watch(link)
        source.origin = (0., 0., 120.)
        self.panel._poll_reference()
        self.panel._poll_reference()
        self.panel._refresh.assert_called_once_with()

    def test_face_rotation_and_successive_moves_with_equal_hash(self):
        source, link = self.source()
        self.watch(link)
        for origin, normal in (((0., 0., 120.), (0., .6, .8)),
                               ((0., 0., 90.), (.6, 0., .8)),
                               ((0., 0., 100.), (0., 0., 1.))):
            source.origin, source.direction = origin, normal
            self.panel._poll_reference()
        self.assertEqual(self.panel._refresh.call_count, 3)
        self.assertEqual(source.Placement, "unchanged-local-placement")

    def test_edge_support_moves_with_equal_hash(self):
        source, link = self.source("Edge")
        self.watch(link)
        source.origin = (0., 0., 120.)
        self.panel._poll_reference()
        source.direction = (0., 1., 0.)
        self.panel._poll_reference()
        self.assertEqual(self.panel._refresh.call_count, 2)

    def test_opposite_associative_reference_is_observed(self):
        source, link = self.source()
        self.member.EndAdjustmentReference = link
        self.watch(None)
        source.origin = (0., 0., 120.)
        self.panel._poll_reference()
        self.panel._refresh.assert_called_once_with()

    def test_reference_validity_changes_with_equal_hash(self):
        source, link = self.source()
        self.watch(link)
        source.valid = False
        self.panel._poll_reference()
        source.valid = True
        self.panel._poll_reference()
        self.assertEqual(self.panel._refresh.call_count, 2)


class Placement:
    def __init__(self, source):
        self.coordinates = tuple(source.coordinates)


class Field:
    def __init__(self, value):
        self.value = value
        self.writes = []
        self.fail_once = False
        self.closed = False

    def getValue(self):
        return self.value

    def setValue(self, value):
        if self.closed:
            raise ReferenceError("View already closed")
        if self.fail_once:
            self.fail_once = False
            raise RuntimeError("Cannot hide source")
        self.writes.append(value)
        self.value = value


class Node:
    def __init__(self):
        self.children = []

    def addChild(self, child):
        self.children.append(child)

    def findChild(self, child):
        return self.children.index(child) if child in self.children else -1

    def removeChild(self, child):
        self.children.remove(child)


class PickStyle:
    UNPICKABLE = 7


class Color:
    def setValue(self, *value):
        self.value = value


class Material:
    def __init__(self):
        self.diffuseColor = Color()

    def setOverride(self, value):
        self.override = value


class Input:
    def setBuffer(self, value):
        self.buffer = value


class Shape:
    def __init__(self, name="candidate"):
        self.name = name
        self.Placement = types.SimpleNamespace(coordinates=(0., 0., 0., 0.))
        self.copies = []
        self.exported_placement = None

    def copy(self):
        result = Shape(self.name)
        self.copies.append(result)
        return result

    def writeInventor(self):
        self.exported_placement = self.Placement.coordinates
        return "Inventor:" + self.name


class View:
    """Reading presentation is allowed; persistent visibility writes are not."""
    def __init__(self, which_child):
        self.SwitchNode = types.SimpleNamespace(whichChild=Field(which_child))
        self._visibility = which_child != -1
        self.DisplayMode = "Flat Lines"

    @property
    def Visibility(self):
        return self._visibility

    @Visibility.setter
    def Visibility(self, value):
        raise AssertionError("Preview must not write persistent Visibility")


class MemberAdjustmentPreviewTests(unittest.TestCase):
    def setUp(self):
        self.read_buffers = []
        self.geometry = Node()

        def read_all(data):
            self.read_buffers.append(data.buffer)
            return self.geometry

        self.coin = types.SimpleNamespace(
            SoSeparator=Node, SoInput=Input, SoPickStyle=PickStyle,
            SoMaterial=Material, SoDB=types.SimpleNamespace(readAll=read_all),
            SO_SWITCH_NONE=-1,
        )
        app = types.ModuleType("FreeCAD")
        app.Placement = Placement
        # No document-creation API is available to the preview in this fixture.
        pivy = types.ModuleType("pivy")
        pivy.coin = self.coin
        self.modules = patch.dict(sys.modules, {"FreeCAD": app, "pivy": pivy})
        self.modules.start()
        self.addCleanup(self.modules.stop)
        spec = importlib.util.spec_from_file_location("_adjustment_preview_qa", SOURCE)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.graph = Node()
        self.preview = module.MemberAdjustmentPreview(self.graph)
        self.addCleanup(self.preview.clear)

    def member(self, which_child=3):
        return types.SimpleNamespace(ViewObject=View(which_child))

    def result(self, name="candidate", coordinates=(12., 34., 56., 90.)):
        return types.SimpleNamespace(
            Shape=Shape(name), Placement=types.SimpleNamespace(coordinates=coordinates),
        )

    def test_exports_copy_with_candidate_placement_without_modifying_candidate(self):
        result = self.result()
        self.preview.update(self.member(), result)
        self.assertIsNot(self.preview.shape, result.Shape)
        self.assertIsNot(self.preview.shape.Placement, result.Placement)
        self.assertEqual(self.preview.shape.exported_placement, result.Placement.coordinates)
        self.assertEqual(result.Shape.Placement.coordinates, (0., 0., 0., 0.))
        self.assertIsNone(result.Shape.exported_placement)
        self.assertEqual(self.read_buffers, ["Inventor:candidate"])

    def test_candidate_branch_is_unpickable_and_contains_exported_geometry(self):
        self.preview.update(self.member(), self.result())
        self.assertEqual(len(self.graph.children), 1)
        branch = self.graph.children[0]
        styles = [child for child in branch.children if isinstance(child, PickStyle)]
        self.assertEqual(len(styles), 1)
        self.assertEqual(styles[0].style, PickStyle.UNPICKABLE)
        self.assertIn(self.geometry, branch.children)

    def test_restores_exact_original_switch_including_initially_hidden(self):
        for initial in (-1, -3, 0, 3):
            with self.subTest(initial=initial):
                member = self.member(initial)
                self.preview.update(member, self.result())
                self.assertEqual(member.ViewObject.SwitchNode.whichChild.value, -1)
                self.preview.clear()
                self.assertEqual(member.ViewObject.SwitchNode.whichChild.value, initial)
                self.assertEqual(self.graph.children, [])

    def test_replacing_same_target_does_not_forget_original_visibility(self):
        member = self.member(4)
        self.preview.update(member, self.result("first"))
        old_node = self.preview.node
        self.preview.update(member, self.result("second"))
        self.assertNotIn(old_node, self.graph.children)
        self.assertEqual(len(self.graph.children), 1)
        self.assertEqual(member.ViewObject.SwitchNode.whichChild.value, -1)
        self.preview.clear()
        self.assertEqual(member.ViewObject.SwitchNode.whichChild.value, 4)

    def test_switching_targets_restores_old_source_and_owns_only_new_branch(self):
        first, second = self.member(2), self.member(5)
        self.preview.update(first, self.result("first"))
        old_node = self.preview.node
        self.preview.update(second, self.result("second"))
        self.assertEqual(first.ViewObject.SwitchNode.whichChild.value, 2)
        self.assertEqual(second.ViewObject.SwitchNode.whichChild.value, -1)
        self.assertNotIn(old_node, self.graph.children)
        self.preview.clear()
        self.assertEqual(second.ViewObject.SwitchNode.whichChild.value, 5)

    def test_invalid_inventor_never_hides_original_or_adds_branch(self):
        self.geometry = None
        member = self.member()
        with self.assertRaisesRegex(ValueError, "geometria candidata"):
            self.preview.update(member, self.result())
        self.assertEqual(member.ViewObject.SwitchNode.whichChild.writes, [])
        self.assertEqual(self.graph.children, [])
        self.assertIsNone(self.preview.shape)

    def test_hide_failure_rolls_back_new_branch_and_restores_source(self):
        member = self.member(6)
        member.ViewObject.SwitchNode.whichChild.fail_once = True
        with self.assertRaisesRegex(RuntimeError, "Cannot hide"):
            self.preview.update(member, self.result())
        self.assertEqual(member.ViewObject.SwitchNode.whichChild.value, 6)
        self.assertEqual(self.graph.children, [])
        self.assertIsNone(self.preview.shape)
        self.assertIsNone(self.preview.node)

    def test_target_switch_failure_also_restores_previous_target(self):
        first, second = self.member(2), self.member(5)
        self.preview.update(first, self.result("first"))
        second.ViewObject.SwitchNode.whichChild.fail_once = True
        with self.assertRaises(RuntimeError):
            self.preview.update(second, self.result("second"))
        self.assertEqual(first.ViewObject.SwitchNode.whichChild.value, 2)
        self.assertEqual(second.ViewObject.SwitchNode.whichChild.value, 5)
        self.assertEqual(self.graph.children, [])

    def test_clear_is_idempotent_and_preserves_unrelated_scene_nodes(self):
        unrelated = Node()
        self.graph.addChild(unrelated)
        member = self.member(8)
        self.preview.update(member, self.result())
        self.preview.clear()
        writes = list(member.ViewObject.SwitchNode.whichChild.writes)
        self.preview.clear()
        self.preview.remove()
        self.assertEqual(member.ViewObject.SwitchNode.whichChild.writes, writes)
        self.assertEqual(self.graph.children, [unrelated])
        self.assertIsNone(self.preview.node)
        self.assertIsNone(self.preview.shape)

    def test_closed_source_does_not_prevent_branch_cleanup(self):
        member = self.member()
        self.preview.update(member, self.result())
        member.ViewObject.SwitchNode.whichChild.closed = True
        self.preview.clear()
        self.assertEqual(self.graph.children, [])
        self.assertIsNone(self.preview.node)
        self.assertIsNone(self.preview.shape)

    def test_user_visibility_change_is_preserved_on_cleanup(self):
        member = self.member(3)
        self.preview.update(member, self.result())
        member.ViewObject._visibility = False  # Simulates an explicit user action.
        self.preview.clear()
        self.assertEqual(member.ViewObject.SwitchNode.whichChild.value, -1)

    def test_user_display_mode_change_does_not_restore_stale_switch(self):
        member = self.member(3)
        self.preview.update(member, self.result())
        member.ViewObject.DisplayMode = "Wireframe"
        member.ViewObject.SwitchNode.whichChild.value = 2
        self.preview.clear()
        self.assertEqual(member.ViewObject.SwitchNode.whichChild.value, 2)


if __name__ == "__main__":
    unittest.main()
