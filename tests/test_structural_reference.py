"""Read-only nominal references: hierarchy, freshness and generated provenance."""
import dataclasses
import json
import math
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from freecad.SteelStructures.structural_reference import (
    AxisReadContext, axis_state_signature, resolve_member_axis,
)

try:
    from .test_member_placement import Vector, Rotation as BaseRotation, mat_vec, transpose
except ImportError:
    from test_member_placement import Vector, Rotation as BaseRotation, mat_vec, transpose


class Rotation(BaseRotation):
    def multVec(self, value):
        return mat_vec(self.matrix, value)

    def multiply(self, other):
        return Rotation(matrix=super().multiply(other).matrix)

    @property
    def Q(self):
        # Generated fixtures below use identity orientation. Rotated fixtures
        # validate the resolved vectors without consulting serialized quaternions.
        if self.matrix != Rotation().matrix:
            raise AssertionError("Quaternion requested for a non-generated fixture")
        return (0., 0., 0., 1.)


class Placement:
    def __init__(self, base=None, rotation=None):
        self.Base = base or Vector()
        self.Rotation = rotation or Rotation()

    def multVec(self, point):
        return self.Rotation.multVec(point).add(self.Base)

    def multiply(self, other):
        return Placement(self.multVec(other.Base), self.Rotation.multiply(other.Rotation))

    def inverse(self):
        inverse = Rotation(matrix=transpose(self.Rotation.matrix))
        return Placement(inverse.multVec(self.Base)*-1, inverse)


class StructuralMemberProxy:
    __module__ = "freecad.SteelStructures.member"


class StructuralTrussProxy:
    __module__ = "freecad.SteelStructures.truss"


class Document:
    def __init__(self):
        self.objects = {}
        self.Name = "TestDocument"

    def getObject(self, name):
        return self.objects.get(name)

    def recompute(self, *args):
        raise AssertionError("read-only resolution cannot recompute")


class Member:
    TypeId = "Part::FeaturePython"

    def __init__(self):
        self.Name = "StructuralMember"
        self.Proxy = StructuralMemberProxy()
        self.Document = Document()
        self.Document.objects[self.Name] = self
        self.StartPoint, self.EndPoint = Vector(10, 20, 30), Vector(10, 20, 1030)
        self.Placement = Placement(self.StartPoint)
        self.AxisDefinitionMode = "Independent"
        self.AxisSource = None
        self.GenerationOwner = None
        self.State = ()
        self.parent = None
        self.ExpressionEngine = ()
        self.Profile = "SHS"
        self.Insertion = "Centroide"
        self.Rotation = SimpleNamespace(Value=0.)
        self.SectionGeometryMode = "Detailed"

    @property
    def Shape(self):
        raise AssertionError("nominal references must never read Shape")

    @property
    def ViewObject(self):
        raise AssertionError("axis resolution must not read presentation")

    def getGlobalPlacement(self):
        return (self.parent.getGlobalPlacement().multiply(self.Placement)
                if self.parent else self.Placement)

    def getParentGeoFeatureGroup(self):
        return self.parent


class Part:
    TypeId = "App::Part"
    State = ()

    def __init__(self, member, name, placement, parent=None):
        self.Name, self.Placement, self.parent = name, placement, parent
        self.Document = member.Document

    def getGlobalPlacement(self):
        return (self.parent.getGlobalPlacement().multiply(self.Placement)
                if self.parent else self.Placement)

    def getParentGeoFeatureGroup(self):
        return self.parent


def xyz(point):
    return (point.x, point.y, point.z)


def generated(member):
    owner = SimpleNamespace(Name="Truss", Proxy=StructuralTrussProxy(),
                            Document=member.Document, State=(),
                            GenerationState="Valid", NeedsRegeneration=False,
                            GeneratedMembers=[member])
    member.Document.objects[owner.Name] = owner
    member.GenerationOwner = owner
    member.GenerationKey = "run:A"
    member.GenerationStatus = "Valid"
    owner.AppliedState = json.dumps({
        "schema_version": 2, "generator_version": 1,
        "bindings": {member.GenerationKey: member.Name},
        "candidate": {"items": [{"key": member.GenerationKey,
                                   "start_global": xyz(member.StartPoint),
                                   "end_global": xyz(member.EndPoint),
                                   "section_u_global": (1, 0, 0),
                                   "spec": {"rotation": 0.}}]}})
    member.ControlledState = json.dumps({
        "StartPoint": xyz(member.StartPoint), "EndPoint": xyz(member.EndPoint),
        "Profile": member.Profile, "Insertion": member.Insertion,
        "Rotation": member.Rotation.Value, "SectionGeometryMode": "Detailed",
        "AxisDefinitionMode": "Independent", "AxisSource": "None",
        "Placement": list(xyz(member.Placement.Base))+list(member.Placement.Rotation.Q),
        "Color": [1, 2, 3]})
    return owner


def generated_pair():
    first, second = Member(), Member()
    owner = generated(first)
    second_owner = generated(second)
    state = json.loads(owner.AppliedState)
    second_item = json.loads(second_owner.AppliedState)["candidate"]["items"][0]
    second.Name, second.GenerationKey = "StructuralMember002", "run:B"
    second.Document, second.GenerationOwner = first.Document, owner
    first.Document.objects[second.Name] = second
    owner.GeneratedMembers.append(second)
    state["bindings"][second.GenerationKey] = second.Name
    second_item["key"] = second.GenerationKey
    state["candidate"]["items"].append(second_item)
    owner.AppliedState = json.dumps(state)
    return first, second, owner


def replay_owner(first, owner):
    """Complete the owner metadata used only by trusted-history fixtures."""
    owner.ID, owner.Placement = 43, Placement()
    owner.C2Configuration = "{}"
    owner.ReferenceLinked, owner.ReferenceSource = False, None
    owner.ReferenceContainers, owner.ExpressionEngine = (), ()
    owner.RoleGroups, owner.GeneratedGussetPlates = [], []
    owner.getParentGeoFeatureGroup = lambda: None
    state = json.loads(owner.AppliedState)
    state["candidate"]["config"] = {}
    owner.AppliedState = json.dumps(state)
    first.ID = 42
    return owner


class StructuralReferenceTests(unittest.TestCase):
    def assertPoint(self, actual, expected):
        self.assertLess(math.dist(actual, expected), 1e-7)

    def test_root_axis_is_nominal_and_detached(self):
        member = Member()
        before = dict(vars(member))
        axis = resolve_member_axis(member).axis
        self.assertEqual(axis.start, (10., 20., 30.))
        self.assertEqual(axis.end, (10., 20., 1030.))
        self.assertEqual(axis.frame, ((1., 0., 0.), (0., 1., 0.), (0., 0., 1.)))
        self.assertEqual(vars(member), before)
        with self.assertRaises(dataclasses.FrozenInstanceError):
            axis.key = "changed"
        member.StartPoint.x = 100
        self.assertEqual(axis.start, (10., 20., 30.))

    def test_effective_cut_base_and_section_offsets_do_not_move_nominal_axis(self):
        member = Member()
        member.Placement.Base = Vector(10, 20, 130)
        member.OffsetX = 80
        member.OffsetY = -35
        member.Insertion = "Canto superior esquerdo"
        member.StartFixedReferenceOffset = 100
        member.StartExtension = 500
        axis = resolve_member_axis(member).axis
        self.assertEqual(axis.start, (10., 20., 30.))
        self.assertEqual(axis.end, (10., 20., 1030.))

    def test_nested_parents_applied_once_and_real_roll_preserved(self):
        member = Member()
        member.Placement.Rotation = Rotation(Vector(0, 0, 1), 29)
        outer = Part(member, "Outer", Placement(Vector(100, 200, 300), Rotation(Vector(0, 1, 0), 37)))
        inner = Part(member, "Inner", Placement(Vector(20, -30, 40), Rotation(Vector(1, 0, 0), -19)), outer)
        member.parent = inner
        axis = resolve_member_axis(member).axis
        parent = outer.Placement.multiply(inner.Placement)
        self.assertPoint(axis.start, xyz(parent.multVec(member.StartPoint)))
        self.assertPoint(axis.end, xyz(parent.multVec(member.EndPoint)))
        self.assertPoint(axis.frame[0], xyz(member.getGlobalPlacement().Rotation.multVec(Vector(1, 0, 0))))
        self.assertEqual(axis.parents, ("Inner", "Outer"))
        old_start = axis.start
        outer.Placement.Base.x += 50
        self.assertPoint(resolve_member_axis(member).axis.start, (old_start[0]+50, *old_start[1:]))

    def test_directions_and_order_keep_frame_direction(self):
        for direction in (Vector(1, 0, 0), Vector(0, 1, 0), Vector(0, 0, -1), Vector(1, 2, 3)):
            member = Member()
            direction.normalize()
            member.EndPoint = member.StartPoint.add(direction*1000)
            member.Placement.Rotation = Rotation(Vector(0, 0, 1), direction)
            axis = resolve_member_axis(member).axis
            self.assertIsNotNone(axis)
            self.assertPoint(axis.frame[2], xyz(direction))

    def test_freshness_linked_foreign_objects_and_removed_members_are_refused(self):
        for state in ("Touched", "Invalid", "Recompute"):
            member = Member()
            member.State = (state,)
            self.assertIsNone(resolve_member_axis(member).axis)
        member = Member()
        member.AxisDefinitionMode = "Linked"
        self.assertIsNone(resolve_member_axis(member).axis)
        member = Member()
        member.TypeId = "App::Link"
        self.assertIsNone(resolve_member_axis(member).axis)
        member = Member()
        member.Document.objects.clear()
        self.assertIsNone(resolve_member_axis(member).axis)
        self.assertIsNone(resolve_member_axis(None).axis)

    def test_invalid_axis_frame_and_container_are_refused(self):
        changes = [lambda m: setattr(m, "EndPoint", m.StartPoint),
                   lambda m: setattr(m, "StartPoint", Vector(math.nan, 0, 0)),
                   lambda m: setattr(m.Placement, "Rotation", Rotation(Vector(0, 1, 0), 90)),
                   lambda m: setattr(m.Placement, "Rotation", Rotation(matrix=((2, 0, 0), (0, 1, 0), (0, 0, 1))))]
        for change in changes:
            member = Member()
            change(member)
            self.assertIsNone(resolve_member_axis(member).axis)
        member = Member()
        member.parent = Part(member, "Unsupported", Placement())
        member.parent.TypeId = "App::Link"
        self.assertIsNone(resolve_member_axis(member).axis)
        member.parent.TypeId = "App::Part"
        member.parent.parent = member.parent
        self.assertIsNone(resolve_member_axis(member).axis)

    def test_generated_physical_child_accepts_valid_snapshot_without_render_access(self):
        member = Member()
        generated(member)
        result = resolve_member_axis(member)
        self.assertIsNotNone(result.axis, result.reason)
        self.assertEqual(result.axis.category, "generated_member")

    def test_generated_pending_conflict_and_needs_regeneration_are_refused(self):
        for change in (lambda m, o: setattr(o, "GenerationState", "Pending"),
                       lambda m, o: setattr(o, "GenerationState", "Conflict"),
                       lambda m, o: setattr(o, "NeedsRegeneration", True),
                       lambda m, o: setattr(m, "GenerationStatus", "Erro"),
                       lambda m, o: setattr(o, "State", ("Touched",))):
            member = Member()
            owner = generated(member)
            change(member, owner)
            self.assertIsNone(resolve_member_axis(member).axis)

    def test_generated_binding_schema_and_accepted_geometry_are_checked(self):
        for mutation in (lambda s: s.update(schema_version=999),
                         lambda s: s["bindings"].update({"run:A": "Wrong"}),
                         lambda s: s["candidate"]["items"][0].update(start_global=[11, 20, 30]),
                         lambda s: s["candidate"]["items"][0].update(section_u_global=[0, 1, 0]),
                         lambda s: s["candidate"].update(items=[])):
            member = Member()
            owner = generated(member)
            state = json.loads(owner.AppliedState)
            mutation(state)
            owner.AppliedState = json.dumps(state)
            self.assertIsNone(resolve_member_axis(member).axis)

    def test_generated_direct_input_edits_and_incomplete_snapshots_are_refused(self):
        member = Member()
        generated(member)
        member.Profile = "Changed"
        self.assertIsNone(resolve_member_axis(member).axis)
        member.Profile = "SHS"
        member.ControlledState = "{}"
        self.assertIsNone(resolve_member_axis(member).axis)

    def test_generated_malformed_payloads_and_duplicate_registry_are_refused(self):
        for value in ("", "null", "[]", '{"schema_version":NaN}', "broken"):
            member = Member()
            owner = generated(member)
            owner.AppliedState = value
            self.assertIsNone(resolve_member_axis(member).axis)
        member = Member()
        owner = generated(member)
        owner.GeneratedMembers.append(member)
        self.assertIsNone(resolve_member_axis(member).axis)

    def test_transactional_replay_cannot_publish_intermediate_reference(self):
        member = Member()
        member.Document.Transacting = True
        self.assertIsNone(resolve_member_axis(member).axis)
        member.Document.Transacting = False
        self.assertIsNotNone(resolve_member_axis(member).axis)

    def test_generated_transform_is_explicitly_outside_proven_domain(self):
        member = Member()
        generated(member)
        member.parent = Part(member, "Moved", Placement(Vector(50, 0, 0)))
        self.assertIsNone(resolve_member_axis(member).axis)

    def test_batch_decodes_owner_once_with_linear_registry_reads(self):
        from freecad.SteelStructures.trusses.serialization import decode_state

        first, second, _owner = generated_pair()
        context = AxisReadContext()
        with patch("freecad.SteelStructures.trusses.serialization.decode_state",
                   wraps=decode_state) as decode, patch.object(
                       first.Document, "getObject", wraps=first.Document.getObject) as lookup:
            for member in (first, second):
                result = resolve_member_axis(member, context=context)
                self.assertIsNotNone(result.axis, result.reason)
            self.assertEqual(decode.call_count, 1)
            # One identity lookup per child, one per binding and one owner.
            self.assertEqual(lookup.call_count, 5)
        with patch("freecad.SteelStructures.trusses.serialization.decode_state",
                   wraps=decode_state) as decode:
            self.assertIsNotNone(resolve_member_axis(first).axis)
            self.assertIsNotNone(resolve_member_axis(second).axis)
            self.assertEqual(decode.call_count, 2)

    def test_new_batch_revalidates_owner_state_and_accepted_geometry(self):
        first, second, owner = generated_pair()
        context = AxisReadContext()
        self.assertIsNotNone(resolve_member_axis(first, context=context).axis)
        self.assertIsNotNone(resolve_member_axis(second, context=context).axis)
        del context  # A context never crosses mutations/event-loop yields.
        owner.GenerationState = "Pending"
        self.assertIsNone(resolve_member_axis(first, context=AxisReadContext()).axis)
        owner.GenerationState = "Valid"
        state = json.loads(owner.AppliedState)
        state["candidate"]["items"][0]["start_global"][0] += 1
        owner.AppliedState = json.dumps(state)
        self.assertIsNone(resolve_member_axis(first, context=AxisReadContext()).axis)

    def test_batch_owner_acceptance_does_not_bypass_child_controlled_inputs(self):
        first, second, _owner = generated_pair()
        second.Profile = "Changed"
        context = AxisReadContext()
        self.assertIsNotNone(resolve_member_axis(first, context=context).axis)
        self.assertIsNone(resolve_member_axis(second, context=context).axis)

    def test_batch_caches_invalid_owner_without_repeated_payload_decode(self):
        from freecad.SteelStructures.trusses.serialization import decode_state

        first, second, owner = generated_pair()
        owner.AppliedState = "broken"
        context = AxisReadContext()
        with patch("freecad.SteelStructures.trusses.serialization.decode_state",
                   wraps=decode_state) as decode:
            for member in (first, second):
                self.assertIsNone(resolve_member_axis(member, context=context).axis)
            self.assertEqual(decode.call_count, 1)

    def test_reacquisition_does_not_keep_deleted_object_wrapper(self):
        old = Member()
        restored = Member()
        old.Document.objects[old.Name] = restored
        self.assertIsNone(resolve_member_axis(old).axis)
        self.assertIsNotNone(resolve_member_axis(restored).axis)

    def test_known_clean_signature_can_be_read_only_replay_evidence(self):
        member = Member()
        self.assertIsNotNone(resolve_member_axis(member).axis)
        signature = axis_state_signature(member)
        self.assertIsNotNone(signature)
        for flags in (("Touched",), ("Recompute",), ("Touched", "Recompute")):
            member.State = flags
            self.assertEqual(axis_state_signature(member), signature)
            self.assertIsNone(resolve_member_axis(member).axis)
            self.assertIsNone(resolve_member_axis(member, context=AxisReadContext()).axis)
            context = AxisReadContext(trusted_replay={member.Name: {signature}})
            self.assertIsNotNone(resolve_member_axis(member, context=context).axis)

    def test_unknown_or_materially_changed_replay_signature_remains_blocked(self):
        changes = (
            lambda m: setattr(m, "EndPoint", Vector(10, 20, 2030)),
            lambda m: setattr(m, "Profile", "Other profile"),
            lambda m: setattr(m, "OffsetX", SimpleNamespace(Value=20)),
            lambda m: setattr(m, "StartFixedReferenceOffset", SimpleNamespace(Value=80)),
            lambda m: setattr(m, "AdjustedLength", SimpleNamespace(Value=900)),
            lambda m: setattr(m.Placement, "Base", Vector(10, 20, 80)),
        )
        for change in changes:
            member = Member()
            signature = axis_state_signature(member)
            change(member)
            member.State = ("Touched",)
            context = AxisReadContext(trusted_replay={member.Name: {signature}})
            self.assertIsNone(resolve_member_axis(member, context=context).axis)

    def test_replay_never_bypasses_invalid_or_transaction_states(self):
        member = Member()
        signature = axis_state_signature(member)
        context = AxisReadContext(trusted_replay={member.Name: {signature}})
        member.State = ("Invalid", "Touched")
        self.assertIsNone(axis_state_signature(member))
        self.assertIsNone(resolve_member_axis(member, context=context).axis)
        member.State = ("Touched",)
        member.Document.Transacting = True
        self.assertIsNone(axis_state_signature(member))
        self.assertIsNone(resolve_member_axis(member, context=context).axis)

    def test_replay_signature_excludes_presentation_and_tracks_native_identity(self):
        member = Member()
        member.ID = 42
        signature = axis_state_signature(member)
        member.Label = "Custom name"
        member.DisplayName = "Presentation only"
        self.assertEqual(axis_state_signature(member), signature)
        member.ID = 43
        self.assertNotEqual(axis_state_signature(member), signature)
        member.State = ("Touched",)
        context = AxisReadContext(trusted_replay={member.Name: {signature}})
        self.assertIsNone(resolve_member_axis(member, context=context).axis)

    def test_generated_expressions_and_live_references_do_not_get_replay_evidence(self):
        member = Member()
        generated(member)
        self.assertIsNone(axis_state_signature(member))
        member = Member()
        member.ExpressionEngine = (("Length", "2000 mm"),)
        self.assertIsNone(axis_state_signature(member))
        member.ExpressionEngine = ()
        member.StartAdjustmentMode = "Associative"
        self.assertIsNone(axis_state_signature(member))
        member.StartAdjustmentMode = "Fixed"
        member.StartAdjustmentReference = (object(), ["Face1"])
        self.assertIsNone(axis_state_signature(member))

    def test_foreign_proxy_with_the_same_class_name_is_not_a_workbench_member(self):
        member = Member()
        foreign = type("StructuralMemberProxy", (), {"__module__": "other_addon.member"})
        member.Proxy = foreign()
        self.assertIsNone(resolve_member_axis(member).axis)

    def test_generated_known_history_restores_member_and_owner_without_recompute(self):
        member = Member()
        owner = replay_owner(member, generated(member))
        self.assertIsNotNone(resolve_member_axis(member).axis)
        signature = axis_state_signature(member, context=AxisReadContext())
        self.assertIsNotNone(signature)
        owner.State = member.State = ("Touched",)
        self.assertIsNone(resolve_member_axis(member).axis)
        context = AxisReadContext(trusted_replay={member.Name: {signature}})
        self.assertIsNotNone(resolve_member_axis(member, context=context).axis)

    def test_generated_trusted_child_cannot_authorize_unknown_sibling(self):
        first, second, owner = generated_pair()
        replay_owner(first, owner)
        signature = axis_state_signature(first, context=AxisReadContext())
        owner.State = first.State = second.State = ("Touched",)
        context = AxisReadContext(trusted_replay={first.Name: {signature}})
        self.assertIsNotNone(resolve_member_axis(first, context=context).axis)
        self.assertIsNone(resolve_member_axis(second, context=context).axis)

    def test_generated_replay_detects_owner_inputs_registry_and_invalid_state(self):
        for change in (
            lambda o: setattr(o, "Span", 7000.),
            lambda o: setattr(o, "NeedsRegeneration", True),
            lambda o: setattr(o, "GenerationState", "Pending"),
            lambda o: setattr(o, "State", ("Touched", "Invalid")),
            lambda o: setattr(o, "GeneratedMembers", []),
            lambda o: setattr(o, "ReferenceLinked", True),
        ):
            member = Member()
            owner = replay_owner(member, generated(member))
            signature = axis_state_signature(member, context=AxisReadContext())
            owner.State = member.State = ("Touched",)
            change(owner)
            context = AxisReadContext(trusted_replay={member.Name: {signature}})
            self.assertIsNone(resolve_member_axis(member, context=context).axis)

    def test_generated_owner_fingerprint_is_computed_once_per_read_batch(self):
        from freecad.SteelStructures import structural_reference as reader
        first, second, owner = generated_pair()
        replay_owner(first, owner)
        with patch.object(reader, "_owner_replay_fingerprint", wraps=reader._owner_replay_fingerprint) as read:
            context = AxisReadContext()
            self.assertIsNotNone(axis_state_signature(first, context=context))
            self.assertIsNotNone(axis_state_signature(second, context=context))
            self.assertEqual(read.call_count, 1)


if __name__ == "__main__":
    unittest.main()
