"""Opening forwards raw selections to the approved linear capture/adoption."""
from copy import deepcopy
import sys
from types import SimpleNamespace as NS
import unittest
from unittest.mock import Mock, patch

from tests.test_truss_manual_fixes import definition
from freecad.SteelStructures import truss_edge_snapshot, truss_reference


class Vector(tuple):
    def __mul__(self, factor): return Vector(v*factor for v in self)
    def add(self, other): return Vector(a+b for a,b in zip(self,other))


class OpeningReferenceTests(unittest.TestCase):
    def setUp(self):
        self.document=object()
        self.selection=[NS(Object=object(),SubElementNames=('Inner.Profile.Edge3',))]
        self.selected=dict(reference_mode='TwoPoints',reference_source='',reference_edge='',reference_linked=False)
        self.values=dict(start=[123.,456.,789.],end=[4623.,456.,789.],span=4500.)
        self.origin=dict(name='Profile',object_id=17,edge='Edge3')
        self.controller=NS(selected_linear_reference=Mock(return_value=(self.selected,self.values,self.origin)),cancel=Mock())
        self.panel=NS(normal_inputs=object(),_read_vector=Mock(return_value=[0.,0.,1.]),
                      _adopt_selected_reference=Mock())
        self.gui=NS(Control=NS(activeDialog=lambda:False),Selection=NS(getSelectionEx=Mock(return_value=self.selection)))
        self.warning=Mock()
        self.initial=dict(span=10000.,start=[0.,0.,0.],end=[10000.,0.,0.],plane_normal=[0.,0.,1.])
        self.show=Mock(return_value=self.panel)
        self.open=definition('interactive/truss_controller.py','open_truss_panel',dict(
            _active_panel=None,Gui=self.gui,App=NS(Console=NS(PrintWarning=self.warning)),
            TrussController=Mock(return_value=self.controller),default_config=lambda:deepcopy(self.initial),
            config_from_object=lambda *_args,**_kwargs:deepcopy(self.initial),_show_truss_panel=self.show))
        plane=NS(position=Vector((0.,0.,0.)),u=Vector((1.,0.,0.)),axis=Vector((0.,0.,1.)))
        working=patch.dict(sys.modules,WorkingPlane=NS(get_working_plane=lambda:plane))
        working.start(); self.addCleanup(working.stop)

    def test_opening_preserves_raw_hierarchical_selection_and_adopts_snapshot(self):
        self.assertIs(self.open(self.document),self.panel)
        self.gui.Selection.getSelectionEx.assert_called_once_with('',0)
        self.controller.selected_linear_reference.assert_called_once_with(self.selection,[0.,0.,1.],allow_rectangle=True)
        self.panel._adopt_selected_reference.assert_called_once_with(self.selected,values=self.values,origin=self.origin)
        self.warning.assert_not_called()

    def test_no_selection_keeps_two_point_initialization(self):
        self.gui.Selection.getSelectionEx.return_value=[]
        self.open(self.document)
        self.controller.selected_linear_reference.assert_not_called()
        self.panel._adopt_selected_reference.assert_not_called()
        self.assertEqual(self.show.call_args.args[1],self.initial)

    def test_invalid_selection_does_not_mutate_initial_config_or_adopt(self):
        for error in (ValueError,RuntimeError,ReferenceError):
            with self.subTest(error=error):
                self.controller.selected_linear_reference.side_effect=error('Selecione uma única linha ou aresta reta.')
                self.open(self.document)
                self.assertEqual(self.show.call_args.args[1],self.initial)
                self.panel._adopt_selected_reference.assert_not_called()
                self.warning.assert_called_with('Selecione uma única linha ou aresta reta.\n')

    def test_existing_owner_does_not_consume_viewport_selection(self):
        self.open(self.document,object())
        self.gui.Selection.getSelectionEx.assert_not_called()
        self.controller.selected_linear_reference.assert_not_called()


class LinearDispatchTests(unittest.TestCase):
    def setUp(self):
        cls=definition('interactive/truss_controller.py','TrussController',dict(
            __name__='freecad.SteelStructures.interactive.truss_controller',
            __package__='freecad.SteelStructures.interactive'))
        self.controller=cls.__new__(cls)
        self.controller.document=object(); self.controller.object=None
        self.controller.session=NS(config=dict(height=2000.))
        self.controller.selected_reference=Mock(return_value=dict(reference_mode='DraftRectangle',reference_edge='Edge1'))
        self.controller.reference_geometry=Mock(return_value=dict(span=4000.,height=2300.))
        self.root,self.source=object(),object()
        self.path=(self.root,self.source,'Inner.Profile.Edge3','Edge3')
        self.result=({'reference_mode':'TwoPoints'},{'start':[123,456,789]}, {'edge':'Edge3'})
        for target,name,value in ((truss_edge_snapshot,'selected_path',Mock(side_effect=lambda *_args:self.path)),
                                  (truss_edge_snapshot,'capture_edge',Mock(return_value=self.result)),
                                  (truss_edge_snapshot,'is_draft_line',Mock(return_value=False)),
                                  (truss_reference,'is_draft_rectangle',Mock(return_value=True))):
            item=patch.object(target,name,value); item.start(); self.addCleanup(item.stop)
        item=patch.dict(sys.modules,WorkingPlane=NS(get_working_plane=lambda:NS(v=[0,1,0])))
        item.start(); self.addCleanup(item.stop)

    def test_opening_and_interactive_use_exactly_the_same_snapshot_capture(self):
        selection=[object()]; normal=[0,0,1]
        for opening in (False,True):
            self.assertEqual(self.controller.selected_linear_reference(selection,normal,allow_rectangle=opening),self.result)
        self.assertEqual(truss_edge_snapshot.capture_edge.call_count,2)
        truss_edge_snapshot.capture_edge.assert_called_with(*self.path,normal,[0,1,0])
        self.controller.selected_reference.assert_not_called()

    def test_whole_rectangle_is_legacy_envelope_only_when_opening(self):
        self.path=(self.root,self.source,'Rectangle.','')
        selected,values,origin=self.controller.selected_linear_reference([object()],[0,0,1],allow_rectangle=True)
        self.assertEqual(selected['reference_mode'],'DraftRectangle')
        self.assertEqual(values,dict(span=4000.,height=2300.))
        self.assertIsNone(origin)
        self.assertEqual(self.controller.selected_reference.call_args.args[0][0].SubElementNames,())
        truss_edge_snapshot.capture_edge.assert_not_called()
        self.controller.selected_linear_reference([object()],[0,0,1])
        truss_edge_snapshot.capture_edge.assert_called_once()

    def test_square_rectangle_waits_for_base_without_geometry_resolution(self):
        self.path=(self.root,self.source,'','')
        self.controller.selected_reference.return_value['reference_edge']=''
        _selected,values,origin=self.controller.selected_linear_reference([object()],[0,0,1],allow_rectangle=True)
        self.assertIsNone(values); self.assertIsNone(origin)
        self.controller.reference_geometry.assert_not_called()


if __name__=='__main__': unittest.main()
