"""Focused pure/integration coverage for C5-B connection intent."""

import copy
import json
import unittest
from dataclasses import asdict, replace
from pathlib import Path

from freecad.SteelStructures.connections import (
    ConnectionForm, ConnectionIntent, DirectFitPolicy, FasteningIntent,
    GussetFitSpec, PriorityMember, dumps, loads, resolve_connection,
)
from freecad.SteelStructures.trusses.connections import (
    _run_data, intent_from_data, resolve_truss_connections,
)
from freecad.SteelStructures.trusses.realization import (build_candidate, plan_regeneration,
                                                         reference_frame, transform_point)
from freecad.SteelStructures.trusses.serialization import encode_state, decode_state
from freecad.SteelStructures.trusses.assemblies import configure_assembly
from freecad.SteelStructures.trusses.interconnector_options import default_connector
from freecad.SteelStructures.fitting.precedence import slot_decision
from freecad.SteelStructures import profile_catalog
from tests.test_truss_assemblies import config


NODE = "T_S_MAIN_1_4"


def configured(form="Direct", policy="BalancedMiter", **changes):
    value = config()
    intent = dict(form=form, direct_policy=policy)
    intent.update(changes)
    value["connection_intents"] = {NODE: intent}
    return value


def node_webs(candidate):
    return [item for item in candidate.items
            if item.role == "DIAGONAL" and NODE in (item.start_node_key, item.end_node_key)
            and item.element_kind == "Component"]


class ConnectionContractTests(unittest.TestCase):
    def test_pure_connection_package_has_no_cad_or_ui_dependency(self):
        root = Path(__file__).parents[1] / "freecad" / "SteelStructures" / "connections"
        source = "\n".join(path.read_text(encoding="utf-8") for path in root.glob("*.py"))
        for forbidden in ("import FreeCAD", "import Part", "from PySide", "import coin"):
            self.assertNotIn(forbidden, source)

    def test_versioned_serialization_and_defaults(self):
        intent = ConnectionIntent("I", "N", ConnectionForm.DIRECT,
                                  FasteningIntent.WELDED,
                                  DirectFitPolicy.PRIORITY,
                                  ("R2", "R1"), PriorityMember.PARTICIPANT_B,
                                  GussetFitSpec(8., 2., 15.))
        self.assertEqual(loads(dumps(intent)), intent)
        default = intent_from_data("N", {})
        self.assertEqual(default.form, ConnectionForm.GEOMETRIC_ONLY)
        self.assertEqual(default.fastening, FasteningIntent.UNSPECIFIED)

    def test_participants_are_stable_runs_and_continuous_chord_is_through(self):
        candidate = build_candidate(config())
        resolutions, diagnostics, _ = resolve_truss_connections(
            build_candidate(configured()), (0., 0., 1.))
        self.assertFalse(diagnostics)
        participant_keys = [p.run_key for p in resolutions[0].participants]
        self.assertEqual(participant_keys, sorted(participant_keys))
        chord = next(p for p in resolutions[0].participants if p.role == "TOP_CHORD")
        self.assertEqual(chord.end, "Through")
        self.assertTrue(chord.continuous_through)
        self.assertEqual(candidate.graph, build_candidate(configured()).graph)

    def test_geometric_only_adds_no_connection_fit(self):
        candidate = build_candidate(configured(form="GeometricOnly"))
        self.assertTrue(all((item.physical_fit_plan or {}).get("mode") != "Custom"
                            for item in node_webs(candidate)))

    def test_geometric_only_preserves_explicit_c5a_to_chord(self):
        value = configured(form="GeometricOnly")
        value["role_specs"]["DIAGONAL"]["physical_fit"] = "ToChord"
        candidate = build_candidate(value)
        self.assertTrue(any(
            (item.physical_fit_plan["start_action"] or item.physical_fit_plan["end_action"])
            for item in node_webs(candidate)))
        self.assertTrue(all(action["source"] == "AutoFit"
                            for item in node_webs(candidate)
                            for action in (item.physical_fit_plan["start_action"],
                                           item.physical_fit_plan["end_action"]) if action))

    def test_balanced_miter_has_one_shared_plane_through_nominal_node(self):
        candidate = build_candidate(configured())
        actions = []
        for item in node_webs(candidate):
            plan = item.physical_fit_plan
            action = plan["start_action"] or plan["end_action"]
            self.assertEqual(plan["mode"], "Custom")
            self.assertEqual(action["source"], "ConnectionIntent")
            self.assertEqual(action["mode"], "PlaneCut")
            actions.append(action)
        self.assertEqual(actions[0]["plane_origin"], actions[1]["plane_origin"])
        self.assertEqual(actions[0]["plane_normal"], actions[1]["plane_normal"])
        self.assertEqual(tuple(actions[0]["plane_origin"]), transform_point(
            candidate.graph.node(NODE).position_local, reference_frame(candidate.config)))

    def test_balanced_gap_is_individual_and_applied_after_plane(self):
        value = configured()
        value["role_specs"]["DIAGONAL"]["physical_fit_gap"] = 12.5
        actions = [(item.physical_fit_plan["start_action"] or
                    item.physical_fit_plan["end_action"])
                   for item in node_webs(build_candidate(value))]
        self.assertEqual([a["gap"] for a in actions], [12.5, 12.5])
        self.assertEqual(actions[0]["plane_origin"], actions[1]["plane_origin"])

    def test_priority_keeps_primary_and_fits_secondary_to_its_physical_face(self):
        base = build_candidate(config())
        runs = [p.run_key for p in resolve_truss_connections(
            build_candidate(configured()), (0., 0., 1.))[0][0].participants
                if p.role == "DIAGONAL"]
        candidate = build_candidate(configured(
            policy="Priority", participant_run_keys=runs,
            priority_member="ParticipantA"))
        by_run = {item.run_key: item for item in node_webs(candidate)}
        self.assertNotEqual(by_run[runs[0]].physical_fit_plan["mode"], "Custom")
        action = (by_run[runs[1]].physical_fit_plan["start_action"] or
                  by_run[runs[1]].physical_fit_plan["end_action"])
        self.assertEqual(action["source"], "ConnectionIntent")
        self.assertEqual(action["reference_key"], runs[0])
        self.assertEqual(base.graph, candidate.graph)

    def test_more_than_two_webs_refuses_balanced_miter(self):
        candidate = build_candidate(configured())
        resolution = resolve_truss_connections(candidate, (0., 0., 1.))[0][0]
        extra = copy.deepcopy(resolution.participants[0])
        resolution = resolve_connection(resolution.intent,
                                        resolution.participants + (extra,),
                                        candidate.graph.node(NODE).position_local,
                                        (0., 0., 1.))
        self.assertFalse(resolution.directives)
        self.assertEqual(resolution.diagnostics[0].code,
                         "BALANCED_MITER_REQUIRES_TWO_WEBS")

    def test_different_physical_geometries_fall_back_independent(self):
        candidate = build_candidate(configured())
        resolution = resolve_truss_connections(candidate, (0., 0., 1.))[0][0]
        webs = [p for p in resolution.participants if p.role == "DIAGONAL"]
        participants = tuple(replace(p, geometry_key="different") if p == webs[1] else p
                             for p in resolution.participants)
        fallback = resolve_connection(resolution.intent, participants,
                                      candidate.graph.node(NODE).position_local,
                                      (0., 0., 1.))
        self.assertFalse(fallback.directives)
        self.assertEqual(fallback.diagnostics[0].code,
                         "BALANCED_MITER_GEOMETRY_MISMATCH")

    def test_gusset_keeps_normal_clearance_distinct_from_axial_setback(self):
        value = configured(form="Gusset", gusset=dict(
            plate_thickness=10., normal_clearance=3., axial_clearance=22., side="Center"))
        candidate = build_candidate(value)
        for item in node_webs(candidate):
            action = item.physical_fit_plan["start_action"] or item.physical_fit_plan["end_action"]
            self.assertEqual(item.physical_fit_plan["mode"], "GussetAware")
            self.assertEqual(action["reference_offset"], 22.)
            self.assertEqual(action["gap"], 0.)
        saved = candidate.config["connection_intents"][NODE]["gusset"]
        self.assertEqual(saved["plate_thickness"], 10.)
        self.assertEqual(saved["normal_clearance"], 3.)

    def test_double_assembly_propagates_fit_and_excludes_interconnectors(self):
        value = configured()
        value["role_specs"]["DIAGONAL"]["physical_fit_gap"] = 30.
        value["role_specs"]["DIAGONAL"] = configure_assembly(
            value["role_specs"]["DIAGONAL"], "DoubleAngle", 60.,
            interconnectors=(default_connector("SingleLacing"),))
        candidate = build_candidate(value)
        components = node_webs(candidate)
        self.assertEqual({item.component_key for item in components}, {"A", "B"})
        self.assertTrue(all(item.physical_fit_plan["mode"] == "Custom"
                            for item in components))
        connectors = [item for item in candidate.items if item.role == "DIAGONAL"
                      and item.element_kind == "Interconnector"]
        self.assertTrue(connectors)
        self.assertTrue(all(item.physical_fit_plan is None for item in connectors))
        unfitted = copy.deepcopy(value)
        unfitted["connection_intents"][NODE]["direct_policy"] = "Independent"
        before = {item.key: (item.start_global, item.end_global)
                  for item in build_candidate(unfitted).items
                  if item.element_kind == "Interconnector"}
        after = {item.key: (item.start_global, item.end_global) for item in connectors}
        self.assertEqual(set(before), set(after))
        self.assertTrue(any(before[key] != after[key] for key in before))

    def test_double_channel_center_gusset_uses_same_logical_run(self):
        value = configured(form="Gusset", gusset=dict(
            plate_thickness=8., normal_clearance=2., axial_clearance=18., side="Center"))
        role = value["role_specs"]["DIAGONAL"]
        role["profile_ref"] = asdict(profile_catalog.ref_for_designation('U 4" x 8,04'))
        value["role_specs"]["DIAGONAL"] = configure_assembly(
            role, "DoubleChannelInward", 140.)
        candidate = build_candidate(value)
        components = node_webs(candidate)
        self.assertEqual({item.component_key for item in components}, {"A", "B"})
        self.assertTrue(all(item.physical_fit_plan["mode"] == "GussetAware"
                            for item in components))
        self.assertEqual(len({item.run_key for item in components}), 2)

    def test_real_manual_end_state_blocks_connection_autofit(self):
        manual_plane_cut = {
            "AdjustmentMode": "Fixed", "AdjustmentGeometryMode": "PlaneCut",
            "AdjustmentGap": 3., "FixedReferenceOffset": 25.,
            "FixedPlaneNormal": "0.0,0.2,1.0",
        }
        self.assertEqual(slot_decision(
            action_present=True, plan_is_none=False, invalid_plan=False,
            current_mode="Fixed", current_state=manual_plane_cut,
            previous_auto_state=None), "ManualBlock")
        previous_auto = dict(manual_plane_cut)
        edited = dict(manual_plane_cut, FixedReferenceOffset=31.)
        self.assertEqual(slot_decision(
            action_present=True, plan_is_none=False, invalid_plan=False,
            current_mode="Fixed", current_state=edited,
            previous_auto_state=previous_auto), "ManualBlock")

    def test_invalid_reference_preserves_previous_connection_action(self):
        valid = build_candidate(configured())
        changed = configured()
        changed["connection_intents"][NODE]["participant_run_keys"] = ["removed-run"]
        rebuilt = build_candidate(changed, valid)
        for before, after in zip(node_webs(valid), node_webs(rebuilt)):
            old = before.physical_fit_plan["start_action"] or before.physical_fit_plan["end_action"]
            new = after.physical_fit_plan["start_action"] or after.physical_fit_plan["end_action"]
            self.assertEqual(new, old)
        self.assertNotIn("removed-run", json.dumps(rebuilt.config["connection_intents"]))

    def test_connection_change_preserves_object_keys_and_is_nonstructural(self):
        before = build_candidate(config())
        after = build_candidate(configured(), before)
        plan = plan_regeneration(after, before)
        self.assertFalse(plan.structural)
        self.assertEqual({item.key for item in before.items}, {item.key for item in after.items})

    def test_schema5_only_for_explicit_intents_and_legacy_remains_schema4(self):
        legacy = build_candidate(config())
        legacy_version = json.loads(encode_state(legacy))["schema_version"]
        self.assertLess(legacy_version, 5)
        connected = build_candidate(configured())
        state = decode_state(encode_state(connected))
        self.assertEqual(state["schema_version"], 5)
        self.assertEqual(build_candidate(state["candidate"]["config"]), connected)
        raw = json.loads(encode_state(legacy))
        raw["candidate"]["config"].pop("connection_intents", None)
        raw["schema_version"] = legacy_version
        restored = build_candidate(decode_state(json.dumps(raw))["candidate"]["config"])
        self.assertEqual(restored.items, legacy.items)


if __name__ == "__main__":
    unittest.main()
