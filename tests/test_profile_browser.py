"""Headless contracts for Profile Browser state and Qt geometry boundary."""

from __future__ import annotations

import unittest
import importlib.util
import re
import sys
import types
from pathlib import Path

from freecad.SteelStructures.paths import CATALOGS_DIR
from freecad.SteelStructures.profiles import (
    ProfileLibrary, UnsupportedSectionGeometryError, build_section_geometry,
    insertion_reference,
)
from freecad.SteelStructures.profiles.presentation import profile_preview_dimension_rows
ROOT = Path(__file__).resolve().parents[1]
MODEL_PATH = ROOT / "freecad/SteelStructures/interactive/profile_browser_model.py"
SPEC = importlib.util.spec_from_file_location("_profile_browser_model_test", MODEL_PATH)
MODEL_MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODEL_MODULE)
ProfileBrowserModel = MODEL_MODULE.ProfileBrowserModel


class _FakeRect:
    def __init__(self, width=20.0, height=10.0):
        self._width, self._height = width, height

    def width(self):
        return self._width

    def height(self):
        return self._height


class _FakeText:
    def __init__(self, text):
        self.text = text
        self._font = types.SimpleNamespace(bold=False, setBold=lambda value: setattr(self._font, "bold", value))

    def setDefaultTextColor(self, _color):
        pass

    def boundingRect(self):
        visible = getattr(self, "html", self.text).replace("&nbsp;", " ")
        visible = re.sub(r"<[^>]+>", "", visible)
        return _FakeRect(max(len(visible) * 5.0, 20.0), 10.0)

    def setPos(self, _x, _y):
        self.position = (_x, _y)

    def setFlag(self, flag, enabled):
        self.flag = (flag, enabled)

    def setHtml(self, html):
        self.html = html

    def setTransform(self, transform):
        self.transform = transform

    def font(self):
        return self._font

    def setFont(self, font):
        self._font = font


class _FakeScene:
    def __init__(self):
        self.lines = []
        self.texts = []
        self.text_items = []
        self.ellipses = []
        self.ellipse_items = []
        self.line_items = []

    def addLine(self, *args):
        self.lines.append(args)
        item = types.SimpleNamespace(
            args=args,
            setPos=lambda x, y: setattr(item, "position", (x, y)),
            setFlag=lambda flag, enabled: setattr(item, "flag", (flag, enabled)),
        )
        self.line_items.append(item)
        return item

    def addText(self, text):
        if text:
            self.texts.append(text)
        item = _FakeText(text)
        self.text_items.append(item)
        return item

    def addEllipse(self, *args):
        self.ellipses.append(args)
        item = types.SimpleNamespace(
            args=args,
            setPos=lambda x, y: setattr(item, "position", (x, y)),
            setFlag=lambda flag, enabled: setattr(item, "flag", (flag, enabled)),
        )
        self.ellipse_items.append(item)
        return item


def _load_preview_runtime_module():
    """Load the real renderer with the smallest Qt surface needed by cotas."""
    root_name = "_profile_preview_runtime"
    root = types.ModuleType(root_name)
    root.__path__ = []
    interactive = types.ModuleType(root_name + ".interactive")
    interactive.__path__ = []
    profiles = sys.modules["freecad.SteelStructures.profiles"]
    preview_geometry = __import__(
        "freecad.SteelStructures.profiles.preview_geometry",
        fromlist=["section_outline_points"],
    )
    qtgui = types.SimpleNamespace(
        QGraphicsView=object,
        QPen=type("QPen", (), {
            "__init__": lambda self, color: setattr(self, "_color", color),
            "setCosmetic": lambda self, _value: None,
            "setWidthF": lambda self, value: setattr(self, "width", value),
            "setStyle": lambda self, value: setattr(self, "style", value),
            "setDashPattern": lambda self, value: setattr(self, "dash_pattern", tuple(value)),
            "color": lambda self: self._color,
        }),
        QBrush=type("QBrush", (), {"__init__": lambda self, _color: None}),
        QColor=type("QColor", (), {"__init__": lambda self, *args: setattr(self, "rgb", args)}),
        QPalette=types.SimpleNamespace(Text=1),
        QPainter=types.SimpleNamespace(Antialiasing=1),
        QTransform=types.SimpleNamespace(fromTranslate=lambda x, y: (x, y)),
    )
    graphics_item = types.SimpleNamespace(ItemIgnoresTransformations=1)
    qtwidgets = types.SimpleNamespace(QGraphicsView=object, QGraphicsItem=graphics_item)
    pyside = types.ModuleType("PySide")
    pyside.QtCore = types.SimpleNamespace(Qt=types.SimpleNamespace(DashDotLine=2))
    pyside.QtGui = qtgui
    pyside.QtWidgets = qtwidgets
    injected = {
        root_name: root,
        root_name + ".interactive": interactive,
        root_name + ".profiles": profiles,
        root_name + ".profiles.preview_geometry": preview_geometry,
        "PySide": pyside,
    }
    previous = {name: sys.modules.get(name) for name in injected}
    sys.modules.update(injected)
    path = ROOT / "freecad/SteelStructures/interactive/profile_browser_preview.py"
    spec = importlib.util.spec_from_file_location(root_name + ".interactive.profile_browser_preview", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        for name, old in previous.items():
            if old is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = old
    return module


def _load_browser_runtime_module():
    """Load the real preview state method without requiring a desktop session."""
    root_name = "_profile_browser_runtime"
    root = types.ModuleType(root_name)
    root.__path__ = []
    interactive = types.ModuleType(root_name + ".interactive")
    interactive.__path__ = []
    pyside = types.ModuleType("PySide")
    pyside.QtCore = types.SimpleNamespace(Qt=types.SimpleNamespace(
        UserRole=32, ItemDataRole=types.SimpleNamespace(UserRole=32)
    ))
    pyside.QtGui = types.SimpleNamespace()
    pyside.QtWidgets = types.SimpleNamespace(QDialog=object)
    preview_module = types.ModuleType(root_name + ".interactive.profile_browser_preview")
    preview_module.SectionPreviewView = object
    preview_module.DIMENSIONS_MODE = "dimensions"
    preview_module.PROPERTIES_MODE = "properties"
    preview_module.NEUTRAL_MODE = "neutral"
    actual_profiles = sys.modules["freecad.SteelStructures.profiles"]
    actual_presentation = sys.modules["freecad.SteelStructures.profiles.presentation"]
    actual_paths = sys.modules["freecad.SteelStructures.paths"]
    injected = {
        root_name: root,
        root_name + ".interactive": interactive,
        root_name + ".profiles": actual_profiles,
        root_name + ".profiles.presentation": actual_presentation,
        root_name + ".paths": actual_paths,
        root_name + ".interactive.profile_browser_model": MODEL_MODULE,
        root_name + ".interactive.profile_browser_preview": preview_module,
        "PySide": pyside,
    }
    previous = {name: sys.modules.get(name) for name in injected}
    sys.modules.update(injected)
    path = ROOT / "freecad/SteelStructures/interactive/profile_browser.py"
    spec = importlib.util.spec_from_file_location(root_name + ".interactive.profile_browser", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        for name, old in previous.items():
            if old is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = old
    return module


class ProfileBrowserModelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.library = ProfileLibrary(CATALOGS_DIR)

    def setUp(self):
        self.model = ProfileBrowserModel(self.library)

    def test_catalog_tree_source_has_tubular_category_and_rolled_steel_is_unchanged(self):
        self.assertEqual(len(self.library.list_categories()), 3)
        self.assertEqual(len(self.library.list_series("rolled-steel")), 7)
        self.assertEqual(len(self.model.set_filter("rolled-steel")), 218)
        self.assertEqual(len(self.model.set_filter("tubular")), 2999)

    def test_series_filter_preserves_catalog_order(self):
        profiles = self.model.set_filter("rolled-steel", "w")
        self.assertEqual(len(profiles), 100)
        self.assertEqual(profiles, self.library.list_profiles(series_id="w"))

    def test_search_respects_tree_filter(self):
        self.model.set_filter("rolled-steel", "w")
        result = self.model.set_query("310")
        self.assertTrue(result)
        self.assertTrue(all(profile.series_id == "w" for profile in result))
        self.model.set_filter("rolled-steel")
        result = self.model.set_query("310")
        self.assertGreater(len({profile.series_id for profile in result}), 1)

    def test_alias_searches_and_selected_profile_ref(self):
        self.model.set_filter("rolled-steel")
        cases = ("W310x52", "W12x35", "HP310", "U6x12.2", "T1 1/4", "L50x5", "L2x1/4")
        for query in cases:
            with self.subTest(query=query):
                result = self.model.set_query(query)
                self.assertTrue(result)
                selected = self.model.select(result[0].ref)
                self.assertEqual(self.model.selected_ref, selected.ref)

    def test_empty_state_clears_selection(self):
        self.model.set_filter("rolled-steel", "w")
        self.assertIsNotNone(self.model.selected_ref)
        self.assertEqual(self.model.set_query("perfil-inexistente"), ())
        self.assertIsNone(self.model.selected_ref)
        self.assertIsNone(self.model.selected_profile())

    def test_preview_support_matches_core_geometry_only(self):
        w = self.library.search("W310x52")[0]
        geometry = build_section_geometry(w)
        self.assertEqual((geometry.bounds.width, geometry.bounds.height), (167.0, 317.0))
        self.assertEqual(len(geometry.outer_path.segments), 12)
        angle = build_section_geometry(self.library.search("L50x5")[0])
        self.assertEqual(len(angle.outer_path.segments), 6)
        self.assertNotEqual(angle.bounds.min_x, -angle.bounds.max_x)
        channel = build_section_geometry(self.library.search("U6x12.2")[0])
        self.assertEqual((channel.bounds.width, channel.bounds.height), (48.77, 152.4))
        self.assertEqual(channel.geometry_type, "channel_section")
        tapered_i = build_section_geometry(self.library.search("I3x8.48")[0])
        self.assertEqual((tapered_i.geometry_type, tapered_i.geometry_variant),
                         ("i_section", "tapered_flange"))
        self.assertEqual(len(tapered_i.outer_path.segments), 20)
        tee = build_section_geometry(self.library.search("T2x1/4")[0])
        self.assertEqual((tee.geometry_type, tee.geometry_variant),
                         ("tee_section", "standard_tee"))
        self.assertEqual(len(tee.outer_path.segments), 8)

    def test_qt_renderer_consumes_section_geometry_not_dimensions(self):
        source = (ROOT / "freecad/SteelStructures/interactive/profile_browser_preview.py").read_text("utf-8")
        self.assertIn("SectionGeometry2D", source)
        self.assertIn("geometry.outer_path.segments", source)
        self.assertNotIn("profile.geometry", source)
        self.assertIn("QColor(216, 219, 223)", source)
        self.assertIn("preview_segments_for_path", source)
        self.assertIn("path.cubicTo(", source)

    def test_real_dimension_renderer_executes_with_section_bounds_properties(self):
        module = _load_preview_runtime_module()
        profile = self.library.search("W150x13")[0]
        geometry = build_section_geometry(profile)
        dimensions = {row.label: row.value for row in profile_preview_dimension_rows(profile)}
        scene = _FakeScene()
        renderer = object.__new__(module.SectionPreviewView)
        renderer.scene = lambda: scene
        renderer._add_dimensions(geometry, dimensions)

        annotations = [item.html for item in scene.text_items]
        self.assertEqual(len(annotations), 4)
        self.assertIn("<b>(bf)</b>&nbsp;100", annotations[0])
        self.assertIn("<b>(d)</b>&nbsp;148", annotations[1])
        self.assertIn("<b>(tw)</b>&nbsp;4,3", annotations[2])
        self.assertIn("<b>(tf)</b>&nbsp;4,9", annotations[3])
        self.assertGreaterEqual(len(scene.lines), 12)
        self.assertTrue(all(item.flag == (1, True) for item in scene.text_items))
        self.assertTrue(all("&nbsp;" in html for html in annotations))

    def test_tee_renderer_uses_real_centroidal_geometry_and_four_dimensions(self):
        module = _load_preview_runtime_module()
        for query in ("T5/8x1/8", "T1 1/2x1/8", "T2x3/16", "T2x1/4"):
            profile = self.library.search(query)[0]
            geometry = build_section_geometry(profile)
            dimensions = {row.label: row.value for row in profile_preview_dimension_rows(profile)}
            stations = module._tee_dimension_stations(geometry)
            scene = _FakeScene()
            renderer = object.__new__(module.SectionPreviewView)
            renderer.scene = lambda: scene
            renderer._add_dimensions(geometry, dimensions)
            with self.subTest(query=query):
                self.assertEqual(set(dimensions), {"d", "bf", "tw", "tf"})
                self.assertEqual(len(scene.text_items), 4)
                self.assertAlmostEqual(geometry.bounds.max_y,
                                       dict(geometry.dimension_stations)["centroid_from_top"])
                self.assertNotAlmostEqual(geometry.bounds.max_y, -geometry.bounds.min_y)
                self.assertAlmostEqual(
                    stations["tw_right"] - stations["tw_left"],
                    profile.geometry["tw"],
                )
                self.assertAlmostEqual(
                    stations["tf_bottom"] - stations["tf_top"],
                    profile.geometry["tf"],
                )
                self.assertAlmostEqual(
                    stations["tw_section_bottom"], -geometry.bounds.min_y
                )
                tw_item = next(
                    item for item in scene.text_items if "(tw)" in item.html
                )
                tf_item = next(
                    item for item in scene.text_items if "(tf)" in item.html
                )
                self.assertGreater(
                    tw_item.position[1], stations["tw_section_bottom"]
                )
                self.assertEqual(tf_item.position[1], (
                    stations["tf_top"] + stations["tf_bottom"]
                ) / 2.0)
                self.assertGreater(tw_item.position[1], tf_item.position[1])
                self.assertTrue(any(
                    line[0] == line[2] == stations["tw_left"]
                    and line[1] > stations["tw_section_bottom"]
                    and line[3] > line[1]
                    for line in scene.lines
                ))
                self.assertTrue(any(
                    line[0] == line[2] == stations["tw_right"]
                    and line[1] > stations["tw_section_bottom"]
                    and line[3] > line[1]
                    for line in scene.lines
                ))

    def test_u_renderer_uses_shared_geometry_and_four_dimensions_across_sizes(self):
        module = _load_preview_runtime_module()
        for query in ("U3x6.10", "U8x20.50", "U12x37.00"):
            profile = self.library.search(query)[0]
            geometry = build_section_geometry(profile)
            dimensions = {row.label: row.value for row in profile_preview_dimension_rows(profile)}
            scene = _FakeScene()
            renderer = object.__new__(module.SectionPreviewView)
            renderer.scene = lambda: scene
            with self.subTest(query=query):
                renderer._add_dimensions(geometry, dimensions)
                self.assertEqual(set(dimensions), {"d", "bf", "tw", "tf"})
                self.assertEqual(len(scene.text_items), 4)
                self.assertGreaterEqual(len(scene.lines), 12)

    def test_tapered_i_renderer_uses_real_geometry_and_tf_station(self):
        module = _load_preview_runtime_module()
        for query in ("I3x8.48", "I5x14.88", "I6x22.00"):
            profile = self.library.search(query)[0]
            geometry = build_section_geometry(profile)
            dimensions = {row.label: row.value for row in profile_preview_dimension_rows(profile)}
            scene = _FakeScene()
            renderer = object.__new__(module.SectionPreviewView)
            renderer.scene = lambda: scene
            renderer._add_dimensions(geometry, dimensions)
            x_tf, outer_y, inner_y = module._tapered_i_tf_measurement(geometry)
            expected_tf = float(dimensions["tf"].removesuffix(" mm").replace(",", "."))
            with self.subTest(query=query):
                self.assertEqual(set(dimensions), {"d", "bf", "tw", "tf"})
                self.assertEqual(len(scene.text_items), 4)
                self.assertAlmostEqual(x_tf, profile.geometry["bf"] / 2 - profile.geometry["tl"])
                self.assertAlmostEqual(outer_y - inner_y, expected_tf, places=8)
                self.assertEqual(len([
                    segment for segment in geometry.outer_path.segments
                    if hasattr(segment, "center")
                ]), 8)

    def test_u_tf_layout_uses_physical_station_and_keeps_dimension_outside(self):
        module = _load_preview_runtime_module()
        for query in ("U3x6.10", "U12x37.00"):
            profile = self.library.search(query)[0]
            geometry = build_section_geometry(profile)
            dimensions = {
                row.label: row.value for row in profile_preview_dimension_rows(profile)
            }
            x_tf, outer_y, inner_y = module._channel_tf_measurement(geometry)
            web_inner_x = geometry.outer_path.segments[5].start.x
            expected_x = geometry.bounds.min_x + (
                geometry.bounds.width + web_inner_x - geometry.bounds.min_x
            ) / 2.0
            expected_tf = float(dimensions["tf"].removesuffix(" mm").replace(",", "."))
            scene = _FakeScene()
            renderer = object.__new__(module.SectionPreviewView)
            renderer.scene = lambda: scene
            renderer._add_dimensions(geometry, dimensions)
            units = renderer._scene_units_per_pixel(geometry.bounds)
            line_x = geometry.bounds.max_x + module.TF_LINE_OFFSET_PIXELS * units
            with self.subTest(query=query):
                self.assertAlmostEqual(x_tf, expected_x)
                self.assertAlmostEqual(outer_y - inner_y, expected_tf, places=8)
                self.assertGreater(line_x, geometry.bounds.max_x)
                self.assertTrue(any(
                    line[:4] == (line_x, -outer_y, line_x, -inner_y)
                    for line in scene.lines
                ))
                # The last two ellipses are the fixed-pixel witnesses at the real faces.
                self.assertEqual(
                    [item.position for item in scene.ellipse_items[-2:]],
                    [(x_tf, -outer_y), (x_tf, -inner_y)],
                )

    def test_u_insertion_marker_maps_all_shared_references_and_changes_position(self):
        module = _load_preview_runtime_module()
        geometry = build_section_geometry(self.library.search("U6x12.2")[0])
        labels = (
            "Centroide", "Centro da alma", "Face externa da alma",
            "Canto superior traseiro", "Canto inferior traseiro",
            "Ponta superior da mesa", "Ponta inferior da mesa",
        )
        positions = []
        for label in labels:
            scene = _FakeScene()
            renderer = object.__new__(module.SectionPreviewView)
            renderer.scene = lambda: scene
            self.assertTrue(renderer._add_insertion_marker(geometry, label))
            point = insertion_reference(geometry, label).point
            positions.append(scene.ellipse_items[0].position)
            with self.subTest(label=label):
                self.assertEqual(scene.ellipse_items[0].position, (point.x, -point.y))
                self.assertEqual(
                    scene.ellipse_items[0].args[:4],
                    (-module.INSERTION_MARKER_RADIUS_PIXELS,) * 2
                    + (module.INSERTION_MARKER_RADIUS_PIXELS * 2.0,) * 2,
                )
                self.assertTrue(all(item.flag == (1, True) for item in scene.ellipse_items))
        self.assertEqual(len(set(positions)), len(labels))

    def test_u_marker_rejects_insertion_from_another_family(self):
        module = _load_preview_runtime_module()
        geometry = build_section_geometry(self.library.search("U6x12.2")[0])
        scene = _FakeScene()
        renderer = object.__new__(module.SectionPreviewView)
        renderer.scene = lambda: scene
        self.assertFalse(renderer._add_insertion_marker(geometry, "Face superior"))
        self.assertEqual(scene.ellipses, [])

    def test_u_tf_extension_leaves_clearance_around_selected_upper_tip(self):
        module = _load_preview_runtime_module()
        profile = self.library.search("U6x12.2")[0]
        geometry = build_section_geometry(profile)
        dimensions = {
            row.label: row.value for row in profile_preview_dimension_rows(profile)
        }
        scene = _FakeScene()
        renderer = object.__new__(module.SectionPreviewView)
        renderer.scene = lambda: scene
        renderer._add_dimensions(geometry, dimensions, "Ponta superior da mesa")
        marker = insertion_reference(geometry, "Ponta superior da mesa").point
        marker_y = -marker.y
        crossing = [
            line for line in scene.lines
            if line[1] == line[3] == marker_y
            and min(line[0], line[2]) < marker.x < max(line[0], line[2])
        ]
        self.assertEqual(crossing, [])

    def test_dimension_renderer_handles_large_w_and_wide_hp(self):
        module = _load_preview_runtime_module()
        cases = {
            "W200x46.1": {"d": "203 mm", "bf": "203 mm", "tw": "7,2 mm", "tf": "11 mm"},
            "W310x67": {"d": "306 mm", "bf": "204 mm", "tw": "8,5 mm", "tf": "14,6 mm"},
            "W410x67": {"d": "410 mm", "bf": "179 mm", "tw": "8,8 mm", "tf": "14,4 mm"},
            "W610x217": {"d": "628 mm", "bf": "328 mm", "tw": "16,5 mm", "tf": "27,7 mm"},
            "HP310x132": {"d": "314 mm", "bf": "313 mm", "tw": "18,3 mm", "tf": "18,3 mm"},
        }
        for query, expected in cases.items():
            with self.subTest(query=query):
                profile = self.library.search(query)[0]
                geometry = build_section_geometry(profile)
                dimensions = {
                    row.label: row.value for row in profile_preview_dimension_rows(profile)
                }
                self.assertEqual(dimensions, expected)
                scene = _FakeScene()
                renderer = object.__new__(module.SectionPreviewView)
                renderer.scene = lambda: scene
                renderer._add_dimensions(geometry, dimensions)
                annotations = [item.html for item in scene.text_items]
                self.assertEqual(len(annotations), 4)
                self.assertEqual(
                    [next(symbol for symbol in ("bf", "d", "tw", "tf") if f"({symbol})" in html)
                     for html in annotations],
                    ["bf", "d", "tw", "tf"],
                )
                self.assertTrue(all("mm" not in html for html in annotations))

    def test_equal_angle_renderer_executes_real_b_and_t_dimensions(self):
        module = _load_preview_runtime_module()
        for query in (
            "L40x3", "L50x5", "L100x9",
            "L1/2x1/8", "L2x1/4", "L4x1/2", "L6x1/2", "L8x3/4",
        ):
            with self.subTest(query=query):
                profile = self.library.search(query)[0]
                geometry = build_section_geometry(profile)
                dimensions = {
                    row.label: row.value for row in profile_preview_dimension_rows(profile)
                }
                scene = _FakeScene()
                renderer = object.__new__(module.SectionPreviewView)
                renderer.scene = lambda: scene
                renderer._add_dimensions(geometry, dimensions)
                annotations = [item.html for item in scene.text_items]
                self.assertEqual(len(annotations), 3)
                self.assertIn("<b>(b)</b>&nbsp;", annotations[0])
                self.assertIn("<b>(b)</b>&nbsp;", annotations[1])
                self.assertIn("<b>(t)</b>&nbsp;", annotations[2])
                self.assertTrue(all("mm" not in html for html in annotations))
                self.assertGreaterEqual(len(scene.lines), 16)
                scene_units = renderer._scene_units_per_pixel(geometry.bounds)
                horizontal_b_line_y = scene.text_items[0].position[1]
                self.assertAlmostEqual(
                    (horizontal_b_line_y + geometry.bounds.min_y) / scene_units,
                    module.ANGLE_B_OFFSET_PIXELS,
                )
                self.assertLess(module.ANGLE_B_OFFSET_PIXELS, module.BF_OFFSET_PIXELS)
                vertical_b_line_x = scene.text_items[1].position[0]
                self.assertAlmostEqual(
                    (geometry.bounds.min_x - vertical_b_line_x) / scene_units,
                    module.ANGLE_VERTICAL_B_OFFSET_PIXELS,
                )
                self.assertGreater(
                    module.ANGLE_VERTICAL_B_OFFSET_PIXELS,
                    module.ANGLE_B_OFFSET_PIXELS,
                )
                t_item = scene.text_items[2]
                horizontal_leg = geometry.outer_path.segments[1]
                leg_top = -horizontal_leg.end.y
                leg_bottom = -horizontal_leg.start.y
                t_extensions = [
                    item for item in scene.line_items
                    if getattr(item, "flag", None) == (1, True)
                    and getattr(item, "position", None)
                    in ((t_item.position[0], leg_top), (t_item.position[0], leg_bottom))
                    and item.args[1] == item.args[3] == 0.0
                ]
                self.assertEqual(len(t_extensions), 2)
                self.assertEqual(
                    {item.args[:4] for item in t_extensions},
                    {(0.0, 0.0, module.ANGLE_T_EXTENSION_OVERHANG_PIXELS, 0.0)},
                )
                self.assertAlmostEqual(
                    scene.text_items[1].position[1],
                    (-geometry.bounds.max_y - geometry.bounds.min_y) / 2.0,
                )

    def test_equal_angle_t_extensions_do_not_depend_on_label_width(self):
        module = _load_preview_runtime_module()

        def render_t_layout(query):
            profile = self.library.search(query)[0]
            geometry = build_section_geometry(profile)
            dimensions = {
                row.label: row.value for row in profile_preview_dimension_rows(profile)
            }
            scene = _FakeScene()
            renderer = object.__new__(module.SectionPreviewView)
            renderer.scene = lambda: scene
            renderer._add_dimensions(geometry, dimensions)
            label = scene.text_items[2]
            extensions = [
                item.args[:4] for item in scene.line_items
                if getattr(item, "flag", None) == (1, True)
                and getattr(item, "position", (None,))[0] == label.position[0]
                and item.args[:4] == (
                    0.0, 0.0, module.ANGLE_T_EXTENSION_OVERHANG_PIXELS, 0.0,
                )
            ]
            return label.boundingRect().width(), extensions

        short_width, short_extensions = render_t_layout("L40x3")
        long_width, long_extensions = render_t_layout("L8x3/4")
        self.assertNotEqual(short_width, long_width)
        self.assertEqual(short_extensions, long_extensions)
        self.assertEqual(len(short_extensions), 2)

    def test_equal_angle_balanced_envelope_keeps_section_as_visual_reference(self):
        module = _load_preview_runtime_module()

        class VisualBounds:
            def __init__(self, left, right, top, bottom):
                self._values = left, right, top, bottom

            def left(self): return self._values[0]
            def right(self): return self._values[1]
            def top(self): return self._values[2]
            def bottom(self): return self._values[3]

        for query in ("L40x3", "L50x5", "L100x9"):
            geometry = build_section_geometry(self.library.search(query)[0])
            bounds = geometry.bounds
            visual = VisualBounds(
                bounds.min_x - 22, bounds.max_x + 35,
                -bounds.max_y - 8, -bounds.min_y + 31,
            )
            x, y, width, height = module._balanced_section_envelope(bounds, visual, 12)
            self.assertAlmostEqual(x + width / 2.0,
                                   (bounds.min_x + bounds.max_x) / 2.0)
            self.assertAlmostEqual(y + height / 2.0,
                                   (-bounds.max_y - bounds.min_y) / 2.0)
            self.assertLessEqual(x, visual.left())
            self.assertGreaterEqual(x + width, visual.right())
            self.assertLessEqual(y, visual.top())
            self.assertGreaterEqual(y + height, visual.bottom())

    def test_equal_angle_subtitle_identifies_equal_legs_without_renaming_series(self):
        module = _load_browser_runtime_module()
        angle = self.library.search("L50x5")[0]
        w = self.library.search("W310x52")[0]
        self.assertEqual(
            module._profile_subtitle(angle, "Cantoneiras - Métricas"),
            "Cantoneiras - Métricas — Abas iguais — Gerdau",
        )
        self.assertEqual(module._profile_subtitle(w, "Perfis W"), "Perfis W — Gerdau")

    def test_equal_angle_axes_cross_catalog_centroid_not_bounding_box_center(self):
        module = _load_preview_runtime_module()
        geometry = build_section_geometry(self.library.search("L50x5")[0])
        scene = _FakeScene()
        renderer = object.__new__(module.SectionPreviewView)
        renderer.scene = lambda: scene
        renderer._add_axes(geometry)
        self.assertEqual(scene.lines[0][1:4:2], (0.0, 0.0))
        self.assertEqual((scene.lines[1][0], scene.lines[1][2]), (0.0, 0.0))
        self.assertNotAlmostEqual(
            (geometry.bounds.min_x + geometry.bounds.max_x) / 2.0, 0.0
        )
        self.assertEqual(len(scene.ellipses), 1)

    def test_d_dimension_is_interrupted_and_tf_label_is_right_of_vertical_measure(self):
        module = _load_preview_runtime_module()
        profile = self.library.search("W150x13")[0]
        geometry = build_section_geometry(profile)
        dimensions = {row.label: row.value for row in profile_preview_dimension_rows(profile)}
        scene = _FakeScene()
        renderer = object.__new__(module.SectionPreviewView)
        renderer.scene = lambda: scene
        renderer._add_dimensions(geometry, dimensions)

        gap_x = renderer._d_offset_pixels(geometry.bounds) * renderer._scene_units_per_pixel(geometry.bounds)
        d_x = geometry.bounds.min_x - gap_x
        d_segments = [
            line for line in scene.lines
            if line[0] == d_x and line[2] == d_x
            and min(line[1], line[3]) <= 0.0 <= max(line[1], line[3])
        ]
        self.assertEqual(d_segments, [])
        split_d_segments = [
            line for line in scene.lines if line[0] == d_x and line[2] == d_x
        ]
        self.assertEqual(len(split_d_segments), 2)
        self.assertEqual(scene.text_items[1].position, (d_x, 0.0))
        d_overshoot = module.EXTENSION_OVERSHOOT_PIXELS * renderer._scene_units_per_pixel(
            geometry.bounds
        )
        d_extensions = [
            line for line in scene.lines
            if line[1] == line[3]
            and line[1] in (-geometry.bounds.max_y, -geometry.bounds.min_y)
            and min(line[0], line[2]) == d_x - d_overshoot
        ]
        self.assertEqual(len(d_extensions), 2)
        web_right = geometry.outer_path.segments[3].end.x
        tw_item = scene.text_items[2]
        self.assertEqual(tw_item.position, (web_right, 0.0))
        self.assertEqual(tw_item.transform[0], module.TW_TEXT_OFFSET)
        device_lines = [item for item in scene.line_items if getattr(item, "flag", None) == (1, True)]
        tw_extension = next(
            item for item in device_lines
            if item.position == (web_right, 0.0)
            and item.args[1] == item.args[3] == 0.0
            and item.args[2] > module.TW_TEXT_OFFSET
        )
        self.assertGreaterEqual(
            tw_extension.args[2],
            module.TW_TEXT_OFFSET + tw_item.boundingRect().width()
            + module.LINE_END_PADDING + module.EXTENSION_OVERSHOOT_PIXELS,
        )
        tf_item = scene.text_items[3]
        self.assertEqual(tf_item.transform[0], module.TF_TEXT_OFFSET)
        self.assertLess(tf_item.position[1], -geometry.bounds.min_y)
        self.assertFalse(any(
            line[1] == line[3] and line[1] > -geometry.bounds.min_y
            for line in scene.lines
        ))
        tick_items = [
            item for item in device_lines
            if item.args[:4] == (
                -module.TICK_PIXELS, module.TICK_PIXELS,
                module.TICK_PIXELS, -module.TICK_PIXELS,
            )
        ]
        self.assertEqual(len(tick_items), 8)
        self.assertTrue(all(item.args[-1]._color.rgb == module.DIMENSION_COLOR for item in tick_items))
        tf_overshoots = [
            item for item in device_lines
            if item.args[:4] == (0.0, 0.0, module.EXTENSION_OVERSHOOT_PIXELS, 0.0)
        ]
        self.assertEqual(len(tf_overshoots), 2)
        scene_units = renderer._scene_units_per_pixel(geometry.bounds)
        bf_line_y = -geometry.bounds.max_y - module.BF_OFFSET_PIXELS * scene_units
        bf_extension_ends = [
            min(line[1], line[3]) for line in scene.lines
            if line[0] == line[2] and line[0] in (geometry.bounds.min_x, geometry.bounds.max_x)
        ]
        self.assertIn(
            bf_line_y - module.EXTENSION_OVERSHOOT_PIXELS * scene_units,
            bf_extension_ends,
        )

    def test_ue_renderer_draws_only_four_dimensions_at_approved_stations(self):
        module = _load_preview_runtime_module()
        profile = self.library.search("Ue 150x60x20x3.00")[0]
        geometry = build_section_geometry(profile)
        dimensions = {row.label: row.value for row in profile_preview_dimension_rows(profile)}
        scene = _FakeScene()
        renderer = object.__new__(module.SectionPreviewView)
        renderer.scene = lambda: scene
        renderer._add_dimensions(geometry, dimensions)
        self.assertEqual(set(dimensions), {"bw", "bf", "D", "t", "ri"})
        rendered = {item.html for item in scene.text_items}
        for symbol in ("bw", "bf", "D", "t"):
            self.assertTrue(any(f"<b>({symbol})</b>" in html for html in rendered))
        self.assertFalse(any("<b>(ri)</b>" in html for html in rendered))
        self.assertEqual(len(scene.text_items), 4)

        stations = dict(geometry.dimension_stations)
        nominal_bottom = -stations["nominal_bottom_y"]
        lower_lip_tip = -stations["lower_lip_tip_y"]
        vertical_lines = [line for line in scene.lines if line[0] == line[2]]
        self.assertTrue(any(
            {line[1], line[3]} == {lower_lip_tip, nominal_bottom}
            for line in vertical_lines
        ))

        inner_flange = geometry.outer_path.segments[2]
        expected_x = inner_flange.start.x + 0.62 * (
            inner_flange.end.x - inner_flange.start.x
        )
        expected_y = -(inner_flange.start.y + 0.62 * (
            inner_flange.end.y - inner_flange.start.y
        ))
        self.assertTrue(any(
            abs(line[0] - expected_x) < 1e-9 and abs(line[1] - expected_y) < 1e-9
            for line in scene.lines
        ))
        self.assertGreater(len(scene.lines), 10)

    def test_ue_layout_uses_constant_apparent_offsets_across_reference_sizes(self):
        module = _load_preview_runtime_module()
        for query in (
                "Ue 50x25x10x1.20",
                "Ue 150x60x20x3.00",
                "Ue 300x85x25x2.25"):
            with self.subTest(query=query):
                profile = self.library.search(query)[0]
                geometry = build_section_geometry(profile)
                dimensions = {
                    row.label: row.value
                    for row in profile_preview_dimension_rows(profile)
                }
                scene = _FakeScene()
                renderer = object.__new__(module.SectionPreviewView)
                renderer.scene = lambda: scene
                renderer._add_dimensions(geometry, dimensions)
                units = renderer._scene_units_per_pixel(geometry.bounds)
                stations = dict(geometry.dimension_stations)

                d_label = scene.text_items[2]
                expected_d_x = (
                    stations["nominal_flange_tip_x"]
                    + module.UE_D_OFFSET_PIXELS * units
                )
                self.assertAlmostEqual(d_label.position[0], expected_d_x)
                self.assertEqual(d_label.transform[0], module.UE_D_TEXT_OFFSET_PIXELS)

                t_leader = scene.lines[-1]
                leader_pixels = (
                    (t_leader[2] - t_leader[0]) ** 2
                    + (t_leader[3] - t_leader[1]) ** 2
                ) ** 0.5 / units
                self.assertGreaterEqual(leader_pixels, 18.0)
                self.assertLessEqual(leader_pixels, 35.0)
                self.assertEqual(scene.text_items[3].transform[0],
                                 module.UE_D_TEXT_OFFSET_PIXELS)

    def test_d_offset_compensates_fit_compression_for_medium_and_large_w(self):
        module = _load_preview_runtime_module()
        for query in ("W150x13", "W410x67", "W610x217"):
            with self.subTest(query=query):
                geometry = build_section_geometry(self.library.search(query)[0])
                scene = _FakeScene()
                renderer = object.__new__(module.SectionPreviewView)
                renderer.scene = lambda: scene
                dimensions = {
                    row.label: row.value
                    for row in profile_preview_dimension_rows(self.library.search(query)[0])
                }
                renderer._add_dimensions(geometry, dimensions)
                units_per_pixel = renderer._scene_units_per_pixel(geometry.bounds)
                d_line_x = scene.text_items[1].position[0]
                apparent_offset = (geometry.bounds.min_x - d_line_x) / units_per_pixel
                self.assertAlmostEqual(apparent_offset, renderer._d_offset_pixels(geometry.bounds))
                if query == "W150x13":
                    self.assertAlmostEqual(apparent_offset, module.D_OFFSET_PIXELS)
                if query == "W610x217":
                    self.assertAlmostEqual(
                        apparent_offset,
                        module.D_OFFSET_PIXELS + module.D_MAX_COMPENSATION_PIXELS,
                    )

    def test_hollow_renderer_uses_nominal_family_dimensions_without_radius_labels(self):
        module = _load_preview_runtime_module()
        cases = (
            ("SHS 75x75x2", {"B", "t"}, {"b", "t"}),
            ("RHS 150x100x4,75", {"H", "B", "t"}, {"h", "b", "t"}),
            ("RHS 203,20x76,20x16", {"H", "B", "t"}, {"h", "b", "t"}),
            ("CHS 26x0,75", {"ØD", "t"}, {"Ø", "t"}),
            ("CHS 88,90x3", {"ØD", "t"}, {"Ø", "t"}),
        )
        for query, catalog_symbols, display_symbols in cases:
            with self.subTest(query=query):
                profile = self.library.search(query)[0]
                geometry = build_section_geometry(profile)
                dimensions = {
                    row.label: row.value
                    for row in profile_preview_dimension_rows(profile)
                }
                self.assertEqual(set(dimensions), catalog_symbols)
                scene = _FakeScene()
                renderer = object.__new__(module.SectionPreviewView)
                renderer.scene = lambda: scene
                renderer._add_dimensions(geometry, dimensions)
                rendered = {item.html for item in scene.text_items}
                for symbol in display_symbols:
                    expected = f"<b>Ø</b>" if symbol == "Ø" else f"<b>({symbol})</b>"
                    self.assertTrue(any(expected in html for html in rendered))
                if geometry.geometry_variant == "circular":
                    self.assertFalse(any("(Ød)" in html for html in rendered))
                self.assertFalse(any("(ro)" in html or "(ri)" in html for html in rendered))
                self.assertEqual(len(scene.text_items), len(display_symbols))
                self.assertGreaterEqual(len(scene.lines), 1 + 3 * (len(display_symbols) - 1))

    def test_hollow_fit_is_continuous_and_independent_of_absolute_catalog_size(self):
        module = _load_preview_runtime_module()
        small = build_section_geometry(self.library.search("SHS 15,87x15,87x0,75")[0]).bounds
        large = build_section_geometry(self.library.search("SHS 254x254x5,6")[0]).bounds
        small_units = module._fit_units_per_pixel(small, 500, 240)
        large_units = module._fit_units_per_pixel(large, 500, 240)
        self.assertAlmostEqual(small.height / small_units, large.height / large_units)
        self.assertAlmostEqual(large_units / small_units, large.height / small.height)
        self.assertLess(small_units, 0.75)

    def test_hollow_scene_envelope_is_section_centred_and_ignores_text_bounds(self):
        module = _load_preview_runtime_module()
        normalized_envelopes = []
        for query in ("SHS 15,87x15,87x0,75", "SHS 254x254x5,6"):
            bounds = build_section_geometry(self.library.search(query)[0]).bounds
            units = module._fit_units_per_pixel(bounds, 500, 240)
            left, top, width, height = module._hollow_section_envelope(bounds, units)
            section_center = (
                (bounds.min_x + bounds.max_x) / 2.0,
                (-bounds.max_y - bounds.min_y) / 2.0,
            )
            envelope_center = (left + width / 2.0, top + height / 2.0)
            self.assertAlmostEqual(envelope_center[0], section_center[0])
            self.assertAlmostEqual(envelope_center[1], section_center[1])
            normalized_envelopes.append((width / units, height / units))
        self.assertAlmostEqual(normalized_envelopes[0][0], normalized_envelopes[1][0])
        self.assertAlmostEqual(normalized_envelopes[0][1], normalized_envelopes[1][1])

    def test_hollow_scene_envelope_reserves_annotation_space_in_screen_units(self):
        module = _load_preview_runtime_module()
        for query in ("RHS 60x30x1,25", "RHS 203,20x76,20x16", "CHS 26x0,75"):
            bounds = build_section_geometry(self.library.search(query)[0]).bounds
            units = module._fit_units_per_pixel(bounds, 500, 240)
            left, top, width, height = module._hollow_section_envelope(bounds, units)
            self.assertAlmostEqual((bounds.min_x - left) / units,
                                   module.HOLLOW_HORIZONTAL_RESERVE_PIXELS)
            self.assertAlmostEqual((-bounds.max_y - top) / units,
                                   module.HOLLOW_VERTICAL_RESERVE_PIXELS)
            self.assertAlmostEqual((left + width - bounds.max_x) / units,
                                   module.HOLLOW_HORIZONTAL_RESERVE_PIXELS)
            self.assertAlmostEqual((top + height + bounds.min_y) / units,
                                   module.HOLLOW_VERTICAL_RESERVE_PIXELS)

    def test_hollow_screen_space_offsets_and_leader_are_size_invariant(self):
        module = _load_preview_runtime_module()
        for query in (
                "SHS 15,87x15,87x0,75", "SHS 254x254x5,6",
                "RHS 60x30x1,25", "RHS 203,20x76,20x16",
                "CHS 26x0,75", "CHS 88,90x3"):
            with self.subTest(query=query):
                profile = self.library.search(query)[0]
                geometry = build_section_geometry(profile)
                dimensions = {row.label: row.value for row in profile_preview_dimension_rows(profile)}
                scene = _FakeScene()
                renderer = object.__new__(module.SectionPreviewView)
                renderer.scene = lambda: scene
                units = renderer._hollow_units_per_pixel(geometry.bounds)
                renderer._add_dimensions(geometry, dimensions)
                leader = scene.lines[-1]
                leader_dx = abs(leader[2] - leader[0]) / units
                leader_dy = abs(leader[3] - leader[1]) / units
                expected_dx = (module.CHS_T_LEADER_X_PIXELS
                               if geometry.geometry_variant == "circular"
                               else module.HOLLOW_T_LEADER_X_PIXELS)
                expected_dy = (module.CHS_T_LEADER_Y_PIXELS
                               if geometry.geometry_variant == "circular"
                               else module.HOLLOW_T_LEADER_Y_PIXELS)
                self.assertAlmostEqual(leader_dx, expected_dx)
                self.assertAlmostEqual(leader_dy, expected_dy)
                for coordinate in leader[:4]:
                    self.assertTrue(float("-inf") < coordinate < float("inf"))

    def test_chs_thickness_leader_targets_wall_midpoint_in_lower_right_quadrant(self):
        module = _load_preview_runtime_module()
        for query in ("CHS 26x0,75", "CHS 33,70x3,75", "CHS 88,90x3", "CHS 165,10x9,5"):
            with self.subTest(query=query):
                profile = self.library.search(query)[0]
                geometry = build_section_geometry(profile)
                dimensions = {row.label: row.value for row in profile_preview_dimension_rows(profile)}
                scene = _FakeScene()
                renderer = object.__new__(module.SectionPreviewView)
                renderer.scene = lambda: scene
                renderer._add_dimensions(geometry, dimensions)
                target_x, target_y = scene.lines[-1][:2]
                stations = dict(geometry.dimension_stations)
                expected_radius = (
                    stations["diameter"] + stations["inner_diameter"]
                ) / 4.0
                self.assertGreater(target_x, 0.0)
                self.assertGreater(target_y, 0.0)
                self.assertAlmostEqual(
                    (target_x ** 2 + target_y ** 2) ** 0.5, expected_radius,
                )

    def test_rhs_hollow_fit_preserves_geometric_aspect_ratio(self):
        module = _load_preview_runtime_module()
        for query in ("RHS 60x30x1,25", "RHS 150x100x4,75", "RHS 203,20x76,20x16"):
            geometry = build_section_geometry(self.library.search(query)[0])
            units = module._fit_units_per_pixel(geometry.bounds, 500, 240)
            screen_width = geometry.bounds.width / units
            screen_height = geometry.bounds.height / units
            self.assertAlmostEqual(
                screen_height / screen_width,
                geometry.bounds.height / geometry.bounds.width,
            )

    def test_rhs_dimension_contract_keeps_h_vertical_and_b_horizontal(self):
        module = _load_preview_runtime_module()
        profile = self.library.search("RHS 150x100x4,75")[0]
        geometry = build_section_geometry(profile)
        dimensions = {row.label: row.value for row in profile_preview_dimension_rows(profile)}
        self.assertEqual(dimensions["H"], "150 mm")
        self.assertEqual(dimensions["B"], "100 mm")
        scene = _FakeScene()
        renderer = object.__new__(module.SectionPreviewView)
        renderer.scene = lambda: scene
        renderer._add_dimensions(geometry, dimensions)
        b_label = next(item for item in scene.text_items if "(b)" in item.html)
        h_label = next(item for item in scene.text_items if "(h)" in item.html)
        self.assertLess(b_label.position[1], -geometry.bounds.max_y)
        self.assertLess(h_label.position[0], geometry.bounds.min_x)

    def test_properties_renderer_draws_axes_centroid_and_scale_independent_labels(self):
        module = _load_preview_runtime_module()
        profile = self.library.search("W310x52")[0]
        scene = _FakeScene()
        renderer = object.__new__(module.SectionPreviewView)
        renderer.scene = lambda: scene
        renderer._add_axes(build_section_geometry(profile))
        self.assertEqual(scene.texts, ["X", "X", "Y", "Y"])
        self.assertEqual(len(scene.ellipses), 1)
        self.assertTrue(all(item.flag == (1, True) for item in scene.text_items))
        self.assertEqual(scene.lines[0][-1]._color.rgb, (205, 45, 45))
        self.assertEqual(scene.lines[1][-1]._color.rgb, (38, 145, 72))
        self.assertEqual(scene.lines[0][-1].width, 1.05)
        self.assertEqual(scene.lines[0][-1].dash_pattern, (9.0, 3.0, 2.0, 3.0))

    def test_supported_unsupported_supported_preview_transition(self):
        module = _load_browser_runtime_module()

        class Preview:
            def __init__(self):
                self.rendered = []
                self.clear_count = 0

            def set_geometry(self, geometry, dimensions, mode, insertion=None):
                self.rendered.append((geometry, tuple(dimensions), mode, insertion))

            def clear_geometry(self):
                self.clear_count += 1

        class Stack:
            def __init__(self):
                self.current = None

            def setCurrentWidget(self, widget):
                self.current = widget

        class Message:
            def __init__(self):
                self.text = ""

            def setText(self, text):
                self.text = text

        class Tabs:
            def __init__(self, index=0):
                self.index = index

            def currentIndex(self):
                return self.index

        dialog = types.SimpleNamespace(
            preview=Preview(), preview_stack=Stack(), preview_message=Message(), tabs=Tabs()
        )
        dialog._current_preview_mode = types.MethodType(
            module.ProfileBrowserDialog._current_preview_mode, dialog
        )
        sequence = (
            "W150x13", "L50x5", "U6x12.2", "U3x7.44", "L2x1/4",
            "T2x1/4", "HP310x132", "W150x13",
        )
        expected_supported = (True, True, True, False, True, True, True, True)
        for query, supported in zip(sequence, expected_supported):
            profile = self.library.search(query)[0]
            module.ProfileBrowserDialog._update_preview(dialog, profile)
            expected_widget = dialog.preview if supported else dialog.preview_message
            self.assertIs(dialog.preview_stack.current, expected_widget)
            if supported:
                expected_dimensions = 2 if profile.geometry_type == "equal_angle" else 4
                self.assertEqual(len(dialog.preview.rendered[-1][1]), expected_dimensions)
                self.assertEqual(dialog.preview.rendered[-1][2], "dimensions")
                self.assertIsNone(dialog.preview.rendered[-1][3])
            else:
                if profile.geometry_status == "pending_technical_review":
                    self.assertIn("inconsistência entre fontes técnicas Gerdau", dialog.preview_message.text)
                else:
                    self.assertIn("não disponível", dialog.preview_message.text)
        self.assertEqual(dialog.preview.clear_count, 1)
        self.assertEqual(len(dialog.preview.rendered), 7)

    def test_select_context_forwards_insertion_while_isolated_catalog_does_not(self):
        module = _load_browser_runtime_module()

        class Preview:
            def __init__(self): self.insertions = []
            def set_geometry(self, _geometry, _dimensions, _mode, insertion=None):
                self.insertions.append(insertion)
            def clear_geometry(self): pass

        base = dict(
            preview=Preview(),
            preview_stack=types.SimpleNamespace(setCurrentWidget=lambda _widget: None),
            preview_message=types.SimpleNamespace(setText=lambda _text: None),
            tabs=types.SimpleNamespace(currentIndex=lambda: 0),
        )
        isolated = types.SimpleNamespace(**base)
        isolated._current_preview_mode = types.MethodType(
            module.ProfileBrowserDialog._current_preview_mode, isolated
        )
        profile = self.library.search("U6x12.2")[0]
        module.ProfileBrowserDialog._update_preview(isolated, profile)
        self.assertEqual(isolated.preview.insertions[-1], None)

        selection = types.SimpleNamespace(**{
            **base, "preview": Preview(), "insertion": "Centro da alma"
        })
        selection._current_preview_mode = types.MethodType(
            module.ProfileBrowserDialog._current_preview_mode, selection
        )
        module.ProfileBrowserDialog._update_preview(selection, profile)
        self.assertEqual(selection.preview.insertions[-1], "Centro da alma")

    def test_tab_mode_changes_and_profile_changes_preserve_current_mode(self):
        module = _load_browser_runtime_module()

        class Preview:
            def __init__(self):
                self.modes = []

            def set_geometry(self, _geometry, _dimensions, mode, _insertion=None):
                self.modes.append(mode)

            def clear_geometry(self):
                pass

        class Stack:
            def setCurrentWidget(self, _widget):
                pass

        class Tabs:
            index = 0

            def currentIndex(self):
                return self.index

        current = self.library.search("W150x13")[0]
        dialog = types.SimpleNamespace(
            preview=Preview(), preview_stack=Stack(), preview_message=types.SimpleNamespace(
                setText=lambda _text: None
            ), tabs=Tabs(), model=types.SimpleNamespace(selected_profile=lambda: current),
        )
        dialog._current_preview_mode = types.MethodType(
            module.ProfileBrowserDialog._current_preview_mode, dialog
        )
        dialog._update_preview = types.MethodType(module.ProfileBrowserDialog._update_preview, dialog)

        for index, expected in ((0, "dimensions"), (1, "properties"), (2, "neutral"), (0, "dimensions")):
            dialog.tabs.index = index
            module.ProfileBrowserDialog._tab_changed(dialog, index)
            self.assertEqual(dialog.preview.modes[-1], expected)

        dialog.tabs.index = 1
        for query in ("W150x13", "W310x52", "HP310x132", "L50x5", "L2x1/4"):
            dialog._update_preview(self.library.search(query)[0])
            self.assertEqual(dialog.preview.modes[-1], "properties")

        dialog.tabs.index = 2
        dialog._update_preview(self.library.search("L100x9")[0])
        self.assertEqual(dialog.preview.modes[-1], "neutral")

    def test_profile_table_has_only_designation_column(self):
        source = (ROOT / "freecad/SteelStructures/interactive/profile_browser.py").read_text("utf-8")
        self.assertIn("QTableWidget(0, 1)", source)
        self.assertIn('setHorizontalHeaderLabels(("Perfil",))', source)
        self.assertNotIn('"Massa [kg/m]"', source)
        self.assertNotIn('"Família"', source)
        self.assertIn("setDefaultSectionSize(self.table.fontMetrics().height() + 6)", source)

    def test_properties_places_axis_groups_side_by_side(self):
        source = (ROOT / "freecad/SteelStructures/interactive/profile_browser.py").read_text("utf-8")
        self.assertIn('"Eixo X-X": (1, 0, 1, 1)', source)
        self.assertIn('"Eixo Y-Y": (1, 1, 1, 1)', source)
        self.assertIn("QGridLayout(page)", source)

    def test_source_tab_renders_compact_presentation_groups(self):
        source = (ROOT / "freecad/SteelStructures/interactive/profile_browser.py").read_text("utf-8")
        self.assertIn("profile_source_groups", source)
        self.assertIn("def _source_widget(self, groups):", source)
        self.assertIn("QGroupBox(group.title)", source)
        self.assertIn("self._source_widget(profile_source_groups(profile))", source)
        self.assertNotIn("self._rows_widget(profile_source_rows(profile))", source)

    def test_select_mode_accepts_only_profiles_allowed_by_its_capability(self):
        module = _load_browser_runtime_module()
        accepted = []
        dialog = types.SimpleNamespace(
            mode=module.ProfileBrowserDialog.SELECT_MODE,
            SELECT_MODE=module.ProfileBrowserDialog.SELECT_MODE,
            selected_profile=lambda: self.library.search("W150x13")[0],
            _is_profile_selectable=lambda profile: profile.series_id in {"w", "hp"},
            accept=lambda: accepted.append(True),
        )
        dialog._current_profile_is_selectable = types.MethodType(
            module.ProfileBrowserDialog._current_profile_is_selectable, dialog
        )
        module.ProfileBrowserDialog._accept_selected(dialog)
        self.assertEqual(accepted, [True])
        dialog.selected_profile = lambda: self.library.search("U6x12.2")[0]
        module.ProfileBrowserDialog._accept_selected(dialog)
        self.assertEqual(accepted, [True])

        for query in ("I3x8.48", "U6x12.2", "T2x1/4", "L50x5", "L2x1/4"):
            dialog.selected_profile = lambda query=query: self.library.search(query)[0]
            self.assertFalse(dialog._current_profile_is_selectable())
        for query in ("W310x52", "HP310x132"):
            dialog.selected_profile = lambda query=query: self.library.search(query)[0]
            self.assertTrue(dialog._current_profile_is_selectable())

    def test_select_and_browse_button_contracts_remain_distinct(self):
        source = (ROOT / "freecad/SteelStructures/interactive/profile_browser.py").read_text("utf-8")
        self.assertIn("QDialogButtonBox.Cancel | QtWidgets.QDialogButtonBox.Ok", source)
        self.assertIn('setText("Selecionar")', source)
        self.assertIn("QDialogButtonBox.Close", source)
        self.assertIn("buttons.accepted.connect(self._accept_selected)", source)
        self.assertIn("initial_profile_ref", source)

    def test_initial_profile_ref_is_preserved_and_missing_ref_falls_back_to_w(self):
        module = _load_browser_runtime_module()

        class TreeItem:
            def __init__(self, value, children=()):
                self.value, self.children = value, list(children)

            def data(self, _column, _role):
                return self.value

            def childCount(self):
                return len(self.children)

            def child(self, index):
                return self.children[index]

        hp_item = TreeItem(("rolled-steel", "hp"))
        w_item = TreeItem(("rolled-steel", "w"))
        root = TreeItem(("rolled-steel", None), (w_item, hp_item))
        selected_items = []
        selected_refs = []
        tree = types.SimpleNamespace(
            topLevelItemCount=lambda: 1,
            topLevelItem=lambda _index: root,
            setCurrentItem=lambda item: selected_items.append(item),
        )
        dialog = types.SimpleNamespace(
            library=self.library, tree=tree,
            _is_profile_selectable=lambda profile: profile.series_id in {"w", "hp"},
            _select_table_ref=lambda ref: selected_refs.append(ref),
            _select_initial_series=lambda: self.fail("catalog has selectable profiles"),
        )
        hp_ref = self.library.search("HP310x132")[0].ref
        module.ProfileBrowserDialog._select_initial_profile(dialog, hp_ref)
        self.assertIs(selected_items[-1], hp_item)
        self.assertEqual(selected_refs[-1], hp_ref)

        missing = type(hp_ref)(hp_ref.catalog_id, "missing")
        module.ProfileBrowserDialog._select_initial_profile(dialog, missing)
        self.assertIs(selected_items[-1], w_item)
        self.assertEqual(selected_refs[-1], self.library.list_profiles(series_id="w")[0].ref)


if __name__ == "__main__":
    unittest.main()
