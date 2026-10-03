# SPDX-License-Identifier: LGPL-2.1-or-later
"""Generate the Brazilian normative solid-bar catalog from its audited snapshot.

No PDF library at runtime or during generation. Published masses and nominal
dimension columns are authoritative inputs; ideal geometry is used only for QA.
"""

from __future__ import annotations

import argparse
from collections import Counter
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from freecad.SteelStructures.profiles.effective_properties import solid_section_properties
from freecad.SteelStructures.profiles.validation import validate_catalog_payload

SNAPSHOT = ROOT / "freecad/SteelStructures/catalog_sources/abnt_nbr_16683_2018_solid_extracted.json"
OUTPUT = ROOT / "freecad/SteelStructures/catalogs/abnt_nbr_16683_2018_solid.json"
CATALOG_ID = "abnt-nbr-16683-2018-solid"
PDF_SHA256 = "dfda6bd8d496dfaf435503d0145fa0ac6d5bb47515c06975bba4bb54fbccddbd"
RECORDS_SHA256 = "0a6b9823c9983f844212a5b180a7e186a88dd74292eb462d84279765567d4b35"
EXPECTED_COUNTS = {"round-bar": 53, "square-bar": 19, "flat-bar": 92}
FAMILIES = {
    "round-bar": ("Barra Redonda", "ROUND_BAR", "circular", "A.2", ("d",)),
    "square-bar": ("Barra Quadrada", "SQUARE_BAR", "square", "A.3", ("b",)),
    "flat-bar": ("Barra Chata", "FLAT_BAR", "rectangular", "A.1", ("b", "t")),
}
PAGE_COUNTS = {6: 14, 7: 29, 8: 29, 9: 20, 10: 25, 11: 28, 12: 19}


def fingerprint(records):
    return hashlib.sha256(json.dumps(
        records, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")).hexdigest()


def number(value, places):
    if not isinstance(value, str) or not re.fullmatch(r"\d+,\d{" + str(places) + "}", value):
        raise ValueError(f"Célula decimal publicada inválida: {value!r}")
    result = Decimal(value.replace(",", "."))
    if result <= 0:
        raise ValueError("Dimensões e massas devem ser positivas")
    return result


def compact(value):
    return format(value, "f").rstrip("0").rstrip(".") if "." in format(value, "f") else str(value)


def geometry_key(record):
    family = record["family"]
    return family, tuple(number(record["dimensions"][key], 2) for key in FAMILIES[family][4])


def validate_snapshot(snapshot):
    source = snapshot["source"]
    if (snapshot.get("schema_version") != 1 or source.get("sha256") != PDF_SHA256
            or source.get("standard") != "ABNT NBR 16683:2018"
            or source.get("edition_date") != "2018-11-29"
            or source.get("corrected_date") != "2020-04-23"
            or source.get("density_kg_m3") != 7850
            or source.get("pdf_page_count") != 25):
        raise ValueError("Snapshot não corresponde à publicação integral auditada")
    records = snapshot["records"]
    digest = fingerprint(records)
    if digest != snapshot["audit"]["raw_records_sha256"] or digest != RECORDS_SHA256:
        raise ValueError("Registros divergem das células auditadas")
    if (snapshot["summary"] != EXPECTED_COUNTS
            or Counter(row["family"] for row in records) != EXPECTED_COUNTS
            or Counter(row["page"] for row in records) != PAGE_COUNTS):
        raise ValueError("Contagens normativas divergentes")
    if snapshot["audit"]["source_corrections_applied"]:
        raise ValueError("Nenhuma correção de células foi aprovada para esta fonte")
    keys, positions = set(), set()
    for row in records:
        family = row["family"]
        if (row["table"] != FAMILIES[family][3]
                or set(row["dimensions"]) != set(FAMILIES[family][4])
                or row["pdf_page"] != row["page"] + 6
                or not 1 <= row["row"] <= PAGE_COUNTS[row["page"]]):
            raise ValueError("Localização ou geometria de origem inválida")
        key, position = geometry_key(row), (row["page"], row["row"])
        if key in keys or position in positions:
            raise ValueError("Duplicata normativa não resolvida")
        keys.add(key)
        positions.add(position)
        dimensions = {k: float(number(v, 2)) for k, v in row["dimensions"].items()}
        solid_section_properties(variant=FAMILIES[family][2], **dimensions)
        number(row["mass_kg_m"], 3)
    return records


def build_catalog(snapshot):
    records = validate_snapshot(snapshot)
    source = snapshot["source"]
    order = {name: index for index, name in enumerate(FAMILIES)}
    profiles, mass_audit = [], []
    for row in sorted(records, key=lambda item: (order[item["family"]], geometry_key(item)[1])):
        family = row["family"]
        label, code, variant, table, keys = FAMILIES[family]
        values = [number(row["dimensions"][key], 2) for key in keys]
        geometry = dict(zip(keys, map(float, values)))
        display = [compact(value).replace(".", ",") for value in values]
        dimensions_label = ("Ø" + display[0] if variant == "circular" else
                            "x".join(display * 2 if variant == "square" else display))
        designation = label + " " + dimensions_label
        profile_id = family + "-" + "x".join(compact(value).replace(".", "-") for value in values)
        aliases = []
        if variant == "circular":
            aliases.append(label + " " + display[0])
        if row["source_inches"]:
            # The square 13/16 row has a trailing typographic prime in the
            # printed inch column. Keep that original in source_metadata.
            inches = row["source_inches"].rstrip("’'′\"").replace("×", "x")
            aliases.extend((label + " " + inches + '"', inches + '"'))
        observations = [item["note"] for item in snapshot["audit"]["observations"]
                        if item.get("page") == row["page"] and item.get("row") == row["row"]]
        mass = float(number(row["mass_kg_m"], 3))
        ideal = solid_section_properties(variant=variant, **geometry).area * source["density_kg_m3"] * 1e-6
        mass_audit.append({
            "profile_id": profile_id, "table": table, "page": row["page"], "row": row["row"],
            "published_kg_m": mass, "ideal_kg_m": ideal,
            "difference_kg_m": mass - ideal, "relative_difference_percent": 100 * (mass / ideal - 1),
            "exceeds_0_5_percent": abs(mass / ideal - 1) >= 0.005,
        })
        profiles.append({
            "id": profile_id, "series_id": family, "designation": designation,
            "equivalent_designation": None, "aliases": aliases, "catalog_markers": [],
            "availability_status": "normative_table", "geometry_type": "solid_section",
            "geometry": geometry, "physical_properties": {"mass_per_length": mass},
            "section_properties": {}, "centroid": {},
            "source_metadata": {
                "source_page": row["page"], "source_table": table,
                "source_pdf_page": row["pdf_page"], "source_row": row["row"],
                "source_designation": row["source_reference"], "source_inches": row["source_inches"],
                "source_dimensions": geometry, "source_mass_per_length_kg_m": mass,
                "mass_type": "published", "mass_basis": "normative_table",
                "availability_note": "Dimensão tabelada; não indica oferta comercial. " + " ".join(observations),
            },
        })
    payload = {
        "schema_version": 2,
        "catalog": {
            "id": CATALOG_ID, "name": "ABNT NBR 16683:2018 — Aço Maciço",
            "catalog_version": "2018-corrected-2020", "manufacturer": None,
            "issuer": {"id": "abnt", "name": "ABNT"},
            "region": "BR", "country": "Brazil", "catalog_pack": "brazil",
            "source": {
                "source_name": "ABNT NBR 16683:2018", "source_type": "normative",
                "source_revision": "Versão corrigida 23.04.2020", "source_date": "2018-11-29",
                "source_url": "https://www.abntcatalogo.com.br/",
                "density_kg_m3": source["density_kg_m3"],
                "notes": source["title"] + ". " + source["mass_rule"] + " " + source["status_note"],
            },
            "standard_references": ["ABNT NBR 16683:2018, versão corrigida 23.04.2020"],
        },
        "units": {"length": "mm", "mass_per_length": "kg/m", "area": "mm2"},
        "categories": [{"id": "solid-steel", "name": "Aço Maciço"}],
        "series": [{
            "id": family, "category_id": "solid-steel", "name": data[0], "family": data[1],
            "geometry_type": "solid_section", "geometry_variant": data[2],
            "geometry_notes": "Seção nominal ideal maciça. A/I/W/r calculados pela Steel Structures; sem raios opcionais.",
        } for family, data in FAMILIES.items()],
        "profiles": profiles,
        "generation_audit": {
            "generator": "scripts/generate_nbr16683_solid_catalog.py",
            "snapshot": SNAPSHOT.name, "source_pdf_sha256": PDF_SHA256,
            "raw_records_sha256": RECORDS_SHA256, "counts": EXPECTED_COUNTS,
            "dimension_policy": "Explicit nominal columns only; no dimension swaps, Cartesian products or inch conversions.",
            "mass_policy": "Published nominal kg/m preserved verbatim numerically; ideal masses are QA only.",
            "mass_precision_decimal_places": 3, "source_corrections_applied": [],
            "observations": snapshot["audit"]["observations"],
            "mass_comparison": mass_audit,
        },
    }
    if len({p["id"] for p in profiles}) != len(profiles) or len({p["designation"] for p in profiles}) != len(profiles):
        raise ValueError("IDs/designações não são únicos")
    validate_catalog_payload(payload, OUTPUT)
    return payload


def render_catalog(snapshot):
    return (json.dumps(build_catalog(snapshot), ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, default=SNAPSHOT)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--check", action="store_true", help="Compare the installed bytes without writing")
    args = parser.parse_args()
    data = render_catalog(json.loads(args.snapshot.read_text(encoding="utf-8")))
    if args.check:
        if args.output.read_bytes() != data:
            parser.error("Catálogo estático diverge do gerador determinístico")
    else:
        args.output.write_bytes(data)
    print("OK: 164 perfis normativos (53 redondas, 19 quadradas, 92 chatas).")


if __name__ == "__main__":
    main()
