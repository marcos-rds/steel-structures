"""Detailed/Simplified representation contracts for typed profile geometry."""

import math
import unittest

from freecad.SteelStructures.paths import CATALOGS_DIR
from freecad.SteelStructures.profiles import ProfileLibrary, ProfileRef
from freecad.SteelStructures.profiles.geometry import (
    ArcSegment2D, LineSegment2D, SectionGeometryMode,
    build_section_geometry, section_geometry_mode_has_effect,
)
from freecad.SteelStructures.profiles.insertion import section_insertion_references


CATALOG_ID = "gerdau-construcao-metalica-2023-01"


class SectionGeometryModeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.library = ProfileLibrary(CATALOGS_DIR)

    def profile(self, profile_id):
        return self.library.get(ProfileRef(CATALOG_ID, profile_id))

    def assert_mode_contract(self, profile):
        detailed = build_section_geometry(profile, SectionGeometryMode.DETAILED)
        simplified = build_section_geometry(profile, SectionGeometryMode.SIMPLIFIED)
        self.assertEqual(detailed.bounds, simplified.bounds)
        self.assertEqual(detailed.origin, simplified.origin)
        self.assertEqual(detailed.dimension_stations, simplified.dimension_stations)
        detailed_refs = section_insertion_references(detailed)
        simplified_refs = section_insertion_references(simplified)
        self.assertEqual(detailed_refs, simplified_refs)
        self.assertTrue(any(isinstance(item, ArcSegment2D)
                            for item in detailed.outer_path.segments))
        self.assertTrue(all(isinstance(item, LineSegment2D)
                            for item in simplified.outer_path.segments))
        self.assertGreater(detailed.area, 0.0)
        self.assertGreater(simplified.area, 0.0)
        return detailed, simplified

    def test_tapered_i_removes_only_radii_and_keeps_taper(self):
        profile = self.profile("i-6x22.00")
        _detailed, simplified = self.assert_mode_contract(profile)
        slopes = [abs((edge.end.y - edge.start.y) / (edge.end.x - edge.start.x))
                  for edge in simplified.outer_path.segments
                  if abs(edge.end.x - edge.start.x) > 1e-9
                  and abs(edge.end.y - edge.start.y) > 1e-9]
        self.assertTrue(any(math.isclose(value, math.tan(math.radians(9.46)),
                                             rel_tol=1e-9) for value in slopes))

    def test_tapered_u_removes_only_radii_and_keeps_taper(self):
        profile = self.profile("u-6x12.20")
        _detailed, simplified = self.assert_mode_contract(profile)
        slopes = [abs((edge.end.y - edge.start.y) / (edge.end.x - edge.start.x))
                  for edge in simplified.outer_path.segments
                  if abs(edge.end.x - edge.start.x) > 1e-9
                  and abs(edge.end.y - edge.start.y) > 1e-9]
        self.assertTrue(any(math.isclose(value, math.tan(math.radians(8.3)),
                                             rel_tol=1e-9) for value in slopes))

    def test_all_ue_profiles_have_sharp_valid_simplified_contours(self):
        profiles = self.library.list_profiles(series_id="ue-nbr-6355")
        self.assertEqual(len(profiles), 85)
        for profile in profiles:
            with self.subTest(profile=profile.designation):
                self.assert_mode_contract(profile)

    def test_capability_uses_typed_geometry_not_display_names(self):
        for profile_id, expected in (
            ("i-6x22.00", True), ("u-6x12.20", True),
            ("w-150x13.0", False), ("t-2x0.25", False),
            ("equal-angle-metric-50x5", False),
        ):
            self.assertEqual(section_geometry_mode_has_effect(self.profile(profile_id)), expected)

    def test_profiles_without_technical_radii_remain_identical(self):
        for profile_id in ("w-150x13.0", "t-2x0.25", "equal-angle-metric-50x5"):
            profile = self.profile(profile_id)
            self.assertEqual(build_section_geometry(profile, "Detailed"),
                             build_section_geometry(profile, "Simplified"))


if __name__ == "__main__":
    unittest.main()
