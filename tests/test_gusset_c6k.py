"""Focused C6-K external-height and physical-option regressions."""

import math
import unittest

from freecad.SteelStructures import profile_catalog
from tests.test_gusset_c6j import _chord_candidates, _production
from tests.test_truss_manual_fixes import definition


def _level(outline):
    edge = next(value for value in outline.semantic_edges
                if value.kind == "CHORD_BOUNDARY")
    # The focused production fixture uses horizontal chords.
    if abs(edge.end[1]-edge.start[1]) > 1e-6:
        raise AssertionError("Limite do banzo não é horizontal no fixture C6-K.")
    return (edge.start[1]+edge.end[1])/2.


class ExternalContactHeightTests(unittest.TestCase):
    def assert_window_has_no_positive_penetration(self, candidate):
        self.assertTrue(any((candidate.contact_direction < 0 and low is None)
                            or (candidate.contact_direction > 0 and high is None)
                            for low, high in candidate.contact_window.intervals))

    def test_laminated_u_internal_and_external_reach_physical_top(self):
        designation = next(value for value in profile_catalog.designations()
                           if value.startswith('U 4"'))
        base = _production(designation)
        internal = _chord_candidates(base, "SurfaceBand")
        external = _chord_candidates(base, "OuterExposed")
        self.assertEqual(len(external), 2)
        self.assertTrue(internal)
        self.assertTrue(all(math.isclose(value.contact_band, 50.8, abs_tol=.02)
                            for value in internal+external))
        self.assertTrue(all(math.isclose(value.outline_band, -50.8, abs_tol=.02)
                            for value in external))
        internal_level = _level(_production(
            designation, placement=internal[0].stable_key))
        external_levels = [_level(_production(
            designation, placement=value.stable_key)) for value in external]
        self.assertLess(max(external_levels)-min(external_levels), .02)
        self.assertAlmostEqual(internal_level-min(external_levels), 101.6,
                               delta=.02)
        for value in external:
            self.assert_window_has_no_positive_penetration(value)

    def test_ue_external_no_longer_stops_at_lip_extremity(self):
        designation = "Ue 150 × 60 × 20 × 3,00"
        base = _production(designation)
        internal = _chord_candidates(base, "SurfaceBand")
        external = _chord_candidates(base, "OuterExposed")
        self.assertEqual(len(external), 2)
        # Before C6-K one side returned no band and the other stopped at 69 mm.
        self.assertTrue(all(math.isclose(value.contact_band, 75., abs_tol=.02)
                            for value in internal+external))
        self.assertTrue(all(math.isclose(value.outline_band, -75., abs_tol=.02)
                            for value in external))
        internal_level = _level(_production(
            designation, placement=internal[0].stable_key))
        external_levels = [_level(_production(
            designation, placement=value.stable_key)) for value in external]
        self.assertLess(max(external_levels)-min(external_levels), .02)
        self.assertAlmostEqual(internal_level-min(external_levels), 150.,
                               delta=.02)
        for value in external:
            self.assert_window_has_no_positive_penetration(value)

    def test_double_angle_lateral_gap_and_external_use_full_component_height(self):
        base = _production("L 40 x 4", assembly="DoubleAngle")
        gaps = _chord_candidates(base, "AssemblyGap")
        lateral = [value for value in gaps if value.placement.value != "Center"]
        centered = next(value for value in gaps
                        if value.placement.value == "Center")
        external = _chord_candidates(base, "OuterExposed")
        self.assertTrue(all(math.isclose(value.contact_band, 28.5, abs_tol=.02)
                            for value in lateral+external))
        self.assertTrue(all(math.isclose(value.outline_band, -11.5, abs_tol=.02)
                            for value in lateral+external))
        self.assertIsNone(centered.contact_band)  # approved centered fallback
        lateral_levels = [_level(_production(
            "L 40 x 4", assembly="DoubleAngle",
            placement=value.stable_key)) for value in lateral+external]
        self.assertLess(max(lateral_levels)-min(lateral_levels), .02)
        centered_level = _level(_production(
            "L 40 x 4", assembly="DoubleAngle",
            placement=centered.stable_key))
        self.assertLess(max(lateral_levels)-min(lateral_levels), .02)
        self.assertAlmostEqual(min(lateral_levels), centered_level, delta=.02)
        for value in lateral+external:
            self.assert_window_has_no_positive_penetration(value)


class PhysicalOptionOrganizationTests(unittest.TestCase):
    def options(self, outline):
        center = definition("interactive/truss_controller.py",
                            "_candidate_center", {})
        deduplicate = definition("interactive/truss_controller.py",
                                 "_deduplicated_transverse_candidates", {})
        function = definition("interactive/truss_controller.py",
                              "_transverse_placement_regions", dict(
                                  _candidate_center=center,
                                  _deduplicated_transverse_candidates=deduplicate))
        return function(outline.attachment.candidates)

    def test_ue_main_opening_is_presented_as_three_internal_positions(self):
        regions = self.options(_production("Ue 150 × 60 × 20 × 3,00"))
        self.assertEqual(tuple(value[1] for value in regions),
                         ("Externa", "Interna"))
        self.assertEqual(tuple(label for _key, label in regions[1][2]),
                         ("Lado A", "Central", "Lado B"))

    def test_double_angle_names_gap_external_and_distinct_internal_bands(self):
        regions = self.options(_production("L 40 x 4", assembly="DoubleAngle"))
        self.assertEqual(tuple(value[1] for value in regions),
                         ("Externa", "Entre componentes",
                          "Cantoneira A", "Cantoneira B"))
        self.assertEqual(tuple(label for _key, label in regions[1][2]),
                         ("Junto ao componente A", "Central",
                          "Junto ao componente B"))
        self.assertEqual(tuple(label for _key, label in regions[2][2]),
                         ("Face interna", "Face externa"))
        self.assertEqual(tuple(label for _key, label in regions[3][2]),
                         ("Face interna", "Face externa"))


if __name__ == "__main__":
    unittest.main()
