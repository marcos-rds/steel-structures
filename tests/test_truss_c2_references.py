"""Reference contracts with transformed Draft fixtures; no FreeCAD required."""
import copy
import unittest
from types import SimpleNamespace
from tests.test_member_placement import Vector, Placement, Rotation
from tests.test_member_axis_source import DraftLine, Vector as LineVector, Curve
from tests.test_truss_qa import config
from freecad.SteelStructures.truss_reference import rectangle_geometry, source_geometry, selection_reference, resolve_linked_reference, reference_containers
from freecad.SteelStructures.trusses.reference_geometry import three_points
from freecad.SteelStructures.trusses.realization import build_candidate, plan_regeneration, transform_point, reference_frame


class Rectangle:
    __module__="draftobjects.rectangle"


def rectangle(length=6000.,height=1200.):
    own=Placement(Vector(10,20,30),Rotation(Vector(1,0,0),35))
    parent=Placement(Vector(100,200,300),Rotation(Vector(0,0,1),20))
    corners=[own.multVec(Vector(*p)) for p in ((0,0,0),(length,0,0),(length,height,0),(0,height,0))]
    edges=[SimpleNamespace(Curve=Curve(),Vertexes=[SimpleNamespace(Point=corners[i]),SimpleNamespace(Point=corners[(i+1)%4])]) for i in range(4)]
    return SimpleNamespace(TypeId="Part::Part2DObjectPython",Proxy=Rectangle(),Name="Rectangle",
        Length=length,Height=height,Placement=own,getGlobalPlacement=lambda:parent.multiply(own),
        Shape=SimpleNamespace(isNull=lambda:False,isValid=lambda:True,Edges=edges),
        getSubObject=lambda name:edges[int(name[-1])-1])


class C2ReferenceTests(unittest.TestCase):
    def test_rectangle_own_and_parent_placement_once_all_bases(self):
        source=rectangle()
        for edge,span,height in (("Edge1",6000,1200),("Edge2",1200,6000),("Edge3",6000,1200),("Edge4",1200,6000)):
            values=rectangle_geometry(source,edge)
            self.assertAlmostEqual(values["span"],span)
            self.assertAlmostEqual(values["height"],height)
            center=transform_point((span/2,height/2,0),reference_frame(values))
            expected=source.getGlobalPlacement().multVec(Vector(3000,600,0))
            for actual,wanted in zip(center,(expected.x,expected.y,expected.z)):
                self.assertAlmostEqual(actual,wanted)

    def test_rectangle_requires_base_even_if_square(self):
        source=rectangle(1000,1000)
        selected=selection_reference([SimpleNamespace(Object=source,SubElementNames=[])])
        self.assertEqual(selected[2],"")
        with self.assertRaises(ValueError): rectangle_geometry(source,selected[2])

    def test_rectangle_rejects_invalid_dimensions_stale_shape_and_curves(self):
        for name,value in (("Length",0),("Height",float("nan")),("Length",7000),("FilletRadius",10),("Rows",2)):
            source=rectangle(); setattr(source,name,value)
            with self.subTest(name=name,value=value),self.assertRaises(ValueError): rectangle_geometry(source,"Edge1")
        source=rectangle(); source.Shape.Edges[0].Curve=SimpleNamespace(isDerivedFrom=lambda _:False)
        with self.assertRaises(ValueError): rectangle_geometry(source,"Edge1")

    def test_line_reuses_axis_source_parent_transform(self):
        source=DraftLine(LineVector(1,2,3),LineVector(6001,2,3),LineVector(10,20,30))
        values=source_geometry(source,"DraftLine","Edge1",[0,0,1])
        self.assertEqual(values["start"],[11,22,33])
        self.assertEqual(values["end"],[6011,22,33])
        self.assertEqual(values["span"],6000.)

    def test_three_points_frame_and_apex(self):
        values=three_points((10,20,30),(10,6020,30),(10,1820,1230))
        self.assertEqual(values["span"],6000.)
        self.assertEqual(values["height"],1200.)
        self.assertEqual(values["apex_position"],.3)
        apex=transform_point((1800,1200,0),reference_frame(values))
        self.assertEqual(apex,(10.,1820.,1230.))
        for points in (((0,0,0),(0,0,0),(1,1,0)),((0,0,0),(10,0,0),(5,0,0)),
                       ((0,0,0),(10,0,0),(11,5,0)),((0,0,0),(10,0,0),(0,5,0))):
            with self.assertRaises(ValueError): three_points(*points)

    def test_line_plane_is_derived_from_working_plane_and_persisted(self):
        line=DraftLine(LineVector(),LineVector(100,0,100))
        values=source_geometry(line,"DraftLine","Edge1",[0,0,1])
        reference_frame(values)
        self.assertAlmostEqual(values["plane_normal"][0],-2**-.5)
        line.End=LineVector(0,0,100)
        values=source_geometry(line,"DraftLine","Edge1",[0,0,1],[0,1,0])
        self.assertEqual(values["plane_normal"],[-1.,0.,0.])

    def test_container_dependencies_reject_cycles(self):
        owner=SimpleNamespace(OutList=[])
        parent=SimpleNamespace(OutList=[owner],getParentGeoFeatureGroup=lambda:None)
        source=DraftLine(LineVector(),LineVector(6000,0,0)); source.getParentGeoFeatureGroup=lambda:parent
        self.assertEqual(reference_containers(source),[parent])
        args=config(reference_mode="DraftLine",reference_linked=True,reference_source="Line")
        with self.assertRaises(ValueError):
            resolve_linked_reference(SimpleNamespace(getObject=lambda _:source),args,owner)

    def test_linked_changes_plan_before_mutation_and_invalid_preserves_config(self):
        source=DraftLine(LineVector(),LineVector(6000,0,0)); source.Name="Line"
        document=SimpleNamespace(getObject=lambda name:source if name=="Line" else None)
        args=config(reference_mode="DraftLine",reference_linked=True,reference_source="Line",panelization_mode="ByTargetSpacing",target_spacing=1000.)
        old=build_candidate(resolve_linked_reference(document,args))
        source.End=LineVector(6100,0,0)
        same=build_candidate(resolve_linked_reference(document,args),old)
        self.assertFalse(plan_regeneration(same,old).structural)
        source.End=LineVector(8000,0,0)
        changed=build_candidate(resolve_linked_reference(document,args),old)
        self.assertTrue(plan_regeneration(changed,old).structural)
        before=copy.deepcopy(args)
        source.End=LineVector()
        with self.assertRaises(ValueError): resolve_linked_reference(document,args)
        self.assertEqual(args,before)
        with self.assertRaises(ValueError): resolve_linked_reference(SimpleNamespace(getObject=lambda _:None),args)
        args["reference_linked"]=False
        self.assertEqual(resolve_linked_reference(SimpleNamespace(getObject=lambda _:None),args),args)
