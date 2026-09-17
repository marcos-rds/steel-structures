"""Focused C5-A pure contracts and truss integration."""

from dataclasses import replace
import importlib
import math
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from freecad.SteelStructures.fitting import (
    FitActionMode, FitEnd, FittingPolicy, GeometryReference, NominalMember,
    PhysicalFitMode, resolve_physical_fit,
)
from freecad.SteelStructures.fitting.serialization import dumps, loads
from freecad.SteelStructures.fitting.precedence import slot_decision
from freecad.SteelStructures.trusses.assemblies import configure_assembly
from freecad.SteelStructures.trusses.interconnector_options import default_connector
from freecad.SteelStructures.trusses.realization import build_candidate, plan_regeneration
from freecad.SteelStructures.trusses.serialization import decode_state, encode_state
from tests.test_truss_assemblies import config
from tests.test_member_placement import Quantity, Vector


def member(start_node="N0", end_node="N1", start=(0., 0., 0.), end=(10., 10., 0.)):
    return NominalMember("MEMBER:A", "RUN", "DIAGONAL", start_node, end_node, start, end)


def chord():
    return GeometryReference("CHORD:MAIN", "Line", (0., 10., 0.), (10., 0., 0.), (0., 0., 1.))


class PhysicalFitCoreTests(unittest.TestCase):
    def test_none_and_reserved_modes_are_explicit(self):
        none = resolve_physical_fit(member(), None, FittingPolicy())
        self.assertEqual(none.mode, PhysicalFitMode.NONE)
        self.assertIsNone(none.start_action)
        reserved = resolve_physical_fit(
            member(), None, FittingPolicy(mode=PhysicalFitMode.GUSSET_AWARE))
        self.assertEqual(reserved.diagnostics[0].code, "MODE_NOT_IMPLEMENTED")

    def test_end_selection_uses_node_identity(self):
        policy = FittingPolicy(PhysicalFitMode.TO_CHORD)
        start = resolve_physical_fit(member(), chord(), policy, "N0")
        end = resolve_physical_fit(member(), chord(), policy, "N1")
        self.assertEqual(start.start_action.end, FitEnd.START)
        self.assertIsNone(start.end_action)
        self.assertEqual(end.end_action.end, FitEnd.END)
        with self.assertRaisesRegex(ValueError, "nó topológico"):
            resolve_physical_fit(member(), chord(), policy, "UNRELATED")

    def test_oblique_to_chord_uses_plane_cut_and_axial_gap(self):
        plan = resolve_physical_fit(
            member(), chord(), FittingPolicy(PhysicalFitMode.TO_CHORD, gap=5.), "N1")
        action = plan.end_action
        self.assertEqual(action.mode, FitActionMode.PLANE_CUT)
        self.assertEqual(action.gap, 5.)
        self.assertEqual(action.plane_origin, chord().origin)
        self.assertAlmostEqual(abs(action.plane_normal[1]), 1.)

    def test_transverse_uses_length_limit_and_parallel_preserves_last_fit(self):
        vertical = replace(member(), start=(0., 0., 0.), end=(0., 10., 0.))
        transverse = resolve_physical_fit(
            vertical, chord(), FittingPolicy(PhysicalFitMode.TO_CHORD), "N1")
        self.assertEqual(transverse.end_action.mode, FitActionMode.LENGTH_LIMIT)
        horizontal = replace(member(), start=(0., 10., 0.), end=(10., 10., 0.))
        parallel = resolve_physical_fit(
            horizontal, chord(), FittingPolicy(PhysicalFitMode.TO_CHORD), "N1")
        self.assertIsNone(parallel.end_action)
        self.assertEqual(parallel.diagnostics[0].code, "MEMBER_PARALLEL_TO_PLANE")
        self.assertEqual(parallel.diagnostics[0].severity, "Warning")

    def test_serialization_is_deterministic_and_versioned(self):
        plan = resolve_physical_fit(
            member(), chord(), FittingPolicy(PhysicalFitMode.TO_CHORD, gap=3.), "N1")
        encoded = dumps(plan)
        self.assertEqual(loads(encoded), plan)
        self.assertEqual(dumps(loads(encoded)), encoded)
        self.assertIn('"schema_version":2', encoded)

    def test_face_and_edge_adapt_to_the_same_pure_primitives(self):
        policy = FittingPolicy(PhysicalFitMode.TO_CHORD)
        face = GeometryReference("FACE", "Face", chord().origin, normal=(0., 1., 0.))
        edge = replace(chord(), kind="Edge")
        self.assertEqual(resolve_physical_fit(member(), face, policy, "N1").end_action.mode,
                         FitActionMode.PLANE_CUT)
        self.assertEqual(resolve_physical_fit(member(), edge, policy, "N1").end_action.mode,
                         FitActionMode.PLANE_CUT)

    def test_invalid_axis_reference_plane_and_gap_are_rejected(self):
        policy = FittingPolicy(PhysicalFitMode.TO_CHORD)
        with self.assertRaisesRegex(ValueError, "degenerado"):
            resolve_physical_fit(replace(member(), end=(0., 0., 0.)), chord(), policy, "N1")
        with self.assertRaisesRegex(ValueError, "gap axial"):
            resolve_physical_fit(member(), chord(), replace(policy, gap=-1.), "N1")
        bad = replace(chord(), direction=(0., 0., 0.))
        with self.assertRaisesRegex(ValueError, "linha de referência"):
            resolve_physical_fit(member(), bad, policy, "N1")


class TrussPhysicalFitTests(unittest.TestCase):
    def fitted(self, *, gap=0., assembly=False, inclined=False, connector=False):
        value = config()
        value["top_continuity"] = value["bottom_continuity"] = "Continuous"
        if inclined:
            value.update(start=[20., 30., 40.], end=[2420., 30., 40.], plane_normal=[0., -.6, .8])
        role = value["role_specs"]["DIAGONAL"]
        role["physical_fit"], role["physical_fit_gap"] = "ToChord", gap
        if assembly:
            role = configure_assembly(role, "DoubleAngle", 60., interconnectors=(
                (default_connector("Battens"),) if connector else ()))
            value["role_specs"]["DIAGONAL"] = role
        return value, build_candidate(value)

    def test_declared_nodes_fit_each_web_independently_and_crossings_do_not_add_items(self):
        value, candidate = self.fitted()
        diagonals = [item for item in candidate.items if item.role == "DIAGONAL"]
        self.assertTrue(diagonals)
        self.assertEqual(len(diagonals), len([run for run in candidate.runs if run.role == "DIAGONAL"]))
        self.assertTrue(all(item.physical_fit_plan for item in diagonals))
        self.assertTrue(all(any((item.physical_fit_plan["start_action"],
                                item.physical_fit_plan["end_action"])) for item in diagonals))

    def test_continuous_chords_are_targets_and_remain_unadjusted(self):
        value, candidate = self.fitted()
        chords = [item for item in candidate.items if item.role in ("TOP_CHORD", "BOTTOM_CHORD")]
        self.assertEqual(value["top_continuity"], "Continuous")
        self.assertTrue(all(item.physical_fit_plan is None for item in chords))
        self.assertEqual(len([run for run in candidate.runs if run.role == "BOTTOM_CHORD"]), 1)

    def test_to_chord_resolves_the_physical_channel_contour(self):
        value = config()
        value["topology_preset"] = "Pratt"
        value["top_continuity"] = value["bottom_continuity"] = "Continuous"
        value["role_specs"]["VERTICAL"]["physical_fit"] = "ToChord"
        candidate = build_candidate(value)
        actions = [action for item in candidate.items if item.role == "VERTICAL"
                   for action in (item.physical_fit_plan["start_action"],
                                  item.physical_fit_plan["end_action"]) if action]
        self.assertTrue(actions)
        # U 4 x 8.04 with centroid insertion reaches its physical flange
        # 50.8 mm from the nominal chord axis, not the nominal line itself.
        self.assertTrue(all(math.isclose(abs(action["reference_offset"]), 50.8,
                                         abs_tol=1e-7) for action in actions))

    def test_double_assembly_fits_a_and_b_but_never_interconnectors(self):
        _value, candidate = self.fitted(assembly=True, connector=True)
        components = [item for item in candidate.items
                      if item.role == "DIAGONAL" and item.element_kind == "Component"]
        connectors = [item for item in candidate.items
                      if item.role == "DIAGONAL" and item.element_kind == "Interconnector"]
        self.assertEqual({item.component_key for item in components}, {"A", "B"})
        self.assertTrue(all(item.physical_fit_plan for item in components))
        self.assertTrue(connectors)
        self.assertTrue(all(item.physical_fit_plan is None for item in connectors))

    def test_interconnectors_regenerate_over_fitted_host_envelope(self):
        _value, zero = self.fitted(gap=0., assembly=True, connector=True)
        _value, gapped = self.fitted(gap=50., assembly=True, connector=True)
        zero_connectors = {item.key: item for item in zero.items
                           if item.role == "DIAGONAL" and item.element_kind == "Interconnector"}
        gapped_connectors = {item.key: item for item in gapped.items
                             if item.role == "DIAGONAL" and item.element_kind == "Interconnector"}
        self.assertEqual(zero_connectors.keys(), gapped_connectors.keys())
        self.assertTrue(any(zero_connectors[key].start_global != gapped_connectors[key].start_global
                            for key in zero_connectors))
        for candidate in (zero, gapped):
            for run in (run for run in candidate.runs if run.role == "DIAGONAL"):
                components = [item for item in candidate.items if item.run_key == run.key
                              and item.element_kind == "Component"]
                connectors = [item for item in candidate.items if item.run_key == run.key
                              and item.element_kind == "Interconnector"]
                self.assertTrue(connectors)
                start = components[0].start_global
                delta = tuple(b-a for a, b in zip(start, components[0].end_global))
                length = math.sqrt(sum(value*value for value in delta))
                direction = tuple(value/length for value in delta)
                plan = components[0].physical_fit_plan
                low = plan["start_action"]["reference_offset"] + plan["start_action"]["gap"]
                high = length-plan["end_action"]["reference_offset"]-plan["end_action"]["gap"]
                stations = [sum((a+b-2*o)*axis/2 for a, b, o, axis in
                                zip(item.start_global, item.end_global, start, direction))
                            for item in connectors]
                self.assertGreaterEqual(min(stations), low-1e-7)
                self.assertLessEqual(max(stations), high+1e-7)

    def test_gap_and_inclined_plane_update_in_place_with_stable_ids(self):
        value, before = self.fitted(gap=0., inclined=True)
        value["role_specs"]["DIAGONAL"]["physical_fit_gap"] = 7.
        after = build_candidate(value, before)
        plan = plan_regeneration(after, before)
        self.assertFalse(plan.structural)
        self.assertEqual({item.key for item in before.items}, {item.key for item in after.items})
        actions = [item.physical_fit_plan for item in after.items if item.role == "DIAGONAL"]
        self.assertTrue(any((p["start_action"] or p["end_action"])["gap"] == 7. for p in actions))
        normals = [(p["start_action"] or p["end_action"])["plane_normal"]
                   for p in actions if (p["start_action"] or p["end_action"])["mode"] == "PlaneCut"]
        self.assertTrue(normals)
        self.assertTrue(any(abs(normal[2]) > 1e-6 for normal in normals))

    def test_fitted_state_uses_schema4_and_roundtrips(self):
        _value, candidate = self.fitted(gap=2.)
        state = decode_state(encode_state(candidate))
        self.assertEqual(state["schema_version"], 4)
        rebuilt = build_candidate(state["candidate"]["config"])
        self.assertEqual(rebuilt, candidate)

    def test_legacy_role_specs_without_fitting_remain_none(self):
        legacy = config()
        for role in legacy["role_specs"].values():
            role.pop("physical_fit", None)
            role.pop("physical_fit_gap", None)
        candidate = build_candidate(legacy)
        primary = [item for item in candidate.items if item.element_kind == "Component"]
        self.assertTrue(all(item.spec.physical_fit == "None" for item in primary))
        self.assertTrue(all(not item.physical_fit_plan or (
            item.physical_fit_plan["start_action"] is None
            and item.physical_fit_plan["end_action"] is None) for item in primary))
        self.assertTrue(all("physical_fit" not in role
                            for role in candidate.config["role_specs"].values()))
        self.assertLess(decode_state(encode_state(candidate))["schema_version"], 4)

    def test_manual_adjustment_has_priority_over_previous_autofit(self):
        previous = {"AdjustmentMode": "Fixed", "AdjustmentGap": 2.}
        self.assertEqual(slot_decision(
            action_present=True, plan_is_none=False, invalid_plan=False,
            current_mode="Fixed", current_state={**previous, "AdjustmentGap": 19.},
            previous_auto_state=previous), "ManualBlock")
        self.assertEqual(slot_decision(
            action_present=True, plan_is_none=False, invalid_plan=False,
            current_mode="Fixed", current_state=previous,
            previous_auto_state=previous), "Apply")
        self.assertEqual(slot_decision(
            action_present=False, plan_is_none=False, invalid_plan=True,
            current_mode="Fixed", current_state=previous,
            previous_auto_state=previous), "Preserve")

    def test_real_manual_plane_cut_fields_block_autofit_with_human_diagnostic(self):
        _value, candidate = self.fitted()
        item = next(item for item in candidate.items if item.role == "DIAGONAL")
        child = SimpleNamespace(PhysicalFitAutoState="")
        for prefix, geometry in (("Start", "PlaneCut"), ("End", "LengthLimit")):
            setattr(child, prefix+"AdjustmentMode", "Fixed")
            setattr(child, prefix+"AdjustmentGeometryMode", geometry)
            setattr(child, prefix+"AdjustmentGap", Quantity(3.))
            setattr(child, prefix+"FixedReferenceOffset", Quantity(25.))
            setattr(child, prefix+"FixedPlaneNormal", Vector(0., .2, 1.))
        fake_app = SimpleNamespace(Vector=Vector)
        module_name = "freecad.SteelStructures.fitting.freecad_adapter"
        sys.modules.pop(module_name, None)
        try:
            with patch.dict(sys.modules, {"FreeCAD": fake_app}):
                adapter = importlib.import_module(module_name)
                merged, _plan, state, status = adapter.fitting_inputs(item, child, {})
        finally:
            sys.modules.pop(module_name, None)
        self.assertFalse(any("Adjustment" in key for key in merged))
        self.assertEqual(state, "")
        self.assertIn("Ajuste manual existente bloqueia", status)

    def test_automatic_numeric_snapshot_allows_gap_update_and_none_clear(self):
        value = config()
        value["topology_preset"] = "Pratt"
        value["role_specs"]["VERTICAL"]["physical_fit"] = "ToChord"
        value["role_specs"]["VERTICAL"]["physical_fit_gap"] = 0.
        zero = build_candidate(value)
        item = next(item for item in zero.items if item.role == "VERTICAL")
        inputs = {"StartPoint": Vector(*item.start_global),
                  "EndPoint": Vector(*item.end_global), "Rotation": 0.}
        fake_app = SimpleNamespace(Vector=Vector)
        module_name = "freecad.SteelStructures.fitting.freecad_adapter"
        sys.modules.pop(module_name, None)
        try:
            with patch.dict(sys.modules, {"FreeCAD": fake_app}):
                adapter = importlib.import_module(module_name)
                applied, _plan, state, _status = adapter.fitting_inputs(item, None, inputs)
                child = SimpleNamespace(PhysicalFitAutoState=state, **applied)
                value["role_specs"]["VERTICAL"]["physical_fit_gap"] = 50.
                changed = build_candidate(value, zero)
                changed_item = next(current for current in changed.items if current.key == item.key)
                updated, _plan, next_state, status = adapter.fitting_inputs(
                    changed_item, child, inputs)
                self.assertEqual(updated["StartAdjustmentGap"], 50.)
                self.assertEqual(updated["EndAdjustmentGap"], 50.)
                self.assertTrue(next_state)
                self.assertNotIn("manual", status.lower())
                child = SimpleNamespace(PhysicalFitAutoState=next_state,
                                        **{**applied, **updated})
                value["role_specs"]["VERTICAL"]["physical_fit"] = "None"
                cleared = build_candidate(value, changed)
                cleared_item = next(current for current in cleared.items if current.key == item.key)
                restored, _plan, final_state, status = adapter.fitting_inputs(
                    cleared_item, child, inputs)
        finally:
            sys.modules.pop(module_name, None)
        self.assertEqual(restored["StartAdjustmentMode"], "None")
        self.assertEqual(restored["EndAdjustmentMode"], "None")
        self.assertEqual(final_state, "")
        self.assertNotIn("manual", status.lower())


if __name__ == "__main__":
    unittest.main()
