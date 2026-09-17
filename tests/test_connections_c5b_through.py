"""Focused generic through-participant regressions."""
import copy
import unittest
from dataclasses import replace
from types import SimpleNamespace
from tests.test_truss_assemblies import config
from tests.test_connections_c5b_blockers import actions
from tests.test_truss_manual_fixes import definition
from freecad.SteelStructures.connections import ThroughParticipant, resolve_connection_participants
from freecad.SteelStructures.connections.presentation import participant_names
from freecad.SteelStructures.trusses.connections import connection_participants, resolve_truss_connections
from freecad.SteelStructures.trusses.realization import build_candidate


def k_config(custom=False):
    value=config()
    value['topology_preset']='K'
    c=build_candidate(value)
    if custom:
        from freecad.SteelStructures.trusses.editing import materialize
        value.update(topology_mode='Custom',topology_preset='Custom',base_preset='K',custom_topology=materialize(c.graph,c.config))
        c=build_candidate(value)
    node=next(n.key for n in c.graph.nodes if any(p.role=='VERTICAL' and p.end=='Through'
        for p in connection_participants(c,n.key)))
    return value,node


class ThroughTests(unittest.TestCase):
    def test_k_custom_automatic_and_each_stable_primary_alias(self):
        for custom in (False,True):
            value,node=k_config(custom)
            ps=connection_participants(build_candidate(value),node)
            through=next(p for p in ps if p.role=='VERTICAL')
            self.assertIsInstance(through,ThroughParticipant)
            self.assertEqual(len(through.physical_run_keys),2)
            self.assertEqual(len(ps),3)
            names=participant_names(ps)
            self.assertEqual(names[through.run_key],'Montante (passante)')
            self.assertEqual(len(set(names.values())),3)
            for primary in ('',)+through.physical_run_keys:
                with self.subTest(custom=custom,primary=primary):
                    value['connection_intents']={node:dict(form='Direct',direct_policy='Priority',priority_run_key=primary)}
                    c=build_candidate(value)
                    r=resolve_truss_connections(c,(0.,0.,1.))[0][0]
                    self.assertFalse(r.diagnostics)
                    self.assertEqual(len(r.directives),2)
                    self.assertTrue(all(d.target_run_keys==through.physical_run_keys for d in r.directives))
                    for item in c.items:
                        cuts=[a for a in actions(item) if a['source']=='ConnectionIntent']
                        if item.run_key in through.physical_run_keys: self.assertFalse(cuts)
                        if item.run_key in {d.run_key for d in r.directives}: self.assertEqual(len(cuts),1)


    def test_incidence_opposition_role_geometry_and_ambiguous_parallel_runs(self):
        value,node=k_config()
        c=build_candidate(value); n=c.graph.node(node)
        runs=[r for r in c.runs if r.role=='VERTICAL' and node in (r.start_node_key,r.end_node_key)]
        resolve=lambda rs,data=None: resolve_connection_participants(n,c.graph,rs,data)
        self.assertEqual(len(resolve(runs)),1)
        self.assertEqual(resolve(runs),resolve(list(reversed(runs))))
        self.assertEqual(len(resolve([runs[0],replace(runs[0],key='parallel')])),2)
        self.assertEqual(len(resolve(runs+[replace(runs[0],key='parallel')])),3)
        self.assertEqual(len(resolve([runs[0],replace(runs[1],role='DIAGONAL')])),2)
        self.assertEqual(len(resolve(runs,{runs[0].key:dict(geometry_key='a'),runs[1].key:dict(geometry_key='b')})),2)
        generic=resolve([replace(r,role='CUSTOM_BAR') for r in runs])
        self.assertEqual(participant_names(generic)[generic[0].run_key],'Barra passante')
        other=replace(n,key='different-stable-node')
        self.assertEqual(resolve_connection_participants(other,c.graph,runs),())

    def test_through_priority_and_gusset_and_defensive_miter(self):
        from freecad.SteelStructures.connections import ConnectionIntent, ConnectionForm, DirectFitPolicy, resolve_connection
        from freecad.SteelStructures.connections.resolver import priority_options
        for custom in (False,True):
            value,node=k_config(custom)
            c=build_candidate(value)
            ps=connection_participants(c,node)
            through=next(p for p in ps if p.end=='Through')
            self.assertEqual(priority_options(ps),(through,))
            # A diagonal passante gets the same priority as a vertical passante.
            ps=tuple(replace(p,role='DIAGONAL') if p==through else p for p in ps)
            through=next(p for p in ps if p.end=='Through')
            self.assertEqual(priority_options(ps),(through,))
            for policy in (DirectFitPolicy.PRIORITY,DirectFitPolicy.BALANCED_MITER):
                intent=ConnectionIntent('i',node,ConnectionForm.DIRECT,direct_policy=policy)
                r=resolve_connection(intent,ps,c.graph.node(node).position_local,(0.,0.,1.))
                if policy==DirectFitPolicy.PRIORITY:
                    self.assertEqual(len(r.directives),2)
                    self.assertTrue(all(d.target_run_keys==through.physical_run_keys for d in r.directives))
                else:
                    self.assertFalse(r.directives)
                    self.assertEqual(r.diagnostics[0].code,'BALANCED_MITER_WITH_THROUGH_UNSUPPORTED')
            r=resolve_connection(ConnectionIntent('g',node,ConnectionForm.GUSSET),ps,
                                 c.graph.node(node).position_local,(0.,0.,1.))
            self.assertEqual(len(r.directives),2)
            self.assertFalse(set(through.physical_run_keys)&{d.run_key for d in r.directives})
            terminals=tuple(p for p in ps if p.end!='Through')
            self.assertEqual(priority_options(terminals),terminals)

    def test_restored_manual_reference_does_not_require_python_cache(self):
        validate=definition('member_batch.py','validate_adjustment_dependencies',dict(
            __package__='freecad.SteelStructures'))
        source=SimpleNamespace(Name='Reference',Label='Reference',State=['Up-to-date'],OutList=[])
        owner=SimpleNamespace()
        child=SimpleNamespace(StartAdjustmentMode='Associative',EndAdjustmentMode='Fixed',
            StartAdjustmentReference=(source,['Face1']),Proxy=SimpleNamespace(),GenerationOwner=owner,Label='Manual')
        validate([child])
        source.OutList=[owner]
        with self.assertRaisesRegex(ValueError,'própria treliça'): validate([child])
        source.OutList=[]; source.State=['Touched']
        with self.assertRaisesRegex(ValueError,'Recompute a origem'): validate([child])

    def test_legacy_member_snapshot_without_status_applies_cleanly(self):
        cls=definition('member_batch.py','MemberInputSnapshot',dict(SimpleNamespace=SimpleNamespace))
        apply=definition('member_batch.py','apply_fit_properties',{})
        result=cls(PhysicalFitPlan='{}',PhysicalFitAutoState='{}')
        obj=SimpleNamespace(PropertiesList=[],setEditorMode=lambda *args:None)
        obj.addProperty=lambda *args:obj.PropertiesList.append(args[1])
        apply(obj,result)
        self.assertEqual(obj.PhysicalFitStatus,'')
        self.assertEqual(obj.PhysicalFitPlan,'{}')
        apply(obj,cls())
        self.assertEqual(obj.PhysicalFitPlan,'{}')

    def test_selection_halo_is_independent_and_replaced(self):
        class Marker:
            def __init__(self): self.data_value=None
            def data(self,_): return self.data_value
            def setData(self,_,v): self.data_value=v
            def setFlag(self,v): self.flag=v
            def setPos(self,*v): self.pos=v
            def setZValue(self,v): self.z=v
        class Scene:
            def __init__(self): self.markers=[]
            def items(self): return list(self.markers)
            def removeItem(self,item): self.markers.remove(item)
            def addEllipse(self,*args):
                marker=Marker(); marker.args=args; self.markers.append(marker); return marker
        cls=definition('interactive/truss_topology_editor.py','TopologyCanvas',dict(
            TrussPreview2D=object,QtWidgets=SimpleNamespace(QGraphicsItem=SimpleNamespace(ItemIgnoresTransformations=1))))
        canvas=object.__new__(cls); scene=Scene(); canvas.scene=lambda:scene
        canvas._pen=lambda color,width:(color,width)
        canvas.editor=SimpleNamespace(_connection_node='N',panel=SimpleNamespace(controller=SimpleNamespace(
            last_candidate=SimpleNamespace(graph=SimpleNamespace(nodes=[SimpleNamespace(key='N',position_local=(5,8,0))])))))
        for _ in range(2): canvas.update_selection_halo()
        self.assertEqual(len(scene.markers),1)
        marker=scene.markers[0]
        self.assertEqual(marker.pos,(5,-8)); self.assertEqual(marker.args,(-9,-9,18,18,((0,190,215),3)))
        canvas.editor._connection_node=None; canvas.update_selection_halo()
        self.assertFalse(scene.markers)


if __name__=='__main__': unittest.main()
