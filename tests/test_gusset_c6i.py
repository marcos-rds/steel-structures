"""Focused C6-I geometry/UI-contract regressions, without FreeCAD/OCC."""

import copy
import unittest
from dataclasses import asdict

from freecad.SteelStructures import profile_catalog
from freecad.SteelStructures.connections import (
    GussetAttachmentSlotKind, GussetSectionMaterial2D,
    derive_surface_band_slot, slot_placements,
)
from freecad.SteelStructures.connections.slots import contact_band_support
from freecad.SteelStructures.trusses.editing import materialize
from freecad.SteelStructures.trusses.assemblies import configure_assembly
from freecad.SteelStructures.trusses.gussets import preliminary_gusset_outlines
from freecad.SteelStructures.trusses.models import TopologyGraph
from freecad.SteelStructures.trusses.realization import build_candidate
from tests.test_connections_c5b_polish import three_web_config
from tests.test_gusset_plate_c6a import configured
from tests.test_ridge_fitting import ridge_config


NORMAL = (0., 0., 1.)
AXIS = (0., 1., 0.)


def material(key, outer, holes=()):
    return GussetSectionMaterial2D(
        "chord", key, tuple(outer), tuple(tuple(path) for path in holes), AXIS)


class SurfaceBandTests(unittest.TestCase):
    def test_closed_section_offers_three_face_positions_not_its_void(self):
        tube = material("tube", ((-20., -20.), (20., -20.),
                                 (20., 20.), (-20., 20.)),
                        (((-18., -18.), (18., -18.),
                          (18., 18.), (-18., 18.)),))
        slot = derive_surface_band_slot("chord", NORMAL, (tube,), -1)
        self.assertEqual(slot.kind, GussetAttachmentSlotKind.SURFACE_BAND)
        values = slot_placements(slot, 8., (tube,))
        self.assertEqual([value[0].value for value in values],
                         ["NearA", "Center", "NearB"])
        self.assertTrue(all(any(low is None for low, _high in value[3].intervals)
                            for value in values))
        self.assertTrue(all(contact_band_support((tube,), low, high, -1,
                                                 include_tangent=False) is not None
                            for _placement, low, high, _window in values))

    def test_tangent_lip_does_not_truncate_governing_inner_surface(self):
        web = material("web", ((0., 8.), (8., 8.), (8., 12.), (0., 12.)))
        lip = material("lip", ((8., 8.), (10., 8.), (10., 25.), (8., 25.)))
        self.assertEqual(contact_band_support((web, lip), 0., 8., 1), 25.)
        self.assertAlmostEqual(contact_band_support(
            (web, lip), 0., 8., 1, include_tangent=False), 12.)


class ProductionPlacementTests(unittest.TestCase):
    def outline(self, designation, rotation=0., placement=""):
        value, node = three_web_config()
        reference = asdict(profile_catalog.ref_for_designation(designation))
        for role in ("TOP_CHORD", "BOTTOM_CHORD"):
            value["role_specs"][role]["profile_ref"] = copy.deepcopy(reference)
            value["role_specs"][role]["rotation"] = rotation
        result = configured(value, node, chord_contact="TrussInterior",
                            transverse_placement=placement)
        outlines, diagnostics = preliminary_gusset_outlines(build_candidate(result))
        self.assertFalse([item for item in diagnostics
                          if item.code == "GUSSET_PLATE_INVALID"])
        return next(item for item in outlines if item.spec.node_key == node)

    def test_shs_rhs_surface_band_has_lateral_and_centered_positions(self):
        for designation in ("SHS 40x40x1,2", "RHS 60x40x1,2"):
            with self.subTest(designation=designation):
                outline = self.outline(designation)
                surface = [value for value in outline.attachment.candidates
                           if value.accessibility.value == "SurfaceBand"
                           and value.governing_participant_key
                           == outline.attachment.governing_participant_key]
                self.assertEqual({value.placement.value for value in surface},
                                 {"NearA", "Center", "NearB"})
                self.assertEqual(outline.attachment.kind, "SurfaceBand")

    def test_w_surface_positions_stop_before_crossing_the_web(self):
        automatic = self.outline("W 150 x 13,0")
        surface = [value for value in automatic.attachment.candidates
                   if value.accessibility.value == "SurfaceBand"
                   and value.governing_participant_key
                   == automatic.attachment.governing_participant_key]
        self.assertEqual({value.placement.value for value in surface},
                         {"NearA", "Center", "NearB"})
        for candidate in surface:
            outline = self.outline("W 150 x 13,0", placement=candidate.stable_key)
            self.assertEqual(outline.attachment.kind, "SurfaceBand")
            self.assertIn("CHORD_BOUNDARY",
                          {edge.kind for edge in outline.semantic_edges})

    def test_rotated_ue_exposes_surface_band_when_recess_is_not_accessible(self):
        counts = []
        for rotation in (0., 90., 180., 270.):
            outline = self.outline("Ue 150 × 60 × 20 × 3,00", rotation)
            counts.append(sum(value.accessibility.value == "OpenRecess"
                              for value in outline.attachment.candidates))
            self.assertGreaterEqual(sum(
                value.accessibility.value == "SurfaceBand"
                for value in outline.attachment.candidates), 3)
        self.assertIn(0, counts)
        self.assertGreater(max(counts), 0)

    def test_invalid_recess_after_rotation_resolves_automatically(self):
        accessible = self.outline("Ue 150 × 60 × 20 × 3,00", 90.)
        old = next(value.stable_key for value in accessible.attachment.candidates
                   if value.accessibility.value == "OpenRecess")
        rotated = self.outline("Ue 150 × 60 × 20 × 3,00", 0., old)
        self.assertNotEqual(rotated.attachment.kind, "NominalFallback")
        self.assertTrue(any("posição anterior ficou indisponível" in message
                            for message in rotated.attachment.diagnostics))
        self.assertNotEqual(rotated.attachment.governing_slot_id,
                            old.rsplit(":", 1)[0])

    def test_double_angle_gap_positions_keep_physical_chord_boundary(self):
        value, node = three_web_config()
        role = copy.deepcopy(value["role_specs"]["BOTTOM_CHORD"])
        role["profile_ref"] = asdict(profile_catalog.ref_for_designation("L 40 x 4"))
        value["role_specs"]["BOTTOM_CHORD"] = configure_assembly(
            role, "DoubleAngle", 80.)
        automatic, diagnostics = preliminary_gusset_outlines(
            build_candidate(configured(copy.deepcopy(value), node)))
        self.assertFalse(diagnostics)
        automatic = next(item for item in automatic
                         if item.spec.node_key == node)
        placements = [candidate for candidate in automatic.attachment.candidates
                      if candidate.accessibility.value == "AssemblyGap"
                      and candidate.governing_participant_key
                      == automatic.attachment.governing_participant_key]
        self.assertEqual({candidate.placement.value for candidate in placements},
                         {"NearA", "Center", "NearB"})
        for candidate in placements:
            with self.subTest(placement=candidate.placement.value):
                outlines, diagnostics = preliminary_gusset_outlines(build_candidate(
                    configured(copy.deepcopy(value), node,
                               transverse_placement=candidate.stable_key)))
                self.assertFalse(diagnostics)
                outline = next(item for item in outlines
                               if item.spec.node_key == node)
                self.assertNotEqual(outline.attachment.kind, "NominalFallback")
                chord_edges = [edge for edge in outline.semantic_edges
                               if edge.kind == "CHORD_BOUNDARY"]
                self.assertTrue(chord_edges)
                self.assertTrue(all(abs(edge.end[0]-edge.start[0]) > 100.
                                    for edge in chord_edges))


class DuoPitchOutlineTests(unittest.TestCase):
    def test_isolated_vertical_has_complete_cap_and_two_side_edges(self):
        value = ridge_config(.37, 1100., diagonals=False)
        base = build_candidate(value)
        node = "T_S_LEFT_1_3"
        graph = TopologyGraph(base.graph.nodes, tuple(
            edge for edge in base.graph.edges
            if not (edge.role == "DIAGONAL"
                    and node in (edge.start_node_key, edge.end_node_key))))
        value.update(topology_mode="Custom", topology_preset="Custom",
                     base_preset="Pratt",
                     custom_topology=materialize(graph, base.config))
        outlines, diagnostics = preliminary_gusset_outlines(
            build_candidate(configured(value, node)))
        self.assertFalse(diagnostics)
        outline = next(item for item in outlines if item.spec.node_key == node)
        kinds = [edge.kind for edge in outline.semantic_edges]
        self.assertEqual(kinds.count("CHORD_BOUNDARY"), 1)
        self.assertEqual(kinds.count("WEB_END_CAP"), 1)
        self.assertEqual(kinds.count("FREE_MARGIN"), 2)
        cap = next(edge for edge in outline.semantic_edges
                   if edge.kind == "WEB_END_CAP")
        self.assertGreater(((cap.end[0]-cap.start[0])**2
                            +(cap.end[1]-cap.start[1])**2)**.5, 40.)
        self.assertEqual(len(outline.points), 4)


if __name__ == "__main__":
    unittest.main()
