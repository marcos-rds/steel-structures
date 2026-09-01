"""Persistent creation settings through FreeCAD's real ParamGet abstraction."""

from __future__ import annotations

import ast
import importlib.util
import math
import sys
import types
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PREFERENCES = ROOT / "freecad/SteelStructures/preferences.py"
MEMBER_TOOL = ROOT / "freecad/SteelStructures/interactive/draft_member_tool.py"
COLUMN_TOOL = ROOT / "freecad/SteelStructures/interactive/draft_column_tool.py"
MEMBER = ROOT / "freecad/SteelStructures/member.py"

PROFILES = {
    "W 150 x 13,0": types.SimpleNamespace(
        category="Aço laminado", series="Perfis W", designation="W 150 x 13,0"
    ),
    "W 310 x 32,7": types.SimpleNamespace(
        category="Aço laminado", series="Perfis W", designation="W 310 x 32,7"
    ),
    "L 50 x 5": types.SimpleNamespace(
        category="Aço laminado", series="Cantoneiras - Métricas", designation="L 50 x 5"
    ),
    'U 6" x 12,20': types.SimpleNamespace(
        category="Aço laminado", series="Perfis U", designation='U 6" x 12,20'
    ),
    "Ue 150 × 60 × 20 × 3,00": types.SimpleNamespace(
        category="Aço Dobrado", series="U Enrijecido (Ue) — NBR 6355",
        designation="Ue 150 × 60 × 20 × 3,00",
    ),
}


class ParamGroup:
    def __init__(self, values): self.values = values
    def GetString(self, key, default=""): return self.values.get(key, default)
    def SetString(self, key, value): self.values[key] = str(value)
    def GetFloat(self, key, default=0.0): return self.values.get(key, default)
    def SetFloat(self, key, value): self.values[key] = float(value)
    def GetBool(self, key, default=False): return self.values.get(key, default)
    def SetBool(self, key, value): self.values[key] = bool(value)


class ParamDatabase:
    def __init__(self): self.groups = {}; self.paths = []
    def ParamGet(self, path):
        self.paths.append(path)
        return ParamGroup(self.groups.setdefault(path, {}))


def load_preferences(database):
    package_name = "_creation_preferences_package"
    package = types.ModuleType(package_name); package.__path__ = [str(PREFERENCES.parent)]
    app = types.ModuleType("FreeCAD"); app.ParamGet = database.ParamGet
    catalog = types.ModuleType(f"{package_name}.profile_catalog")
    catalog.categories = lambda: ["Aço laminado", "Aço Dobrado"]
    catalog.series_for_category = lambda category: (
        ["Perfis W", "Perfis U", "Cantoneiras - Métricas"]
        if category == "Aço laminado" else ["U Enrijecido (Ue) — NBR 6355"]
    )
    catalog.designations = lambda category=None, series=None: [
        key for key, profile in PROFILES.items()
        if (category is None or profile.category == category)
        and (series is None or profile.series == series)
    ]
    catalog.get = lambda designation: PROFILES[designation]
    catalog.insertion_options = lambda profile: (
        ("Centroide", "Quina externa", "Ponta superior", "Ponta direita", "Quina interna")
        if profile.series == "Cantoneiras - Métricas" else (
            "Centroide", "Centro da alma", "Face externa da alma",
            "Canto superior traseiro", "Canto inferior traseiro",
            "Ponta superior da mesa", "Ponta inferior da mesa",
        ) if profile.series == "Perfis U" else (
            "Centroide", "Centro da alma", "Face externa da alma",
            "Canto externo superior", "Canto externo inferior",
            "Ponta do enrijecedor superior", "Ponta do enrijecedor inferior",
            "Centro externo superior", "Centro externo inferior",
            "Canto externo do enrijecedor superior",
            "Canto externo do enrijecedor inferior",
        ) if profile.series == "U Enrijecido (Ue) — NBR 6355" else tuple(
            member.INSERTION_OPTIONS
        )
    )
    member = types.ModuleType(f"{package_name}.member")
    member.INSERTION_OPTIONS = [
        "Centroide", "Face esquerda", "Face direita", "Face superior", "Face inferior",
        "Canto superior esquerdo", "Canto superior direito",
        "Canto inferior esquerdo", "Canto inferior direito",
    ]
    injected = {package_name: package, "FreeCAD": app,
                f"{package_name}.profile_catalog": catalog,
                f"{package_name}.member": member}
    old = {name: sys.modules.get(name) for name in injected}; sys.modules.update(injected)
    spec = importlib.util.spec_from_file_location(f"{package_name}.preferences", PREFERENCES)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try: spec.loader.exec_module(module)
    finally:
        sys.modules.pop(spec.name, None)
        for name, previous in old.items():
            if previous is None: sys.modules.pop(name, None)
            else: sys.modules[name] = previous
    return module


class CreationPreferencesTests(unittest.TestCase):
    def setUp(self):
        self.database = ParamDatabase()
        self.preferences = load_preferences(self.database)

    def member(self, **changes):
        values = dict(category="Aço laminado", series="Perfis W",
                      designation="W 310 x 32,7", insertion="Face superior",
                      rotation=20.0, color=(1.0, 0.0, 0.0), element_type="Viga")
        values.update(changes)
        return self.preferences.MemberCreationSettings(**values)

    def column(self, **changes):
        values = dict(category="Aço laminado", series="Perfis W",
                      designation="W 150 x 13,0", insertion="Face inferior",
                      rotation=90.0, color=(0.0, 0.0, 1.0), height=6000.0,
                      continue_creating=True)
        values.update(changes)
        return self.preferences.ColumnCreationSettings(**values)

    def grid(self, **changes):
        values = dict(
            line_color=(0.1, 0.2, 0.3), line_width=2.5,
            show_intersections=False, intersection_color=(0.2, 0.4, 0.6),
            intersection_size=8.0, show_labels=False, label_position="End",
            label_offset=375.0, font_name="Arial", font_size=18.0,
            text_color=(0.8, 0.7, 0.6),
        )
        values.update(changes)
        return self.preferences.GridAppearanceSettings(**values)

    def test_first_member_run_uses_exact_defaults(self):
        value = self.preferences.load_member_creation_settings()
        self.assertEqual((value.designation, value.insertion, value.rotation,
                          value.element_type),
                         ("W 150 x 13,0", "Centroide", 0.0, "Membro"))
        self.assertEqual(value.color, self.preferences.DEFAULT_COLOR)

    def test_first_column_run_uses_exact_defaults(self):
        value = self.preferences.load_column_creation_settings()
        self.assertEqual((value.designation, value.height, value.rotation,
                          value.continue_creating),
                         ("W 150 x 13,0", 3000.0, 0.0, True))

    def test_first_grid_run_uses_new_factory_colors(self):
        value = self.preferences.load_grid_appearance_settings()
        self.assertEqual(value.line_color, (127.0 / 255.0,) * 3)
        self.assertEqual(value.intersection_color, (0.0, 170.0 / 255.0, 1.0))
        self.assertEqual((value.line_width, value.show_intersections,
                          value.show_labels, value.label_position, value.label_offset),
                         (1.0, True, True, "Both", 250.0))

    def test_member_round_trip_persists_profile_color_rotation_type_and_insertion(self):
        self.preferences.save_member_creation_settings(self.member())
        value = self.preferences.load_member_creation_settings()
        self.assertEqual(value, self.member())

    def test_column_round_trip_persists_profile_color_rotation_height_and_continue(self):
        self.preferences.save_column_creation_settings(self.column())
        value = self.preferences.load_column_creation_settings()
        self.assertEqual(value, self.column())

    def test_grid_appearance_round_trip_persists_only_cosmetic_values(self):
        self.assertTrue(self.preferences.save_grid_appearance_settings(self.grid()))
        self.assertEqual(self.preferences.load_grid_appearance_settings(), self.grid())
        keys = set(self.database.groups[self.preferences.GRID_PREFERENCES])
        for forbidden in ("XSpacings", "YSpacings", "XStartExtension",
                          "YStartExtension", "Placement", "XAxisIdentification"):
            self.assertNotIn(forbidden, keys)

    def test_invalid_grid_values_fall_back_to_factory_defaults(self):
        group = self.database.groups.setdefault(self.preferences.GRID_PREFERENCES, {})
        group.update(LineWidth=float("nan"), IntersectionPointSize=-1,
                     LabelPosition="Around", FontSize=0,
                     LineColorRed=2.0, LineColorGreen=0.0, LineColorBlue=0.0)
        value = self.preferences.load_grid_appearance_settings()
        self.assertEqual(value.line_width, 1.0)
        self.assertEqual(value.intersection_size, 5.0)
        self.assertEqual(value.label_position, "Both")
        self.assertEqual(value.font_size, 14.0)
        self.assertEqual(value.line_color, (127.0 / 255.0,) * 3)

    def test_tools_have_independent_parameter_groups(self):
        self.preferences.save_member_creation_settings(self.member())
        self.preferences.save_column_creation_settings(self.column())
        self.assertEqual(self.preferences.load_member_creation_settings(), self.member())
        self.assertEqual(self.preferences.load_column_creation_settings(), self.column())
        self.assertNotEqual(self.preferences.MEMBER_PREFERENCES,
                            self.preferences.COLUMN_PREFERENCES)
        self.assertNotIn(self.preferences.GRID_PREFERENCES,
                         (self.preferences.MEMBER_PREFERENCES,
                          self.preferences.COLUMN_PREFERENCES))

    def test_new_module_instance_simulating_restart_restores_values(self):
        self.preferences.save_column_creation_settings(self.column(height=5678, rotation=23))
        restarted = load_preferences(self.database)
        value = restarted.load_column_creation_settings()
        self.assertEqual((value.height, value.rotation), (5678, 23))

    def test_missing_profile_falls_back_to_valid_default(self):
        group = self.database.groups.setdefault(self.preferences.MEMBER_PREFERENCES, {})
        group.update(Category="Aço laminado", Series="Perfis W", Designation="removido")
        self.assertEqual(self.preferences.load_member_creation_settings().designation,
                         "W 150 x 13,0")

    def test_mismatched_category_or_series_falls_back(self):
        group = self.database.groups.setdefault(self.preferences.MEMBER_PREFERENCES, {})
        group.update(Category="Aço dobrado", Series="Outra", Designation="W 310 x 32,7")
        self.assertEqual(self.preferences.load_member_creation_settings().designation,
                         "W 150 x 13,0")

    def test_invalid_element_type_falls_back_to_member(self):
        self.preferences.save_member_creation_settings(self.member(element_type="Pilar"))
        self.assertEqual(self.preferences.load_member_creation_settings().element_type,
                         "Membro")

    def test_invalid_height_falls_back_to_3000(self):
        for invalid in (0, -1, float("nan"), float("inf"), 1000001):
            self.database.groups[self.preferences.COLUMN_PREFERENCES] = {"Height": invalid}
            with self.subTest(invalid=invalid):
                self.assertEqual(self.preferences.load_column_creation_settings().height, 3000)

    def test_invalid_rotation_falls_back_to_zero(self):
        for invalid in (float("nan"), float("inf"), -3601, 3601):
            self.database.groups[self.preferences.MEMBER_PREFERENCES] = {"RotationAngle": invalid}
            with self.subTest(invalid=invalid):
                self.assertEqual(self.preferences.load_member_creation_settings().rotation, 0)

    def test_invalid_color_falls_back_without_traceback(self):
        group = self.database.groups.setdefault(self.preferences.MEMBER_PREFERENCES, {})
        group.update(ColorRed=2.0, ColorGreen=float("nan"), ColorBlue=-1.0)
        self.assertEqual(self.preferences.load_member_creation_settings().color,
                         self.preferences.DEFAULT_COLOR)

    def test_invalid_insertion_falls_back_and_storage_uses_stable_key(self):
        self.preferences.save_member_creation_settings(self.member(insertion="Face superior"))
        group = self.database.groups[self.preferences.MEMBER_PREFERENCES]
        self.assertEqual(group["Insertion"], "top")
        group["Insertion"] = "obsolete"
        self.assertEqual(self.preferences.load_member_creation_settings().insertion,
                         "Centroide")

    def test_equal_angle_insertion_round_trip_uses_stable_family_id(self):
        settings = self.member(
            series="Cantoneiras - Métricas", designation="L 50 x 5",
            insertion="Quina externa",
        )
        self.preferences.save_member_creation_settings(settings)
        group = self.database.groups[self.preferences.MEMBER_PREFERENCES]
        self.assertEqual(group["Insertion"], "outer_corner")
        self.assertEqual(self.preferences.load_member_creation_settings(), settings)

    def test_u_insertion_round_trip_uses_stable_family_ids(self):
        expected = {
            "Centro da alma": "web_center",
            "Face externa da alma": "web_back",
            "Canto superior traseiro": "rear_top",
            "Canto inferior traseiro": "rear_bottom",
            "Ponta superior da mesa": "flange_top_tip",
            "Ponta inferior da mesa": "flange_bottom_tip",
        }
        for label, identifier in expected.items():
            settings = self.member(
                series="Perfis U", designation='U 6" x 12,20', insertion=label
            )
            with self.subTest(label=label):
                self.preferences.save_member_creation_settings(settings)
                group = self.database.groups[self.preferences.MEMBER_PREFERENCES]
                self.assertEqual(group["Insertion"], identifier)
                self.assertEqual(
                    self.preferences.load_member_creation_settings().insertion, label
                )

    def test_ue_member_insertion_round_trip_uses_stable_family_ids(self):
        expected = {
            "Canto externo superior": "outer_top_corner",
            "Canto externo inferior": "outer_bottom_corner",
            "Ponta do enrijecedor superior": "lip_top_tip",
            "Ponta do enrijecedor inferior": "lip_bottom_tip",
        }
        for label, identifier in expected.items():
            settings = self.member(
                category="Aço Dobrado",
                series="U Enrijecido (Ue) — NBR 6355",
                designation="Ue 150 × 60 × 20 × 3,00",
                insertion=label,
            )
            with self.subTest(label=label):
                self.assertTrue(
                    self.preferences.save_member_creation_settings(settings)
                )
                stored = self.database.groups[self.preferences.MEMBER_PREFERENCES]
                self.assertEqual(stored["Insertion"], identifier)
                self.assertEqual(
                    self.preferences.load_member_creation_settings().insertion,
                    label,
                )

    def test_ue_column_insertion_round_trip_uses_stable_family_ids(self):
        expected = {
            "Canto externo superior": "outer_top_corner",
            "Canto externo inferior": "outer_bottom_corner",
            "Ponta do enrijecedor superior": "lip_top_tip",
            "Ponta do enrijecedor inferior": "lip_bottom_tip",
        }
        for label, identifier in expected.items():
            settings = self.column(
                category="Aço Dobrado",
                series="U Enrijecido (Ue) — NBR 6355",
                designation="Ue 150 × 60 × 20 × 3,00",
                insertion=label,
            )
            with self.subTest(label=label):
                self.assertTrue(
                    self.preferences.save_column_creation_settings(settings)
                )
                stored = self.database.groups[self.preferences.COLUMN_PREFERENCES]
                self.assertEqual(stored["Insertion"], identifier)
                self.assertEqual(
                    self.preferences.load_column_creation_settings().insertion,
                    label,
                )

    def test_new_ue_member_insertion_round_trip_uses_approved_ids(self):
        expected = {
            "Centro externo superior": "outer_top_mid",
            "Centro externo inferior": "outer_bottom_mid",
            "Canto externo do enrijecedor superior": "outer_lip_top_corner",
            "Canto externo do enrijecedor inferior": "outer_lip_bottom_corner",
        }
        for label, identifier in expected.items():
            settings = self.member(
                category="Aço Dobrado",
                series="U Enrijecido (Ue) — NBR 6355",
                designation="Ue 150 × 60 × 20 × 3,00",
                insertion=label,
            )
            with self.subTest(label=label):
                self.assertTrue(self.preferences.save_member_creation_settings(settings))
                stored = self.database.groups[self.preferences.MEMBER_PREFERENCES]
                self.assertEqual(stored["Insertion"], identifier)
                self.assertEqual(
                    self.preferences.load_member_creation_settings().insertion, label
                )

    def test_new_ue_column_insertion_round_trip_uses_approved_ids(self):
        expected = {
            "Centro externo superior": "outer_top_mid",
            "Centro externo inferior": "outer_bottom_mid",
            "Canto externo do enrijecedor superior": "outer_lip_top_corner",
            "Canto externo do enrijecedor inferior": "outer_lip_bottom_corner",
        }
        for label, identifier in expected.items():
            settings = self.column(
                category="Aço Dobrado",
                series="U Enrijecido (Ue) — NBR 6355",
                designation="Ue 150 × 60 × 20 × 3,00",
                insertion=label,
            )
            with self.subTest(label=label):
                self.assertTrue(self.preferences.save_column_creation_settings(settings))
                stored = self.database.groups[self.preferences.COLUMN_PREFERENCES]
                self.assertEqual(stored["Insertion"], identifier)
                self.assertEqual(
                    self.preferences.load_column_creation_settings().insertion, label
                )

    def test_unknown_column_insertion_key_falls_back_without_exception(self):
        settings = self.column(
            category="Aço Dobrado",
            series="U Enrijecido (Ue) — NBR 6355",
            designation="Ue 150 × 60 × 20 × 3,00",
            insertion="Canto externo inferior",
        )
        self.assertTrue(self.preferences.save_column_creation_settings(settings))
        group = self.database.groups[self.preferences.COLUMN_PREFERENCES]
        group["Insertion"] = "unknown_ue_reference"
        self.assertEqual(
            self.preferences.load_column_creation_settings().insertion,
            "Centroide",
        )

    def test_namespace_is_exclusively_steel_structures(self):
        self.preferences.save_member_creation_settings(self.member())
        self.preferences.save_column_creation_settings(self.column())
        self.assertTrue(all("/Mod/SteelStructures/" in path for path in self.database.paths))
        self.assertFalse(any("/Draft" in path or "/BIM" in path for path in self.database.paths))

    def test_transient_points_hover_names_and_offsets_are_not_stored(self):
        self.preferences.save_member_creation_settings(self.member())
        keys = set(self.database.groups[self.preferences.MEMBER_PREFERENCES])
        for forbidden in ("StartPoint", "EndPoint", "Hover", "Name", "DisplayName",
                          "OffsetX", "OffsetY"):
            self.assertNotIn(forbidden, keys)

    def test_member_geometry_has_no_preferences_dependency(self):
        self.assertNotIn("preferences", MEMBER.read_text(encoding="utf-8"))


def extracted_method(path, class_name, method_name, globals_):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    original = next(node for node in tree.body
                    if isinstance(node, ast.ClassDef) and node.name == class_name)
    method = next(node for node in original.body
                  if isinstance(node, ast.FunctionDef) and node.name == method_name)
    cls = ast.ClassDef(name="Tool", bases=[], keywords=[], body=[method], decorator_list=[])
    namespace = dict(globals_)
    exec(compile(ast.fix_missing_locations(ast.Module(body=[cls], type_ignores=[])),
                 str(path), "exec"), namespace)
    return namespace["Tool"]


class SaveLifecycleTests(unittest.TestCase):
    def member_tool(self, create):
        self.saved = []
        Tool = extracted_method(MEMBER_TOOL, "StructuralMemberDraftTool", "finish", {
            "TOOL_ACTIVE": "ACTIVE", "TOOL_FINISHING": "FINISHING",
            "TOOL_FINISHED": "FINISHED",
            "App": types.SimpleNamespace(Console=types.SimpleNamespace(PrintError=lambda *_: None)),
            "save_member_creation_settings": self.saved.append,
        })
        tool = Tool(); tool._lifecycle_state = "ACTIVE"; tool.node = [1, 2]
        settings = object()
        tool.profile_options = types.SimpleNamespace(
            creation_options=lambda *_: object(), creation_settings=lambda: settings,
            creation_succeeded=lambda _name: None,
        )
        tool.controller = types.SimpleNamespace(create=create)
        tool.ui = types.SimpleNamespace(continueMode=False)
        tool._reset_segment_for_continue = lambda: None
        tool._terminate_native_session = lambda: None
        return tool, settings

    def test_member_success_saves_once(self):
        tool, settings = self.member_tool(
            lambda _options: types.SimpleNamespace(next_default_name="Membro 002")
        )
        tool.finish()
        self.assertEqual(self.saved, [settings])

    def test_member_cancel_or_escape_without_object_does_not_save(self):
        tool, _ = self.member_tool(lambda _options: None)
        tool.node = []
        tool.finish()
        self.assertEqual(self.saved, [])

    def test_member_failed_creation_does_not_save(self):
        def fail(_options): raise ValueError("invalid")
        tool, _ = self.member_tool(fail)
        app = types.SimpleNamespace(Console=types.SimpleNamespace(PrintError=lambda *_: None))
        tool.finish.__func__.__globals__["App"] = app
        tool.finish()
        self.assertEqual(self.saved, [])

    def column_tool(self):
        self.saved = []
        app = types.SimpleNamespace(Console=types.SimpleNamespace(PrintError=lambda *_: None))
        Tool = extracted_method(COLUMN_TOOL, "StructuralColumnDraftTool", "_confirm_base", {
            "App": app, "save_column_creation_settings": self.saved.append,
        })
        Creation = extracted_method(
            COLUMN_TOOL, "StructuralColumnDraftTool", "_create_from_options", {
                "App": app, "save_column_creation_settings": self.saved.append,
            }
        )
        tool = Tool(); tool.node = [1]
        tool._create_from_options = types.MethodType(
            Creation._create_from_options, tool
        )
        tool.ui = types.SimpleNamespace(continueMode=True)
        settings = object()
        tool.column_panel = types.SimpleNamespace(
            creation_options=lambda _base: object(),
            creation_settings=lambda _continue: settings,
            creation_succeeded=lambda _name: None,
        )
        tool._reset_for_continue = lambda: None
        tool._terminate_native_session = lambda: None
        return tool, settings

    def test_column_each_success_in_continue_updates_saved_settings(self):
        tool, first = self.column_tool()
        tool.controller = types.SimpleNamespace(create=lambda _options:
            types.SimpleNamespace(next_default_name="Pilar 002"))
        tool._confirm_base(object())
        second = object()
        tool.column_panel.creation_settings = lambda _continue: second
        tool._confirm_base(object())
        self.assertEqual(self.saved, [first, second])

    def test_column_failed_or_cancelled_creation_does_not_save(self):
        tool, _ = self.column_tool()
        tool.controller = types.SimpleNamespace(create=lambda _options:
            (_ for _ in ()).throw(ValueError("invalid")))
        tool._confirm_base(object())
        self.assertEqual(self.saved, [])


if __name__ == "__main__":
    unittest.main()
