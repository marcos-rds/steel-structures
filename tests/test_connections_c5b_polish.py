"""Focused final C5-B regressions, without OCC or document writes."""
import copy
import unittest
from types import SimpleNamespace

from tests.test_truss_assemblies import config
from tests.test_connections_c5b_blockers import actions
from freecad.SteelStructures.connections import dumps, loads, resolve_connection
from freecad.SteelStructures.trusses.connections import connection_participants, resolve_truss_connections
from freecad.SteelStructures.trusses.realization import build_candidate, plan_regeneration
from freecad.SteelStructures.trusses.assemblies import configure_assembly
from freecad.SteelStructures.trusses.editing import restore_preset
from freecad.SteelStructures.fitting.precedence import same_auto_state, slot_decision
from tests.test_truss_manual_fixes import definition


def three_web_config(preset='Pratt'):
    value = config()
    value.update(topology_preset=preset)
    for key, role in value['role_specs'].items():
        role['physical_fit'] = 'ToChord' if key not in ('TOP_CHORD','BOTTOM_CHORD') else 'None'
    c = build_candidate(value)
    node = next(n for n in c.graph.nodes if len(webs(c,n.key)) == 3)
    value['connection_intents'] = {node.key: dict(form='Direct', direct_policy='Priority')}
    return value, node.key


def webs(candidate, node):
    return [p for p in connection_participants(candidate,node) if p.role in ('DIAGONAL','VERTICAL','END_POST')]


class PolishTests(unittest.TestCase):
    def test_removed_end_action_clears_even_when_other_end_still_has_to_chord(self):
        state=dict(AdjustmentMode='Fixed')
        self.assertEqual(slot_decision(action_present=False,plan_is_none=False,invalid_plan=False,
            current_mode='Fixed',current_state=state,previous_auto_state=state),'Clear')

    def test_automatic_three_webs_composes_both_diagonals_with_to_chord(self):
        value, node = three_web_config()
        c = build_candidate(value)
        resolution = resolve_truss_connections(c,(0.,0.,1.))[0][0]
        vertical = next(p for p in webs(c,node) if p.role == 'VERTICAL')
        self.assertEqual(len(resolution.directives),2)
        self.assertEqual({d.target_run_key for d in resolution.directives},{vertical.run_key})
        for p in webs(c,node):
            item = next(i for i in c.items if i.run_key == p.run_key)
            sources = {a['source'] for a in actions(item) if a['end'] == p.end}
            self.assertEqual(sources, {'AutoFit'} if p.role == 'VERTICAL' else {'AutoFit','ConnectionIntent'})
        for participants in (resolution.participants, tuple(reversed(resolution.participants))):
            self.assertEqual(resolve_connection(loads(dumps(resolution.intent)),participants,
                c.graph.node(node).position_local,(0.,0.,1.)).directives, resolution.directives)

    def test_manual_stable_primary_can_select_each_of_three_webs(self):
        value,node = three_web_config()
        c = build_candidate(value)
        for primary in webs(c,node):
            with self.subTest(primary=primary.role):
                value['connection_intents'][node]['priority_run_key'] = primary.run_key
                resolved = resolve_truss_connections(build_candidate(value),(0.,0.,1.))[0][0]
                self.assertEqual(len(resolved.directives),2)
                self.assertEqual({d.target_run_key for d in resolved.directives},{primary.run_key})

    def test_legacy_two_selected_keys_do_not_exclude_third_web(self):
        value,node = three_web_config()
        ps = webs(build_candidate(value),node)
        value['connection_intents'][node]['participant_run_keys'] = [p.run_key for p in ps[:2]]
        resolved = resolve_truss_connections(build_candidate(value),(0.,0.,1.))[0][0]
        self.assertEqual(len(resolved.directives),2)
        self.assertEqual({d.target_run_key for d in resolved.directives},
                         {p.run_key for p in ps if p.role == 'VERTICAL'})

    def test_automatic_ignores_obsolete_legacy_participant_subset(self):
        value,node = three_web_config()
        value['connection_intents'][node]['participant_run_keys'] = ['removed-run']
        resolved = resolve_truss_connections(build_candidate(value),(0.,0.,1.))[0][0]
        self.assertEqual(len(resolved.directives),2)
        self.assertFalse(resolved.diagnostics)

    def test_double_gusset_preset_candidates_clean_stale_intents(self):
        value,node = three_web_config('WarrenVerticals')
        value['role_specs']['DIAGONAL'] = configure_assembly(value['role_specs']['DIAGONAL'],'DoubleAngle',100.)
        value['connection_intents'][node] = dict(form='Gusset',gusset=dict(plate_thickness=8.,normal_clearance=2.,axial_clearance=20.))
        before = build_candidate(value)
        original = copy.deepcopy(before.config)
        for preset in ('Pratt','K','X','Custom'):
            with self.subTest(preset=preset):
                changed = copy.deepcopy(value)
                if preset == 'Custom':
                    changed.update(topology_preset='Custom',base_preset='WarrenVerticals')
                else:
                    changed['topology_preset'] = preset
                changed['connection_intents']['REMOVED_NODE'] = dict(form='Gusset')
                after = build_candidate(changed, applied=before)
                self.assertNotIn('REMOVED_NODE',after.config['connection_intents'])
                self.assertTrue(set(after.config['connection_intents']) <= {n.key for n in after.graph.nodes})
                self.assertEqual(before.config,original)
                self.assertIsNotNone(plan_regeneration(after,before))
                if preset == 'Custom':
                    restored=build_candidate(restore_preset(after.config),applied=after)
                    self.assertEqual(restored.graph,before.graph)

    def test_normal_serialization_roundoff_is_not_a_manual_edit(self):
        old=dict(AdjustmentMode='Fixed',AdjustmentGeometryMode='PlaneCut',AdjustmentGap=0.,
                 FixedReferenceOffset=8.,FixedPlaneNormal=[-2.2204460492503136e-16,-.6401843996644799,.7682212795973762])
        current=copy.deepcopy(old)
        current['FixedPlaneNormal']=[-2e-16,-.6401843996644797,.768221279597376]
        self.assertTrue(same_auto_state(current,old))
        for action in (True,False):
            self.assertEqual(slot_decision(action_present=action,plan_is_none=True,invalid_plan=False,
                current_mode='Fixed',current_state=current,previous_auto_state=old),'Apply' if action else 'Clear')
        for name,value in (('FixedReferenceOffset',9.),('FixedPlaneNormal',[.2,0.,1.]),
                           ('AdjustmentGeometryMode','LengthLimit'),('ManualReference',True)):
            manual=dict(current,**{name:value})
            self.assertFalse(same_auto_state(manual,old))

    def test_node_options_and_conditional_rows(self):
        class Widget:
            def __init__(self):
                self.items=[]; self.index=0; self.visible=True; self.number=0.; self.tip=''
            def addItem(self,label,data): self.items.append((label,data))
            def clear(self): self.items=[]; self.index=0
            def findData(self,data): return next((i for i,p in enumerate(self.items) if p[1]==data),-1)
            def setCurrentIndex(self,index): self.index=index
            def currentData(self): return self.items[self.index][1] if self.items and self.index>=0 else None
            def blockSignals(self,_value): return False
            def setEnabled(self,_value): pass
            def setText(self,value): self.text=value
            def setToolTip(self,value): self.tip=value
            def toolTip(self): return self.tip
            def setVisible(self,value): self.visible=value
            def maximum(self): return 100000.
            def setMaximum(self,value): pass
            def setValue(self,value): self.number=value
            def value(self): return self.number
        cls=definition('interactive/truss_topology_editor.py','TopologyEditor',dict(
            QtWidgets=SimpleNamespace(QDialog=object),
            __package__='freecad.SteelStructures.interactive'))
        editor=object.__new__(cls)
        value,node=three_web_config()
        c=build_candidate(value)
        editor.panel=SimpleNamespace(get_config=lambda:c.config,controller=SimpleNamespace(last_candidate=c))
        for name in ('connection_box','connection_type','fastening','direct_policy','priority_member',
                     'gusset_plate','gusset_normal','gusset_axial','gusset_margin','gusset_overlap',
                     'gusset_region','gusset_position','participants','message'):
            setattr(editor,name,Widget())
        for form in ('GeometricOnly','Direct','Gusset'): editor.connection_type.addItem(form,form)
        editor.fastening.addItem('Unspecified','Unspecified')
        editor.gusset_region.addItem('Automática','')
        editor.gusset_position.addItem('Resolvida automaticamente','')
        editor._connection_tooltips=dict.fromkeys(('GeometricOnly','Direct','Gusset'),'help')
        labels={widget:Widget() for widget in (editor.direct_policy,editor.priority_member,
                                             editor.gusset_plate,editor.gusset_normal,editor.gusset_axial,
                                             editor.gusset_margin,editor.gusset_overlap,
                                             editor.gusset_region,editor.gusset_position)}
        transverse_labels = {widget: labels[widget] for widget in (
            editor.gusset_region, editor.gusset_position)}
        connection_labels = {widget: label for widget, label in labels.items()
                             if widget not in transverse_labels}
        editor._connection_form=SimpleNamespace(labelForField=connection_labels.__getitem__)
        editor._transverse_form=SimpleNamespace(labelForField=transverse_labels.__getitem__)
        editor.select_node(node)
        self.assertEqual(editor.direct_policy.findData('BalancedMiter'),-1)
        self.assertEqual(editor.direct_policy.findData('Independent'),-1)
        vertical=next(p for p in webs(c,node) if p.role=='VERTICAL')
        self.assertIn(('Montante',vertical.run_key),editor.priority_member.items)
        self.assertEqual(len(editor.priority_member.items),4)
        for form,policy,visible in (('GeometricOnly','Independent',(False,False,False)),
                ('Direct','Independent',(True,False,False)),('Direct','Priority',(True,True,False)),
                ('Gusset','Independent',(False,False,True))):
            editor.connection_type.setCurrentIndex(editor.connection_type.findData(form))
            editor.direct_policy.setCurrentIndex(editor.direct_policy.findData(policy))
            editor._update_connection_visibility()
            for widget,expected in zip((editor.direct_policy,editor.priority_member,editor.gusset_plate),visible):
                self.assertEqual(widget.visible,expected)
                self.assertEqual(labels[widget].visible,expected)
            for widget in (editor.gusset_margin,editor.gusset_overlap,
                           editor.gusset_region,editor.gusset_position):
                self.assertEqual(widget.visible,form=='Gusset')
                self.assertEqual(labels[widget].visible,form=='Gusset')
        c.config['connection_intents'][node]['direct_policy']='Independent'
        before=copy.deepcopy(c.config)
        editor.select_node(node)
        self.assertEqual(editor.direct_policy.currentData(),'Independent')
        self.assertEqual(c.config,before)
        self.assertNotIn('Encontro independente',[label for label,_ in editor.direct_policy.items])
        from tests.test_connections_c5b_through import k_config
        for custom in (False,True):
            value,node=k_config(custom)
            value['connection_intents']={node:dict(form='Direct',direct_policy='Priority')}
            c=build_candidate(value)
            editor.panel.controller.last_candidate=c
            editor.select_node(node)
            through=next(p for p in connection_participants(c,node) if p.end=='Through')
            self.assertEqual(editor.priority_member.items,[('Automática','Automatic'),('Montante (passante)',through.run_key)])
            self.assertEqual(editor.direct_policy.items,[('Prioridade','Priority')])




if __name__ == '__main__':
    unittest.main()
