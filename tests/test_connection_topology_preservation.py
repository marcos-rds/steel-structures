"""Partial intent preservation across successive, unconfirmed candidates."""
import copy
from types import SimpleNamespace
import unittest

from freecad.SteelStructures.trusses.connections import connection_participants
from freecad.SteelStructures.trusses.realization import build_candidate, plan_regeneration
from freecad.SteelStructures.trusses.serialization import decode_state, encode_state
from tests.test_gusset_c6p import real_config
from tests.test_truss_manual_fixes import definition


class PreservationTests(unittest.TestCase):
    node = "B_S_MAIN_1_3"

    def initial(self, preset="Warren", policy=None):
        value = real_config("Parallel", preset)
        value["connection_intents"] = {self.node: {
            "form": "Direct" if policy else "Gusset",
            "direct_policy": policy or "Independent",
            "gusset": {"plate_thickness": 12., "edge_margin": 31.,
                       "member_overlap": 163., "normal_clearance": 2.,
                       "axial_clearance": 3., "transverse_placement": ""}}}
        return build_candidate(value)

    def change(self, before, **changes):
        value = copy.deepcopy(before.config)
        value.update(changes)
        return build_candidate(value, before)

    def test_two_diagonals_gain_and_lose_vertical_without_losing_parameters(self):
        before = self.initial()
        original = copy.deepcopy(before.config)
        for preset, count in (("WarrenVerticals", 3), ("Warren", 2),
                              ("WarrenVerticals", 3), ("Pratt", 2), ("Warren", 2)):
            after = self.change(before, topology_preset=preset)
            webs = [p for p in connection_participants(after, self.node)
                    if p.role in ("DIAGONAL", "VERTICAL")]
            self.assertEqual(len(webs), count)
            self.assertEqual(after.config["connection_intents"], original["connection_intents"])
            before = after
        self.assertEqual(decode_state(encode_state(before))["candidate"]["config"][
            "connection_intents"], original["connection_intents"])

    def test_balanced_policy_falls_back_only_when_invalid(self):
        before = self.initial(policy="BalancedMiter")
        after = self.change(before, topology_preset="WarrenVerticals")
        intent = after.config["connection_intents"][self.node]
        self.assertEqual(intent["direct_policy"], "Independent")
        self.assertEqual(intent["gusset"], before.config["connection_intents"][self.node]["gusset"])
        before = self.initial("WarrenVerticals", "BalancedMiter")
        after = self.change(before, topology_preset="Warren")
        self.assertEqual(after.config["connection_intents"][self.node]["direct_policy"], "BalancedMiter")

    def test_explicit_priority_survives_addition_and_falls_back_on_removal(self):
        for role, expected in (("DIAGONAL", "Priority"), ("VERTICAL", "Independent")):
            before = self.initial("WarrenVerticals", "Priority")
            key = next(p.run_key for p in connection_participants(before, self.node) if p.role == role)
            before.config["connection_intents"][self.node]["priority_run_key"] = key
            after = self.change(before, topology_preset="Warren")
            intent = after.config["connection_intents"][self.node]
            self.assertEqual(intent["direct_policy"], expected)
            self.assertEqual(intent["priority_run_key"], key if expected == "Priority" else "")
            self.assertEqual(self.change(after, topology_preset="WarrenVerticals").config[
                "connection_intents"][self.node], intent)

    def test_explicit_selection_prunes_missing_member_without_selecting_all(self):
        before = self.initial("WarrenVerticals")
        keys = [p.run_key for p in connection_participants(before, self.node)]
        before.config["connection_intents"][self.node]["participant_run_keys"] = keys
        after = self.change(before, topology_preset="Warren")
        expected = [key for key in keys if not key.startswith("VERTICAL:")]
        self.assertEqual(after.config["connection_intents"][self.node]["participant_run_keys"], expected)
        before.config["connection_intents"][self.node]["participant_run_keys"] = [
            key for key in keys if key.startswith("VERTICAL:")]
        self.assertNotIn(self.node, self.change(before, topology_preset="Warren").config["connection_intents"])

    def test_legacy_priority_keeps_the_physical_primary(self):
        from freecad.SteelStructures.trusses.connections import resolve_truss_connections
        before = self.initial("WarrenVerticals", "Priority")
        intent = before.config["connection_intents"][self.node]
        intent["priority_member"] = "ParticipantA"
        resolution = resolve_truss_connections(before, (0., 0., 1.))[0][0]
        target = resolution.directives[0].target_run_key
        after = self.change(before, topology_preset="Warren")
        self.assertEqual(after.config["connection_intents"][self.node]["priority_run_key"], target)

    def test_envelope_changes_never_transfer_to_equal_coordinates(self):
        before = self.initial()
        for envelope in ("DuoPitch", "Parallel", "DuoPitch", "Parallel"):
            after = self.change(before, envelope_type=envelope)
            self.assertFalse(after.config["connection_intents"])
            before = after
        value = real_config("DuoPitch", "Warren")
        value["connection_intents"] = {"B_S_LEFT_2_3": {
            "form": "Gusset", "gusset": {"plate_thickness": 12.}}}
        pitched = build_candidate(value)
        parallel = self.change(pitched, envelope_type="Parallel")
        self.assertEqual(pitched.graph.node("B_S_LEFT_2_3").position_local,
                         parallel.graph.node(self.node).position_local)
        self.assertFalse(parallel.config["connection_intents"])

    def test_real_removal_and_dimensions(self):
        before = self.initial()
        self.assertEqual(self.change(before, height=2400.).config["connection_intents"],
                         before.config["connection_intents"])
        self.assertFalse(self.change(before, panel_count=4).config["connection_intents"])

    def test_explicit_transverse_position_and_plate_identity_survive(self):
        from freecad.SteelStructures.trusses.gussets import preliminary_gusset_outlines
        before = self.initial()
        outline = preliminary_gusset_outlines(before)[0][0]
        position = next(c.stable_key for c in outline.attachment.candidates
                        if c.governing_participant_key == outline.attachment.governing_participant_key
                        and c.accessibility.value == "OuterExposed" and c.placement.value == "NearA")
        before.config["connection_intents"][self.node]["gusset"]["transverse_placement"] = position
        for preset in ("WarrenVerticals", "Warren"):
            after = self.change(before, topology_preset=preset)
            outlines, diagnostics = preliminary_gusset_outlines(after)
            self.assertFalse(diagnostics)
            self.assertEqual(len(outlines), 1)
            self.assertEqual(outlines[0].spec.stable_key, outline.spec.stable_key)
            self.assertEqual(outlines[0].spec.transverse_placement, position)
            self.assertEqual(after.config["connection_intents"], before.config["connection_intents"])
            before = after

    def test_editor_refresh_publishes_reconciled_state_without_aliasing(self):
        cls = definition("interactive/truss_topology_editor.py", "TopologyCanvas", dict(
            TrussPreview2D=object, __package__="freecad.SteelStructures.interactive"))
        before = self.initial(policy="BalancedMiter")
        after = self.change(before, topology_preset="WarrenVerticals")
        panel = SimpleNamespace(_initial=copy.deepcopy(before.config),
            get_config=lambda: before.config,
            controller=SimpleNamespace(preview=lambda config: {"nodes": [{"key": self.node}]}, last_candidate=after))
        canvas = cls.__new__(cls)
        canvas.editor = SimpleNamespace(panel=panel, diagnostic_legend=SimpleNamespace(setVisible=lambda x: None))
        preview_refreshes = []
        canvas.editor._refresh_transverse_preview = lambda: preview_refreshes.append(
            copy.deepcopy(panel._initial["connection_intents"]))
        canvas.set_model = lambda model: None
        canvas.scene = lambda: SimpleNamespace(items=lambda: [])
        canvas.update_selection_halo = lambda: None
        canvas.refresh_candidate()
        self.assertEqual(panel._initial["connection_intents"], after.config["connection_intents"])
        panel._initial["connection_intents"].clear()
        self.assertTrue(after.config["connection_intents"])
        refreshed = []
        canvas.editor._connection_node = self.node
        canvas.editor.select_node = refreshed.append
        canvas._last_model = {}
        canvas.refresh_candidate()
        self.assertEqual(refreshed, [self.node])
        self.assertEqual(preview_refreshes, [after.config["connection_intents"]]*2)

    def test_controller_uses_successive_candidates_before_creation_and_apply(self):
        cls = definition("interactive/truss_controller.py", "TrussController", dict(
            resolve_linked_reference=lambda doc, config, obj: config,
            build_candidate=build_candidate, decode_state=decode_state))
        initial = self.initial()
        for owner in (None, SimpleNamespace(AppliedState=encode_state(initial))):
            controller = cls.__new__(cls)
            controller.document, controller.object = None, owner
            controller.last_candidate = None
            before = controller.candidate(initial.config)
            for preset in ("WarrenVerticals", "Warren", "WarrenVerticals"):
                value = copy.deepcopy(before.config)
                value["topology_preset"] = preset
                after = controller.candidate(value)
                self.assertIs(controller.last_candidate, after)
                self.assertEqual(after.config["connection_intents"], initial.config["connection_intents"])
                before = after
            if owner:
                self.assertEqual(owner.AppliedState, encode_state(initial))

    def test_surviving_members_keep_bindings_and_manual_conflicts(self):
        before = self.initial()
        after = self.change(before, topology_preset="WarrenVerticals")
        bindings = {item.key: "Object"+str(index) for index, item in enumerate(before.items)}
        protected = next(iter(bindings))
        plan = plan_regeneration(after, before, bindings, {protected: "manual"})
        for action in plan.actions:
            if action.key in bindings:
                self.assertEqual(action.existing_binding, bindings[action.key])
        self.assertEqual(next(a.action for a in plan.actions if a.key == protected), "CONFLICT")


if __name__ == "__main__":
    unittest.main()
