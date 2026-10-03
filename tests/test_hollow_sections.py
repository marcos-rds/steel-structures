"""Stage-A contracts for future SHS, RHS and CHS catalog integration."""

from __future__ import annotations

import math
import types
import unittest

from freecad.SteelStructures.profiles import (
    CatalogMetadata, CatalogSource, PhysicalProperties, ProfileDefinition, ProfileRef,
    SectionGeometryMode, build_circular_hollow_section,
    build_rectangular_hollow_section, build_section_geometry,
    build_square_hollow_section, hollow_section_properties,
    canonical_rhs_key, nominal_hollow_section_radii,
    normalize_hollow_profile_definition, normalize_rhs_dimensions,
    section_geometry_mode_has_effect, section_insertion_references,
)
from freecad.SteelStructures.profiles.geometry import ArcSegment2D, LineSegment2D
from freecad.SteelStructures.profiles.preview_geometry import (
    SchematicCubic2D, schematic_section_for_geometry, section_contour_points,
)
from freecad.SteelStructures.profiles.presentation import (
    profile_preview_dimension_rows, profile_property_groups,
)


CATALOG = CatalogMetadata(
    id="test-hollow-fixtures", name="Fixtures tubulares", catalog_version="0",
    manufacturer=None, source=CatalogSource("fixture de teste"), units={},
)


def fixture(variant, geometry, mass=10.0, area=1000.0, section_properties=None):
    return ProfileDefinition(
        ref=ProfileRef(CATALOG.id, f"{variant}-fixture"),
        designation=f"{variant.upper()} fixture", equivalent_designation=None,
        aliases=(), catalog_markers=(), availability_status="test-only",
        geometry_status="released", series_id=variant, category_id="hollow-test",
        manufacturer=None, family=variant.upper(), geometry_type="hollow_section",
        geometry_variant=variant, geometry_notes="fixture; não é catálogo comercial",
        geometry=geometry, physical_properties=PhysicalProperties(mass, area),
        section_properties=section_properties or {}, reported_section_properties={},
        section_property_override=None, centroid_from_top_flange_face=None,
        centroid={"x": 0.0, "y": 0.0}, catalog=CATALOG,
    )


class HollowSectionPureGeometryTests(unittest.TestCase):
    def test_cad_radii_are_2t_and_t_without_manufacturer_or_calculation_claim(self):
        for t, side in ((3.0, 100.0), (8.0, 100.0), (16.0, 76.2)):
            with self.subTest(t=t, side=side):
                radii = nominal_hollow_section_radii(t, side)
                self.assertEqual(radii.cad_outer_corner_radius, 2.0 * t)
                self.assertEqual(radii.cad_inner_corner_radius, t)

    def test_unrealizable_2t_cad_radius_is_rejected_without_clamp(self):
        with self.assertRaisesRegex(ValueError, "não é realizável"):
            nominal_hollow_section_radii(16.0, 60.0)
        with self.assertRaisesRegex(ValueError, "não é realizável"):
            nominal_hollow_section_radii(16.0, 64.0)
        self.assertEqual(nominal_hollow_section_radii(16.0, 64.0001).cad_outer_corner_radius, 32.0)

    def test_rhs_public_dimensions_are_normalized_and_h_is_vertical(self):
        self.assertEqual(normalize_rhs_dimensions(100, 150, 4.75), (150, 100, 4.75))
        self.assertEqual(canonical_rhs_key(100, 150, 4.75), canonical_rhs_key(150, 100, 4.75))
        profile = fixture("rectangular", {"h": 100.0, "b": 150.0, "t": 4.75})
        normalized = normalize_hollow_profile_definition(profile)
        self.assertEqual((normalized.geometry["h"], normalized.geometry["b"]), (150.0, 100.0))
        geometry = build_section_geometry(profile)
        self.assertEqual((geometry.bounds.height, geometry.bounds.width), (150.0, 100.0))

    def test_shs_rhs_detailed_and_simplified_preserve_outer_dimensions(self):
        for builder, kwargs in (
            (build_square_hollow_section, {"b": 100.0, "t": 4.0}),
            (build_rectangular_hollow_section,
             {"width": 150.0, "height": 100.0, "t": 4.75}),
        ):
            detailed = builder(**kwargs, mode=SectionGeometryMode.DETAILED)
            simplified = builder(**kwargs, mode=SectionGeometryMode.SIMPLIFIED)
            with self.subTest(builder=builder.__name__):
                self.assertEqual(detailed.bounds, simplified.bounds)
                self.assertEqual(len(detailed.inner_paths), 1)
                self.assertEqual(len(simplified.inner_paths), 1)
                self.assertTrue(any(isinstance(s, ArcSegment2D)
                                    for s in detailed.outer_path.segments))
                self.assertTrue(all(isinstance(s, LineSegment2D)
                                    for s in simplified.outer_path.segments))
                self.assertGreater(detailed.area, 0.0)
                self.assertGreater(simplified.area, 0.0)

    def test_chs_curvature_is_fundamental_and_has_one_circular_void(self):
        geometry = build_circular_hollow_section(d=88.9, t=3.0)
        self.assertEqual(len(geometry.outer_path.segments), 2)
        self.assertEqual(len(geometry.inner_paths), 1)
        self.assertTrue(all(isinstance(segment, ArcSegment2D)
                            for segment in geometry.outer_path.segments))
        expected = math.pi * (88.9 ** 2 - (88.9 - 6.0) ** 2) / 4.0
        self.assertAlmostEqual(geometry.area, expected)

    def test_mode_independent_dimensional_property_contract_and_axes(self):
        rhs = hollow_section_properties(family="RHS", h=150, b=100, t=4.75)
        self.assertGreater(rhs.ix, rhs.iy)
        self.assertIn("EN 10219-2:2019 Annex A", rhs.basis)
        self.assertIn("not product certification", rhs.basis)
        self.assertEqual(rhs.centroid_x, 0.0)
        self.assertEqual(rhs.centroid_y, 0.0)
        chs = hollow_section_properties(family="CHS", d=88.9, t=3.0)
        self.assertAlmostEqual(chs.ix, chs.iy)
        self.assertAlmostEqual(chs.wx, chs.wy)
        self.assertIn("exact circular", chs.basis)

    def test_property_contract_rejects_nonfinite_and_unknown_family(self):
        for kwargs in (
            {"family": "RHS", "h": math.inf, "b": 100, "t": 4},
            {"family": "CHS", "d": math.nan, "t": 3},
            {"family": "XYZ", "h": 100, "b": 50, "t": 3},
        ):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                hollow_section_properties(**kwargs)

    def test_invalid_hollow_dimensions_fail_before_cad_boundary(self):
        invalid = (
            lambda: build_square_hollow_section(b=20, t=10),
            lambda: build_rectangular_hollow_section(width=100, height=100, t=3),
            lambda: build_circular_hollow_section(d=20, t=10),
        )
        for call in invalid:
            with self.assertRaises(ValueError):
                call()


class HollowSectionTypedIntegrationTests(unittest.TestCase):
    def test_rhs_presentation_normalizes_dimensions_and_groups_units(self):
        profile = fixture(
            "rectangular", {"h": 100.0, "b": 150.0, "t": 4.75},
            section_properties={
                "ix": 10_000.0, "iy": 5_000.0,
                "wx": 1_000.0, "wy": 500.0, "rx": 10.0, "ry": 5.0,
            },
        )
        dimensions = {row.label: row.value for row in profile_preview_dimension_rows(profile)}
        self.assertEqual(dimensions, {"H": "150 mm", "B": "100 mm", "t": "4,75 mm"})
        groups = {group.title: {row.label: row.value for row in group.rows}
                  for group in profile_property_groups(profile)}
        self.assertEqual(groups["Físicas"]["Área"], "10,0 cm²")
        self.assertEqual(groups["Propriedades geométricas"]["Ix"], "1 cm⁴")
        self.assertEqual(groups["Propriedades geométricas"]["Wx"], "1 cm³")
        self.assertEqual(groups["Propriedades geométricas"]["rx"], "1 cm")
        self.assertEqual(groups["Centroide"], {
            "x do centroide": "0 cm", "y do centroide": "0 cm",
        })

    def test_typed_dispatch_and_geometry_mode_capability(self):
        profiles = (
            fixture("square", {"b": 100.0, "t": 3.0}),
            fixture("rectangular", {"h": 150.0, "b": 100.0, "t": 4.75}),
            fixture("circular", {"d": 88.9, "t": 3.0}),
        )
        for profile in profiles:
            geometry = build_section_geometry(profile, SectionGeometryMode.SIMPLIFIED)
            with self.subTest(variant=profile.geometry_variant):
                self.assertEqual(geometry.geometry_variant, profile.geometry_variant)
                self.assertEqual(
                    section_geometry_mode_has_effect(profile),
                    profile.geometry_variant != "circular",
                )

    def test_nominal_insertion_points_do_not_depend_on_radius_mode(self):
        profile = fixture("rectangular", {"h": 150.0, "b": 100.0, "t": 4.75})
        references = []
        for mode in SectionGeometryMode:
            geometry = build_section_geometry(profile, mode)
            references.append(section_insertion_references(geometry))
        self.assertEqual(references[0], references[1])
        self.assertEqual({item.id for item in references[0]}, {
            "centroid", "left", "right", "top", "bottom",
            "top_left", "top_right", "bottom_left", "bottom_right",
        })

    def test_chs_uses_the_shared_face_labels_for_cardinal_insertions(self):
        references = section_insertion_references(
            build_circular_hollow_section(d=88.9, t=3.0)
        )
        self.assertEqual([item.label for item in references], [
            "Centroide", "Face esquerda", "Face direita",
            "Face superior", "Face inferior",
        ])

    def test_preview_contracts_include_inner_contour_and_hotspots(self):
        for geometry in (
            build_square_hollow_section(b=100, t=3),
            build_rectangular_hollow_section(width=150, height=100, t=4.75),
            build_circular_hollow_section(d=88.9, t=3),
        ):
            contours = section_contour_points(geometry)
            schematic = schematic_section_for_geometry(geometry)
            with self.subTest(variant=geometry.geometry_variant):
                self.assertEqual(len(contours), 2)
                self.assertIsNotNone(schematic)
                self.assertEqual(len(schematic.inner_segments), 1)
                self.assertTrue(schematic.references)
                if geometry.geometry_variant == "circular":
                    self.assertTrue(all(
                        isinstance(segment, SchematicCubic2D)
                        for contour in (schematic.segments,) + schematic.inner_segments
                        for segment in contour
                    ))
                    for contour in (schematic.segments,) + schematic.inner_segments:
                        self.assertEqual(contour[0].start, contour[-1].end)
                        for first, second in zip(contour, contour[1:]):
                            self.assertEqual(first.end, second.start)
                    outer_cardinals = {
                        (round(segment.start.x, 8), round(segment.start.y, 8))
                        for segment in schematic.segments
                    }
                    self.assertTrue({(1.0, 0.0), (0.0, 1.0), (-1.0, 0.0), (0.0, -1.0)} <= outer_cardinals)

    def test_mass_and_equivalent_length_use_catalog_mass_and_same_shape_area(self):
        profile = fixture("rectangular", {"h": 150.0, "b": 100.0, "t": 4.75}, mass=17.25)
        physical_length = 2345.0
        for mode in SectionGeometryMode:
            geometry = build_section_geometry(profile, mode)
            shape_volume = geometry.area * physical_length
            equivalent_length = shape_volume / geometry.area
            total_mass = profile.physical_properties.mass_per_length_kg_m * equivalent_length / 1000.0
            with self.subTest(mode=mode):
                self.assertAlmostEqual(equivalent_length, physical_length)
                self.assertAlmostEqual(total_mass, 17.25 * 2.345)
                self.assertEqual(profile.physical_properties.area_mm2, 1000.0)


class HollowTechnicalPropertyTests(unittest.TestCase):
    """Regression values evaluated from the documented Annex-A equations."""

    EXPECTED = (
        (dict(family="SHS", h=100, b=100, t=4),
         (1494.79644737231, 2263516.8621122013, 2263516.8621122013)),
        (dict(family="SHS", h=200, b=200, t=12),
         (8405.94671058465, 47302212.78710835, 47302212.78710835)),
        (dict(family="RHS", h=150, b=100, t=4.75),
         (2226.646552739859, 6889168.763949921, 3681577.795022629)),
        (dict(family="RHS", h=200, b=80, t=6.3),
         (3232.9592496839155, 15027852.008026935, 3543262.2325846506)),
        (dict(family="RHS", h=203.2, b=76.2, t=16),
         (6818.0385965949345, 23742844.82284037, 4845697.365885922)),
        (dict(family="CHS", d=88.9, t=3),
         (809.5884268300898, 747635.6844524506, 747635.6844524506)),
        (dict(family="CHS", d=100, t=20),
         (5026.548245743669, 4272566.008882118, 4272566.008882118)),
    )

    def test_reference_values_invariants_and_axes(self):
        for arguments, expected in self.EXPECTED:
            with self.subTest(arguments=arguments):
                result = hollow_section_properties(**arguments)
                self.assertAlmostEqual(result.area, expected[0], places=7)
                self.assertAlmostEqual(result.ix, expected[1], places=6)
                self.assertAlmostEqual(result.iy, expected[2], places=6)
                for value in (result.area, result.ix, result.iy, result.wx,
                              result.wy, result.rx, result.ry):
                    self.assertGreater(value, 0.0)
                self.assertAlmostEqual(result.rx, math.sqrt(result.ix / result.area))
                self.assertAlmostEqual(result.ry, math.sqrt(result.iy / result.area))
                if arguments["family"] in ("SHS", "CHS"):
                    self.assertAlmostEqual(result.ix, result.iy)
                    self.assertAlmostEqual(result.wx, result.wy)
                elif arguments["h"] > arguments["b"]:
                    self.assertGreater(result.ix, result.iy)

    def test_calculation_radius_range_boundaries(self):
        from freecad.SteelStructures.profiles.effective_properties import (
            rectangular_hollow_calculation_radii,
        )
        self.assertEqual(rectangular_hollow_calculation_radii(6), (12, 6))
        ro, ri = rectangular_hollow_calculation_radii(6.00001)
        self.assertAlmostEqual(ro, 15.000025)
        self.assertAlmostEqual(ri, 9.000015)
        self.assertEqual(rectangular_hollow_calculation_radii(10), (25, 15))
        ro, ri = rectangular_hollow_calculation_radii(10.00001)
        self.assertAlmostEqual(ro, 30.00003)
        self.assertAlmostEqual(ri, 20.00002)

    def test_extreme_calculation_is_not_constrained_by_cad_radius(self):
        from freecad.SteelStructures.profiles.effective_properties import (
            rectangular_hollow_calculation_radii,
        )
        result = hollow_section_properties(family="RHS", h=203.2, b=76.2, t=16)
        cad = nominal_hollow_section_radii(16, 76.2)
        calculation = rectangular_hollow_calculation_radii(16)
        self.assertEqual((cad.cad_outer_corner_radius, cad.cad_inner_corner_radius), (32, 16))
        self.assertEqual(calculation, (48, 32))
        self.assertGreater(calculation[0], 76.2 / 2.0)
        self.assertIn("EN 10219-2", result.basis)
        # The normative algebra is intentionally evaluated without pretending
        # that ro_calc is a realizable CAD/manufacturing rounded rectangle.
        self.assertAlmostEqual(result.area, 6818.0385965949345)

    def test_installed_commercial_profiles_are_calculated_on_every_reload(self):
        from pathlib import Path
        from freecad.SteelStructures.profiles.catalog import ProfileLibrary
        root = Path(__file__).parents[1] / "freecad" / "SteelStructures" / "catalogs"
        library = ProfileLibrary(root).reload()
        hollows = library.list_profiles(category_id="tubular")
        self.assertEqual(len(hollows), 2999)
        sample_ids = {
            "shs-100x100x4-25", "rhs-150x100x4-75",
            "rhs-203-2x76-2x16", "chs-88-9x3",
        }
        samples = tuple(profile for profile in hollows if profile.ref.profile_id in sample_ids)
        self.assertEqual(len(samples), 4)
        expected = {}
        for profile in samples:
            self.assertIsNotNone(profile.physical_properties.area_mm2)
            self.assertEqual(set(profile.section_properties), {
                "ix", "iy", "wx", "wy", "rx", "ry",
            })
            self.assertEqual(profile.centroid, {"x": 0.0, "y": 0.0})
            self.assertEqual(profile.reported_section_properties, {})
            self.assertEqual(profile.property_provenance["area"].source_type, "calculated")
            expected[profile.ref] = (
                profile.physical_properties.mass_per_length_kg_m,
                profile.section_properties,
            )
        library.reload()
        for ref, (mass, properties) in expected.items():
            reloaded = library.get(ref)
            self.assertEqual(reloaded.physical_properties.mass_per_length_kg_m, mass)
            self.assertEqual(reloaded.section_properties, properties)


class HollowStructuralMemberIntegrationTests(unittest.TestCase):
    """Exercise the real member proxy with a test-only typed hollow profile."""

    @classmethod
    def setUpClass(cls):
        from tests.test_member_placement import load_member
        cls.member = load_member()
        cls.definition = fixture(
            "rectangular", {"h": 150.0, "b": 100.0, "t": 4.75},
            mass=17.25, area=1000.0,
        )
        cls.profile = types.SimpleNamespace(
            definition=cls.definition, mass_per_m=17.25, area_cm2=10.0,
            manufacturer="Fixture", family="RHS", source="fixture de teste",
            designation="RHS fixture", category="Tubulares", series="RHS",
        )

    def proxy(self):
        proxy = self.member.StructuralMemberProxy.__new__(self.member.StructuralMemberProxy)
        proxy._updating = proxy._syncing_length = proxy._syncing_placement = False
        proxy._placement_from_points_pending = True
        proxy._last_placement = None
        proxy._last_section_rotation = 0.0
        proxy._last_valid_length = None
        return proxy

    def hollow_face(self, geometry):
        """Adapt pure area to the established member stub; OCC is tested separately."""
        from tests.test_member_placement import Face, Vector, Wire
        points = (
            Vector(geometry.bounds.min_x, geometry.bounds.min_y, 0),
            Vector(geometry.bounds.max_x, geometry.bounds.min_y, 0),
            Vector(geometry.bounds.max_x, geometry.bounds.max_y, 0),
            Vector(geometry.bounds.min_x, geometry.bounds.max_y, 0),
        )
        face = Face(Wire(tuple(
            (points[index], points[(index + 1) % len(points)])
            for index in range(len(points))
        )))
        face.Area = geometry.area
        return face

    def execute(self, obj, proxy):
        old_get = self.member.profile_catalog.get
        old_face = self.member.section_geometry_to_face
        self.member.profile_catalog.get = lambda _designation: self.profile
        self.member.section_geometry_to_face = self.hollow_face
        try:
            proxy.execute(obj)
        finally:
            self.member.profile_catalog.get = old_get
            self.member.section_geometry_to_face = old_face

    def object(self, start=(0, 0, 0), end=(3000, 0, 0)):
        from tests.test_member_placement import MemberObject
        obj, proxy = MemberObject(start, end), self.proxy()
        obj.Profile = "RHS fixture"
        return obj, proxy

    def test_member_execute_modes_preserve_axis_rotation_insertion_and_catalog_mass(self):
        from tests.test_member_placement import Quantity, Vector
        results = []
        for mode in ("Detailed", "Simplified"):
            obj, proxy = self.object((100, 200, 300), (3100, 200, 300))
            obj.SectionGeometryMode = mode
            obj.Insertion = "Canto superior direito"
            obj.Rotation = Quantity(37)
            self.execute(obj, proxy)
            results.append(obj)
            self.assertEqual(obj.SectionGeometryMode, mode)
            self.assertAlmostEqual(obj.AdjustedLength, 3000.0)
            self.assertAlmostEqual(obj.TotalMass, 17.25 * 3.0)
            self.assertEqual((obj.StartPoint.x, obj.StartPoint.y, obj.StartPoint.z), (100, 200, 300))
            self.assertEqual((obj.EndPoint.x, obj.EndPoint.y, obj.EndPoint.z), (3100, 200, 300))
            self.assertEqual(obj.Rotation.Value, 37)
            self.assertFalse(obj.Shape.empty)
        self.assertNotAlmostEqual(results[0].Shape.Volume, results[1].Shape.Volume)
        self.assertEqual(
            (results[0].Placement.Base.x, results[0].Placement.Base.y, results[0].Placement.Base.z),
            (100, 200, 300),
        )

    def test_same_member_keeps_technical_properties_through_mode_and_rotation(self):
        from freecad.SteelStructures.profiles.effective_properties import (
            calculate_hollow_profile_properties,
        )
        from tests.test_member_placement import Quantity

        technical = calculate_hollow_profile_properties(self.definition)
        old_profile = self.profile
        self.profile = types.SimpleNamespace(
            definition=technical,
            mass_per_m=technical.physical_properties.mass_per_length_kg_m,
            area_cm2=technical.physical_properties.area_mm2 / 100.0,
            manufacturer="Fixture", family="RHS", source="fixture de teste",
            designation="RHS fixture", category="Tubulares", series="RHS",
        )
        obj, proxy = self.object()
        # These persistent catalog fields are populated during object creation;
        # execute/recompute must preserve them while changing representation.
        obj.MassPerMeter = self.profile.mass_per_m
        obj.CatalogArea = self.profile.area_cm2
        expected = (
            technical.physical_properties.area_mm2,
            *(technical.section_properties[name]
              for name in ("ix", "iy", "wx", "wy", "rx", "ry")),
            technical.physical_properties.mass_per_length_kg_m,
            self.profile.area_cm2,
        )
        observed = []
        try:
            for mode, angle in (
                ("Detailed", 0), ("Simplified", 90), ("Detailed", 180)
            ):
                obj.SectionGeometryMode = mode
                obj.Rotation = Quantity(angle)
                self.execute(obj, proxy)
                observed.append((
                    technical.physical_properties.area_mm2,
                    *(technical.section_properties[name]
                      for name in ("ix", "iy", "wx", "wy", "rx", "ry")),
                    obj.MassPerMeter,
                    obj.CatalogArea,
                ))
        finally:
            self.profile = old_profile
        self.assertEqual(observed, [expected, expected, expected])

    def test_length_limit_and_gap_use_nominal_axis_independently_of_section_mode(self):
        from tests.test_member_placement import Quantity
        lengths = []
        for mode in ("Detailed", "Simplified"):
            obj, proxy = self.object()
            obj.SectionGeometryMode = mode
            obj.EndAdjustmentMode = "Fixed"
            obj.AdjustedEnd = "End"
            obj.FixedReferenceOffset = Quantity(100)
            obj.AdjustmentGap = Quantity(20)
            self.execute(obj, proxy)
            lengths.append(obj.AdjustedLength)
            self.assertAlmostEqual(obj.TotalMass, 17.25 * 2.88)
            self.assertEqual(obj.EffectiveEndPoint.x, 2880)
        self.assertEqual(lengths, [2880, 2880])

    def test_oblique_plane_cut_uses_matching_hollow_shape_area_for_mass(self):
        from tests.test_member_adjustment_reference import Reference
        from tests.test_member_placement import Quantity
        masses = []
        for mode in ("Detailed", "Simplified"):
            obj, proxy = self.object()
            obj.SectionGeometryMode = mode
            obj.EndAdjustmentMode = "Associative"
            obj.AdjustedEnd = "End"
            obj.AdjustmentGeometryMode = "PlaneCut"
            obj.AdjustmentReference = (Reference(
                point=(2800, 0, 0), normal=(1, 1, 0),
            ), ["Face3"])
            obj.AdjustmentGap = Quantity(20)
            self.execute(obj, proxy)
            geometry = build_section_geometry(self.definition, mode)
            equivalent_length = obj.Shape.Volume / geometry.area
            self.assertTrue(obj.Shape.clipped)
            self.assertAlmostEqual(obj.TotalMass, 17.25 * equivalent_length / 1000.0)
            masses.append(obj.TotalMass)
        self.assertTrue(all(mass > 0.0 for mass in masses))

    def test_linked_source_axis_drives_hollow_member_without_owning_section_mode(self):
        from tests.test_member_placement import Vector
        obj, proxy = self.object()
        obj.AxisDefinitionMode = "Linked"
        source = object()
        obj.AxisSource = source
        proxy._syncing_axis_source = False
        old_resolve = self.member.resolve_axis_source
        self.member.resolve_axis_source = lambda value: types.SimpleNamespace(
            start=Vector(10, 20, 30), end=Vector(1010, 2020, 3030),
        ) if value is source else None
        try:
            self.assertTrue(proxy._sync_axis_from_source(obj))
            obj.SectionGeometryMode = "Simplified"
            self.execute(obj, proxy)
        finally:
            self.member.resolve_axis_source = old_resolve
        self.assertIs(obj.AxisSource, source)
        self.assertEqual(obj.SectionGeometryMode, "Simplified")
        self.assertEqual((obj.StartPoint.x, obj.StartPoint.y, obj.StartPoint.z), (10, 20, 30))
        self.assertEqual((obj.EndPoint.x, obj.EndPoint.y, obj.EndPoint.z), (1010, 2020, 3030))
        self.assertAlmostEqual(obj.AdjustedLength, math.sqrt(14_000_000))
        self.assertAlmostEqual(obj.TotalMass, 17.25 * math.sqrt(14.0))

    def test_dual_oblique_plane_cuts_use_matching_area_in_both_modes(self):
        from tests.test_member_adjustment_reference import Reference
        from tests.test_member_placement import Quantity, Vector
        for mode in ("Detailed", "Simplified"):
            obj, proxy = self.object()
            obj.SectionGeometryMode = mode
            obj.StartAdjustmentMode = "Fixed"
            obj.StartAdjustmentGeometryMode = "PlaneCut"
            obj.StartFixedReferenceOffset = Quantity(200)
            obj.StartAdjustmentGap = Quantity(25)
            obj.StartFixedPlaneNormal = Vector(1, 0, 1)
            obj.EndAdjustmentMode = "Associative"
            obj.EndAdjustmentGeometryMode = "PlaneCut"
            obj.EndAdjustmentReference = (Reference(
                point=(2800, 0, 0), normal=(1, 1, 1),
            ), ["Face3"])
            obj.EndAdjustmentGap = Quantity(40)
            self.execute(obj, proxy)
            geometry = build_section_geometry(self.definition, mode)
            equivalent_length = obj.Shape.Volume / geometry.area
            with self.subTest(mode=mode):
                self.assertTrue(obj.Shape.clipped)
                self.assertEqual(obj.AdjustedLength, 2535)
                self.assertGreater(obj.Shape.Volume, 0.0)
                self.assertAlmostEqual(
                    obj.TotalMass, 17.25 * equivalent_length / 1000.0,
                )


if __name__ == "__main__":
    unittest.main()
