"""Isolated FreeCAD adapter tests using the project's controlled-module pattern."""

from __future__ import annotations

import importlib.util
import math
import sys
import types
import unittest
from dataclasses import dataclass, replace
from pathlib import Path

from freecad.SteelStructures.paths import CATALOGS_DIR
from freecad.SteelStructures.profiles import ProfileLibrary, ProfileRef
from freecad.SteelStructures.profiles.geometry import (
    LineSegment2D, Point2D, SectionBounds2D, SectionGeometry2D, SectionPath2D,
    build_section_geometry,
)


ROOT = Path(__file__).resolve().parents[1]
ADAPTER = ROOT / "freecad/SteelStructures/profiles/freecad_geometry.py"
CATALOG_ID = "gerdau-construcao-metalica-2023-01"


class Vector:
    def __init__(self, x=0.0, y=0.0, z=0.0):
        self.x, self.y, self.z = float(x), float(y), float(z)


class Edge:
    def __init__(self, start, end):
        self.start, self.end = start, end


class Arc:
    def __init__(self, start, mid, end):
        self.start, self.mid, self.end = start, mid, end

    def toShape(self):
        return Edge(self.start, self.end)


class Wire:
    def __init__(self, edges):
        self.Edges = list(edges)

    def isClosed(self):
        if not self.Edges:
            return False
        first, last = self.Edges[0].start, self.Edges[-1].end
        return (first.x, first.y, first.z) == (last.x, last.y, last.z)


class BoundBox:
    def __init__(self, points):
        xs, ys, zs = ([getattr(point, axis) for point in points] for axis in ("x", "y", "z"))
        self.XMin, self.XMax = min(xs), max(xs)
        self.YMin, self.YMax = min(ys), max(ys)
        self.ZMin, self.ZMax = min(zs), max(zs)
        self.XLength = self.XMax - self.XMin
        self.YLength = self.YMax - self.YMin


class Solid:
    def __init__(self, face, vector):
        self.Volume = face.Area * abs(vector.z)

    def isNull(self):
        return False


class Face:
    def __init__(self, wires):
        self.Wires = list(wires) if isinstance(wires, (list, tuple)) else [wires]
        def polygon_area(wire):
            points = [edge.start for edge in wire.Edges]
            return abs(0.5 * sum(
                point.x * wire.Edges[(index + 1) % len(wire.Edges)].start.y
                - wire.Edges[(index + 1) % len(wire.Edges)].start.x * point.y
                for index, point in enumerate(points)
            ))
        self.Area = polygon_area(self.Wires[0]) - sum(
            polygon_area(wire) for wire in self.Wires[1:]
        )
        self.BoundBox = BoundBox([edge.start for edge in self.Wires[0].Edges])

    def isNull(self):
        return False

    def extrude(self, vector):
        return Solid(self, vector)


def load_adapter():
    app = types.ModuleType("FreeCAD")
    app.Vector = Vector
    part = types.ModuleType("Part")
    part.makeLine, part.Arc = lambda start, end: Edge(start, end), Arc
    part.Wire, part.Face = Wire, Face
    injected = {"FreeCAD": app, "Part": part}
    previous = {name: sys.modules.get(name) for name in injected}
    sys.modules.update(injected)
    try:
        name = "freecad.SteelStructures.profiles._freecad_geometry_adapter_test"
        spec = importlib.util.spec_from_file_location(name, ADAPTER)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        for name, old in previous.items():
            if old is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = old


@dataclass(frozen=True)
class FutureArcSegment:
    start: Point2D
    end: Point2D


class FreeCADSectionAdapterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.adapter = load_adapter()
        cls.library = ProfileLibrary(CATALOGS_DIR)

    def profile(self, profile_id):
        return self.library.get(ProfileRef(CATALOG_ID, profile_id))

    def test_point_maps_directly_to_xy_millimetres_at_zero_z(self):
        vector = self.adapter.point_to_vector(Point2D(12.5, -7.25))
        self.assertEqual((vector.x, vector.y, vector.z), (12.5, -7.25, 0.0))
        with self.assertRaises(self.adapter.FreeCADSectionGeometryError):
            self.adapter.point_to_vector((1, 2))

    def test_closed_path_creates_ordered_twelve_edge_wire(self):
        geometry = build_section_geometry(self.profile("w-150x13.0"))
        wire = self.adapter.section_path_to_wire(geometry.outer_path)
        self.assertTrue(wire.isClosed())
        self.assertEqual(len(wire.Edges), 12)
        expected = geometry.outer_path.segments
        for edge, segment in zip(wire.Edges, expected):
            self.assertEqual((edge.start.x, edge.start.y), (segment.start.x, segment.start.y))
            self.assertEqual((edge.end.x, edge.end.y), (segment.end.x, segment.end.y))

    def test_open_path_is_rejected_defensively(self):
        points = Point2D(0, 0), Point2D(1, 0), Point2D(1, 1)
        from freecad.SteelStructures.profiles.geometry import LineSegment2D
        path = SectionPath2D((LineSegment2D(points[0], points[1]), LineSegment2D(points[1], points[2])), False)
        with self.assertRaisesRegex(self.adapter.FreeCADSectionGeometryError, "fechados"):
            self.adapter.section_path_to_wire(path)

    def test_future_segment_is_rejected_instead_of_approximated(self):
        a, b, c = Point2D(0, 0), Point2D(1, 0), Point2D(0, 1)
        path = SectionPath2D((FutureArcSegment(a, b), FutureArcSegment(b, c), FutureArcSegment(c, a)), True)
        with self.assertRaisesRegex(self.adapter.FreeCADSectionGeometryError, "FutureArcSegment"):
            self.adapter.section_path_to_wire(path)

    def test_inner_paths_create_valid_positive_face_holes_instead_of_being_ignored(self):
        geometry = build_section_geometry(self.profile("w-150x13.0"))
        inner = SectionPath2D((
            LineSegment2D(Point2D(-1, -1), Point2D(1, -1)),
            LineSegment2D(Point2D(1, -1), Point2D(1, 1)),
            LineSegment2D(Point2D(1, 1), Point2D(-1, 1)),
            LineSegment2D(Point2D(-1, 1), Point2D(-1, -1)),
        ), True)
        with_hole = replace(geometry, inner_paths=(inner,))
        face = self.adapter.section_geometry_to_face(with_hole)
        self.assertEqual(len(face.Wires), 2)
        self.assertGreater(face.Area, 0.0)
        self.assertLess(face.Area, geometry.area)

    def test_coincident_inner_path_is_rejected_as_zero_area_face(self):
        geometry = build_section_geometry(self.profile("w-150x13.0"))
        coincident = replace(geometry, inner_paths=(geometry.outer_path,))
        with self.assertRaisesRegex(
                self.adapter.FreeCADSectionGeometryError, "área positiva"):
            self.adapter.section_geometry_to_face(coincident)

    def test_required_w_hp_faces_preserve_area_and_bounds(self):
        ids = ("w-150x13.0", "w-310x52.0", "w-610x217.0", "hp-200x53.0", "hp-310x132.0")
        for profile_id in ids:
            profile = self.profile(profile_id)
            geometry = build_section_geometry(profile)
            face = self.adapter.section_geometry_to_face(geometry)
            box = face.BoundBox
            with self.subTest(profile=profile_id):
                self.assertFalse(face.isNull())
                self.assertAlmostEqual(face.Area, geometry.area)
                self.assertAlmostEqual(box.XMin, geometry.bounds.min_x)
                self.assertAlmostEqual(box.XMax, geometry.bounds.max_x)
                self.assertAlmostEqual(box.YMin, geometry.bounds.min_y)
                self.assertAlmostEqual(box.YMax, geometry.bounds.max_y)
                self.assertEqual((box.ZMin, box.ZMax), (0.0, 0.0))

    def test_all_eighty_equal_angles_create_valid_faces_and_extrusions(self):
        angles = [
            profile for profile in self.library.list_profiles()
            if profile.series_id in ("equal-angle-inch", "equal-angle-metric")
        ]
        self.assertEqual(len(angles), 80)
        for profile in angles:
            geometry = build_section_geometry(profile)
            face = self.adapter.section_geometry_to_face(geometry)
            solid = face.extrude(Vector(0, 0, 1000))
            b, t = profile.geometry["b"], profile.geometry["t"]
            with self.subTest(profile=profile.designation):
                self.assertFalse(face.isNull())
                self.assertAlmostEqual(face.Area, 2.0 * b * t - t * t)
                self.assertAlmostEqual(solid.Volume, face.Area * 1000.0)
                self.assertEqual(len(face.Wires[0].Edges), 6)

    def test_all_nine_released_u_profiles_create_faces_and_extrusions_with_four_arcs(self):
        channels = tuple(profile for profile in self.library.list_profiles(series_id="u")
                         if profile.geometry_status == "released")
        self.assertEqual(len(channels), 9)
        for profile in channels:
            geometry = build_section_geometry(profile)
            face = self.adapter.section_geometry_to_face(geometry)
            solid = face.extrude(Vector(0, 0, 1000))
            with self.subTest(profile=profile.designation):
                self.assertFalse(face.isNull())
                self.assertFalse(solid.isNull())
                self.assertEqual(len(face.Wires[0].Edges), 12)
                self.assertAlmostEqual(face.BoundBox.XLength, profile.geometry["bf"])
                self.assertAlmostEqual(face.BoundBox.YLength, profile.geometry["d"])

    def test_all_eight_tapered_i_profiles_create_faces_and_extrusions_with_eight_arcs(self):
        profiles = self.library.list_profiles(series_id="i")
        self.assertEqual(len(profiles), 8)
        for profile in profiles:
            geometry = build_section_geometry(profile)
            face = self.adapter.section_geometry_to_face(geometry)
            solid = face.extrude(Vector(0, 0, 1000))
            with self.subTest(profile=profile.designation):
                self.assertFalse(face.isNull())
                self.assertFalse(solid.isNull())
                self.assertEqual(len(face.Wires[0].Edges), 20)
                self.assertAlmostEqual(face.BoundBox.XLength, profile.geometry["bf"])
                self.assertAlmostEqual(face.BoundBox.YLength, profile.geometry["d"])

    def test_all_ten_standard_tees_create_eight_edge_faces_and_extrusions(self):
        profiles = self.library.list_profiles(series_id="t")
        self.assertEqual(len(profiles), 10)
        for profile in profiles:
            geometry = build_section_geometry(profile)
            face = self.adapter.section_geometry_to_face(geometry)
            solid = face.extrude(Vector(0, 0, 1000))
            with self.subTest(profile=profile.designation):
                self.assertFalse(face.isNull())
                self.assertFalse(solid.isNull())
                self.assertEqual(len(face.Wires[0].Edges), 8)
                self.assertAlmostEqual(face.Area, geometry.area)
                self.assertAlmostEqual(face.BoundBox.XLength, profile.geometry["bf"])
                self.assertAlmostEqual(face.BoundBox.YLength, profile.geometry["d"])
                self.assertAlmostEqual(solid.Volume, geometry.area * 1000.0)

    def test_representative_ue_creates_closed_face_and_extrusion(self):
        profile = self.library.get(ProfileRef(
            "abnt-nbr-6355-2012-a3", "ue-150x60x20x3.00"
        ))
        geometry = build_section_geometry(profile)
        wire = self.adapter.section_path_to_wire(geometry.outer_path)
        face = self.adapter.section_geometry_to_face(geometry)
        solid = face.extrude(Vector(0, 0, 1000))
        self.assertTrue(wire.isClosed())
        self.assertFalse(face.isNull())
        self.assertFalse(solid.isNull())
        self.assertEqual(len(wire.Edges), 20)
        self.assertAlmostEqual(solid.Volume, face.Area * 1000.0)

    def test_w310_face_and_extrusion_match_expected_area_bounds_and_volume(self):
        geometry = build_section_geometry(self.profile("w-310x52.0"))
        face = self.adapter.section_geometry_to_face(geometry)
        self.assertAlmostEqual(face.Area, 6617.36)
        self.assertEqual((face.BoundBox.XLength, face.BoundBox.YLength), (167.0, 317.0))
        solid = face.extrude(Vector(0, 0, 1000))
        self.assertFalse(solid.isNull())
        self.assertAlmostEqual(solid.Volume, 6_617_360.0)

    def test_face_area_is_not_the_commercial_catalog_area(self):
        profile = self.profile("w-150x13.0")
        face = self.adapter.section_geometry_to_face(build_section_geometry(profile))
        self.assertNotAlmostEqual(face.Area, profile.physical_properties.area_mm2)

    def test_invalid_adapter_inputs_fail_explicitly(self):
        with self.assertRaises(self.adapter.FreeCADSectionGeometryError):
            self.adapter.section_path_to_wire(object())
        with self.assertRaises(self.adapter.FreeCADSectionGeometryError):
            self.adapter.section_geometry_to_face(object())


class MemberFaceIntegrationTests(unittest.TestCase):
    def test_legacy_i_section_face_uses_common_twelve_segment_contract(self):
        try:
            from test_member_placement import PROFILE, load_member
        except ModuleNotFoundError:
            from tests.test_member_placement import PROFILE, load_member
        member = load_member()
        face = member._i_section_face(PROFILE)
        self.assertEqual(len(face.wire.edges), 12)
        starts = tuple((edge[0].x, edge[0].y) for edge in face.wire.edges)
        self.assertEqual(starts[0], (-75.0, -75.0))
        self.assertIn((3.0, -66.0), starts)
        self.assertIn((-3.0, 66.0), starts)


if __name__ == "__main__":
    unittest.main()
