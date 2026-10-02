"""C6-Q: presentation consumes the physical solution without changing it."""

from dataclasses import asdict, replace
from types import SimpleNamespace
import unittest

from freecad.SteelStructures import profile_catalog
from freecad.SteelStructures.trusses.assemblies import configure_assembly
from freecad.SteelStructures.trusses.connections import connection_participants
from freecad.SteelStructures.trusses.gusset_attachment import attachment_slot_geometry
from freecad.SteelStructures.trusses.gusset_presentation import (
    fit_transverse_bounds, transverse_views,
)
from freecad.SteelStructures.trusses.gussets import preliminary_gusset_outlines
from freecad.SteelStructures.trusses.realization import build_candidate, reference_frame
from tests.test_connections_c5b_polish import three_web_config
from tests.test_gusset_plate_c6a import configured
from tests.test_ridge_fitting import ridge_config
from tests.test_truss_manual_fixes import definition


def preview_config(designation='U 4" x 8,04', assembly=None, rotation=0., spacing=80.):
    value, node = three_web_config()
    role = value["role_specs"]["BOTTOM_CHORD"]
    role.update(profile_ref=asdict(profile_catalog.ref_for_designation(designation)),
                rotation=rotation, section_geometry_mode="Detailed")
    if assembly:
        value["role_specs"]["BOTTOM_CHORD"] = configure_assembly(role, assembly, spacing)
    return configured(value, node, chord_contact="TrussInterior"), node


def resolved_preview(value, node):
    candidate = build_candidate(value)
    views = {}
    outlines, diagnostics = preliminary_gusset_outlines(candidate, transverse_previews=views)
    outline = next(item for item in outlines if item.spec.node_key == node)
    if diagnostics:
        raise AssertionError([item.message for item in diagnostics])
    return candidate, outline, views[node]


class TransverseGeometryTests(unittest.TestCase):
    def test_uniform_fit_preserves_scale_centers_and_inverts_y(self):
        view = fit_transverse_bounds((-20., -10., 80., 40.), 224., 124.)
        self.assertEqual(view.scale, 2.)
        self.assertEqual(view.point((-20., -10.)), (12., 112.))
        self.assertEqual(view.point((80., 40.)), (212., 12.))
        self.assertEqual(view.point((30., 15.)), (112., 62.))
        smaller = fit_transverse_bounds((-20., -10., 80., 40.), 124., 224.)
        self.assertEqual(smaller.scale, 1.)

    def test_unusable_bounds_do_not_invent_scale(self):
        for bounds, width, height in (
                (None, 200., 200.), ((0., 0., 0., 0.), 200., 200.),
                ((0., 0., 10., float("nan")), 200., 200.),
                ((0., 0., 10., 10.), 0., 10.)):
            self.assertIsNone(fit_transverse_bounds(bounds, width, height))

    def test_supported_profiles_reuse_material_including_holes_and_components(self):
        for designation, assembly, rotation, count in (
                ('U 4" x 8,04', None, 0., 1),
                ("Ue 150 × 60 × 20 × 3,00", None, 90., 1),
                ("L 40 x 4", "DoubleAngle", 0., 2),
                ('U 4" x 8,04', "DoubleChannelInward", 0., 2),
                ('U 4" x 8,04', "DoubleChannelOutward", 0., 2),
                ("L 40 x 4", "SpacedPair", 0., 2),
                ("SHS 40x40x1,2", None, 0., 1),
                ("RHS 60x40x1,2", None, 0., 1),
                ("W 150 x 13,0", None, 0., 1)):
            with self.subTest(profile=designation, assembly=assembly):
                value, node = preview_config(designation, assembly, rotation)
                candidate, outline, views = resolved_preview(value, node)
                self.assertEqual(len(views), 1)
                view = views[0]
                self.assertFalse(view.message)
                self.assertEqual(len(view.components), count)
                participants = connection_participants(candidate, node)
                _, materials, _ = attachment_slot_geometry(
                    candidate, participants, reference_frame(candidate.config))
                materials = [m for m in materials if m.participant_key == view.participant_key]
                for actual, expected in zip(view.components, materials):
                    self.assertEqual(actual.outer, expected.outer)
                    self.assertEqual(actual.holes, expected.holes)
                if designation.startswith(("SHS", "RHS")):
                    self.assertEqual(len(view.components[0].holes), 1)
                self.assertEqual(view.plate[0][0], outline.attachment.plate_low)
                self.assertEqual(view.plate[1][0], outline.attachment.plate_high)

    def test_optional_presentation_does_not_change_outline_or_diagnostics(self):
        value, node = preview_config()
        candidate, _, _ = resolved_preview(value, node)
        before = preliminary_gusset_outlines(candidate)
        collected = {}
        after = preliminary_gusset_outlines(candidate, transverse_previews=collected)
        self.assertEqual(before, after)
        self.assertIn(node, collected)

    def test_reused_collection_discards_previous_nodes_on_invalid_update(self):
        value, node = preview_config()
        candidate, _, _ = resolved_preview(value, node)
        collected = {}
        preliminary_gusset_outlines(candidate, transverse_previews=collected)
        self.assertIn(node, collected)
        value["connection_intents"][node]["gusset"]["plate_thickness"] = 0.
        outlines, diagnostics = preliminary_gusset_outlines(
            build_candidate(value), transverse_previews=collected)
        self.assertFalse(outlines)
        self.assertTrue(diagnostics)
        self.assertEqual(collected, {})

    def test_opposite_component_axes_are_aligned_without_changing_material(self):
        value, node = preview_config("L 40 x 4", "DoubleAngle")
        candidate, outline, expected = resolved_preview(value, node)
        participants = connection_participants(candidate, node)
        _, materials, _ = attachment_slot_geometry(
            candidate, participants, reference_frame(candidate.config))
        target = next(m for m in materials if m.participant_key == expected[0].participant_key)
        mirrored = replace(target, local_axis=tuple(-v for v in target.local_axis),
                           outer=tuple((x, -y) for x, y in target.outer),
                           holes=tuple(tuple((x, -y) for x, y in loop) for loop in target.holes))
        # Append the same physical component observed with an opposite axis.
        actual = transverse_views(outline, participants, materials+(mirrored,))
        self.assertEqual(actual, expected)

    def test_every_available_position_uses_resolved_slab_and_final_contour(self):
        value, node = preview_config("L 40 x 4", "DoubleAngle")
        _, initial, _ = resolved_preview(value, node)
        for choice in initial.attachment.candidates:
            with self.subTest(placement=choice.stable_key):
                value["connection_intents"][node]["gusset"]["transverse_placement"] = choice.stable_key
                candidate, outline, views = resolved_preview(value, node)
                view = views[0]
                self.assertEqual((view.plate[0][0], view.plate[1][0]),
                                 (outline.attachment.plate_low, outline.attachment.plate_high))
                _, materials, _ = attachment_slot_geometry(
                    candidate, connection_participants(candidate, node),
                    reference_frame(candidate.config))
                axis = next(m.local_axis for m in materials
                            if m.participant_key == view.participant_key)
                frame = outline.spec.frame
                heights = [sum(axis[i]*(x*frame.x_axis[i]+y*frame.y_axis[i])
                               for i in range(3)) for x, y in outline.points]
                self.assertEqual((view.plate[0][1], view.plate[2][1]),
                                 (min(heights), max(heights)))

    def test_thickness_rotation_insertion_and_spacing_are_refreshed(self):
        value, node = preview_config('U 4" x 8,04', "DoubleChannelInward")
        _, first, initial = resolved_preview(value, node)
        value["connection_intents"][node]["gusset"]["plate_thickness"] = 12.
        _, changed, views = resolved_preview(value, node)
        self.assertAlmostEqual(views[0].plate[1][0]-views[0].plate[0][0], 12.)
        self.assertNotEqual(first.attachment.plate_high, changed.attachment.plate_high)
        wider, _ = preview_config('U 4" x 8,04', "DoubleChannelInward", spacing=130.)
        _, _, spaced = resolved_preview(wider, node)
        self.assertNotEqual(initial[0].components, spaced[0].components)
        rotated, _ = preview_config('U 4" x 8,04', rotation=90.)
        _, _, rotated_views = resolved_preview(rotated, node)
        original, _ = preview_config()
        _, _, original_views = resolved_preview(original, node)
        self.assertNotEqual(original_views[0].components, rotated_views[0].components)
        original["role_specs"]["BOTTOM_CHORD"]["insertion"] = "web_center"
        _, _, inserted = resolved_preview(original, node)
        self.assertNotEqual(original_views[0].components, inserted[0].components)

    def test_global_translation_and_inclination_preserve_section(self):
        value, node = preview_config()
        _, _, initial = resolved_preview(value, node)
        value.update(start=[20., 30., 40.], end=[2420., 30., 40.],
                     plane_normal=[0., -.6, .8])
        _, _, transformed = resolved_preview(value, node)
        for first, second in zip(initial[0].components[0].outer,
                                 transformed[0].components[0].outer):
            for a, b in zip(first, second):
                self.assertAlmostEqual(a, b, places=6)

    def test_multiple_chords_have_independent_views(self):
        value = configured(ridge_config(), "T_S_APEX", chord_contact="TrussInterior")
        _, _, views = resolved_preview(value, "T_S_APEX")
        self.assertEqual(len(views), 2)
        self.assertEqual(len({view.label for view in views}), 2)
        self.assertTrue(all(view.components and view.plate for view in views))

    def test_missing_material_fallback_and_incompatible_axes_are_explicit(self):
        value, node = preview_config()
        candidate, outline, _ = resolved_preview(value, node)
        participants = connection_participants(candidate, node)
        _, materials, _ = attachment_slot_geometry(
            candidate, participants, reference_frame(candidate.config))
        missing = transverse_views(outline, participants, ())
        fallback = transverse_views(replace(outline, attachment=replace(
            outline.attachment, kind="NominalFallback")), participants, materials)
        chord_material = next(m for m in materials if m.participant_key == missing[0].participant_key)
        conflicting = tuple(replace(m, local_axis=(0., 0., 0.))
                            if m.participant_key == chord_material.participant_key else m
                            for m in materials)
        incompatible = transverse_views(outline, participants, conflicting)
        for result in (missing, fallback, incompatible):
            self.assertTrue(result[0].message)
            self.assertFalse(result[0].plate)
            self.assertIsNone(result[0].bounds)

    def test_contact_diagnostics_survive_presentation_unchanged(self):
        value, node = preview_config()
        candidate, outline, views = resolved_preview(value, node)
        self.assertTrue(views[0].plate)
        self.assertTrue(outline.attachment.residuals)
        original = preliminary_gusset_outlines(candidate)[0][0]
        self.assertEqual(original.attachment.residuals, outline.attachment.residuals)
        self.assertEqual(original.attachment.diagnostics, outline.attachment.diagnostics)


class TransverseSelectionTests(unittest.TestCase):
    def setUp(self):
        cls = definition("interactive/truss_topology_editor.py", "TopologyEditor", dict(
            QtWidgets=SimpleNamespace(QDialog=object),
            __package__="freecad.SteelStructures.interactive"))
        self.editor = object.__new__(cls)
        self.calls = []
        self.editor.transverse_preview = SimpleNamespace(set_preview=lambda *args, **kw:
                                                        self.calls.append((args, kw)))
        self.editor.canvas = SimpleNamespace(_last_model={
            "connections": [dict(node_key="N", form="Gusset"),
                            dict(node_key="M", form="Gusset"),
                            dict(node_key="D", form="Direct")],
            "transverse_previews": {"N": ("first",), "M": ("second",)},
            "gussets": [dict(node_key="N", transverse_placement="a",
                             resolved_transverse_placement="a",
                             transverse_regions=(("external", "Externa", (("a", "Lado A"),)),))],
            "connection_diagnostics_by_node": {"M": ("Warning of another node",)},
        })

    def test_selection_switch_uses_only_selected_node_and_no_resolve(self):
        for node, expected in (("N", "first"), ("M", "second")):
            self.editor._connection_node = node
            self.editor._refresh_transverse_preview()
            self.assertEqual(self.calls[-1][0][0], (expected,))
        self.assertEqual(self.calls[0][0][1], "Externa · Lado A")
        self.assertNotIn("Warning", self.calls[-1][0][1])

    def test_none_direct_and_invalid_do_not_reuse_old_outline(self):
        self.editor.canvas._last_model["connections"].append(dict(node_key="X", form="Gusset"))
        for node in (None, "D", "X"):
            self.editor._connection_node = node
            self.editor._refresh_transverse_preview()
            self.assertFalse(self.calls[-1][0])
        self.assertIn("indisponível", self.calls[-1][1]["caption"])

    def test_config_refresh_replaces_transverse_data_with_unchanged_graph(self):
        self.editor._connection_node = "N"
        self.editor._refresh_transverse_preview()
        self.editor.canvas._last_model["transverse_previews"]["N"] = ("new section",)
        self.editor._refresh_transverse_preview()
        self.assertEqual(self.calls[-1][0][0], ("new section",))


if __name__ == "__main__":
    unittest.main()
