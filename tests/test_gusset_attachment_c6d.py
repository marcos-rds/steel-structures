"""Pure C6-D connection-surface, attachment-plane and residual tests."""

import copy
import math
import unittest
from dataclasses import FrozenInstanceError, asdict, replace
from types import SimpleNamespace

from freecad.SteelStructures import profile_catalog
from freecad.SteelStructures.connections import (
    GussetConnectionSurface, GussetPlateFrame, GussetPlateSpec,
    GussetResidualStatus, GussetSide, resolve_gusset_attachment,
)
from freecad.SteelStructures.trusses.gusset_attachment import (
    component_connection_surfaces, connection_surfaces,
)
from freecad.SteelStructures.trusses.assemblies import configure_assembly
from freecad.SteelStructures.trusses.gussets import preliminary_gusset_outlines
from freecad.SteelStructures.trusses.realization import build_candidate, reference_frame
from tests.test_connections_c5b_polish import three_web_config
from tests.test_gusset_plate_c6a import configured
from tests.test_truss_assemblies import config


FRAME = GussetPlateFrame((0., 0., 0.), (1., 0., 0.),
                         (0., 1., 0.), (0., 0., 1.))


def _spec(side=GussetSide.CENTER, thickness=8.):
    return GussetPlateSpec(
        "N:gusset-plate", "N", thickness, side=side,
        participant_keys=("chord", "web"), component_keys=("A",), frame=FRAME)


def _participant(key, role="DIAGONAL", end="End", assembly="Single"):
    return SimpleNamespace(participant_key=key, role=role, end=end,
                           assembly=assembly)


def _surface(key, offset, sign, role="DIAGONAL", extent=40., component="A",
             surface_id=None, end="End"):
    surface_id = surface_id or "%s:%+.3f:%+d" % (key, offset, sign)
    return GussetConnectionSurface(
        key, key+":run", component, surface_id, role, end,
        (0., 0., float(sign)), float(offset), ((0., 0.), (0., extent)),
        GussetSide.FACE_A if sign > 0 else GussetSide.FACE_B,
        sign, 0., extent,
        "Chord" if role in ("TOP_CHORD", "BOTTOM_CHORD") else "Web",
        component_band_low=float(offset), component_band_high=float(offset))


def _profile_surfaces(designation, insertion="centroid", rotation=0.,
                      section_transform=None):
    value = config()
    role = copy.deepcopy(value["role_specs"]["BOTTOM_CHORD"])
    role.update(profile_ref=asdict(profile_catalog.ref_for_designation(designation)),
                insertion=insertion, rotation=rotation,
                section_geometry_mode="Simplified")
    value["role_specs"]["BOTTOM_CHORD"] = role
    candidate = build_candidate(value)
    item = next(item for item in candidate.items
                if item.role == "BOTTOM_CHORD" and item.element_kind == "Component")
    if section_transform is not None:
        item = replace(item, section_transform=section_transform)
    participant = _participant("chord", "BOTTOM_CHORD", "Through")
    return component_connection_surfaces(
        item, participant, item.start_global, reference_frame(candidate.config)[3])


class ConnectionSurfaceTests(unittest.TestCase):
    def assert_offsets(self, designation, expected, places=5, **kwargs):
        values = {round(surface.signed_offset, places)
                  for surface in _profile_surfaces(designation, **kwargs)}
        for expected_value in expected:
            self.assertIn(round(expected_value, places), values)

    def test_numeric_offsets_for_channel_i_angle_and_lipped_channel(self):
        cases = (
            ('U 4" x 8,04', (11.60, 6.93, -28.63)),
            ("W 150 x 13,0", (-2.15, 2.15, -50., 50.)),
            ("HP 310 x 132,0", (-9.15, 9.15, -156.5, 156.5)),
            ("L 40 x 4", (11.5, 7.5, -28.5)),
            ("Ue 150 × 60 × 20 × 3,00", (19.1998719, 16.1998719,
                                           -37.8001281, -40.8001281)),
        )
        for designation, expected in cases:
            with self.subTest(profile=designation):
                self.assert_offsets(designation, expected)

    def test_insertion_rotation_and_reflection_offsets(self):
        self.assert_offsets('U 4" x 8,04', (2.335, -2.335), insertion="web_center")
        self.assert_offsets('U 4" x 8,04', (0., -4.67), insertion="web_back")
        self.assert_offsets("L 40 x 4", (20., 16., -20.), insertion="envelope_center")
        base = sorted(round(value.signed_offset, 6)
                      for value in _profile_surfaces("L 40 x 4"))
        reflected = sorted(round(value.signed_offset, 6) for value in
                           _profile_surfaces("L 40 x 4", section_transform={
                               "rotation_degrees": 0., "reflect_x": True}))
        rotated = sorted(round(value.signed_offset, 6)
                         for value in _profile_surfaces("L 40 x 4", rotation=180.))
        self.assertEqual(reflected, sorted(-value for value in base))
        self.assertEqual(rotated, sorted(-value for value in base))

    def test_surface_ids_are_stable_and_long_web_beats_short_tips(self):
        first = _profile_surfaces('U 4" x 8,04')
        second = _profile_surfaces('U 4" x 8,04')
        self.assertEqual(tuple((value.surface_id, value.signed_offset) for value in first),
                         tuple((value.surface_id, value.signed_offset) for value in second))
        longest = max(first, key=lambda value: value.contact_extent)
        self.assertAlmostEqual(longest.signed_offset, 11.6)
        self.assertEqual(longest.outward_sign, 1)

    def test_angular_tolerance_does_not_accept_large_endpoint_offset_variation(self):
        value = config()
        candidate = build_candidate(value)
        item = next(item for item in candidate.items if item.role == "BOTTOM_CHORD")
        angle = math.radians(1.)
        item = replace(item, section_u_global=(0., math.cos(angle), math.sin(angle)))
        normal = reference_frame(candidate.config)[3]
        surfaces = component_connection_surfaces(
            item, _participant("chord", "BOTTOM_CHORD", "Through"),
            item.start_global, normal)
        self.assertTrue(surfaces)
        self.assertTrue(all(value.contact_extent < 6. for value in surfaces))
        self.assertTrue(all(abs(sum(a*b for a, b in
                                    zip(value.plane_normal, normal))) < 1.
                            for value in surfaces))

    def test_inclined_plane_preserves_signed_offsets(self):
        value = config()
        value.update(span=3000., start=[100., 200., 300.], end=[2500., 200., 2100.])
        candidate = build_candidate(value)
        frame = reference_frame(candidate.config)
        node = candidate.graph.nodes[0]
        participants = tuple(SimpleNamespace(
            participant_key=p.participant_key, node_key=p.node_key,
            role=p.role, end=p.end,
            assembly=p.assembly, physical_run_keys=p.physical_run_keys)
            for p in __import__(
                "freecad.SteelStructures.trusses.connections", fromlist=["connection_participants"]
                ).connection_participants(candidate, node.key))
        values = connection_surfaces(candidate, participants, frame)
        self.assertTrue(values)
        for surface in values:
            self.assertAlmostEqual(math.sqrt(sum(v*v for v in surface.plane_normal)), 1.)
            self.assertAlmostEqual(abs(sum(a*b for a, b in
                                            zip(surface.plane_normal, frame[3]))), 1.)


class AttachmentPlaneTests(unittest.TestCase):
    def test_attachment_contracts_are_immutable_and_reject_impossible_states(self):
        surface = _surface("web", 0., 1)
        with self.assertRaises(FrozenInstanceError):
            surface.signed_offset = 2.
        with self.assertRaisesRegex(ValueError, "unitária"):
            replace(surface, plane_normal=(0., 0., 2.))
        participants = (_participant("web"),)
        plane = resolve_gusset_attachment(_spec(), participants, (surface,))
        with self.assertRaises(FrozenInstanceError):
            plane.plate_low = -10.
        with self.assertRaisesRegex(ValueError, "Intervalo"):
            replace(plane, plate_low=plane.plate_high)

    def test_chord_then_through_semantic_priority_and_order_independence(self):
        participants = (_participant("web"),
                        _participant("through", "VERTICAL", "Through"),
                        _participant("chord", "BOTTOM_CHORD"))
        surfaces = (_surface("web", 5., 1),
                    _surface("through", 18., 1, "VERTICAL", end="Through"),
                    _surface("chord", 25., 1, "BOTTOM_CHORD"))
        first = resolve_gusset_attachment(_spec(GussetSide.FACE_A), participants, surfaces)
        second = resolve_gusset_attachment(_spec(GussetSide.FACE_A), tuple(reversed(participants)),
                                           tuple(reversed(surfaces)))
        self.assertEqual(first, second)
        self.assertEqual(first.governing_participant_key, "chord")
        without_chord = resolve_gusset_attachment(
            _spec(GussetSide.FACE_A), participants[:2], surfaces[:2])
        self.assertEqual(without_chord.governing_participant_key, "through")

    def test_side_a_and_b_align_one_wide_face(self):
        participants = (_participant("chord", "BOTTOM_CHORD"),)
        surfaces = (_surface("chord", 25., 1, "BOTTOM_CHORD"),
                    _surface("chord", -21., -1, "BOTTOM_CHORD"))
        side_a = resolve_gusset_attachment(_spec(GussetSide.FACE_A),
                                           participants, surfaces)
        side_b = resolve_gusset_attachment(_spec(GussetSide.FACE_B),
                                           participants, surfaces)
        self.assertEqual((side_a.plate_low, side_a.plate_high), (25., 33.))
        self.assertEqual((side_b.plate_low, side_b.plate_high), (-29., -21.))

    def test_centered_symmetric_assembly_uses_physical_mid_plane(self):
        participants = (_participant("pair", "DIAGONAL", assembly="DoubleAngle"),)
        surfaces = (_surface("pair", -18.5, 1, component="A"),
                    _surface("pair", 18.5, -1, component="B"))
        plane = resolve_gusset_attachment(_spec(), participants, surfaces)
        self.assertEqual(plane.kind, "AssemblyMidPlane")
        self.assertEqual((plane.signed_offset, plane.plate_low, plane.plate_high),
                         (0., -4., 4.))

    def test_explicit_nominal_fallback(self):
        participants = (_participant("web"),)
        plane = resolve_gusset_attachment(_spec(GussetSide.FACE_A), participants, ())
        self.assertEqual(plane.kind, "NominalFallback")
        self.assertEqual(plane.status, "Warning")
        self.assertTrue(plane.diagnostics)
        self.assertEqual(plane.residuals[0].status,
                         GussetResidualStatus.NO_COMPATIBLE_SURFACE)

    def test_contact_gap_interference_and_no_surface_are_numeric(self):
        participants = (_participant("contact", "BOTTOM_CHORD"),
                        _participant("gap"), _participant("interference"),
                        _participant("none"))
        surfaces = (_surface("contact", 25., 1, "BOTTOM_CHORD", extent=60.),
                    _surface("gap", 18., 1, extent=60.),
                    _surface("interference", 32., 1, extent=60.))
        plane = resolve_gusset_attachment(
            _spec(GussetSide.FACE_A), participants, surfaces)
        by_key = {value.participant_key: value for value in plane.residuals}
        self.assertEqual(by_key["contact"].status, GussetResidualStatus.CONTACT)
        self.assertEqual((by_key["gap"].status, by_key["gap"].residual),
                         (GussetResidualStatus.GAP, 7.))
        self.assertEqual((by_key["interference"].status,
                          by_key["interference"].residual),
                         (GussetResidualStatus.INTERFERENCE, -7.))
        self.assertEqual(by_key["none"].status,
                         GussetResidualStatus.NO_COMPATIBLE_SURFACE)
        self.assertEqual(plane.status, "Warning")

    def test_exact_contact_beats_a_longer_but_distant_surface_for_residual(self):
        participants = (_participant("chord", "BOTTOM_CHORD"), _participant("web"))
        surfaces = (_surface("chord", 25., 1, "BOTTOM_CHORD", extent=60.),
                    _surface("web", 25., 1, extent=10., surface_id="contact"),
                    _surface("web", 10., 1, extent=100., surface_id="long-gap"))
        plane = resolve_gusset_attachment(
            _spec(GussetSide.FACE_A), participants, surfaces)
        web = next(value for value in plane.residuals if value.participant_key == "web")
        self.assertEqual((web.status, web.residual, web.surface_id),
                         (GussetResidualStatus.CONTACT, 0., "contact"))


class TrussAttachmentIntegrationTests(unittest.TestCase):
    def _outline(self, value, node, **parameters):
        candidate = build_candidate(configured(value, node, **parameters))
        outlines, diagnostics = preliminary_gusset_outlines(candidate)
        self.assertFalse(diagnostics, [value.message for value in diagnostics])
        return next(value for value in outlines if value.spec.node_key == node)

    def test_channel_chord_governs_physical_web_surface(self):
        value, node = three_web_config()
        outline = self._outline(value, node)
        self.assertEqual(outline.attachment.kind, "PhysicalSurface")
        self.assertAlmostEqual(outline.attachment.signed_offset, 11.6)
        self.assertEqual((outline.attachment.plate_low,
                          outline.attachment.plate_high), (11.6, 19.6))
        self.assertEqual(outline.attachment.governing_participant_key,
                         next(key for key in outline.spec.participant_keys
                              if ":through:BC:" in key))

    def test_side_a_b_change_physical_attachment_not_outline(self):
        value, node = three_web_config()
        side_a = self._outline(value, node, side="FaceA")
        value, node = three_web_config()
        side_b = self._outline(value, node, side="FaceB")
        self.assertEqual(side_a.points, side_b.points)
        self.assertEqual((side_a.attachment.plate_low,
                          side_a.attachment.plate_high), (11.6, 19.6))
        self.assertAlmostEqual(side_b.attachment.plate_high, -28.63)
        self.assertAlmostEqual(side_b.attachment.plate_low, -36.63)

    def test_assemblies_use_one_plate_and_clear_symmetric_gap_uses_mid_plane(self):
        for mode in ("DoubleAngle", "DoubleChannelInward", "SpacedPair"):
            with self.subTest(mode=mode):
                value, node = three_web_config()
                role = value["role_specs"]["DIAGONAL"]
                if mode == "DoubleChannelInward":
                    role["profile_ref"] = copy.deepcopy(
                        value["role_specs"]["BOTTOM_CHORD"]["profile_ref"])
                value["role_specs"]["DIAGONAL"] = configure_assembly(role, mode, 100.)
                outline = self._outline(value, node)
                self.assertEqual(outline.attachment.kind, "AssemblyMidPlane")
                offset = outline.attachment.signed_offset
                self.assertEqual((outline.attachment.plate_low,
                                  outline.attachment.plate_high),
                                 (offset-4., offset+4.))

    def test_residual_warning_keeps_outline_and_is_not_fatal(self):
        value, node = three_web_config()
        value["role_specs"]["DIAGONAL"]["rotation"] = 180.
        outline = self._outline(value, node)
        self.assertEqual(outline.attachment.status, "Warning")
        self.assertTrue(any(value.status in (
            GussetResidualStatus.GAP, GussetResidualStatus.INTERFERENCE)
                            for value in outline.attachment.residuals))

    def test_assembly_component_offsets_are_applied_exactly_once(self):
        cases = (
            ("DoubleAngle", 60., "L 40 x 4", (18.5, 22.5)),
            ("DoubleChannelOutward", 100., 'U 4" x 8,04', (38.4, 43.07)),
            ("SpacedPair", 100., "W 150 x 13,0", (47.85, 52.15)),
        )
        for mode, spacing, designation, expected_absolute in cases:
            with self.subTest(mode=mode):
                value, node = three_web_config()
                role = value["role_specs"]["DIAGONAL"]
                role["profile_ref"] = asdict(
                    profile_catalog.ref_for_designation(designation))
                value["role_specs"]["DIAGONAL"] = configure_assembly(
                    role, mode, spacing)
                candidate = build_candidate(configured(value, node))
                frame = reference_frame(candidate.config)
                from freecad.SteelStructures.trusses.connections import resolve_truss_connections
                resolution = next(item for item in resolve_truss_connections(
                    candidate, frame[3])[0] if item.intent.node_key == node)
                surfaces = connection_surfaces(candidate, resolution.participants, frame)
                absolute = {round(abs(item.signed_offset), 2) for item in surfaces
                            if item.role == "DIAGONAL" and item.contact_extent > 30.}
                for expected in expected_absolute:
                    self.assertIn(round(expected, 2), absolute)


if __name__ == "__main__":
    unittest.main()
