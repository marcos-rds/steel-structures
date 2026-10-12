"""Mutation failures in the structural native-recompute path preserve objects."""
from types import SimpleNamespace
import unittest

from tests.test_truss_manual_fixes import definition


class Shape:
    Volume = 100.

    def __init__(self, valid=True):
        self.valid = valid

    def copy(self):
        return Shape(self.valid)

    def isNull(self):
        return False

    def isValid(self):
        return self.valid


class Object:
    def __init__(self, document, name, **properties):
        self.Document, self.Name = document, name
        self.PropertiesList = list(properties)
        self.__dict__.update(properties)
        self.Proxy = SimpleNamespace(_updating=False, cache={"accepted": True})
        self.ViewObject = SimpleNamespace(Visibility=True, ShapeColor=(.2, .4, .6))
        self.enums, self.modes = {}, {}

    def addProperty(self, _kind, name, *_args):
        self.PropertiesList.append(name)
        setattr(self, name, "")

    def removeProperty(self, name):
        self.PropertiesList.remove(name)
        delattr(self, name)

    def getTypeIdOfProperty(self, name):
        return "App::PropertyEnumeration" if name in self.enums else "App::PropertyString"

    def getEnumerationsOfProperty(self, name):
        return self.enums[name]

    def getEditorMode(self, name):
        mode = self.modes.get(name, 0)
        return [label for flag, label in ((1, "ReadOnly"), (2, "Hidden")) if mode & flag]

    def setEditorMode(self, name, value):
        assert isinstance(value, int)
        self.modes[name] = value


class Document:
    def __init__(self):
        self.Objects = []

    def getObject(self, name):
        return next((value for value in self.Objects if value.Name == name), None)

    def removeObject(self, name):
        self.Objects.remove(self.getObject(name))

    def recompute(self):
        raise AssertionError("No nested recompute")

    def openTransaction(self, _label):
        raise AssertionError("No nested transaction")


class StructuralRecomputeRollbackTests(unittest.TestCase):
    def test_post_apply_validation_failure_restores_owner_members_groups_and_new_objects(self):
        document = Document()
        keep = Object(document, "Keep", Shape=Shape(), GenerationStatus="Valid", ControlledState="old",
                      State=[], GenerationKey="KEEP", Profile="old-profile")
        keep.enums["Profile"] = ["old-profile"]
        keep.modes["Profile"] = 3
        keep.ViewObject.Visibility = False
        obsolete = Object(document, "Obsolete")
        subgroup = Object(document, "Connectors", AssemblyInterconnectorGroup=True, Group=[obsolete])
        group = Object(document, "Group", TrussRole="TOP_CHORD", Group=[keep, obsolete, subgroup])
        owner = Object(document, "Owner", AppliedState="accepted", GeneratedMembers=[keep, obsolete],
                       GeneratedGussetPlates=[], RoleGroups=[group], NominalSpan=6000.)
        document.Objects = [owner, keep, obsolete, group, subgroup]
        original = list(document.Objects)
        spec = SimpleNamespace(section_geometry_mode="Detailed", color=(1., 0., 0.), assembly="Single")
        def item(key):
            return SimpleNamespace(key=key, role="TOP_CHORD", run_key=key, assembly_key="", component_key="",
                                   element_kind="Member", interconnector_key="", slot_key=None,
                                   generated_element_key="", spec=spec)
        candidate = SimpleNamespace(config={}, items=[item("KEEP"), item("NEW")])
        def create_member(doc, *_args, **_kwargs):
            child = Object(doc, "New", Shape=Shape(), State=[], GenerationStatus="Valid", ControlledState="")
            doc.Objects.append(child)
            return child
        def apply_result(child, _prepared, color):
            child.Shape = Shape()
            child.ViewObject.ShapeColor = color
            child.Proxy.cache = {"changed": True}
            if child == keep:
                child.Profile = "new-profile"
                child.addProperty("App::PropertyString", "NewOutput")
                child.NewOutput = "temporary"
        def set_config(obj, _config):
            obj.NominalSpan = 5900.
        def accept_state(obj, _candidate, result, plates):
            self.assertIs(document.getObject("Obsolete"), obsolete)
            self.assertIs(document.getObject("Connectors"), subgroup)
            obj.GeneratedMembers = list(result.values())
            obj.AppliedState = "candidate"
            keep.Shape = Shape(False)  # Simulates a failed native post-apply solid check.
        namespace = dict(resolve_linked_reference=lambda _doc, config, _obj: config,
                         decode_state=lambda _state: {"candidate": {"config": {}}, "bindings": {}},
                         build_candidate=lambda *_args: candidate,
                         bound_children=lambda *_args: {"KEEP": keep, "OLD": obsolete},
                         bound_gusset_plates=lambda *_args: {}, conflicts_for=lambda *_args: {},
                         plan_regeneration=lambda *_args: SimpleNamespace(conflicts=[]),
                         prepare_batch=lambda *_args: {"KEEP": None, "NEW": None},
                         prepare_gusset_plates=lambda *_args: {}, ensure_gusset_registry=lambda *_args: None,
                         set_config=set_config, create_member=create_member,
                         item_values=lambda _item: {"StartPoint": None, "EndPoint": None, "Profile": "new",
                                                   "Insertion": "centroid", "Rotation": 0.},
                         ROLE_LABELS={"TOP_CHORD": "Banzo"}, ROLES=("TOP_CHORD",),
                         apply_result=apply_result, controlled_state=lambda _child: "candidate",
                         dumps=lambda value: str(value), accept_state=accept_state)
        definition("truss.py", "snapshot_regeneration", namespace)
        definition("truss.py", "restore_regeneration", namespace)
        apply = definition("truss.py", "apply_truss", namespace)
        with self.assertRaisesRegex(ValueError, "Falha ao aplicar membro"):
            apply(document, {}, owner, _transaction=False, _recompute=False)
        self.assertEqual(document.Objects, original)
        self.assertEqual(owner.GeneratedMembers, [keep, obsolete])
        self.assertEqual(owner.AppliedState, "accepted")
        self.assertEqual(owner.NominalSpan, 6000.)
        self.assertEqual(group.Group, [keep, obsolete, subgroup])
        self.assertEqual(subgroup.Group, [obsolete])
        self.assertEqual(keep.Profile, "old-profile")
        self.assertEqual(keep.modes["Profile"], 3)
        self.assertEqual(keep.ControlledState, "old")
        self.assertTrue(keep.Shape.isValid())
        self.assertNotIn("NewOutput", keep.PropertiesList)
        self.assertEqual(keep.ViewObject.ShapeColor, (.2, .4, .6))
        self.assertFalse(keep.ViewObject.Visibility)
        self.assertEqual(keep.Proxy.cache, {"accepted": True})


if __name__ == "__main__":
    unittest.main()
