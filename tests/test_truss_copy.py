"""Focused ownership/rollback contracts; native movement is covered by the GUI gate."""
import json
from types import SimpleNamespace
import unittest

from tests.test_truss_manual_fixes import definition


class Proxy:
    pass


class Object:
    def __init__(self, name, **values):
        self.Name = name
        self.ViewObject = SimpleNamespace(Visibility=True, ShapeColor=(.2, .45, .85))
        self.__dict__.update(values)


class Document:
    def __init__(self):
        self.Objects = []
        self.fail = False
        self.calls = 0

    def copyObject(self, originals, recursive):
        assert recursive is False
        self.calls += 1
        copies = []
        for original in originals:
            target = Object(original.Name + "Copy", **{name: value for name, value in original.__dict__.items()
                                                     if name not in ("Name", "ViewObject")})
            copies.append(target)
            self.Objects.append(target)
            if self.fail:
                raise RuntimeError("native copy failure")
        mapping = dict(zip(originals, copies))
        for original, target in mapping.items():
            if hasattr(original, "Group"):
                target.Group = [mapping.get(child, child) for child in original.Group]
        return copies

    def removeObject(self, name):
        self.Objects = [child for child in self.Objects if child.Name != name]


class TrussCopyTests(unittest.TestCase):
    def setUp(self):
        self.doc = Document()
        self.source = Object("Original", Document=self.doc, Proxy=Proxy())
        self.copy = Object("Copy", Document=self.doc, Proxy=Proxy())
        self.member = Object("Member", Document=self.doc, GenerationOwner=self.source, GenerationKey="KEY")
        self.member.ExternalReference = object()
        self.member.ViewObject.Visibility = False
        self.plate = Object("Gusset", Document=self.doc, ParentTruss=self.source)
        self.subgroup = Object("Connectors", Group=[self.member], AssemblyInterconnectorGroup=True)
        self.group = Object("Role", Group=[self.member, self.subgroup])
        for owner in (self.source, self.copy):
            owner.GeneratedMembers = [self.member]
            owner.GeneratedGussetPlates = [self.plate]
            owner.RoleGroups = [self.group]
            owner.AppliedState = json.dumps(dict(bindings={"KEY": "Member"}, candidate={"unchanged": True}))
        self.doc.Objects = [self.source, self.copy, self.member, self.plate, self.group, self.subgroup]
        self.namespace = dict(StructuralTrussProxy=Proxy, decode_state=json.loads, dumps=json.dumps,
                              bound_children=lambda source, state: {"KEY": self.member},
                              bound_gusset_plates=lambda source: {"NODE": self.plate})
        self.restore = definition("truss.py", "restore_copied_children", self.namespace)

    def test_exact_shallow_copy_gets_its_own_complete_aggregate(self):
        self.restore(self.copy)
        child = self.copy.GeneratedMembers[0]
        plate = self.copy.GeneratedGussetPlates[0]
        group = self.copy.RoleGroups[0]
        self.assertIsNot(child, self.member)
        self.assertIs(child.GenerationOwner, self.copy)
        self.assertIs(plate.ParentTruss, self.copy)
        self.assertIs(group.Group[0], child)
        self.assertIs(group.Group[1].Group[0], child)
        self.assertEqual(json.loads(self.copy.AppliedState)["bindings"], {"KEY": child.Name})
        self.assertIs(child.ExternalReference, self.member.ExternalReference)
        self.assertEqual(child.ViewObject.ShapeColor, self.member.ViewObject.ShapeColor)
        self.assertFalse(child.ViewObject.Visibility)
        self.assertIs(self.source.GeneratedMembers[0], self.member)
        self.assertIs(self.member.GenerationOwner, self.source)

    def test_normal_restore_does_not_duplicate_children(self):
        self.restore(self.source)
        self.assertEqual(self.doc.calls, 0)

    def test_view_restored_before_copy_callback_gets_remapped(self):
        provider = definition("truss.py", "StructuralTrussViewProvider", {})
        proxy = object.__new__(provider)
        proxy.Object = self.copy
        proxy._hidden_children = {self.member.Name: True}
        self.copy.ViewObject.Proxy = proxy
        self.restore(self.copy)
        self.assertEqual(proxy._hidden_children, {self.copy.GeneratedMembers[0].Name: True})

    def test_mixed_owners_are_not_silently_repaired(self):
        foreign = Object("Foreign", GenerationOwner=Object("Other"))
        self.copy.GeneratedMembers.append(foreign)
        self.restore(self.copy)
        self.assertEqual(self.doc.calls, 0)

    def test_partial_registries_are_not_silently_repaired(self):
        self.copy.RoleGroups = []
        self.restore(self.copy)
        self.assertEqual(self.doc.calls, 0)

    def test_invalid_source_bindings_fail_before_mutation(self):
        def invalid(*_args):
            raise ValueError("Binding inconsistente")
        self.namespace["bound_children"] = invalid
        with self.assertRaisesRegex(ValueError, "Binding inconsistente"):
            self.restore(self.copy)
        self.assertEqual(self.doc.calls, 0)

    def test_external_group_content_is_not_copied(self):
        self.group.Group.append(Object("External"))
        with self.assertRaisesRegex(ValueError, "objetos externos"):
            self.restore(self.copy)
        self.assertEqual(self.doc.calls, 0)

    def test_copy_failure_removes_only_new_objects_and_keeps_registries(self):
        before = list(self.doc.Objects)
        self.doc.fail = True
        with self.assertRaisesRegex(RuntimeError, "native copy failure"):
            self.restore(self.copy)
        self.assertEqual(self.doc.Objects, before)
        self.assertEqual(self.copy.GeneratedMembers, [self.member])
        self.assertIs(self.member.GenerationOwner, self.source)

    def test_visibility_does_not_touch_foreign_members_or_gussets(self):
        provider = definition("truss.py", "StructuralTrussViewProvider", {})
        view = SimpleNamespace(Object=self.copy, Visibility=False)
        proxy = object.__new__(provider)
        self.member.ViewObject.Visibility = True
        proxy.onChanged(view, "Visibility")
        self.assertTrue(self.member.ViewObject.Visibility)
        self.assertTrue(self.plate.ViewObject.Visibility)
        self.assertEqual(proxy._hidden_children, {})

    def test_hidden_cache_is_remapped_only_for_copied_children(self):
        self.restore(self.copy)
        provider = definition("truss.py", "StructuralTrussViewProvider", {})
        proxy = object.__new__(provider)
        proxy.Object = self.copy
        proxy.loads(dict(hidden_children={self.member.Name: False, "External": True}))
        self.assertEqual(proxy._hidden_children, {self.copy.GeneratedMembers[0].Name: False, "External": True})

    def test_native_delete_cleans_only_its_complete_independent_aggregate(self):
        self.restore(self.copy)
        provider = definition("truss.py", "StructuralTrussViewProvider", {})
        proxy = object.__new__(provider)
        self.copy.ViewObject.Object = self.copy
        children = list(self.copy.GeneratedMembers)+list(self.copy.GeneratedGussetPlates)
        groups = list(self.copy.RoleGroups)
        groups += [g for group in self.copy.RoleGroups for g in group.Group
                   if getattr(g, "AssemblyInterconnectorGroup", False)]
        external = Object("ExternalReference")
        self.doc.Objects.append(external)
        self.copy.ReferenceSource = external
        before = list(self.doc.Objects)
        self.assertTrue(proxy.onDelete(self.copy.ViewObject, ()))
        self.assertEqual(self.doc.Objects, [o for o in before if o not in children+groups])
        self.assertIn(self.member, self.doc.Objects)
        self.assertIn(self.plate, self.doc.Objects)

    def test_native_delete_preserves_foreign_and_shared_registry_content(self):
        # An unrepaired shallow copy must never delete the source's children.
        provider = definition("truss.py", "StructuralTrussViewProvider", {})
        proxy = object.__new__(provider)
        self.copy.ViewObject.Object = self.copy
        before = list(self.doc.Objects)
        self.assertTrue(proxy.onDelete(self.copy.ViewObject, ()))
        self.assertEqual(self.doc.Objects, before)
        self.restore(self.copy)
        external = Object("ForeignMember", GenerationOwner=self.source)
        self.doc.Objects.append(external)
        group = self.copy.RoleGroups[0]
        group.Group.append(external)
        self.assertTrue(proxy.onDelete(self.copy.ViewObject, ()))
        self.assertIn(group, self.doc.Objects)
        self.assertIn(external, self.doc.Objects)


if __name__ == "__main__":
    unittest.main()
