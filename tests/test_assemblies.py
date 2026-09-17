"""Focused C3-A pure contracts and geometry gates; no FreeCAD stubs needed."""
from dataclasses import replace
import json
import math
import unittest

from freecad.SteelStructures import profile_catalog
from freecad.SteelStructures.assemblies import (
    MemberAssemblySpec, AssemblyComponentSpec, MemberFrame, SectionTransform,
    resolve_member_assembly, plan_regeneration)
from freecad.SteelStructures.assemblies.presets import single, spaced_pair, double_angle, double_channel
from freecad.SteelStructures.assemblies.serialization import dumps, loads
from freecad.SteelStructures.assemblies.transforms import transform_section
from freecad.SteelStructures.profiles.geometry import (
    Point2D, ArcSegment2D, build_section_geometry, build_parallel_flange_i_section)
from freecad.SteelStructures.profiles.insertion import section_insertion_references

AXIS = ((10., 20., 30.), (610., 820., 30.))
FRAME = MemberFrame.from_axis(AXIS, (0., 0., 1.))


class AssemblyContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.channel = profile_catalog.ref_for_designation('U 4" x 8,04')
        cls.angle = profile_catalog.ref_for_designation('L 40 x 4')

    def realize(self, spec):
        return resolve_member_assembly(AXIS, FRAME, spec)

    def test_serialization_round_trip_all_presets(self):
        for spec in (single("s", self.channel), double_angle("a", self.angle, 40),
                     double_channel("u", self.channel, 100), spaced_pair("p", self.channel, 300)):
            with self.subTest(spec=spec):
                self.assertEqual(loads(dumps(spec)), spec)
                self.assertEqual(dumps(loads(dumps(spec))), dumps(spec))

    def test_unknown_schema_rejected(self):
        data = json.loads(dumps(single("s", self.channel)))
        for version in (0, 2, True):
            data["schema_version"] = version
            with self.assertRaises(ValueError):
                loads(json.dumps(data))

    def test_single_preserves_axis(self):
        item = self.realize(single("s", self.channel)).components[0]
        self.assertEqual((item.start_global, item.end_global), AXIS)
        self.assertEqual(item.section_transform, SectionTransform())

    def test_logical_run_bridge_preserves_c1_c2_frame_and_topology(self):
        from freecad.SteelStructures.trusses.realization import build_candidate
        from freecad.SteelStructures.trusses.models import RegenerationPlan
        from freecad.SteelStructures.assemblies.resolver import resolve_logical_member
        from tests.test_truss_qa import config
        from dataclasses import asdict
        candidate = build_candidate(config())
        before = asdict(candidate)
        item = next(i for i in candidate.items if i.role == "DIAGONAL")
        result = resolve_logical_member(item, double_angle(item.key+"_ASM", self.angle, 40))
        self.assertEqual(result.member_frame.u, item.section_u_global)
        self.assertEqual(result.member_frame.u, (0., 0., -1.))
        self.assertEqual(asdict(candidate), before)
        self.assertIsInstance(plan_regeneration(result), RegenerationPlan)

    def test_center_is_nominal_origin_not_bounding_box_recentering(self):
        spec = single("s", self.channel, transverse_translation=(20, 30))
        item = self.realize(spec).components[0]
        expected = tuple(AXIS[0][i]+20*FRAME.u[i]+30*FRAME.v[i] for i in range(3))
        self.assertEqual(item.start_global, expected)

    def test_symmetric_pair_preserves_midpoint_length_parallelism(self):
        result = self.realize(spaced_pair("p", self.channel, 120))
        a, b = result.components
        for i in range(3):
            self.assertAlmostEqual((a.start_global[i]+b.start_global[i])/2, AXIS[0][i])
        self.assertAlmostEqual(math.dist(a.start_global, b.start_global), 120)
        for c in result.components:
            self.assertAlmostEqual(math.dist(c.start_global, c.end_global), 1000)
            self.assertEqual(tuple(y-x for x, y in zip(c.start_global, c.end_global)), (600, 800, 0))

    def test_inclined_plane_shift_uses_u_and_v(self):
        axis = ((0, 0, 0), (100, 100, 100))
        frame = MemberFrame.from_axis(axis, (1, -1, 0))
        result = resolve_member_assembly(axis, frame, single("s", self.angle, transverse_translation=(17, 29)))
        shift = result.components[0].start_global
        self.assertAlmostEqual(sum(a*b for a, b in zip(shift, frame.w)), 0)
        self.assertAlmostEqual(sum(a*b for a, b in zip(shift, frame.u)), 17)
        self.assertAlmostEqual(sum(a*b for a, b in zip(shift, frame.v)), 29)

    def test_invalid_frames_and_axes(self):
        for axis, u in ((((0, 0, 0), (0, 0, 0)), (1, 0, 0)),
                        (((0, 0, 0), (0, 0, 10)), (1, 0, 1))):
            with self.assertRaises(ValueError):
                MemberFrame.from_axis(axis, u)
        with self.assertRaises(ValueError):
            MemberFrame((1, 0, 0), (0, 1, 0), (0, 0, -1))
        with self.assertRaises(ValueError):
            resolve_member_assembly(AXIS[::-1], FRAME, single("s", self.channel))

    def test_invalid_specs_rejected(self):
        spec = spaced_pair("p", self.channel, 100)
        for changes in (dict(components=()), dict(components=(spec.components[0],)*2),
                        dict(behavior_mode="Single"), dict(component_spacing=99),
                        dict(component_spacing=float("nan")), dict(interconnectors=({"lacing": 1},)),
                        dict(assembly_insertion="NearSide"), dict(assembly_key=""),
                        dict(components=(replace(spec.components[0], transverse_translation=(10, 0)), spec.components[1]))):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                replace(spec, **changes)

    def test_invalid_component_numbers(self):
        base = single("s", self.channel)
        for changes in (dict(transverse_translation=(math.inf, 0)), dict(color=(1, -1, 0)),
                        dict(component_key=""), dict(transverse_translation=(True, 0))):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                replace(base, components=(replace(base.components[0], **changes),))

    def test_identity_independent_of_order_coordinates_profile_transform(self):
        spec = spaced_pair("p", self.channel, 100)
        first = self.realize(spec)
        next_spec = spaced_pair("p", self.angle, 200, (SectionTransform(90), SectionTransform(270, True)))
        second = self.realize(replace(next_spec, components=next_spec.components[::-1]))
        plan = plan_regeneration(second, first, {("p", "A"): "PhysicalA", ("p", "B"): "PhysicalB"})
        self.assertFalse(plan.structural)
        self.assertEqual([a.action for a in plan.actions], ["UPDATE_EXISTING"]*2)
        self.assertEqual([a.existing_binding for a in plan.actions], ["PhysicalA", "PhysicalB"])

    def test_single_double_transitions_are_structural_and_reuse_a(self):
        one = self.realize(single("p", self.channel))
        two = self.realize(spaced_pair("p", self.channel, 100))
        for before, after, action in ((one, two, "CREATE_NEW"), (two, one, "REMOVE_EXISTING")):
            plan = plan_regeneration(after, before)
            self.assertTrue(plan.structural)
            self.assertEqual([a.action for a in plan.actions], ["UPDATE_EXISTING", action])

    def test_conflict_and_unchanged_protocol(self):
        result = self.realize(single("p", self.channel))
        self.assertEqual(plan_regeneration(result, result).actions[0].action, "UNCHANGED")
        self.assertEqual(len(plan_regeneration(result, result, conflicts={("p", "A"): "manual"}).conflicts), 1)

    def test_identity_has_no_delimiter_collision(self):
        a = MemberAssemblySpec("x/y", "Single", "Center", (AssemblyComponentSpec("z", self.channel),))
        b = MemberAssemblySpec("x", "Single", "Center", (AssemblyComponentSpec("y/z", self.channel),))
        self.assertNotEqual(self.realize(a).components[0].stable_identity, self.realize(b).components[0].stable_identity)

    def test_real_catalog_double_angle_symmetry(self):
        geometry = build_section_geometry(profile_catalog.get('L 40 x 4').definition)
        a, b = double_angle("L", self.angle, 40).components
        self.assertEqual(a.section_transform.determinant, -1)
        for segment in geometry.outer_path.segments:
            pa, pb = a.section_transform.point(segment.start), b.section_transform.point(segment.start)
            self.assertEqual((pa.x, pa.y), (-pb.x, pb.y))

    def test_double_channel_mouths_are_opposed_and_arrangements_differ(self):
        outward = double_channel("U", self.channel, 100, "outward")
        inward = double_channel("U", self.channel, 100, "inward")
        self.assertEqual([c.section_transform.point(Point2D(1, 0)).x for c in outward.components], [-1, 1])
        self.assertEqual([c.section_transform.point(Point2D(1, 0)).x for c in inward.components], [1, -1])


class SectionTransformTests(unittest.TestCase):
    def test_quarter_turns_and_reflection_semantics(self):
        for angle, expected in ((0, (2, 3)), (90, (-3, 2)), (180, (-2, -3)), (270, (3, -2))):
            result = SectionTransform(angle).point(Point2D(2, 3))
            self.assertAlmostEqual(result.x, expected[0])
            self.assertAlmostEqual(result.y, expected[1])
            self.assertEqual(SectionTransform(angle).determinant, 1)
        self.assertEqual(SectionTransform(90, True).point(Point2D(2, 3)), Point2D(-3, -2))

    def test_invalid_transform(self):
        for angle, mirror in ((math.nan, False), (True, False), (0, 1)):
            with self.assertRaises(ValueError):
                SectionTransform(angle, mirror)

    def test_paths_arcs_insertion_and_origin_all_transform_together(self):
        for name in ('U 4" x 8,04', 'L 40 x 4'):
            geometry = build_section_geometry(profile_catalog.get(name).definition)
            for rotation in (0, 90, 180, 270, 37):
                for reflected in (False, True):
                    transform = SectionTransform(rotation, reflected)
                    changed, refs = transform_section(geometry, transform)
                    self.assertAlmostEqual(changed.area, geometry.area, places=6)
                    self.assertAlmostEqual(changed.outer_path.signed_area, geometry.outer_path.signed_area, places=6)
                    self.assertEqual(changed.origin, transform.point(geometry.origin))
                    for old, new in zip(section_insertion_references(geometry), refs):
                        if old.id == "envelope_center":
                            self.assertEqual(new.id, old.id)
                            self.assertAlmostEqual(new.point.x,(changed.bounds.min_x+changed.bounds.max_x)/2.)
                            self.assertAlmostEqual(new.point.y,(changed.bounds.min_y+changed.bounds.max_y)/2.)
                            continue
                        self.assertEqual(new.point, transform.point(old.point))
                        self.assertEqual(new.id, old.id)
                        # T(point - insertion) == T(point) - T(insertion)
                        p = geometry.outer_path.segments[0].start
                        relative = transform.point(Point2D(p.x-old.point.x, p.y-old.point.y))
                        absolute = transform.point(p)
                        self.assertAlmostEqual(relative.x, absolute.x-new.point.x)
                        self.assertAlmostEqual(relative.y, absolute.y-new.point.y)

    def test_holes_and_full_circle_arcs_preserve_winding(self):
        from freecad.SteelStructures.profiles.geometry import SectionPath2D
        outer = build_parallel_flange_i_section(d=100, bf=100, tw=90, tf=40)
        p, center = Point2D(5, 0), Point2D(0, 0)
        hole = SectionPath2D((ArcSegment2D(p, p, center),), True)
        original = replace(outer, inner_paths=(hole,))
        changed, _ = transform_section(original, SectionTransform(37, True))
        self.assertAlmostEqual(changed.area, original.area)
        self.assertAlmostEqual(changed.inner_paths[0].signed_area, hole.signed_area)
        self.assertAlmostEqual(changed.inner_paths[0].segments[0].radius, 5)


if __name__ == "__main__":
    unittest.main()
