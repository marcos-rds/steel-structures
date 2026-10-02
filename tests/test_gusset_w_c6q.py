"""C6-Q: physical auto/manual equivalence and accessible rotated W/I recesses."""

import copy
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from freecad.SteelStructures.connections.slots import material_intervals
from freecad.SteelStructures.trusses.connections import connection_participants
from freecad.SteelStructures.trusses.gusset_attachment import attachment_slot_geometry
from freecad.SteelStructures.trusses.gusset_freecad import build_gusset_shape
from freecad.SteelStructures.trusses.gussets import preliminary_gusset_outlines
from freecad.SteelStructures.trusses.realization import build_candidate, reference_frame
from tests.test_gusset_presentation_c6q import preview_config, resolved_preview
from tests.test_gusset_c6l import fcstd_config, TOP_NODE
from tests.test_gusset_ui_c6m import regions_for


def choice(outline):
    plane = outline.attachment
    return next(c for c in plane.candidates if (c.slot_id, c.placement) ==
                (plane.governing_slot_id, plane.placement_kind))


def physical_extrusion(outline):
    """Capture the production adapter's global wire and extrusion, without OCC."""
    class Face:
        def __init__(self, wire):
            self.wire = tuple(wire)

        def extrude(self, vector):
            return SimpleNamespace(wire=self.wire, vector=vector,
                                   isNull=lambda: False, isValid=lambda: True)

    with patch.dict(sys.modules, {
            "FreeCAD": SimpleNamespace(Vector=lambda *coords: tuple(coords)),
            "Part": SimpleNamespace(makePolygon=tuple, Face=Face)}):
        solid = build_gusset_shape(outline)
    return solid.wire, solid.vector


class AutomaticEquivalenceTests(unittest.TestCase):
    def assert_same_physical_plate(self, automatic, manual):
        self.assertEqual(choice(automatic), choice(manual))
        self.assertEqual(automatic.attachment, manual.attachment)
        self.assertEqual(automatic.points, manual.points)
        self.assertEqual(automatic.semantic_edges, manual.semantic_edges)
        self.assertEqual(automatic.area, manual.area)
        self.assertEqual(physical_extrusion(automatic), physical_extrusion(manual))

    def test_profile_orientation_and_thickness_matrix(self):
        for profile, assembly in (
                ("W 150 x 13,0", None), ('I 3" x 8,48', None),
                ('U 4" x 8,04', None), ("Ue 150 × 60 × 20 × 3,00", None),
                ("L 40 x 4", "DoubleAngle"),
                ('U 4" x 8,04', "DoubleChannelInward"),
                ('U 4" x 8,04', "DoubleChannelOutward"),
                ("L 40 x 4", "SpacedPair"), ("SHS 40x40x1,2", None)):
            for rotation in (0., 90.):
                for thickness in (4., 8., 12.):
                    with self.subTest(profile=profile, assembly=assembly,
                                      rotation=rotation, thickness=thickness):
                        value, node = preview_config(profile, assembly, rotation)
                        spec = value["connection_intents"][node]["gusset"]
                        spec["plate_thickness"] = thickness
                        candidate, automatic, auto_views = resolved_preview(value, node)
                        spec["transverse_placement"] = choice(automatic).stable_key
                        _, manual, manual_views = resolved_preview(value, node)
                        self.assert_same_physical_plate(automatic, manual)
                        self.assertEqual(auto_views, manual_views)
                        selected = choice(automatic)
                        if selected.outline_band != selected.contact_band:
                            participants = connection_participants(candidate, node)
                            _, materials, _ = attachment_slot_geometry(
                                candidate, participants, reference_frame(candidate.config))
                            material = tuple(m for m in materials if m.participant_key ==
                                             selected.governing_participant_key)
                            # The newly included external/lateral extent may
                            # touch the section, never penetrate its material.
                            for fraction in (0., .1, .25, .5, .75, .9, 1.):
                                q = selected.contact_direction*(selected.outline_band+
                                    fraction*(selected.contact_band-selected.outline_band))
                                for a, b in material_intervals(material, q):
                                    self.assertLessEqual(min(b, selected.plate_high)
                                                         -max(a, selected.plate_low), 1e-6)

    def test_all_reference_connection_families(self):
        fixture = json.loads((Path(__file__).parent/
                              "fixtures/gusset_round1.json").read_text(encoding="utf8"))
        families = set()
        for owner, original in fixture["owners"].items():
            value = copy.deepcopy(original)
            for intent in value["connection_intents"].values():
                intent["gusset"]["transverse_placement"] = ""
            automatic, diagnostics = preliminary_gusset_outlines(build_candidate(value))
            self.assertFalse(diagnostics, owner)
            for outline in automatic:
                value["connection_intents"][outline.spec.node_key]["gusset"][
                    "transverse_placement"] = choice(outline).stable_key
            manual, diagnostics = preliminary_gusset_outlines(build_candidate(value))
            self.assertFalse(diagnostics, owner)
            manual = {o.spec.node_key: o for o in manual}
            for outline in automatic:
                with self.subTest(owner=owner, node=outline.spec.node_key):
                    self.assert_same_physical_plate(outline, manual[outline.spec.node_key])
            families.update(case["group"].split("_")[0] for case in fixture["cases"]
                            if case["owner"] == owner)
        self.assertIn("F04", families)
        self.assertIn("F08", families)

    def test_distinct_candidates_keep_distinct_physical_extrusions(self):
        for rotation in (0., 90.):
            value, node = preview_config("W 150 x 13,0", rotation=rotation)
            _, outline, _ = resolved_preview(value, node)
            shapes = []
            for selected in outline.attachment.candidates:
                if selected.accessibility.value != "OuterExposed":
                    continue
                value["connection_intents"][node]["gusset"][
                    "transverse_placement"] = selected.stable_key
                _, explicit, _ = resolved_preview(value, node)
                shapes.append(physical_extrusion(explicit))
            self.assertEqual(len(set(shapes)), 2)


class RotatedRecessTests(unittest.TestCase):
    def test_upper_chord_uses_opposite_open_ray(self):
        for profile in ("W 150 x 13,0", 'I 3" x 8,48'):
            source, _node = preview_config(profile, rotation=90.)
            value = fcstd_config(explicit_external=False)
            value["role_specs"]["TOP_CHORD"].update({
                key: source["role_specs"]["BOTTOM_CHORD"][key]
                for key in ("profile_ref", "rotation", "section_geometry_mode")})
            spec = value["connection_intents"][TOP_NODE]["gusset"]
            spec["plate_thickness"] = 8.
            _, outline, _ = resolved_preview(value, TOP_NODE)
            recesses = [c for c in outline.attachment.candidates
                        if c.accessibility.value == "OpenRecess"]
            self.assertEqual(len(recesses), 3)
            for selected in recesses:
                self.assertEqual(selected.contact_direction, -1)
                self.assertEqual(selected.contact_window.intervals,
                                 ((None, -selected.contact_band),))
                spec["transverse_placement"] = selected.stable_key
                _, _outline, views = resolved_preview(value, TOP_NODE)
                self.assertAlmostEqual(views[0].plate[2][1],
                                       -selected.outline_band-.01, places=6)

    def test_zero_degree_recesses_are_blocked_but_face_supports_remain(self):
        for name in ("W 150 x 13,0", 'I 3" x 8,48'):
            for thickness in (4., 8., 20.):
                value, node = preview_config(name, rotation=0.)
                value["connection_intents"][node]["gusset"]["plate_thickness"] = thickness
                _, outline, _ = resolved_preview(value, node)
                self.assertFalse(any(c.accessibility.value == "OpenRecess"
                                     for c in outline.attachment.candidates))
                self.assertEqual(sum(c.accessibility.value == "SurfaceBand"
                                     for c in outline.attachment.candidates), 3)

    def test_rotated_slabs_fit_actual_recess_and_preview(self):
        for name in ("W 150 x 13,0", 'I 3" x 8,48'):
            for rotation in (90., -90.):
                for thickness in (4., 8., 20., 48., 60.):
                    with self.subTest(profile=name, rotation=rotation, thickness=thickness):
                        value, node = preview_config(name, rotation=rotation)
                        spec = value["connection_intents"][node]["gusset"]
                        spec["plate_thickness"] = thickness
                        candidate, outline, _ = resolved_preview(value, node)
                        candidates = [c for c in outline.attachment.candidates
                                      if c.accessibility.value == "OpenRecess"]
                        self.assertEqual({c.placement.value for c in candidates},
                                         {"NearA", "Center", "NearB"})
                        internal = next(p for _id, label, p in regions_for(outline)
                                        if label == "Interna")
                        self.assertEqual({key for key, _label in internal},
                                         {c.stable_key for c in candidates})
                        participants = connection_participants(candidate, node)
                        _, materials, _ = attachment_slot_geometry(
                            candidate, participants, reference_frame(candidate.config))
                        for selected in candidates:
                            spec["transverse_placement"] = selected.stable_key
                            _, manual, views = resolved_preview(value, node)
                            self.assertEqual(choice(manual).stable_key, selected.stable_key)
                            self.assertAlmostEqual(selected.plate_high-selected.plate_low,
                                                   thickness)
                            material = tuple(m for m in materials
                                             if m.participant_key == selected.governing_participant_key)
                            extent = max(selected.contact_direction*q for m in material
                                         for _n, q in m.outer)
                            start = selected.outline_band+.01
                            self.assertLess(start, extent)
                            window = selected.contact_window.intervals
                            self.assertEqual(window, ((selected.contact_band, None),))
                            # Check actual material along the complete intrusion.
                            for fraction in (0., .1, .25, .5, .75, .9):
                                q = selected.contact_direction*(start+(extent-start)*fraction)
                                for a, b in material_intervals(material, q):
                                    self.assertLessEqual(min(b, selected.plate_high)
                                                         -max(a, selected.plate_low), 1e-6)
                            plate = views[0].plate
                            self.assertAlmostEqual(plate[0][0], selected.plate_low)
                            self.assertAlmostEqual(plate[1][0], selected.plate_high)
                            self.assertAlmostEqual(plate[0][1], start, places=6)
                            self.assertEqual(len(manual.attachment.residuals), len(participants))
                            self.assertEqual(manual.attachment.status, "Warning")
                            self.assertTrue(manual.attachment.diagnostics)

    def test_width_and_taper_depend_on_geometry_and_thickness(self):
        widths, contacts = {}, {}
        for name in ("W 150 x 13,0", 'I 3" x 8,48'):
            for thickness in (8., 60., 150.):
                value, node = preview_config(name, rotation=90.)
                value["connection_intents"][node]["gusset"]["plate_thickness"] = thickness
                _, outline, _ = resolved_preview(value, node)
                candidates = [c for c in outline.attachment.candidates
                              if c.accessibility.value == "OpenRecess"]
                if thickness == 150.:
                    self.assertFalse(candidates)
                    continue
                widths[name, thickness] = max(c.plate_high for c in candidates)-min(
                    c.plate_low for c in candidates)
                contacts[name, thickness] = max(c.contact_band for c in candidates)
        self.assertAlmostEqual(widths["W 150 x 13,0", 8.], 138.2)
        self.assertAlmostEqual(widths["W 150 x 13,0", 60.], 138.2)
        self.assertAlmostEqual(widths['I 3" x 8,48', 8.], 46.56925, places=4)
        self.assertGreater(widths['I 3" x 8,48', 60.], 60.)
        self.assertGreater(contacts['I 3" x 8,48', 60.], contacts['I 3" x 8,48', 8.])


if __name__ == "__main__":
    unittest.main()
