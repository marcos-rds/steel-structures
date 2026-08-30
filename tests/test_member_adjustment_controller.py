"""Controller tests for the Recortar / Ajustar Membro command."""

import importlib.util
import sys
import types
import unittest
from pathlib import Path

from freecad.SteelStructures.member_adjustment_geometry import axis_geometry
import freecad.SteelStructures.member_adjustment_geometry as adjustment_geometry
import freecad.SteelStructures.member_adjustment_reference as adjustment_reference
import freecad.SteelStructures.member_plane_cut as plane_cut
from tests.test_member_adjustment_reference import EdgeReference, Reference
from tests.test_member_placement import MemberObject, Vector, load_member


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "freecad/SteelStructures"


def load_adjustment_controller():
    package_name = "_adjustment_controller_test"
    package = types.ModuleType(package_name); package.__path__ = [str(PACKAGE)]
    interactive_name = package_name + ".interactive"
    interactive = types.ModuleType(interactive_name); interactive.__path__ = [str(PACKAGE / "interactive")]
    injected = {
        package_name: package,
        interactive_name: interactive,
        package_name + ".member_adjustment_geometry": adjustment_geometry,
        package_name + ".member_adjustment_reference": adjustment_reference,
        package_name + ".member_plane_cut": plane_cut,
    }
    previous = {name: sys.modules.get(name) for name in injected}; sys.modules.update(injected)
    path = PACKAGE / "interactive/member_adjustment_controller.py"
    spec = importlib.util.spec_from_file_location(interactive_name + ".member_adjustment_controller", path)
    module = importlib.util.module_from_spec(spec); sys.modules[spec.name] = module; spec.loader.exec_module(module)
    return module, previous


controller_module, _previous_modules = load_adjustment_controller()
AdjustmentProposal = controller_module.AdjustmentProposal
AdjustmentValidationError = controller_module.AdjustmentValidationError
MemberAdjustmentController = controller_module.MemberAdjustmentController
freeze_adjustment_reference = controller_module.freeze_adjustment_reference
resolve_adjusted_end = controller_module.resolve_adjusted_end
validate_proposal = controller_module.validate_proposal


class Document:
    def __init__(self, recompute=None):
        self.opened = []; self.commits = self.aborts = self.recomputes = 0
        self._recompute = recompute
    def openTransaction(self, name): self.opened.append(name)
    def commitTransaction(self): self.commits += 1
    def abortTransaction(self): self.aborts += 1
    def recompute(self):
        self.recomputes += 1
        if self._recompute: self._recompute()


class MemberAdjustmentControllerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.member_module = load_member()

    def member(self, start=(0, 0, 0), end=(3000, 0, 0)):
        obj = MemberObject(start, end)
        proxy = self.member_module.StructuralMemberProxy.__new__(self.member_module.StructuralMemberProxy)
        proxy._updating = proxy._syncing_length = proxy._syncing_placement = False
        proxy._placement_from_points_pending = True; proxy._last_placement = None
        proxy._last_section_rotation = 0.0; proxy._last_valid_length = None
        obj.Proxy = proxy; obj.TypeId = "Part::FeaturePython"; obj.Name = "StructuralMember"
        proxy.execute(obj)
        return obj, proxy

    def proposal(self, obj, reference=None, **kwargs):
        values = dict(member=obj, geometry_mode="LengthLimit", end_choice="Auto",
                      gap=0.0, keep_reference=True,
                      reference=reference or (Reference(point=(2800, 0, 0)), ["Face3"]))
        values.update(kwargs)
        return AdjustmentProposal(**values)

    def test_valid_member_and_invalid_target(self):
        obj, _proxy = self.member()
        self.assertEqual(validate_proposal(self.proposal(obj)).adjusted_end, "End")
        with self.assertRaisesRegex(AdjustmentValidationError, "membro estrutural"):
            validate_proposal(self.proposal(types.SimpleNamespace()))

    def test_face_edge_and_planecut_edge_rules(self):
        obj, _proxy = self.member()
        face = validate_proposal(self.proposal(obj))
        edge_ref = (EdgeReference((200, -10, 0), (200, 10, 0)), ["Edge3"])
        edge = validate_proposal(self.proposal(obj, edge_ref))
        self.assertEqual((face.message, edge.message),
                         ("Face plana selecionada", "Aresta reta selecionada"))
        with self.assertRaisesRegex(AdjustmentValidationError, "exige uma Face"):
            validate_proposal(self.proposal(obj, edge_ref, geometry_mode="PlaneCut"))

    def test_auto_start_end_outside_and_ambiguous(self):
        axis = axis_geometry((0, 0, 0), (3000, 0, 0))
        self.assertEqual(resolve_adjusted_end(axis, -500, "Auto"), "Start")
        self.assertEqual(resolve_adjusted_end(axis, 3400, "Auto"), "End")
        with self.assertRaisesRegex(AdjustmentValidationError, "Escolha Início ou Fim"):
            resolve_adjusted_end(axis, 1500, "Auto")

    def test_positive_and_negative_gap_are_preserved(self):
        obj, _proxy = self.member()
        for gap in (-50, 0, 50):
            with self.subTest(gap=gap):
                self.assertEqual(validate_proposal(self.proposal(obj, gap=gap)).gap, gap)

    def test_cycle_is_rejected_before_apply(self):
        obj, _proxy = self.member(); obj.OutList = []
        with self.assertRaisesRegex(AdjustmentValidationError, "dependência circular"):
            validate_proposal(self.proposal(obj, (obj, ["Face3"])))

    def test_fixed_length_limit_freeze_offset(self):
        obj, _proxy = self.member()
        resolved = freeze_adjustment_reference(
            obj, (Reference(point=(2800, 0, 0)), ["Face3"]),
            "LengthLimit", "End", gap=20,
        )
        self.assertFalse(resolved.keep_reference)
        self.assertEqual((resolved.station, resolved.fixed_reference_offset), (2800, 200))

    def test_fixed_planecut_freeze_stores_local_normal(self):
        obj, _proxy = self.member()
        old = sys.modules.get("FreeCAD")
        sys.modules["FreeCAD"] = types.SimpleNamespace(Vector=Vector)
        try:
            resolved = freeze_adjustment_reference(
                obj, (Reference(point=(2800, 0, 0), normal=(1, 1, 0)), ["Face3"]),
                "PlaneCut", "End",
            )
        finally:
            if old is None: sys.modules.pop("FreeCAD", None)
            else: sys.modules["FreeCAD"] = old
        self.assertIsNotNone(resolved.fixed_plane_normal)
        self.assertAlmostEqual(sum(value * value for value in resolved.fixed_plane_normal), 1.0)

    def test_associative_and_fixed_apply_in_one_transaction(self):
        for keep in (True, False):
            with self.subTest(keep=keep):
                obj, proxy = self.member()
                doc = Document(lambda: proxy.execute(obj))
                controller = MemberAdjustmentController(doc, obj)
                resolved = controller.validate(
                    geometry_mode="LengthLimit", end_choice="End", gap=20,
                    keep_reference=keep,
                    reference=(Reference(point=(2800, 0, 0)), ["Face3"]),
                )
                controller.apply(resolved)
                self.assertEqual(doc.opened, ["Recortar / Ajustar membro"])
                self.assertEqual((doc.commits, doc.aborts, doc.recomputes), (1, 0, 1))
                self.assertEqual(str(obj.EndAdjustmentMode), "Associative" if keep else "Fixed")
                self.assertEqual(obj.EndAdjustmentGap.Value, 20)
                self.assertIsNotNone(obj.EndAdjustmentReference if keep else True)

    def test_cancel_is_controller_noop_and_remove_is_transactional(self):
        obj, proxy = self.member(); before = str(obj.EndAdjustmentMode)
        doc = Document(lambda: proxy.execute(obj)); MemberAdjustmentController(doc, obj)
        self.assertEqual((str(obj.EndAdjustmentMode), doc.opened), (before, []))
        controller = MemberAdjustmentController(doc, obj); controller.remove_adjustment("End")
        self.assertEqual((str(obj.EndAdjustmentMode), doc.commits), ("None", 1))

    def test_existing_fixed_allows_gap_only_without_reference(self):
        obj, _proxy = self.member(); obj.EndAdjustmentMode = "Fixed"
        obj.EndAdjustmentGeometryMode = "LengthLimit"
        controller = MemberAdjustmentController(Document(), obj)
        resolved = controller.validate_existing_fixed(
            geometry_mode="LengthLimit", end_choice="End", gap=-25
        )
        self.assertEqual(resolved.gap, -25)
        with self.assertRaisesRegex(AdjustmentValidationError, "nova referência"):
            controller.validate_existing_fixed(
                geometry_mode="PlaneCut", end_choice="End", gap=0
            )

    def test_applying_start_preserves_existing_end_slot(self):
        obj, proxy = self.member(); end_reference = Reference(point=(2800, 0, 0))
        obj.EndAdjustmentMode = "Associative"; obj.EndAdjustmentReference = (end_reference, ["Face3"])
        doc = Document(lambda: proxy.execute(obj)); controller = MemberAdjustmentController(doc, obj)
        resolved = controller.validate(
            geometry_mode="LengthLimit", end_choice="Start", gap=15,
            keep_reference=False,
            reference=(Reference(point=(200, 0, 0)), ["Face3"]),
        )
        controller.apply(resolved)
        self.assertEqual(str(obj.StartAdjustmentMode), "Fixed")
        self.assertIs(obj.EndAdjustmentReference[0], end_reference)
        self.assertEqual(str(obj.EndAdjustmentMode), "Associative")

    def test_applying_end_preserves_existing_start_slot(self):
        obj, proxy = self.member(); start_reference = Reference(point=(200, 0, 0))
        obj.StartAdjustmentMode = "Associative"; obj.StartAdjustmentReference = (start_reference, ["Face3"])
        doc = Document(lambda: proxy.execute(obj)); controller = MemberAdjustmentController(doc, obj)
        resolved = controller.validate(
            geometry_mode="LengthLimit", end_choice="End", gap=-20,
            keep_reference=True,
            reference=(Reference(point=(2800, 0, 0)), ["Face3"]),
        )
        controller.apply(resolved)
        self.assertIs(obj.StartAdjustmentReference[0], start_reference)
        self.assertEqual(str(obj.StartAdjustmentMode), "Associative")
        self.assertEqual(obj.EndAdjustmentGap.Value, -20)

    def test_remove_one_slot_preserves_the_other_and_auto_is_rejected(self):
        obj, proxy = self.member(); obj.StartAdjustmentMode = "Fixed"
        obj.EndAdjustmentMode = "Fixed"; doc = Document(lambda: proxy.execute(obj))
        controller = MemberAdjustmentController(doc, obj); controller.remove_adjustment("End")
        self.assertEqual(str(obj.StartAdjustmentMode), "Fixed")
        self.assertEqual(str(obj.EndAdjustmentMode), "None")
        with self.assertRaisesRegex(AdjustmentValidationError, "Início ou Fim"):
            controller.remove_adjustment("Auto")

    def test_freeze_explicit_start_and_end_offsets(self):
        obj, _proxy = self.member()
        start = freeze_adjustment_reference(
            obj, (Reference(point=(200, 0, 0)), ["Face3"]), "LengthLimit", "Start"
        )
        end = freeze_adjustment_reference(
            obj, (Reference(point=(2800, 0, 0)), ["Face3"]), "LengthLimit", "End"
        )
        self.assertEqual((start.fixed_reference_offset, end.fixed_reference_offset), (200, 200))


if __name__ == "__main__":
    unittest.main()
