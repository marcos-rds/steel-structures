"""C4-B role/candidate/preview contracts, without document or GUI mutation."""
from copy import deepcopy
from dataclasses import replace
import math
import unittest
from freecad.SteelStructures.trusses.assemblies import configure_assembly, role_assembly_spec
from freecad.SteelStructures.trusses.realization import build_candidate, plan_regeneration
from freecad.SteelStructures.trusses.serialization import encode_state, decode_state
from freecad.SteelStructures.trusses.assembly_preview import transverse_preview, longitudinal_preview
from freecad.SteelStructures.trusses.interconnector_options import (
    default_connector, edited_connector, quantity_to_stations, stations_to_quantity, compatible_profile)
from freecad.SteelStructures import profile_catalog
from tests.test_truss_assemblies import config


def configured(kind="Battens", plane="FaceA"):
    value = config()
    connector = default_connector(kind)
    if kind != "SpacerPlate":
        connector = replace(connector, attachment_plane=plane)
    value["role_specs"]["TOP_CHORD"] = configure_assembly(value["role_specs"]["TOP_CHORD"],
        "SpacedPair", 240., interconnectors=(connector,))
    return value


class TrussInterconnectorTests(unittest.TestCase):
    def test_all_patterns_expand_members_without_changing_topology_or_runs(self):
        plain = build_candidate(config())
        for kind, count in (("SpacerPlate",4),("Battens",4),("SingleLacing",3),("DoubleLacing",6)):
            value = configured(kind)
            before = deepcopy(value)
            candidate = build_candidate(value)
            self.assertEqual(candidate.graph,plain.graph)
            self.assertEqual(candidate.runs,plain.runs)
            self.assertEqual(value,before)
            items = [i for i in candidate.items if i.element_kind=="Interconnector"]
            self.assertEqual(len(items),count)
            self.assertTrue(all(i.role=="TOP_CHORD" and i.component_key=="" for i in items))
            self.assertTrue(all(i.spec.profile_ref!=candidate.config["role_specs"]["TOP_CHORD"]["profile_ref"] for i in items))

    def test_role_roundtrip_and_composition_edits_preserve_connector(self):
        value=configured("DoubleLacing","Both")
        role=value["role_specs"]["TOP_CHORD"]
        old=role_assembly_spec(role).interconnectors
        changed=configure_assembly(role,"DoubleChannelOutward",300.)
        self.assertEqual(role_assembly_spec(changed).interconnectors,old)
        candidate=build_candidate(value)
        state=decode_state(encode_state(candidate))
        self.assertEqual(build_candidate(state["candidate"]["config"]),candidate)

    def test_side_changes_and_count_changes_use_regeneration_plan(self):
        a=build_candidate(configured())
        b=build_candidate(configured(plane="FaceB"))
        both=build_candidate(configured(plane="Both"))
        self.assertFalse(plan_regeneration(b,a).structural)
        self.assertEqual({i.key for i in a.items},{i.key for i in b.items})
        self.assertTrue(plan_regeneration(both,b).structural)
        self.assertEqual(sum(i.action=="CREATE_NEW" for i in plan_regeneration(both,b).actions),4)
        self.assertEqual(sum(i.action=="REMOVE_EXISTING" for i in plan_regeneration(b,both).actions),4)

    def test_each_role_including_end_posts_uses_its_own_nominal_runs(self):
        value=config()
        for key,role in value["role_specs"].items():
            value["role_specs"][key]=configure_assembly(role,"SpacedPair",240.,interconnectors=(default_connector("Battens"),))
        candidate=build_candidate(value)
        for run in candidate.runs:
            elements=[i for i in candidate.items if i.run_key==run.key]
            self.assertEqual(len(elements),6)
            self.assertEqual(sum(i.element_kind=="Interconnector" for i in elements),4)

    def test_preview_projects_the_same_realization_and_both_faces(self):
        role=configured("Battens","Both")["role_specs"]["TOP_CHORD"]
        original=deepcopy(role)
        transverse=transverse_preview(role,2400.)
        longitudinal=longitudinal_preview(role,2400.)
        self.assertEqual(role,original)
        self.assertEqual(len(transverse["components"]),2)
        self.assertEqual(len(transverse["attachments"]),2)
        self.assertEqual({f["label"] for f in transverse["faces"] if f["selected"]},{"A","B"})
        self.assertEqual(len(longitudinal["lines"]),10)
        self.assertAlmostEqual(longitudinal["distributions"][0][1].effective_spacing,(2400.-50.8)/3)
        outlines = [line for line in longitudinal["lines"] if not line["component"]]
        self.assertTrue(all(line["outline"] for line in outlines))
        self.assertAlmostEqual(min(line["longitudinal_bounds"][0] for line in outlines),0.)
        self.assertAlmostEqual(max(line["longitudinal_bounds"][1] for line in outlines),2400.)

    def test_longitudinal_changes_immediately_for_offsets_and_start_side(self):
        role=configured("SingleLacing")["role_specs"]["TOP_CHORD"]
        a=longitudinal_preview(role,2400.)
        spec=role_assembly_spec(role).interconnectors[0]
        role=configure_assembly(role,"SpacedPair",240.,interconnectors=(replace(spec,start_offset=100.,end_offset=200.,start_side="B"),))
        b=longitudinal_preview(role,2400.)
        self.assertEqual(len(b["stations"]),4)
        outlines = [line for line in b["lines"] if not line["component"]]
        self.assertAlmostEqual(min(line["longitudinal_bounds"][0] for line in outlines),100.,places=6)
        self.assertAlmostEqual(max(line["longitudinal_bounds"][1] for line in outlines),2200.,places=6)
        self.assertNotEqual(a["lines"][2]["start"],b["lines"][2]["start"])

    def test_simple_transition_explicitly_removes_connectors_from_candidate(self):
        value=configured()
        before=build_candidate(value)
        value["role_specs"]["TOP_CHORD"]=configure_assembly(value["role_specs"]["TOP_CHORD"],"Single")
        after=build_candidate(value)
        self.assertFalse(any(i.element_kind=="Interconnector" for i in after.items))
        self.assertTrue(plan_regeneration(after,before).structural)

    def test_ui_quantity_mapping_and_maximum_spacing(self):
        for kind in ("SpacerPlate","Battens","SingleLacing","DoubleLacing"):
            count=quantity_to_stations(kind,4)
            self.assertEqual(stations_to_quantity(kind,count),4)
            spec=default_connector(kind)
            edited=edited_connector(spec,kind,"FaceA","ByTargetSpacing",4,300.,20.,30.,"B")
            self.assertIsNone(edited.distribution.station_count)
            self.assertEqual(edited.distribution.target_spacing,300.)
            self.assertEqual(edited.attachment_plane,"InnerFaces" if kind=="SpacerPlate" else "FaceA")

    def test_ui_filters_do_not_restrict_geometric_core(self):
        u=profile_catalog.get('U 4" x 8,04').definition
        l=profile_catalog.get('L 40 x 4').definition
        flat=profile_catalog.get('Barra Chata 50,8x6,35').definition
        self.assertTrue(compatible_profile(flat,"Battens"))
        self.assertFalse(compatible_profile(l,"Battens"))
        self.assertTrue(compatible_profile(l,"DoubleLacing"))
        self.assertFalse(compatible_profile(u,"SingleLacing"))
        spec=replace(default_connector("Battens"),profile_ref=profile_catalog.ref_for_designation('U 4" x 8,04'))
        value=configured()
        role=value["role_specs"]["TOP_CHORD"]
        value["role_specs"]["TOP_CHORD"]=configure_assembly(role,"SpacedPair",240.,interconnectors=(spec,))
        self.assertTrue(build_candidate(value).items)
        with self.assertRaisesRegex(ValueError,"perfil compatível"):
            edited_connector(spec,"Battens","FaceA","ByCount",4,300,0,0,"A")


if __name__=="__main__":
    unittest.main()
