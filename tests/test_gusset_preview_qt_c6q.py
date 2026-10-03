"""Isolated Qt tests: no FreeCAD import, process, document, or GUI automation.

Run with a Python providing PySide6; otherwise these focused tests are skipped.
"""

import copy
from dataclasses import asdict, replace
import importlib
import os
from pathlib import Path
import sys
from time import perf_counter
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import patch

from freecad.SteelStructures.trusses.envelope import paths
from freecad.SteelStructures.trusses.gusset_presentation import (
    GussetTransverseView, TransverseComponent,
)
from freecad.SteelStructures.trusses.models import EnvelopeDefinition
from freecad.SteelStructures.trusses.realization import build_candidate, reference_frame
from tests.test_gusset_presentation_c6q import preview_config, resolved_preview
from tests.test_gusset_plate_c6a import configured
from tests.test_ridge_fitting import ridge_config
from tests.test_truss_manual_fixes import definition

try:
    from PySide6 import QtCore, QtGui, QtWidgets
    import shiboken6
except ImportError:
    QtWidgets = None


def controller_class():
    namespace = dict(asdict=asdict, perf_counter=perf_counter,
                     EnvelopeDefinition=EnvelopeDefinition, paths=paths,
                     reference_frame=reference_frame,
                     __package__="freecad.SteelStructures.interactive")
    for name in ("_candidate_center", "_deduplicated_transverse_candidates",
                 "_transverse_placement_regions", "_resolved_transverse_key",
                 "TrussController"):
        definition("interactive/truss_controller.py", name, namespace)
    return namespace["TrussController"]


@unittest.skipIf(QtWidgets is None, "PySide6 não disponível neste Python")
class TransverseQtTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        # interactive.__init__ imports unrelated document controllers. Load
        # only the tested UI modules, without executing that GUI entry point.
        package = ModuleType("freecad.SteelStructures.interactive")
        package.__path__ = [str(Path(__file__).resolve().parents[1]
                               / "freecad/SteelStructures/interactive")]
        cls.modules = patch.dict(sys.modules, {
            "freecad.SteelStructures.interactive": package,
            "PySide": SimpleNamespace(QtCore=QtCore, QtGui=QtGui, QtWidgets=QtWidgets),
            "FreeCAD": None, "FreeCADGui": None, "Part": None})
        cls.modules.start()
        cls.addClassCleanup(cls.modules.stop)
        cls.preview_module = importlib.import_module(
            "freecad.SteelStructures.interactive.gusset_section_preview")
        cls.editor_module = importlib.import_module(
            "freecad.SteelStructures.interactive.truss_topology_editor")

    def setUp(self):
        self.parents = []
        self.errors = []
        self.old_hook = sys.excepthook
        sys.excepthook = lambda kind, error, trace: self.errors.append(str(error))

    def flush(self):
        self.app.processEvents()
        self.app.sendPostedEvents(None, QtCore.QEvent.DeferredDelete)
        self.app.processEvents()

    def tearDown(self):
        for parent in self.parents:
            if shiboken6.isValid(parent):
                parent.deleteLater()
        self.flush()
        sys.excepthook = self.old_hook
        self.assertEqual(self.errors, [])

    def make_editor(self, designation='U 4" x 8,04', rotation=0.):
        value, node = preview_config(designation, rotation=rotation)
        form = QtWidgets.QWidget()
        self.parents.append(form)
        controller = object.__new__(controller_class())
        controller.timings = {}

        def candidate(config):
            controller.last_candidate = build_candidate(config)
            return controller.last_candidate

        controller.candidate = candidate
        panel = SimpleNamespace(form=form, controller=controller, _initial=value)
        panel.get_config = lambda: copy.deepcopy(panel._initial)
        panel.set_connection_intent = lambda key, intent: panel._initial[
            "connection_intents"].__setitem__(key, copy.deepcopy(intent))
        editor = self.editor_module.TopologyEditor(panel)
        editor.select_node(node)
        return editor, panel, node

    def test_editor_selection_thickness_region_position_and_connection_type(self):
        editor, panel, node = self.make_editor()
        preview = editor.transverse_preview
        self.assertTrue(preview.canvas._views)
        editor.gusset_plate.setValue(12.)
        self.assertAlmostEqual(preview.canvas._views[0].plate[1][0]
                               -preview.canvas._views[0].plate[0][0], 12.)
        external = editor.gusset_region.findData("external")
        self.assertGreater(external, 0)
        editor.gusset_region.setCurrentIndex(external)
        first = preview.canvas._views[0].plate
        editor.gusset_position.setCurrentIndex(editor.gusset_position.count()-1)
        self.assertNotEqual(first, preview.canvas._views[0].plate)
        self.assertIn("Externa", preview.caption.text())
        other = next(n.key for n in panel.controller.last_candidate.graph.nodes if n.key != node)
        editor.select_node(other)
        self.assertEqual(preview.canvas._views, ())
        editor.select_node(node)
        self.assertTrue(preview.canvas._views)
        editor.connection_type.setCurrentIndex(editor.connection_type.findData("Direct"))
        self.assertEqual(preview.canvas._views, ())
        editor.connection_type.setCurrentIndex(editor.connection_type.findData("Gusset"))
        self.assertTrue(preview.canvas._views)
        editor.select_node(None)
        self.assertEqual(preview.canvas._views, ())

    def test_w_automatic_explicit_and_internal_switches_track_physical_views(self):
        for profile, rotation in ((p, r) for p in ("W 150 x 13,0", 'I 3" x 8,48')
                                  for r in (0., 90.)):
            with self.subTest(profile=profile, rotation=rotation):
                editor, _panel, _node = self.make_editor(
                    profile, rotation=rotation)
                preview = editor.transverse_preview
                automatic = preview.canvas._views[0].plate
                self.assertIn("Automática:", preview.caption.text())
                data = editor._gusset_preview_options()
                key = data["resolved_transverse_placement"]
                region = next(region for region, _label, positions in data["transverse_regions"]
                              if any(candidate == key for candidate, _name in positions))
                editor.gusset_region.setCurrentIndex(
                    editor.gusset_region.findData(region))
                editor.gusset_position.setCurrentIndex(editor.gusset_position.findData(key))
                manual = preview.canvas._views[0].plate
                self.assertEqual(automatic, manual)
                editor.gusset_region.setCurrentIndex(editor.gusset_region.findData("external"))
                first = preview.canvas._views[0].plate
                editor.gusset_position.setCurrentIndex(1)
                self.assertNotEqual(first, preview.canvas._views[0].plate)
                internal_index = editor.gusset_region.findData("internal")
                self.assertGreater(internal_index, 0)
                editor.gusset_region.setCurrentIndex(internal_index)
                self.assertEqual(editor.gusset_position.count(), 3)
                for index in range(3):
                    editor.gusset_position.setCurrentIndex(index)
                    self.assertTrue(preview.canvas._views[0].plate)
                    preview.canvas.grab()
                editor.gusset_region.setCurrentIndex(0)
                self.assertEqual(preview.canvas._views[0].plate, automatic)

    def test_recess_options_follow_thickness_without_stale_preview(self):
        for profile in ("W 150 x 13,0", 'I 3" x 8,48'):
            editor, _panel, _node = self.make_editor(profile, rotation=90.)
            editor.gusset_region.setCurrentIndex(editor.gusset_region.findData("internal"))
            editor.gusset_plate.setValue(150.)
            self.assertEqual(editor.gusset_region.findData("internal"), -1)
            plate = editor.transverse_preview.canvas._views[0].plate
            self.assertAlmostEqual(plate[1][0]-plate[0][0], 150.)
            editor.gusset_plate.setValue(8.)
            self.assertGreater(editor.gusset_region.findData("internal"), 0)

    def test_hover_has_no_canvas_tooltip_and_preserves_diagnostics_and_controls(self):
        editor, _panel, _node = self.make_editor("W 150 x 13,0", rotation=90.)
        preview = editor.transverse_preview
        editor.show()
        self.flush()
        self.assertEqual(preview.canvas.toolTip(), "")
        self.assertEqual(preview.toolTip(), "")
        self.assertTrue(editor.gusset_region.toolTip())
        self.assertTrue(editor.gusset_position.toolTip())
        before = editor.message.text()
        self.assertTrue(before)
        QtWidgets.QToolTip.hideText()
        point = QtCore.QPoint(60, 60)
        self.app.sendEvent(preview.canvas, QtGui.QHelpEvent(
            QtCore.QEvent.ToolTip, point, preview.canvas.mapToGlobal(point)))
        self.flush()
        self.assertFalse(QtWidgets.QToolTip.isVisible())
        self.assertEqual(editor.message.text(), before)

    def test_connection_layout_keeps_schematic_full_width_and_selectors_by_view(self):
        editor, _panel, _node = self.make_editor()
        editor.show()
        self.flush()
        preview = editor.transverse_preview
        self.assertGreaterEqual(editor.canvas.width(), 650)
        self.assertGreater(editor.canvas.width(), preview.width())
        self.assertLessEqual(editor.width(), 1000)
        self.assertLessEqual(preview.mapTo(editor, QtCore.QPoint(preview.width(), 0)).x(),
                             editor.width())
        self.assertGreater(preview.mapTo(editor, QtCore.QPoint(0, 0)).y(),
                           editor.canvas.mapTo(editor, QtCore.QPoint(0, 0)).y())
        self.assertIs(editor.connection_box.layout().itemAt(1).widget(), preview)
        self.assertIs(editor.gusset_region.parentWidget(), preview)
        self.assertIs(editor.gusset_position.parentWidget(), preview)
        self.assertGreater(editor.gusset_region.mapTo(preview, QtCore.QPoint(0, 0)).y(),
                           preview.canvas.mapTo(preview, QtCore.QPoint(0, 0)).y())
        self.assertIsNotNone(editor._transverse_form.labelForField(editor.gusset_region))
        self.assertIsNotNone(editor._transverse_form.labelForField(editor.gusset_position))
        self.assertFalse(hasattr(preview, "legend"))
        self.assertFalse(preview.section_selector.isVisible())
        editor.connection_type.setCurrentIndex(editor.connection_type.findData("Direct"))
        self.assertFalse(editor.gusset_region.isVisible())
        self.assertFalse(editor.gusset_position.isVisible())

    def test_equivalent_ridge_views_collapse_and_distinct_views_switch_compactly(self):
        value = configured(ridge_config(), "T_S_APEX", chord_contact="TrussInterior")
        _, _, views = resolved_preview(value, "T_S_APEX")
        self.assertEqual(len(views), 2)
        preview = self.preview_module.GussetSectionPreview()
        self.parents.append(preview)
        preview.set_preview(views, "Automática")
        self.assertEqual(len(preview._views), 1)
        self.assertEqual(preview.section_selector.count(), 1)
        self.assertEqual(len(preview.canvas._views), 1)
        self.assertFalse(preview.section_selector.isVisible())
        distinct = replace(views[1], label="Outro banzo",
                           plate=tuple((x+4., y) for x, y in views[1].plate))
        preview.set_preview((views[0], distinct), "Posição selecionada")
        self.assertEqual(preview.section_selector.count(), 2)
        preview.show()
        self.flush()
        self.assertTrue(preview.section_selector.isVisible())
        self.assertEqual(preview.canvas.minimumHeight(), 210)
        preview.section_selector.setCurrentIndex(1)
        self.assertEqual(preview.canvas._views, (distinct,))
        preview.set_preview((views[0], distinct), "Espessura modificada")
        self.assertEqual(preview.section_selector.currentIndex(), 1)

    def test_physical_config_refresh_updates_existing_widget(self):
        editor, panel, _node = self.make_editor()
        canvas = editor.transverse_preview.canvas
        before = canvas._views[0].components
        panel._initial["role_specs"]["BOTTOM_CHORD"]["rotation"] = 90.
        editor.canvas.refresh_candidate()
        self.assertIs(editor.transverse_preview.canvas, canvas)
        self.assertNotEqual(before, canvas._views[0].components)

    def test_invalid_edit_clears_transverse_even_when_schematic_keeps_last_valid(self):
        editor, _panel, node = self.make_editor()
        self.assertTrue(editor.transverse_preview.canvas._views)
        editor.gusset_plate.setValue(0.)
        self.assertTrue(editor.canvas._last_model["gussets"])
        self.assertIn(node, editor.canvas._last_model["gusset_diagnostic_nodes"])
        self.assertEqual(editor.transverse_preview.canvas._views, ())
        self.assertIn("indisponível", editor.transverse_preview.caption.text())
        editor.gusset_plate.setValue(10.)
        self.assertTrue(editor.transverse_preview.canvas._views)

    def test_failed_candidate_does_not_leave_previous_section(self):
        editor, panel, _node = self.make_editor()
        with patch.object(panel.controller, "preview", side_effect=ValueError("Invalid profile")):
            editor.gusset_plate.setValue(12.)
        self.assertEqual(editor.transverse_preview.canvas._views, ())
        self.assertEqual(editor.message.text(), "Invalid profile")

    def test_selection_and_resize_do_not_call_controller_or_resolver(self):
        editor, panel, node = self.make_editor()
        with patch.object(panel.controller, "preview", side_effect=AssertionError("Recomputed")):
            editor.select_node(None)
            editor.select_node(node)
            editor.resize(1100, 900)
            editor.transverse_preview.canvas.grab()
            self.flush()

    def test_repeated_create_close_delete_drains_pending_paint_events(self):
        for _ in range(4):
            editor, panel, _node = self.make_editor()
            preview = editor.transverse_preview
            canvas = preview.canvas
            selector = preview.section_selector
            editor.show()
            canvas.update()
            editor.reject()
            editor.deleteLater()
            self.flush()
            self.assertFalse(shiboken6.isValid(editor))
            self.assertFalse(shiboken6.isValid(preview))
            self.assertFalse(shiboken6.isValid(canvas))
            self.assertFalse(shiboken6.isValid(selector))
            # A subsequent model refresh has no registered callbacks to old UI.
            panel.controller.preview(panel.get_config())
            self.flush()

    def test_holes_stay_empty_and_material_visible_in_light_and_dark_palettes(self):
        value, node = preview_config("SHS 40x40x1,2")
        _, _, views = resolved_preview(value, node)
        canvas = self.preview_module.GussetSectionCanvas()
        self.parents.append(canvas)
        canvas.resize(270, 210)
        canvas.set_views(views)
        view = views[0]
        viewport = self.preview_module.fit_transverse_bounds(view.bounds, 270, 160)
        hole = view.components[0].holes[0]
        center = (sum(p[0] for p in hole)/len(hole), sum(p[1] for p in hole)/len(hole))
        x, y = viewport.point(center)
        for background, foreground in (("#ffffff", "#202020"), ("#252525", "#eeeeee")):
            palette = QtGui.QPalette()
            palette.setColor(QtGui.QPalette.Base, QtGui.QColor(background))
            palette.setColor(QtGui.QPalette.Text, QtGui.QColor(foreground))
            canvas.setPalette(palette)
            image = canvas.grab().toImage()
            self.assertEqual(image.pixelColor(round(x), round(y+42)).name(), background)
            colors = {image.pixelColor(px, py).name()
                      for px in range(image.width()) for py in range(30, image.height())}
            self.assertGreater(len(colors), 10)
        self.assertIsNone(sys.modules["FreeCAD"])

    def test_profile_has_soft_fill_and_clear_outline_across_native_palette_values(self):
        component = TransverseComponent(
            "A", ((0., 0.), (80., 0.), (80., 60.), (0., 60.)),
            (((20., 20.), (60., 20.), (60., 40.), (20., 40.)),))
        view = GussetTransverseView(
            "chord", "Banzo", (component,),
            ((80., 0.), (90., 0.), (90., 60.), (80., 60.)))
        canvas = self.preview_module.GussetSectionCanvas()
        self.parents.append(canvas)
        canvas.resize(280, 210)
        canvas.set_views((view,))
        viewport = self.preview_module.fit_transverse_bounds(view.bounds, 280, 160)
        for base, fill, edge in (("#ffffff", "#bed3e3", "#365b78"),
                                 ("#f4f4f4", "#bed3e3", "#365b78"),
                                 ("#252525", "#527694", "#d2e5f2")):
            palette = QtGui.QPalette()
            palette.setColor(QtGui.QPalette.Base, QtGui.QColor(base))
            canvas.setPalette(palette)
            image = canvas.grab().toImage()
            x, y = viewport.point((10., 10.))
            self.assertEqual(image.pixelColor(round(x), round(y+42)).name(), fill)
            x, y = viewport.point((40., 30.))
            self.assertEqual(image.pixelColor(round(x), round(y+42)).name(), base)
            colors = {image.pixelColor(px, py).name()
                      for px in range(image.width()) for py in range(image.height())}
            self.assertIn(edge, colors)
            self.assertIn("#e6aa50" if base == "#252525" else "#9a5100", colors)


if __name__ == "__main__":
    unittest.main()
