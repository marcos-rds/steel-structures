"""Static tests that do not require FreeCAD to be installed."""

from __future__ import annotations

import ast
import importlib.util
import json
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_XML = PROJECT_ROOT / "package.xml"
PACKAGE_INIT = PROJECT_ROOT / "freecad" / "SteelStructures" / "__init__.py"
CATALOG = (
    PROJECT_ROOT
    / "freecad"
    / "SteelStructures"
    / "catalogs"
    / "gerdau_construcao_metalica_2023_01.json"
)

REQUIRED_PROFILE_FIELDS = {
    "id",
    "series_id",
    "designation",
    "equivalent_designation",
    "aliases",
    "catalog_markers",
    "availability_status",
    "geometry_type",
    "geometry",
    "physical_properties",
    "section_properties",
}
ESSENTIAL_FILES = (
    "package.xml",
    "README.md",
    "LICENSE",
    "freecad/SteelStructures/__init__.py",
    "freecad/SteelStructures/init_gui.py",
    "freecad/SteelStructures/commands.py",
    "freecad/SteelStructures/interactive/__init__.py",
    "freecad/SteelStructures/interactive/member_controller.py",
    "freecad/SteelStructures/interactive/draft_member_tool.py",
    "freecad/SteelStructures/interactive/draft_column_tool.py",
    "freecad/SteelStructures/interactive/column_task_panel.py",
    "freecad/SteelStructures/interactive/profile_options_widget.py",
    "freecad/SteelStructures/member.py",
    "freecad/SteelStructures/profile_catalog.py",
    "freecad/SteelStructures/paths.py",
    "freecad/SteelStructures/profiles/__init__.py",
    "freecad/SteelStructures/profiles/models.py",
    "freecad/SteelStructures/profiles/catalog.py",
    "freecad/SteelStructures/profiles/validation.py",
    "freecad/SteelStructures/catalogs/gerdau_construcao_metalica_2023_01.json",
    "Resources/Icons/SteelStructures.svg",
    "Resources/Icons/CreateMember.svg",
    "Resources/Icons/CreateColumn.svg",
    "Resources/Icons/StructuralMember.svg",
    "Resources/Icons/CreateGrid.svg",
    "Resources/Icons/StructuralGrid.svg",
    "freecad/SteelStructures/interactive/grid_task_panel.py",
)


def read_internal_version() -> str:
    tree = ast.parse(PACKAGE_INIT.read_text(encoding="utf-8"))
    for node in tree.body:
        if (
            isinstance(node, ast.Assign)
            and any(isinstance(target, ast.Name) and target.id == "__version__" for target in node.targets)
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str)
        ):
            return node.value.value
    raise AssertionError("__version__ não encontrada")


class PackageMetadataTests(unittest.TestCase):
    def test_package_xml_is_valid(self):
        root = ET.parse(PACKAGE_XML).getroot()
        self.assertEqual(root.tag.rsplit("}", 1)[-1], "package")

    def test_versions_are_synchronized(self):
        root = ET.parse(PACKAGE_XML).getroot()
        manifest_version = root.find("{*}version")
        self.assertIsNotNone(manifest_version)
        self.assertEqual(manifest_version.text.strip(), read_internal_version())


class IdentityMigrationTests(unittest.TestCase):
    def setUp(self):
        self.package = PROJECT_ROOT / "freecad" / "SteelStructures"
        self.gui_source = (self.package / "init_gui.py").read_text(encoding="utf-8")
        self.commands_source = (self.package / "commands.py").read_text(encoding="utf-8")
        self.manifest = ET.parse(PACKAGE_XML).getroot()

    def test_only_new_package_and_identity_icon_exist(self):
        legacy_package = "Bancada" + "FCSteel"
        legacy_icon = legacy_package + ".svg"
        self.assertTrue(self.package.is_dir())
        self.assertFalse((PROJECT_ROOT / "freecad" / legacy_package).exists())
        self.assertTrue((PROJECT_ROOT / "Resources/Icons/SteelStructures.svg").is_file())
        self.assertFalse((PROJECT_ROOT / "Resources/Icons" / legacy_icon).exists())

    def test_manifest_uses_the_new_identity(self):
        self.assertEqual(self.manifest.findtext("{*}name"), "Steel Structures")
        workbench = self.manifest.find("{*}content/{*}workbench")
        self.assertIsNotNone(workbench)
        self.assertEqual(workbench.findtext("{*}classname"), "SteelStructuresWorkbench")
        self.assertEqual(workbench.findtext("{*}subdirectory"), "freecad/SteelStructures")
        self.assertEqual(self.manifest.findtext("{*}icon"), "Resources/Icons/SteelStructures.svg")

    def test_only_new_workbench_class_is_declared_and_registered(self):
        tree = ast.parse(self.gui_source)
        classes = [node.name for node in tree.body if isinstance(node, ast.ClassDef)]
        self.assertEqual(classes, ["SteelStructuresWorkbench"])
        self.assertIn("Gui.addWorkbench(SteelStructuresWorkbench())", self.gui_source)
        self.assertIn('MenuText = "Steel Structures"', self.gui_source)
        self.assertNotIn("Metal" + "StructureWorkbench", self.gui_source)

    def test_only_new_command_ids_are_registered(self):
        tree = ast.parse(self.commands_source)
        registered = []
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "Gui"
                and node.func.attr == "addCommand"
                and node.args
                and isinstance(node.args[0], ast.Constant)
            ):
                registered.append(node.args[0].value)
        self.assertEqual(
            registered,
            [
                "SteelStructures_CreateMember",
                "SteelStructures_CreateColumn",
                "SteelStructures_CreateGrid",
                "SteelStructures_AdjustMember",
                "SteelStructures_ProfileBrowser",
                "SteelStructures_MoveCopy",
            ],
        )
        self.assertFalse(any(command.startswith("B" + "FC_") for command in registered))

    def test_runtime_python_has_no_legacy_identity(self):
        runtime = "\n".join(
            path.read_text(encoding="utf-8")
            for path in sorted(self.package.rglob("*.py"))
        )
        forbidden = (
            "Bancada" + "FCSteel",
            "B" + "FC_",
            "Metal" + "StructureWorkbench",
            "Metal" + " Structure",
        )
        for fragment in forbidden:
            with self.subTest(fragment=fragment):
                self.assertNotIn(fragment, runtime)

    def test_paths_resolve_resources_from_the_renamed_package(self):
        paths_file = self.package / "paths.py"
        spec = importlib.util.spec_from_file_location("_steel_structures_paths_test", paths_file)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.assertEqual(module.ADDON_ROOT, PROJECT_ROOT)
        self.assertEqual(Path(module.WORKBENCH_ICON), PROJECT_ROOT / "Resources/Icons/SteelStructures.svg")
        self.assertTrue(Path(module.MEMBER_ICON).is_file())
        self.assertTrue(Path(module.COLUMN_ICON).is_file())
        self.assertTrue(Path(module.GRID_COMMAND_ICON).is_file())


class CatalogIntegrityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.payload = json.loads(CATALOG.read_text(encoding="utf-8"))
        cls.profiles = cls.payload["profiles"]

    def test_catalog_is_valid_json_with_profiles(self):
        self.assertIsInstance(self.payload, dict)
        self.assertEqual(self.payload["schema_version"], 2)
        self.assertIsInstance(self.profiles, list)

    def test_catalog_contains_exactly_218_profiles(self):
        self.assertEqual(len(self.profiles), 218)
        expected = {"w": 100, "hp": 8, "i": 8, "u": 12, "t": 10,
                    "equal-angle-inch": 50, "equal-angle-metric": 30}
        self.assertEqual(
            {series: sum(p["series_id"] == series for p in self.profiles) for series in expected},
            expected,
        )

    def test_designations_are_unique(self):
        designations = [profile["designation"] for profile in self.profiles]
        self.assertEqual(len(designations), len(set(designations)))

    def test_profiles_have_all_required_fields(self):
        for profile in self.profiles:
            with self.subTest(profile=profile.get("designation")):
                self.assertFalse(REQUIRED_PROFILE_FIELDS.difference(profile))

    def test_profile_numeric_values_are_positive(self):
        for profile in self.profiles:
            values = {
                **profile["geometry"],
                **profile["physical_properties"],
                **profile["section_properties"],
                **profile.get("centroid", {}),
            }
            for field, value in values.items():
                with self.subTest(profile=profile.get("designation"), field=field):
                    self.assertIsInstance(value, (int, float))
                    self.assertNotIsInstance(value, bool)
                    self.assertGreater(value, 0)


class ProjectLayoutTests(unittest.TestCase):
    def test_essential_files_exist(self):
        for relative in ESSENTIAL_FILES:
            with self.subTest(path=relative):
                self.assertTrue((PROJECT_ROOT / relative).is_file(), relative)

    def test_legacy_interactive_modules_are_absent(self):
        for name in (
            "member_task_panel.py",
            "point_capture.py",
            "preview_tracker.py",
            "snap_adapter.py",
        ):
            with self.subTest(name=name):
                self.assertFalse(
                    (PROJECT_ROOT / "freecad/SteelStructures/interactive" / name).exists()
                )


if __name__ == "__main__":
    unittest.main()
