"""Focused C6-J physical ContactBand, flat-band and compact-outline tests."""

import copy
import math
import unittest
from dataclasses import asdict
from types import SimpleNamespace

from freecad.SteelStructures import profile_catalog
from freecad.SteelStructures.connections import (
    GussetSectionMaterial2D, derive_surface_band_slots,
    flat_contact_intervals, slot_placements,
)
from freecad.SteelStructures.trusses.assemblies import configure_assembly
from freecad.SteelStructures.trusses.editing import materialize
from freecad.SteelStructures.trusses.gussets import preliminary_gusset_outlines
from freecad.SteelStructures.trusses.models import TopologyGraph
from freecad.SteelStructures.trusses.realization import build_candidate
from tests.test_connections_c5b_polish import three_web_config
from tests.test_gusset_c6f import _outline
from tests.test_gusset_plate_c6a import configured
from tests.test_ridge_fitting import ridge_config
from tests.test_truss_manual_fixes import definition


NORMAL = (0., 0., 1.)
AXIS = (0., 1., 0.)


def _material(points):
    return GussetSectionMaterial2D("chord", "A", tuple(points), (), AXIS)


def _production(designation, rotation=0., mode="Detailed", assembly=None,
                placement=""):
    value, node = three_web_config()
    reference = asdict(profile_catalog.ref_for_designation(designation))
    for role in ("TOP_CHORD", "BOTTOM_CHORD"):
        value["role_specs"][role].update(
            profile_ref=copy.deepcopy(reference), rotation=rotation,
            section_geometry_mode=mode)
    if assembly:
        value["role_specs"]["BOTTOM_CHORD"] = configure_assembly(
            value["role_specs"]["BOTTOM_CHORD"], assembly, 80.)
    outlines, diagnostics = preliminary_gusset_outlines(build_candidate(
        configured(value, node, chord_contact="TrussInterior",
                   transverse_placement=placement)))
    if diagnostics:
        raise AssertionError([item.message for item in diagnostics])
    return next(item for item in outlines if item.spec.node_key == node)


def _chord_candidates(outline, accessibility):
    key = outline.attachment.governing_participant_key
    return [candidate for candidate in outline.attachment.candidates
            if candidate.governing_participant_key == key
            and candidate.accessibility.value == accessibility]


class FlatSurfaceBandTests(unittest.TestCase):
    def test_rounded_face_excludes_corner_radii_from_lateral_placements(self):
        rounded = _material(((-7., 10.), (7., 10.), (10., 7.),
                             (10., -7.), (7., -10.), (-7., -10.),
                             (-10., -7.), (-10., 7.)))
        sharp = _material(((-10., 10.), (10., 10.), (10., -10.),
                           (-10., -10.)))
        self.assertEqual(flat_contact_intervals((rounded,), 1), ((-7., 7.),))
        self.assertEqual(flat_contact_intervals((sharp,), 1), ((-10., 10.),))
        rounded_slot, = derive_surface_band_slots(
            "chord", NORMAL, (rounded,), 1)
        placements = slot_placements(rounded_slot, 8., (rounded,))
        self.assertEqual([(value[1], value[2]) for value in placements],
                         [(-7., 1.), (-4., 4.), (-1., 7.)])

    def test_detailed_tube_moves_lateral_slab_inside_flat_tangencies(self):
        detailed = _production("SHS 40x40x1,2", mode="Detailed")
        simplified = _production("SHS 40x40x1,2", mode="Simplified")
        detailed_values = {value.placement.value: value
                           for value in _chord_candidates(detailed, "SurfaceBand")}
        simplified_values = {value.placement.value: value
                             for value in _chord_candidates(simplified, "SurfaceBand")}
        self.assertGreater(detailed_values["NearA"].plate_low,
                           simplified_values["NearA"].plate_low)
        self.assertLess(detailed_values["NearB"].plate_high,
                        simplified_values["NearB"].plate_high)
        self.assertEqual((detailed_values["Center"].plate_low,
                          detailed_values["Center"].plate_high), (-4., 4.))


class PlacementContactBandTests(unittest.TestCase):
    def assert_accessible_window(self, candidate):
        self.assertIn(candidate.contact_direction, (-1, 1))
        self.assertTrue(any((candidate.contact_direction < 0 and low is None)
                            or (candidate.contact_direction > 0 and high is None)
                            for low, high in candidate.contact_window.intervals))

    def test_u_and_ue_internal_external_placements_have_physical_windows(self):
        for designation in ('U 4" x 8,04', "Ue 150 × 60 × 20 × 3,00"):
            with self.subTest(designation=designation):
                base = _production(designation)
                candidates = (_chord_candidates(base, "OpenRecess")
                              +_chord_candidates(base, "OuterExposed"))
                self.assertTrue(candidates)
                for candidate in candidates:
                    self.assert_accessible_window(candidate)
                    outline = _production(designation,
                                          placement=candidate.stable_key)
                    self.assertNotEqual(outline.attachment.kind,
                                        "NominalFallback")
                    self.assertIn("CHORD_BOUNDARY",
                                  {edge.kind for edge in outline.semantic_edges})

    def test_ue_external_sides_reach_the_same_accessible_section_extreme(self):
        base = _production("Ue 150 × 60 × 20 × 3,00")
        external = _chord_candidates(base, "OuterExposed")
        self.assertEqual(len(external), 2)
        outlines = [_production("Ue 150 × 60 × 20 × 3,00",
                                placement=value.stable_key)
                    for value in external]
        self.assertAlmostEqual(external[0].contact_band,
                               external[1].contact_band, places=6)
        self.assertAlmostEqual(outlines[0].area, outlines[1].area, places=3)

    def test_double_angle_gap_positions_keep_distinct_effective_extents(self):
        base = _production("L 40 x 4", assembly="DoubleAngle")
        gaps = _chord_candidates(base, "AssemblyGap")
        self.assertEqual({value.placement.value for value in gaps},
                         {"NearA", "Center", "NearB"})
        outlines = {value.placement.value: _production(
            "L 40 x 4", assembly="DoubleAngle", placement=value.stable_key)
            for value in gaps}
        self.assertAlmostEqual(outlines["NearA"].area,
                               outlines["NearB"].area, places=5)
        self.assertNotAlmostEqual(outlines["Center"].area,
                                  outlines["NearA"].area, places=3)
        self.assertTrue(all(value.attachment.kind != "NominalFallback"
                            for value in outlines.values()))


class PlacementPresentationTests(unittest.TestCase):
    @staticmethod
    def candidate(key, accessibility, placement, low, high, band, intervals):
        return SimpleNamespace(
            stable_key=key,
            accessibility=SimpleNamespace(value=accessibility),
            placement=SimpleNamespace(value=placement),
            governing_participant_key="chord", plate_low=low, plate_high=high,
            contact_direction=1, contact_band=band, outline_band=band,
            slot_id=key, diagnostics=(),
            contact_window=SimpleNamespace(intervals=intervals))

    @staticmethod
    def regions():
        center = definition("interactive/truss_controller.py",
                            "_candidate_center", {})
        deduplicate = definition("interactive/truss_controller.py",
                                 "_deduplicated_transverse_candidates", {})
        return definition("interactive/truss_controller.py",
                          "_transverse_placement_regions", dict(
                              _candidate_center=center,
                              _deduplicated_transverse_candidates=deduplicate))

    def test_equivalent_slab_contact_and_window_use_intuitive_single_label(self):
        options = self.regions()
        values = (
            self.candidate("surface", "SurfaceBand", "Center", -4., 4.,
                           None, ((None, None),)),
            self.candidate("gap", "AssemblyGap", "Center", -4., 4.,
                           None, ((None, None),)),
        )
        self.assertEqual(options(values),
                         (("between", "Entre componentes",
                           (("gap", "Central"),)),))

    def test_same_offset_with_different_region_or_contact_is_not_deduplicated(self):
        options = self.regions()
        values = (
            self.candidate("first", "OpenRecess", "Center", -4., 4., 10.,
                           ((None, 10.),)),
            self.candidate("second", "SurfaceBand", "Center", -4., 4., 12.,
                           ((None, 12.),)),
        )
        result = options(values)
        visible = tuple((key, label) for _region, _name, positions in result
                        for key, label in positions)
        self.assertEqual(len(visible), 2)
        self.assertEqual({key for key, _label in visible}, {"first", "second"})
        self.assertFalse(any("faixa" in label.lower() or "região" in label.lower()
                             for _key, label in visible))


class CompactDuoPitchTests(unittest.TestCase):
    def test_diagonal_vertical_caps_bound_remote_expansion_directly(self):
        # Automatic now uses the same approved external frontier as manual.
        for node, area in (("T_S_LEFT_1_3", 39829.703810723564),
                           ("T_S_RIGHT_1_5", 30413.738125295262)):
            with self.subTest(node=node):
                outline = _outline(ridge_config(.37, 1100.), node)
                caps = [edge for edge in outline.semantic_edges
                        if edge.kind == "WEB_END_CAP"]
                self.assertEqual(len(caps), 2)
                self.assertEqual(sum(edge.kind == "WEB_SECTOR_BRIDGE"
                                     for edge in outline.semantic_edges), 0)
                self.assertAlmostEqual(outline.area, area, places=6)
                self.assertLess(max(math.dist(edge.start, edge.end)
                                    for edge in caps), 130.)
                self.assertGreaterEqual(sum(edge.kind == "FREE_MARGIN"
                                            for edge in outline.semantic_edges), 2)

    def test_isolated_vertical_keeps_inclined_chord_and_full_cap(self):
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
        outline = next(item for item in preliminary_gusset_outlines(
            build_candidate(configured(value, node)))[0]
            if item.spec.node_key == node)
        chord = next(edge for edge in outline.semantic_edges
                     if edge.kind == "CHORD_BOUNDARY")
        cap = next(edge for edge in outline.semantic_edges
                   if edge.kind == "WEB_END_CAP")
        self.assertGreater(abs(chord.end[1]-chord.start[1]), 1.)
        self.assertGreater(math.dist(cap.start, cap.end), 40.+2.*25.)
        self.assertEqual(len(outline.points), 4)


if __name__ == "__main__":
    unittest.main()
