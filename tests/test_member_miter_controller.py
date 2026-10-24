"""Eligibility and bilateral transaction discipline with controlled documents.

Native gates independently exercise the real OCC pair evaluation and FCStd.
"""
import ast
from pathlib import Path
import types
import unittest
from unittest.mock import Mock

from freecad.SteelStructures.member_miter_geometry import MiterValidationError
from freecad.SteelStructures.member_adjustment_reference import would_create_adjustment_cycle


SOURCE = Path(__file__).resolve().parents[1] / "freecad/SteelStructures/interactive/member_miter_controller.py"


class Document:
    def __init__(self):
        self.objects = {}
        self.opens = self.commits = self.aborts = 0
        self.after_recompute = lambda: None
        self.recomputed = []

    def getObject(self, name): return self.objects.get(name)
    def openTransaction(self, title):
        self.opens += 1
        self.backup = {n: dict(o.__dict__) for n, o in self.objects.items()}
    def recompute(self, objects):
        self.recomputed.append(list(objects))
        for obj in objects: obj.State = ()
        self.after_recompute()
    def commitTransaction(self): self.commits += 1
    def abortTransaction(self):
        self.aborts += 1
        for name, values in self.backup.items():
            self.objects[name].__dict__.clear()
            self.objects[name].__dict__.update(values)


class MiterControllerTests(unittest.TestCase):
    def setUp(self):
        # Compile the actual controller; bypass only its native imports.
        tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
        node = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "MemberMiterController")
        definition = types.SimpleNamespace(geometry_type="i_section", geometry_variant="parallel_flange")
        self.namespace = dict(MiterValidationError=MiterValidationError,
            is_structural_member=lambda o: o is not None and getattr(o, "structural", False),
            profile_catalog=types.SimpleNamespace(get=lambda _: types.SimpleNamespace(definition=definition)),
            SUPPORTED_SECTIONS={("i_section", "parallel_flange")},
            would_create_adjustment_cycle=would_create_adjustment_cycle,
            global_member_shape=lambda obj: obj.Shape.copy(),
            signature=lambda obj: (obj.Name, obj.Profile, obj.StartAdjustmentMode, obj.EndAdjustmentMode),
            verify_adjustment_candidate=Mock(), validate_pair_shapes=Mock())
        exec(compile(ast.Module(body=[node], type_ignores=[]), str(SOURCE), "exec"), self.namespace)
        self.controller_type = self.namespace["MemberMiterController"]
        self.doc = Document()
        self.a, self.b = self.member("A"), self.member("B")
        self.controller = self.controller_type(self.doc, (self.a, self.b))

    def member(self, name):
        obj = types.SimpleNamespace(Name=name, Label=name, structural=True, Document=self.doc,
            GenerationOwner=None, AxisDefinitionMode="Independent", SectionGeometryMode="Detailed",
            Profile="W 150 x 13,0", State=(), ExpressionEngine=(), OutList=[], Shape=object(),
            StartAdjustmentMode="None", EndAdjustmentMode="None")
        self.doc.objects[name] = obj
        return obj

    def test_two_distinct_members_required(self):
        for members in ((), (self.a,), (self.a, self.a), (self.a, None)):
            with self.subTest(members=len(members)), self.assertRaises(MiterValidationError):
                self.controller_type(self.doc, members)._eligible()
        with self.assertRaises(MiterValidationError):
            self.controller_type(self.doc, (self.a, self.b, self.a))

    def test_selection_checks_duplicate_and_other_document(self):
        controller = self.controller_type(self.doc)
        controller.set_member(0, self.a)
        with self.assertRaisesRegex(MiterValidationError, "diferentes"):
            controller.set_member(1, self.a)
        self.b.Document = Document()
        with self.assertRaisesRegex(MiterValidationError, "documento"):
            controller.set_member(1, self.b)

    def test_current_eligibility_restrictions(self):
        for field, value in (("GenerationOwner", object()), ("AxisDefinitionMode", "Linked"),
                             ("AssemblySectionTransform", "{}"), ("PhysicalFitPlan", "{}"),
                             ("PhysicalFitAutoState", "{}"), ("ExpressionEngine", (("Length", "2"),)),
                             ("State", ("Invalid",)),
                             ("SectionGeometryMode", "Simplified"), ("Profile", "different")):
            with self.subTest(field=field):
                old = getattr(self.b, field, None)
                setattr(self.b, field, value)
                with self.assertRaises(MiterValidationError): self.controller._eligible()
                if old is None: delattr(self.b, field)
                else: setattr(self.b, field, old)
        self.controller._eligible()

    def test_deleted_and_foreign_objects_rejected(self):
        self.doc.objects.pop("B")
        with self.assertRaisesRegex(MiterValidationError, "indisponível"):
            self.controller._eligible()

    def test_existing_direct_or_transitive_dependency_rejected(self):
        for bridge in (self.b, types.SimpleNamespace(Name="bridge", State=(), OutList=[self.b])):
            self.a.OutList = [bridge]
            with self.assertRaisesRegex(MiterValidationError, "dependem"):
                self.controller._eligible()

    def test_pending_dependency_rejected(self):
        self.a.OutList = [types.SimpleNamespace(Name="source", State=("Touched",), OutList=[])]
        with self.assertRaisesRegex(MiterValidationError, "referências"):
            self.controller._eligible()

    def test_source_watch_includes_transitive_states_even_with_unchanged_shapes(self):
        source = types.SimpleNamespace(Name="source", State=(), OutList=[])
        bridge = types.SimpleNamespace(Name="bridge", State=(), OutList=[source])
        self.a.OutList = [bridge, source]
        before = self.controller._source_states(self.a)
        source.State = ("Touched",)
        self.assertNotEqual(before, self.controller._source_states(self.a))
        self.assertEqual(self.controller._source_states(self.a),
                         (("bridge", ()), ("source", ("Touched",))))
        # Identity deduplication also terminates an invalid dependency cycle.
        source.OutList = [bridge]
        self.assertEqual(len(self.controller._source_states(self.a)), 2)

    def test_replay_pending_members_recompute_locally_without_transaction(self):
        outsider = self.member("Outside")
        for obj in (self.a, self.b, outsider): obj.State = ("Touched",)
        self.controller.prepare_inputs()
        self.assertEqual(self.doc.recomputed, [[self.a, self.b]])
        self.assertEqual((self.a.State, self.b.State, outsider.State), ((), (), ("Touched",)))
        self.assertEqual((self.doc.opens, self.doc.commits, self.doc.aborts), (0, 0, 0))

    def test_clean_members_do_not_recompute(self):
        self.controller.prepare_inputs()
        self.assertEqual(self.doc.recomputed, [])

    def test_only_pending_participant_recomputes(self):
        self.a.State = ("Recompute",)
        self.controller.prepare_inputs()
        self.assertEqual(self.doc.recomputed, [[self.a]])

    def test_pending_source_blocks_before_either_member_recomputes(self):
        self.a.State = ("Touched",)
        self.b.OutList = [types.SimpleNamespace(Name="source", State=("Touched",), OutList=[])]
        with self.assertRaisesRegex(MiterValidationError, "referências"):
            self.controller.prepare_inputs()
        self.assertEqual(self.doc.recomputed, [])
        self.assertEqual(self.a.State, ("Touched",))

    def test_invalid_second_member_blocks_before_first_recomputes(self):
        self.a.State, self.b.State = ("Touched",), ("Invalid",)
        with self.assertRaisesRegex(MiterValidationError, "inválido"):
            self.controller.prepare_inputs()
        self.assertEqual(self.doc.recomputed, [])

    def test_recompute_cannot_hide_remaining_pending_or_changed_inputs(self):
        for update in (lambda: setattr(self.a, "State", ("Touched",)),
                       lambda: setattr(self.a, "Profile", "changed")):
            with self.subTest(update=update):
                self.a.Profile, self.a.State = "W 150 x 13,0", ("Touched",)
                self.doc.after_recompute = update
                with self.assertRaises(MiterValidationError): self.controller.prepare_inputs()

    def prepared(self):
        values = [{"StartAdjustmentMode": "Fixed"}, {"EndAdjustmentMode": "Fixed"}]
        candidate = types.SimpleNamespace(members=(self.a, self.b),
            candidates=tuple(types.SimpleNamespace(values=v) for v in values),
            plan=types.SimpleNamespace(ends=("Start", "End")))
        # Shape native geometry verification is separately tested in the gate.
        for obj in (self.a, self.b): obj.Shape = types.SimpleNamespace(copy=lambda: object())
        self.controller.evaluate = Mock(return_value=candidate)
        self.controller._preserved = lambda obj, end: (obj.Name, getattr(obj, "nominal", 100.))
        return candidate

    def test_one_transaction_contains_both_outputs_before_verification(self):
        candidate = self.prepared()
        observed = []
        self.namespace["verify_adjustment_candidate"].side_effect = lambda *_: observed.append(
            (self.a.StartAdjustmentMode, self.b.EndAdjustmentMode))
        self.assertIs(self.controller.apply(), candidate)
        self.assertEqual(observed, [("Fixed", "Fixed"), ("Fixed", "Fixed")])
        self.assertEqual((self.doc.opens, self.doc.commits, self.doc.aborts), (1, 1, 0))
        self.assertEqual(self.doc.recomputed, [[self.a, self.b]])
        self.controller.evaluate.assert_called_once_with()

    def test_late_failure_rolls_back_both_inputs(self):
        self.prepared()
        self.namespace["verify_adjustment_candidate"].side_effect = (None, ValueError("late failure"))
        with self.assertRaisesRegex(ValueError, "late failure"): self.controller.apply()
        self.assertEqual((self.a.StartAdjustmentMode, self.b.EndAdjustmentMode), ("None", "None"))
        self.assertEqual((self.doc.opens, self.doc.commits, self.doc.aborts), (1, 0, 1))

    def test_pair_verification_failure_rolls_back_both(self):
        self.prepared()
        self.namespace["validate_pair_shapes"].side_effect = ValueError("pair failed")
        with self.assertRaisesRegex(ValueError, "pair failed"): self.controller.apply()
        self.assertEqual((self.a.StartAdjustmentMode, self.b.EndAdjustmentMode), ("None", "None"))
        self.assertEqual(self.doc.commits, 0)

    def test_nominal_output_drift_aborts_both(self):
        self.prepared()
        self.doc.after_recompute = lambda: setattr(self.a, "nominal", 99.)
        with self.assertRaisesRegex(MiterValidationError, "fora das pontas"): self.controller.apply()
        self.assertFalse(hasattr(self.a, "nominal"))
        self.assertEqual(self.doc.aborts, 1)

    def test_revalidation_failure_never_opens_transaction(self):
        self.controller.evaluate = Mock(side_effect=MiterValidationError("new invalid inputs"))
        with self.assertRaises(MiterValidationError): self.controller.apply()
        self.assertEqual((self.doc.opens, self.doc.commits, self.doc.aborts), (0, 0, 0))


if __name__ == "__main__": unittest.main()
