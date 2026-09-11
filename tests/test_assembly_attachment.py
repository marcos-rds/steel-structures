"""C4-B exact geometric attachment, identities and legacy isolation."""
from dataclasses import replace
import json
import math
import unittest
from freecad.SteelStructures import profile_catalog
from freecad.SteelStructures.assemblies import MemberFrame, SectionTransform, resolve_member_assembly, plan_regeneration
from freecad.SteelStructures.assemblies.attachment import (
    support, section_at_insertion, section_support, resolve_pair_attachment, dot, section_band_support)
from freecad.SteelStructures.assemblies.serialization import dumps, loads
from freecad.SteelStructures.profiles.geometry import build_section_geometry, ArcSegment2D
from freecad.SteelStructures.assemblies.transforms import transform_section
from tests.assemblies_c4a_fixtures import proof_specs

AXIS = ((0., 0., 0.), (0., 0., 1000.))
FRAME = MemberFrame.from_axis(AXIS, (1., 0., 0.))


def physical_spec(kind="Battens", plane="FaceA"):
    base = proof_specs()[4 if kind in ("Battens", "SpacerPlate") else 5]
    return replace(base, interconnectors=(replace(base.interconnectors[0], kind=kind,
        attachment_plane="InnerFaces" if kind == "SpacerPlate" else plane),))


class SupportTests(unittest.TestCase):
    def test_exact_projection_for_real_families_and_transforms(self):
        for designation in ('U 4" x 8,04', 'L 40 x 4', 'SHS 40x40x1,2', 'RHS 60x40x1,2', 'Barra Chata 50,8x6,35'):
            geometry = build_section_geometry(profile_catalog.get(designation).definition)
            for transform in (SectionTransform(), SectionTransform(37, True), SectionTransform(90)):
                section, _ = transform_section(geometry, transform)
                for angle in (0, .37, 1.8):
                    direction = (math.cos(angle), math.sin(angle))
                    low, high = support(section, direction)
                    samples = [p.x*direction[0]+p.y*direction[1]
                        for path in (section.outer_path,)+section.inner_paths for segment in path.segments
                        for p in (segment.start,)+(segment.sampled_points(2000) if isinstance(segment, ArcSegment2D) else (segment.end,))]
                    self.assertLessEqual(low, min(samples)+1e-10)
                    self.assertGreaterEqual(high, max(samples)-1e-10)
                    self.assertAlmostEqual(low, min(samples), delta=1e-4)
                    self.assertAlmostEqual(high, max(samples), delta=1e-4)

    def test_full_circle_support_and_clockwise_arc(self):
        from freecad.SteelStructures.profiles.solid_sections import build_round_bar
        for transform in (SectionTransform(), SectionTransform(31, True)):
            geometry, _ = transform_section(build_round_bar(d=20), transform)
            self.assertEqual(support(geometry, (3, 4)), (-50., 50.))

    def test_noncentral_insertion_is_transformed_before_projection(self):
        spec = proof_specs()[6]
        spec = replace(spec, components=tuple(replace(c, insertion_reference="outer_corner",
            section_transform=SectionTransform(37, c.section_transform.reflect_x)) for c in spec.components))
        result = resolve_member_assembly(AXIS, FRAME, replace(spec, interconnectors=()))
        for c in result.components:
            section, insertion = section_at_insertion(c)
            low, high = support(section, (1., 0.))
            self.assertEqual(section_support(c, FRAME.u), (low-insertion.x, high-insertion.x))


class AttachmentTests(unittest.TestCase):
    def realize(self, spec):
        return resolve_member_assembly(AXIS, FRAME, spec)

    def test_spacer_centers_physical_band_for_transforms_and_insertions(self):
        spec = physical_spec("SpacerPlate")
        for angle in (0, 37, 90):
            for insertion in ("centroid", "rear_bottom", "rear_top"):
                with self.subTest(angle=angle, insertion=insertion):
                    changed = replace(spec, components=tuple(replace(c,
                        insertion_reference=insertion,
                        section_transform=SectionTransform(angle, c.section_transform.reflect_x))
                        for c in spec.components), interconnectors=(replace(spec.interconnectors[0],
                            insertion_reference="bottom_left", section_transform=SectionTransform(37, True)),))
                    if angle == 90 and insertion != "centroid":
                        # Mirrored rear faces meet only at their transverse edge.
                        with self.assertRaisesRegex(ValueError, "sobreposição transversal"):
                            self.realize(changed)
                        continue
                    result = self.realize(changed)
                    pair = resolve_pair_attachment(AXIS, result.components, ("A", "B"))
                    center = (max(pair.a_n[0], pair.b_n[0])+min(pair.a_n[1], pair.b_n[1]))/2
                    for c in result.interconnectors:
                        position = dot(tuple(x-y for x,y in zip(c.start_global, pair.origin)), pair.n)
                        low, high = section_support(c, pair.n)
                        self.assertAlmostEqual(position+(low+high)/2, center)
                        band = (position+low, position+high)
                        a = section_band_support(result.components[0], pair.origin, pair.d, pair.n, band)[1]
                        b = section_band_support(result.components[1], pair.origin, pair.d, pair.n, band)[0]
                        self.assertAlmostEqual(math.dist(c.start_global, c.end_global), b-a)

    def test_spacer_follows_real_translation(self):
        spec = physical_spec("SpacerPlate")
        original = self.realize(spec)
        moved = self.realize(replace(spec, assembly_insertion="Center", components=tuple(replace(c,
            transverse_translation=(c.transverse_translation[0]+13., c.transverse_translation[1]+29.))
            for c in spec.components)))
        for first, second in zip(original.interconnectors, moved.interconnectors):
            for p, q in ((first.start_global, second.start_global), (first.end_global, second.end_global)):
                self.assertLess(math.dist(q, (p[0]+13., p[1]+29., p[2])), 1e-7)

    def test_spacer_component_reference_change_with_same_geometry(self):
        spec = physical_spec("SpacerPlate")
        original = self.realize(spec)
        changed = replace(spec, assembly_insertion="Center", component_spacing=None,
                          components=tuple(replace(c, insertion_reference="rear_bottom") for c in spec.components))
        trial = self.realize(replace(changed, interconnectors=()))
        corrected = []
        for definition, before, after in zip(changed.components, original.components, trial.components):
            _, old_ref = section_at_insertion(before)
            _, new_ref = section_at_insertion(after)
            corrected.append(replace(definition, transverse_translation=(
                definition.transverse_translation[0]+new_ref.x-old_ref.x,
                definition.transverse_translation[1]+new_ref.y-old_ref.y)))
        result = self.realize(replace(changed, components=tuple(corrected)))
        for before, after in zip(original.interconnectors, result.interconnectors):
            self.assertLess(math.dist(before.start_global, after.start_global), 1e-7)
            self.assertLess(math.dist(before.end_global, after.end_global), 1e-7)

    def test_spacer_rejects_missing_or_zero_transverse_overlap(self):
        from freecad.SteelStructures.assemblies.attachment import PairAttachment
        for band in ((10., 20.), (11., 20.)):
            pair = PairAttachment((0.,0.,0.), FRAME.u, FRAME.v, FRAME.w,
                                  (0.,10.), (50.,60.), (0.,10.), band)
            with self.assertRaisesRegex(ValueError, "sobreposição transversal.*faces internas"):
                pair.spacer_center()

    def test_spacer_partial_overlap_center(self):
        from freecad.SteelStructures.assemblies.attachment import PairAttachment
        pair = PairAttachment((0.,0.,0.), FRAME.u, FRAME.v, FRAME.w,
                              (0.,10.), (50.,60.), (-20.,30.), (10.,50.))
        self.assertEqual(pair.spacer_center(), 20.)

    def test_spacer_length_is_inner_gap_not_axis_distance(self):
        result = self.realize(physical_spec("SpacerPlate"))
        pair = resolve_pair_attachment(AXIS, result.components, ("A", "B"))
        definition = profile_catalog.get('U 4" x 8,04').definition
        # At mid-height the facing surfaces are the webs, not flange tips.
        web = definition.geometry["tw"]-definition.centroid["x"]
        expected = result.spec.component_spacing-2*web
        for c in result.interconnectors:
            self.assertAlmostEqual(math.dist(c.start_global, c.end_global), expected)
            self.assertAlmostEqual(dot(tuple(x-y for x,y in zip(c.start_global,pair.origin)), pair.d), web)
            self.assertAlmostEqual(c.end_global[0], result.components[1].start_global[0]-web)
        self.assertNotAlmostEqual(expected, pair.inner_gap)
        self.assertNotAlmostEqual(expected, result.spec.component_spacing)

    def test_batten_span_covers_outer_extremes(self):
        result = self.realize(physical_spec())
        pair = resolve_pair_attachment(AXIS, result.components, ("A", "B"))
        for c in result.interconnectors:
            self.assertAlmostEqual(math.dist(c.start_global, c.end_global), pair.outer_span)
        self.assertGreater(pair.outer_span, result.spec.component_spacing)

    def test_tangency_both_faces_and_generic_connector_sections(self):
        for kind in ("Battens", "SingleLacing", "DoubleLacing"):
            spec = physical_spec(kind, "Both")
            spec = replace(spec, interconnectors=(replace(spec.interconnectors[0],
                section_transform=SectionTransform(37, True),
                insertion_reference="bottom_left" if kind == "Battens" else "outer_corner"),))
            result = self.realize(spec)
            pair = resolve_pair_attachment(AXIS, result.components, ("A", "B"))
            for c in result.interconnectors:
                position = dot(tuple(x-y for x,y in zip(c.start_global,pair.origin)), pair.n)
                low, high = section_support(c, pair.n)
                face = pair.face_plane(c.attachment_plane)
                self.assertAlmostEqual(position+(low if c.attachment_plane == "FaceA" else high), face)
                if c.attachment_plane == "FaceA":
                    self.assertGreaterEqual(position+low, face-1e-8)
                else:
                    self.assertLessEqual(position+high, face+1e-8)

    def test_lacing_preserves_axis_separation_and_legacy_stations(self):
        old = proof_specs()[5]
        legacy = self.realize(old)
        physical = self.realize(replace(old, interconnectors=(replace(old.interconnectors[0], attachment_plane="FaceB"),)))
        for a,b in zip(legacy.interconnectors, physical.interconnectors):
            self.assertEqual((a.start_global[0],a.end_global[0]), (b.start_global[0],b.end_global[0]))
            self.assertEqual(a.stable_identity, b.stable_identity)
            self.assertNotEqual(a.start_global[1], b.start_global[1])
        self.assertEqual(tuple(s.position for s in legacy.distributions[0][1].stations), (100.,350.,600.,850.))
        self.assertGreater(physical.interconnectors[0].start_global[2], 100.)

    def test_non_coplanar_components_fail_without_changing_spec(self):
        spec = physical_spec()
        spec = replace(spec, components=(spec.components[0], replace(spec.components[1], section_transform=SectionTransform(90))))
        before = dumps(spec)
        with self.assertRaisesRegex(ValueError, "não são coplanares"):
            self.realize(spec)
        self.assertEqual(dumps(spec), before)

    def test_spacer_rejects_closed_gap(self):
        spec = physical_spec("SpacerPlate")
        spec = replace(spec, component_spacing=10., components=tuple(replace(c,
            profile_ref=profile_catalog.ref_for_designation('SHS 40x40x1,2'),
            transverse_translation=(-5. if c.component_key=="A" else 5.,0.)) for c in spec.components))
        with self.assertRaisesRegex(ValueError, "espaço livre"):
            self.realize(spec)

    def test_spacer_requires_inner_faces(self):
        spec = physical_spec("SpacerPlate").interconnectors[0]
        for plane in ("FaceA", "FaceB", "Both", "AxisToAxis"):
            with self.assertRaises(ValueError):
                replace(spec, attachment_plane=plane)

    def test_face_convention_and_inclined_rigid_equivariance(self):
        spec = physical_spec("DoubleLacing", "Both")
        base = self.realize(spec)
        axis = ((10., 20., 30.), (610., 820., 30.))
        frame = MemberFrame.from_axis(axis, (0., 0., 1.))
        inclined = resolve_member_assembly(axis, frame, spec)
        pair = resolve_pair_attachment(axis, inclined.components, ("A", "B"))
        self.assertEqual(pair.n, frame.v)
        for first, second in zip(base.interconnectors, inclined.interconnectors):
            for p,q in ((first.start_global,second.start_global),(first.end_global,second.end_global)):
                expected = tuple(axis[0][i]+p[0]*frame.u[i]+p[1]*frame.v[i]+p[2]*frame.w[i] for i in range(3))
                self.assertLess(math.dist(expected,q),1e-7)

    def test_single_side_swap_preserves_primary_and_both_preserves_survivor(self):
        spec = physical_spec()
        a = self.realize(spec)
        b = self.realize(replace(spec,interconnectors=(replace(spec.interconnectors[0],attachment_plane="FaceB"),)))
        both = self.realize(replace(spec,interconnectors=(replace(spec.interconnectors[0],attachment_plane="Both"),)))
        self.assertFalse(plan_regeneration(b,a).structural)
        self.assertEqual([i.stable_identity for i in a.elements],[i.stable_identity for i in b.elements])
        self.assertTrue(plan_regeneration(both,a).structural)
        plan = plan_regeneration(b,both)
        self.assertTrue(plan.structural)
        self.assertEqual(sum(i.action=="REMOVE_EXISTING" for i in plan.actions),4)
        self.assertTrue(all(i.key[-1]=="SECONDARY" for i in plan.actions if i.action=="REMOVE_EXISTING"))

    def test_c4a_payload_defaults_to_axis_to_axis_and_same_ids(self):
        spec = proof_specs()[5]
        payload = json.loads(dumps(spec))
        payload["spec"]["interconnectors"][0].pop("attachment_plane")
        loaded = loads(json.dumps(payload))
        self.assertEqual(loaded, spec)
        self.assertEqual(self.realize(loaded),self.realize(spec))
        attached = replace(spec,interconnectors=(replace(spec.interconnectors[0],attachment_plane="FaceA"),))
        self.assertEqual(loads(dumps(attached)),attached)
        self.assertFalse(plan_regeneration(self.realize(attached),self.realize(spec)).structural)

    def test_double_angle_spacer_uses_its_own_transformed_geometry(self):
        base = proof_specs()[6]
        connector = physical_spec("SpacerPlate").interconnectors[0]
        result = self.realize(replace(base,interconnectors=(connector,)))
        pair = resolve_pair_attachment(AXIS,result.components,("A","B"))
        self.assertAlmostEqual(math.dist(result.interconnectors[0].start_global,result.interconnectors[0].end_global),pair.inner_gap)

    def test_physical_longitudinal_envelopes_with_zero_and_nonzero_offsets(self):
        from freecad.SteelStructures.assemblies import DistributionSpec
        axis = ((10.,20.,30.), (610.,820.,30.))
        frame = MemberFrame.from_axis(axis, (0.,0.,1.))
        for kind in ("SpacerPlate", "Battens", "SingleLacing", "DoubleLacing"):
            for offsets in ((0.,0.), (70.,130.)):
                for distribution in (DistributionSpec(station_count=4),
                                     DistributionSpec(mode="ByTargetSpacing",station_count=None,target_spacing=300.)):
                    with self.subTest(kind=kind, offsets=offsets, distribution=distribution):
                        spec = physical_spec(kind, "Both")
                        connector = replace(spec.interconnectors[0], start_offset=offsets[0], end_offset=offsets[1],
                            distribution=distribution, section_transform=SectionTransform(37, True),
                            insertion_reference="bottom_left" if kind in ("SpacerPlate","Battens") else "outer_corner")
                        result = resolve_member_assembly(axis, frame, replace(spec, interconnectors=(connector,)))
                        for c in result.interconnectors:
                            section, insertion = section_at_insertion(c)
                            # Independently project actual contour points at both extrusion ends.
                            for segment in section.outer_path.segments:
                                samples = (segment.start,)+(segment.sampled_points(40)
                                    if isinstance(segment, ArcSegment2D) else (segment.end,))
                                for p in samples:
                                    for end in (c.start_global,c.end_global):
                                        physical = tuple(end[i]-axis[0][i]+(p.x-insertion.x)*c.orientation.u[i]+
                                            (p.y-insertion.y)*c.orientation.v[i] for i in range(3))
                                        station = dot(physical, frame.w)
                                        self.assertGreaterEqual(station, offsets[0]-1e-7)
                                        self.assertLessEqual(station, 1000.-offsets[1]+1e-7)
                        if distribution.mode == "ByTargetSpacing":
                            self.assertLessEqual(result.distributions[0][1].effective_spacing, 300.)

    def test_flat_bar_edges_touch_offset_boundaries_and_single_piece_fits(self):
        from freecad.SteelStructures.assemblies import DistributionSpec
        spec = physical_spec()
        for count in (1,4):
            connector = replace(spec.interconnectors[0], start_offset=0.,end_offset=0.,
                                distribution=DistributionSpec(station_count=count))
            result = self.realize(replace(spec,interconnectors=(connector,)))
            bounds = [(c.start_global[2]+section_support(c, FRAME.w)[0],
                       c.end_global[2]+section_support(c, FRAME.w)[1]) for c in result.interconnectors]
            if count == 4:
                self.assertAlmostEqual(bounds[0][0],0.)
                self.assertAlmostEqual(bounds[-1][1],1000.)
            else:
                self.assertAlmostEqual(sum(bounds[0])/2,500.)
        with self.assertRaisesRegex(ValueError,"comprimento útil"):
            resolve_member_assembly(((0.,0.,0.),(0.,0.,20.)), FRAME, replace(spec,interconnectors=(connector,)))

    def test_band_support_handles_rotated_arcs_and_full_width_contact(self):
        spec = physical_spec("SpacerPlate")
        for angle in (0,37,90):
            components = self.realize(replace(spec, interconnectors=(), components=tuple(
                replace(c,section_transform=SectionTransform(angle,c.section_transform.reflect_x))
                for c in spec.components))).components
            for c in components:
                section, insertion = section_at_insertion(c)
                for band in ((-3.175,3.175),(-30.,20.),(-100.,100.)):
                    actual = section_band_support(c,(0.,0.,0.),FRAME.u,FRAME.v,band)
                    samples = []
                    for segment in section.outer_path.segments:
                        points = (segment.start,)+(segment.sampled_points(2000)
                            if isinstance(segment,ArcSegment2D) else tuple(type(segment.start)(
                                segment.start.x+t/2000*(segment.end.x-segment.start.x),
                                segment.start.y+t/2000*(segment.end.y-segment.start.y)) for t in range(2001)))
                        samples.extend(p.x-insertion.x+c.start_global[0] for p in points
                                       if band[0] <= p.y-insertion.y+c.start_global[1] <= band[1])
                    self.assertLessEqual(actual[0],min(samples)+1e-8)
                    self.assertGreaterEqual(actual[1],max(samples)-1e-8)
                    self.assertAlmostEqual(actual[0],min(samples),delta=.06)
                    self.assertAlmostEqual(actual[1],max(samples),delta=.06)


if __name__ == "__main__":
    unittest.main()
