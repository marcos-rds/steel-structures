"""Geometry domain, endpoint conventions and symmetric selection order."""
import math
import unittest

from freecad.SteelStructures.member_miter_geometry import resolve_miter, MiterValidationError, dot


class MiterGeometryTests(unittest.TestCase):
    def pair(self, angle=90., reverse_a=False, reverse_b=False, gap=50., scale=1.):
        rays = ((1., 0., 0.), (math.cos(math.radians(angle)), math.sin(math.radians(angle)), 0.))
        axes = []
        for ray, reverse in zip(rays, (reverse_a, reverse_b)):
            axis = [tuple(v*d*scale for v in ray) for d in (gap, 1000.)]
            axes.extend(axis[::-1] if reverse else axis)
        return axes

    def test_right_and_oblique_angles(self):
        for angle in (30., 60., 90., 135., 170.):
            with self.subTest(angle=angle):
                p = resolve_miter(*self.pair(angle))
                self.assertAlmostEqual(p.angle_degrees, angle)
                self.assertTrue(all(abs(v) < 1e-9 for v in p.point))
                self.assertLess(dot(p.normal, p.inward[0])*dot(p.normal, p.inward[1]), 0)
                self.assertEqual(p.ends, ("Start", "Start"))

    def test_start_end_combinations_and_order_invariance(self):
        for reverse_a, reverse_b in ((False, False), (False, True), (True, False), (True, True)):
            for angle in (60., 90., 135.):
                with self.subTest(reverse_a=reverse_a, reverse_b=reverse_b, angle=angle):
                    axes = self.pair(angle, reverse_a, reverse_b)
                    p = resolve_miter(*axes)
                    q = resolve_miter(*(axes[2:]+axes[:2]))
                    self.assertEqual(p.ends, tuple("End" if v else "Start" for v in (reverse_a, reverse_b)))
                    self.assertEqual(p.ends, q.ends[::-1])
                    for a, b in zip(p.normal, q.normal): self.assertAlmostEqual(a, b)
                    for a, b in zip(p.point, q.point): self.assertAlmostEqual(a, b)
                    for a, b in zip(p.stations, q.stations[::-1]): self.assertAlmostEqual(a, b)

    def test_coincident_endpoints(self):
        self.assertEqual(resolve_miter(*self.pair(gap=0)).stations, (0., 0.))

    def test_inclined_plane_translation_and_scale(self):
        for scale in (.01, 1., 1000.):
            axes = self.pair(60., scale=scale)
            # Rigid transform (x,y,z)->(z,x,y), then global translation.
            axes = [(p[2]+1e4, p[0]+2e4, p[1]+3e4) for p in axes]
            plan = resolve_miter(*axes)
            for a, b in zip(plan.point, (1e4, 2e4, 3e4)): self.assertAlmostEqual(a, b, places=7)
            self.assertAlmostEqual(plan.angle_degrees, 60.)

    def test_skew_axes_are_not_projected_to_a_joint(self):
        axes = self.pair()
        axes[2:] = [(x, y, z+1) for x, y, z in axes[2:]]
        with self.assertRaisesRegex(MiterValidationError, "mesmo plano"):
            resolve_miter(*axes)

    def test_parallel_and_collinear_rejected(self):
        for a, b in (((0, 1, 0), (1000, 1, 0)), ((-1000, 0, 0), (0, 0, 0))):
            with self.assertRaisesRegex(MiterValidationError, "paralelos"):
                resolve_miter((0, 0, 0), (1000, 0, 0), a, b)

    def test_nearly_parallel_rejected_before_unstable_intersection(self):
        with self.assertRaisesRegex(MiterValidationError, "paralelos"):
            resolve_miter(*self.pair(.00001))

    def test_t_and_crossing_rejected(self):
        for axes in (((-100, 0, 0), (100, 0, 0), (0, 0, 0), (0, 100, 0)),
                     ((-100, 0, 0), (100, 0, 0), (0, -100, 0), (0, 100, 0))):
            with self.assertRaisesRegex(MiterValidationError, "interior"):
                resolve_miter(*axes)

    def test_small_terminal_overrun_is_not_silently_classified_by_distance(self):
        # The same short tail can belong to a continuous member or to a corner
        # awaiting trimming. There is no retained-side intent in these inputs.
        for angle in (60., 90., 120.):
            for excess in (.001, 1., 50.):
                axes = self.pair(angle, gap=0.)
                axes[0] = (-excess, 0., 0.)
                for order in (axes, axes[2:]+axes[:2]):
                    with self.subTest(angle=angle, excess=excess), self.assertRaisesRegex(
                            MiterValidationError, "interior"):
                        resolve_miter(*order)

    def test_zero_length_and_nonfinite_rejected(self):
        with self.assertRaisesRegex(MiterValidationError, "nulo"):
            resolve_miter((0, 0, 0), (0, 0, 0), (0, 0, 0), (0, 1, 0))
        for value in (math.nan, math.inf, -math.inf):
            with self.assertRaisesRegex(MiterValidationError, "inválidas"):
                resolve_miter((value, 0, 0), (1, 0, 0), (0, 0, 0), (0, 1, 0))

    def test_finite_coordinates_that_overflow_axis_length_are_rejected(self):
        with self.assertRaisesRegex(MiterValidationError, "escala numérica"):
            resolve_miter((0, 0, 0), (1e200, 0, 0), (0, 0, 0), (0, 1e200, 0))


if __name__ == "__main__": unittest.main()
