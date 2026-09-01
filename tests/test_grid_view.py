"""Behavioral tests for the localized Structural Grid view provider."""

from __future__ import annotations

import importlib.util
import sys
import types
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "freecad/SteelStructures/grid_view.py"
GEOMETRY_PATH = ROOT / "freecad/SteelStructures/grid_geometry.py"


class Field:
    def __init__(self): self.value = None
    def setValue(self, *value): self.value = value


class StrictRgbField(Field):
    def setValue(self, *value):
        if len(value) != 3 or not all(type(component) is float for component in value):
            raise TypeError("expected a sequence with 3 floats")
        super().setValue(*value)


class Node:
    def __init__(self):
        self.children = []
        self.translation = Field()
        self.point = Field()
    def addChild(self, child): self.children.append(child)
    def removeChild(self, child): self.children.remove(child)
    def removeAllChildren(self): self.children.clear()


class BaseColor(Node):
    def __init__(self):
        super().__init__()
        self.rgb = StrictRgbField()


class Text(Node):
    LEFT, RIGHT, CENTER = 0, 1, 2


class Coordinate(Node):
    def __init__(self):
        super().__init__()
        self.point = type("Points", (), {
            "setValue": lambda field, *value: setattr(field, "value", value),
            "setValues": lambda field, start, count, values: setattr(
                field, "value", (start, count, values)
            ),
        })()


class Switch(Node):
    def __init__(self):
        super().__init__()
        self.whichChild = None


class FakeCoin:
    SoSeparator = SoTranslation = SoFont = SoDrawStyle = SoPointSet = Node
    SoText2 = Text
    SoCoordinate3 = Coordinate
    SoBaseColor = BaseColor
    SoSwitch = Switch
    SO_SWITCH_ALL = -3
    SO_SWITCH_NONE = -1


class Quantity:
    def __init__(self, value): self.Value = float(value)


class Vector:
    def __init__(self, x, y, z=0.0): self.x, self.y, self.z = x, y, z


class View:
    def __init__(self, obj):
        self.Object = obj
        self.PropertiesList = []
        self.records = {}
        self.modes = []
        self.RootNode = Node()
        self.DrawStyle = "Solid"
        self.PointSize = 1.0
        self.PointColor = (0.2, 0.3, 0.4)
        self.Visibility = True
        self.enum_options = {}
        self.editor_modes = {}
    def addProperty(self, kind, name, group, description):
        self.PropertiesList.append(name); self.records[name] = (kind, group, description); setattr(self, name, None)
    def removeProperty(self, name):
        self.PropertiesList.remove(name); self.records.pop(name, None); self.__dict__.pop(name, None)
    def getTypeIdOfProperty(self, name): return self.records[name][0]
    def setEditorMode(self, name, mode): self.editor_modes[name] = mode
    def __setattr__(self, name, value):
        record = self.__dict__.get("records", {}).get(name)
        if record and record[0] == "App::PropertyEnumeration" and isinstance(value, list):
            self.enum_options[name] = list(value)
            value = value[0] if value else ""
        object.__setattr__(self, name, value)
    def addDisplayMode(self, root, name): self.modes.append((root, name))


def load_module():
    package_name = "_grid_view_test_package"
    package = types.ModuleType(package_name)
    package.__path__ = [str(PATH.parent)]
    sys.modules[package_name] = package
    geometry_spec = importlib.util.spec_from_file_location(
        package_name + ".grid_geometry", GEOMETRY_PATH
    )
    geometry = importlib.util.module_from_spec(geometry_spec)
    sys.modules[geometry_spec.name] = geometry
    geometry_spec.loader.exec_module(geometry)
    spec = importlib.util.spec_from_file_location(package_name + ".grid_view", PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    module.coin = FakeCoin
    return module


class GridViewTests(unittest.TestCase):
    def setUp(self):
        self.module = load_module()
        self.obj = types.SimpleNamespace(
            XSpacings=[6000.0], YSpacings=[5000.0], XStartExtension=Quantity(1000),
            XEndExtension=Quantity(1000), YStartExtension=Quantity(1000), YEndExtension=Quantity(1000),
            XAxisIdentification="Numeric", YAxisIdentification="Alphabetic",
            XAxisLabels=["1", "2"], YAxisLabels=["A", "B"],
            IntersectionPoints=[Vector(0, 0), Vector(6000, 5000)], IntersectionCount=2, Placement=object())
        self.obj.PropertiesList = list(self.module._VIEW_DATA_PROPERTIES)
        self.view = View(self.obj)
        self.proxy = self.module.StructuralGridViewProvider(self.view)

    def test_properties_defaults_and_groups(self):
        expected = {"ShowIntersections": "App::PropertyBool", "ShowLabels": "App::PropertyBool",
                    "IntersectionPointColor": "App::PropertyColor", "IntersectionPointSize": "App::PropertyFloat",
                    "LabelPosition": "App::PropertyEnumeration", "FontName": "App::PropertyEnumeration",
                    "FontSize": "App::PropertyFloat", "TextColor": "App::PropertyColor",
                    "LabelOffset": "App::PropertyLength"}
        self.assertEqual({name: self.view.records[name][0] for name in expected}, expected)
        self.assertTrue(self.view.ShowIntersections and self.view.ShowLabels)
        self.assertEqual((self.view.LabelPosition, self.view.FontName, self.view.FontSize,
                          getattr(self.view.LabelOffset, "Value", self.view.LabelOffset)),
                         ("Both", "Sans", 14.0, 250.0))
        self.assertTrue(all(self.view.records[name][1] == "Grid Appearance" for name in expected))
        self.assertEqual((self.view.LineWidth, self.view.DrawStyle, self.view.PointSize,
                          self.view.IntersectionPointSize), (1.0, "Dashdot", 0.0, 5.0))
        self.assertEqual(self.view.LineColor, (127.0 / 255.0,) * 3)
        self.assertEqual(self.view.IntersectionPointColor, (0.0, 170.0 / 255.0, 1.0))
        self.assertEqual(self.view.editor_modes, {"PointColor": 2, "PointSize": 2})

    def test_points_toggle_without_changing_shape_or_line_width(self):
        shape = self.obj.Shape = object()
        self.view.ShowIntersections = False
        self.proxy.onChanged(self.view, "ShowIntersections")
        self.assertEqual(self.proxy._points.children, [])
        self.assertIs(self.obj.Shape, shape)
        self.assertEqual(self.view.LineWidth, 1.0)
        self.view.ShowIntersections = True
        self.proxy.onChanged(self.view, "ShowIntersections")
        self.assertEqual(self.view.PointSize, 0.0)
        self.assertEqual(len(self.proxy._points.children), 4)

    def test_coin_points_are_exactly_x_major_intersections_not_line_endpoints(self):
        color, style, coordinates, point_set = self.proxy._points.children
        start, count, values = coordinates.point.value
        self.assertEqual((start, count, point_set.numPoints), (0, self.obj.IntersectionCount, 2))
        self.assertEqual(values, [(0.0, 0.0, 0.0), (6000.0, 5000.0, 0.0)])
        for extension_endpoint in ((0.0, -1000.0, 0.0), (0.0, 6000.0, 0.0),
                                   (-1000.0, 0.0, 0.0), (7000.0, 0.0, 0.0)):
            self.assertNotIn(extension_endpoint, values)
        self.assertEqual(style.pointSize, self.view.IntersectionPointSize)
        self.assertEqual(color.rgb.value, self.view.IntersectionPointColor)

    def test_native_point_properties_do_not_control_coin_intersections(self):
        self.view.PointColor = (1.0, 0.0, 0.0); self.view.PointSize = 99.0
        self.proxy.onChanged(self.view, "PointSize")
        color, style = self.proxy._points.children[:2]
        self.assertEqual(color.rgb.value, self.view.IntersectionPointColor)
        self.assertEqual(style.pointSize, self.view.IntersectionPointSize)

    def test_labels_update_for_spacings_custom_identification_and_placement(self):
        initial = self.proxy._label_specs()
        self.obj.XSpacings = [1000.0, 2000.0]
        self.obj.XAxisIdentification = "Custom"
        self.obj.XAxisLabels = ["E1", "E2", "E3"]
        self.proxy.updateData(self.obj, "XSpacings")
        self.assertNotEqual(self.proxy._label_specs(), initial)
        self.assertTrue(any(item.text == "E3" for item in self.proxy._label_specs()))
        before = len(self.proxy._labels.children)
        self.obj.Placement = object(); self.proxy.updateData(self.obj, "Placement")
        self.assertEqual(len(self.proxy._labels.children), before)

    def test_show_labels_and_position_update_scene_immediately(self):
        self.view.ShowLabels = False; self.proxy.onChanged(self.view, "ShowLabels")
        self.assertEqual(self.proxy._labels.children, [])
        self.view.ShowLabels = True; self.view.LabelPosition = "Start"
        self.proxy.onChanged(self.view, "LabelPosition")
        self.assertEqual(len(self.proxy._label_specs()), 4)
        self.assertGreater(len(self.proxy._labels.children), 0)

    def test_global_visibility_switch_preserves_individual_flags(self):
        self.assertEqual(self.proxy._visibility.whichChild, self.module.coin.SO_SWITCH_ALL)
        original = (self.view.ShowLabels, self.view.ShowIntersections)
        for visible in (False, True, False, True):
            self.view.Visibility = visible
            self.proxy.onChanged(self.view, "Visibility")
            expected = (self.module.coin.SO_SWITCH_ALL if visible
                        else self.module.coin.SO_SWITCH_NONE)
            self.assertEqual(self.proxy._visibility.whichChild, expected)
            self.assertEqual(
                (self.view.ShowLabels, self.view.ShowIntersections), original
            )

    def test_each_label_branch_contains_its_text_node(self):
        expected = [spec.text for spec in self.proxy._label_specs()]
        actual = []
        for separator in self.proxy._labels.children[1:]:
            texts = [child.string for child in separator.children if isinstance(child, Text)]
            self.assertEqual(len(texts), 1)
            actual.extend(texts)
        self.assertEqual(actual, expected)

    def test_data_proxy_keeps_view_provider_alive_and_icon_is_structural_grid(self):
        data_proxy = types.SimpleNamespace()
        obj = types.SimpleNamespace(**vars(self.obj))
        obj.Proxy = data_proxy
        view = View(obj)
        proxy = self.module.StructuralGridViewProvider(view)
        self.assertIs(data_proxy._view_provider, proxy)
        paths_name = self.module.__package__ + ".paths"
        paths = types.ModuleType(paths_name)
        paths.GRID_OBJECT_ICON = "Resources/Icons/StructuralGrid.svg"
        sys.modules[paths_name] = paths
        try:
            self.assertEqual(proxy.getIcon(), paths.GRID_OBJECT_ICON)
        finally:
            sys.modules.pop(paths_name, None)

    def test_restore_and_attach_reconstruct_coin_nodes(self):
        restored = self.module.StructuralGridViewProvider()
        restored.__setstate__(None)
        restored.attach(self.view)
        self.assertIsNotNone(restored._root)
        self.assertIsNotNone(restored._labels)
        self.assertIn(restored._root, self.view.RootNode.children)

    def test_rgb3_accepts_float_integer_rgba_qcolor_and_property_color(self):
        class QColor:
            def redF(self): return 0.1
            def greenF(self): return 0.2
            def blueF(self): return 0.3
        class PropertyColor:
            Value = (0.4, 0.5, 0.6, 0.7)
        self.assertEqual(self.module._rgb3((0.1, 0.2, 0.3)), (0.1, 0.2, 0.3))
        self.assertEqual(self.module._rgb3([255, 128, 0]), (1.0, 128 / 255.0, 0.0))
        self.assertEqual(self.module._rgb3((0.1, 0.2, 0.3, 0.4)), (0.1, 0.2, 0.3))
        self.assertEqual(self.module._rgb3(QColor()), (0.1, 0.2, 0.3))
        self.assertEqual(self.module._rgb3(PropertyColor()), (0.4, 0.5, 0.6))

    def test_invalid_color_uses_one_safe_rgb_for_many_labels(self):
        warnings = []
        original = self.module._view_warning
        self.module._view_warning = warnings.append
        try:
            self.view.TextColor = (float("nan"), 0.0, 0.0, 1.0)
            self.proxy.onChanged(self.view, "TextColor")
        finally:
            self.module._view_warning = original
        self.assertEqual(len(warnings), 1)
        color = self.proxy._labels.children[0]
        self.assertEqual(color.rgb.value, (0.95, 0.95, 0.95))
        self.assertGreater(len(self.proxy._labels.children), 2)

    def test_rgb3_rejects_invalid_colors(self):
        for value in ((1, 2), (1, 2, 3, 4, 5), (-1, 0, 0), (256, 0, 0), (1.2, 0.0, 0.0), object()):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.module._rgb3(value)

    def test_attach_failure_removes_partial_coin_subgraph(self):
        view = View(self.obj)
        original = self.module.StructuralGridViewProvider._update_scene
        self.module.StructuralGridViewProvider._update_scene = lambda _self: (_ for _ in ()).throw(RuntimeError("Coin failed"))
        try:
            with self.assertRaisesRegex(RuntimeError, "Coin failed"):
                self.module.StructuralGridViewProvider(view)
        finally:
            self.module.StructuralGridViewProvider._update_scene = original
        self.assertEqual(view.RootNode.children, [])
        self.assertIsNone(view.Proxy)

    def test_four_sides_have_explicit_symmetric_alignment(self):
        specs = self.proxy._label_specs()
        by_side = {spec.side: spec for spec in specs}
        self.assertEqual(by_side["left"].anchor_point_local[0], -1250.0)
        self.assertEqual(by_side["right"].anchor_point_local[0], 7250.0)
        self.assertEqual(by_side["bottom"].anchor_point_local[1], -1250.0)
        self.assertEqual(by_side["top"].anchor_point_local[1], 6250.0)

    def test_alignment_is_independent_of_identifier_length_and_placement(self):
        self.obj.XAxisLabels = ["10", "EIXO-1"]
        self.obj.YAxisLabels = ["AA", "AB"]
        before = self.proxy._label_specs()
        self.obj.Placement = types.SimpleNamespace(Angle=1.2, Base=Vector(10, 20, 30))
        self.proxy.updateData(self.obj, "Placement")
        self.assertEqual(self.proxy._label_specs(), before)
        self.assertEqual({item.side for item in before}, {"top", "bottom", "left", "right"})

    def test_font_catalog_is_sorted_unique_and_uses_application_default(self):
        database = type("Database", (), {"families": staticmethod(lambda: ["Zulu", "Arial", "Zulu"])})
        font = type("Font", (), {"family": lambda self: "FreeCAD Sans"})()
        application = type("Application", (), {"font": staticmethod(lambda: font)})
        self.assertEqual(self.module._font_catalog(database, application),
                         (["Arial", "FreeCAD Sans", "Zulu"], "FreeCAD Sans"))
        empty_database = type("EmptyDatabase", (), {"families": staticmethod(lambda: [])})
        no_font = type("NoApplication", (), {"font": staticmethod(lambda: (_ for _ in ()).throw(RuntimeError()))})
        self.assertEqual(self.module._font_catalog(empty_database, no_font), (["Sans"], "Sans"))

    def test_font_string_migration_selection_unavailable_restore_and_empty_list(self):
        view = View(self.obj)
        view.addProperty("App::PropertyString", "FontName", "Grid Appearance", "old")
        view.FontName = "Zulu"
        original = self.module._font_catalog
        self.module._font_catalog = lambda: (["Arial", "Zulu"], "Arial")
        try:
            proxy = self.module.StructuralGridViewProvider(view)
            self.assertEqual((view.records["FontName"][0], view.FontName), ("App::PropertyEnumeration", "Zulu"))
            view.FontName = "Missing"
            proxy.onDocumentRestored(view)
            self.assertEqual(view.FontName, "Arial")
            self.module._font_catalog = lambda: (["Sans"], "Sans")
            proxy.onDocumentRestored(view)
            self.assertEqual(view.FontName, "Sans")
        finally:
            self.module._font_catalog = original

    def test_point_visibility_preserves_size_color_and_standard_lines_on_restore(self):
        self.view.IntersectionPointSize = 9.0; self.view.IntersectionPointColor = (0.1, 0.2, 0.3)
        self.view.ShowIntersections = False
        self.proxy.onChanged(self.view, "ShowIntersections")
        self.assertEqual((self.view.IntersectionPointSize, self.view.IntersectionPointColor, self.view.LineWidth),
                         (9.0, (0.1, 0.2, 0.3), 1.0))
        self.proxy.detach(self.view)
        restored = self.module.StructuralGridViewProvider(self.view)
        self.assertFalse(self.view.ShowIntersections)
        self.assertEqual((self.view.IntersectionPointSize, self.view.IntersectionPointColor), (9.0, (0.1, 0.2, 0.3)))
        self.assertEqual(restored._points.children, [])

    def test_migrates_native_point_values_once(self):
        view = View(self.obj)
        view.addProperty("App::PropertyBool", "ShowIntersections", "Grid Appearance", "existing")
        view.ShowIntersections = True
        view.PointColor = (0.4, 0.5, 0.6); view.PointSize = 8.0
        self.module.StructuralGridViewProvider(view)
        self.assertEqual(view.IntersectionPointColor, (0.4, 0.5, 0.6))
        self.assertEqual(view.IntersectionPointSize, 8.0)
        self.assertEqual(view.PointSize, 0.0)

    def test_view_provider_waits_for_partial_data_schema_then_rebuilds(self):
        self.obj.PropertiesList.remove("YSpacings")
        view = View(self.obj); proxy = self.module.StructuralGridViewProvider(view)
        self.assertEqual(proxy._points.children, [])
        self.assertEqual(proxy._labels.children, [])
        self.obj.PropertiesList.append("YSpacings")
        proxy.updateData(self.obj, "YSpacings")
        self.assertEqual(len(proxy._points.children), 4)
        self.assertGreater(len(proxy._labels.children), 0)


if __name__ == "__main__":
    unittest.main()
