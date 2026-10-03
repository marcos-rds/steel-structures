"""Numerical C6-H contact-band regressions, independent of FreeCAD/OCC."""

import unittest
from types import SimpleNamespace
import copy
from dataclasses import asdict

from freecad.SteelStructures.connections.models import (GussetCorridor,
    GussetPlateFrame, GussetPlateSpec, GussetSectionMaterial2D)
from freecad.SteelStructures.connections.slots import contact_band_support
from freecad.SteelStructures.connections.gusset import build_gusset_outline
from freecad.SteelStructures.trusses.gussets import (
    _chord_support_lines, _web_end_lines, _web_sector_bridge_lines,
    preliminary_gusset_outlines)
from freecad.SteelStructures.trusses.realization import build_candidate
from freecad.SteelStructures.trusses.assemblies import assembly_frame
from freecad.SteelStructures.trusses.fitting_geometry import _section_at_insertion
from freecad.SteelStructures.trusses.gusset_attachment import component_section_material
from freecad.SteelStructures.profiles.geometry import ArcSegment2D
from freecad.SteelStructures import profile_catalog
from tests.test_connections_c5b_polish import three_web_config
from tests.test_gusset_plate_c6a import configured


AXIS = (0., 1., 0.)


def section(points, key="component", holes=()):
    return GussetSectionMaterial2D("chord", key, tuple(points),
                                   tuple(tuple(path) for path in holes), AXIS)


class ContactBandTests(unittest.TestCase):
    def test_wall_thickness_is_measured_from_real_boundaries(self):
        flange = section(((-10., -20.), (10., -20.),
                          (10., -16.), (-10., -16.)))
        outside = -contact_band_support((flange,), -5., 5., -1)
        inside = contact_band_support((flange,), -5., 5., 1)
        self.assertAlmostEqual(outside, -20.)
        self.assertAlmostEqual(inside, -16.)
        self.assertAlmostEqual(inside-outside, 4.)

    def test_tapered_flange_uses_most_salient_point_across_full_slab(self):
        taper = section(((-10., -20.), (10., -20.),
                         (10., -12.), (-10., -18.)))
        inside = contact_band_support((taper,), -5., 5., 1)
        self.assertAlmostEqual(inside, -13.5)
        self.assertAlmostEqual(inside-(-20.), 6.5)
        self.assertGreater(inside, -15.)  # the plate centre is insufficient

    def test_lip_and_assembly_components_govern_by_extreme_material(self):
        flange = section(((-10., -20.), (10., -20.),
                          (10., -16.), (-10., -16.)), "flange")
        lip = section(((3., -16.), (5., -16.),
                       (5., -11.), (3., -11.)), "lip")
        self.assertAlmostEqual(contact_band_support((flange, lip),
                                                    -5., 5., 1), -11.)

    def test_closed_hollow_uses_exterior_material_support(self):
        tube = section(((-20., -20.), (20., -20.),
                        (20., 20.), (-20., 20.)),
                       holes=(((-18., -18.), (18., -18.),
                               (18., 18.), (-18., 18.)),))
        self.assertAlmostEqual(contact_band_support((tube,), 19., 22., 1), 20.)
        self.assertAlmostEqual(contact_band_support((tube,), -22., -19., 1), 20.)

    def test_unoccupied_slab_has_no_contact(self):
        wall = section(((-2., -10.), (2., -10.),
                        (2., 10.), (-2., 10.)))
        self.assertIsNone(contact_band_support((wall,), 3., 8., 1))


class ContactDirectionTests(unittest.TestCase):
    def _normal(self, chord_direction, web_direction, role):
        participants = (SimpleNamespace(participant_key="chord", role=role),
                        SimpleNamespace(participant_key="web", role="DIAGONAL"))
        corridors = (GussetCorridor("chord", "c", chord_direction, -5., 5.),
                     GussetCorridor("web", "w", web_direction, -5., 5.))
        return _chord_support_lines(participants, corridors)[0].normal

    def test_parallel_top_and_bottom_interior_faces_webs(self):
        self.assertEqual(self._normal((1., 0.), (0., -1.), "TOP_CHORD"),
                         (0., 1.))
        self.assertEqual(self._normal((1., 0.), (0., 1.), "BOTTOM_CHORD"),
                         (0., -1.))

    def test_duopitch_branches_use_local_directions(self):
        left = self._normal((.8, .6), (0., -1.), "TOP_CHORD")
        right = self._normal((.8, -.6), (0., -1.), "TOP_CHORD")
        self.assertAlmostEqual(left[0], -.6)
        self.assertAlmostEqual(left[1], .8)
        self.assertAlmostEqual(right[0], .6)
        self.assertAlmostEqual(right[1], .8)


class MirroredBridgeTests(unittest.TestCase):
    def _outline(self, reflected):
        x = -1. if reflected else 1.
        participants = (SimpleNamespace(participant_key="chord", role="TOP_CHORD",
                                        end="Through"),
                        SimpleNamespace(participant_key="diagonal", role="DIAGONAL",
                                        end="End"),
                        SimpleNamespace(participant_key="vertical", role="VERTICAL",
                                        end="End"))
        corridors = (GussetCorridor("chord", "c", (x, 0.), -8., 8.),
                     GussetCorridor("diagonal", "d", (.6*x, -.8), -5., 5.),
                     GussetCorridor("vertical", "v", (0., -1.), -5., 5.))
        spec = GussetPlateSpec("n:gusset-plate", "n", 10., 25., 150.,
                               participant_keys=("chord", "diagonal", "vertical"),
                               frame=GussetPlateFrame((0., 0., 0.),
                                                      (1., 0., 0.), (0., 1., 0.),
                                                      (0., 0., 1.)))
        supports = (_chord_support_lines(participants, corridors)
                    +_web_end_lines(participants, corridors, spec)
                    +_web_sector_bridge_lines(participants, corridors, spec))
        return build_gusset_outline(spec, corridors, supports)

    def test_exact_mirrors_have_equal_area_edges_and_vertices(self):
        left, right = self._outline(False), self._outline(True)
        self.assertAlmostEqual(left.area, right.area, places=5)
        self.assertEqual(sorted(edge.kind for edge in left.semantic_edges),
                         sorted(edge.kind for edge in right.semantic_edges))
        reflected = {(-round(x, 5), round(y, 5)) for x, y in left.points}
        actual = {(round(x, 5), round(y, 5)) for x, y in right.points}
        self.assertEqual(reflected, actual)
        left_contact = {(-round(x, 5), round(y, 5))
                        for edge in left.semantic_edges
                        if edge.kind == "CHORD_BOUNDARY"
                        for x, y in (edge.start, edge.end)}
        right_contact = {(round(x, 5), round(y, 5))
                         for edge in right.semantic_edges
                         if edge.kind == "CHORD_BOUNDARY"
                         for x, y in (edge.start, edge.end)}
        self.assertEqual(left_contact, right_contact)


class ProductionContactTests(unittest.TestCase):
    def _outline(self, designation, rotation=0.):
        value, node = three_web_config()
        reference = asdict(profile_catalog.ref_for_designation(designation))
        for role in ("TOP_CHORD", "BOTTOM_CHORD"):
            value["role_specs"][role]["profile_ref"] = copy.deepcopy(reference)
            value["role_specs"][role]["rotation"] = rotation
        candidate = build_candidate(configured(
            value, node, chord_contact="TrussInterior"))
        outlines, diagnostics = preliminary_gusset_outlines(candidate)
        self.assertFalse(diagnostics, [item.message for item in diagnostics])
        return next(item for item in outlines if item.spec.node_key == node)

    def test_rotated_u_contact_is_independent_of_recess_access(self):
        counts = []
        for angle in (0., 90., 180., 270.):
            with self.subTest(angle=angle):
                outline = self._outline('U 4" x 8,04', angle)
                self.assertGreater(outline.area, 0.)
                self.assertIn("CHORD_BOUNDARY",
                              {edge.kind for edge in outline.semantic_edges})
                counts.append(sum(value.accessibility.value == "OpenRecess"
                                  for value in outline.attachment.candidates))
        self.assertIn(0, counts)
        self.assertGreater(max(counts), 0)

    def test_rotated_ue_keeps_web_facing_contact_with_lips(self):
        for angle in (0., 90., 180., 270.):
            with self.subTest(angle=angle):
                outline = self._outline("Ue 150 × 60 × 20 × 3,00", angle)
                self.assertGreater(outline.area, 0.)
                self.assertIn("CHORD_BOUNDARY",
                              {edge.kind for edge in outline.semantic_edges})

    def test_shs_truss_interior_uses_exterior_without_void_placement(self):
        outline = self._outline("SHS 40x40x1,2")
        self.assertGreater(outline.area, 0.)
        self.assertTrue(all(value.accessibility.value != "EnclosedVoid"
                            for value in outline.attachment.candidates))
        self.assertIn("CHORD_BOUNDARY",
                      {edge.kind for edge in outline.semantic_edges})

    def test_laminated_u_and_i_radii_match_dense_section_geometry(self):
        for designation in ('U 4" x 8,04', 'I 3" x 8,48'):
            with self.subTest(designation=designation):
                value, _node = three_web_config()
                value["role_specs"]["BOTTOM_CHORD"]["profile_ref"] = asdict(
                    profile_catalog.ref_for_designation(designation))
                candidate = build_candidate(value)
                item = next(item for item in candidate.items
                            if item.role == "BOTTOM_CHORD"
                            and item.element_kind == "Component")
                normal = tuple(candidate.config["plane_normal"])
                participant = SimpleNamespace(participant_key="chord")
                material = component_section_material(
                    item, participant, item.start_global, normal)
                section, insertion = _section_at_insertion(item)
                self.assertTrue(any(isinstance(segment, ArcSegment2D)
                                    for segment in section.outer_path.segments))
                frame = assembly_frame((item.start_global, item.end_global),
                                       item.section_u_global, item.spec.rotation)
                dense = []
                for segment in section.outer_path.segments:
                    points = (segment.sampled_points(2000)
                              if isinstance(segment, ArcSegment2D)
                              else (segment.end,))
                    for point in points:
                        relative = tuple((point.x+insertion[0])*frame.u[i]
                                         +(point.y+insertion[1])*frame.v[i]
                                         for i in range(3))
                        dense.append((sum(relative[i]*normal[i] for i in range(3)),
                                      sum(relative[i]*material.local_axis[i]
                                          for i in range(3))))
                exact = GussetSectionMaterial2D(
                    "chord", "dense", tuple(dense), (), material.local_axis)
                n_values = [n for n, _q in material.outer]
                low, high = min(n_values), max(n_values)
                for index in range(10):
                    slab = (low+(high-low)*index/10.,
                            low+(high-low)*(index+1)/10.)
                    actual = contact_band_support((material,), *slab, 1)
                    reference = contact_band_support((exact,), *slab, 1)
                    self.assertIsNotNone(actual)
                    self.assertAlmostEqual(actual, reference, delta=.02)


if __name__ == "__main__":
    unittest.main()
