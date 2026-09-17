"""Focused ridge fitting and envelope-center insertion contracts."""
import unittest
from dataclasses import replace

from tests.test_truss_assemblies import config
from freecad.SteelStructures.connections import (ChordBreakParticipant,
                                                  ChordClosureParticipant,
                                                  ThroughParticipant)
from freecad.SteelStructures.connections.resolver import chord_break_plane
from freecad.SteelStructures.trusses.connections import chord_joints, connection_participants
from freecad.SteelStructures.trusses.realization import (build_candidate, reference_frame,
                                                         transform_point)
from freecad.SteelStructures.trusses.serialization import encode_state, decode_state
from freecad.SteelStructures.trusses.editing import materialize
from freecad.SteelStructures.trusses.models import TopologyEdge, TopologyGraph
from freecad.SteelStructures.profiles.insertion import insertion_reference
from freecad.SteelStructures.assemblies.transforms import SectionTransform, transform_section
from freecad.SteelStructures.trusses.assemblies import configure_assembly
from freecad.SteelStructures.trusses.assembly_preview import transverse_preview


def ridge_config(apex=.5, height=900., inclined=False, diagonals=True):
    value=config()
    value.update(envelope_type='DuoPitch',apex_position=apex,height=height,
                 panel_count=8,left_panels=None,right_panels=None,
                 topology_preset='Pratt',top_continuity='Continuous',bottom_continuity='Continuous')
    for role,spec in value['role_specs'].items():
        spec['physical_fit']='None' if role in ('TOP_CHORD','BOTTOM_CHORD') else 'ToChord'
    if inclined:
        value.update(start=[20.,30.,40.],end=[2420.,30.,40.],plane_normal=[0.,-.6,.8])
    if diagonals:
        base=build_candidate(value)
        node=base.graph.node('T_S_APEX')
        bottom=sorted((n for n in base.graph.nodes if n.key.startswith('B_')
                       and abs(n.position_local[0]-node.position_local[0])>1e-7),
                      key=lambda n:abs(n.position_local[0]-node.position_local[0]))
        targets=[next(n for n in bottom if n.position_local[0]<node.position_local[0]),
                 next(n for n in bottom if n.position_local[0]>node.position_local[0])]
        edges=list(base.graph.edges)
        for index,n in enumerate(targets):
            if not any({e.start_node_key,e.end_node_key}=={n.key,node.key} for e in edges):
                edges.append(TopologyEdge('ridge-diagonal-'+str(index),n.key,node.key,'DIAGONAL'))
        graph=TopologyGraph(base.graph.nodes,tuple(edges))
        value.update(topology_mode='Custom',topology_preset='Custom',base_preset='Pratt',
                     custom_topology=materialize(graph,base.config))
    return value


def actions(item, end=None):
    p=item.physical_fit_plan or {}
    values=[a for a in (p.get('start_action'),p.get('end_action')) if a]+list(p.get('additional_actions',()))
    return [a for a in values if end is None or a['end']==end]


class RidgeTests(unittest.TestCase):
    def test_chord_envelope_tracks_physical_insertion_translation(self):
        from freecad.SteelStructures.trusses.fitting_geometry import chord_envelope_reference
        from freecad.SteelStructures.trusses.assemblies import assembly_frame, role_profile
        from freecad.SteelStructures.profiles.geometry import build_section_geometry
        value = ridge_config(diagonals=False)
        value['role_specs']['TOP_CHORD']['profile_ref'] = value['role_specs']['VERTICAL']['profile_ref']
        candidate = build_candidate(value)
        chord = next(i for i in candidate.items if i.key == 'TC_LEFT')
        web = next(i for i in candidate.items if i.role == 'VERTICAL' and i.end_node_key == 'T_S_APEX')
        normal = tuple(value['plane_normal'])
        before = chord_envelope_reference(web, chord, web.end_global, normal, 'End')
        shifted = replace(chord, spec=replace(chord.spec, insertion='envelope_center'))
        after = chord_envelope_reference(web, shifted, web.end_global, normal, 'End')
        geometry = build_section_geometry(role_profile(value['role_specs']['TOP_CHORD']))
        p = insertion_reference(geometry, 'envelope_center').point
        frame = assembly_frame((chord.start_global, chord.end_global), chord.section_u_global, chord.spec.rotation)
        physical_shift = tuple(-p.x*u-p.y*v for u,v in zip(frame.u, frame.v))
        projected = sum(a*b for a,b in zip(physical_shift, before.normal))
        for a,b,n in zip(after.origin, before.origin, before.normal):
            self.assertAlmostEqual(a-b, projected*n)

    def test_asymmetric_diagonal_composes_opposite_physical_contact(self):
        value = ridge_config(.37, 1100.)
        value['role_specs']['TOP_CHORD']['rotation'] = -90.
        candidate = build_candidate(value)
        diagonal = next(i for i in candidate.items if i.key == 'ridge-diagonal-1')
        cuts = actions(diagonal, 'End')
        self.assertEqual([a['reference_key'] for a in cuts], ['TC_RIGHT', 'TC_LEFT'])

    def test_priority_composes_with_ridge_constraints_and_assemblies(self):
        value = ridge_config()
        base = build_candidate(value)
        vertical = next(i for i in base.items if i.role == 'VERTICAL'
                        and 'T_S_APEX' in (i.start_node_key, i.end_node_key))
        value['connection_intents'] = {'T_S_APEX': dict(
            form='Direct', direct_policy='Priority', priority_run_key=vertical.run_key)}
        candidate = build_candidate(value)
        for item in candidate.items:
            if item.role != 'DIAGONAL' or 'T_S_APEX' not in (item.start_node_key, item.end_node_key):
                continue
            end = 'Start' if item.start_node_key == 'T_S_APEX' else 'End'
            cuts = actions(item, end)
            self.assertTrue(any(a['source'] == 'ConnectionIntent' for a in cuts))
            self.assertTrue(any(a['reference_key'] in ('TC_LEFT', 'TC_RIGHT') for a in cuts))
        value['role_specs']['TOP_CHORD'] = configure_assembly(
            value['role_specs']['TOP_CHORD'], 'DoubleChannelInward', 100.)
        value['role_specs']['VERTICAL']['insertion'] = 'envelope_center'
        value['role_specs']['VERTICAL'] = configure_assembly(
            value['role_specs']['VERTICAL'], 'DoubleAngle', 70.)
        composite = build_candidate(value)
        self.assertEqual(candidate.graph, composite.graph)
        self.assertEqual(candidate.runs, composite.runs)
        chord_components = [i for i in composite.items if i.run_key in ('TC_LEFT', 'TC_RIGHT')]
        self.assertEqual(len(chord_components), 4)
        self.assertTrue(all(len([a for a in actions(i)
                                 if 'chord-break' in a['reference_key']]) == 1
                            for i in chord_components))
        self.assertEqual(composite, build_candidate(decode_state(encode_state(composite))['candidate']['config']))

    def test_symmetric_asymmetric_height_and_inclined_ridge(self):
        for apex,height,inclined in ((.5,900.,False),(.37,900.,False),(.61,1200.,True)):
            with self.subTest(apex=apex,height=height,inclined=inclined):
                value=ridge_config(apex,height,inclined)
                c=build_candidate(value)
                node=c.graph.node('T_S_APEX')
                ridge=next(p for p in connection_participants(c,node.key) if p.role=='TOP_CHORD')
                self.assertIsInstance(ridge,ChordBreakParticipant)
                self.assertNotIsInstance(ridge,ThroughParticipant)
                self.assertEqual(len(ridge.physical_run_keys),2)
                chords=[i for i in c.items if i.run_key in ridge.physical_run_keys]
                chord_actions=[a for i in chords for a in actions(i)
                               if 'chord-break' in a['reference_key']]
                self.assertEqual(len(chord_actions),2)
                self.assertEqual(chord_actions[0]['plane_origin'],chord_actions[1]['plane_origin'])
                self.assertEqual(chord_actions[0]['plane_normal'],chord_actions[1]['plane_normal'])
                self.assertTrue(all(abs(a['reference_offset'])<1e-7 for a in chord_actions))
                self.assertFalse(c.config.get('connection_intents'))
                for item in c.items:
                    if node.key not in (item.start_node_key,item.end_node_key) or item.role not in ('VERTICAL','DIAGONAL'):
                        continue
                    end='Start' if item.start_node_key==node.key else 'End'
                    cuts=actions(item,end)
                    if item.role=='VERTICAL':
                        self.assertEqual({a['reference_key'] for a in cuts},{i.key for i in chords})
                        self.assertEqual(len(cuts),2)
                    else:
                        other=c.graph.node(item.end_node_key if end=='Start' else item.start_node_key)
                        left=other.position_local[0]<node.position_local[0]
                        self.assertIn(len(cuts),(1,2))
                        self.assertEqual(cuts[0]['reference_key'],'TC_LEFT' if left else 'TC_RIGHT')
                restored=build_candidate(decode_state(encode_state(c))['candidate']['config'])
                self.assertEqual(c,restored)

    def test_ridge_webs_use_physical_section_contact_with_transform_and_gap(self):
        from freecad.SteelStructures.trusses.fitting_geometry import (
            chord_contact_reference, chord_envelope_reference)
        cases = (
            dict(rotation=-90., insertion='centroid', gap=0., angle=False),
            dict(rotation=35., insertion='envelope_center', gap=7., angle=False),
            dict(rotation=20., insertion='centroid', gap=0., angle=True),
        )
        for case in cases:
            with self.subTest(**case):
                value = ridge_config(.37, 1100., inclined=True)
                top = value['role_specs']['TOP_CHORD']
                top['rotation'] = case['rotation']
                top['insertion'] = case['insertion']
                if case['angle']:
                    top['profile_ref'] = dict(value['role_specs']['VERTICAL']['profile_ref'])
                for role in ('VERTICAL', 'DIAGONAL'):
                    value['role_specs'][role]['physical_fit_gap'] = case['gap']
                candidate = build_candidate(value)
                frame = reference_frame(candidate.config)
                node = candidate.graph.node('T_S_APEX')
                node_global = transform_point(node.position_local, frame)
                targets = [item for item in candidate.items
                           if item.run_key in ('TC_LEFT', 'TC_RIGHT')]
                webs = [item for item in candidate.items
                        if node.key in (item.start_node_key, item.end_node_key)
                        and item.role in ('VERTICAL', 'DIAGONAL')]
                self.assertTrue(webs)
                for web in webs:
                    end = 'Start' if web.start_node_key == node.key else 'End'
                    end_actions = actions(web, end)
                    by_target = {action['reference_key']: action for action in end_actions}
                    required_targets = targets
                    if web.role == 'DIAGONAL':
                        other_key = (web.end_node_key if end == 'Start'
                                     else web.start_node_key)
                        other = candidate.graph.node(other_key)
                        side = 'TC_LEFT' if other.position_local[0] < node.position_local[0] else 'TC_RIGHT'
                        required_targets = [target for target in targets if target.run_key == side]
                    for target in required_targets:
                        self.assertIn(target.key, by_target)
                    for target in (target for target in targets if target.key in by_target):
                        physical, _parameter = chord_contact_reference(
                            web, target, node_global, tuple(frame[3]), end)
                        action = by_target[target.key]
                        self.assertEqual(tuple(action['plane_origin']), physical.origin)
                        alignment = sum(a*b for a,b in zip(
                            action['plane_normal'], physical.normal))
                        self.assertAlmostEqual(abs(alignment), 1.)
                        self.assertEqual(action['gap'], case['gap'])
                vertical = next(item for item in webs if item.role == 'VERTICAL')
                end = 'Start' if vertical.start_node_key == node.key else 'End'
                self.assertEqual({a['reference_key'] for a in actions(vertical, end)},
                                 {item.key for item in targets})
                if case['rotation'] == -90.:
                    contact, _ = chord_contact_reference(
                        vertical, targets[0], node_global, tuple(frame[3]), end)
                    envelope = chord_envelope_reference(
                        vertical, targets[0], node_global, tuple(frame[3]), end)
                    separation = sum((a-b)**2 for a,b in zip(
                        contact.origin, envelope.origin))**.5
                    self.assertGreater(separation, 25.)

    def test_terminal_chord_joints_miter_both_ends_with_different_sections(self):
        value = ridge_config(.37, 1100., inclined=True, diagonals=False)
        baseline = build_candidate(value)
        value['role_specs']['TOP_CHORD']['profile_ref'] = dict(
            value['role_specs']['VERTICAL']['profile_ref'])
        candidate = build_candidate(value, baseline)
        self.assertEqual(candidate.graph, baseline.graph)
        self.assertEqual(candidate.runs, baseline.runs)
        self.assertEqual([(i.key, i.start_global, i.end_global) for i in candidate.items],
                         [(i.key, i.start_global, i.end_global) for i in baseline.items])
        for node_key in ('N_S_START', 'N_S_END'):
            with self.subTest(node=node_key):
                joint, = chord_joints(candidate, node_key)
                self.assertIsInstance(joint, ChordClosureParticipant)
                public = connection_participants(candidate, node_key)
                self.assertFalse(any(isinstance(p, ChordClosureParticipant) for p in public))
                self.assertEqual({p.role for p in public if p.role in ('TOP_CHORD','BOTTOM_CHORD')},
                                 {'TOP_CHORD','BOTTOM_CHORD'})
                planes = []
                for run_key, end in joint.run_ends:
                    item = next(i for i in candidate.items if i.run_key == run_key)
                    action = next(a for a in actions(item, end)
                                  if a['reference_key'] == joint.participant_key)
                    self.assertAlmostEqual(action['reference_offset'], 0., places=7)
                    self.assertEqual(action['gap'], 0.)
                    planes.append((action['plane_origin'], action['plane_normal']))
                self.assertEqual(planes[0], planes[1])
        restored = build_candidate(
            decode_state(encode_state(candidate))['candidate']['config'])
        self.assertEqual(candidate, restored)

    def test_degenerate_terminal_joint_preserves_applied_candidate(self):
        value = ridge_config(diagonals=False)
        applied = build_candidate(value)
        accepted = encode_state(applied)
        value['height'] = .1
        with self.assertRaisesRegex(
                ValueError, 'Encontro terminal de banzos degenerado; Ãºltimo estado vÃ¡lido preservado'):
            build_candidate(value, applied=applied)
        self.assertEqual(encode_state(applied), accepted)

    def test_incompatible_sections_diagnose_before_document_write(self):
        c=build_candidate(ridge_config(diagonals=False))
        ridge=next(p for p in connection_participants(c,'T_S_APEX') if isinstance(p,ChordBreakParticipant))
        bad=replace(ridge,branches=(ridge.branches[0],replace(ridge.branches[1],geometry_key='incompatible')))
        with self.assertRaisesRegex(ValueError,'incompatíveis'): chord_break_plane(bad)

    def test_apex_change_updates_plans_and_insertion_only_changes_physical_section(self):
        value=ridge_config(diagonals=False)
        before=build_candidate(value)
        value['apex_position']=.38
        after=build_candidate(value,applied=before)
        self.assertNotEqual(actions(next(i for i in before.items if i.key=='TC_LEFT')),
                            actions(next(i for i in after.items if i.key=='TC_LEFT')))
        for role in ('DIAGONAL','VERTICAL'):
            value['role_specs'][role]['insertion']='envelope_center'
        shifted=build_candidate(value,applied=after)
        self.assertEqual(after.graph,shifted.graph)
        self.assertEqual(after.runs,shifted.runs)
        self.assertEqual([(i.start_global,i.end_global) for i in after.items],
                         [(i.start_global,i.end_global) for i in shifted.items])

    def test_envelope_center_rotation_assembly_and_preview_marker(self):
        role=config()['role_specs']['VERTICAL']
        role['insertion']='envelope_center'
        role=configure_assembly(role,'DoubleAngle',70.)
        role['rotation']=35.
        preview=transverse_preview(role)
        for component in preview['components']:
            self.assertIsNotNone(component['insertion'])
        from freecad.SteelStructures import profile_catalog
        from freecad.SteelStructures.profiles.geometry import build_section_geometry
        geometry=build_section_geometry(profile_catalog.get('L 40 x 4').definition)
        center=insertion_reference(geometry,'envelope_center').point
        self.assertNotEqual(center,geometry.origin)
        transform=SectionTransform(90.,True)
        transformed,refs=transform_section(geometry,transform)
        self.assertEqual(next(r.point for r in refs if r.id=='envelope_center'),transform.point(center))
        bounds=transformed.bounds
        p=next(r.point for r in refs if r.id=='envelope_center')
        self.assertAlmostEqual(p.x,(bounds.min_x+bounds.max_x)/2.)
        self.assertAlmostEqual(p.y,(bounds.min_y+bounds.max_y)/2.)


if __name__=='__main__': unittest.main()
