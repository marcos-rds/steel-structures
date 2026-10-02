"""Focused geometric invariants for the C6-C preliminary gusset outline."""

import math
import unittest
from dataclasses import asdict
from types import SimpleNamespace

from freecad.SteelStructures import profile_catalog
from freecad.SteelStructures.connections import (
    GussetCorridor, GussetPlateFrame, GussetPlateSpec, GussetSide,
    GussetSupportLine, build_gusset_outline,
)
from freecad.SteelStructures.trusses.assemblies import configure_assembly
from freecad.SteelStructures.trusses.connections import (
    connection_participants, resolve_truss_connections,
)
from freecad.SteelStructures.trusses.gussets import (
    _chord_support_lines, _corridors, _selected_participants,
    preliminary_gusset_outlines,
)
from freecad.SteelStructures.trusses.realization import (
    build_candidate, reference_frame,
)
from tests.test_connections_c5b_polish import three_web_config
from tests.test_connections_c5b_through import k_config
from tests.test_gusset_plate_c6a import configured
from tests.test_ridge_fitting import ridge_config
from tests.test_truss_assemblies import config
from tests.test_truss_manual_fixes import definition


FRAME = GussetPlateFrame((0., 0., 0.), (1., 0., 0.),
                         (0., 1., 0.), (0., 0., 1.))


def _unit(value):
    length = math.hypot(*value)
    return value[0]/length, value[1]/length


def _inside(points, point, tolerance=1e-6):
    return all((b[0]-a[0])*(point[1]-a[1])-(b[1]-a[1])*(point[0]-a[0])
               >= -tolerance for a, b in zip(points, points[1:]+points[:1]))


def _inputs(value, node, **gusset):
    candidate = build_candidate(configured(value, node, **gusset))
    local_frame = reference_frame(candidate.config)
    resolution = next(item for item in resolve_truss_connections(candidate, local_frame[3])[0]
                      if item.intent.node_key == node)
    participants = _selected_participants(resolution.intent, resolution.participants)
    runs = {run.key: run for run in candidate.runs}
    corridors = tuple(corridor for participant in participants
                      for run_key in participant.physical_run_keys
                      for corridor in _corridors(candidate, participant, runs[run_key], local_frame))
    supports = _chord_support_lines(participants, corridors)
    outlines, diagnostics = preliminary_gusset_outlines(candidate)
    if diagnostics:
        raise AssertionError([value.message for value in diagnostics])
    outline = next(item for item in outlines if item.spec.node_key == node)
    return candidate, participants, corridors, supports, outline


class RegularizationAssertions:
    def assert_regularized(self, outline, corridors, supports):
        allowed = []
        chord_keys = {value.participant_key for value in supports
                      if value.kind == "CHORD_BOUNDARY"}
        for corridor in corridors:
            direction = _unit(corridor.direction)
            allowed.extend((direction, (-direction[1], direction[0])))
            dx, dy = direction
            px, py = -dy, dx
            for transverse in (corridor.transverse_low, corridor.transverse_high):
                if outline.attachment is not None and corridor.participant_key in chord_keys:
                    # The physical contact band trims away the chord material;
                    # its far-side overlap corners no longer belong to plate.
                    continue
                required = (outline.spec.member_overlap*dx+transverse*px,
                            outline.spec.member_overlap*dy+transverse*py)
                if outline.attachment is not None and any(
                        edge.kind == "CHORD_BOUNDARY" and
                        (edge.end[0]-edge.start[0])*(required[1]-edge.start[1])
                        -(edge.end[1]-edge.start[1])*(required[0]-edge.start[0]) < -1e-6
                        for edge in outline.semantic_edges):
                    continue
                self.assertTrue(_inside(outline.points, required), required)
        edges = []
        for first, second in zip(outline.points, outline.points[1:]+outline.points[:1]):
            edge = _unit((second[0]-first[0], second[1]-first[1]))
            edges.append(edge)
            self.assertTrue(any(abs(edge[0]*axis[1]-edge[1]*axis[0]) < 2e-6
                                for axis in allowed), edge)
        self.assertTrue(all(math.hypot(b[0]-a[0], b[1]-a[1]) > 1e-5
                            for a, b in zip(outline.points,
                                            outline.points[1:]+outline.points[:1])))
        for support in supports:
            if outline.attachment is not None and support.kind == "CHORD_BOUNDARY":
                continue
            distances = [support.normal[0]*point[0]+support.normal[1]*point[1]-support.offset
                         for point in outline.points]
            self.assertLessEqual(max(distances), 2e-6)
            self.assertGreaterEqual(sum(abs(value) < 2e-6 for value in distances), 2)


class GussetRegularizationTests(RegularizationAssertions, unittest.TestCase):
    def test_horizontal_chord_caps_external_face_and_margin_remains_free(self):
        spec = GussetPlateSpec("N:gusset-plate", "N", 8., edge_margin=25.,
                               member_overlap=150., participant_keys=("C", "V", "D"),
                               component_keys=("C", "V", "D"), frame=FRAME)
        corridors = (GussetCorridor("C", "C", (1., 0.), -20., 20.),
                     GussetCorridor("V", "V", (0., 1.), -10., 10.),
                     GussetCorridor("D", "D", (1., 1.), -8., 8.))
        support = GussetSupportLine("C", (1., 0.), (0., -1.), 20.)
        outline = build_gusset_outline(spec, corridors, (support,))
        self.assertAlmostEqual(min(point[1] for point in outline.points), -20.)
        self.assert_regularized(outline, corridors, (support,))
        larger = build_gusset_outline(
            GussetPlateSpec(**{**spec.__dict__, "edge_margin": 40.}), corridors, (support,))
        self.assertAlmostEqual(min(point[1] for point in larger.points), -20.)
        self.assertGreater(larger.area, outline.area)

    def test_inclined_chord_uses_rotated_physical_support(self):
        angle = math.radians(31.)
        rotate = lambda value: (value[0]*math.cos(angle)-value[1]*math.sin(angle),
                                value[0]*math.sin(angle)+value[1]*math.cos(angle))
        chord, web = rotate((1., 0.)), rotate((0., 1.))
        corridors = (GussetCorridor("C", "C", chord, -20., 20.),
                     GussetCorridor("W", "W", web, -10., 10.))
        outward = rotate((0., -1.))
        support = GussetSupportLine("C", chord, outward, 20.)
        spec = GussetPlateSpec("N:gusset-plate", "N", 8., participant_keys=("C", "W"),
                               component_keys=("C", "W"), frame=FRAME)
        outline = build_gusset_outline(spec, corridors, (support,))
        self.assert_regularized(outline, corridors, (support,))

    def test_nearly_parallel_participants_do_not_create_spikes(self):
        corridors = (GussetCorridor("A", "A", (1., 0.), -10., 10.),
                     GussetCorridor("B", "B", (1., 1e-5), -10., 10.))
        spec = GussetPlateSpec("N:gusset-plate", "N", 8., participant_keys=("A", "B"),
                               component_keys=("A", "B"), frame=FRAME)
        outline = build_gusset_outline(spec, corridors)
        self.assertLess(max(math.hypot(*point) for point in outline.points), 300.)
        self.assert_regularized(outline, corridors, ())

    def test_ambiguous_chord_side_is_diagnostic_not_arbitrary(self):
        participants = (SimpleNamespace(participant_key="C", role="TOP_CHORD"),
                        SimpleNamespace(participant_key="W", role="VERTICAL"))
        corridors = (GussetCorridor("C", "C", (1., 0.), -20., 20.),
                     GussetCorridor("W", "W1", (0., 1.), -10., 10.),
                     GussetCorridor("W", "W2", (0., -1.), -10., 10.))
        with self.assertRaisesRegex(ValueError, "ambíguo"):
            _chord_support_lines(participants, corridors)


class GussetTrussGeometryTests(RegularizationAssertions, unittest.TestCase):
    def test_pratt_and_warren_chord_edges_govern_outline(self):
        for preset in ("Pratt", "Warren"):
            with self.subTest(preset=preset):
                if preset == "Pratt":
                    value, node = three_web_config(preset)
                else:
                    value = config()
                    value["topology_preset"] = preset
                    candidate = build_candidate(value)
                    node = next(item.key for item in candidate.graph.nodes
                                if len(connection_participants(candidate, item.key)) >= 3
                                and any(p.role in ("TOP_CHORD", "BOTTOM_CHORD")
                                        for p in connection_participants(candidate, item.key))
                                and not any(p.role == "END_POST"
                                            for p in connection_participants(candidate, item.key)))
                _candidate, _participants, corridors, supports, outline = _inputs(value, node)
                self.assertTrue(supports)
                self.assert_regularized(outline, corridors, supports)
                self.assertTrue(any(abs(support.direction[1]) < 1e-8 for support in supports))

    def test_k_keeps_one_through_participant_and_regular_outline(self):
        value, node = k_config()
        candidate, participants, corridors, supports, outline = _inputs(value, node)
        through = [item for item in connection_participants(candidate, node)
                   if item.end == "Through"]
        self.assertEqual(len(through), 1)
        self.assertEqual(outline.spec.participant_keys.count(through[0].participant_key), 1)
        self.assert_regularized(outline, corridors, supports)

    def test_duopitch_symmetric_asymmetric_and_inclined_plane(self):
        horizontal_points = None
        for apex, inclined in ((.5, False), (.37, False), (.37, True)):
            with self.subTest(apex=apex, inclined=inclined):
                value = ridge_config(apex, 1100., inclined=inclined)
                _candidate, _participants, corridors, supports, outline = _inputs(
                    value, "T_S_APEX")
                self.assertEqual(len(supports), 2)
                self.assert_regularized(outline, corridors, supports)
                if apex == .5:
                    mirrored = {(round(-x, 6), round(y, 6)) for x, y in outline.points}
                    self.assertEqual(mirrored,
                                     {(round(x, 6), round(y, 6)) for x, y in outline.points})
                if apex == .37 and not inclined:
                    horizontal_points = outline.points
                if apex == .37 and inclined:
                    self.assertEqual(outline.points, horizontal_points)

    def test_terminal_chord_closure_uses_both_chord_limits(self):
        for node in ("N_S_START", "N_S_END"):
            with self.subTest(node=node):
                value = ridge_config(diagonals=False)
                _candidate, participants, corridors, supports, outline = _inputs(value, node)
                self.assertEqual({item.role for item in participants},
                                 {"TOP_CHORD", "BOTTOM_CHORD"})
                self.assertEqual(len(supports), 2)
                self.assert_regularized(outline, corridors, supports)

    def test_assemblies_rotation_and_insertion_keep_physical_supports(self):
        modes = ("Single", "DoubleAngle", "DoubleChannelInward", "SpacedPair")
        for mode in modes:
            with self.subTest(mode=mode):
                value, node = three_web_config()
                role = value["role_specs"]["DIAGONAL"]
                if mode == "DoubleChannelInward":
                    role["profile_ref"] = asdict(profile_catalog.ref_for_designation('U 4" x 8,04'))
                if mode != "Single":
                    value["role_specs"]["DIAGONAL"] = configure_assembly(role, mode, 100.)
                _candidate, _participants, corridors, supports, outline = _inputs(value, node)
                self.assert_regularized(outline, corridors, supports)
        base, node = three_web_config()
        first = _inputs(base, node)[-1]
        changed, node = three_web_config()
        changed["role_specs"]["BOTTOM_CHORD"].update(
            insertion="envelope_center", rotation=23.)
        second = _inputs(changed, node)[-1]
        self.assertNotEqual(first.points, second.points)

    def test_overlap_changes_2d_shape_but_thickness_and_side_do_not(self):
        value, node = three_web_config()
        base = _inputs(value, node, member_overlap=100., plate_thickness=8., side="Center")[-1]
        value, node = three_web_config()
        long = _inputs(value, node, member_overlap=250., plate_thickness=8., side="Center")[-1]
        self.assertGreater(long.area, base.area)
        value, node = three_web_config()
        other_side = _inputs(value, node, member_overlap=100., plate_thickness=16., side="FaceB")[-1]
        self.assertEqual(other_side.spec.side, GussetSide.FACE_B)
        self.assertEqual(other_side.points, base.points)

    def test_3d_preview_preserves_last_valid_plate_for_same_frame_diagnostic(self):
        class Shape:
            def __init__(self, kind):
                self.kind = kind
            def copy(self):
                return Shape(self.kind)
        class ScenePreview:
            histories = []
            def __init__(self, _graph):
                self.node = object()
            def update(self, shapes, _colors, _compound):
                ScenePreview.histories.append(tuple(shape.kind for shape in shapes))
            def frame(self, _view):
                pass
        view = SimpleNamespace(getSceneGraph=lambda: object())
        controller_type = definition("interactive/truss_controller.py", "TrussController", dict(
            App=SimpleNamespace(Console=SimpleNamespace(PrintWarning=lambda _text: None)),
            Gui=SimpleNamespace(activeDocument=lambda: SimpleNamespace(activeView=lambda: view)),
            resynchronize_accepted_snapshots=lambda _obj: None))
        calls = []
        outline = SimpleNamespace(spec=SimpleNamespace(node_key="N", frame=FRAME))
        diagnostic = SimpleNamespace(node_key="N")
        item = SimpleNamespace(key="M", spec=SimpleNamespace(color=(1., .5, 0.)))
        node = SimpleNamespace(key="N", position_local=(0., 0., 0.))
        graph = SimpleNamespace(nodes=(node,), node=lambda _key: node)
        candidates = {
            "valid": SimpleNamespace(signature="valid", items=(item,), config={}, graph=graph),
            "invalid": SimpleNamespace(signature="invalid", items=(item,), config={}, graph=graph),
        }
        globals_ = controller_type.preview3d.__globals__
        globals_.update(
            dumps=lambda candidate: candidate.signature,
            bound_children=lambda *_args: {}, decode_state=lambda _value: {},
            prepare_batch=lambda candidate, _children: {
                value.key: SimpleNamespace(Shape=Shape("member"), Placement=None)
                for value in candidate.items},
            preliminary_gusset_outlines=lambda _candidate: (
                ((outline,), ()) if not calls else ((), (diagnostic,))),
            build_gusset_shape=lambda _outline: Shape("plate"),
            Part=SimpleNamespace(makeCompound=lambda shapes: tuple(shapes)),
            TrussScenePreview=ScenePreview, perf_counter=lambda: 0.,
            reference_frame=lambda _config: ((0., 0., 0.), (1., 0., 0.),
                                              (0., 1., 0.), (0., 0., 1.)),
            transform_point=lambda point, _frame: point)
        controller = controller_type(SimpleNamespace(Objects=[]))
        controller.candidate = lambda value: candidates[value["state"]]
        controller.preview3d({"state": "valid"})
        calls.append(True)
        controller.preview3d({"state": "invalid"})
        self.assertEqual(ScenePreview.histories, [("member", "plate"),
                                                  ("member", "plate")])


if __name__ == "__main__":
    unittest.main()
