"""Apply/finish contracts with an explicit fake native transaction boundary."""
from copy import deepcopy
from types import SimpleNamespace
import unittest
from tests.test_truss_qa import config
from tests.test_truss_manual_fixes import definition
from freecad.SteelStructures.trusses.realization import build_candidate
from freecad.SteelStructures.trusses.serialization import encode_state


class ApplySessionTests(unittest.TestCase):
    def test_factory_pratt_does_not_rewrite_explicit_warren(self):
        from dataclasses import asdict
        from freecad.SteelStructures import profile_catalog
        from freecad.SteelStructures.trusses.models import ROLES
        from freecad.SteelStructures.trusses.preset_contracts import compatible_presets
        factory = definition("truss.py", "default_config", dict(
            asdict=asdict, profile_catalog=profile_catalog, ROLES=ROLES))
        self.assertEqual(factory()["topology_preset"], "Pratt")
        self.assertTrue(all("Pratt" in compatible_presets(kind) for kind in ("Parallel", "DuoPitch")))
        controller, _ = self.controller()
        self.assertEqual(controller.session.config["topology_preset"], "Warren")

    def controller(self, existing=True):
        calls = []
        value = build_candidate(config(height=1000.)).config
        owner = SimpleNamespace(Name="Truss", AppliedState=encode_state(build_candidate(value)), requested=deepcopy(value)) if existing else None
        doc = SimpleNamespace(Name="Doc", getObject=lambda name: controller.object)
        if owner:
            owner.Document = doc
        def native_apply(document, cfg, obj):
            calls.append(deepcopy(cfg))
            if obj is None:
                obj = SimpleNamespace(Name="Truss", Document=doc)
            obj.AppliedState = encode_state(build_candidate(cfg))
            obj.requested = deepcopy(cfg)
            return obj
        cls = definition("interactive/truss_controller.py", "TrussController", dict(
            resolve_linked_reference=lambda doc, cfg, obj: cfg,
            build_candidate=build_candidate, apply_truss=native_apply,
            perf_counter=lambda: 0., App=SimpleNamespace(), Gui=SimpleNamespace(Selection=SimpleNamespace(
                clearSelection=lambda:None, addSelection=lambda obj:None))))
        controller = cls.__new__(cls)
        controller.document, controller.object = doc, owner
        controller._persistent_config_reader = lambda obj: deepcopy(obj.requested)
        controller.closed = False
        controller.timings = {}
        controller.session = None
        controller.last_candidate = None
        controller.remove_preview = lambda: None
        controller.cancel_picker = lambda: None
        controller.bind_session(value)
        return controller, calls

    def test_required_apply_then_cancel_keeps_last_applied_height(self):
        controller, calls = self.controller()
        controller.session.config["height"] = 1200.
        owner = controller.apply(controller.session.snapshot())
        self.assertEqual(owner.requested["height"], 1200.)
        self.assertFalse(controller.closed)
        self.assertFalse(controller.session.pending_changes)
        controller.session.config["height"] = 1400.
        controller.cancel()
        self.assertEqual(owner.requested["height"], 1200.)
        self.assertEqual(len(calls), 1)
        self.assertTrue(controller.session.closed)

    def test_creation_multiple_apply_same_owner_and_noop(self):
        controller, calls = self.controller(existing=False)
        owner = controller.apply(controller.session.snapshot())
        self.assertIs(controller.session.owner, owner)
        self.assertIs(controller.apply(controller.session.snapshot()), owner)
        self.assertEqual(len(calls), 1)
        controller.session.config["height"] = 1200.
        self.assertIs(controller.apply(controller.session.snapshot()), owner)
        self.assertEqual(len(calls), 2)
        self.assertEqual(controller.session.baseline_config["height"], 1200.)
        self.assertEqual(controller.session.applied_state, owner.AppliedState)
        self.assertEqual(controller.session.realized_config["height"], 1200.)
        self.assertIs(controller.last_candidate, controller.session.validated_candidate)

    def test_invalid_and_native_failure_leave_baseline_and_owner(self):
        controller, calls = self.controller()
        applied = controller.object.AppliedState
        controller.session.config["height"] = -1.
        with self.assertRaises(ValueError):
            controller.apply(controller.session.snapshot())
        self.assertFalse(calls)
        self.assertEqual(controller.object.AppliedState, applied)
        self.assertEqual(controller.session.baseline_config["height"], 1000.)
        controller.session.config["height"] = 1200.
        namespace = controller.apply.__globals__
        namespace["apply_truss"] = lambda *args: (_ for _ in ()).throw(ValueError("OCC failed"))
        with self.assertRaises(ValueError):
            controller.apply(controller.session.snapshot())
        self.assertEqual(controller.object.AppliedState, applied)
        self.assertTrue(controller.session.pending_changes)
        self.assertFalse(controller.closed)

    def test_ok_with_and_without_changes(self):
        for changed in (False, True):
            controller, calls = self.controller()
            if changed:
                controller.session.config["height"] = 1200.
            controller.accept(controller.session.snapshot())
            self.assertEqual(len(calls), int(changed))
            self.assertTrue(controller.closed)
            self.assertTrue(controller.session.closed)

    def test_external_applied_or_requested_edit_blocks_even_noop_and_latches(self):
        for kind in ("applied", "requested"):
            controller, calls = self.controller()
            applied = controller.object.AppliedState
            if kind == "applied":
                controller.object.AppliedState = encode_state(build_candidate(config(height=900.)))
            else:
                controller.object.requested["height"] = 900.
            with self.assertRaisesRegex(ValueError, "reabra"):
                controller.apply(controller.session.snapshot())
            self.assertFalse(calls)
            controller.object.AppliedState = applied
            controller.object.requested["height"] = 1000.
            with self.assertRaises(ValueError):
                controller.accept(controller.session.snapshot())
            self.assertFalse(controller.session.valid)
            controller.cancel()

    def test_pending_loaded_requested_definition_is_not_a_noop(self):
        controller, calls = self.controller()
        controller.object.requested["height"] = 1200.
        controller.session = None
        controller.bind_session(controller.object.requested)
        self.assertFalse(controller.session.pending_changes)
        controller.apply(controller.session.snapshot())
        self.assertEqual(len(calls), 1)
        self.assertEqual(controller.session.realized_config["height"], 1200.)
        controller.apply(controller.session.snapshot())
        self.assertEqual(len(calls), 1)

    def test_active_document_switch_blocks_apply(self):
        controller, calls = self.controller()
        controller._active_document = lambda: object()
        with self.assertRaises(ValueError):
            controller.apply(controller.session.snapshot())
        self.assertFalse(calls)
        controller.cancel()


if __name__ == "__main__":
    unittest.main()
