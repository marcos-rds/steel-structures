"""Shared draft contracts, independent of FreeCAD and Qt."""
from copy import deepcopy
from types import SimpleNamespace
import unittest
from tests.test_truss_qa import config
from tests.test_truss_manual_fixes import definition
from freecad.SteelStructures.trusses.edit_session import TrussEditSession
from freecad.SteelStructures.trusses.editing import edit_candidate
from freecad.SteelStructures.trusses.realization import build_candidate
from freecad.SteelStructures.trusses.serialization import encode_state


class SessionTests(unittest.TestCase):
    def controller(self, value, owner=None, resolver=None):
        cls = definition("interactive/truss_controller.py", "TrussController", dict(
            resolve_linked_reference=resolver or (lambda doc, cfg, obj: cfg),
            build_candidate=build_candidate))
        controller = cls.__new__(cls)
        controller.document, controller.object = None, owner
        controller.session = None
        controller.last_candidate = None
        controller.bind_session(value)
        return controller

    def test_round_trip_full_draft_and_loaded_baseline_do_not_alias(self):
        value = config()
        value.update(reference_mode="DraftLine", reference_source="Line", reference_linked=True,
                     reference_edge="Edge1", advanced_extension={"future": [1, 2]},
                     default_gusset_thickness=12.)
        value["role_specs"]["DIAGONAL"].update(physical_fit="ToChord", physical_fit_gap=4.)
        session = TrussEditSession(None, None, value)
        self.assertEqual(session.snapshot(), value)
        exported = session.snapshot()
        exported["advanced_extension"]["future"].clear()
        value["advanced_extension"]["future"].clear()
        self.assertEqual(session.config["advanced_extension"]["future"], [1, 2])
        baseline = session.baseline_config
        baseline.clear()
        self.assertTrue(session.baseline_config)

    def test_creation_and_edit_unchanged_are_clean_with_distinct_realized_state(self):
        initial = build_candidate(config())
        for owner in (None, SimpleNamespace(AppliedState=encode_state(initial))):
            controller = self.controller(initial.config, owner)
            session = controller.session
            controller.candidate(session.snapshot())
            self.assertFalse(session.pending_changes)
            self.assertIs(session.validated_candidate, controller.last_candidate)
            self.assertEqual(session.baseline_config, initial.config)
        requested = deepcopy(initial.config)
        requested["height"] = 1400.
        controller = self.controller(requested, owner)
        self.assertEqual(controller.session.realized_config["height"], 1200.)
        self.assertEqual(controller.session.config["height"], 1400.)
        self.assertEqual(controller.candidate(requested).config["height"], 1400.)
        self.assertEqual(owner.AppliedState, encode_state(initial))

    def test_successive_nested_edits_and_revert_track_revision(self):
        controller = self.controller(config())
        candidate = controller.candidate(config())
        session = controller.session
        clean = session.snapshot()
        revision = session.revision
        session.config["role_specs"]["DIAGONAL"]["rotation"] = 45.
        self.assertTrue(session.pending_changes)
        self.assertGreater(session.revision, revision)
        self.assertIsNone(session.validated_candidate)
        self.assertIs(controller.last_candidate, candidate)
        controller.candidate(session.snapshot())
        self.assertIsNotNone(session.validated_candidate)
        session.replace_config(clean)
        self.assertFalse(session.pending_changes)

    def test_invalid_candidate_keeps_draft_and_reconciliation_history(self):
        controller = self.controller(config())
        before = controller.candidate(config())
        invalid = deepcopy(before.config)
        invalid["height"] = -10.
        with self.assertRaises(ValueError):
            controller.candidate(invalid)
        self.assertEqual(controller.session.config["height"], -10.)
        self.assertIsNone(controller.session.validated_candidate)
        self.assertIs(controller.last_candidate, before)
        self.assertTrue(controller.session.diagnostics)
        self.assertTrue(controller.session.pending_changes)
        controller.candidate(before.config)
        self.assertIsNotNone(controller.session.validated_candidate)

    def test_invalid_associative_source_opens_then_can_be_corrected(self):
        value = config(reference_mode="DraftLine", reference_source="Missing", reference_linked=True)
        def resolve(doc, cfg, owner):
            if cfg["reference_linked"]:
                raise ValueError("Fonte ausente")
            return cfg
        controller = self.controller(value, resolver=resolve)
        with self.assertRaises(ValueError):
            controller.candidate(value)
        self.assertEqual(controller.session.baseline_config, value)
        controller.session.config["reference_linked"] = False
        controller.candidate(controller.session.snapshot())
        self.assertIsNotNone(controller.session.validated_candidate)

    def test_custom_round_trip_preserves_full_configuration(self):
        candidate = build_candidate(config())
        edge = next(e for e in candidate.graph.edges if e.role == "DIAGONAL")
        custom = edit_candidate(candidate, "remove_edge", key=edge.key)
        controller = self.controller(custom)
        result = controller.candidate(custom)
        self.assertEqual(result.config["topology_mode"], "Custom")
        self.assertEqual(controller.session.snapshot(), result.config)
        self.assertEqual(controller.candidate(controller.session.snapshot()).graph, result.graph)
        self.assertFalse(controller.session.pending_changes)

    def test_composites_interconnectors_and_gussets_survive_successive_edits(self):
        from tests.test_truss_interconnectors import configured
        value = configured("DoubleLacing", "Both")
        value["connection_intents"] = {"B_S_MAIN_1_3": {
            "form": "Gusset", "gusset": {"plate_thickness": 12., "edge_margin": 31.,
            "member_overlap": 163., "normal_clearance": 2., "axial_clearance": 3.,
            "transverse_placement": ""}}}
        controller = self.controller(value)
        first = controller.candidate(value)
        advanced = deepcopy(first.config["role_specs"])
        intents = deepcopy(first.config["connection_intents"])
        for height in (800., 900., 700.):
            draft = controller.session.snapshot()
            draft["height"] = height
            candidate = controller.candidate(draft)
            self.assertEqual(candidate.config["role_specs"], advanced)
            self.assertEqual(candidate.config["connection_intents"], intents)
        self.assertFalse(controller.session.pending_changes)
        owner = SimpleNamespace(AppliedState=encode_state(candidate))
        reopened = self.controller(candidate.config, owner)
        self.assertEqual(reopened.session.snapshot(), candidate.config)
        self.assertEqual(reopened.candidate(reopened.session.snapshot()).items, candidate.items)

    def test_active_panel_cannot_be_reused_for_another_owner_or_document(self):
        doc, owner = object(), None
        panel = SimpleNamespace(session=TrussEditSession(doc, owner, config()))
        namespace = dict(_active_panel=panel)
        open_panel = definition("interactive/truss_controller.py", "open_truss_panel", namespace)
        self.assertIs(open_panel(doc), panel)
        with self.assertRaises(ValueError):
            open_panel(object())
        with self.assertRaises(ValueError):
            open_panel(doc, object())
        self.assertFalse(panel.session.closed)

    def test_context_owner_identity_and_close(self):
        owner = SimpleNamespace(Name="Truss")
        doc = SimpleNamespace(getObject=lambda name: owner)
        owner.Document = doc
        session = TrussEditSession(doc, owner, config())
        session.assert_context(doc, owner)
        for other_doc, other_owner in ((object(), owner), (doc, object()), (doc, None)):
            with self.assertRaises(ValueError):
                session.assert_context(other_doc, other_owner)
        doc.getObject = lambda name: None
        with self.assertRaises(ValueError):
            session.snapshot()
        session.close()
        session.close()
        with self.assertRaises(ValueError):
            session.replace_config(config())

    def test_initial_control_defaults_are_clean_without_replacing_baseline(self):
        value = config()
        session = TrussEditSession(None, None, value)
        projected = deepcopy(value)
        projected.update(target_spacing=1000., target_angle=45., reference_edge="Edge1")
        session.initialize_projection(projected)
        self.assertEqual(session.baseline_config, value)
        self.assertFalse(session.pending_changes)
        with self.assertRaises(ValueError):
            session.initialize_projection(projected)
        session.config["height"] = 1400.
        self.assertTrue(session.pending_changes)

    def test_closed_document_invalidates_session_and_current_candidate(self):
        opened = [True]
        session = TrussEditSession(None, None, config(), document_is_open=lambda: opened[0])
        session.record_candidate(build_candidate(config()))
        self.assertTrue(session.valid)
        opened[0] = False
        self.assertFalse(session.valid)
        self.assertIsNone(session.validated_candidate)
        with self.assertRaises(ValueError):
            session.snapshot()


if __name__ == "__main__":
    unittest.main()
