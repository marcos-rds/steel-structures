"""Stage 2 integration contracts for the released NBR 6355 Ue family."""

import unittest

from freecad.SteelStructures import profile_catalog
from freecad.SteelStructures.paths import CATALOGS_DIR
from freecad.SteelStructures.profiles import (
    ProfileLibrary, build_section_geometry, section_insertion_references,
)
from freecad.SteelStructures.profiles.presentation import (
    profile_dimension_rows, profile_preview_dimension_rows,
    profile_property_groups, profile_source_groups,
)
from freecad.SteelStructures.profiles.preview_geometry import (
    SchematicCubic2D, schematic_section_for_geometry, section_outline_points,
)


class UeStage2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.library = ProfileLibrary(CATALOGS_DIR)
        cls.profiles = tuple(
            profile for profile in cls.library.list_profiles()
            if profile.series_id == "ue-nbr-6355"
        )

    def profile(self, token):
        return next(profile for profile in self.profiles if token in profile.designation)

    @staticmethod
    def rows(items):
        return {item.label: item.value for item in items}

    def test_released_category_series_and_numeric_catalog_order(self):
        profile_catalog.reload()
        self.assertEqual(profile_catalog.categories().count("Aço Dobrado"), 1)
        self.assertEqual(profile_catalog.series_for_category("Aço Dobrado"), (
            ["U Dobrado Simples (U) — NBR 6355", "U Enrijecido (Ue) — NBR 6355"]
        ))
        self.assertEqual(len(profile_catalog.designations("Aço Dobrado")), 210)
        self.assertEqual(len(profile_catalog.designations("Aço Dobrado", "U Enrijecido (Ue) — NBR 6355")), 85)
        self.assertTrue(all(profile.geometry_status == "released" for profile in self.profiles))
        keys = [tuple(profile.geometry[name] for name in ("bw", "bf", "D", "tn"))
                for profile in self.profiles]
        self.assertEqual(keys, sorted(keys))

    def test_browser_uses_real_contour_and_five_requested_dimensions(self):
        for token in ("50 × 25 × 10 × 1,20", "300 × 100 × 25 × 4,75"):
            profile = self.profile(token)
            geometry = build_section_geometry(profile)
            with self.subTest(profile=profile.designation):
                self.assertGreater(len(section_outline_points(geometry)), 20)
                self.assertEqual(self.rows(profile_preview_dimension_rows(profile)), {
                    "bw": f"{profile.geometry['bw']:g} mm".replace(".", ","),
                    "bf": f"{profile.geometry['bf']:g} mm".replace(".", ","),
                    "D": f"{profile.geometry['D']:g} mm".replace(".", ","),
                    "t": str(profile.geometry['t']).replace(".", ",") + " mm",
                    "ri": str(profile.geometry['ri']).replace(".", ",") + " mm",
                })
                self.assertEqual(geometry.bounds.width, profile.geometry["bf"])
                self.assertAlmostEqual(geometry.bounds.height, profile.geometry["bw"])

    def test_full_dimensions_keep_tn_while_preview_omits_it(self):
        profile = self.profile("150 × 60 × 20 × 3,00")
        dimensions = self.rows(profile_dimension_rows(profile))
        self.assertIn("tn", dimensions)
        self.assertIn("ri", dimensions)
        self.assertNotIn("tn", self.rows(profile_preview_dimension_rows(profile)))

    def test_source_and_normative_properties_are_semantically_explicit(self):
        profile = self.profile("150 × 60 × 20 × 3,00")
        source = {group.title: self.rows(group.rows) for group in profile_source_groups(profile)}
        self.assertEqual(source["Fonte"], {
            "Organismo": "ABNT", "Norma": "ABNT NBR 6355", "Edição": "2012",
            "Anexo": "A — informativo", "Figura": "A.3", "Tabela": "A.3",
            "Condição": "Aço sem revestimento",
        })
        self.assertNotIn("Fabricante", source["Fonte"])
        groups = {group.title: self.rows(group.rows) for group in profile_property_groups(profile)}
        self.assertEqual(groups["Físicas"]["Massa linear"], "6,84 kg/m")
        self.assertEqual(groups["Físicas"]["Área"], "8,71 cm²")
        self.assertEqual(groups["Centroide / propriedades adicionais"]["Xg"], "1,92 cm")
        self.assertIn("x0", groups["Torção / estabilidade"])
        self.assertIn("r0", groups["Torção / estabilidade"])

    def test_schematic_is_shared_curved_ue_with_eleven_hotspots(self):
        schematics = [schematic_section_for_geometry(build_section_geometry(self.profile(token)))
                      for token in ("50 × 25", "150 × 60", "300 × 100")]
        first = schematics[0]
        self.assertTrue(all(item.outline == first.outline for item in schematics[1:]))
        self.assertTrue(any(isinstance(segment, SchematicCubic2D) for segment in first.segments))
        self.assertEqual(tuple(reference.id for reference in first.references), (
            "centroid", "web_center", "web_back", "rear_top", "rear_bottom",
            "lip_top_tip", "lip_bottom_tip",
            "outer_top_mid", "outer_bottom_mid",
            "outer_lip_top_corner", "outer_lip_bottom_corner",
        ))
        centroid = first.references[0].point
        self.assertEqual(centroid.y, 0.0)
        self.assertLess(centroid.x, (min(p.x for p in first.outline) + max(p.x for p in first.outline)) / 2.0)

    def test_insertion_nominal_corners_and_real_lip_caps(self):
        geometry = build_section_geometry(self.profile("150 × 60 × 20 × 3,00"))
        refs = {item.id: item.point for item in section_insertion_references(geometry)}
        self.assertEqual(refs["centroid"], geometry.origin)
        self.assertEqual((refs["rear_top"].x, refs["rear_top"].y),
                         (geometry.bounds.min_x, geometry.bounds.max_y))
        for identifier, segment in (("lip_top_tip", geometry.outer_path.segments[-1]),
                                    ("lip_bottom_tip", geometry.outer_path.segments[9])):
            point = refs[identifier]
            self.assertAlmostEqual(point.x, (segment.start.x + segment.end.x) / 2.0)
            self.assertAlmostEqual(point.y, (segment.start.y + segment.end.y) / 2.0)


if __name__ == "__main__":
    unittest.main()
