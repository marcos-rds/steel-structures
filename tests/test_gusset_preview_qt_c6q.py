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
            # Unit parsing and exact numeric storage have separate real-FreeCAD
            # tests. This fixture exercises presentation without importing App.
            "freecad.SteelStructures.interactive.truss_units": SimpleNamespace(
                length_text=lambda value,locale=None:(locale or QtCore.QLocale()).toString(float(value),"f",2)+" mm"),
            "freecad.SteelStructures.interactive.truss_length_spinbox": SimpleNamespace(
                TrussLengthSpinBox=QtWidgets.QDoubleSpinBox),
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

    def make_editor(self, designation='U 4" x 8,04', rotation=0., with_profiles=False):
        value, node = preview_config(designation, rotation=rotation)
        form = QtWidgets.QWidget()
        self.parents.append(form)
        controller = object.__new__(controller_class())
        controller.timings = {}
        from freecad.SteelStructures.trusses.edit_session import TrussEditSession
        controller.session = TrussEditSession(None,None,value)

        def candidate(config):
            controller.last_candidate = build_candidate(config)
            controller.session.record_candidate(controller.last_candidate)
            return controller.last_candidate

        controller.candidate = candidate
        panel = SimpleNamespace(form=form, controller=controller, session=controller.session)
        panel.get_config = lambda: copy.deepcopy(panel.session.config)
        panel.set_connection_intent = lambda key, intent: panel.session.config[
            "connection_intents"].__setitem__(key, copy.deepcopy(intent))
        # Presentation-only panel controls. Native gates
        # below this layer exercise the real TaskPanel handlers and validation.
        def number(value,minimum=-1e9,maximum=1e9,suffix=" mm"):
            spin=QtWidgets.QDoubleSpinBox()
            spin.setRange(minimum,maximum)
            spin.setDecimals(3 if suffix else 6)
            spin.setSuffix(suffix)
            spin.setValue(value)
            return spin
        panel._number=number
        for name,key in (("height","height"),("span","span"),("apex","apex_position"),
                         ("left_end_height","left_end_height"),("right_end_height","right_end_height"),
                         ("target_spacing","target_spacing"),("target_angle","target_angle")):
            setattr(panel,name,number(value.get(key,0.)))
        panel.panel_count=QtWidgets.QSpinBox()
        panel.panel_count.setRange(4,200)
        panel.panel_count.setValue(value["panel_count"])
        for name,key,default in (("envelope_type","envelope_type","Parallel"),
                                 ("reference_mode","reference_mode","TwoPoints"),
                                 ("reference_edge","reference_edge","Edge1"),
                                 ("reference_alignment","reference_alignment","BottomChord"),
                                 ("preset","topology_preset","Pratt"),("driver","panelization_mode","ByPanelCount"),
                                 ("x_connection","x_connection","Disconnected"),
                                 ("top_continuity","top_continuity","Continuous"),
                                 ("bottom_continuity","bottom_continuity","Continuous")):
            combo=QtWidgets.QComboBox()
            combo.addItem(value.get(key,default),value.get(key,default))
            setattr(panel,name,combo)
        for name in ("link_end_heights","keep_reference_link"):
            setattr(panel,name,QtWidgets.QCheckBox(name))
        for name,key in (("start_inputs","start"),("end_inputs","end"),("normal_inputs","plane_normal")):
            setattr(panel,name,[number(v,suffix="") for v in value[key]])
        for name in ("plane_label","message","topology_state","closure","spacing_balance"):
            setattr(panel,name,QtWidgets.QLabel())
        class Spacings(QtWidgets.QWidget):
            def __init__(self,title,values,callback):
                super().__init__()
                self._values=list(values)
                self.callback=callback
                self.summary=QtWidgets.QLabel(title,self)
            def values(self): return list(self._values)
            def set_values(self,values):
                self._values=list(values)
                self.callback()
        panel.spacing_editor=Spacings("Spacing",[value["span"]/value["panel_count"]]*value["panel_count"],lambda:None)
        panel.complete_span=QtWidgets.QPushButton()
        panel._complete_span=panel._restore_topology=lambda:None
        panel.role_buttons={}
        panel.role_labels={}
        if with_profiles:
            panel.role_buttons["DIAGONAL"]=QtWidgets.QToolButton(form)
            panel.role_buttons["DIAGONAL"].setText("Perfil da diagonal")
            panel.role_labels["DIAGONAL"]=QtWidgets.QLabel("Diagonais:",form)
        for item in vars(panel).values():
            widgets=item if isinstance(item,list) else [item]
            for widget in widgets:
                if isinstance(widget,QtWidgets.QWidget) and widget is not form:
                    widget.setParent(form)
                    widget.show()
        panel._valid=True
        panel._closed=False
        panel._last_preview_model=controller.preview(value)
        editor = self.editor_module.TopologyEditor(panel)
        editor.select_node(node)
        editor.tabs.setCurrentWidget(editor.connections_scroll)
        return editor, panel, node

    def test_hidden_task_projection_preserves_editor_conditional_controls(self):
        editor,panel,_node=self.make_editor(with_profiles=True)
        projection=QtWidgets.QWidget(panel.form)
        projection.hide()
        layout=QtWidgets.QVBoxLayout(projection)
        for _name,source,_widget,_label in editor.fields.rows:
            layout.addWidget(source)
            source.setVisible(True)
        for source in panel.role_buttons.values():
            layout.addWidget(source)
            source.setVisible(True)
        layout.addWidget(panel.spacing_editor)
        panel.spacing_editor.setVisible(True)
        editor.tabs.setCurrentWidget(editor.fields.geometry_scroll)
        editor.show()
        editor.fields.sync()
        self.flush()
        self.assertFalse(panel.height.isVisibleTo(panel.form))
        self.assertFalse(panel.height.isHidden())
        self.assertTrue(editor.fields.controls["height"].isVisible())
        self.assertTrue(editor.fields.spacing_editor.isVisible())
        for visible in (False,True):
            panel.apex.setVisible(visible)
            panel.role_buttons["DIAGONAL"].setVisible(visible)
            editor.fields.sync()
            self.assertEqual(editor.fields.controls["apex"].isHidden(),not visible)
            self.assertEqual(editor.fields.role_buttons["DIAGONAL"][0].isHidden(),not visible)
        self.assertTrue(projection.isHidden())
        self.assertFalse(panel.apex.isVisibleTo(panel.form))

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
        self.assertLessEqual(editor.width(), min(1200, editor.screen().availableGeometry().width()-40))
        # Only the connections controls scroll; the schematic is outside tabs.
        self.assertLessEqual(preview.mapTo(editor.connections_page, QtCore.QPoint(preview.width(), 0)).x(),
                             editor.connections_page.width())
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
        panel.session.config["role_specs"]["BOTTOM_CHORD"]["rotation"] = 90.
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

    def test_tabs_share_canvas_selection_and_cancel_pending_tools(self):
        editor, panel, node = self.make_editor()
        editor.show()
        self.flush()
        canvas=editor.canvas
        candidate=panel.controller.last_candidate
        config=copy.deepcopy(panel.session.config)
        with patch.object(panel.controller,"preview",side_effect=AssertionError("Recomputed")):
            for page in (editor.fields.geometry_scroll,editor.fields.profiles_scroll,editor.connections_scroll):
                editor.mode_buttons["create"].click()
                self.assertEqual(editor.current_mode(),"create")
                canvas.pending=node
                canvas.rubber=canvas.scene().addLine(0,0,10,10)
                editor.tabs.setCurrentWidget(page)
                self.flush()
                self.assertEqual(editor.current_mode(),"select")
                self.assertTrue(canvas.isVisible())
                self.assertIsNone(canvas.rubber)
                self.assertIsNone(canvas.pending)
                self.assertEqual(editor._connection_node,node)
                self.assertTrue(editor.transverse_preview.canvas._views)
                self.assertTrue(editor.topology_toolbar.isVisible())
                for button in editor.mode_buttons.values():
                    self.assertFalse(button.icon().isNull())
                    self.assertTrue(button.toolTip())
        self.assertIs(editor.canvas,canvas)
        self.assertIs(panel.controller.last_candidate,candidate)
        self.assertEqual(panel.session.config,config)
        self.assertEqual([editor.tabs.tabText(i) for i in range(editor.tabs.count())],
                         ["Geometria","Perfis","Ligações"])
        self.assertIs(canvas.parentWidget(),editor)

    def test_canvas_height_tracks_bounds_without_rebuilding_candidate(self):
        editor, panel, _node = self.make_editor()
        canvas=editor.canvas
        with patch.object(panel.controller,"preview",side_effect=AssertionError("Recomputed")):
            canvas._geometry_bounds=QtCore.QRectF(0,0,6000,1000)
            shallow=canvas.heightForWidth(1100)
            canvas._geometry_bounds=QtCore.QRectF(0,0,6000,2400)
            self.assertGreater(canvas.heightForWidth(1100),shallow)
            self.assertLess(canvas.heightForWidth(700),canvas.heightForWidth(1100))
            canvas._geometry_bounds=QtCore.QRectF(0,0,100,10000)
            self.assertLessEqual(canvas.heightForWidth(1100),24*canvas.fontMetrics().height())
            editor.resize(760,560)
            editor.show()
            self.flush()
            self.assertAlmostEqual(canvas.transform().m11(),canvas.transform().m22())

    def test_small_window_scrolls_controls_but_keeps_canvas_and_close_visible(self):
        editor, _panel, _node = self.make_editor()
        editor.resize(760,560)
        editor.show()
        self.flush()
        buttons=editor.action_buttons
        for scroll in (editor.fields.geometry_scroll,editor.fields.profiles_scroll,editor.connections_scroll):
            editor.tabs.setCurrentWidget(scroll)
            self.flush()
            self.assertTrue(editor.rect().contains(editor.canvas.geometry()))
            self.assertTrue(editor.rect().contains(buttons.geometry()))
            self.assertTrue(editor.canvas.isVisible())
            self.assertIs(scroll.parentWidget(),editor.tabs.findChild(QtWidgets.QStackedWidget))
        self.assertGreater(editor.connections_scroll.verticalScrollBar().maximum(),0)
        editor.connections_scroll.ensureWidgetVisible(editor.gusset_position)
        self.flush()
        position=editor.gusset_position.mapTo(editor.connections_scroll.viewport(),QtCore.QPoint())
        self.assertTrue(editor.connections_scroll.viewport().rect().contains(position))

    def test_short_window_and_larger_font_leave_usable_scrollable_controls(self):
        editor, _panel, _node = self.make_editor()
        font=editor.font()
        font.setPointSizeF(font.pointSizeF()*1.4)
        editor.setFont(font)
        editor.resize(620,480)
        editor.show()
        self.flush()
        self.assertLessEqual(editor.canvas.height(),max(
            9*editor.canvas.fontMetrics().height(),round(editor.height()*.45))+2)
        self.assertGreater(editor.connections_scroll.viewport().height(),100)
        for widget in (editor.connection_type,editor.gusset_plate,editor.gusset_overlap,
                       editor.gusset_region,editor.gusset_position):
            editor.connections_scroll.ensureWidgetVisible(widget)
            self.flush()
            point=widget.mapTo(editor.connections_scroll.viewport(),QtCore.QPoint())
            self.assertTrue(editor.connections_scroll.viewport().rect().contains(point))
        editor.select_node(None)
        self.flush()
        self.assertFalse(editor.message_scroll.isVisible())
        editor.message.setText("Diagnóstico de teste")
        self.flush()
        self.assertTrue(editor.message_scroll.isVisible())

    def test_diagnostics_expand_without_losing_text_and_invalid_preview_stays_blocked(self):
        editor,panel,_node=self.make_editor()
        editor.show()
        message="Ligação sem solução.\nA configuração precisa ser corrigida antes da realização."
        editor.message.setText(message,"warning")
        self.flush()
        self.assertTrue(editor.message_toggle.isVisible())
        self.assertIn("Alertas e diagnósticos",editor.message_toggle.text())
        self.assertFalse(editor.message_scroll.isVisible())
        editor.message_toggle.click()
        self.assertTrue(editor.message_scroll.isVisible())
        self.assertEqual(editor.message.text(),message)
        panel._valid=False
        panel.message.setText("Entrada inválida: altura zero. Preview anterior desatualizado.")
        editor.sync_from_panel()
        self.assertFalse(editor.topology_toolbar.isEnabled())
        self.assertFalse(editor.canvas.isEnabled())
        self.assertTrue(editor.message_scroll.isVisible())
        self.assertIn("Entrada inválida",editor.message_toggle.text())
        self.assertEqual(editor.message.text(),panel.message.text())

    def test_toolbar_isolates_task_view_theme_rules_and_checked_state(self):
        # OpenDark uses this more-specific Task View descendant rule, which
        # wins over its generic QToolButton:checked. Reproduce that cascade
        # without requiring the external theme or native QSint in unit tests.
        old_style = self.app.styleSheet()
        old_palette = self.app.palette()
        try:
            for dark in (False, True):
                palette = QtGui.QPalette(old_palette)
                palette.setColor(QtGui.QPalette.Window, QtGui.QColor("#343a40" if dark else "#efefef"))
                # A red system accent must not become the toolbar's active fill.
                palette.setColor(QtGui.QPalette.Highlight, QtGui.QColor("#e52222"))
                palette.setColor(QtGui.QPalette.HighlightedText, QtGui.QColor("white"))
                self.app.setPalette(palette)
                self.app.setStyleSheet("""
                    QToolButton { margin: 0px 3px; padding: 2px; background: transparent; }
                    QToolButton:checked { background: #339af0; border: 1px solid #264b69; }
                    QWidget#taskView QFrame[class="content"] QToolButton {
                        padding: 4px 20px; background: #495057; border: 1px solid #495057; }
                    QWidget#taskView QFrame[class="content"] QToolButton:focus {
                        background: #495057; }
                """)
                ancestor = QtWidgets.QWidget()
                ancestor.setObjectName("taskView")
                self.parents.append(ancestor)
                content = QtWidgets.QFrame(ancestor)
                content.setProperty("class", "content")
                editor, panel, _ = self.make_editor()
                panel.form.setParent(content)
                editor.show()
                self.flush()
                ordinary = QtWidgets.QToolButton(content)
                ordinary.setCheckable(True)
                ordinary.show()
                self.flush()
                def corner(button):
                    return button.grab().toImage().pixelColor(6, 6).name()
                # Demonstrate the unprotected theme cascade actually masks
                # checked; the editor's local rules must make it visible.
                off = corner(ordinary)
                ordinary.setChecked(True)
                self.assertEqual(corner(ordinary), off)
                self.assertGreater(ordinary.sizeHint().width(), 32)
                for mode, button in editor.mode_buttons.items():
                    editor.mode_buttons["select" if mode != "select" else "create"].click()
                    unchecked = corner(button)
                    button.click()
                    self.assertEqual(button.size(), QtCore.QSize(32, 32))
                    self.assertEqual(editor.current_mode(), mode)
                    self.assertEqual(sum(b.isChecked() for b in editor.mode_group.buttons()), 1)
                    self.assertNotEqual(corner(button), unchecked)
                    active = button.grab().toImage()
                    fill = active.pixelColor(6, 6)
                    self.assertGreater(fill.blue(), fill.red())
                    self.assertNotEqual(fill.name(), palette.color(QtGui.QPalette.Highlight).name())
                    self.assertEqual(active.pixelColor(16, 0).name(), "#4c96b7")
                self.assertFalse(editor.invert_button.isCheckable())
                self.assertFalse(editor.copy_button.isCheckable())
                editor.close()
        finally:
            self.app.setStyleSheet(old_style)
            self.app.setPalette(old_palette)

    def test_information_reads_current_candidate_and_clears_invalid_or_stale_values(self):
        editor,panel,_node=self.make_editor()
        fields=editor.fields
        candidate=panel.session.validated_candidate
        self.assertIsNotNone(candidate)
        self.assertEqual(fields.mass_status.text(),"Aguardando aplicação")
        self.assertEqual(fields.information_values["mass"].text(),"—")
        self.assertIn("7850 kg/m³",fields.mass_status.toolTip())
        self.assertEqual(fields.information_values["nodes"].text(),str(len(candidate.graph.nodes)))
        self.assertEqual(fields.information_values["bars"].text(),str(len(candidate.graph.edges)))
        self.assertEqual(fields.information_values["panels"].text(),str(candidate.config["panelization_result"]["panel_count"]))
        with patch.object(panel.controller,"candidate",side_effect=AssertionError("Presentation rebuilt topology")):
            fields.sync()
            panel.session.config["height"]+=100.
            fields.sync()
            self.assertTrue(panel._valid)  # The revision guard, not only this flag, matters.
            self.assertTrue(all(label.text()=="—" for label in fields.information_values.values()))
            self.assertFalse(fields.information_box.isEnabled())
            panel._valid=False
            fields.sync()
            self.assertTrue(all(label.text()=="—" for label in fields.information_values.values()))

    def test_information_updates_with_candidate_and_keeps_custom_diagnostics(self):
        editor,panel,_node=self.make_editor()
        fields=editor.fields
        value=copy.deepcopy(panel.session.config)
        value["panel_count"]=8
        candidate=build_candidate(value)
        panel.session.record_candidate(candidate)
        panel.topology_state.setText("Base para restaurar: Pratt")
        fields.sync()
        self.assertEqual(fields.information_values["panels"].text(),str(candidate.config["panelization_result"]["panel_count"]))
        self.assertEqual(fields.information_values["nodes"].text(),str(len(candidate.graph.nodes)))
        self.assertIn("Base para restaurar",fields.geometry_status.text())
        panel.topology_state.setText("")
        panel.spacing_balance.hide()
        fields.sync()
        self.assertEqual(fields.geometry_status.text(),"")
        self.assertTrue(fields.geometry_status.isHidden())
        self.assertTrue(fields.restore.isEnabled())
        value.update(panelization_mode="ByTargetDiagonalAngle",target_angle=45.)
        panel.session.record_candidate(build_candidate(value))
        fields.sync()
        self.assertIn("Ângulo médio efetivo",fields.geometry_status.text())
        panel._valid=False
        fields.sync()
        self.assertNotIn("Ângulo médio efetivo",fields.geometry_status.text())

    def test_mass_current_pending_nonphysical_and_failed_are_distinct(self):
        from freecad.SteelStructures.trusses.serialization import encode_state,decode_state
        from freecad.SteelStructures.trusses.physical_mass import PhysicalMass,PhysicalPiece
        editor,panel,_node=self.make_editor()
        fields=editor.fields
        candidate=panel.session.validated_candidate
        owner=SimpleNamespace(Name="Truss",AppliedState=encode_state(candidate))
        doc=SimpleNamespace(getObject=lambda name:owner)
        owner.Document=doc
        panel.session.owner=owner
        panel.session.owner_name=owner.Name
        panel.session.document=doc
        panel.session.applied_state=owner.AppliedState
        panel.session.realized_state=decode_state(owner.AppliedState)
        result=PhysicalMass((PhysicalPiece("member","Member",1e6),),(),2400.,2400.)
        with patch("freecad.SteelStructures.trusses.physical_mass.read_physical_mass",return_value=result) as reader, \
             patch("freecad.SteelStructures.trusses.physical_changes.materialization_pending",return_value=False):
            fields.sync()
            confirmed=fields.information_values["mass"].text()
            self.assertTrue(confirmed.endswith(" kg"))
            self.assertTrue(fields.mass_status.isHidden())
            self.assertFalse(fields.information_values["mass"].font().bold())
            self.assertTrue(fields.mass_information.labels["mass"].font().bold())
            self.assertEqual(fields.information_values["mass"].font().pointSizeF(),fields.information_values["nodes"].font().pointSizeF())
            value=copy.deepcopy(candidate.config)
            for role in value["role_specs"].values(): role["color"]=[.1,.2,.3]
            panel.session.record_candidate(build_candidate(value))
            fields.sync()
            self.assertEqual(fields.information_values["mass"].text(),confirmed)
            reader.reset_mock()
            value["height"]+=100.
            panel.session.record_candidate(build_candidate(value))
            fields.sync()
            self.assertEqual(fields.information_values["mass"].text(),"—")
            self.assertEqual(fields.mass_status.text(),"Aguardando aplicação")
            # The last materialized pieces are still inspected for real faults;
            # an unapplied draft must not conceal a failed physical calculation.
            reader.assert_called_once()
            reader.return_value=PhysicalMass(diagnostics=("Shape inválida",))
            fields.sync()
            self.assertEqual(fields.information_values["mass"].text(),"Indisponível")
            panel.session.record_candidate(candidate)
            reader.return_value=PhysicalMass(diagnostics=("Shape inválida",))
            fields.sync()
            self.assertEqual(fields.information_values["mass"].text(),"Indisponível")
            self.assertTrue(fields.mass_status.isHidden())
            self.assertIn("Shape inválida",fields.information_values["mass"].toolTip())

    def test_editor_reference_summary_only_explains_associative_link(self):
        editor,panel,_node=self.make_editor()
        fields=editor.fields
        fields.sync()
        self.assertTrue(fields.reference_summary.isHidden())
        self.assertEqual(fields.reference_summary.text(),"")
        panel.keep_reference_link.setChecked(True)
        panel.session.config["reference_source"]="DraftLine"
        fields.sync()
        self.assertIn("Vínculo associativo: DraftLine",fields.reference_summary.text())
        self.assertFalse(fields.reference_summary.isHidden())
        self.assertNotIn("Face externa",fields.reference_summary.text())

    def test_coordinates_stay_in_panel_and_profiles_wrap(self):
        editor,panel,_node=self.make_editor()
        editor.tabs.setCurrentWidget(editor.fields.geometry_scroll)
        editor.show()
        self.flush()
        fields=editor.fields
        self.assertGreater(fields.geometry_controls.width(),fields.geometry_scroll.viewport().width()*.8)
        self.assertLessEqual(fields.geometry_controls.width(),1040)
        groups={group.title():group for group in fields.geometry_controls.findChildren(QtWidgets.QGroupBox)}
        self.assertLess(groups["Geometria"].geometry().right(),groups["Alma e panelização"].geometry().left())
        for name in ("span","height","panel_count"):
            self.assertGreater(fields.controls[name].width(),0)
            self.assertLessEqual(fields.controls[name].width(),180)
        self.assertLessEqual(fields.controls["preset"].width(),300)
        self.assertFalse(hasattr(editor.fields,"advanced"))
        self.assertFalse(any(name.startswith(("start_inputs","end_inputs","normal_inputs"))
                             for name in editor.fields.controls))
        self.assertEqual([spin.value() for spin in panel.start_inputs],panel.session.config["start"])
        self.assertEqual(fields.controls["reference_alignment"].currentData(),panel.reference_alignment.currentData())
        self.assertTrue(fields.controls["reference_alignment"].isVisible())
        from freecad.SteelStructures.interactive.truss_editor_fields import _ProfileCard
        source=QtWidgets.QToolButton(editor)
        card=_ProfileCard(source)
        self.parents.append(card)
        caption="Perfil tubular retangular de designação extensa\nComposição: Par espaçado · ajuste ao banzo"
        card.setText(caption)
        card.resize(260,card.heightForWidth(260))
        card.show()
        self.flush()
        self.assertEqual(card.caption.text(),caption)
        self.assertGreater(card.heightForWidth(260),card.heightForWidth(600))
        self.assertGreaterEqual(card.caption.height(),card.caption.heightForWidth(card.caption.width()))
        called=[]
        card.clicked.connect(lambda:called.append(True))
        card.click()
        self.assertEqual(called,[True])

    def test_first_click_after_navigation_and_free_node_toggle_do_not_change_mode(self):
        from PySide6 import QtTest
        editor,panel,node=self.make_editor()
        editor.show()
        self.flush()
        canvas=editor.canvas
        other=next(n for n in panel.controller.last_candidate.graph.nodes if n.key!=node)
        for page in (editor.fields.geometry_scroll,editor.fields.profiles_scroll,editor.connections_scroll):
            editor.mode_buttons["create"].click()
            canvas.pending=node
            canvas.rubber=canvas.scene().addLine(0,0,10,10)
            canvas.snap_marker=canvas.scene().addEllipse(0,0,4,4)
            editor.message.setText("Selecione o segundo nó; Esc cancela o gesto.")
            editor.tabs.setCurrentWidget(page)
            self.flush()
            self.assertNotIn("segundo nó",editor.message.text())
            self.assertIsNone(canvas.pending)
            self.assertIsNone(canvas.rubber)
            self.assertIsNone(canvas.snap_marker)
            self.assertEqual(editor.current_mode(),"select")
            self.assertEqual(sum(b.isChecked() for b in editor.mode_buttons.values()),1)
            point=canvas.mapFromScene(QtCore.QPointF(other.position_local[0],-other.position_local[1]))
            QtTest.QTest.mouseClick(canvas.viewport(),QtCore.Qt.LeftButton,pos=point)
            self.assertEqual(editor._connection_node,other.key)
            editor.select_node(node)
        editor.mode_buttons["add_node"].click()
        editor.allow_free.click()
        self.assertTrue(editor.allow_free.isChecked())
        self.assertEqual(editor.current_mode(),"add_node")
        self.assertNotIn(editor.allow_free,editor.mode_group.buttons())
        self.assertFalse(editor.invert_button.isCheckable())
        self.assertFalse(editor.copy_button.isCheckable())

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
