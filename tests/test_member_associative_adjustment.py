"""Integration tests for associative structural-member end adjustment."""

import math
import unittest

from tests.test_member_adjustment_reference import EdgeReference, Reference
from tests.test_member_placement import Placement, Quantity, Rotation, Vector, MemberObject, load_member


class MemberAssociativeAdjustmentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.member = load_member()

    def proxy(self):
        proxy = self.member.StructuralMemberProxy.__new__(self.member.StructuralMemberProxy)
        proxy._updating = proxy._syncing_length = proxy._syncing_placement = False
        proxy._placement_from_points_pending = True; proxy._last_placement = None
        proxy._last_section_rotation = 0.0; proxy._last_valid_length = None
        return proxy

    def create(self, start=(0, 0, 0), end=(3000, 0, 0)):
        obj, proxy = MemberObject(start, end), self.proxy()
        obj.EndAdjustmentMode = "Associative"; obj.AdjustedEnd = "End"
        proxy.execute(obj)
        return obj, proxy

    def assertVector(self, actual, expected, places=6):
        for value, wanted in zip((actual.x, actual.y, actual.z), expected):
            self.assertAlmostEqual(value, wanted, places=places)

    def reference(self, point=(2800, 0, 0), normal=(1, 0, 0), placement=None):
        return Reference(point=point, normal=normal, placement=placement)

    def test_associative_end_updates_when_reference_moves_without_changing_nominal_axis(self):
        obj, proxy = self.create(); reference = self.reference()
        obj.AdjustmentReference = (reference, ["Face3"]); proxy.execute(obj)
        self.assertEqual(obj.AdjustedLength, 2800); self.assertVector(obj.EffectiveEndPoint, (2800, 0, 0))
        self.assertAlmostEqual(obj.TotalMass, 13.0 * 2.8)
        self.assertVector(obj.StartPoint, (0, 0, 0)); self.assertVector(obj.EndPoint, (3000, 0, 0))
        reference.Placement = Placement(Vector(-100, 0, 0), Rotation()); proxy.execute(obj)
        self.assertEqual(obj.AdjustedLength, 2700); self.assertVector(obj.EffectiveEndPoint, (2700, 0, 0))
        self.assertEqual(obj.FixedReferenceOffset.Value, 0)

    def test_associative_end_gap_positive_zero_and_negative(self):
        obj, proxy = self.create(); obj.AdjustmentReference = (self.reference(), ["Face3"])
        for gap, expected in ((0, 2800), (20, 2780), (-20, 2820)):
            obj.AdjustmentGap = Quantity(gap); proxy.execute(obj)
            self.assertEqual(obj.AdjustedLength, expected); self.assertEqual(obj.AdjustmentGap.Value, gap)

    def test_length_limit_inclined_laterally_offset_face_uses_infinite_plane(self):
        obj, proxy = self.create()
        obj.AdjustmentReference = (self.reference(point=(2800, 100, 500), normal=(1, 1, 0)), ["Face3"])
        proxy.execute(obj)
        self.assertVector(obj.EffectiveEndPoint, (2900, 0, 0)); self.assertEqual(obj.AdjustedLength, 2900)
        obj.AdjustmentReference[0].local_face.normal = Vector(-1, -1, 0); proxy.execute(obj)
        self.assertEqual(obj.AdjustedLength, 2900)

    def test_length_limit_straight_edge_crossing_offset_skew_start_end_and_gap(self):
        cases = [
            (EdgeReference((2800, -10, 0), (2800, 10, 0)), 2800),
            (EdgeReference((2700, -10, 500), (2700, 10, 500)), 2700),
            (EdgeReference((2600, -10, 500), (2600, 10, 510)), 2600),
        ]
        for reference, station in cases:
            with self.subTest(station=station):
                obj, proxy = self.create(); obj.AdjustmentReference = (reference, ["Edge3"])
                obj.AdjustmentGap = Quantity(20); proxy.execute(obj)
                self.assertEqual(obj.AdjustedLength, station - 20)
        obj, proxy = self.create(); obj.EndAdjustmentMode = "None"; obj.AdjustedEnd = "Start"; obj.StartAdjustmentMode = "Associative"
        obj.AdjustmentReference = (EdgeReference((200, -10, 100), (200, 10, 100)), ["Edge3"])
        obj.AdjustmentGap = Quantity(-20); proxy.execute(obj)
        self.assertVector(obj.EffectiveStartPoint, (180, 0, 0)); self.assertEqual(obj.AdjustedLength, 2820)

    def test_length_limit_edge_reference_and_member_placements(self):
        obj, proxy = self.create((0, 0, 0), (10, 0, 0))
        reference = EdgeReference((0, -1, 0), (0, 1, 0), Placement(Vector(8, 4, 6), Rotation()))
        obj.AdjustmentReference = (reference, ["Edge3"]); proxy.execute(obj)
        self.assertEqual(obj.AdjustedLength, 8)
        rigid = Placement(Vector(), Rotation(Vector(0, 0, 1), 90))
        obj.Placement = rigid.multiply(obj.Placement); proxy.onChanged(obj, "Placement")
        reference.Placement = rigid.multiply(reference.Placement); proxy.execute(obj)
        self.assertVector(obj.EffectiveEndPoint, (0, 8, 0)); self.assertEqual(obj.AdjustedLength, 8)

    def test_length_limit_parallel_curved_and_degenerate_edges_are_invalid(self):
        for reference in (EdgeReference((0, 1, 0), (10, 1, 0)),
                          EdgeReference((5, -1, 0), (5, 1, 0), linear=False),
                          EdgeReference((5, 1, 0), (5, 1, 0))):
            obj, proxy = self.create((0, 0, 0), (10, 0, 0))
            obj.AdjustmentReference = (reference, ["Edge3"]); proxy.execute(obj)
            self.assertTrue(obj.Shape.empty); self.assertEqual(obj.AdjustedLength, 0)

    def test_associative_start_gap_and_extensions(self):
        obj, proxy = self.create(); obj.EndAdjustmentMode = "None"; obj.AdjustedEnd = "Start"; obj.StartAdjustmentMode = "Associative"
        obj.AdjustmentReference = (self.reference(point=(200, 0, 0)), ["Face3"])
        obj.AdjustmentGap = Quantity(20); obj.StartExtension = Quantity(80); obj.EndExtension = Quantity(50)
        proxy.execute(obj)
        self.assertVector(obj.EffectiveStartPoint, (220, 0, 0)); self.assertVector(obj.EffectiveEndPoint, (3050, 0, 0))
        self.assertEqual(obj.AdjustedLength, 2830)

    def test_associative_end_keeps_start_extension_and_ignores_end_extension(self):
        obj, proxy = self.create(); obj.AdjustmentReference = (self.reference(), ["Face3"])
        obj.StartExtension = Quantity(50); obj.EndExtension = Quantity(80); proxy.execute(obj)
        self.assertVector(obj.EffectiveStartPoint, (-50, 0, 0)); self.assertVector(obj.EffectiveEndPoint, (2800, 0, 0))
        self.assertEqual(obj.AdjustedLength, 2850)

    def test_inclined_3d_member_uses_infinite_plane(self):
        obj, proxy = self.create((0, 0, 0), (3000, 3000, 3000))
        obj.AdjustmentReference = (self.reference(point=(2800, 0, 0)), ["Face3"]); proxy.execute(obj)
        self.assertVector(obj.EffectiveEndPoint, (2800, 2800, 2800))
        self.assertAlmostEqual(obj.AdjustedLength, math.sqrt(3) * 2800)

    def test_reference_translation_rotation_and_combined_placement_update_cut(self):
        obj, proxy = self.create()
        reference = self.reference(point=(100, 0, 0), normal=(1, 0, 0))
        obj.AdjustmentReference = (reference, ["Face3"])
        reference.Placement = Placement(Vector(2600, 0, 0), Rotation()); proxy.execute(obj)
        self.assertEqual(obj.AdjustedLength, 2700)
        reference.local_face.point = Vector(0, 100, 0); reference.local_face.normal = Vector(0, 1, 0)
        reference.Placement = Placement(Vector(2700, 0, 0), Rotation(Vector(0, 0, 1), -90)); proxy.execute(obj)
        self.assertEqual(obj.AdjustedLength, 2800)

    def test_member_translation_rotation_and_recompute_have_no_drift(self):
        obj, proxy = self.create((0, 0, 0), (10, 0, 0))
        reference = self.reference(point=(4, 4, 0), normal=(1, 1, 0))
        obj.AdjustmentReference = (reference, ["Face3"]); proxy.execute(obj)
        self.assertEqual(obj.AdjustedLength, 8)
        rigid = Placement(Vector(), Rotation(Vector(0, 0, 1), 90))
        obj.Placement = rigid.multiply(obj.Placement); proxy.onChanged(obj, "Placement")
        for _ in range(4):
            proxy.execute(obj)
            self.assertVector(obj.StartPoint, (0, 0, 0)); self.assertVector(obj.EndPoint, (0, 10, 0))
            self.assertVector(obj.EffectiveEndPoint, (0, 8, 0)); self.assertEqual(obj.AdjustedLength, 8)

    def test_invalid_reference_parallel_cycle_and_inverted_length_are_safe(self):
        obj, proxy = self.create()
        invalid_values = [None, (self.reference(normal=(0, 1, 0)), ["Face3"]),
                          (Reference(planar=False), ["Face3"]), (self.reference(), ["Face99"])]
        for value in invalid_values:
            obj.AdjustmentReference = value; proxy.execute(obj)
            self.assertTrue(obj.Shape.empty); self.assertEqual(obj.AdjustedLength, 0); self.assertEqual(obj.TotalMass, 0)
        obj.AdjustmentReference = (obj, ["Face3"]); proxy.execute(obj)
        self.assertTrue(obj.Shape.empty); self.assertEqual(obj.AdjustedLength, 0)
        obj.AdjustmentReference = (self.reference(point=(-10, 0, 0)), ["Face3"]); proxy.execute(obj)
        self.assertTrue(obj.Shape.empty); self.assertEqual(obj.AdjustedLength, 0)
        self.assertVector(obj.EndPoint, (3000, 0, 0)); self.assertEqual(obj.MemberLength, 3000)
        obj.AdjustmentReference = (self.reference(normal=(1e-10, 1, 0)), ["Face3"]); proxy.execute(obj)
        self.assertTrue(obj.Shape.empty); self.assertEqual(obj.AdjustedLength, 0)

    def test_none_and_fixed_ignore_residual_reference(self):
        obj, proxy = self.create(); reference = self.reference(point=(100, 0, 0))
        obj.AdjustmentReference = (reference, ["Face3"])
        obj.EndAdjustmentMode = "None"; proxy.execute(obj); self.assertEqual(obj.AdjustedLength, 3000)
        obj.EndAdjustmentMode = "Fixed"; obj.FixedReferenceOffset = Quantity(100); proxy.execute(obj)
        self.assertEqual(obj.AdjustedLength, 2900)

    def test_restore_preserves_associative_link_face_mode_end_and_gap(self):
        obj, proxy = self.create(); reference = self.reference()
        obj.AdjustmentReference = (reference, ["Face3"]); obj.AdjustedEnd = "End"; obj.AdjustmentGap = Quantity(20)
        proxy.execute(obj)
        restored = self.proxy(); restored.__setstate__(None); restored.onDocumentRestored(obj); restored.execute(obj)
        self.assertIs(obj.AdjustmentReference[0], reference); self.assertEqual(obj.AdjustmentReference[1], ["Face3"])
        self.assertEqual(obj.EndAdjustmentMode, "Associative"); self.assertEqual(obj.AdjustedEnd, "End")
        self.assertEqual(obj.AdjustmentGap.Value, 20); self.assertEqual(obj.AdjustedLength, 2780)

    def test_plane_cut_orthogonal_uses_fast_extrusion_without_common(self):
        obj, proxy = self.create(); obj.AdjustmentGeometryMode = "PlaneCut"
        obj.AdjustmentReference = (self.reference(), ["Face3"]); proxy.execute(obj)
        self.assertFalse(obj.Shape.clipped); self.assertEqual(obj.AdjustedLength, 2800)

    def test_plane_cut_oblique_angles_normal_inversion_and_axial_gap(self):
        for angle in (75, 60, 45, 30):
            with self.subTest(angle=angle):
                obj, proxy = self.create(); obj.AdjustmentGeometryMode = "PlaneCut"
                tilt = math.radians(90 - angle)
                normal = (math.cos(tilt), math.sin(tilt), 0)
                reference = self.reference(normal=normal)
                obj.AdjustmentReference = (reference, ["Face3"]); obj.AdjustmentGap = Quantity(20)
                proxy.execute(obj)
                self.assertTrue(obj.Shape.clipped); self.assertEqual(obj.AdjustedLength, 2780)
                face = obj.Shape.half_space.face
                axis_point = Vector(0, 0, 2780)
                self.assertAlmostEqual(face.normal.dot(axis_point.sub(face.point)), 0.0)
                reference.local_face.normal = Vector(*(-value for value in normal)); proxy.execute(obj)
                self.assertTrue(obj.Shape.clipped); self.assertEqual(obj.AdjustedLength, 2780)
        obj.AdjustmentGap = Quantity(-20); proxy.execute(obj); self.assertEqual(obj.AdjustedLength, 2820)

    def test_plane_cut_tracks_rotated_reference_plane(self):
        obj, proxy = self.create(); obj.AdjustmentGeometryMode = "PlaneCut"
        reference = self.reference(point=(0, 0, 0), normal=(1, 0, 0),
                                   placement=Placement(Vector(2800, 0, 0), Rotation(Vector(0, 0, 1), 45)))
        obj.AdjustmentReference = (reference, ["Face3"]); proxy.execute(obj)
        first_normal = Vector(obj.Shape.half_space.face.normal)
        self.assertTrue(obj.Shape.clipped); self.assertEqual(obj.AdjustedLength, 2800)
        reference.Placement = Placement(Vector(2700, 0, 0), Rotation(Vector(0, 0, 1), 30)); proxy.execute(obj)
        self.assertTrue(obj.Shape.clipped); self.assertEqual(obj.AdjustedLength, 2700)
        self.assertNotEqual((first_normal.x, first_normal.y, first_normal.z),
                            (obj.Shape.half_space.face.normal.x, obj.Shape.half_space.face.normal.y,
                             obj.Shape.half_space.face.normal.z))

    def test_plane_cut_start_and_edge_combination_rules(self):
        obj, proxy = self.create(); obj.EndAdjustmentMode = "None"; obj.AdjustedEnd = "Start"; obj.StartAdjustmentMode = "Associative"; obj.AdjustmentGeometryMode = "PlaneCut"
        obj.AdjustmentReference = (self.reference(point=(200, 0, 0), normal=(1, 1, 0)), ["Face3"])
        obj.AdjustmentGap = Quantity(20); proxy.execute(obj)
        self.assertTrue(obj.Shape.clipped); self.assertVector(obj.EffectiveStartPoint, (220, 0, 0))
        face = obj.Shape.half_space.face
        self.assertAlmostEqual(face.normal.dot(Vector(0, 0, 0).sub(face.point)), 0.0)
        obj.AdjustmentReference = (EdgeReference((200, -1, 0), (200, 1, 0)), ["Edge3"]); proxy.execute(obj)
        self.assertTrue(obj.Shape.empty); self.assertEqual(obj.AdjustedLength, 0)

    def test_oblique_plane_cut_mass_uses_final_volume_over_section_area(self):
        obj, proxy = self.create(); obj.AdjustmentGeometryMode = "PlaneCut"
        obj.AdjustmentReference = (self.reference(normal=(1, 1, 0)), ["Face3"]); proxy.execute(obj)
        expected_equivalent_length = obj.Shape.Volume / 1000.0
        self.assertAlmostEqual(obj.TotalMass, 13.0 * expected_equivalent_length / 1000.0)

    def test_fixed_plane_cut_local_normal_tracks_member_and_keeps_gap_independent(self):
        obj, proxy = self.create((0, 0, 0), (3000, 0, 0))
        obj.EndAdjustmentMode = "Fixed"; obj.AdjustmentGeometryMode = "PlaneCut"
        obj.FixedReferenceOffset = Quantity(100); obj.AdjustmentGap = Quantity(20)
        component = 1.0 / math.sqrt(2.0)
        obj.FixedPlaneNormal = Vector(component, 0, component); proxy.execute(obj)
        self.assertTrue(obj.Shape.clipped); self.assertEqual(obj.AdjustedLength, 2880)
        rigid = Placement(Vector(10, 20, 30), Rotation(Vector(0, 0, 1), 90))
        obj.Placement = rigid.multiply(obj.Placement); proxy.onChanged(obj, "Placement")
        for _ in range(4):
            proxy.execute(obj); self.assertTrue(obj.Shape.clipped); self.assertEqual(obj.AdjustedLength, 2880)
            self.assertVector(obj.FixedPlaneNormal, (component, 0, component))
        obj.AdjustmentGap = Quantity(30); proxy.execute(obj)
        self.assertEqual(obj.AdjustedLength, 2870); self.assertEqual(obj.FixedReferenceOffset.Value, 100)
        obj.EndPoint = Vector(0, 3500, 30); proxy.onChanged(obj, "EndPoint"); proxy.execute(obj)
        self.assertAlmostEqual(obj.AdjustedLength, obj.MemberLength - 130)

    def test_fixed_plane_cut_null_normal_is_legacy_orthogonal_and_restore_preserves_oblique(self):
        obj, proxy = self.create(); obj.EndAdjustmentMode = "Fixed"; obj.AdjustmentGeometryMode = "PlaneCut"
        obj.FixedReferenceOffset = Quantity(100); obj.FixedPlaneNormal = Vector(); proxy.execute(obj)
        self.assertFalse(obj.Shape.clipped); self.assertEqual(obj.AdjustedLength, 2900)
        component = 1.0 / math.sqrt(2.0)
        obj.FixedPlaneNormal = Vector(component, 0, component); proxy.execute(obj)
        restored = self.proxy(); restored.__setstate__(None); restored.onDocumentRestored(obj); restored.execute(obj)
        self.assertEqual(obj.AdjustmentGeometryMode, "PlaneCut")
        self.assertVector(obj.FixedPlaneNormal, (component, 0, component))
        self.assertTrue(obj.Shape.clipped)

    def test_dual_length_limits_gaps_and_nominal_axis_are_independent(self):
        obj, proxy = self.create(); nominal = (Vector(obj.StartPoint), Vector(obj.EndPoint))
        obj.StartAdjustmentMode = "Associative"
        obj.StartAdjustmentReference = (self.reference(point=(200, 0, 0)), ["Face3"])
        obj.StartAdjustmentGap = Quantity(25)
        obj.EndAdjustmentReference = (self.reference(point=(2800, 0, 0)), ["Face3"])
        obj.EndAdjustmentGap = Quantity(-40); proxy.execute(obj)
        self.assertVector(obj.EffectiveStartPoint, (225, 0, 0))
        self.assertVector(obj.EffectiveEndPoint, (2840, 0, 0))
        self.assertEqual(obj.AdjustedLength, 2615)
        self.assertVector(obj.StartPoint, (nominal[0].x, nominal[0].y, nominal[0].z))
        self.assertVector(obj.EndPoint, (nominal[1].x, nominal[1].y, nominal[1].z))

    def test_dual_references_move_only_their_own_limit(self):
        obj, proxy = self.create(); start_ref = self.reference(point=(200, 0, 0)); end_ref = self.reference()
        obj.StartAdjustmentMode = "Associative"; obj.StartAdjustmentReference = (start_ref, ["Face3"])
        obj.EndAdjustmentReference = (end_ref, ["Face3"]); proxy.execute(obj)
        baseline_end = Vector(obj.EffectiveEndPoint)
        start_ref.Placement = Placement(Vector(100, 0, 0), Rotation()); proxy.execute(obj)
        self.assertVector(obj.EffectiveStartPoint, (300, 0, 0)); self.assertVector(obj.EffectiveEndPoint, (baseline_end.x, baseline_end.y, baseline_end.z))
        baseline_start = Vector(obj.EffectiveStartPoint)
        end_ref.Placement = Placement(Vector(-100, 0, 0), Rotation()); proxy.execute(obj)
        self.assertVector(obj.EffectiveStartPoint, (baseline_start.x, baseline_start.y, baseline_start.z))
        self.assertVector(obj.EffectiveEndPoint, (2700, 0, 0))

    def test_dual_extensions_are_suppressed_per_adjusted_side_and_reactivate(self):
        obj, proxy = self.create(); obj.EndAdjustmentMode = "None"
        obj.StartExtension = Quantity(50); obj.EndExtension = Quantity(80)
        obj.StartAdjustmentMode = "Associative"
        obj.StartAdjustmentReference = (self.reference(point=(200, 0, 0)), ["Face3"])
        proxy.execute(obj)
        self.assertVector(obj.EffectiveStartPoint, (200, 0, 0)); self.assertVector(obj.EffectiveEndPoint, (3080, 0, 0))
        obj.EndAdjustmentMode = "Associative"
        obj.EndAdjustmentReference = (self.reference(point=(2800, 0, 0)), ["Face3"]); proxy.execute(obj)
        self.assertVector(obj.EffectiveEndPoint, (2800, 0, 0))
        obj.StartAdjustmentMode = "None"; obj.StartAdjustmentReference = None; proxy.execute(obj)
        self.assertVector(obj.EffectiveStartPoint, (-50, 0, 0)); self.assertVector(obj.EffectiveEndPoint, (2800, 0, 0))

    def test_dual_plane_cut_and_mixed_modes_are_valid(self):
        for start_geometry, end_geometry in (("PlaneCut", "PlaneCut"),
                                              ("PlaneCut", "LengthLimit"),
                                              ("LengthLimit", "PlaneCut"),
                                              ("LengthLimit", "LengthLimit")):
            with self.subTest(start=start_geometry, end=end_geometry):
                obj, proxy = self.create(); obj.StartAdjustmentMode = "Fixed"
                obj.StartAdjustmentGeometryMode = start_geometry; obj.StartFixedReferenceOffset = Quantity(200)
                obj.StartFixedPlaneNormal = Vector(1, 0, 1)
                obj.EndAdjustmentGeometryMode = end_geometry; obj.EndAdjustmentReference = (self.reference(normal=(1, 1, 0)), ["Face3"])
                proxy.execute(obj)
                self.assertFalse(obj.Shape.empty); self.assertGreater(obj.Shape.Volume, 0)
                self.assertEqual(obj.AdjustedLength, 2600)

    def test_fixed_and_associative_slots_remain_independent(self):
        obj, proxy = self.create(); start_ref = self.reference(point=(200, 0, 0)); end_ref = self.reference()
        obj.StartAdjustmentMode = "Fixed"; obj.StartFixedReferenceOffset = Quantity(200)
        obj.EndAdjustmentReference = (end_ref, ["Face3"]); proxy.execute(obj)
        before_start = Vector(obj.EffectiveStartPoint)
        start_ref.Placement = Placement(Vector(500, 0, 0), Rotation())
        end_ref.Placement = Placement(Vector(-100, 0, 0), Rotation()); proxy.execute(obj)
        self.assertVector(obj.EffectiveStartPoint, (before_start.x, before_start.y, before_start.z))
        self.assertVector(obj.EffectiveEndPoint, (2700, 0, 0))

    def test_crossed_dual_limits_fail_safely(self):
        obj, proxy = self.create(); obj.StartAdjustmentMode = "Fixed"
        obj.StartFixedReferenceOffset = Quantity(2000)
        obj.EndAdjustmentMode = "Fixed"; obj.EndFixedReferenceOffset = Quantity(1500)
        proxy.execute(obj)
        self.assertTrue(obj.Shape.empty); self.assertEqual(obj.AdjustedLength, 0)


if __name__ == "__main__":
    unittest.main()
