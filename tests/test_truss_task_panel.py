"""Behavioral controller/GUI contracts without requiring FreeCAD or a Qt runtime."""

from __future__ import annotations

from copy import deepcopy
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch

from freecad.SteelStructures import profile_catalog
from freecad.SteelStructures import profiles
from freecad.SteelStructures.paths import CATALOGS_DIR


ROOT = Path(__file__).resolve().parents[1]
LIBRARY = profiles.ProfileLibrary(CATALOGS_DIR)
CHANNEL_DESIGNATION = LIBRARY.search("U3x6.10")[0].designation


def load_gui():
    package = "_truss_gui_contract"
    injected = {}
    for suffix in ("", ".interactive"):
        module = types.ModuleType(package + suffix)
        module.__path__ = []
        injected[module.__name__] = module
    pyside = types.ModuleType("PySide")
    pyside.QtCore = types.SimpleNamespace()
    pyside.QtGui = types.SimpleNamespace()
    pyside.QtWidgets = types.SimpleNamespace(
        QDialog=object, QGraphicsView=object, QWidget=object, QToolButton=object,
    )
    injected["PySide"] = pyside
    injected[package + ".profile_catalog"] = profile_catalog
    injected[package + ".profiles"] = profiles
    grid = types.ModuleType(package + ".interactive.grid_task_panel")
    grid.SpacingDoubleSpinBox = object
    grid.standard_buttons_value = lambda _box: 3
    grid.stabilize_compact_tool_button = lambda button: None
    injected[grid.__name__] = grid
    for suffix, name in (("profile_options_widget", "ProfileOptionsWidget"),
                         ("section_orientation_preview", "SectionOrientationPreview")):
        module = types.ModuleType(package + ".interactive." + suffix)
        setattr(module, name, object)
        injected[module.__name__] = module
    previous = {name: sys.modules.get(name) for name in injected}
    sys.modules.update(injected)
    loaded = []
    try:
        for filename in ("truss_preview", "truss_task_panel"):
            name = package + ".interactive." + filename
            path = ROOT / "freecad/SteelStructures/interactive" / (filename + ".py")
            spec = importlib.util.spec_from_file_location(name, path)
            module = importlib.util.module_from_spec(spec)
            sys.modules[name] = module
            loaded.append(module)
            spec.loader.exec_module(module)
        return loaded
    finally:
        for module in loaded:
            sys.modules.pop(module.__name__, None)
        for name, old in previous.items():
            if old is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = old


preview_module, panel_module = load_gui()
# Qt stays stubbed in the loaded globals. Lazy C2 imports resolve against the
# real pure package after load_gui removes its temporary import namespace.
panel_module.__package__ = "freecad.SteelStructures.interactive"
panel_module.__spec__ = None


class Number:
    def __init__(self, value):
        self._value = value
        self.visible = True

    def value(self): return self._value
    def setValue(self, value): self._value = round(value, 3)
    def blockSignals(self, _blocked): return False
    def setVisible(self, visible): self.visible = visible


class Combo:
    def __init__(self, data): self.data = data
    def currentData(self): return self.data


class Text:
    def __init__(self): self.text = ""; self.style = ""
    def setText(self, text): self.text = text
    def setStyleSheet(self, style): self.style = style
    def setVisible(self, _visible): pass
    def setEnabled(self, enabled): self.enabled = enabled


class Timer:
    def __init__(self): self.running = False; self.starts = 0
    def stop(self): self.running = False
    def start(self): self.running = True; self.starts += 1


class Check:
    def __init__(self, value=True): self.value = value
    def isChecked(self): return self.value


class Controller:
    def __init__(self):
        self.previews = []; self.previews3d = []; self.accepts = []; self.cancels = 0
        self.error = None; self.accept_error = None

    def preview(self, config):
        self.previews.append(deepcopy(config))
        if self.error:
            raise ValueError(self.error)
        return {
            "nodes": [{"key": "a", "position_local": [0, 0, 0]},
                      {"key": "b", "position_local": [10, 3, 0]}],
            "edges": [{"key": "ab", "start_node_key": "a", "end_node_key": "b",
                       "role": "TOP_CHORD"}],
            "envelope": {"top": [[0, 0, 0], [10, 3, 0]], "bottom": [[0, 0, 0], [10, 0, 0]]},
            "stations": [{"key": str(x), "x": x, "mandatory": True} for x in (0, 3, 5, 7, 10)],
            "left_panels": 2, "right_panels": 2, "warnings": ["Aviso do gerador"],
        }

    def preview3d(self, config, enabled=True):
        self.previews3d.append((deepcopy(config), enabled))

    def accept(self, config):
        self.accepts.append(deepcopy(config))
        if self.accept_error:
            raise ValueError(self.accept_error)

    def cancel(self): self.cancels += 1


def config_fixture():
    ref = profile_catalog.ref_for_designation(CHANNEL_DESIGNATION)
    role = {
        "profile_ref": {"catalog_id": ref.catalog_id, "profile_id": ref.profile_id},
        "insertion": "centroid", "rotation": 0.0, "color": [0.72, 0.72, 0.76],
        "section_geometry_mode": "Detailed", "assembly": "Single", "physical_fit": "None",
    }
    return {
        "envelope_type": "Parallel", "span": 10.0, "height": 3.0,
        "apex_position": 0.5, "panel_count": 4, "topology_preset": "Warren",
        "top_continuity": "Continuous", "bottom_continuity": "SegmentAtEveryNode",
        "start": [0.0, 0.0, 0.0], "end": [10.0, 0.0, 0.0],
        "plane_normal": [0.0, -1.0, 0.0], "left_panels": None, "right_panels": None,
        "role_specs": {key: deepcopy(role) for key, _label in panel_module.ROLE_LABELS},
    }


def make_panel():
    config = config_fixture()
    panel = object.__new__(panel_module.TrussTaskPanel)
    panel._initial = deepcopy(config)
    panel._role_specs = deepcopy(config["role_specs"])
    panel.controller = Controller()
    panel._closed = False; panel._updating = False; panel._valid = False
    panel._axis_direction = [1.0, 0.0, 0.0]
    panel._last_preview_config = None
    panel._point_generation = 0
    panel._point_picker = None
    panel._on_close = None
    panel._preview_timer = Timer()
    panel.preview = types.SimpleNamespace(models=[])
    panel.preview.set_model = lambda model: panel.preview.models.append(deepcopy(model))
    panel.start_inputs = [Number(x) for x in config["start"]]
    panel.end_inputs = [Number(x) for x in config["end"]]
    panel.normal_inputs = [Number(x) for x in config["plane_normal"]]
    panel.envelope_type = Combo(config["envelope_type"])
    panel.preset = Combo(config["topology_preset"])
    panel.top_continuity = Combo(config["top_continuity"])
    panel.bottom_continuity = Combo(config["bottom_continuity"])
    panel.height = Number(config["height"])
    panel.span = Number(config["span"])
    panel.apex = Number(100 * config["apex_position"])
    panel.panel_count = Number(config["panel_count"])
    panel.show_3d = Check()
    for name in ("message", "summary", "closure", "pitch_note", "apex_label", "plane_label", "pick_button"):
        setattr(panel, name, Text())
    panel._set_accept_enabled = lambda enabled: setattr(panel, "accept_enabled", enabled)
    return panel


class TrussPanelContractTests(unittest.TestCase):
    def test_nominal_lengths_collapse_numerically_equal_choices(self):
        self.assertEqual(panel_module.distinct_nominal_lengths(
            (1000., 1000.+5e-8, 1250., 1250.+5e-7)), (1000., 1250.))

    def test_get_config_uses_endpoint_distance_and_preserves_independent_physical_roles(self):
        panel = make_panel()
        panel.end_inputs = [Number(0), Number(6), Number(8)]
        panel._role_specs["END_POST_RIGHT"]["rotation"] = 45.0
        panel.span.setValue(999)
        result = panel.get_config()
        self.assertEqual(result["span"], 10.0)
        self.assertEqual(len(result["role_specs"]), 6)
        self.assertEqual(result["role_specs"]["END_POST_RIGHT"]["rotation"], 45.0)
        result["role_specs"]["END_POST_RIGHT"]["rotation"] = 1
        self.assertEqual(panel._role_specs["END_POST_RIGHT"]["rotation"], 45.0)

    def test_point_edit_updates_span_without_changing_explicit_normal(self):
        panel = make_panel()
        panel.end_inputs = [Number(0), Number(6), Number(8)]
        panel._points_changed()
        self.assertEqual(panel.span.value(), 10.0)
        self.assertEqual(panel.get_config()["plane_normal"], [0, -1, 0])
        self.assertEqual(panel._axis_direction, [0, 0.6, 0.8])

    def test_span_edit_moves_endpoint_along_existing_direction(self):
        panel = make_panel()
        panel.start_inputs = [Number(2), Number(3), Number(4)]
        panel._axis_direction = [0, 0.6, 0.8]
        panel._span_changed(20)
        self.assertEqual(panel.get_config()["end"], [2, 15, 20])
        self.assertEqual(panel.get_config()["span"], 20)

    def test_display_precision_does_not_quantize_picked_coordinates(self):
        panel = make_panel()
        exact = [1.123456789, 2.987654321, 3.141592654]
        panel._write_vector(panel.start_inputs, exact)
        self.assertEqual(panel._read_vector(panel.start_inputs), exact)
        panel.start_inputs[0].setValue(5)
        self.assertEqual(panel._read_vector(panel.start_inputs), [5, exact[1], exact[2]])

    def test_role_editor_keeps_profile_ref_and_maps_label_to_id(self):
        previous = config_fixture()["role_specs"]["TOP_CHORD"]
        previous["physical_fit"], previous["physical_fit_gap"] = "ToChord", 4.5
        profile = profile_catalog.get(CHANNEL_DESIGNATION)
        geometry = profiles.build_section_geometry(profile.definition)
        insertion = next(item for item in profiles.section_insertion_references(geometry)
                         if item.id == "web_back")
        options = types.SimpleNamespace(
            profile_designation=CHANNEL_DESIGNATION, section_geometry_mode="Simplified",
            insertion=types.SimpleNamespace(currentText=lambda: insertion.label),
            rotation=Number(90), rgb=(0.1, 0.2, 0.3),
        )
        result = panel_module.role_spec_from_options(previous, options)
        self.assertEqual(result["profile_ref"], previous["profile_ref"])
        self.assertEqual(result["insertion"], "web_back")
        self.assertEqual(result["rotation"], 90)
        self.assertEqual(result["assembly"], "Single")
        self.assertEqual(result["section_geometry_mode"], "Simplified")
        self.assertEqual((result["physical_fit"], result["physical_fit_gap"]), ("ToChord", 4.5))
        self.assertEqual(previous["insertion"], "centroid")

    def test_profile_refs_from_other_families_are_supported(self):
        for query in ("L50x5", "W150x13", "Ue 50x25x10x1.20", "SHS", "Barra Redonda"):
            with self.subTest(query=query):
                designation = LIBRARY.search(query)[0].designation
                ref = profile_catalog.ref_for_designation(designation)
                spec = config_fixture()["role_specs"]["END_POST_RIGHT"]
                spec["profile_ref"] = {"catalog_id": ref.catalog_id, "profile_id": ref.profile_id}
                name, geometry = panel_module.role_geometry(spec)
                self.assertEqual(name, designation)
                self.assertGreater(geometry.bounds.width, 0)
                self.assertGreater(geometry.bounds.height, 0)

    def test_invalid_core_result_keeps_last_scene_and_disables_accept(self):
        panel = make_panel()
        self.assertTrue(panel._refresh())
        previous = deepcopy(panel.preview.models)
        panel.controller.error = "Normal não perpendicular"
        self.assertFalse(panel._refresh())
        self.assertEqual(panel.preview.models, previous)
        self.assertFalse(panel.accept_enabled)
        self.assertFalse(panel._preview_timer.running)
        self.assertIn("Normal não perpendicular", panel.message.text)

    def test_multiple_updates_only_build_3d_when_timer_fires(self):
        panel = make_panel()
        panel._refresh()
        panel.height.setValue(8)
        panel._refresh()
        self.assertEqual(panel.controller.previews3d, [])
        panel._update_preview3d()
        self.assertEqual(len(panel.controller.previews3d), 1)
        self.assertEqual(panel.controller.previews3d[0][0]["height"], 8)

    def test_stale_3d_request_revalidates_before_build(self):
        panel = make_panel()
        panel._refresh()
        panel.height.setValue(9)
        panel._update_preview3d()
        self.assertEqual(panel.controller.previews3d, [])
        self.assertEqual(panel._last_preview_config["height"], 9)

    def test_preview_toggle_off_calls_controller_without_creating_objects(self):
        panel = make_panel()
        panel._refresh()
        panel.show_3d.value = False
        panel._toggle_preview3d(False)
        self.assertFalse(panel._preview_timer.running)
        self.assertEqual(panel.controller.previews3d[0][1], False)

    def test_duopitch_summary_uses_controller_allocation(self):
        panel = make_panel()
        panel.envelope_type.data = "DuoPitch"
        panel.apex.setValue(30)
        panel._refresh()
        self.assertIn("2 painéis à esquerda + 2 à direita", panel.closure.text)

    def test_accept_uses_current_state_and_closes_once(self):
        panel = make_panel()
        closed = []
        panel._on_close = lambda: closed.append(True)
        panel.height.setValue(7)
        self.assertTrue(panel.accept())
        self.assertTrue(panel.accept())
        self.assertEqual(len(panel.controller.accepts), 1)
        self.assertEqual(panel.controller.accepts[0]["height"], 7)
        self.assertEqual(closed, [True])
        self.assertFalse(panel._preview_timer.running)

    def test_accept_failure_preserves_open_editor(self):
        panel = make_panel()
        panel.controller.accept_error = "Shape inválida"
        self.assertFalse(panel.accept())
        self.assertFalse(panel._closed)
        self.assertEqual(panel.controller.cancels, 0)
        self.assertIn("Shape inválida", panel.message.text)

    def test_constructor_failure_disposes_partial_form_and_stops_timer(self):
        disposed = []
        timer = Timer()
        timer.start()
        form = types.SimpleNamespace(deleteLater=lambda: disposed.append(True))

        def fail_build(panel, _config):
            panel._preview_timer = timer
            raise TypeError("Qt render failed")

        with patch.object(panel_module.QtWidgets, "QWidget", return_value=form, create=True), \
                patch.object(panel_module.TrussTaskPanel, "_build_form", fail_build):
            with self.assertRaisesRegex(TypeError, "Qt render failed"):
                panel_module.TrussTaskPanel(None, Controller(), config_fixture())
        self.assertEqual(disposed, [True])
        self.assertFalse(timer.running)

    def test_close_callback_failure_still_closes_once_and_releases_form(self):
        panel = make_panel()
        disposed = []
        panel.form = types.SimpleNamespace(deleteLater=lambda: disposed.append(True))

        def failed_close():
            raise RuntimeError("Host dialog failed")

        panel._on_close = failed_close
        with self.assertRaisesRegex(RuntimeError, "Host dialog failed"):
            panel.reject()
        self.assertTrue(panel._closed)
        self.assertFalse(panel._preview_timer.running)
        self.assertEqual(disposed, [True])
        self.assertTrue(panel.reject())
        self.assertEqual(panel.controller.cancels, 1)

    def test_cancel_is_idempotent_and_late_picker_is_ignored(self):
        panel = make_panel()
        callbacks = []
        panel._point_picker = callbacks.append
        panel._pick_points()
        previous = panel.get_config()
        panel.reject(); panel.reject()
        callbacks[0]([1, 2, 3], [4, 5, 6])
        panel._update_preview3d()
        self.assertEqual(panel.controller.cancels, 1)
        self.assertEqual(panel.get_config(), previous)
        self.assertEqual(panel.controller.previews3d, [])

    def test_picker_sets_both_points_and_never_changes_normal(self):
        panel = make_panel()
        panel._point_picker = lambda callback: callback([1, 2, 3], [7, 10, 3])
        panel._pick_points()
        result = panel.get_config()
        self.assertEqual(result["start"], [1, 2, 3])
        self.assertEqual(result["end"], [7, 10, 3])
        self.assertEqual(result["span"], 10)
        self.assertEqual(result["plane_normal"], [0, -1, 0])

    def test_invalid_second_pick_does_not_partially_replace_first_point(self):
        panel = make_panel()
        previous = panel.get_config()
        panel._point_picker = lambda callback: callback([1, 2, 3], [float("nan"), 2, 3])
        panel._pick_points()
        self.assertEqual(panel.get_config(), previous)
        self.assertFalse(panel.accept_enabled)

    def test_point_adapter_accepts_native_vector_components(self):
        vector = types.SimpleNamespace(x=1.5, y=-2.5, z=3.5)
        self.assertEqual(panel_module.point_components(vector), [1.5, -2.5, 3.5])


class TrussPreviewContractTests(unittest.TestCase):
    def test_graph_uses_node_keys_and_upward_local_y(self):
        model = Controller().preview(config_fixture())
        nodes, edges, envelope = preview_module.graph_presentation(model)
        self.assertEqual(nodes["b"], (10, -3))
        self.assertEqual(edges[0], ((0, 0), (10, -3), "TOP_CHORD", "ab"))
        self.assertEqual(envelope[0], ((0, 0), (10, -3)))

    def test_nonfinite_preview_is_rejected_before_replacing_scene(self):
        model = Controller().preview(config_fixture())
        model["nodes"][0]["position_local"][0] = float("nan")
        with self.assertRaises(ValueError):
            preview_module.graph_presentation(model)

    def test_missing_endpoint_is_not_drawn_at_zero(self):
        model = Controller().preview(config_fixture())
        model["edges"][0]["end_node_key"] = "missing"
        with self.assertRaises(KeyError):
            preview_module.graph_presentation(model)


if __name__ == "__main__":
    unittest.main()
