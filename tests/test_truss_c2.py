"""Focused C2 contracts: graph editing, drivers, identity and persistence."""
import copy
import json
import unittest
from tests.test_truss_qa import config
from freecad.SteelStructures.trusses.realization import build_candidate, plan_regeneration
from freecad.SteelStructures.trusses.editing import edit_candidate, restore_preset
from freecad.SteelStructures.trusses.preset_contracts import PRESETS, compatible_presets
from freecad.SteelStructures.trusses.serialization import encode_state, decode_state
from freecad.SteelStructures.trusses.validation import validate_graph


class C2GraphTests(unittest.TestCase):
    def test_presets_have_valid_incidence_and_deterministic_identity(self):
        for kind in ("Parallel", "DuoPitch"):
            for preset in PRESETS:
                with self.subTest(kind=kind, preset=preset):
                    args = config(envelope_type=kind, topology_preset=preset,
                                  panel_count=6 if preset=="QueenPost" else 8)
                    if preset not in compatible_presets(kind):
                        with self.assertRaises(ValueError): build_candidate(args)
                        continue
                    candidate = build_candidate(args)
                    self.assertEqual(candidate.graph, build_candidate(args).graph)
                    self.assertFalse(validate_graph(candidate.graph)[0])
                    if preset == "K":
                        internal = [n for n in candidate.graph.nodes if n.classification=="INTERNAL_NODE"]
                        self.assertTrue(internal)
                        self.assertTrue(all(candidate.graph.incidence[n.key] for n in internal))

    def test_incompatible_preset_does_not_round_count(self):
        for preset, count in (("Fink",5),("Fan",7),("KingPost",5),("QueenPost",8)):
            args=config(topology_preset=preset,panel_count=count)
            before=copy.deepcopy(args)
            with self.assertRaises(ValueError): build_candidate(args)
            self.assertEqual(args,before)

    def test_x_connection_is_explicit(self):
        plain=build_candidate(config(topology_preset="X"))
        joined=build_candidate(config(topology_preset="X",x_connection="Connected"))
        self.assertFalse(any(n.classification=="INTERNAL_NODE" for n in plain.graph.nodes))
        centers=[n for n in joined.graph.nodes if n.classification=="INTERNAL_NODE"]
        self.assertEqual(len(centers),6)
        self.assertTrue(all(len(joined.graph.incidence[n.key])==4 for n in centers))
        self.assertEqual(sum(e.role=="DIAGONAL" for e in plain.graph.edges),12)
        self.assertEqual(sum(e.role=="DIAGONAL" for e in joined.graph.edges),24)

    def test_queen_post_web_is_symmetric_and_has_two_posts(self):
        candidate=build_candidate(config(topology_preset="QueenPost",envelope_type="DuoPitch"))
        web=[e for e in candidate.graph.edges if e.role not in ("TOP_CHORD","BOTTOM_CHORD")]
        self.assertEqual(sum(e.role=="VERTICAL" for e in web),2)
        segments={frozenset((candidate.graph.node(e.start_node_key).position_local,
                             candidate.graph.node(e.end_node_key).position_local)) for e in web}
        mirrored={frozenset((6000-x,y,z) for x,y,z in segment) for segment in segments}
        self.assertEqual(segments,mirrored)

    def test_manual_edit_roundtrip_and_geometric_bindings(self):
        initial=build_candidate(config())
        candidate=build_candidate(edit_candidate(initial,"add_node",point=(750.,400.,0.)))
        node=next(n for n in candidate.graph.nodes if n.key.startswith("N_MANUAL_"))
        candidate=build_candidate(edit_candidate(candidate,"add_edge",start=node.key,end=initial.graph.nodes[0].key))
        restored=build_candidate(decode_state(encode_state(candidate))["candidate"]["config"])
        self.assertEqual(candidate.graph,restored.graph)
        change=copy.deepcopy(restored.config)
        change.update(span=12000.,end=[12000.,0.,0.],height=2400.)
        resized=build_candidate(change,restored)
        self.assertEqual(resized.graph.node(node.key).position_local,(1500.,800.,0.))
        self.assertFalse(plan_regeneration(resized,restored).structural)
        self.assertEqual(resized.config["topology_mode"],"Custom")
        change["role_specs"]["DIAGONAL"]["rotation"]=90
        self.assertEqual(build_candidate(change).graph,resized.graph)

    def test_remove_add_and_invalid_edits_are_atomic(self):
        initial=build_candidate(config())
        edge=next(e for e in initial.graph.edges if e.role=="DIAGONAL")
        removed=build_candidate(edit_candidate(initial,"remove_edge",key=edge.key))
        self.assertEqual(len(removed.graph.edges),len(initial.graph.edges)-1)
        added=build_candidate(edit_candidate(removed,"add_edge",start=edge.start_node_key,end=edge.end_node_key))
        before=encode_state(added)
        for a,b in ((edge.start_node_key,edge.end_node_key),(edge.start_node_key,edge.start_node_key),("missing",edge.end_node_key)):
            with self.assertRaises(ValueError): edit_candidate(added,"add_edge",start=a,end=b)
        with self.assertRaises(ValueError): edit_candidate(added,"move_node",key=edge.start_node_key,point=(100.,100.,0.))
        self.assertEqual(encode_state(added),before)

    def test_explicit_connected_node_splits_crossing_edges(self):
        candidate=build_candidate(config(topology_preset="X"))
        candidate=build_candidate(edit_candidate(candidate,"add_node",point=(500.,600.,0.)))
        center=next(n for n in candidate.graph.nodes if n.key.startswith("N_MANUAL_"))
        self.assertEqual(len(candidate.graph.incidence[center.key]),4)
        support=next(n for n in candidate.graph.nodes if n.position_local==(0.,0.,0.))
        with self.assertRaises(ValueError):
            edit_candidate(candidate,"add_edge",start=center.key,end=support.key)
        self.assertFalse(validate_graph(candidate.graph)[0])

    def test_mirror_twice_and_restore_preserve_specs(self):
        initial=build_candidate(config(panel_count=5))
        mirror=build_candidate(edit_candidate(initial,"mirror"))
        back=build_candidate(edit_candidate(mirror,"mirror"))
        pairs=lambda c:{frozenset((e.start_node_key,e.end_node_key)) for e in c.graph.edges}
        self.assertEqual(pairs(initial),pairs(back))
        self.assertEqual(len(pairs(mirror)),len(mirror.graph.edges))
        restored=build_candidate(restore_preset(back.config))
        self.assertEqual(initial.graph,restored.graph)
        self.assertEqual(initial.config["role_specs"],restored.config["role_specs"])
        self.assertEqual(restored.config["topology_mode"],"Preset")

    def test_c1_schema_is_readable_and_custom_roundtrip_is_schema2(self):
        candidate=build_candidate(config())
        old=json.loads(encode_state(candidate)); old["schema_version"]=1
        for key in ("topology_mode","panelization_mode","reference_mode","reference_linked","panelization_result"):
            old["candidate"]["config"].pop(key,None)
        migrated=build_candidate(decode_state(json.dumps(old))["candidate"]["config"])
        self.assertEqual(candidate.graph,migrated.graph)
        self.assertEqual(json.loads(encode_state(migrated))["schema_version"],2)


class C2DriverTests(unittest.TestCase):
    def test_spacing_is_discrete_and_reports_actual(self):
        candidate=build_candidate(config(panelization_mode="ByTargetSpacing",target_spacing=1050.))
        self.assertEqual(candidate.stations.panel_count,6)
        self.assertEqual(candidate.config["panelization_result"]["spacing"],1000.)
        change=copy.deepcopy(candidate.config); change.update(span=8000.,end=[8000.,0.,0.])
        changed=build_candidate(change,candidate)
        self.assertEqual(changed.stations.panel_count,8)
        self.assertTrue(plan_regeneration(changed,candidate).structural)

    def test_angle_uses_declared_diagonal_family(self):
        candidate=build_candidate(config(panelization_mode="ByTargetDiagonalAngle",target_angle=45.))
        self.assertEqual(candidate.stations.panel_count,5)
        self.assertAlmostEqual(candidate.config["panelization_result"]["angle"],45.)
        for preset in ("K","Fan","Custom"):
            with self.assertRaises(ValueError): build_candidate(config(topology_preset=preset,panelization_mode="ByTargetDiagonalAngle"))
        edited=edit_candidate(candidate,"add_node",point=(100.,100.,0.))
        self.assertEqual(build_candidate(edited).stations,candidate.stations)
        edited["panelization_mode"]="ByTargetDiagonalAngle"
        with self.assertRaises(ValueError): build_candidate(edited)

    def test_custom_spacing_and_apex_conflicts(self):
        args=config(panelization_mode="CustomSpacingList",custom_spacings=[500.,1000.,1500.,1500.,1000.,500.])
        candidate=build_candidate(args)
        self.assertEqual([s.x for s in candidate.stations.stations],[0,500,1500,3000,4500,5500,6000])
        self.assertEqual(candidate.stations.left_panels,0)
        args["envelope_type"]="DuoPitch"
        self.assertEqual(next(s.x for s in build_candidate(args).stations.stations if s.key=="S_APEX"),3000.)
        for spacing in ([1000.]*5,[800.,800.,800.,1200.,1200.,1200.],[0.,1000.,2000.,3000.]):
            args["custom_spacings"]=spacing
            with self.assertRaises(ValueError): build_candidate(args)

    def test_custom_repanelization_requires_explicit_resolution(self):
        old=build_candidate(config())
        edited=edit_candidate(old,"add_node",point=(100.,100.,0.))
        edited["panel_count"]=8
        with self.assertRaises(ValueError): build_candidate(edited)
        self.assertEqual(old.config["panel_count"],6)
