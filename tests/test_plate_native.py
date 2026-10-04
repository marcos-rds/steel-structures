"""Native FreeCAD checks for the StructuralPlate BRep and Draft adapters.

The system Python skips these; FreeCAD's bundled Python runs them directly.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "freecad"))

try:
    import FreeCAD as App
    import Draft
    import Part
    from SteelStructures.plate import create_plate
    from SteelStructures.plate_geometry import PlateContour2D
    from SteelStructures.plate_planes import (PlateFaceReference,
                                               placement_from_face, placement_from_points,
                                               point_from_pick_info, preselection_pick,
                                               screen_coordinates, selected_plane_face,
                                               view_pick)
    from SteelStructures.plate_sources import resolve_plate_source
except (ImportError, ModuleNotFoundError):
    Draft = None
    App = None


@unittest.skipIf(App is None or Draft is None, "FreeCAD/Draft native Python required")
class StructuralPlateNativeTests(unittest.TestCase):
    def setUp(self):
        self.doc = App.newDocument("NativeStructuralPlate")

    def tearDown(self):
        App.closeDocument(self.doc.Name)

    def _planar_object(self, points):
        wire = Part.makePolygon([App.Vector(*point) for point in points + points[:1]])
        obj = self.doc.addObject("Part::Feature", "PlaneSource")
        obj.Shape = Part.Face(wire)
        self.doc.recompute()
        return obj

    def test_ordered_three_point_frames_and_plate_persistence(self):
        samples = (
            ((20, 0, 0), (40, 0, 0), (60, 20, 0)),
            ((20, 0, 0), (20, 0, 40), (60, 0, 40)),
            ((0, 20, 0), (0, 20, 40), (0, 80, 40)),
            ((4, 5, 6), (14, 5, 9), (17, 15, 11)),
        )
        for sample in samples:
            with self.subTest(sample=sample):
                p1, p2, p3 = [App.Vector(*point) for point in sample]
                frame = placement_from_points(p1, p2, p3)
                self.assertIsNotNone(frame)
                expected_normal = p2.sub(p1).cross(p3.sub(p1))
                actual_normal = frame.Rotation.multVec(App.Vector(0, 0, 1))
                self.assertGreater(actual_normal.dot(expected_normal), 0)
                local = [frame.inverse().multVec(point) for point in (p1, p2, p3)]
                self.assertTrue(all(abs(point.z) < 1e-7 for point in local))
                contour = PlateContour2D.from_points(
                    [(point.x, point.y) for point in local], closed=True)
                plate = create_plate(self.doc, contour, placement=frame,
                                     thickness=6, offset=2)
                self.doc.recompute()
                self.assertEqual(plate.Placement, frame)
                self.assertAlmostEqual(plate.Shape.Volume, contour.area * 6)
                self.assertEqual(PlateContour2D.from_data(plate.ContourData), contour)
        self.assertIsNone(placement_from_points(
            App.Vector(0, 0, 0), App.Vector(10, 0, 0), App.Vector(20, 0, 0)))
        plate_name, saved_placement, saved_contour, saved_volume = (
            plate.Name, plate.Placement, plate.ContourData, plate.Shape.Volume)
        handle, path = tempfile.mkstemp(prefix="plate_point_frame_", suffix=".FCStd")
        os.close(handle)
        try:
            self.doc.saveAs(path)
            App.closeDocument(self.doc.Name)
            self.doc = App.openDocument(path)
            self.doc.recompute()
            restored = self.doc.getObject(plate_name)
            self.assertLess(restored.Placement.Base.sub(saved_placement.Base).Length, 1e-7)
            self.assertLess(restored.Placement.Rotation.multVec(
                App.Vector(0, 0, 1)).sub(saved_placement.Rotation.multVec(
                    App.Vector(0, 0, 1))).Length, 1e-7)
            self.assertEqual(restored.ContourData, saved_contour)
            self.assertAlmostEqual(restored.Shape.Volume, saved_volume)
        finally:
            os.remove(path)

    def test_face_frames_horizontal_vertical_inclined_and_plate_once(self):
        cases = (
            [(0, 0, 0), (40, 0, 0), (40, 30, 0), (0, 30, 0)],
            [(0, 0, 0), (0, 30, 0), (40, 30, 0), (40, 0, 0)],
            [(0, 0, 0), (0, 40, 0), (0, 40, 30), (0, 0, 30)],
            [(0, 0, 0), (40, 0, 10), (40, 30, 10), (0, 30, 0)],
        )
        contour = PlateContour2D(((0, 0), (10, 0), (10, 8), (0, 8)))
        for index, points in enumerate(cases):
            with self.subTest(plane=index):
                obj = self._planar_object(points)
                reference = PlateFaceReference(obj, "Face1")
                placement = placement_from_face(reference)
                expected = obj.Shape.Faces[0].normalAt(0, 0)
                actual = placement.Rotation.multVec(App.Vector(0, 0, 1))
                self.assertAlmostEqual(actual.dot(expected), 1.0, places=7)
                center = obj.Shape.Faces[0].CenterOfMass
                self.assertLess(placement.Base.sub(center).Length, 1e-6)
                plate = create_plate(self.doc, contour, placement=placement,
                                     thickness=4, offset=0)
                self.assertEqual(plate.Placement, placement)
                self.assertAlmostEqual(plate.Shape.Volume, 10 * 8 * 4)
                self.assertTrue(any(vertex.Point.sub(placement.Base).Length < 1e-6
                                    for vertex in plate.Shape.Vertexes))

    def test_face_selection_snap_context_container_and_invalid_face(self):
        obj = self._planar_object(
            [(0, 0, 0), (40, 0, 0), (40, 30, 0), (0, 30, 0)])
        group = self.doc.addObject("App::Part", "PlaneContainer")
        group.addObject(obj)
        group.Placement = App.Placement(App.Vector(100, 200, 300),
                                        App.Rotation(App.Vector(0, 1, 0), 25))
        self.doc.recompute()
        item = type("Selection", (), {
            "Object": group, "SubElementNames": [obj.Name + ".Face1"],
            "SubObjects": [group.getSubObject(obj.Name + ".Face1")],
        })()
        selected = selected_plane_face([item], self.doc)
        self.assertEqual(selected.subelement, obj.Name + ".Face1")
        hover = type("Preselection", (), {
            "DocumentName": self.doc.Name, "Object": group,
            "SubElementNames": (obj.Name + ".Face1",),
            "PickedPoints": (group.Placement.multVec(App.Vector(20, 15, 0)),),
        })()
        hover_info, hover_point = preselection_pick(hover, self.doc)
        self.assertLess(hover_point.sub(hover.PickedPoints[0]).Length, 1e-8)
        self.assertEqual(hover_info["Component"], obj.Name + ".Face1")
        from_child = placement_from_face(PlateFaceReference(obj, "Face1"))
        from_parent = placement_from_face(selected)
        self.assertLess(from_child.Base.sub(from_parent.Base).Length, 1e-6)
        expected_center = group.Placement.multVec(App.Vector(20, 15, 0))
        self.assertLess(from_parent.Base.sub(expected_center).Length, 1e-6)
        expected_normal = group.Placement.Rotation.multVec(App.Vector(0, 0, 1))
        actual_normal = from_parent.Rotation.multVec(App.Vector(0, 0, 1))
        self.assertAlmostEqual(actual_normal.dot(expected_normal), 1.0, places=7)
        cylinder = self.doc.addObject("Part::Feature", "CurvedSource")
        cylinder.Shape = Part.makeCylinder(10, 20)
        self.doc.recompute()
        curved_face = next(index for index, face in enumerate(cylinder.Shape.Faces, 1)
                           if not face.Surface.isDerivedFrom("Part::GeomPlane"))
        with self.assertRaisesRegex(ValueError, "deve ser plana"):
            placement_from_face(PlateFaceReference(cylinder, "Face%d" % curved_face))
        contour = PlateContour2D(((0, 0), (12, 0), (12, 8), (0, 8)))
        plate = create_plate(self.doc, contour, placement=from_parent, thickness=5)
        plate_name = plate.Name
        before = sorted((round(v.Point.x, 6), round(v.Point.y, 6),
                         round(v.Point.z, 6)) for v in plate.Shape.Vertexes)
        handle, path = tempfile.mkstemp(prefix="plate_face_frame_", suffix=".FCStd")
        os.close(handle)
        try:
            self.doc.saveAs(path)
            App.closeDocument(self.doc.Name)
            self.doc = App.openDocument(path)
            self.doc.recompute()
            restored = self.doc.getObject(plate_name)
            after = sorted((round(v.Point.x, 6), round(v.Point.y, 6),
                            round(v.Point.z, 6)) for v in restored.Shape.Vertexes)
            self.assertEqual(after, before)
            self.assertEqual(restored.Placement, from_parent)
        finally:
            os.remove(path)

    def test_native_view_pick_and_preselection_supply_face_edge_vertex_points(self):
        box = self.doc.addObject("Part::Feature", "PickBox")
        box.Shape = Part.makeBox(40, 30, 8)
        box.Placement.Base = App.Vector(0, 0, 120)
        self.doc.recompute()
        top = next("Face%d" % index for index, face in enumerate(box.Shape.Faces, 1)
                   if face.normalAt(0, 0).z > .9)
        info = {"Object": box.Name, "Component": top,
                "x": 20.0, "y": 15.0, "z": 128.0}
        view = type("PickView", (), {"getObjectInfo": lambda _self, _pos: info})()
        picked, point = view_pick(view, (200, 300), self.doc)
        self.assertIs(picked, info)
        self.assertLess(point.sub(App.Vector(20, 15, 128)).Length, 1e-8)
        coin_position = type("CoinPosition", (), {
            "getValue": lambda _self: (200, 300)})()
        self.assertEqual(screen_coordinates(coin_position), (200, 300))
        self.assertLess(view_pick(view, coin_position, self.doc)[1].sub(point).Length, 1e-8)
        preselection = type("Preselection", (), {
            "DocumentName": self.doc.Name, "ObjectName": box.Name,
            "Object": box, "SubElementNames": (top,),
            "PickedPoints": (App.Vector(20, 15, 128),)})()
        pre_info, pre_point = preselection_pick(preselection, self.doc)
        self.assertEqual(pre_info["Component"], top)
        self.assertLess(pre_point.sub(App.Vector(20, 15, 128)).Length, 1e-8)
        for component in ("Edge10", "Vertex1"):
            preselection.SubElementNames = (component,)
            pre_info, pre_point = preselection_pick(preselection, self.doc)
            self.assertEqual(pre_info["Component"], component)
            self.assertLess(pre_point.sub(point).Length, 1e-8)
            info["Component"] = component
            picked, picked_point = view_pick(view, (200, 300), self.doc)
            self.assertIs(picked, info)
            self.assertLess(picked_point.sub(point).Length, 1e-8)
        preselection.DocumentName = ""
        self.assertEqual(preselection_pick(preselection, self.doc), (None, None))
        self.assertIsNone(point_from_pick_info({"Object": "Missing", "Component": top,
                                                 "x": 20, "y": 15, "z": 128}, self.doc))

    def test_arbitrary_polygon_extrudes_in_local_positive_z(self):
        contour = PlateContour2D(((0, 0), (0, 40), (60, 30), (80, 0)))
        placement = App.Placement(App.Vector(100, 200, 300), App.Rotation())
        plate = create_plate(self.doc, contour, placement=placement, thickness=7, offset=-2)
        self.assertEqual(plate.SourceMode, "InteractivePolygon")
        self.assertAlmostEqual(plate.GrossArea.Value, contour.area)
        self.assertAlmostEqual(plate.EnvelopeVolume.Value, contour.area * 7)
        self.assertAlmostEqual(plate.Shape.Volume, contour.area * 7)
        self.assertAlmostEqual(plate.Shape.BoundBox.ZMin, 298)
        self.assertAlmostEqual(plate.Shape.BoundBox.ZMax, 305)
        self.assertEqual(PlateContour2D.from_data(plate.ContourData).vertices, contour.vertices)
        self.assertTrue(plate.Shape.isValid())

    def test_rectangle_and_wire_share_contour_model_with_distinct_link_semantics(self):
        rectangle = Draft.make_rectangle(90, 30)
        wire = Draft.make_wire([App.Vector(0, 0, 0), App.Vector(80, 0, 0),
                                App.Vector(70, 40, 0), App.Vector(0, 30, 0)], closed=True)
        self.doc.recompute()
        rectangle_plate = create_plate(self.doc, None, source_mode="DraftRectangle",
                                       source_object=rectangle, keep_source_link=True)
        wire_plate = create_plate(self.doc, None, source_mode="DraftWire",
                                  source_object=wire, keep_source_link=False)
        self.assertEqual(len(PlateContour2D.from_data(rectangle_plate.ContourData).vertices), 4)
        self.assertEqual(len(PlateContour2D.from_data(wire_plate.ContourData).vertices), 4)
        self.assertIs(rectangle_plate.SourceObject, rectangle)
        self.assertIsNone(wire_plate.SourceObject)
        old_wire_volume = wire_plate.Shape.Volume
        rectangle.Length = 120
        wire.Points = [App.Vector(0, 0, 0), App.Vector(120, 0, 0),
                       App.Vector(70, 40, 0), App.Vector(0, 30, 0)]
        self.doc.recompute()
        self.assertAlmostEqual(rectangle_plate.GrossArea.Value, 120 * 30)
        self.assertAlmostEqual(wire_plate.Shape.Volume, old_wire_volume)

    def test_invalid_linked_wire_preserves_last_valid_solid(self):
        wire = Draft.make_wire([App.Vector(0, 0, 0), App.Vector(100, 0, 0),
                                App.Vector(50, 50, 0)], closed=True)
        self.doc.recompute()
        plate = create_plate(self.doc, None, source_mode="DraftWire",
                             source_object=wire, keep_source_link=True)
        old_volume, old_contour = plate.Shape.Volume, plate.ContourData
        wire.Closed = False
        self.doc.recompute()
        self.assertTrue(plate.GenerationStatus.startswith("Erro:"))
        self.assertAlmostEqual(plate.Shape.Volume, old_volume)
        self.assertEqual(plate.ContourData, old_contour)
        self.assertTrue(plate.KeepSourceLink)

    def test_wire_own_placement_and_container_are_applied_once(self):
        wire = Draft.make_wire([App.Vector(0, 0, 0), App.Vector(100, 0, 0),
                                App.Vector(80, 50, 0), App.Vector(0, 50, 0)], closed=True)
        group = self.doc.addObject("App::Part", "SourceContainer")
        group.addObject(wire)
        wire.Placement.Base = App.Vector(20, 30, 40)
        group.Placement.Base = App.Vector(200, 300, 400)
        self.doc.recompute()
        resolved = resolve_plate_source(wire, "DraftWire")
        plate = create_plate(self.doc, None, source_mode="DraftWire", source_object=wire,
                             keep_source_link=True)
        self.assertAlmostEqual(resolved.placement.Base.x, 220)
        self.assertAlmostEqual(resolved.placement.Base.y, 330)
        self.assertAlmostEqual(resolved.placement.Base.z, 440)
        self.assertAlmostEqual(plate.Shape.BoundBox.XMin, 220)
        self.assertAlmostEqual(plate.Shape.BoundBox.YMin, 330)
        self.assertAlmostEqual(plate.Shape.BoundBox.ZMin, 440)
        self.assertIn(group, plate.SourceContainers)
        group.Placement.Base = App.Vector(300, 400, 500)
        self.doc.recompute()
        self.assertAlmostEqual(plate.Shape.BoundBox.XMin, 320)
        self.assertAlmostEqual(plate.Shape.BoundBox.YMin, 430)
        self.assertAlmostEqual(plate.Shape.BoundBox.ZMin, 540)

    def test_transaction_undo_redo_restores_link_and_contour(self):
        self.doc.UndoMode = 1
        rectangle = Draft.make_rectangle(40, 25)
        self.doc.recompute()
        self.doc.openTransaction("Criar Chapa")
        plate = create_plate(self.doc, None, source_mode="DraftRectangle",
                             source_object=rectangle, keep_source_link=True,
                             thickness=6, offset=-3)
        name, contour_data = plate.Name, plate.ContourData
        self.doc.commitTransaction()
        self.assertIsNotNone(self.doc.getObject(name))
        self.doc.undo()
        self.assertIsNone(self.doc.getObject(name))
        self.doc.redo()
        restored = self.doc.getObject(name)
        self.assertIsNotNone(restored)
        self.doc.recompute()
        self.assertIs(restored.SourceObject, rectangle)
        self.assertEqual(restored.ContourData, contour_data)
        self.assertAlmostEqual(restored.Shape.BoundBox.ZMin, -3)

    def test_linked_plate_inside_source_container_uses_parent_local_placement(self):
        rectangle = Draft.make_rectangle(100, 40)
        source_group = self.doc.addObject("App::Part", "SourcePart")
        source_group.addObject(rectangle)
        source_group.Placement.Base = App.Vector(200, 300, 400)
        self.doc.recompute()
        plate = create_plate(self.doc, None, source_mode="DraftRectangle",
                             source_object=rectangle, keep_source_link=False)
        source_group.addObject(plate)
        plate.KeepSourceLink = True
        plate.SourceObject = rectangle
        rectangle.Length = 120
        self.doc.recompute()
        self.assertEqual(plate.GenerationStatus, "Valid")
        self.assertAlmostEqual(plate.getGlobalPlacement().Base.x, 200)
        self.assertAlmostEqual(plate.getGlobalPlacement().Base.y, 300)
        self.assertAlmostEqual(plate.getGlobalPlacement().Base.z, 400)
        self.assertAlmostEqual(plate.Placement.Base.x, 0)
        self.assertAlmostEqual(plate.Placement.Base.y, 0)
        self.assertAlmostEqual(plate.Placement.Base.z, 0)
        self.assertAlmostEqual(plate.Shape.BoundBox.XMin, 0)
        self.assertNotIn(source_group, plate.SourceContainers)
        source_group.Placement.Base = App.Vector(250, 350, 450)
        self.doc.recompute()
        self.assertAlmostEqual(plate.getGlobalPlacement().Base.x, 250)
        self.assertAlmostEqual(plate.getGlobalPlacement().Base.z, 450)
        self.assertAlmostEqual(plate.Shape.BoundBox.XMin, 0)
        self.assertAlmostEqual(plate.Shape.BoundBox.ZMin, 0)

    def test_linked_plate_in_other_container_keeps_global_source_plane(self):
        rectangle = Draft.make_rectangle(100, 40)
        source_group = self.doc.addObject("App::Part", "SourcePart")
        source_group.addObject(rectangle)
        source_group.Placement.Base = App.Vector(200, 300, 400)
        plate_group = self.doc.addObject("App::Part", "PlatePart")
        plate_group.Placement.Base = App.Vector(500, 600, 700)
        self.doc.recompute()
        plate = create_plate(self.doc, None, source_mode="DraftRectangle",
                             source_object=rectangle, keep_source_link=False)
        plate_group.addObject(plate)
        plate.KeepSourceLink = True
        plate.SourceObject = rectangle
        rectangle.Length = 120
        self.doc.recompute()
        self.assertEqual(plate.GenerationStatus, "Valid")
        self.assertAlmostEqual(plate.getGlobalPlacement().Base.x, 200)
        self.assertAlmostEqual(plate.getGlobalPlacement().Base.y, 300)
        self.assertAlmostEqual(plate.getGlobalPlacement().Base.z, 400)
        self.assertAlmostEqual(plate.Placement.Base.x, -300)
        self.assertAlmostEqual(plate.Placement.Base.y, -300)
        self.assertAlmostEqual(plate.Placement.Base.z, -300)
        self.assertIn(source_group, plate.SourceContainers)
        source_group.Placement.Base = App.Vector(250, 350, 450)
        self.doc.recompute()
        self.assertAlmostEqual(plate.getGlobalPlacement().Base.x, 250)
        self.assertAlmostEqual(plate.getGlobalPlacement().Base.z, 450)
        self.assertAlmostEqual(plate.Shape.BoundBox.XMin, -250)
        self.assertAlmostEqual(plate.Shape.BoundBox.ZMin, -250)
        handle, path = tempfile.mkstemp(prefix="plate_two_parts_", suffix=".FCStd")
        os.close(handle)
        try:
            plate_name, source_group_name = plate.Name, source_group.Name
            self.doc.saveAs(path)
            App.closeDocument(self.doc.Name)
            self.doc = App.openDocument(path)
            self.doc.recompute()
            restored = self.doc.getObject(plate_name)
            self.assertEqual(restored.GenerationStatus, "Valid")
            self.assertAlmostEqual(restored.getGlobalPlacement().Base.x, 250)
            self.assertAlmostEqual(restored.getGlobalPlacement().Base.z, 450)
            self.assertAlmostEqual(restored.Shape.BoundBox.XMin, -250)
            self.assertIn(self.doc.getObject(source_group_name), restored.SourceContainers)
        finally:
            os.remove(path)


if __name__ == "__main__":
    unittest.main()
