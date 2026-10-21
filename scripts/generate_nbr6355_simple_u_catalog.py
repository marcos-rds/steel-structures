# SPDX-License-Identifier: LGPL-2.1-or-later
"""Deterministic Tabela A.2 catalog from the authorized, audited 125-row XLSX.

Default: use the committed source snapshot, with no Excel/PDF dependency.
--xlsx: extract the exact source file to the snapshot before generation.
--check: compare bytes only, without modifying either file.
"""

import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import sys
from zipfile import ZipFile
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from freecad.SteelStructures.profiles.validation import validate_catalog_payload

SNAPSHOT = ROOT / "freecad/SteelStructures/catalog_sources/abnt_nbr_6355_2012_a2_extracted.json"
OUTPUT = ROOT / "freecad/SteelStructures/catalogs/abnt_nbr_6355_2012_a2.json"
XLSX_NAME = "NBR_6355_2012_Perfis_Formados_a_Frio_Ajustado.xlsx"
XLSX_SHA256 = "291618ca5ad72dfb97606b4b340e72d18cfdb368b9ebaf50dc43b69c7c370155"
PDF_SHA256 = "92de1de4f0547c44c1007397d87a3f80b20ae02b772fbb141220c6fda6ae4b71"
CELLS_SHA256 = "a0394c448abc0f1c8ecc5beddaf312816dd0562106b53627d878d675cb33883f"
CATALOG_ID = "abnt-nbr-6355-2012-a2"
SERIES_ID = "u-simple-nbr-6355"
SHEET = "U - Sem revest"
COLUMNS = "ABCDEFGHIJKLMNOPQR"
NS = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
PAGE_RANGES = ((4, 34, 27), (35, 60, 28), (61, 92, 29), (93, 123, 30), (124, 128, 31))


def fingerprint(cells):
    return hashlib.sha256(json.dumps(
        cells, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    ).encode("utf-8")).hexdigest()


def extract_snapshot(path):
    """Keep original XML numeric strings; never round to display formats."""
    if hashlib.sha256(path.read_bytes()).hexdigest() != XLSX_SHA256:
        raise ValueError("Planilha diverge da fonte autorizada e auditada")
    with ZipFile(path) as archive:
        strings = (["".join(item.itertext()) for item in ET.fromstring(archive.read("xl/sharedStrings.xml"))]
                   if "xl/sharedStrings.xml" in archive.namelist() else [])
        workbook = ET.fromstring(archive.read("xl/workbook.xml"))
        sheet = next(item for item in workbook.find("s:sheets", NS) if item.get("name") == SHEET)
        relations = {item.get("Id"): item.get("Target") for item in
                     ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))}
        target = relations[sheet.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id")]
        target = target.lstrip("/") if target.startswith("/") else "xl/" + target
        cells = {}
        for row in ET.fromstring(archive.read(target)).findall("s:sheetData/s:row", NS):
            number = int(row.get("r"))
            if not 4 <= number <= 128:
                continue
            values = {}
            for cell in row:
                column = re.sub(r"\d", "", cell.get("r"))
                if column not in COLUMNS or len(column) != 1:
                    continue
                if cell.find("s:f", NS) is not None:
                    raise ValueError("A fonte auditada não contém fórmulas")
                value = cell.find("s:v", NS)
                if cell.get("t") == "s":
                    value = strings[int(value.text)]
                elif cell.get("t") == "inlineStr":
                    value = "".join(cell.find("s:is", NS).itertext())
                else:
                    value = value.text if value is not None else None
                values[column] = value
            cells[str(number)] = values
    snapshot = {
        "schema_version": 1,
        "source": {"file": XLSX_NAME, "sha256": XLSX_SHA256, "sheet": SHEET,
                   "range": "A4:R128", "pdf_sha256": PDF_SHA256},
        "audit": {
            "cells_sha256": CELLS_SHA256, "profile_count": 125,
            "numeric_cells_compared_with_pdf": 2125,
            "numeric_differences": 0,
            "excluded_pdf_row": {
                "designation": "U300x100x2,65", "pdf_page": 30, "printed_page": 24,
                "reason": "Ausente da planilha autorizada; célula de massa vazia no PDF. Nenhum valor reconstruído.",
            },
        },
        "cells": cells,
    }
    validate_snapshot(snapshot)
    return snapshot


def validate_snapshot(snapshot):
    source = snapshot["source"]
    if (snapshot.get("schema_version") != 1
            or source != {"file": XLSX_NAME, "sha256": XLSX_SHA256, "sheet": SHEET,
                          "range": "A4:R128", "pdf_sha256": PDF_SHA256}
            or snapshot["audit"]["cells_sha256"] != CELLS_SHA256
            or fingerprint(snapshot["cells"]) != CELLS_SHA256):
        raise ValueError("Snapshot diverge das células auditadas da Tabela A.2")
    cells = snapshot["cells"]
    if set(cells) != {str(row) for row in range(4, 129)}:
        raise ValueError("Esperadas exatamente as 125 linhas A4:R128")
    for values in cells.values():
        if set(values) != set(COLUMNS):
            raise ValueError("Linha incompleta no snapshot")
        if any(not math.isfinite(float(values[c])) or float(values[c]) <= 0 for c in COLUMNS[1:]):
            raise ValueError("Propriedades devem ser positivas e finitas")


def build_catalog(snapshot):
    validate_snapshot(snapshot)
    profiles = []
    for number in range(4, 129):
        values = snapshot["cells"][str(number)]
        # Python float parsing preserves the source's available binary precision.
        v = {column: float(values[column]) for column in COLUMNS[1:]}
        bw, bf, t = v["D"], v["E"], v["F"]
        compact = f"{bw:g}x{bf:g}x{t:.2f}"
        if values["A"] != "U" + compact.replace(".", ","):
            raise ValueError("Designação diverge das dimensões da planilha")
        page = next(page for start, end, page in PAGE_RANGES if start <= number <= end)
        geometry = {"bw": bw, "bf": bf, "tn": t, "t": t, "ri": v["G"]}
        profiles.append({
            "id": "u-" + compact,
            "designation": f"U {bw:g} × {bf:g} × {t:.2f}".replace(".", ","),
            "aliases": [values["A"], "U " + compact],
            "catalog_markers": ["Tabela A.2", "aço sem revestimento"],
            "availability_status": "normative_table", "geometry_status": "released",
            "series_id": SERIES_ID, "geometry_type": "cold_formed_channel",
            "geometry": geometry,
            "physical_properties": {"mass_per_length": v["B"], "area": v["C"]},
            "section_properties": {name: v[column] for name, column in (
                ("ix", "H"), ("wx", "I"), ("rx", "J"), ("x0", "L"),
                ("iy", "M"), ("wy", "N"), ("ry", "O"), ("it", "P"), ("cw", "Q"), ("r0", "R"),
            )},
            "centroid": {"x": v["K"]},
            "source_metadata": {
                "source_table": "A.2", "source_row": number, "source_page": page - 6,
                "source_pdf_page": page, "source_designation": values["A"],
                "source_dimensions": geometry.copy(),
                "source_mass_per_length_kg_m": v["B"],
                "mass_type": "published", "mass_basis": "normative_table",
            },
        })
    profiles.sort(key=lambda p: tuple(p["geometry"][key] for key in ("bw", "bf", "tn")))
    if len({p["id"] for p in profiles}) != 125 or len({p["designation"] for p in profiles}) != 125:
        raise ValueError("IDs/designações duplicadas")
    payload = {
        "schema_version": 2,
        "catalog": {
            "id": CATALOG_ID, "name": "Perfis U dobrados simples - ABNT NBR 6355:2012",
            "catalog_version": "2012-a2", "manufacturer": None,
            "issuer": {"id": "abnt", "name": "Associação Brasileira de Normas Técnicas"},
            "source": {
                "source_name": "ABNT NBR 6355:2012 - Anexo A - Tabela A.2",
                "source_type": "normative", "source_revision": "Segunda edição, 30.11.2012",
                "source_date": "2012-12-30",
                "notes": "Anexo A informativo; Figura A.2; Tabela A.2; aço sem revestimento. Propriedades publicadas pelo método linear; distintas da geometria física CAD.",
            },
            "standard_references": ["ABNT NBR 6355:2012", "Anexo A (informativo)", "Figura A.2", "Tabela A.2"],
            "material_notes": "Aço sem revestimento; t = tn.",
        },
        "units": {"length": "mm", "centroid": "cm", "radius_of_gyration": "cm",
                  "mass_per_length": "kg/m", "area": "cm2", "section_modulus": "cm3",
                  "second_moment_of_area": "cm4", "warping_constant": "cm6"},
        "categories": [{"id": "aco-dobrado", "name": "Aço Dobrado"}],
        "series": [{"id": SERIES_ID, "category_id": "aco-dobrado",
                    "name": "U Dobrado Simples (U) — NBR 6355", "family": "U",
                    "geometry_type": "cold_formed_channel", "geometry_variant": "simple_u",
                    "geometry_notes": "Alma e duas mesas, sem enrijecedores. Espessura constante e dobras circulares; propriedades tabeladas pelo método linear normativo."}],
        "profiles": profiles,
        "generation_audit": {
            "generator": "scripts/generate_nbr6355_simple_u_catalog.py",
            "snapshot": SNAPSHOT.name, "source": snapshot["source"],
            "cells_sha256": CELLS_SHA256, "profile_count": 125,
            "numeric_cells_compared_with_pdf": 2125, "numeric_differences": 0,
            "excluded_pdf_row": snapshot["audit"]["excluded_pdf_row"],
            "area_policy": "Tabela A.2 preservada; aparente inconsistência de uma dobra na expressão impressa do item 10 documentada, sem correção silenciosa.",
            "source_corrections_applied": [],
        },
    }
    validate_catalog_payload(payload, OUTPUT)
    return payload


def render_catalog(snapshot):
    return (json.dumps(build_catalog(snapshot), ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--xlsx", type=Path)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    snapshot = extract_snapshot(args.xlsx) if args.xlsx else json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    data = render_catalog(snapshot)
    snapshot_bytes = (json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    if args.check:
        if data != OUTPUT.read_bytes() or snapshot_bytes != SNAPSHOT.read_bytes():
            parser.error("Catálogo/snapshot divergem das fontes e do gerador")
    else:
        SNAPSHOT.write_bytes(snapshot_bytes)
        OUTPUT.write_bytes(data)
    print("OK: 125 perfis U simples; dados publicados preservados.")


if __name__ == "__main__":
    main()
