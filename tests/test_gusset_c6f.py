"""Focused C6-F physical placement, bridge, terminal and defaults tests."""

import copy
import math
import unittest
from dataclasses import FrozenInstanceError, asdict
from types import SimpleNamespace

from freecad.SteelStructures import profile_catalog
from freecad.SteelStructures.connections import (
    GussetAccessibility, GussetAttachmentMode, GussetSide,
    attachment_side_options, gusset_attachment_candidates,
)
from freecad.SteelStructures.profiles.models import ProfileRef
from freecad.SteelStructures.trusses.models import ROLES
from freecad.SteelStructures.trusses.assemblies import configure_assembly
from freecad.SteelStructures.trusses.connections import (
    gusset_default_after_edit, gusset_thickness_for_transition,
)
from freecad.SteelStructures.trusses.gussets import preliminary_gusset_outlines
from freecad.SteelStructures.trusses.realization import build_candidate
from tests.test_connections_c5b_polish import three_web_config
from tests.test_connections_c5b_through import k_config
from tests.test_gusset_attachment_c6d import (
    _participant, _profile_surfaces, _spec,
)
from tests.test_gusset_plate_c6a import configured
from tests.test_ridge_fitting import ridge_config
from tests.test_truss_assemblies import config as warren_config
from tests.test_truss_manual_fixes import definition


def _outline(value, node, **gusset):
    candidate = build_candidate(configured(value, node, **gusset))
    outlines, diagnostics = preliminary_gusset_outlines(candidate)
    if diagnostics:
        raise AssertionError([item.message for item in diagnostics])
    return next(item for item in outlines if item.spec.node_key == node)


class AttachmentCandidateTests(unittest.TestCase):
    def candidates(self, designation, thickness=10.):
        surfaces = _profile_surfaces(designation)
        participant = _participant("chord", "BOTTOM_CHORD", "Through")
        spec = _spec(thickness=thickness)
        return surfaces, gusset_attachment_candidates(
            spec, (participant,), surfaces)

    def test_u_outer_inner_are_stable_accessible_and_extrude_to_free_space(self):
        surfaces, candidates = self.candidates('U 4" x 8,04')
        outer = next(value for value in candidates
                     if value.attachment_mode == GussetAttachmentMode.OUTER
                     and value.signed_offset == 11.6)
        inner = next(value for value in candidates
                     if value.attachment_mode == GussetAttachmentMode.INNER
                     and abs(value.signed_offset-6.93) < 1e-6)
        self.assertEqual(outer.accessibility, GussetAccessibility.OUTER_EXPOSED)
        self.assertEqual(inner.accessibility, GussetAccessibility.OPEN_RECESS)
        self.assertEqual((outer.extrusion_sign, inner.extrusion_sign), (1, -1))
        self.assertAlmostEqual(outer.signed_offset-inner.signed_offset, 4.67)
        self.assertIn(GussetSide.CENTER, inner.allowed_sides)
        self.assertNotIn(GussetSide.CENTER, outer.allowed_sides)
        self.assertEqual(outer.stable_key, self.candidates('U 4" x 8,04')[1][
            candidates.index(outer)].stable_key)
        with self.assertRaises(FrozenInstanceError):
            outer.signed_offset = 0.
        # Contact faces bound the web material; both extrusion intervals grow
        # away from that wall rather than through [6.93, 11.60].
        self.assertGreaterEqual(outer.signed_offset, 11.6)
        self.assertLessEqual(inner.signed_offset-10., 6.93)

    def test_rhs_hole_is_not_exposed_and_chs_has_no_flat_candidate(self):
        rhs_surfaces, rhs = self.candidates("RHS 60x40x1,2")
        self.assertTrue(rhs_surfaces)
        self.assertFalse(any(value.attachment_mode == GussetAttachmentMode.INNER
                             for value in rhs))
        chs_surfaces, chs = self.candidates("CHS 88,90x3")
        self.assertEqual((chs_surfaces, chs), ((), ()))

    def test_angle_exposes_only_geometrically_resolved_recesses(self):
        _surfaces, values = self.candidates("L 40 x 4")
        self.assertEqual({value.accessibility for value in values}, {
            GussetAccessibility.OUTER_EXPOSED,
            GussetAccessibility.OPEN_RECESS,
        })
        self.assertIn(7.5, {round(value.signed_offset, 6) for value in values})

    def test_dynamic_sides_hide_center_for_outer_and_keep_it_for_inner(self):
        _surfaces, values = self.candidates('U 4" x 8,04')
        outer = attachment_side_options(values, GussetAttachmentMode.OUTER)
        inner = attachment_side_options(values, GussetAttachmentMode.INNER)
        self.assertNotIn(GussetSide.CENTER, outer)
        self.assertIn(GussetSide.CENTER, inner)
        self.assertTrue({GussetSide.FACE_A, GussetSide.FACE_B}.issubset(set(outer)))

    def test_resolver_cannot_bypass_candidate_side_compatibility(self):
        value, node = three_web_config()
        forbidden = _outline(value, node, attachment_mode="Outer", side="Center")
        self.assertEqual(forbidden.attachment.kind, "NominalFallback")
        automatic = _outline(value, node, attachment_mode="Auto", side="Center")
        self.assertEqual(automatic.attachment.kind, "PhysicalSurface")
        self.assertEqual(automatic.attachment.governing_surface_class.value,
                         "Outer")

    def test_spaced_pair_uses_physical_gap_and_rejects_too_thick_plate(self):
        value, node = three_web_config()
        role = copy.deepcopy(value["role_specs"]["DIAGONAL"])
        role["profile_ref"] = asdict(profile_catalog.ref_for_designation("W 150 x 13,0"))
        value["role_specs"]["DIAGONAL"] = configure_assembly(role, "SpacedPair", 120.)
        valid = _outline(value, node, attachment_mode="Center", side="Center",
                         plate_thickness=10.)
        self.assertEqual(valid.attachment.kind, "AssemblyMidPlane")
        self.assertAlmostEqual(valid.attachment.plate_low, -5.)
        self.assertAlmostEqual(valid.attachment.plate_high, 5.)
        invalid = _outline(value, node, attachment_mode="Center", side="Center",
                           plate_thickness=120.)
        self.assertEqual(invalid.attachment.kind, "NominalFallback")
        self.assertFalse(any(candidate.attachment_mode == GussetAttachmentMode.CENTER
                             for candidate in invalid.attachment.candidates))


class SemanticBoundaryTests(unittest.TestCase):
    def test_two_terminal_webs_have_two_caps_and_one_chord_parallel_bridge(self):
        value = warren_config()
        node = "B_S_MAIN_1_2"
        outline = _outline(value, node)
        caps = [edge for edge in outline.semantic_edges if edge.kind == "WEB_END_CAP"]
        bridges = [edge for edge in outline.semantic_edges
                   if edge.kind == "WEB_SECTOR_BRIDGE"]
        self.assertEqual((len(caps), len(bridges)), (2, 1))
        bridge = bridges[0]
        self.assertAlmostEqual(bridge.end[1]-bridge.start[1], 0., places=6)
        cap_points = {tuple(round(value, 6) for value in point)
                      for cap in caps for point in (cap.start, cap.end)}
        self.assertIn(tuple(round(value, 6) for value in bridge.start), cap_points)
        self.assertIn(tuple(round(value, 6) for value in bridge.end), cap_points)

    def test_k_and_duopitch_do_not_receive_artificial_bridge(self):
        value, node = k_config(False)
        k_outline = _outline(value, node)
        self.assertFalse(any(edge.kind == "WEB_SECTOR_BRIDGE"
                             for edge in k_outline.semantic_edges))
        ridge = _outline(ridge_config(.37, 1100.), "T_S_APEX")
        self.assertFalse(any(edge.kind == "WEB_SECTOR_BRIDGE"
                             for edge in ridge.semantic_edges))

    def test_terminal_boundaries_clip_large_margin_and_overlap_both_sides(self):
        cases = (("DuoPitch", ridge_config(diagonals=False),
                  ("N_S_START", "N_S_END")),
                 ("Parallel", warren_config(),
                  ("B_S_START", "B_S_END")))
        for envelope, base, nodes in cases:
            for node, comparison in ((nodes[0], lambda x: x >= -1e-7),
                                     (nodes[1], lambda x: x <= 1e-7)):
              with self.subTest(envelope=envelope, node=node):
                outline = _outline(copy.deepcopy(base), node,
                                   edge_margin=500., member_overlap=1000.)
                terminal_edges = sum(edge.kind == "TERMINAL_BOUNDARY"
                                     for edge in outline.semantic_edges)
                # At a DuoPitch closure the two real interior chord faces
                # intersect beyond the nominal end; the nominal limit still
                # clips the plate but is not necessarily an active edge.
                self.assertEqual(terminal_edges, 0 if envelope == "DuoPitch" else 1)
                self.assertTrue(all(comparison(point[0]) for point in outline.points))
                self.assertGreater(outline.area, 0.)

    def test_terminal_clipping_is_invariant_in_an_inclined_truss_plane(self):
        horizontal = ridge_config(diagonals=False)
        inclined = copy.deepcopy(horizontal)
        inclined["plane_normal"] = [0., -0.6, 0.8]
        for node in ("N_S_START", "N_S_END"):
            self.assertEqual(_outline(copy.deepcopy(horizontal), node).points,
                             _outline(copy.deepcopy(inclined), node).points)


class GussetDefaultTests(unittest.TestCase):
    def test_new_truss_default_and_transition_copy_last_accepted_value(self):
        factory = definition("truss.py", "default_config", dict(
            ProfileRef=ProfileRef, ROLES=ROLES, asdict=asdict,
            profile_catalog=profile_catalog))
        self.assertEqual(factory()["default_gusset_thickness"], 10.)
        self.assertEqual(gusset_thickness_for_transition("N", None, 10.), 10.)
        self.assertEqual(gusset_thickness_for_transition("N", None, 20.), 20.)

    def test_existing_gusset_value_is_never_overwritten_by_default(self):
        existing = {"form": "Gusset", "gusset": {"plate_thickness": 8.}}
        self.assertEqual(gusset_thickness_for_transition("N", existing, 20.), 8.)
        migrated = build_candidate(warren_config())
        self.assertEqual(migrated.config["default_gusset_thickness"], 10.)

    def test_side_only_edit_does_not_replace_default_with_old_plate_value(self):
        existing = {"form": "Gusset", "gusset": {
            "plate_thickness": 8., "side": "Center"}}
        side_only = {"form": "Gusset", "gusset": {
            "plate_thickness": 8., "side": "FaceA"}}
        self.assertEqual(gusset_default_after_edit(
            "N", existing, side_only, 20.), 20.)
        thickness_edit = copy.deepcopy(side_only)
        thickness_edit["gusset"]["plate_thickness"] = 12.
        self.assertEqual(gusset_default_after_edit(
            "N", existing, thickness_edit, 20.), 12.)

    def test_old_owner_receives_additive_read_only_default(self):
        ensure = definition("truss.py", "ensure_gusset_defaults", {})
        modes = {}
        owner = SimpleNamespace(PropertiesList=[])
        def add_property(_kind, name, _group):
            owner.PropertiesList.append(name)
            setattr(owner, name, None)
        owner.addProperty = add_property
        owner.setEditorMode = lambda name, mode: modes.__setitem__(name, mode)
        ensure(owner)
        self.assertEqual(owner.DefaultGussetThickness, 10.)
        self.assertEqual(modes["DefaultGussetThickness"], 1)
        ensure(owner)
        self.assertEqual(owner.PropertiesList.count("DefaultGussetThickness"), 1)


if __name__ == "__main__":
    unittest.main()
