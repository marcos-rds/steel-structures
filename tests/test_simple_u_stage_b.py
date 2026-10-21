"""Focused presentation and shared creation/truss contracts for simple U."""

import copy
from dataclasses import asdict
import math
import types
import unittest

from freecad.SteelStructures import profile_catalog
from freecad.SteelStructures.paths import CATALOGS_DIR
from freecad.SteelStructures.profiles import (
    ProfileLibrary, build_section_geometry, section_insertion_references,
)
from freecad.SteelStructures.profiles.presentation import (
    profile_dimension_rows, profile_preview_dimension_rows, profile_property_groups,
    profile_source_groups,
)
from freecad.SteelStructures.profiles.preview_geometry import (
    SchematicCubic2D, SchematicLine2D, nearest_reference, preview_screen_point,
    schematic_section_for_geometry, transform_preview_point,
)
from freecad.SteelStructures.trusses.assemblies import configure_assembly, compatible_modes, role_profile
from freecad.SteelStructures.trusses.realization import build_candidate
from freecad.SteelStructures.trusses.serialization import encode_state, decode_state
from tests.test_profile_browser import (
    ProfileBrowserModel, _FakeScene, _load_preview_runtime_module, _load_browser_runtime_module,
)
from tests.test_truss_assemblies import config as truss_config
from tests.test_creation_preferences import ParamDatabase, load_preferences


class SimpleUStageBTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.library = ProfileLibrary(CATALOGS_DIR)
        cls.profiles = cls.library.list_profiles(series_id="u-simple-nbr-6355")

    @staticmethod
    def rows(rows):
        return {row.label: row.value for row in rows}

    def test_all_profiles_roundtrip_browser_and_creation_identity(self):
        model = ProfileBrowserModel(self.library)
        self.assertEqual(len(model.set_filter("aco-dobrado", "u-simple-nbr-6355")), 125)
        for p in self.profiles:
            with self.subTest(profile=p.designation):
                self.assertEqual(model.select(p.ref), p)
                category, series, designation = profile_catalog.selection_for_ref(p.ref)
                self.assertEqual((category, series), ("Aço Dobrado", "U Dobrado Simples (U) — NBR 6355"))
                self.assertEqual(designation, p.designation)
                self.assertEqual(profile_catalog.ref_for_designation(designation), p.ref)
                self.assertEqual(profile_catalog.get(designation).definition, p)
                self.assertEqual(len(profile_catalog.insertion_options(profile_catalog.get(designation))), 9)
        self.assertEqual(len(model.set_query("U250x100x6,35")), 1)

    def test_browser_groups_catalog_categories_once_and_preserves_both_folded_series(self):
        module = _load_browser_runtime_module()

        class TreeItem:
            def __init__(self, labels):
                self.name, self.children = labels[0], []

            def setData(self, _column, _role, value):
                self.value = value

            def addChild(self, child):
                self.children.append(child)

            def setExpanded(self, _value):
                pass

        previous = getattr(module.QtWidgets, "QTreeWidgetItem", None)
        module.QtWidgets.QTreeWidgetItem = TreeItem
        try:
            for filtered in (False, True):
                roots = []
                dialog = types.SimpleNamespace(
                    library=self.library, _filter_catalog=filtered,
                    _profile_filter=(lambda p: p.series_id == "u-simple-nbr-6355") if filtered else (lambda p: True),
                    tree=types.SimpleNamespace(addTopLevelItem=roots.append),
                )
                module.ProfileBrowserDialog._populate_tree(dialog)
                folded = [root for root in roots if root.name == "Aço Dobrado"]
                self.assertEqual(len(folded), 1)
                self.assertEqual([child.value[1] for child in folded[0].children],
                                 ["u-simple-nbr-6355"] if filtered else ["u-simple-nbr-6355", "ue-nbr-6355"])
                self.assertEqual(len(roots), 1 if filtered else 4)
        finally:
            if previous is None:
                del module.QtWidgets.QTreeWidgetItem
            else:
                module.QtWidgets.QTreeWidgetItem = previous

    def test_precision_and_normative_source_are_visible_without_replacing_values(self):
        for p in self.profiles:
            original = (p.geometry, p.physical_properties, p.section_properties, p.centroid)
            rows = self.rows(profile_preview_dimension_rows(p))
            self.assertEqual(tuple(rows), ("bw", "bf", "t", "ri"))
            self.assertIn("tn", self.rows(profile_dimension_rows(p)))
            groups = {g.title: self.rows(g.rows) for g in profile_property_groups(p)}
            self.assertEqual(groups["Físicas"]["Massa linear"], f"{p.physical_properties.mass_per_length_kg_m:.2f} kg/m".replace(".", ","))
            self.assertEqual(groups["Torção / estabilidade"]["It"], f"{p.section_properties['it'] / 1e4:.3f} cm⁴".replace(".", ","))
            source = {g.title: self.rows(g.rows) for g in profile_source_groups(p)}
            self.assertEqual(source["Fonte"]["Tabela"], "A.2")
            self.assertEqual(source["Fonte"]["Figura"], "A.2")
            self.assertEqual(source["Fonte"]["Organismo"], "ABNT")
            self.assertNotIn("Fabricante", source["Fonte"])
            self.assertEqual(source["Geometria"]["Propriedades"], "Seção bruta — método linear normativo")
            self.assertEqual(original, (p.geometry, p.physical_properties, p.section_properties, p.centroid))
            if p.geometry["tn"] == 6.35:
                self.assertEqual(rows["ri"], "9,525 mm")
                self.assertEqual(self.rows(profile_dimension_rows(p))["ri"], "9,525 mm")
        first = self.profiles[0]
        self.assertEqual({g.title: self.rows(g.rows) for g in profile_property_groups(first)}["Torção / estabilidade"]["It"], "0,006 cm⁴")

    def test_real_renderer_has_four_callouts_and_targets_named_geometry_stations(self):
        module = _load_preview_runtime_module()
        for p in self.profiles:
            g = build_section_geometry(p)
            s = dict(g.dimension_stations)
            scene = _FakeScene()
            renderer = object.__new__(module.SectionPreviewView)
            renderer.scene = lambda: scene
            renderer._add_dimensions(g, self.rows(profile_preview_dimension_rows(p)))
            labels = [item.html for item in scene.text_items]
            with self.subTest(profile=p.designation):
                self.assertEqual(len(labels), 4)
                for symbol in ("bw", "bf", "t", "ri"):
                    self.assertTrue(any(f"<b>({symbol})</b>" in label for label in labels))
                self.assertFalse(any("<b>(D)</b>" in label for label in labels))
                thickness_line, radius_line, landing = [
                    item.args for item in scene.line_items if not hasattr(item, "flag")
                ][-3:]
                self.assertAlmostEqual(thickness_line[1], -s["nominal_top_y"] + s["thickness"])
                ri = s["internal_radius"]
                cx = s["external_web_x"] + ri + s["thickness"]
                cy = -s["nominal_bottom_y"] - ri - s["thickness"]
                self.assertAlmostEqual(math.hypot(radius_line[0] - cx, radius_line[1] - cy), ri)
                self.assertLess(thickness_line[3], radius_line[3])
                self.assertAlmostEqual(radius_line[2] - radius_line[0], radius_line[1] - radius_line[3])
                self.assertEqual(landing[1], landing[3])
                self.assertTrue(any("<b>(ri)</b>&nbsp;R " in label for label in labels))
                self.assertEqual(len(scene.ellipse_items), 1)
                arrow, = scene.path_items
                self.assertEqual(arrow.position, radius_line[:2])
                self.assertEqual(arrow.flag, (1, True))
                self.assertTrue(arrow.path.closed)
                tip, base1, base2 = arrow.path.points
                self.assertEqual(tip, (0., 0.))
                base = tuple((a + b) / 2. for a, b in zip(base1, base2))
                self.assertAlmostEqual(math.hypot(*base), 8.)
                self.assertAlmostEqual(math.dist(base1, base2), 2.4)
                self.assertAlmostEqual(base[0], -base[1])
                self.assertEqual(arrow.brush.color.rgb, module.DIMENSION_COLOR)
                for ref in section_insertion_references(g):
                    renderer._add_insertion_marker(g, ref.id)
                self.assertGreater(len(scene.ellipse_items), 2)

    def test_one_curved_parallel_thickness_schematic_and_nine_distinct_hotspots(self):
        schematics = [schematic_section_for_geometry(build_section_geometry(p)) for p in self.profiles]
        first = schematics[0]
        for diagram, profile in zip(schematics, self.profiles):
            self.assertEqual(diagram.outline, first.outline)
            self.assertEqual(diagram.segments, first.segments)
            self.assertEqual(diagram.references, first.references)
            self.assertEqual(diagram.typology_key, ("cold_formed_channel", "simple_u"))
            self.assertEqual([(r.id, r.label) for r in diagram.references],
                             [(r.id, r.label) for r in section_insertion_references(build_section_geometry(profile))])
        self.assertEqual(len(first.segments), 12)
        self.assertEqual(sum(isinstance(s, SchematicCubic2D) for s in first.segments), 4)
        horizontal = [s for s in first.segments if isinstance(s, SchematicLine2D) and abs(s.start.y - s.end.y) < 1e-12]
        self.assertEqual(len(horizontal), 4)
        self.assertEqual(len({r.point for r in first.references}), 9)
        points = {r.id: r.point for r in first.references}
        self.assertEqual(points["web_center"].y, 0.)
        self.assertEqual(points["web_back"].y, 0.)
        web_edges = [s for s in first.segments if isinstance(s, SchematicLine2D)
                     and s.start.x == s.end.x and s.start.x < 0.]
        self.assertEqual(len(web_edges), 2)
        self.assertAlmostEqual(points["web_center"].x,
                               sum(s.start.x for s in web_edges) / 2.)
        self.assertEqual(points["rear_top"].y, points["outer_top_mid"].y)
        self.assertEqual(points["rear_bottom"].y, points["outer_bottom_mid"].y)
        self.assertAlmostEqual(points["flange_top_tip"].y, -points["flange_bottom_tip"].y)
        self.assertEqual(points["flange_top_tip"].y, points["outer_top_mid"].y)
        self.assertEqual(points["flange_bottom_tip"].y, points["outer_bottom_mid"].y)
        # Outer bends occupy under 30% of the normalized half-height.
        outer_bends = [s for s in first.segments if isinstance(s, SchematicCubic2D)
                       and abs(s.start.x - s.end.x) > .1]
        self.assertTrue(all(abs(s.start.x - s.end.x) < .30 for s in outer_bends))
        self.assertNotEqual(first.outline, schematic_section_for_geometry(build_section_geometry(self.library.list_profiles(series_id="ue-nbr-6355")[0])).outline)

    def test_every_hotspot_is_selectable_after_rotation_and_matches_local_roll(self):
        diagram = schematic_section_for_geometry(build_section_geometry(self.profiles[0]))
        for angle in (0, 37, 90, 180, 270):
            for ref in diagram.references:
                x, y = preview_screen_point(ref.point, diagram.center, angle, 200, 130, 70)
                self.assertEqual(nearest_reference(diagram.references, diagram.center, angle, 200, 130, 70, x, y, 8), ref)
                transformed = transform_preview_point(ref.point, diagram.center, angle)
                theta = math.radians(angle)
                dx, dy = ref.point.x - diagram.center.x, ref.point.y - diagram.center.y
                self.assertAlmostEqual(transformed.x, dx * math.cos(theta) - dy * math.sin(theta))
                self.assertAlmostEqual(transformed.y, dx * math.sin(theta) + dy * math.cos(theta))

    def test_all_insertion_preferences_and_rotation_angle_roundtrip_for_member_and_column(self):
        preferences = load_preferences(ParamDatabase())
        # Exercise actual catalog eligibility and insertion labels through the
        # existing ParamGet serialization, rather than extending its test stub.
        preferences.profile_catalog = profile_catalog
        p = self.profiles[116]
        category, series, designation = profile_catalog.selection_for_ref(p.ref)
        for ref in section_insertion_references(build_section_geometry(p)):
            for radii in (True, False):
                common = dict(category=category, series=series, designation=designation,
                              insertion=ref.label, rotation=37.0, color=(.2, .4, .8),
                              generate_radii=radii)
                member = preferences.MemberCreationSettings(**common, element_type="Viga")
                column = preferences.ColumnCreationSettings(**common, height=2500., continue_creating=True)
                self.assertTrue(preferences.save_member_creation_settings(member))
                self.assertEqual(preferences.load_member_creation_settings(), member)
                self.assertTrue(preferences.save_column_creation_settings(column))
                self.assertEqual(preferences.load_column_creation_settings(), column)

    def test_truss_all_roles_and_insertions_roundtrip_without_schema_change(self):
        p = next(p for p in self.profiles if p.geometry["tn"] == 6.35)
        refs = section_insertion_references(build_section_geometry(p))
        for ref in refs:
            config = truss_config()
            for role in config["role_specs"].values():
                role.update(profile_ref=asdict(p.ref), insertion=ref.label, rotation=37,
                            section_geometry_mode="Simplified")
            candidate = build_candidate(config)
            state = decode_state(encode_state(candidate))
            self.assertEqual(state["schema_version"], 2)
            self.assertEqual(build_candidate(state["candidate"]["config"]), candidate)
            self.assertTrue(candidate.items)
            for item in candidate.items:
                self.assertEqual(item.spec.insertion, ref.label)
                self.assertEqual(item.spec.rotation, 37)
                self.assertEqual(item.spec.profile_ref, asdict(p.ref))

    def test_truss_double_channel_uses_existing_spacing_transforms_and_schema(self):
        for p in (self.profiles[0], self.profiles[116], self.profiles[-1]):
            for mode in ("DoubleChannelInward", "DoubleChannelOutward", "SpacedPair"):
                config = truss_config()
                role = copy.deepcopy(config["role_specs"]["TOP_CHORD"])
                role.update(profile_ref=asdict(p.ref), rotation=37, insertion="Centro da alma")
                self.assertIn(mode, compatible_modes(role_profile(role)))
                config["role_specs"]["TOP_CHORD"] = configure_assembly(role, mode, 180)
                candidate = build_candidate(config)
                state = decode_state(encode_state(candidate))
                self.assertEqual(state["schema_version"], 3)
                self.assertEqual(build_candidate(state["candidate"]["config"]), candidate)
                self.assertEqual(config["role_specs"]["TOP_CHORD"]["assembly_spec"]["spec"]["component_spacing"], 180)


if __name__ == "__main__":
    unittest.main()
