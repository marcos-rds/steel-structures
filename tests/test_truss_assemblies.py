"""Focused C3-B role integration, legacy compatibility and preview contracts."""
import copy
import json
import math
import unittest
from dataclasses import asdict
from freecad.SteelStructures import profile_catalog
from freecad.SteelStructures.assemblies.transforms import SectionTransform
from freecad.SteelStructures.trusses.assemblies import (
    configure_assembly, role_assembly_spec, compatible_modes, role_profile, assembly_frame)
from freecad.SteelStructures.trusses.assembly_preview import transverse_preview
from freecad.SteelStructures.trusses.realization import build_candidate, plan_regeneration
from freecad.SteelStructures.trusses.serialization import encode_state, decode_state
from tests.test_truss_task_panel import config_fixture


def config():
    value = config_fixture()
    value.update(span=2400., height=700., start=[0., 0., 0.], end=[2400., 0., 0.])
    value["role_specs"]["END_POST"] = copy.deepcopy(value["role_specs"]["END_POST_LEFT"])
    for key, role in value["role_specs"].items():
        role["profile_ref"] = asdict(profile_catalog.ref_for_designation(
            'U 4" x 8,04' if key in ("TOP_CHORD", "BOTTOM_CHORD") else 'L 40 x 4'))
    return value


class TrussAssemblyTests(unittest.TestCase):
    def test_missing_assembly_is_identical_to_single(self):
        explicit = config()
        legacy = copy.deepcopy(explicit)
        for role in legacy["role_specs"].values():
            role.pop("assembly")
        before, after = build_candidate(explicit), build_candidate(legacy)
        self.assertEqual(before.items, after.items)
        self.assertFalse(plan_regeneration(after, before).structural)
        self.assertTrue(all(a.action == "UNCHANGED" for a in plan_regeneration(after, before).actions))
        self.assertEqual(json.loads(encode_state(after))["schema_version"], 2)

    def test_composite_roundtrip_uses_schema3(self):
        value = config()
        value["role_specs"]["TOP_CHORD"] = configure_assembly(value["role_specs"]["TOP_CHORD"], "DoubleChannelInward", 110)
        candidate = build_candidate(value)
        state = decode_state(encode_state(candidate))
        self.assertEqual(state["schema_version"], 3)
        self.assertEqual(build_candidate(state["candidate"]["config"]), candidate)

    def test_old_c1_and_c2_states_remain_readable(self):
        state = json.loads(encode_state(build_candidate(config())))
        for version in (1, 2):
            state["schema_version"] = version
            self.assertEqual(decode_state(json.dumps(state))["schema_version"], version)

    def test_family_compatibility(self):
        value = config()
        angle, channel = (value["role_specs"][k] for k in ("DIAGONAL", "TOP_CHORD"))
        self.assertEqual(compatible_modes(role_profile(angle)), ("Single", "DoubleAngle", "SpacedPair"))
        self.assertIn("DoubleChannelInward", compatible_modes(role_profile(channel)))
        for role, mode in ((channel, "DoubleAngle"), (angle, "DoubleChannelOutward")):
            with self.assertRaisesRegex(ValueError, "incompatível"):
                configure_assembly(role, mode, 100)

    def test_profile_change_cannot_silently_keep_invalid_composition(self):
        value = config()
        composite = configure_assembly(value["role_specs"]["TOP_CHORD"], "DoubleChannelInward", 100)
        composite["profile_ref"] = value["role_specs"]["DIAGONAL"]["profile_ref"]
        with self.assertRaisesRegex(ValueError, "incompatível"):
            role_assembly_spec(composite)
        simple = configure_assembly(composite, "Single")
        self.assertNotIn("assembly_spec", simple)
        self.assertEqual(role_assembly_spec(simple).behavior_mode, "Single")

    def test_case_a_expands_roles_without_changing_logical_topology(self):
        value = config()
        before = build_candidate(value)
        for role in ("TOP_CHORD", "BOTTOM_CHORD"):
            value["role_specs"][role] = configure_assembly(value["role_specs"][role], "DoubleChannelInward", 100)
        value["role_specs"]["DIAGONAL"] = configure_assembly(value["role_specs"]["DIAGONAL"], "DoubleAngle", 40)
        after = build_candidate(value)
        self.assertEqual(before.graph, after.graph)
        self.assertEqual(before.runs, after.runs)
        for run in after.runs:
            children = [i for i in after.items if i.run_key == run.key]
            self.assertEqual(len(children), 2 if run.role in ("TOP_CHORD", "BOTTOM_CHORD", "DIAGONAL") else 1)
            self.assertTrue(all(i.role == run.role for i in children))

    def test_stable_component_ids_preserve_a_across_cardinality(self):
        value = config()
        one = build_candidate(value)
        value["role_specs"]["TOP_CHORD"] = configure_assembly(value["role_specs"]["TOP_CHORD"], "DoubleChannelOutward", 100)
        two = build_candidate(value)
        plan = plan_regeneration(two, one, {i.key: "object_"+i.key for i in one.items})
        self.assertTrue(plan.structural)
        a = next(i for i in two.items if i.role == "TOP_CHORD" and i.component_key == "A")
        b = next(i for i in two.items if i.role == "TOP_CHORD" and i.component_key == "B")
        self.assertEqual(a.key, a.run_key)
        self.assertEqual(json.loads(b.key), [b.run_key, "ASSEMBLY", "B"])
        self.assertEqual(next(p for p in plan.actions if p.key == a.key).existing_binding, "object_"+a.key)
        self.assertTrue(plan_regeneration(one, two).structural)

    def test_same_cardinality_spacing_orientation_profile_color_update_in_place(self):
        value = config()
        role = configure_assembly(value["role_specs"]["TOP_CHORD"], "SpacedPair", 100)
        value["role_specs"]["TOP_CHORD"] = role
        before = build_candidate(value)
        role.update(profile_ref=value["role_specs"]["DIAGONAL"]["profile_ref"], rotation=35, color=[1, 0, 0])
        value["role_specs"]["TOP_CHORD"] = configure_assembly(role, "SpacedPair", 150,
            transforms=(SectionTransform(90, True), SectionTransform(270)))
        after = build_candidate(value)
        plan = plan_regeneration(after, before)
        self.assertFalse(plan.structural)
        self.assertEqual({i.key for i in before.items}, {i.key for i in after.items})
        self.assertTrue(all(a.action in ("UPDATE_EXISTING", "UNCHANGED") for a in plan.actions))

    def test_channel_inward_outward_is_not_global_rotation(self):
        role = config()["role_specs"]["TOP_CHORD"]
        inward = role_assembly_spec(configure_assembly(role, "DoubleChannelInward", 100))
        outward = role_assembly_spec(configure_assembly(role, "DoubleChannelOutward", 100))
        self.assertEqual([c.section_transform.reflect_x for c in inward.components], [False, True])
        self.assertEqual([c.section_transform.reflect_x for c in outward.components], [True, False])
        self.assertEqual([c.transverse_translation for c in inward.components], [c.transverse_translation for c in outward.components])

    def test_spacing_rotates_once_with_role_frame(self):
        value = config()
        role = dict(value["role_specs"]["TOP_CHORD"], rotation=90.)
        value["role_specs"]["TOP_CHORD"] = configure_assembly(role, "SpacedPair", 100,
            transforms=(SectionTransform(90, True), SectionTransform(180)))
        candidate = build_candidate(value)
        a, b = [i for i in candidate.items if i.role == "TOP_CHORD"]
        self.assertAlmostEqual(math.dist(a.start_global, b.start_global), 100)
        self.assertAlmostEqual(abs(b.start_global[2]-a.start_global[2]), 100)
        self.assertAlmostEqual(b.start_global[1]-a.start_global[1], 0)
        self.assertEqual(a.spec.rotation, 0.)  # role roll is already in section_u_global
        self.assertEqual(a.section_transform, dict(rotation_degrees=90., reflect_x=True))

    def test_preview_insertion_matches_realized_axes_in_inclined_frame(self):
        value = config()
        value.update(start=[10., 20., 30.], end=[2410., 20., 30.], plane_normal=[0., -.6, .8])
        role = configure_assembly(dict(value["role_specs"]["TOP_CHORD"], rotation=37), "SpacedPair", 137)
        value["role_specs"]["TOP_CHORD"] = role
        candidate = build_candidate(value)
        nominal = copy.deepcopy(value)
        nominal["role_specs"]["TOP_CHORD"] = configure_assembly(role, "Single")
        logical = next(i for i in build_candidate(nominal).items if i.role == "TOP_CHORD")
        base = assembly_frame((logical.start_global, logical.end_global), logical.section_u_global, 0.)
        preview = transverse_preview(role)
        for drawn, actual in zip(preview["components"], [i for i in candidate.items if i.role == "TOP_CHORD"]):
            p = drawn["insertion"]
            expected = tuple(logical.start_global[j]+p.x*base.u[j]+p.y*base.v[j] for j in range(3))
            self.assertLess(math.dist(expected, actual.start_global), 1e-7)
            self.assertAlmostEqual(math.dist(actual.start_global, actual.end_global), 2400)

    def test_transverse_preview_uses_real_insertion_and_transform(self):
        role = dict(config()["role_specs"]["DIAGONAL"], insertion="outer_corner", rotation=90)
        role = configure_assembly(role, "DoubleAngle", 40)
        preview = transverse_preview(role)
        a, b = preview["components"]
        self.assertAlmostEqual(math.dist((a["insertion"].x, a["insertion"].y),
                                        (b["insertion"].x, b["insertion"].y)), 40)
        # Outer corner is a real contour vertex attached to each physical axis.
        for component in (a, b):
            p = component["insertion"]
            self.assertTrue(any(math.hypot(q.x-p.x, q.y-p.y) < 1e-8 for q in component["paths"][0]))

    def test_candidate_and_preview_leave_caller_config_untouched(self):
        value = config()
        value["role_specs"]["TOP_CHORD"] = configure_assembly(value["role_specs"]["TOP_CHORD"], "SpacedPair", 200)
        before = copy.deepcopy(value)
        build_candidate(value)
        transverse_preview(value["role_specs"]["TOP_CHORD"])
        self.assertEqual(value, before)

    def test_default_spaced_pair_is_parallel_not_mirrored(self):
        role = configure_assembly(config()["role_specs"]["TOP_CHORD"], "SpacedPair", 200)
        self.assertEqual([c.section_transform for c in role_assembly_spec(role).components], [SectionTransform()]*2)

    def test_component_order_is_canonicalized_by_key_not_position(self):
        role = configure_assembly(config()["role_specs"]["TOP_CHORD"], "SpacedPair", 200)
        before = role_assembly_spec(role)
        role["assembly_spec"]["spec"]["components"].reverse()
        self.assertEqual(role_assembly_spec(role), before)

    def test_channel_label_cannot_disagree_with_physical_arrangement(self):
        role = configure_assembly(config()["role_specs"]["TOP_CHORD"], "DoubleChannelInward", 100)
        role["assembly"] = "DoubleChannelOutward"
        with self.assertRaisesRegex(ValueError, "diverge"):
            role_assembly_spec(role)

    def test_unsupported_transverse_arrangement_is_not_silently_flattened(self):
        role = configure_assembly(config()["role_specs"]["TOP_CHORD"], "SpacedPair", 100)
        components = role["assembly_spec"]["spec"]["components"]
        components[0]["transverse_translation"] = [0, -50]
        components[1]["transverse_translation"] = [0, 50]
        with self.assertRaisesRegex(ValueError, "editor requer"):
            role_assembly_spec(role)

    def test_center_and_symmetric_pair_exposed_without_near_far(self):
        role = config()["role_specs"]["TOP_CHORD"]
        for insertion in ("Center", "SymmetricPair"):
            self.assertEqual(role_assembly_spec(configure_assembly(role, "SpacedPair", 100, insertion)).assembly_insertion, insertion)
        with self.assertRaises(ValueError):
            configure_assembly(role, "SpacedPair", 100, "NearSide")


if __name__ == "__main__":
    unittest.main()
