"""Focused C6-E attachment-mode, surface classification and UX tests."""

import copy
import json
import unittest
from dataclasses import asdict, replace

from freecad.SteelStructures import profile_catalog
from freecad.SteelStructures.connections import (
    GussetAttachmentMode, GussetFitSpec, GussetResidualStatus, GussetSide,
    GussetSurfaceClass, attachment_warning_messages, compact_connection_messages,
    dumps, loads,
)
from freecad.SteelStructures.trusses.assemblies import configure_assembly
from freecad.SteelStructures.trusses.connections import (
    gusset_thickness_for_transition, intent_from_data,
)
from freecad.SteelStructures.trusses.gussets import preliminary_gusset_outlines
from freecad.SteelStructures.trusses.realization import build_candidate
from tests.test_connections_c5b_polish import three_web_config
from tests.test_gusset_attachment_c6d import (
    _participant, _profile_surfaces, _spec, _surface,
)
from tests.test_gusset_plate_c6a import configured


class SurfaceClassificationTests(unittest.TestCase):
    def test_channel_outer_and_inner_are_geometry_classified(self):
        surfaces = _profile_surfaces('U 4" x 8,04')
        outer = next(value for value in surfaces
                     if value.surface_class == GussetSurfaceClass.OUTER
                     and value.outward_sign > 0)
        inner = next(value for value in surfaces
                     if value.surface_class == GussetSurfaceClass.INNER)
        self.assertAlmostEqual(outer.signed_offset, 11.60)
        self.assertAlmostEqual(inner.signed_offset, 6.93)
        self.assertAlmostEqual(outer.signed_offset-inner.signed_offset, 4.67)
        self.assertEqual((outer.recess_depth, inner.recess_depth > 0.), (0., True))

    def test_angle_i_and_lipped_channel_classification_is_deterministic(self):
        for designation in ("L 40 x 4", "W 150 x 13,0", "HP 310 x 132,0",
                            "Ue 150 × 60 × 20 × 3,00"):
            with self.subTest(profile=designation):
                first = _profile_surfaces(designation)
                second = _profile_surfaces(designation)
                signature = lambda values: tuple(
                    (item.surface_id, item.surface_class, round(item.recess_depth, 6))
                    for item in values)
                self.assertEqual(signature(first), signature(second))
                self.assertTrue(any(item.surface_class == GussetSurfaceClass.OUTER
                                    for item in first))

    def test_rotation_reflection_and_insertion_keep_geometric_classes(self):
        cases = (
            dict(insertion="web_center"), dict(rotation=180.),
            dict(section_transform={"rotation_degrees": 0., "reflect_x": True}),
        )
        for parameters in cases:
            with self.subTest(parameters=parameters):
                surfaces = _profile_surfaces('U 4" x 8,04', **parameters)
                self.assertEqual({item.surface_class for item in surfaces},
                                 {GussetSurfaceClass.OUTER,
                                  GussetSurfaceClass.INNER})


class AttachmentModeTests(unittest.TestCase):
    def _outline(self, mode, side="Center", thickness=10.):
        value, node = three_web_config()
        candidate = build_candidate(configured(
            value, node, attachment_mode=mode, side=side,
            plate_thickness=thickness))
        outlines, diagnostics = preliminary_gusset_outlines(candidate)
        self.assertFalse(diagnostics, [item.message for item in diagnostics])
        return next(item for item in outlines if item.spec.node_key == node)

    def test_u_lateral_recess_is_not_accessible_from_web_region(self):
        outer = self._outline("Outer", "FaceA")
        inner = self._outline("Inner", "Center")
        self.assertEqual(outer.attachment.governing_surface_class,
                         GussetSurfaceClass.OUTER)
        self.assertEqual(inner.attachment.kind, "NominalFallback")
        self.assertAlmostEqual(outer.attachment.signed_offset, 11.60)
        self.assertEqual((outer.attachment.plate_low,
                          outer.attachment.plate_high), (11.6, 21.6))
        self.assertFalse(any(value.attachment_mode == GussetAttachmentMode.INNER
                             for value in inner.attachment.candidates))

    def test_side_filters_surface_family_and_unsupported_mode_is_explicit(self):
        side_b = self._outline("Outer", "FaceB")
        self.assertLess(side_b.attachment.signed_offset, 0.)
        near_opening = self._outline("Inner", "FaceA")
        near_wall = self._outline("Inner", "FaceB")
        self.assertEqual((near_opening.attachment.kind,
                          near_wall.attachment.kind),
                         ("NominalFallback", "NominalFallback"))

    def test_auto_preserves_c6d_and_simple_center_is_nominal_fallback(self):
        automatic = self._outline("Auto")
        centered = self._outline("Center")
        self.assertEqual(automatic.attachment.kind, "PhysicalSurface")
        self.assertAlmostEqual(automatic.attachment.signed_offset, 11.6)
        self.assertEqual(centered.attachment.kind, "NominalFallback")
        self.assertEqual(centered.attachment.signed_offset, 0.)

    def test_center_mode_uses_symmetric_assembly_axis_plane_for_all_pair_types(self):
        for assembly in ("DoubleAngle", "DoubleChannelInward", "SpacedPair"):
            with self.subTest(assembly=assembly):
                value, node = three_web_config()
                role = value["role_specs"]["DIAGONAL"]
                if assembly == "DoubleChannelInward":
                    role["profile_ref"] = asdict(
                        profile_catalog.ref_for_designation('U 4" x 8,04'))
                spacing = 120. if assembly == "SpacedPair" else 100.
                value["role_specs"]["DIAGONAL"] = configure_assembly(
                    role, assembly, spacing)
                candidate = build_candidate(configured(
                    value, node, attachment_mode="Center", side="FaceA"))
                outline = preliminary_gusset_outlines(candidate)[0][0]
                self.assertEqual(outline.attachment.kind, "AssemblyMidPlane")
                offset = outline.attachment.signed_offset
                self.assertEqual((outline.attachment.plate_low,
                                  outline.attachment.plate_high),
                                 (offset, offset+8.))

    def test_schema_two_migrates_to_auto_and_roundtrip_preserves_modes(self):
        legacy = dict(intent_key="I", node_key="N", form="Gusset",
                      schema_version=2, gusset=dict(plate_thickness=8.))
        migrated = loads(json.dumps(legacy))
        self.assertEqual(migrated.schema_version, 4)
        self.assertEqual(migrated.gusset.attachment_mode,
                         GussetAttachmentMode.AUTO)
        for mode in GussetAttachmentMode:
            restored = loads(dumps(replace(
                migrated, gusset=replace(migrated.gusset,
                                         attachment_mode=mode))))
            self.assertEqual(restored.gusset.attachment_mode, mode)
        with self.assertRaises(ValueError):
            intent_from_data("N", dict(
                form="Gusset", schema_version=3,
                gusset=dict(plate_thickness=8., attachment_mode="Unknown")))


class DefaultsAndMessagesTests(unittest.TestCase):
    def test_new_gusset_gets_ten_mm_but_prior_values_are_preserved(self):
        self.assertEqual(gusset_thickness_for_transition("N"), 10.)
        direct_with_prior = dict(form="Direct", schema_version=2,
                                 gusset=dict(plate_thickness=8.))
        self.assertEqual(gusset_thickness_for_transition(
            "N", direct_with_prior), 8.)
        existing = dict(form="Gusset", schema_version=3,
                        gusset=dict(plate_thickness=12., attachment_mode="Inner"))
        self.assertEqual(gusset_thickness_for_transition("N", existing), 12.)
        self.assertEqual(intent_from_data("N", direct_with_prior).gusset.plate_thickness,
                         8.)

    def test_ok_is_empty_and_all_warnings_are_actionable_and_deterministic(self):
        participant = (_participant("chord", "BOTTOM_CHORD"),)
        good = __import__(
            "freecad.SteelStructures.connections", fromlist=["resolve_gusset_attachment"]
            ).resolve_gusset_attachment(
                _spec(GussetSide.FACE_A), participant,
                (_surface("chord", 25., 1, "BOTTOM_CHORD"),))
        holder = type("Outline", (), {"attachment": good})()
        self.assertEqual(attachment_warning_messages((holder,)), ())
        compact = compact_connection_messages(("z", "a", "b", "c", "a"))
        self.assertEqual(compact, ("a", "b", "c", "z"))
        self.assertFalse(any("avisos adicionais" in value for value in compact))


if __name__ == "__main__":
    unittest.main()
