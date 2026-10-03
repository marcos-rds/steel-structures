"""Regressions from the C5-B manual gate; no document mutations."""
import copy
import json
import unittest
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import patch

from tests.test_connections_c5b import NODE, configured, node_webs
from tests.test_truss_assemblies import config
from freecad.SteelStructures.trusses.realization import build_candidate, plan_regeneration
from freecad.SteelStructures.trusses.serialization import encode_state, decode_state
from freecad.SteelStructures.trusses.connections import connection_participants, resolve_truss_connections
from freecad.SteelStructures.trusses.assemblies import configure_assembly
from freecad.SteelStructures.connections import ConnectionIntent, ConnectionForm, DirectFitPolicy, resolve_connection
from freecad.SteelStructures.connections.presentation import participant_names
from freecad.SteelStructures.fitting.serialization import loads as load_plan, dumps as dump_plan


def actions(item):
    plan = item.physical_fit_plan or {}
    return [a for a in (plan.get('start_action'), plan.get('end_action')) if a] + list(plan.get('additional_actions', ()))


class BlockerTests(unittest.TestCase):
    def test_to_chord_and_miter_are_both_retained_on_each_end(self):
        value = configured()
        value['role_specs']['DIAGONAL'].update(physical_fit='ToChord', physical_fit_gap=7.)
        candidate = build_candidate(value)
        for item in node_webs(candidate):
            end = 'Start' if item.start_node_key == NODE else 'End'
            same_end = [a for a in actions(item) if a['end'] == end]
            self.assertEqual({a['source'] for a in same_end}, {'AutoFit', 'ConnectionIntent'})
            self.assertEqual(len(same_end), 2)
            self.assertTrue(all(a['gap'] == 7. for a in same_end))
            plan = load_plan(json.dumps(item.physical_fit_plan))
            self.assertEqual(load_plan(dump_plan(plan)), plan)

    def test_v1_plan_still_loads_without_extra_planes(self):
        plan = copy.deepcopy(node_webs(build_candidate(configured()))[0].physical_fit_plan)
        plan.pop('additional_actions')
        plan['schema_version'] = 1
        self.assertEqual(load_plan(json.dumps(plan)).additional_actions, ())

    def test_through_chord_not_counted_but_vertical_is_a_third_web(self):
        c = build_candidate(configured())
        ps = connection_participants(c, NODE)
        intent = ConnectionIntent('i', NODE, ConnectionForm.DIRECT,
                                  direct_policy=DirectFitPolicy.BALANCED_MITER)
        self.assertEqual(len(resolve_connection(intent, ps, (0.,0.,0.), (0.,0.,1.)).directives), 2)
        vertical = replace(next(p for p in ps if p.role == 'DIAGONAL'), role='VERTICAL', run_key='v')
        resolution = resolve_connection(intent, ps+(vertical,), (0.,0.,0.), (0.,0.,1.))
        self.assertFalse(resolution.directives)
        self.assertEqual(resolution.diagnostics[0].message,
                         'Meia-esquadria equilibrada requer exatamente duas barras da alma equivalentes.')

    def test_priority_automatic_uses_web_and_local_left(self):
        c = build_candidate(configured(policy='Priority'))
        resolution = resolve_truss_connections(c, (0.,0.,1.))[0][0]
        ps = connection_participants(c, NODE)
        names = participant_names(ps)
        primary = resolution.directives[0].target_run_key
        self.assertEqual(names[primary], 'Diagonal esquerda')
        reversed_result = resolve_connection(resolution.intent, tuple(reversed(ps)),
                                            c.graph.node(NODE).position_local, (0.,0.,1.))
        self.assertEqual(reversed_result.directives, resolution.directives)
        self.assertEqual(build_candidate(decode_state(encode_state(c))['candidate']['config']), c)

    def test_participant_names_use_local_directions_and_disambiguate_duplicates(self):
        c=build_candidate(configured())
        ps=connection_participants(c,NODE)
        names=participant_names(ps)
        self.assertEqual(set(names.values()),{'Diagonal esquerda','Diagonal direita','Banzo superior (passante)'})
        left=next(p for p in ps if names[p.run_key]=='Diagonal esquerda')
        named=participant_names(ps+(replace(left,run_key='duplicate'),))
        self.assertIn('Diagonal esquerda 1',named.values())
        self.assertIn('Diagonal esquerda 2',named.values())

    def test_gusset_plane_normal_parameters_are_independent_of_axial_clearance(self):
        c=build_candidate(configured(form='Gusset',gusset=dict(plate_thickness=8.,normal_clearance=200.,axial_clearance=200.)))
        resolution=resolve_truss_connections(c,(0.,0.,1.))[0][0]
        self.assertEqual(resolution.gusset_plane.origin,c.graph.node(NODE).position_local)
        self.assertEqual(resolution.gusset_plane.normal,(0.,0.,1.))
        self.assertEqual(resolution.gusset_plane.plate_thickness,8.)
        self.assertEqual(resolution.gusset_plane.normal_clearance,200.)

    def test_pratt_priority_both_directions_and_automatic(self):
        value = config()
        value['topology_preset'] = 'Pratt'
        for spec in value['role_specs'].values():
            if spec.get('physical_fit') is not None:
                spec['physical_fit'] = 'ToChord'
        base = build_candidate(value)
        node = next(n for n in base.graph.nodes if {p.role for p in connection_participants(base,n.key)
                     if p.role in ('DIAGONAL','VERTICAL')} == {'DIAGONAL','VERTICAL'})
        webs = [p for p in connection_participants(base,node.key) if p.role in ('DIAGONAL','VERTICAL')]
        for primary_index, choice in ((0,'ParticipantA'),(1,'ParticipantB'),(None,'Automatic')):
            cfg = copy.deepcopy(value)
            cfg['connection_intents'] = {node.key: dict(form='Direct', direct_policy='Priority',
                participant_run_keys=[p.run_key for p in webs], priority_member=choice)}
            c = build_candidate(cfg)
            resolution = resolve_truss_connections(c,(0.,0.,1.))[0][0]
            primary = webs[primary_index] if primary_index is not None else next(p for p in webs if p.role=='VERTICAL')
            self.assertTrue(all(d.target_run_key == primary.run_key for d in resolution.directives))
            secondaries = [i for i in c.items if i.run_key in {d.run_key for d in resolution.directives}]
            self.assertTrue(secondaries)
            for item in secondaries:
                self.assertTrue(any(a['source']=='ConnectionIntent' for a in actions(item)), actions(item))

    def test_gusset_values_and_all_components_survive_transitions(self):
        for mode in ('DoubleAngle', 'DoubleChannelInward', 'SpacedPair'):
            value = configured(form='Gusset', gusset=dict(plate_thickness=8.,normal_clearance=200.,axial_clearance=200.))
            if mode.startswith('DoubleChannel'):
                value['role_specs']['DIAGONAL']['profile_ref'] = copy.deepcopy(value['role_specs']['TOP_CHORD']['profile_ref'])
            single = build_candidate(value)
            value['role_specs']['DIAGONAL'] = configure_assembly(value['role_specs']['DIAGONAL'],mode,100.)
            for candidate in (build_candidate(value),build_candidate(value,single)):
                for item in node_webs(candidate):
                    self.assertTrue(any(a['source']=='ConnectionIntent' and a['reference_offset']==200.
                                        for a in actions(item)))
                restored = build_candidate(decode_state(encode_state(candidate))['candidate']['config'])
                self.assertEqual(restored.config['connection_intents'][NODE]['gusset'],
                                 dict(plate_thickness=8.,normal_clearance=200.,axial_clearance=200.,
                                      side='Center',edge_margin=25.,member_overlap=150.,
                                      attachment_mode='Auto', chord_contact='Auto',
                                      transverse_placement=''))
                self.assertEqual({i.component_key for i in node_webs(candidate)}, {'A','B'})
            value['role_specs']['DIAGONAL'] = configure_assembly(value['role_specs']['DIAGONAL'],'Single')
            back = build_candidate(value,candidate)
            self.assertEqual({i.key for i in node_webs(single)}, {i.key for i in node_webs(back)})
            self.assertTrue(any(a.action=='REMOVE_EXISTING' for a in plan_regeneration(back,candidate).actions))

    def test_orphan_intents_removed_only_from_candidate(self):
        value = configured()
        value['connection_intents']['removed_node'] = dict(form='Gusset')
        candidate = build_candidate(value)
        self.assertNotIn('removed_node', candidate.config['connection_intents'])
        self.assertIn('removed_node',value['connection_intents'])
        self.assertIn(NODE,candidate.config['connection_intents'])

    def test_preset_switch_cleans_stale_intents(self):
        value=configured()
        before=build_candidate(value)
        for preset in ('Pratt','Howe','Warren'):
            value['topology_preset']=preset
            after=build_candidate(value,before)
            self.assertTrue(set(after.config['connection_intents']).issubset({n.key for n in after.graph.nodes}))

    def test_manual_provenance_is_exact_and_reference_sensitive(self):
        import importlib, sys
        from tests.test_member_placement import Vector
        name='freecad.SteelStructures.fitting.freecad_adapter'
        old=sys.modules.pop(name,None)
        try:
            with patch.dict(sys.modules, {'FreeCAD':SimpleNamespace(Vector=Vector)}):
                adapter=importlib.import_module(name)
                child=SimpleNamespace(EndAdjustmentMode='None',StartAdjustmentMode='Fixed',
                    StartAdjustmentGeometryMode='PlaneCut',StartAdjustmentGap=3.,
                    StartFixedReferenceOffset=10.,StartFixedPlaneNormal=Vector(1,0,1),
                    StartAdjustmentReference=None)
                child.PhysicalFitAutoState=json.dumps({'Start':adapter._slot_state(child,'Start')})
                self.assertFalse(adapter.has_manual_adjustment(child))
                child.StartFixedReferenceOffset=11.
                self.assertTrue(adapter.has_manual_adjustment(child))
                child.StartFixedReferenceOffset=10.
                child.StartAdjustmentReference=object()
                self.assertTrue(adapter.has_manual_adjustment(child))
        finally:
            sys.modules.pop(name,None)
            if old is not None: sys.modules[name]=old
