"""Integrity and arithmetic of read-only physical piece accounting."""
from copy import deepcopy
from types import SimpleNamespace as NS
import unittest

from freecad.SteelStructures.trusses.models import SCHEMA_VERSION, GENERATOR_VERSION
from freecad.SteelStructures.trusses.serialization import dumps, loads
from freecad.SteelStructures.trusses.physical_mass import read_physical_mass


class Shape:
    def __init__(self, volume=1000., kind="Solid", children=None, valid=True):
        self.Volume=volume
        self.ShapeType=kind
        self.children=children or []
        self.Solids=[self] if kind=="Solid" else [solid for child in self.children for solid in child.Solids]
        self.valid=valid
    def isNull(self): return self.ShapeType=="Null"
    def isValid(self): return self.valid
    def childShapes(self): return self.children


def fixture(plate=False):
    owner=NS(Name="Truss",State=[],NeedsRegeneration=False,GenerationState="Valid",RoleGroups=[])
    objects={owner.Name:owner}
    document=NS(getObject=objects.get,Objects=list(objects.values()),recompute=lambda:(_ for _ in ()).throw(AssertionError("recompute")))
    owner.Document=document
    config=dict(start=[0.,0.,0.],end=[3000.,4000.,0.],span=5000.,nominal_span=4500.,connection_intents={})
    members=[]
    for name,key,volume in (("A","run:A",1000.),("B","run:B",2000.),("Connector","run:connector",300.)):
        member=NS(Name=name,GenerationKey=key,GenerationOwner=owner,GenerationStatus="Valid",State=[],Shape=Shape(volume),Document=document,
                  ViewObject=NS(Visibility=False),TotalMass=99999.)
        members.append(member)
        objects[name]=member
    owner.GeneratedMembers=members
    owner.GeneratedGussetPlates=[]
    if plate:
        config["connection_intents"]={"node":dict(node_key="node",form="Gusset")}
        gusset=NS(Name="Plate",NodeKey="node",StableKey="node:gusset-plate",ParentTruss=owner,GeneratedByTruss=True,
                  GenerationStatus="Valid",State=[],Shape=Shape(400.),Document=document)
        owner.GeneratedGussetPlates=[gusset]
        objects[gusset.Name]=gusset
    document.Objects[:]=objects.values()
    state=dict(schema_version=SCHEMA_VERSION,generator_version=GENERATOR_VERSION,
               candidate=dict(config=config,items=[dict(key=child.GenerationKey) for child in members]),
               bindings={child.GenerationKey:child.Name for child in members})
    owner.AppliedState=dumps(state)
    return owner,objects


class PhysicalMassTests(unittest.TestCase):
    def test_simple_composite_and_connector_pieces_use_final_volumes_even_hidden(self):
        owner,_=fixture()
        result=read_physical_mass(owner)
        self.assertTrue(result.available,result.diagnostics)
        self.assertEqual(result.volume_mm3,3300.)
        self.assertAlmostEqual(result.mass_kg,3300.*.00000785)
        self.assertAlmostEqual(result.linear_mass_kg_m,result.mass_kg/5.)
        self.assertEqual(result.nominal_span_mm,4500.)
        self.assertEqual(result.support_distance_mm,5000.)
        owner.GeneratedMembers[0].Shape=Shape(750.)  # Final cut/fitted shape.
        self.assertEqual(read_physical_mass(owner).volume_mm3,3050.)

    def test_gusset_is_added_only_as_an_owned_physical_piece(self):
        owner,_=fixture(plate=True)
        result=read_physical_mass(owner)
        self.assertTrue(result.available,result.diagnostics)
        self.assertEqual(result.volume_mm3,3700.)
        self.assertEqual([piece.kind for piece in result.pieces].count("Gusset"),1)

    def test_groups_reference_objects_and_same_object_references_never_multiply_pieces(self):
        owner,objects=fixture(plate=True)
        owner.RoleGroups=[NS(Group=owner.GeneratedMembers+owner.GeneratedGussetPlates)]*3
        reference=NS(Name="DraftLine",Shape=Shape(1e12))
        objects[reference.Name]=reference
        owner.Document.Objects.append(reference)
        owner.GeneratedMembers*=2
        owner.GeneratedGussetPlates*=2
        result=read_physical_mass(owner)
        self.assertTrue(result.available,result.diagnostics)
        self.assertEqual(result.volume_mm3,3700.)
        self.assertEqual(len(result.pieces),4)

    def test_reader_never_writes_or_recomputes_or_uses_catalog_mass(self):
        owner,_=fixture()
        before=(owner.AppliedState,list(owner.Document.Objects),[vars(child).copy() for child in owner.GeneratedMembers])
        for _ in range(3):
            self.assertTrue(read_physical_mass(owner).available)
        self.assertEqual(owner.AppliedState,before[0])
        self.assertEqual(owner.Document.Objects,before[1])
        self.assertEqual([vars(child) for child in owner.GeneratedMembers],before[2])

    def test_invalid_pending_owner_and_child_preserved_old_shape_are_unavailable(self):
        for target,attribute,value in (("owner","GenerationState","Conflict"),("owner","NeedsRegeneration",True),
                ("owner","State",["Touched"]),("child","GenerationStatus","Erro: Shape anterior preservada"),
                ("child","State",["Invalid"]),("child","State",["Touched"])):
            with self.subTest(target=target,attribute=attribute):
                owner,_=fixture()
                setattr(owner if target=="owner" else owner.GeneratedMembers[0],attribute,value)
                self.assertFalse(read_physical_mass(owner).available)
                self.assertIsNone(read_physical_mass(owner).mass_kg)

    def test_invalid_non_solid_mixed_negative_and_nonfinite_volume_are_unavailable(self):
        for shape in (Shape(kind="Null"),Shape(valid=False),Shape(kind="Shell"),Shape(-2.),Shape(float("nan")),
                      Shape(1.,"Compound",[Shape(2.),Shape(-1.)]),
                      Shape(2.,"Compound",[Shape(2.),Shape(0.,"Edge")]),
                      Shape(2.,"Compound",[Shape(float("inf"))]),
                      Shape(4.,"Compound",[Shape(2.)])):
            with self.subTest(kind=shape.ShapeType,volume=shape.Volume):
                owner,_=fixture()
                owner.GeneratedMembers[0].Shape=shape
                self.assertFalse(read_physical_mass(owner).available)

    def test_valid_multisolid_compound_is_sum_of_its_solids(self):
        owner,_=fixture()
        owner.GeneratedMembers[0].Shape=Shape(1500.,"Compound",[Shape(700.),Shape(800.)])
        self.assertEqual(read_physical_mass(owner).volume_mm3,3800.)

    def test_missing_members_mismatched_binding_and_foreign_ownership_are_unavailable(self):
        for mode in ("missing","foreign","binding","expected"):
            owner,objects=fixture()
            if mode=="missing": del objects["A"]
            if mode=="foreign": owner.GeneratedMembers[0].GenerationOwner=NS(Name="Other")
            state=loads(owner.AppliedState)
            if mode=="binding": state["bindings"]["run:A"]="B"
            if mode=="expected": state["candidate"]["items"].pop()
            owner.AppliedState=dumps(state)
            self.assertFalse(read_physical_mass(owner).available,mode)

    def test_foreign_object_with_colliding_name_is_rejected_before_deduplication(self):
        for registry in ("GeneratedMembers","GeneratedGussetPlates"):
            owner,_=fixture(plate=True)
            originals=getattr(owner,registry)
            foreign=NS(**vars(originals[0]))
            originals.append(foreign)
            self.assertFalse(read_physical_mass(owner).available)

    def test_unregistered_owned_pieces_are_an_explicit_limitation(self):
        for plate in (False,True):
            owner,_=fixture(plate=plate)
            if plate: owner.GeneratedGussetPlates=[]
            else: owner.GeneratedMembers=owner.GeneratedMembers[1:]
            self.assertFalse(read_physical_mass(owner).available)

    def test_requested_nominal_or_missing_gusset_is_not_silently_zero(self):
        owner,_=fixture()
        state=loads(owner.AppliedState)
        state["candidate"]["config"]["connection_intents"]={"node":dict(form="Gusset")}
        owner.AppliedState=dumps(state)
        result=read_physical_mass(owner)
        self.assertFalse(result.available)
        self.assertIn("fallback nominal",result.diagnostics[0])

    def test_distinct_plates_at_same_node_are_rejected(self):
        owner,objects=fixture(plate=True)
        plate=NS(**vars(owner.GeneratedGussetPlates[0]))
        plate.Name="DuplicatePlate"
        objects[plate.Name]=plate
        owner.Document.Objects.append(plate)
        owner.GeneratedGussetPlates.append(plate)
        self.assertFalse(read_physical_mass(owner).available)

    def test_invalid_applied_state_supports_and_density_are_unavailable(self):
        for mode in ("json","schema","zero","nonfinite","bad_points"):
            owner,_=fixture()
            state=loads(owner.AppliedState)
            if mode=="schema": state["schema_version"]=999
            if mode=="zero": state["candidate"]["config"]["end"]=[0.,0.,0.]
            if mode=="bad_points": state["candidate"]["config"]["end"]=[0.,0.]
            owner.AppliedState="{" if mode=="json" else dumps(state)
            result=read_physical_mass(owner,float("nan") if mode=="nonfinite" else 7850.)
            self.assertFalse(result.available,mode)
        self.assertFalse(read_physical_mass(fixture()[0],0.).available)

    def test_independent_copy_quantities_do_not_reference_source_children(self):
        source,_=fixture(plate=True)
        copied=deepcopy(source)
        copied_objects={child.Name:child for child in copied.Document.Objects}
        copied.Document.getObject=copied_objects.get
        self.assertEqual(read_physical_mass(source).mass_kg,read_physical_mass(copied).mass_kg)
        copied.GeneratedMembers[0].Shape.Volume=800.
        self.assertEqual(source.GeneratedMembers[0].Shape.Volume,1000.)
