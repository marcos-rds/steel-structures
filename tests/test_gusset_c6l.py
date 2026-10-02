"""C6-L regressions derived from C6-Defeito-Externa.FCStd."""

import json
import math
import unittest

from freecad.SteelStructures.trusses.connections import connection_participants
from freecad.SteelStructures.trusses.gusset_attachment import attachment_slot_geometry
from freecad.SteelStructures.trusses.gussets import preliminary_gusset_outlines
from freecad.SteelStructures.trusses.realization import build_candidate, reference_frame
from tests.test_truss_assemblies import config
from tests.test_truss_manual_fixes import definition


TOP_NODE = "T_S_MAIN_1_2"
BOTTOM_NODE = "B_S_MAIN_1_3"


def fcstd_config(explicit_external=True):
    """Distilled persisted configuration; never reads the user's FCStd."""
    value = config()
    value.update(
        span=10000., height=2000., panel_count=6,
        topology_preset="WarrenVerticals",
        start=[0., 0., 0.], end=[10000., 0., 0.],
        top_continuity="Continuous", bottom_continuity="Continuous",
    )
    value["role_specs"]["TOP_CHORD"]["rotation"] = -90.
    value["role_specs"]["BOTTOM_CHORD"]["rotation"] = 90.
    gusset = dict(
        plate_thickness=10., edge_margin=25., member_overlap=150.,
        chord_contact="TrussInterior", side="Center",
    )
    value["connection_intents"] = {
        TOP_NODE: dict(form="Gusset", gusset=dict(gusset)),
        BOTTOM_NODE: dict(form="Gusset", gusset=dict(gusset)),
    }
    if explicit_external:
        probe, diagnostics = preliminary_gusset_outlines(build_candidate(value))
        if diagnostics:
            raise AssertionError(tuple(item.message for item in diagnostics))
        for node in (TOP_NODE, BOTTOM_NODE):
            outline = next(item for item in probe if item.spec.node_key == node)
            selected = next(
                item for item in outline.attachment.candidates
                if item.accessibility.value == "OuterExposed"
                and item.placement.value == "NearA"
                and item.governing_participant_key.endswith(
                    "TC_MAIN" if node == TOP_NODE else "BC_MAIN"))
            value["connection_intents"][node]["gusset"][
                "transverse_placement"] = selected.stable_key
    return value


def resolved(value):
    candidate = build_candidate(value)
    outlines, diagnostics = preliminary_gusset_outlines(candidate)
    if diagnostics:
        raise AssertionError(tuple(item.message for item in diagnostics))
    return candidate, {item.spec.node_key: item for item in outlines}


def chord_level(outline):
    edge = next(item for item in outline.semantic_edges
                if item.kind == "CHORD_BOUNDARY")
    if abs(edge.start[1]-edge.end[1]) > 1e-7:
        raise AssertionError("Fixture C6-L requer banzo horizontal.")
    return (edge.start[1]+edge.end[1])/2.


class FcstdExternalExtentTests(unittest.TestCase):
    def test_saved_top_and_bottom_nodes_reach_opposite_exterior_frontier(self):
        _candidate, outlines = resolved(fcstd_config())
        top, bottom = outlines[TOP_NODE], outlines[BOTTOM_NODE]
        top_choice = next(item for item in top.attachment.candidates
                          if item.stable_key == top.spec.transverse_placement)
        bottom_choice = next(item for item in bottom.attachment.candidates
                             if item.stable_key == bottom.spec.transverse_placement)

        # The FCStd saved -28.64/+28.64: the web-facing frontier plus 0.01 mm.
        self.assertAlmostEqual(top_choice.contact_band, 28.63, places=6)
        self.assertAlmostEqual(bottom_choice.contact_band, 28.63, places=6)
        # The exposed side reaches the opposite physical face at +/-11.60 mm.
        self.assertAlmostEqual(top_choice.outline_band, -11.60, places=6)
        self.assertAlmostEqual(bottom_choice.outline_band, -11.60, places=6)
        self.assertAlmostEqual(chord_level(top), 11.59, places=6)
        self.assertAlmostEqual(chord_level(bottom), -11.59, places=6)
        self.assertAlmostEqual(max(point[1] for point in top.points), 11.59,
                               places=6)
        self.assertAlmostEqual(min(point[1] for point in bottom.points), -11.59,
                               places=6)
        self.assertAlmostEqual(11.59-(-28.64), 40.23, places=6)
        self.assertAlmostEqual(28.64-(-11.59), 40.23, places=6)

        top_global_z = top.spec.frame.origin[2] + chord_level(top)*top.spec.frame.y_axis[2]
        bottom_global_z = (bottom.spec.frame.origin[2]
                           + chord_level(bottom)*bottom.spec.frame.y_axis[2])
        self.assertAlmostEqual(top_global_z, 2011.59, places=6)
        self.assertAlmostEqual(bottom_global_z, -11.59, places=6)

    def test_external_slab_is_tangent_without_positive_section_penetration(self):
        candidate, outlines = resolved(fcstd_config())
        frame = reference_frame(candidate.config)
        for node in (TOP_NODE, BOTTOM_NODE):
            with self.subTest(node=node):
                outline = outlines[node]
                selected = next(item for item in outline.attachment.candidates
                                if item.stable_key == outline.spec.transverse_placement)
                participants = connection_participants(candidate, node)
                _surfaces, materials, _slots = attachment_slot_geometry(
                    candidate, participants, frame)
                governing = tuple(item for item in materials
                                  if item.participant_key
                                  == selected.governing_participant_key)
                transverse_max = max(point[0] for item in governing
                                     for point in item.outer)
                self.assertAlmostEqual(transverse_max, selected.plate_low,
                                       places=6)
                self.assertGreater(selected.plate_high, transverse_max)
                self.assertTrue(any(low is None and high is None
                                    for low, high in selected.contact_window.intervals))

    def test_explicit_internal_placement_retains_approved_frontier(self):
        value = fcstd_config(explicit_external=False)
        _candidate, outlines = resolved(value)
        probe = outlines[TOP_NODE]
        internal = next(item for item in probe.attachment.candidates
                        if item.accessibility.value == "OpenRecess"
                        and item.placement.value == "Center")
        value["connection_intents"][TOP_NODE]["gusset"][
            "transverse_placement"] = internal.stable_key
        _candidate, outlines = resolved(value)
        outline = outlines[TOP_NODE]
        selected = next(item for item in outline.attachment.candidates
                        if item.stable_key == internal.stable_key)
        self.assertAlmostEqual(selected.contact_band, -6.93, places=6)
        self.assertAlmostEqual(selected.outline_band, selected.contact_band,
                               places=9)
        self.assertAlmostEqual(chord_level(outline), 6.92, places=6)

    def test_preview_outline_is_the_document_signature_source(self):
        _candidate, outlines = resolved(fcstd_config())
        signature = definition("gusset_plate.py", "outline_signature",
                               dict(json=json))
        for node in (TOP_NODE, BOTTOM_NODE):
            outline = outlines[node]
            persisted = json.loads(signature(outline))
            self.assertEqual(persisted["stable_key"], node+":gusset-plate")
            self.assertEqual(persisted["node_key"], node)
            self.assertEqual(persisted["transverse_placement"],
                             outline.spec.transverse_placement)
            self.assertEqual(tuple(tuple(point) for point in persisted["points"]),
                             outline.points)
            self.assertTrue(math.isclose(
                persisted["attachment"]["plate_high"]
                -persisted["attachment"]["plate_low"], 10., abs_tol=1e-9))


if __name__ == "__main__":
    unittest.main()
