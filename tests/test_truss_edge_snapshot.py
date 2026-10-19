"""Pure validation contracts; actual Placement/Part behavior is gated natively."""
import math
import sys
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch

from freecad.SteelStructures import truss_edge_snapshot as capture
from tests import test_truss_reference_controls as reference_controls


class EdgeCaptureTests(unittest.TestCase):
    def setUp(self):
        self.edge=NS(ShapeType='Edge',isNull=lambda:False,isValid=lambda:True,
                     Vertexes=(object(),object()),Curve=NS(isDerivedFrom=lambda name:True),
                     FirstParameter=0.,LastParameter=4500.,Length=4500.,
                     valueAt=lambda t:NS(x=123.+t,y=456.,z=789.))
        self.source=NS(Name='PhysicalProfile',ID=17,
                       Shape=NS(isNull=lambda:False,isValid=lambda:True))
        self.paths=[]
        self.root=NS(getSubObject=lambda path:self.paths.append(path) or self.edge)
        self.part=patch.dict(sys.modules,Part=NS(Precision=NS(isInfinite=lambda v:abs(v)>1e99)))
        self.part.start()
        self.addCleanup(self.part.stop)

    def read(self):
        return capture.capture_edge(self.root,self.source,'Parent.PhysicalProfile.Edge3','Edge3',[0,0,1],[0,1,0])

    def test_snapshot_contains_only_full_precision_coordinates_and_no_dependency(self):
        selected,values,origin=self.read()
        self.assertEqual(selected,dict(reference_mode='TwoPoints',reference_source='',reference_edge='',
                                       reference_linked=False,reference_defined=True))
        self.assertEqual(values['start'],[123.,456.,789.])
        self.assertEqual(values['end'],[4623.,456.,789.])
        self.assertEqual(values['span'],4500.)
        self.assertEqual(self.paths,['Parent.PhysicalProfile.Edge3'])
        self.assertEqual(origin,dict(name='PhysicalProfile',object_id=17,edge='Edge3'))
        self.assertFalse(set(origin)&set(selected))

    def test_rejects_face_vertex_whole_object_and_missing_edge(self):
        for path,index in (('Face1','Face1'),('Vertex1','Vertex1'),('','')):
            with self.subTest(index=index),self.assertRaises(ValueError):
                capture.capture_edge(self.root,self.source,path,index,[0,0,1],[0,1,0])
        self.root.getSubObject=lambda path:None
        with self.assertRaises(ValueError): self.read()

    def test_rejects_invalid_shape_curve_open_infinite_and_degenerate_edges(self):
        cases=[('ShapeType','Wire'),('Vertexes',()),('Curve',NS(isDerivedFrom=lambda name:False)),
               ('Length',math.inf),('FirstParameter',-2e100),('Length',1e-12),
               ('valueAt',lambda t:NS(x=1.,y=2.,z=3.)),
               ('valueAt',lambda t:NS(x=math.nan,y=2.,z=3.)),
               ('isValid',lambda:False),('isNull',lambda:True)]
        for name,value in cases:
            previous=getattr(self.edge,name)
            setattr(self.edge,name,value)
            try:
                with self.subTest(name=name),self.assertRaises(ValueError): self.read()
            finally: setattr(self.edge,name,previous)

    def test_normal_is_projected_using_existing_reference_frame(self):
        values=capture.line_values([.123456789,0,0],[3000.123456789,4000,0],[0,1,1],[0,1,0])
        axis=[.6,.8,0]
        self.assertAlmostEqual(sum(a*n for a,n in zip(axis,values['plane_normal'])),0.)
        self.assertEqual(values['start'][0],.123456789)
        vertical=capture.line_values([0,0,0],[0,0,5000],[0,0,1],[0,1,0])
        self.assertEqual(vertical['plane_normal'],[-1.,0.,0.])

    def test_raw_path_retains_authority_and_rejects_unsafe_sources(self):
        doc=NS()
        source=NS(Name='Leaf',Document=doc,isDerivedFrom=lambda name:False)
        root=NS(Name='Parent',Document=doc,isDerivedFrom=lambda name:False,
                getSubObject=lambda path,kind:source,getSubObjectList=lambda path:[root,source],
                resolveSubElement=lambda path:(source,'mapped','Leaf.Edge3'))
        doc.getObject=lambda name:root
        item=NS(Object=root,SubElementNames=('Leaf.Edge3',))
        self.assertEqual(capture.selected_path([item],doc),(root,source,'Leaf.Edge3','Edge3'))
        for selection in ([],[item,item],[NS(Object=root,SubElementNames=('Edge1','Edge2'))]):
            with self.assertRaises(ValueError): capture.selected_path(selection,doc)
        with self.assertRaises(ValueError): capture.selected_path([item],object())
        with patch.object(capture,'would_create_adjustment_cycle',lambda owner,obj:True):
            with self.assertRaises(ValueError): capture.selected_path([item],doc,object())
        source.isDerivedFrom=lambda name:True
        with self.assertRaises(ValueError): capture.selected_path([item],doc)
        source.isDerivedFrom=lambda name:False
        source.ArrayType='ortho'
        with self.assertRaises(ValueError): capture.selected_path([item],doc)


class SnapshotCaptionTests(unittest.TestCase):
    setUp=reference_controls.ReferenceControlTests.setUp
    def test_snapshot_caption_is_information_only_and_does_not_revive_reused_name(self):
        self.source.ID=17
        self.panel.session.config.update(reference_mode='TwoPoints',reference_source='',reference_edge='',reference_linked=False)
        self.panel.session._edge_snapshot_origin=dict(name=self.source.Name,object_id=17,edge='Edge3')
        before=self.panel.session.snapshot()
        self.panel._sync_reference_source()
        self.assertEqual(self.panel.source_label.text,'Referência selecionada: Eixo principal · Edge3 — Snapshot')
        self.assertEqual(self.panel._reference_ui_mode(),'DraftLine')
        self.source.ID=18
        self.panel._sync_reference_source()
        self.assertEqual(self.panel.source_label.text,'Geometria capturada — Snapshot')
        self.assertEqual(self.panel.session.config,before)


if __name__=='__main__': unittest.main()
