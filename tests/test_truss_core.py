"""Pure C1 boundaries and public data contracts."""
import copy
import math
import unittest
from dataclasses import replace

from freecad.SteelStructures.trusses.envelope import paths
from freecad.SteelStructures.trusses.models import EnvelopeDefinition, TopologyGraph, TopologyNode, TopologyEdge
from freecad.SteelStructures.trusses.panelization import allocate_panels, panelize
from freecad.SteelStructures.trusses.validation import validate_graph
from freecad.SteelStructures.trusses.realization import build_candidate, plan_regeneration
from freecad.SteelStructures.trusses.runs import physical_runs
from tests.test_truss_qa import config


class TrussCoreBoundaryTests(unittest.TestCase):
    def test_parallel_paths(self):
        self.assertEqual(paths(EnvelopeDefinition("Parallel", 9000.,1500.)),
                         {"top": ((0.,1500.,0.),(9000.,1500.,0.)), "bottom": ((0.,0.,0.),(9000.,0.,0.))})

    def test_duopitch_paths_shared_supports(self):
        value = paths(EnvelopeDefinition("DuoPitch",10000.,2300.,.37))
        self.assertEqual(value["top"], ((0.,0.,0.),(3700.,2300.,0.),(10000.,0.,0.)))
        self.assertEqual(value["top"][::2], value["bottom"])

    def test_panel_count_type_and_minimum(self):
        for count in (True, 4., 3, 0, -6):
            with self.subTest(count=count), self.assertRaises(ValueError):
                allocate_panels(count,.5)

    def test_allocation_rounds_ties_up_without_empty_branch(self):
        self.assertEqual(allocate_panels(7,.5),(4,3))
        self.assertEqual(allocate_panels(8,.001),(1,7))
        self.assertEqual(allocate_panels(8,.999),(7,1))

    def test_invalid_allocation_never_silently_corrected(self):
        for allocation in ((0,6),(4,4),(2.5,3.5),(True,5)):
            with self.subTest(allocation=allocation), self.assertRaises(ValueError):
                panelize(EnvelopeDefinition("DuoPitch",6000.,1000.),6,allocation)

    def test_nonfinite_envelope(self):
        for name in ("span", "height", "apex_position"):
            for number in (math.inf, math.nan, -1., 0.):
                with self.subTest(name=name,number=number), self.assertRaises(ValueError):
                    build_candidate(config(**{name:number}))

    def test_reference_normal_is_explicit_and_perpendicular(self):
        with self.assertRaisesRegex(ValueError, "perpendicular"):
            build_candidate(config(plane_normal=[1,1,0]))
        with self.assertRaises(ValueError):
            build_candidate(config(plane_normal=[0,0,0]))

    def test_reference_span_is_single_truth(self):
        with self.assertRaisesRegex(ValueError,"Vão"):
            build_candidate(config(span=7000.))

    def test_role_specs_independent_and_all_five_required(self):
        value=config()
        value["role_specs"]["DIAGONAL"]["rotation"]=90.
        candidate=build_candidate(value)
        for item in candidate.items:
            self.assertEqual(item.spec.rotation,90. if item.role=="DIAGONAL" else 0.)

    def test_scope_is_strict(self):
        for field,value in (("assembly","DoubleAngle"),
                            ("section_geometry_mode","Unknown"),("color",[2,0,0])):
            data=config()
            data["role_specs"]["DIAGONAL"][field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):
                build_candidate(data)

    def test_graph_rejects_missing_coordinate_and_nonfinite(self):
        for point in ((0,0),(math.inf,0,0)):
            graph=TopologyGraph((TopologyNode("a",point,(),"INTERNAL_NODE"),
                                 TopologyNode("b",(1,0,0),(),"INTERNAL_NODE")),
                                (TopologyEdge("e","a","b","DIAGONAL"),))
            self.assertTrue(validate_graph(graph)[0])

    def test_atomic_edge_must_split_at_connected_node(self):
        graph=TopologyGraph(tuple(TopologyNode(k,p,(),"INTERNAL_NODE") for k,p in
                                  (("a",(0,0,0)),("b",(2,0,0)),("c",(1,0,0)),("d",(1,1,0)))),
                            (TopologyEdge("ab","a","b","TOP_CHORD"),TopologyEdge("cd","c","d","VERTICAL")))
        self.assertTrue(any("intermediário" in error for error in validate_graph(graph)[0]))

    def test_frame_rigid_transform_preserves_all_run_lengths(self):
        base=build_candidate(config())
        rotated=build_candidate(config(start=[40,20,-80],end=[40,3620,4720],plane_normal=[1,0,0]))
        for a,b in zip(base.items,rotated.items):
            self.assertEqual(a.key,b.key)
            self.assertAlmostEqual(math.dist(a.start_global,a.end_global),math.dist(b.start_global,b.end_global))

    def test_changes_to_profile_do_not_change_graph_or_runs(self):
        before=build_candidate(config())
        data=copy.deepcopy(before.config)
        data["role_specs"]["DIAGONAL"]["profile_ref"]["profile_id"]="another"
        after=build_candidate(data,before)
        self.assertEqual(before.graph,after.graph)
        self.assertEqual(before.runs,after.runs)
        plan=plan_regeneration(after,before)
        self.assertFalse(plan.structural)
        self.assertNotIn("CREATE_NEW",{action.action for action in plan.actions})

    def test_restored_frame_roundoff_is_not_a_geometry_update(self):
        before=build_candidate(config())
        after=build_candidate(config(plane_normal=[0.,2.220446049250313e-16,1.]))
        self.assertEqual({a.action for a in plan_regeneration(after,before).actions},{"UNCHANGED"})

    def test_color_is_canonical_for_freecad_persistence(self):
        value=config()
        value["role_specs"]["TOP_CHORD"]["color"]=[.25,.45,.7]
        candidate=build_candidate(value)
        color=candidate.config["role_specs"]["TOP_CHORD"]["color"]
        self.assertEqual(color,[64/255,115/255,179/255])
        self.assertEqual(build_candidate(candidate.config).config,candidate.config)

    def test_run_rejects_bent_chain_even_with_inconsistent_envelope(self):
        candidate=build_candidate(config())
        nodes=tuple(replace(n,position_local=(n.position_local[0],1250.,0.))
                    if n.key=="T_S_MAIN_1_2" else n for n in candidate.graph.nodes)
        graph=replace(candidate.graph,nodes=nodes)
        with self.assertRaisesRegex(ValueError,"direção"):
            physical_runs(graph,EnvelopeDefinition("Parallel",6000.,1200.),"Continuous","Continuous")


if __name__ == "__main__":
    unittest.main()
