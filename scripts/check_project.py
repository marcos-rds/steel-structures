"""Static integrity checks for the Steel Structures workbench."""

from __future__ import annotations

import ast
import hashlib
import json
import sys
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
TUPER_HOLLOW_CATALOG = (
    PROJECT_ROOT / "freecad" / "SteelStructures" / "catalogs"
    / "tuper_hollow_2024.json"
)
TUPER_HOLLOW_SNAPSHOT = (
    PROJECT_ROOT / "freecad" / "SteelStructures" / "catalog_sources"
    / "tuper_hollow_2024_extracted.json"
)

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
    "freecad/SteelStructures/interactive/profile_options_widget.py",
    "freecad/SteelStructures/member.py",
    "freecad/SteelStructures/profile_catalog.py",
    "freecad/SteelStructures/paths.py",
    "freecad/SteelStructures/profiles/__init__.py",
    "freecad/SteelStructures/profiles/models.py",
    "freecad/SteelStructures/profiles/catalog.py",
    "freecad/SteelStructures/profiles/validation.py",
    "freecad/SteelStructures/catalogs/gerdau_construcao_metalica_2023_01.json",
    "freecad/SteelStructures/catalogs/tuper_hollow_2024.json",
    "freecad/SteelStructures/catalog_sources/tuper_hollow_2024_extracted.json",
    "scripts/generate_tuper_hollow_catalog.py",
    "Resources/Icons/SteelStructures.svg",
    "Resources/Icons/CreateMember.svg",
    "Resources/Icons/StructuralMember.svg",
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


def package_version() -> str:
    root = ET.parse(PACKAGE_XML).getroot()
    version = root.find("{*}version")
    if version is None or not version.text or not version.text.strip():
        raise ValueError("package.xml não contém uma versão válida")
    return version.text.strip()


def python_package_version() -> str:
    tree = ast.parse(PACKAGE_INIT.read_text(encoding="utf-8"), filename=str(PACKAGE_INIT))
    for node in tree.body:
        if (
            isinstance(node, ast.Assign)
            and any(isinstance(target, ast.Name) and target.id == "__version__" for target in node.targets)
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str)
        ):
            return node.value.value
    raise ValueError("__version__ não foi encontrada em __init__.py")


def catalog_payload() -> dict:
    payload = json.loads(CATALOG.read_text(encoding="utf-8"))
    if payload.get("schema_version") != 2:
        raise ValueError("o catálogo não usa schema_version 2")
    return payload


def catalog_profiles() -> list[dict]:
    payload = catalog_payload()
    profiles = payload.get("profiles")
    if not isinstance(profiles, list):
        raise ValueError("o catálogo não contém uma lista 'profiles'")
    return profiles


def run_checks() -> list[str]:
    errors: list[str] = []

    missing = [relative for relative in ESSENTIAL_FILES if not (PROJECT_ROOT / relative).is_file()]
    if missing:
        errors.append("arquivos essenciais ausentes: " + ", ".join(missing))

    try:
        manifest_version = package_version()
    except (ET.ParseError, OSError, ValueError) as exc:
        errors.append(f"package.xml inválido: {exc}")
        manifest_version = None

    try:
        internal_version = python_package_version()
    except (OSError, SyntaxError, ValueError) as exc:
        errors.append(f"versão Python inválida: {exc}")
        internal_version = None

    if manifest_version and internal_version and manifest_version != internal_version:
        errors.append(
            f"versões divergentes: package.xml={manifest_version}, __version__={internal_version}"
        )

    payload = {}
    try:
        payload = catalog_payload()
        profiles = payload.get("profiles")
        if not isinstance(profiles, list):
            raise ValueError("o catálogo não contém uma lista 'profiles'")
    except (json.JSONDecodeError, OSError, ValueError) as exc:
        errors.append(f"catálogo JSON inválido: {exc}")
        profiles = []

    if len(profiles) != 218:
        errors.append(f"quantidade de perfis incorreta: esperado 218, encontrado {len(profiles)}")
    expected_counts = {"w": 100, "hp": 8, "i": 8, "u": 12, "t": 10,
                       "equal-angle-inch": 50, "equal-angle-metric": 30}
    counts = {series: sum(profile.get("series_id") == series for profile in profiles) for series in expected_counts}
    if counts != expected_counts:
        errors.append(f"quantidade por série incorreta: {counts!r}")
    if len(payload.get("series", [])) != 7:
        errors.append(f"quantidade de séries incorreta: esperado 7, encontrado {len(payload.get('series', []))}")

    designations: list[str] = []
    for index, profile in enumerate(profiles, start=1):
        if not isinstance(profile, dict):
            errors.append(f"perfil {index} não é um objeto JSON")
            continue
        missing_fields = sorted(REQUIRED_PROFILE_FIELDS.difference(profile))
        if missing_fields:
            errors.append(f"perfil {index} sem campos obrigatórios: {', '.join(missing_fields)}")
        designation = profile.get("designation")
        if isinstance(designation, str):
            designations.append(designation)
        numeric_values = {}
        for group in ("geometry", "physical_properties", "section_properties", "centroid"):
            values = profile.get(group, {})
            if isinstance(values, dict):
                numeric_values.update(values)
        for field, value in numeric_values.items():
            if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
                errors.append(
                    f"perfil {index} possui valor não positivo ou não numérico em {field}: {value!r}"
                )

    duplicates = sorted(
        designation for designation in set(designations) if designations.count(designation) > 1
    )
    if duplicates:
        errors.append("designações duplicadas: " + ", ".join(duplicates))

    try:
        tuper_payload = json.loads(TUPER_HOLLOW_CATALOG.read_text(encoding="utf-8"))
        tuper_profiles = tuper_payload.get("profiles")
        if not isinstance(tuper_profiles, list):
            raise ValueError("profiles deve ser uma lista")
        expected_tuper_counts = {"shs": 678, "rhs": 1190, "chs": 1131}
        tuper_counts = {
            series: sum(item.get("series_id") == series for item in tuper_profiles)
            for series in expected_tuper_counts
        }
        if len(tuper_profiles) != 2999 or tuper_counts != expected_tuper_counts:
            errors.append(
                f"catálogo Tuper: contagens incorretas: total={len(tuper_profiles)}, "
                f"séries={tuper_counts!r}"
            )
        ids = [item.get("id") for item in tuper_profiles]
        designations = [item.get("designation") for item in tuper_profiles]
        if len(ids) != len(set(ids)) or len(designations) != len(set(designations)):
            errors.append("catálogo Tuper: IDs ou designações duplicados")
        geometry_keys = [
            (item.get("series_id"), tuple(sorted(item.get("geometry", {}).items())))
            for item in tuper_profiles
        ]
        if len(geometry_keys) != len(set(geometry_keys)):
            errors.append("catálogo Tuper: geometrias comerciais duplicadas")
        base_dimensions = {
            (item["series_id"], tuple(sorted(
                (key, value) for key, value in item["geometry"].items() if key != "t"
            ))) for item in tuper_profiles
        }
        if len(base_dimensions) != 217:
            errors.append(f"catálogo Tuper: dimensões-base={len(base_dimensions)}, esperado=217")
        availability = {
            family: {
                status: sum(item["series_id"] == family and
                            item.get("availability_status") == status
                            for item in tuper_profiles)
                for status in ("standard", "consultation")
            } for family in expected_tuper_counts
        }
        expected_availability = {
            "chs": {"standard": 1097, "consultation": 34},
            "rhs": {"standard": 803, "consultation": 387},
            "shs": {"standard": 548, "consultation": 130},
        }
        if availability != expected_availability:
            errors.append(f"catálogo Tuper: availability incorreta: {availability!r}")
        by_id = {item["id"]: item for item in tuper_profiles}
        critical = {
            "shs-75x75x2": 27.345,
            "shs-76-2x76-2x2": 27.797,
            "chs-21-3x0-75": 2.281,
            "chs-26x0-75": 2.802,
        }
        for profile_id, expected_weight in critical.items():
            actual = by_id.get(profile_id, {}).get("source_metadata", {}).get(
                "source_weight_p_kg_per_6m"
            )
            if actual != expected_weight:
                errors.append(
                    f"catálogo Tuper: {profile_id} possui p={actual!r}, "
                    f"esperado={expected_weight}"
                )
        for index, item in enumerate(tuper_profiles, start=1):
            source = item.get("source_metadata", {})
            weight = source.get("source_weight_p_kg_per_6m")
            basis = source.get("source_weight_basis_mm")
            if isinstance(weight, bool) or not isinstance(weight, (int, float)) or weight <= 0:
                errors.append(f"catálogo Tuper: perfil {index} possui p inválido")
                break
            if basis != 6000.0:
                errors.append(f"catálogo Tuper: perfil {index} não usa base 6000 mm")
                break
            mass = item.get("physical_properties", {}).get("mass_per_length")
            if mass != weight / 6.0:
                errors.append(f"catálogo Tuper: perfil {index} não usa MassPerMeter=p/6")
                break
        snapshot = json.loads(TUPER_HOLLOW_SNAPSHOT.read_text(encoding="utf-8"))
        raw_digest = hashlib.sha256(json.dumps(
            snapshot.get("raw_records", []), ensure_ascii=False, separators=(",", ":"),
        ).encode("utf-8")).hexdigest()
        if snapshot.get("audit", {}).get("raw_records_sha256") != raw_digest:
            errors.append("catálogo Tuper: raw_records_sha256 divergente")
        expected_corrections = {
            "chs-printed-page-30-stale-weight-body": 108,
            "shs-printed-page-58-first-header-dimension": 10,
        }
        applied = {item["id"]: item["matched_records"]
                   for item in snapshot.get("source_corrections_applied", [])}
        if applied != expected_corrections or snapshot.get("duplicate_key_count") != 0:
            errors.append("catálogo Tuper: erratas ou conflitos não resolvidos")
    except (json.JSONDecodeError, OSError, ValueError) as exc:
        errors.append(f"catálogo Tuper inválido: {exc}")

    for path in sorted(PROJECT_ROOT.rglob("*.py")):
        try:
            source = path.read_text(encoding="utf-8")
            compile(source, str(path), "exec")
        except (OSError, SyntaxError, UnicodeError) as exc:
            errors.append(f"Python inválido em {path.relative_to(PROJECT_ROOT)}: {exc}")

    return errors


def main() -> int:
    errors = run_checks()
    if errors:
        print("FALHA: verificações do projeto encontraram problemas:")
        for error in errors:
            print(f"- {error}")
        return 1
    print("OK: package.xml é XML válido.")
    print("OK: package.xml e __version__ indicam a mesma versão.")
    print("OK: catálogo Gerdau 01/23 é JSON válido e contém 218 perfis em 7 séries.")
    print("OK: designações são únicas e todos os perfis possuem campos e valores válidos.")
    print("OK: catálogo Tuper 2024 contém 2.999 perfis tubulares rastreáveis em 3 séries.")
    print("OK: todos os arquivos Python compilam sintaticamente.")
    print("OK: todos os arquivos essenciais existem.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
