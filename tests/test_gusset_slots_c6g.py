"""Focused pure C6-G attachment-slot and contact-window tests."""

import copy
import unittest
from dataclasses import asdict
from types import SimpleNamespace

from freecad.SteelStructures import profile_catalog
from freecad.SteelStructures.connections import (
    GussetAttachmentMode, GussetAttachmentSlotKind, GussetResidualStatus,
    GussetSlotPlacement, attachment_side_options, derive_attachment_slots,
    material_intervals, slot_placements,
)
from freecad.SteelStructures.trusses.gussets import preliminary_gusset_outlines
from freecad.SteelStructures.trusses.gusset_attachment import (
    component_connection_surfaces, component_section_material,
)
from freecad.SteelStructures.trusses.realization import build_candidate, reference_frame
from tests.test_truss_assemblies import config
from tests.test_connections_c5b_polish import three_web_config
from tests.test_gusset_plate_c6a import configured


PARTICIPANT = SimpleNamespace(participant_key="chord", role="BOTTOM_CHORD",
                              end="Through", assembly="Single")


def geometry(designation):
    value = config()
    role = copy.deepcopy(value["role_specs"]["BOTTOM_CHORD"])
    role.update(profile_ref=asdict(profile_catalog.ref_for_designation(designation)),
                section_geometry_mode="Simplified")
    value["role_specs"]["BOTTOM_CHORD"] = role
    candidate = build_candidate(value)
    item = next(item for item in candidate.items
                if item.role == "BOTTOM_CHORD" and item.element_kind == "Component")
    normal = reference_frame(candidate.config)[3]
    surfaces = component_connection_surfaces(
        item, PARTICIPANT, item.start_global, normal)
    material = component_section_material(
        item, PARTICIPANT, item.start_global, normal)
    slots = derive_attachment_slots("chord", normal, (material,), surfaces)
    return surfaces, (material,), slots


class FamilyTopologyTests(unittest.TestCase):
    def test_open_families_derive_accessible_slots_without_family_switches(self):
        for designation in ('U 4" x 8,04', "W 150 x 13,0", "HP 310 x 132,0",
                            "L 40 x 4", "Ue 150 × 60 × 20 × 3,00"):
            with self.subTest(designation=designation):
                _surfaces, _materials, slots = geometry(designation)
                self.assertTrue(slots)
                self.assertTrue(any(slot.open_accessibility for slot in slots))
                self.assertFalse(any(slot.kind == GussetAttachmentSlotKind.ENCLOSED_VOID
                                     for slot in slots))

    def test_hollow_voids_are_explicit_and_never_offer_a_placement(self):
        for designation in ("RHS 60x40x1,2", "SHS 40x40x1,2", "CHS 88,90x3"):
            with self.subTest(designation=designation):
                _surfaces, materials, slots = geometry(designation)
                enclosed = [slot for slot in slots
                            if slot.kind == GussetAttachmentSlotKind.ENCLOSED_VOID]
                self.assertTrue(enclosed)
                self.assertTrue(all(not slot.open_accessibility
                                    and not slot.allowed_placements
                                    and not slot_placements(slot, 8., materials)
                                    for slot in enclosed))

    def test_w_and_hp_recesses_are_split_by_actual_material(self):
        for designation in ("W 150 x 13,0", "HP 310 x 132,0"):
            with self.subTest(designation=designation):
                _surfaces, materials, slots = geometry(designation)
                recesses = [slot for slot in slots
                            if slot.kind == GussetAttachmentSlotKind.OPEN_RECESS]
                self.assertGreaterEqual(len(recesses), 2)
                for slot in recesses:
                    for _placement, low, high, window in slot_placements(
                            slot, 8., materials):
                        self.assertLess(low, high)
                        self.assertTrue(window.intervals)

    def test_u_lateral_recess_does_not_offer_a_plate_from_webs(self):
        _surfaces, materials, slots = geometry('U 4" x 8,04')
        recess = next(slot for slot in slots
                      if slot.kind == GussetAttachmentSlotKind.OPEN_RECESS
                      and slot.free_low <= 0. <= slot.free_high)
        placements = slot_placements(recess, 8., materials)
        self.assertEqual(recess.access_sign, 0)
        self.assertFalse(recess.open_accessibility)
        self.assertEqual(placements, ())

    def test_w_web_splits_recesses_and_does_not_offer_false_center(self):
        _surfaces, materials, slots = geometry("W 150 x 13,0")
        recesses = [slot for slot in slots
                    if slot.kind == GussetAttachmentSlotKind.OPEN_RECESS]
        self.assertGreaterEqual(len(recesses), 2)
        self.assertTrue(all(GussetSlotPlacement.CENTER not in slot.allowed_placements
                            for slot in recesses))
        self.assertTrue(all(not slot.open_accessibility
                            and not slot_placements(slot, 8., materials)
                            for slot in recesses))

    def test_every_returned_family_placement_is_collision_free_at_member_axis(self):
        for designation in ('U 4" x 8,04', "W 150 x 13,0", "HP 310 x 132,0",
                            "L 40 x 4", "Ue 150 × 60 × 20 × 3,00"):
            with self.subTest(designation=designation):
                _surfaces, materials, slots = geometry(designation)
                occupied = material_intervals(materials, 0.)
                values = [value for slot in slots
                          if slot.open_accessibility
                          for value in slot_placements(slot, 8., materials)]
                self.assertTrue(values)
                for _placement, low, high, _window in values:
                    overlap = max((min(high, b)-max(low, a)
                                   for a, b in occupied), default=0.)
                    self.assertLessEqual(overlap, .1)


class PureAssemblyGapTests(unittest.TestCase):
    def test_two_transformed_components_form_three_gap_placements(self):
        from freecad.SteelStructures.connections import (
            GussetConnectionSurface, GussetSectionMaterial2D, GussetSide,
            GussetSurfaceClass,
        )
        normal = (0., 0., 1.)
        axis = (1., 0., 0.)
        materials = (
            GussetSectionMaterial2D("p", "A", ((-20., -10.), (-10., -10.),
                                                (-10., 10.), (-20., 10.)), (), axis),
            GussetSectionMaterial2D("p", "B", ((10., -10.), (20., -10.),
                                                (20., 10.), (10., 10.)), (), axis),
        )
        def surface(component, surface_id, offset, sign):
            return GussetConnectionSurface(
                "p", "r", component, surface_id, "DIAGONAL", "End", normal,
                offset, ((0., -10.), (0., 10.)),
                GussetSide.FACE_A if sign > 0 else GussetSide.FACE_B,
                sign, 0., 20., surface_class=GussetSurfaceClass.OUTER,
                component_band_low=offset, component_band_high=offset)
        surfaces = (surface("A", "A:gap", -10., 1),
                    surface("B", "B:gap", 10., -1))
        slots = derive_attachment_slots("p", normal, materials, surfaces)
        gap = next(slot for slot in slots
                   if slot.kind == GussetAttachmentSlotKind.BETWEEN_COMPONENTS)
        self.assertEqual((gap.free_low, gap.free_high,
                          gap.available_clear_width), (-10., 10., 20.))
        values = slot_placements(gap, 8., materials)
        self.assertEqual(tuple(value[0] for value in values), (
            GussetSlotPlacement.NEAR_A, GussetSlotPlacement.CENTER,
            GussetSlotPlacement.NEAR_B))
        self.assertEqual(tuple((value[1], value[2]) for value in values),
                         ((-10., -2.), (-4., 4.), (2., 10.)))


class ProductionSlotResolutionTests(unittest.TestCase):
    def outline(self, designation, side, mode="Inner"):
        value, node = three_web_config()
        reference = asdict(profile_catalog.ref_for_designation(designation))
        for role in ("TOP_CHORD", "BOTTOM_CHORD"):
            value["role_specs"][role]["profile_ref"] = copy.deepcopy(reference)
        candidate = build_candidate(configured(
            value, node, attachment_mode=mode, side=side))
        outlines, diagnostics = preliminary_gusset_outlines(candidate)
        self.assertFalse(diagnostics)
        return next(outline for outline in outlines
                    if outline.spec.node_key == node)

    def test_w_lateral_recesses_are_not_accessible_from_web_region(self):
        side_a = self.outline("W 150 x 13,0", "FaceA")
        side_b = self.outline("W 150 x 13,0", "FaceB")
        self.assertEqual(side_a.attachment.kind, "NominalFallback")
        self.assertEqual(side_b.attachment.kind, "NominalFallback")
        self.assertEqual(attachment_side_options(
            side_a.attachment.candidates, GussetAttachmentMode.INNER),
            ())
        centered = self.outline("W 150 x 13,0", "Center")
        self.assertEqual(centered.attachment.kind, "NominalFallback")

    def test_governing_chord_is_contact_without_alternative_surface_warning(self):
        outline = self.outline('U 4" x 8,04', "Center", "Auto")
        governing = next(value for value in outline.attachment.residuals
                         if value.participant_key
                         == outline.attachment.governing_participant_key)
        self.assertEqual((governing.status, governing.residual),
                         (GussetResidualStatus.CONTACT, 0.))
        self.assertFalse(any("101,6" in message
                             for message in outline.attachment.diagnostics))
        self.assertIsNotNone(outline.attachment.contact_window)


if __name__ == "__main__":
    unittest.main()
