"""Focused pure/integration coverage for preliminary C6-A gusset plates."""

import json
import math
import unittest
from dataclasses import FrozenInstanceError, asdict, replace

from freecad.SteelStructures import profile_catalog
from freecad.SteelStructures.connections import (
    ConnectionIntent, GussetCorridor, GussetFitSpec, GussetPlateFrame,
    GussetPlateSpec, GussetSide, build_gusset_outline, extrusion_limits,
    loads,
)
from freecad.SteelStructures.trusses.assemblies import configure_assembly
from freecad.SteelStructures.trusses.connections import connection_participants
from freecad.SteelStructures.trusses.gussets import preliminary_gusset_outlines
from freecad.SteelStructures.trusses.realization import build_candidate
from tests.test_connections_c5b_polish import three_web_config
from tests.test_connections_c5b_through import k_config
from tests.test_ridge_fitting import ridge_config
from tests.test_truss_assemblies import config


FRAME = GussetPlateFrame((0., 0., 0.), (1., 0., 0.), (0., 1., 0.), (0., 0., 1.))


def spec(**changes):
    values = dict(stable_key="N:gusset-plate", node_key="N", plate_thickness=8.,
                  participant_keys=("P1", "P2"), component_keys=("C1", "C2"), frame=FRAME)
    values.update(changes)
    return GussetPlateSpec(**values)


def corridors(count=2):
    values = [GussetCorridor("P1", "C1", (1., 0.), -10., 10.),
              GussetCorridor("P2", "C2", (0., 1.), -12., 12.),
              GussetCorridor("P3", "C3", (-1., -.5), -8., 8.)]
    return tuple(values[:count])


def configured(value, node, **gusset):
    fields = dict(plate_thickness=8., normal_clearance=2., axial_clearance=20.,
                  edge_margin=25., member_overlap=150., side="Center")
    fields.update(gusset)
    value["connection_intents"] = {node: dict(form="Gusset", gusset=fields)}
    return value


class GussetContractTests(unittest.TestCase):
    def test_immutable_versioned_defaults_and_stable_key(self):
        value = GussetFitSpec(8., 2., 20.)
        self.assertEqual((value.edge_margin, value.member_overlap, value.side),
                         (25., 150., GussetSide.CENTER))
        plate = spec()
        self.assertEqual((plate.schema_version, plate.stable_key), (3, "N:gusset-plate"))
        with self.assertRaises(FrozenInstanceError):
            plate.node_key = "changed"
        self.assertEqual(build_gusset_outline(plate, corridors()),
                         build_gusset_outline(plate, tuple(reversed(corridors()))))

    def test_connection_intent_v1_migrates_without_changing_c5b_values(self):
        legacy = dict(intent_key="I", node_key="N", form="Gusset",
                      fastening="Bolted", direct_policy="Independent",
                      participant_run_keys=[], priority_member="Automatic",
                      priority_run_key="", schema_version=1,
                      gusset=dict(plate_thickness=9., normal_clearance=3.,
                                  axial_clearance=21., side="FaceA"))
        restored = loads(json.dumps(legacy))
        self.assertEqual(restored.schema_version, 4)
        self.assertEqual((restored.gusset.plate_thickness, restored.gusset.normal_clearance,
                          restored.gusset.axial_clearance), (9., 3., 21.))
        self.assertEqual((restored.gusset.edge_margin, restored.gusset.member_overlap),
                         (25., 150.))
        from freecad.SteelStructures.trusses.connections import intent_from_data
        with self.assertRaisesRegex(ValueError, "não suportada"):
            intent_from_data("N", {"schema_version": 99})

    def test_two_three_participants_margin_overlap_and_real_coverage(self):
        base = build_gusset_outline(spec(edge_margin=0.), corridors())
        margin = build_gusset_outline(spec(edge_margin=25.), corridors())
        longer = build_gusset_outline(spec(edge_margin=0., member_overlap=300.), corridors(3))
        self.assertGreater(base.area, 0.)
        self.assertGreater(margin.area, base.area)
        self.assertGreater(longer.area, base.area)
        # Every un-margined corridor support corner lies in/on the CCW outline.
        for corridor in corridors():
            dx, dy = corridor.direction
            length = math.hypot(dx, dy); dx, dy = dx/length, dy/length
            px, py = -dy, dx
            for station in (0., base.spec.member_overlap):
                for transverse in (corridor.transverse_low, corridor.transverse_high):
                    point = (station*dx+transverse*px, station*dy+transverse*py)
                    self.assertTrue(all((b[0]-a[0])*(point[1]-a[1])-
                                        (b[1]-a[1])*(point[0]-a[0]) >= -1e-6
                                        for a, b in zip(base.points,
                                                        base.points[1:]+base.points[:1])))

    def test_center_face_a_face_b_have_exact_thickness_and_orientation(self):
        self.assertEqual(extrusion_limits(spec(side=GussetSide.CENTER)), (-4., 4.))
        self.assertEqual(extrusion_limits(spec(side=GussetSide.FACE_A)), (0., 8.))
        self.assertEqual(extrusion_limits(spec(side=GussetSide.FACE_B)), (-8., 0.))

    def test_invalid_inputs_do_not_return_broken_geometry(self):
        cases = (replace(spec(), plate_thickness=0.), replace(spec(), member_overlap=0.),
                 replace(spec(), edge_margin=-1.), replace(spec(), participant_keys=("P1",)))
        for value in cases:
            with self.subTest(value=value), self.assertRaises(ValueError):
                build_gusset_outline(value, corridors())
        with self.assertRaisesRegex(ValueError, "Direção nula"):
            build_gusset_outline(spec(), (corridors()[0], replace(corridors()[1], direction=(0., 0.))))
        bad_frame = replace(FRAME, normal=(0., 0., 2.))
        with self.assertRaisesRegex(ValueError, "ortonormal"):
            build_gusset_outline(spec(frame=bad_frame), corridors())


class GussetCandidateTests(unittest.TestCase):
    def assert_plate(self, value, node):
        candidate = build_candidate(value)
        outlines, diagnostics = preliminary_gusset_outlines(candidate)
        self.assertFalse(diagnostics, [d.message for d in diagnostics])
        self.assertEqual(len(outlines), 1)
        self.assertEqual(outlines[0].spec.node_key, node)
        self.assertGreater(outlines[0].area, 0.)
        return candidate, outlines[0]

    def test_chord_vertical_diagonal_three_participants(self):
        value, node = three_web_config()
        candidate, outline = self.assert_plate(configured(value, node), node)
        participants = connection_participants(candidate, node)
        self.assertGreaterEqual(len(participants), 3)
        self.assertEqual(set(outline.spec.participant_keys),
                         {p.participant_key for p in participants})

    def test_k_through_and_custom_keep_one_semantic_participant(self):
        for custom in (False, True):
            value, node = k_config(custom)
            candidate, outline = self.assert_plate(configured(value, node), node)
            through = next(p for p in connection_participants(candidate, node) if p.end == "Through")
            self.assertIn(through.participant_key, outline.spec.participant_keys)
            self.assertEqual(outline.spec.participant_keys.count(through.participant_key), 1)

    def test_ridge_chord_break_asymmetric_duopitch_and_inclined_plane(self):
        value = ridge_config(.37, 1100., inclined=True)
        node = "T_S_APEX"
        candidate, outline = self.assert_plate(configured(value, node), node)
        ridge = next(p for p in connection_participants(candidate, node) if p.end == "ChordBreak")
        self.assertEqual(len(ridge.physical_run_keys), 2)
        expected = tuple(value["plane_normal"])
        self.assertTrue(all(abs(a-b) < 1e-9 for a, b in zip(outline.spec.frame.normal, expected)))

    def test_rotation_and_insertion_change_physical_outline(self):
        value, node = three_web_config()
        first = self.assert_plate(configured(value, node), node)[1]
        changed, node = three_web_config()
        changed["role_specs"]["DIAGONAL"].update(rotation=37., insertion="outer_corner")
        second = self.assert_plate(configured(changed, node), node)[1]
        self.assertNotEqual(first.points, second.points)

    def test_single_double_angle_double_channel_and_spaced_pair(self):
        cases = ("Single", "DoubleAngle", "DoubleChannelInward", "SpacedPair")
        for mode in cases:
            with self.subTest(mode=mode):
                value, node = three_web_config()
                role = value["role_specs"]["DIAGONAL"]
                if mode == "DoubleChannelInward":
                    role["profile_ref"] = asdict(profile_catalog.ref_for_designation('U 4" x 8,04'))
                if mode != "Single":
                    value["role_specs"]["DIAGONAL"] = configure_assembly(role, mode, 100.)
                _candidate, outline = self.assert_plate(configured(value, node), node)
                diagonal_components = [key for key in outline.spec.component_keys
                                       if key.startswith("DIAGONAL:")]
                self.assertTrue(diagonal_components)
                if mode != "Single":
                    self.assertTrue(any(key.endswith(":B") for key in diagonal_components))

    def test_side_and_dimension_changes_are_live_candidate_inputs(self):
        value, node = three_web_config()
        a = self.assert_plate(configured(value, node, side="FaceA", edge_margin=5.,
                                         member_overlap=100.), node)[1]
        value, node = three_web_config()
        b = self.assert_plate(configured(value, node, side="FaceB", edge_margin=40.,
                                         member_overlap=250.), node)[1]
        self.assertEqual(a.spec.side, GussetSide.FACE_A)
        self.assertEqual(b.spec.side, GussetSide.FACE_B)
        self.assertGreater(b.area, a.area)

    def test_fitting_reservation_uses_same_center_face_a_face_b_semantics(self):
        from freecad.SteelStructures.trusses.connections import (
            _gusset_reserved_interval, resolve_truss_connections)
        expected = {"Center": (-6., 6.), "FaceA": (-2., 10.), "FaceB": (-10., 2.)}
        for side, interval in expected.items():
            value, node = three_web_config()
            candidate = build_candidate(configured(value, node, side=side))
            plane = resolve_truss_connections(candidate, (0., 0., 1.))[0][0].gusset_plane
            self.assertEqual(plane.side.value, side)
            self.assertEqual(_gusset_reserved_interval(plane), interval)

    def test_invalid_plate_is_diagnostic_and_returns_no_outline(self):
        value, node = three_web_config()
        candidate = build_candidate(configured(value, node, plate_thickness=0.))
        outlines, diagnostics = preliminary_gusset_outlines(candidate)
        self.assertFalse(outlines)
        self.assertEqual(diagnostics[-1].code, "GUSSET_PLATE_INVALID")
        self.assertIn("maior que zero", diagnostics[-1].message)

    def test_missing_selected_participant_preserves_semantic_failure(self):
        value, node = three_web_config()
        candidate = build_candidate(value)
        valid = [p.run_key for p in connection_participants(candidate, node)[:2]]
        configured(value, node)
        value["connection_intents"][node]["participant_run_keys"] = valid+["removed-run"]
        outlines, diagnostics = preliminary_gusset_outlines(build_candidate(value))
        self.assertFalse(outlines)
        self.assertEqual(diagnostics[-1].code, "MISSING_PARTICIPANT")


if __name__ == "__main__":
    unittest.main()
