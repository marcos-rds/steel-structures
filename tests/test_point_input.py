"""Pure conversions with translated XY/XZ/YZ/inclined orthonormal frames."""
import math
import importlib.util
from pathlib import Path
import sys
import unittest

spec = importlib.util.spec_from_file_location(
    "_pure_point_input", Path(__file__).resolve().parents[1]
    / "freecad/SteelStructures/interactive/point_input.py")
model = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = model
spec.loader.exec_module(model)
Mode, Ref = model.CoordinateMode, model.CoordinateReference
PointCandidate, PointInputPlane, PointInputSpec = (
    model.PointCandidate, model.PointInputPlane, model.PointInputSpec)


class PointInputTests(unittest.TestCase):
    def assertPoint(self, expected, actual):
        for a, b in zip(expected, actual):
            self.assertAlmostEqual(a, b, places=9)

    def frames(self):
        a = math.sqrt(.5)
        return (
            PointInputPlane((10, -20, 30), (1, 0, 0), (0, 1, 0), (0, 0, 1)),
            PointInputPlane((10, -20, 30), (1, 0, 0), (0, 0, 1), (0, -1, 0)),
            PointInputPlane((10, -20, 30), (0, 1, 0), (0, 0, 1), (1, 0, 0)),
            PointInputPlane((10, -20, 30), (a, 0, a), (0, 1, 0), (-a, 0, a)),
        )

    def test_global_absolute_negative(self):
        candidate = PointInputSpec().candidate((-10, 0, 3.5))
        self.assertEqual((-10, 0, 3.5), candidate.world)

    def test_global_relative(self):
        spec = PointInputSpec(Ref.GLOBAL, Mode.RELATIVE)
        self.assertEqual((8, -17, 30), spec.candidate((-2, 3, 0),
                                                   last_point=(10, -20, 30)).world)

    def test_plane_absolute_and_relative_all_frames(self):
        for plane in self.frames():
            with self.subTest(plane=plane):
                absolute = PointInputSpec(Ref.PLANE)
                first = absolute.candidate((4, -3), plane=plane)
                expected = tuple(o + 4 * u - 3 * v
                                 for o, u, v in zip(plane.origin, plane.u, plane.v))
                self.assertPoint(expected, first.world)
                relative = PointInputSpec(Ref.PLANE, Mode.RELATIVE)
                second = relative.candidate((-8, 5), plane=plane, last_point=first.world)
                self.assertPoint(absolute.candidate((-4, 2), plane=plane).world, second.world)

    def test_references_and_modes_preserve_candidate_all_frames(self):
        for plane in self.frames():
            with self.subTest(plane=plane):
                candidate = PointInputSpec(Ref.PLANE).candidate((-12, 7), plane=plane)
                last = PointInputSpec(Ref.PLANE).candidate((6, -5), plane=plane).world
                for reference in Ref:
                    for mode in Mode:
                        spec = PointInputSpec(reference, mode)
                        values = spec.present(candidate, plane=plane, last_point=last)
                        restored = spec.candidate(values, plane=plane, last_point=last)
                        self.assertPoint(candidate.world, restored.world)

    def test_absolute_relative_values(self):
        candidate = PointCandidate((-5, 10, 3))
        spec = PointInputSpec(Ref.GLOBAL, Mode.RELATIVE)
        self.assertEqual((-7, 7, -1), spec.present(candidate, last_point=(2, 3, 4)))
        self.assertEqual(candidate.world, PointInputSpec().present(candidate))

    def test_relative_requires_last_point(self):
        for reference in Ref:
            spec = PointInputSpec(reference, Mode.RELATIVE)
            with self.assertRaises(ValueError):
                spec.candidate((1, 2, 3) if reference == Ref.GLOBAL else (1, 2),
                               plane=self.frames()[0])
            with self.assertRaises(ValueError):
                spec.present(PointCandidate((1, 2, 3)), plane=self.frames()[0])

    def test_plane_requires_defined_frame(self):
        with self.assertRaisesRegex(ValueError, "ainda não"):
            PointInputSpec(Ref.PLANE).candidate((1, 2))
        with self.assertRaises(ValueError):
            PointInputSpec(Ref.PLANE).present(PointCandidate((1, 2, 0)))

    def test_presentation_does_not_project_off_plane(self):
        with self.assertRaisesRegex(ValueError, "fora do plano"):
            PointInputSpec(Ref.PLANE).present(PointCandidate((10, -20, 31)),
                                             plane=self.frames()[0])

    def test_incomplete_invalid_and_nonfinite(self):
        for values in ((), (1, 2), (1, 2, 3, 4), (None, 1, 2), ("-", 1, 2),
                       ("2 cm", 1, 2), (float("nan"), 1, 2),
                       (1, float("inf"), 2), (1, 2, -float("inf"))):
            with self.subTest(values=values), self.assertRaises(ValueError):
                PointInputSpec().candidate(values)
        with self.assertRaises(ValueError):
            PointInputSpec(Ref.PLANE).candidate((1, float("nan")), plane=self.frames()[0])

    def test_candidate_is_immutable(self):
        values = [1, 2, 3]
        candidate = PointCandidate(values)
        values[0] = 7
        self.assertEqual((1, 2, 3), candidate.world)


if __name__ == "__main__":
    unittest.main()
