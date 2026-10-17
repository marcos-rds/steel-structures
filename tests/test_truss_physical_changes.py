"""Physical staleness excludes presentation and includes every fabricated element."""
from copy import deepcopy
from dataclasses import asdict
import unittest

from freecad.SteelStructures.trusses.physical_changes import same_physical_definition, materialization_pending
from freecad.SteelStructures.trusses.realization import build_candidate
from freecad.SteelStructures.trusses.assemblies import configure_assembly
from freecad.SteelStructures.trusses.interconnector_options import default_connector
from tests.test_truss_assemblies import config
from tests.test_truss_physical_mass import fixture
from freecad.SteelStructures.connections import GussetSide, GussetAttachmentMode
from freecad.SteelStructures.profiles.geometry import SectionGeometryMode


class PhysicalChangesTests(unittest.TestCase):
    def test_serialized_current_and_frame_roundoff_match(self):
        candidate=build_candidate(config())
        applied=asdict(candidate)
        applied["items"][0]["start_global"]=list(applied["items"][0]["start_global"])
        applied["items"][0]["start_global"][0]+=1e-12
        self.assertTrue(same_physical_definition(candidate,applied))

    def test_supported_missing_item_defaults_are_normalized(self):
        candidate=build_candidate(config())
        applied=asdict(candidate)
        for item in applied["items"]:
            item.pop("element_label")
            for key in ("generated_element_key","run_key","assembly_key","component_key","physical_fit_plan"):
                item.pop(key)
            item["spec"].pop("color")
        self.assertTrue(same_physical_definition(candidate,applied))

    def test_color_labels_and_inactive_driver_values_do_not_stale_mass(self):
        before=build_candidate(config())
        value=deepcopy(before.config)
        value.update(target_spacing=998.,target_angle=33.,reference_source="visual-name")
        for role in value["role_specs"].values(): role["color"]=[.1,.2,.3]
        after=asdict(build_candidate(value))
        after["items"][0]["element_label"]="Only a display label"
        self.assertTrue(same_physical_definition(after,asdict(before)))

    def test_geometry_topology_profile_and_section_changes_stale_mass(self):
        before=build_candidate(config())
        for mode in ("height","panels","profile","rotation","section_mode","fit"):
            with self.subTest(mode=mode):
                value=deepcopy(before.config)
                if mode=="height": value["height"]+=20.
                if mode=="panels": value["panel_count"]+=2
                if mode=="profile": value["role_specs"]["DIAGONAL"]["profile_ref"]=value["role_specs"]["TOP_CHORD"]["profile_ref"]
                if mode=="rotation": value["role_specs"]["DIAGONAL"]["rotation"]+=90.
                if mode=="section_mode": value["role_specs"]["DIAGONAL"]["section_geometry_mode"]=next(mode.value for mode in SectionGeometryMode if mode.value!="Detailed")
                if mode=="fit": value["role_specs"]["DIAGONAL"].update(physical_fit="ToChord",physical_fit_gap=3.)
                self.assertFalse(same_physical_definition(build_candidate(value),asdict(before)))

    def test_composition_spacing_and_interconnector_changes_stale_mass_but_colors_do_not(self):
        value=config()
        value["role_specs"]["TOP_CHORD"]=configure_assembly(value["role_specs"]["TOP_CHORD"],"SpacedPair",240.,
            interconnectors=(default_connector("Battens"),))
        before=asdict(build_candidate(value))
        colored=deepcopy(before)
        for item in colored["items"]:
            item["spec"]["color"]=[.1,.1,.1]
            spec=item["spec"].get("assembly_spec")
            if spec:
                for component in spec.get("components",[]): component["color"]=[.2,.2,.2]
                for connector in spec.get("interconnectors",[]): connector["color"]=[.3,.3,.3]
        self.assertTrue(same_physical_definition(colored,before))
        for kind,spacing in (("Battens",250.),("SingleLacing",240.)):
            value["role_specs"]["TOP_CHORD"]=configure_assembly(value["role_specs"]["TOP_CHORD"],"SpacedPair",spacing,
                interconnectors=(default_connector(kind),))
            self.assertFalse(same_physical_definition(build_candidate(value),before))

    def test_all_active_gusset_geometry_fields_stale_mass(self):
        before=asdict(build_candidate(config()))
        before["config"]["connection_intents"]={"N":dict(form="Gusset",gusset=dict(plate_thickness=8.))}
        for key,value in (("plate_thickness",10.),("edge_margin",35.),("member_overlap",175.),
                          ("normal_clearance",2.),("axial_clearance",3.),("side",next(value.value for value in GussetSide if value.value!="Center")),
                          ("attachment_mode",next(value.value for value in GussetAttachmentMode if value.value!="Auto")),
                          ("chord_contact","TrussInterior"),("transverse_placement","slot-key")):
            with self.subTest(key=key):
                after=deepcopy(before)
                after["config"]["connection_intents"]["N"]["gusset"][key]=value
                self.assertFalse(same_physical_definition(after,before))

    def test_fastening_and_inactive_gusset_parameters_are_nonphysical(self):
        before=asdict(build_candidate(config()))
        after=deepcopy(before)
        after["config"]["connection_intents"]={"N":dict(form="GeometricOnly",fastening="Welded",gusset=dict(edge_margin=30.))}
        self.assertTrue(same_physical_definition(after,before))

    def test_pending_materialization_is_distinct_from_failed_geometry(self):
        owner,_=fixture()
        self.assertFalse(materialization_pending(owner))
        owner.GeneratedMembers[0].State=["Touched"]
        self.assertTrue(materialization_pending(owner))
        owner.GeneratedMembers[0].GenerationStatus="Erro: old Shape preserved"
        self.assertFalse(materialization_pending(owner))
        owner.GeneratedMembers[0].GenerationStatus="Pending"
        self.assertTrue(materialization_pending(owner))
        owner.GeneratedMembers[0].State=["Invalid"]
        self.assertFalse(materialization_pending(owner))
