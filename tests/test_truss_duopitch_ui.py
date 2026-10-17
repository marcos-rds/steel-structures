"""Focused panel/preview contracts for DuoPitch support geometry."""

from copy import deepcopy
import unittest

from tests.test_truss_task_panel import (
    Check, Combo, Controller, Number, config_fixture, make_panel, preview_module,
)


class DuoPitchControlsTests(unittest.TestCase):
    def panel(self):
        panel = make_panel()
        panel.envelope_type = Combo("DuoPitch")
        panel.left_end_height = Number(300)
        panel.right_end_height = Number(700)
        panel.link_end_heights = Check(False)
        panel.reference_alignment = Combo("TopChordSupports")
        return panel

    def test_independent_heights_and_alignment_reach_controller_config(self):
        panel = self.panel()
        config = panel.get_config()
        self.assertEqual((config["left_end_height"], config["right_end_height"]), (300, 700))
        self.assertFalse(config["link_end_heights"])
        self.assertEqual(config["reference_alignment"], "TopChordSupports")

    def test_link_uses_left_height_and_updates_right_control(self):
        panel = self.panel()
        panel.link_end_heights.value = True
        panel._refresh = lambda: None
        panel._end_heights_changed()
        self.assertEqual(panel.right_end_height.value(), 300)
        panel.left_end_height.setValue(450)
        panel._end_heights_changed()
        self.assertEqual(panel.right_end_height.value(), 450)
        self.assertEqual(panel.get_config()["right_end_height"], 450)

    def test_unlink_preserves_distinct_values(self):
        panel = self.panel()
        panel._refresh = lambda: None
        panel._end_heights_changed()
        self.assertEqual(panel.right_end_height.value(), 700)

    def test_controls_update_draft_without_mutating_loaded_baseline(self):
        panel = self.panel()
        original = panel.session.baseline_config
        panel.get_config()
        self.assertEqual(panel.session.baseline_config, original)
        self.assertEqual(panel.session.config["envelope_type"], "DuoPitch")


class DuoPitchPreviewTests(unittest.TestCase):
    def model(self):
        model = Controller().preview(config_fixture())
        model.update(envelope_type="DuoPitch", reference_alignment="BottomChord")
        model["envelope"] = {"top": [[0, 300, 0], [5, 1000, 0], [10, 700, 0]],
                             "bottom": [[0, 0, 0], [10, 0, 0]]}
        return model

    def envelope(self, model):
        return preview_module.graph_presentation(model)[2]

    def test_asymmetric_heights_are_shown_at_both_ends(self):
        model = self.model()
        dimensions = preview_module.end_height_presentation(model, self.envelope(model))
        self.assertEqual(dimensions, (((0, -300), (0, 0), "E: 300.00 mm"),
                                      ((10, -700), (10, 0), "D: 700.00 mm")))

    def test_zero_heights_add_no_overlapping_dimensions(self):
        model = self.model()
        model["envelope"]["top"][0][1] = 0
        model["envelope"]["top"][-1][1] = 0
        self.assertEqual(preview_module.end_height_presentation(model, self.envelope(model)), ())

    def test_bottom_reference_uses_bottom_endpoints(self):
        model = self.model()
        result = preview_module.reference_presentation(model, self.envelope(model))
        self.assertEqual(result[:2], ((0, 0), (10, 0)))

    def test_upper_reference_uses_computed_physical_points(self):
        model = self.model()
        model.update(reference_alignment="TopChordSupports",
                     support_reference_local=[[0, 325, 0], [10, 726, 0]])
        result = preview_module.reference_presentation(model, self.envelope(model))
        self.assertEqual(result[:2], ((0, -325), (10, -726)))
        self.assertEqual(len(result), 2)  # reference has no repeated caption

    def test_bottom_face_uses_physical_points_in_both_forms(self):
        for kind in ("Parallel", "DuoPitch"):
            model = self.model()
            model.update(envelope_type=kind, reference_surface="OuterFace",
                         support_reference_local=[[0, -25.4, 0], [10, -25.4, 0]])
            self.assertEqual(preview_module.reference_presentation(model, self.envelope(model)),
                             ((0, 25.4), (10, 25.4)))
            model.pop("support_reference_local")
            self.assertIsNone(preview_module.reference_presentation(model, self.envelope(model)))

    def test_upper_reference_never_guesses_profile_offset(self):
        model = self.model()
        model["reference_alignment"] = "TopChordSupports"
        self.assertIsNone(preview_module.reference_presentation(model, self.envelope(model)))

    def test_invalid_physical_points_are_rejected(self):
        model = self.model()
        model.update(reference_alignment="TopChordSupports",
                     support_reference_local=[[0, float("nan"), 0], [10, 1, 0]])
        with self.assertRaises(ValueError):
            preview_module.reference_presentation(model, self.envelope(model))

    def test_parallel_preview_dimensions_constant_nominal_height(self):
        model = self.model()
        model["envelope_type"] = "Parallel"
        model["envelope"]["top"] = [[0, 1000, 0], [10, 1000, 0]]
        envelope = self.envelope(model)
        self.assertEqual(preview_module.reference_presentation(model, envelope), ((0, 0), (10, 0)))
        self.assertEqual(preview_module.end_height_presentation(model, envelope),
                         (((0, -1000), (0, 0), "1000.00 mm"),))

    def test_dimensions_stay_outside_contour_with_fixed_pixel_spacing(self):
        for height in (120, 170, 250):
            for extent in (.01, 5., 100.):
                for side, x in ((-1, 40.), (1, 440.)):
                    top, bottom = (x, height-20.-extent), (x, height-20.)
                    lines, label = preview_module.dimension_layout(top, bottom, side, 80., height)
                    self.assertTrue(all((xx-x)*side > 0 for line in lines for xx in (line[0], line[2])))
                    self.assertEqual(lines[0][1], top[1])
                    self.assertEqual(lines[1][1], bottom[1])
                    self.assertEqual(label[0], x+side*25.)
                    self.assertGreaterEqual(label[1]-40., 5.)
                    self.assertLessEqual(label[1]+40., height-5.)


if __name__ == "__main__":
    unittest.main()
