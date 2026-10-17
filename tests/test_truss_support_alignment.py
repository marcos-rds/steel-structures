"""Pure exact-section and rigid-support alignment contracts (no FreeCAD)."""
import copy
import math
import unittest
from dataclasses import asdict
from unittest.mock import patch

from freecad.SteelStructures import profile_catalog
from freecad.SteelStructures.assemblies.transforms import SectionTransform
from freecad.SteelStructures.trusses.assemblies import configure_assembly, expand_run
from freecad.SteelStructures.trusses.fitting_geometry import _section_interval
from freecad.SteelStructures.trusses.models import MemberSpec, RealizationItem
from freecad.SteelStructures.trusses.support_alignment import (
    aligned_frame, resolve_support_alignment, upper_section_offset, _solve_nominal_span)


def fixture(**changes):
    value = dict(envelope_type="DuoPitch", span=6000., height=1200.,
                 apex_position=.5, left_end_height=0., right_end_height=0.,
                 link_end_heights=False, reference_alignment="TopChordSupports",
                 role_specs={"TOP_CHORD": dict(profile_ref=asdict(
                     profile_catalog.ref_for_designation("Barra Chata 50,8x6,35")),
                     insertion="centroid", rotation=0., assembly="Single",
                     section_geometry_mode="Detailed", color=(.4, .5, .6))})
    value.update(changes)
    return value


def transform(point, frame):
    origin, x, y, z = frame
    return tuple(o+point[0]*u+point[1]*v+point[2]*w
                 for o, u, v, w in zip(origin, x, y, z))


class SupportAlignmentTests(unittest.TestCase):
    def test_parallel_uses_constant_height_and_preserves_nominal_span(self):
        value = fixture(envelope_type="Parallel", left_end_height=9000.,
                        right_end_height=-100., apex_position=0.)
        for assembly in ("Single", "SpacedPair", "DoubleChannelOutward"):
            role = value["role_specs"]["TOP_CHORD"]
            role["profile_ref"] = asdict(profile_catalog.ref_for_designation('U 4" x 8,04'))
            value["role_specs"]["TOP_CHORD"] = configure_assembly(role, assembly, 80.)
            for rotation in (0., 23., 90., -90.):
                for insertion in ("centroid", "top", "bottom"):
                    with self.subTest(assembly=assembly, rotation=rotation, insertion=insertion):
                        role = value["role_specs"]["TOP_CHORD"]
                        role.update(rotation=rotation, insertion=insertion)
                        before = copy.deepcopy(value)
                        resolved = resolve_support_alignment(value)
                        offset = upper_section_offset(value)
                        self.assertEqual(resolved["nominal_span"], value["span"])
                        self.assertEqual(resolved["support_reference_local"],
                            ((0., value["height"]+offset, 0.),
                             (value["span"], value["height"]+offset, 0.)))
                        self.assertEqual(value, before)

    def test_parallel_horizontal_inclined_and_reversed_frames(self):
        value = fixture(envelope_type="Parallel")
        resolved = resolve_support_alignment(value)
        for angle in (0., .37, math.pi, math.pi+.37):
            raw = ((100., 200., 300.), (math.cos(angle), math.sin(angle), 0.),
                   (-math.sin(angle), math.cos(angle), 0.), (0., 0., 1.))
            frame = aligned_frame(dict(value, **resolved), raw)
            for q, target in zip(resolved["support_reference_local"],
                    (raw[0], tuple(o+value["span"]*u for o,u in zip(raw[0], raw[1])))):
                self.assertLess(math.dist(transform(q, frame), target), 1e-8)

    def test_parallel_candidate_recomputes_offset_and_bottom_is_legacy_default(self):
        from tests.test_truss_core import config as core_config
        from freecad.SteelStructures.trusses.realization import build_candidate, reference_frame, input_reference_frame
        value = core_config()
        value.update(envelope_type="Parallel", reference_alignment="TopChordSupports")
        value["role_specs"]["TOP_CHORD"] = fixture()["role_specs"]["TOP_CHORD"]
        first = build_candidate(value)
        self.assertEqual(first.config["nominal_span"], value["span"])
        value = copy.deepcopy(first.config)
        value["role_specs"]["TOP_CHORD"]["rotation"] = 37.
        second = build_candidate(value, first)
        self.assertNotEqual(first.config["support_section_offset"], second.config["support_section_offset"])
        value.pop("reference_alignment")
        bottom = build_candidate(value)
        self.assertEqual(bottom.config["reference_alignment"], "BottomChord")
        self.assertNotIn("support_reference_local", bottom.config)
        self.assertEqual(reference_frame(bottom.config), input_reference_frame(bottom.config))

    def test_inferior_keeps_raw_frame_and_does_not_resolve_profile(self):
        value = fixture(reference_alignment="BottomChord", role_specs={})
        raw = ((10., 20., 30.), (1., 0., 0.), (0., 1., 0.), (0., 0., 1.))
        self.assertIs(aligned_frame(value, raw), raw)
        self.assertEqual(resolve_support_alignment(value), {"nominal_span": 6000.})

    def test_physical_bottom_in_both_forms_rotations_insertions_and_compositions(self):
        from tests.test_truss_core import config as core_config
        from freecad.SteelStructures.trusses.realization import build_candidate, reference_frame
        for kind in ("Parallel", "DuoPitch"):
            for assembly in ("Single", "SpacedPair", "DoubleChannelOutward"):
                for rotation in (0., 23., 90., -90.):
                    for insertion in ("centroid", "top", "bottom"):
                        with self.subTest(kind=kind, assembly=assembly, rotation=rotation, insertion=insertion):
                            value = core_config()
                            value.update(envelope_type=kind, reference_alignment="BottomChord",
                                         reference_surface="OuterFace", start=[100., 200., 300.],
                                         end=[3700., 5000., 300.], plane_normal=[0., 0., 1.])
                            role = value["role_specs"]["BOTTOM_CHORD"]
                            role.update(profile_ref=asdict(profile_catalog.ref_for_designation('U 4" x 8,04')),
                                        rotation=rotation, insertion=insertion)
                            value["role_specs"]["BOTTOM_CHORD"] = configure_assembly(role, assembly, 80.)
                            candidate = build_candidate(value)
                            frame = reference_frame(candidate.config)
                            for q, target in zip(candidate.config["support_reference_local"],
                                                 (value["start"], value["end"])):
                                self.assertLess(math.dist(transform(q, frame), target), 1e-7)
                            normal = frame[2]
                            low = min(_section_interval(item, normal)[0] for item in candidate.items
                                      if item.role == "BOTTOM_CHORD")
                            self.assertAlmostEqual(low, sum(a*b for a,b in zip(value["start"],normal)), places=7)

    def test_legacy_candidate_stays_put_and_explicit_face_opt_in_moves_only_global_geometry(self):
        from tests.test_truss_core import config as core_config
        from freecad.SteelStructures.trusses.realization import build_candidate, reference_frame, input_reference_frame
        from freecad.SteelStructures.trusses.serialization import encode_state, decode_state
        value = core_config()
        value["role_specs"]["BOTTOM_CHORD"] = fixture()["role_specs"]["TOP_CHORD"]
        legacy = build_candidate(value)
        restored = build_candidate(decode_state(encode_state(legacy))["candidate"]["config"])
        self.assertEqual(restored.items, legacy.items)
        self.assertEqual(reference_frame(restored.config), input_reference_frame(restored.config))
        physical = build_candidate(dict(restored.config, reference_surface="OuterFace"), restored)
        self.assertEqual(physical.graph, legacy.graph)
        self.assertEqual(physical.runs, legacy.runs)
        self.assertNotEqual(physical.items[0].start_global, legacy.items[0].start_global)
        roundtrip = build_candidate(decode_state(encode_state(physical))["candidate"]["config"])
        self.assertEqual(roundtrip.items, physical.items)

    def test_rectangle_roll_uses_exact_transverse_projection(self):
        value = fixture()
        for angle in (0., 23., 90., 137.):
            value["role_specs"]["TOP_CHORD"]["rotation"] = angle
            expected = 25.4*abs(math.sin(math.radians(angle)))+3.175*abs(math.cos(math.radians(angle)))
            self.assertAlmostEqual(upper_section_offset(value), expected)

    def test_insertion_and_circular_arc_extrema(self):
        value = fixture()
        role = value["role_specs"]["TOP_CHORD"]
        role["insertion"] = "bottom"
        self.assertAlmostEqual(upper_section_offset(value), 6.35)
        role["insertion"] = "top"
        self.assertEqual(upper_section_offset(value), 0.)
        role["profile_ref"] = asdict(profile_catalog.ref_for_designation("CHS 88,90x3"))
        role["insertion"] = "centroid"
        for angle in (0., 23.456, 90., 163.):
            role["rotation"] = angle
            self.assertAlmostEqual(upper_section_offset(value), 44.45)

    def test_composition_translation_transform_and_role_roll(self):
        value = fixture()
        role = configure_assembly(value["role_specs"]["TOP_CHORD"], "SpacedPair", 80.,
                                  transforms=(SectionTransform(90.), SectionTransform()))
        value["role_specs"]["TOP_CHORD"] = role
        self.assertAlmostEqual(upper_section_offset(value), 25.4)
        role["rotation"] = 90.
        self.assertAlmostEqual(upper_section_offset(value), 65.4)

    def test_section_query_ignores_connectors_and_does_not_mutate_spec(self):
        value = fixture()
        role = configure_assembly(value["role_specs"]["TOP_CHORD"], "SpacedPair", 80.)
        # Section query must not instantiate connector distributions. Even a
        # stale connector payload does not change a chord's upper envelope.
        role["assembly_spec"]["spec"]["interconnectors"] = [{"stale": "connector"}]
        value["role_specs"]["TOP_CHORD"] = role
        before = copy.deepcopy(value)
        self.assertAlmostEqual(upper_section_offset(value), 3.175)
        self.assertEqual(value, before)

    def test_zero_equal_and_different_heights_keep_reference_length(self):
        for left, right in ((0., 0.), (400., 400.), (200., 700.)):
            with self.subTest(left=left, right=right):
                value = fixture(left_end_height=left, right_end_height=right)
                before = copy.deepcopy(value)
                result = resolve_support_alignment(value)
                ql, qr = result["support_reference_local"]
                self.assertAlmostEqual(math.dist(ql, qr), value["span"], places=8)
                self.assertLessEqual(result["nominal_span"], value["span"])
                if left == right:
                    self.assertEqual(result["nominal_span"], value["span"])
                else:
                    self.assertLess(result["nominal_span"], value["span"])
                self.assertEqual(value, before)

    def test_linked_heights_ignore_stale_right_value(self):
        linked = resolve_support_alignment(fixture(left_end_height=300., right_end_height=900., link_end_heights=True))
        equal = resolve_support_alignment(fixture(left_end_height=300., right_end_height=300.))
        self.assertEqual(linked, equal)

    def test_horizontal_inclined_reference_and_both_physical_top_planes(self):
        for tilt in (0., .35):
            for apex in (.35, .5, .7):
                value = fixture(left_end_height=200., right_end_height=650., apex_position=apex)
                result = resolve_support_alignment(value)
                angle = tilt
                raw = ((100., 200., 300.), (math.cos(angle), math.sin(angle), 0.),
                       (-math.sin(angle), math.cos(angle), 0.), (0., 0., 1.))
                frame = aligned_frame(dict(value, **result), raw)
                ql, qr = result["support_reference_local"]
                expected = (raw[0], tuple(o+value["span"]*v for o, v in zip(raw[0], raw[1])))
                for point, target in zip((ql, qr), expected):
                    self.assertLess(math.dist(transform(point, frame), target), 1e-8)
                span = result["nominal_span"]
                points = ((0., 200., 0.), (apex*span, 1200., 0.), (span, 650., 0.))
                for index, support in enumerate(expected):
                    a, b = points[index:index+2]
                    item = RealizationItem("PROOF", "TOP_CHORD", "A", "B", a, b,
                                           transform(a, frame), transform(b, frame),
                                           (0., 0., -1.), MemberSpec(**value["role_specs"]["TOP_CHORD"]))
                    w = tuple((y-x)/math.dist(a, b) for x, y in zip(item.start_global, item.end_global))
                    normal = (-w[1], w[0], 0.)
                    top = max(_section_interval(component, normal)[1] for component in expand_run(item))
                    self.assertAlmostEqual(top, sum(x*y for x, y in zip(support, normal)), places=8)

    def test_largest_root_is_selected_when_two_solutions_exist(self):
        span = _solve_nominal_span(1000., 1000., 0., 900., .5, 25.)
        self.assertAlmostEqual(span, 553.4962880665262, places=7)
        self.assertGreater(span, 500.)

    def test_no_solution_and_invalid_envelopes_have_diagnostics(self):
        with self.assertRaisesRegex(ValueError, "compatível|curta"):
            _solve_nominal_span(20., 1000., 0., 900., .5, 25.)
        with self.assertRaisesRegex(ValueError, "positivo"):
            _solve_nominal_span(900., 1000., 0., 900., .5, 0.)
        for changes in (dict(left_end_height=-1.), dict(right_end_height=1200.),
                        dict(apex_position=0.), dict(height=float("nan")),
                        dict(envelope_type="Unsupported"), dict(reference_alignment="Unknown")):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                resolve_support_alignment(fixture(**changes))
        with patch("freecad.SteelStructures.trusses.support_alignment.upper_section_offset", return_value=-1.):
            with self.assertRaisesRegex(ValueError, "abaixo"):
                resolve_support_alignment(fixture())
        with patch("freecad.SteelStructures.trusses.support_alignment.upper_section_offset", return_value=200.):
            with self.assertRaisesRegex(ValueError, "cumeeira"):
                resolve_support_alignment(fixture(span=100.))


if __name__ == "__main__":
    unittest.main()
