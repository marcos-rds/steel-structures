# SPDX-License-Identifier: LGPL-2.1-or-later
"""Extract the audited ABNT solid-bar tables from a user-supplied PDF.

PyMuPDF is needed only for this development command, never at workbench runtime.
The PDF is read in place and is not copied into the repository.  All source
dimensions and masses are retained as printed decimal strings; this command
does not calculate, repair, or discard normative table entries.
"""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re


PDF_SHA256 = "dfda6bd8d496dfaf435503d0145fa0ac6d5bb47515c06975bba4bb54fbccddbd"
EXPECTED_COUNTS = {"round-bar": 53, "square-bar": 19, "flat-bar": 92}
# PDF page number, family, table, number of data rows (excluding notes/header).
PAGE_TABLES = (
    (12, "flat-bar", "A.1", 14),
    (13, "flat-bar", "A.1", 29),
    (14, "flat-bar", "A.1", 29),
    (15, "flat-bar", "A.1", 20),
    (16, "round-bar", "A.2", 25),
    (17, "round-bar", "A.2", 28),
    (18, "square-bar", "A.3", 19),
)
DEFAULT_OUTPUT = (
    Path(__file__).resolve().parents[1]
    / "freecad" / "SteelStructures" / "catalog_sources"
    / "abnt_nbr_16683_2018_solid_extracted.json"
)


def records_sha256(records):
    """Fingerprint the literal extracted records, independently of formatting."""
    raw = json.dumps(
        records, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def extract_records(document):
    records = []
    for pdf_page, family, table_name, expected_rows in PAGE_TABLES:
        tables = document[pdf_page - 1].find_tables().tables
        if len(tables) != 1:
            raise ValueError(f"Expected one table on PDF page {pdf_page}")
        rows = [
            row for row in tables[0].extract()[1:]
            if row[-1] and re.fullmatch(r"\d+,\d{3}", row[-1])
        ]
        if len(rows) != expected_rows:
            raise ValueError(
                f"PDF page {pdf_page}: {len(rows)} rows, expected {expected_rows}"
            )
        for row_number, row in enumerate(rows, 1):
            if family == "flat-bar":
                dimensions = {"b": row[2], "t": row[3]}
            else:
                dimensions = {"d" if family == "round-bar" else "b": row[2]}
            if any(
                not re.fullmatch(r"\d+,\d{2}", value)
                for value in dimensions.values()
            ):
                raise ValueError(f"Invalid dimensions on page {pdf_page}: {row}")
            records.append({
                "family": family,
                "table": table_name,
                "page": pdf_page - 6,
                "pdf_page": pdf_page,
                "row": row_number,
                "source_inches": None if row[0] in (None, "b") else row[0],
                "source_reference": row[1],
                "dimensions": dimensions,
                "mass_kg_m": row[-1],
            })
    if Counter(record["family"] for record in records) != EXPECTED_COUNTS:
        raise ValueError("Unexpected family counts in extracted tables")
    keys = [(record["family"], tuple(record["dimensions"].items()))
            for record in records]
    if len(keys) != len(set(keys)):
        raise ValueError("Duplicate nominal dimensions require a separate audit")
    return records


def build_snapshot(pdf_path):
    pdf_path = Path(pdf_path)
    digest = hashlib.sha256(pdf_path.read_bytes()).hexdigest()
    if digest != PDF_SHA256:
        raise ValueError("The PDF differs from the visually audited publication")
    import pymupdf

    with pymupdf.open(pdf_path) as document:
        if len(document) != 25:
            raise ValueError("Expected six preliminary pages and 19 numbered pages")
        records = extract_records(document)
    return {
        "schema_version": 1,
        "source": {
            "standard": "ABNT NBR 16683:2018",
            "title": (
                "Barras laminadas de aço, chatas, redondas, quadradas e "
                "sextavadas, para uso estrutural — Dimensões e tolerâncias"
            ),
            "publisher": "ABNT",
            "publication_kind": "user_supplied_primary_publication",
            "sha256": digest,
            "edition_date": "2018-11-29",
            "corrected_date": "2020-04-23",
            "errata": [{"number": 1, "date": "2020-04-23", "reference": "Prefácio, p. v"}],
            "isbn": "978-85-07-07801-2",
            "pdf_page_count": 25,
            "numbered_page_count": 19,
            "table_pages": {"A.1": [6, 7, 8, 9], "A.2": [10, 11], "A.3": [12]},
            "density_kg_m3": 7850,
            "density_printed": "7,85 g/cm³",
            "mass_rule_reference": "4.3.3 e nota, p. 2",
            "mass_rule": (
                "Massas nominais orientativas, não usadas como critério de reprovação. "
                "A nota informa cálculo com densidade de 7,85 g/cm³. "
                "Este snapshot conserva a massa publicada sem recalculá-la."
            ),
            "scope": (
                "Barras laminadas a quente para uso estrutural e geral. Exclui barras "
                "nervuradas para concreto, produtos cortados de chapas ou bobinas, "
                "produtos para processos de aplicação mecânica e barras laminadas a frio."
            ),
            "scope_reference": "1.1 a 1.5, p. 1",
            "current_status_verified": False,
            "status_note": (
                "Edição e correção conferidas no exemplar fornecido. "
                "A vigência atual não foi confirmada no catálogo online da ABNT."
            ),
        },
        "summary": EXPECTED_COUNTS,
        "audit": {
            "raw_records_sha256": records_sha256(records),
            "raw_records_sha256_basis": (
                "UTF-8 JSON of records; ensure_ascii=False; sort_keys=True; "
                "separators=(',', ':')"
            ),
            "source_corrections_applied": [],
            "duplicate_nominal_geometry_count": 0,
            "visual_review": (
                "Cabeçalhos, linhas de dados, continuações e notas das Tabelas A.1, "
                "A.2 e A.3 conferidos nas sete páginas renderizadas do exemplar."
            ),
            "observations_are_official_errata": False,
            "observations": [
                {
                    "table": "A.1", "page": 8, "pdf_page": 14, "row": 19,
                    "kind": "reference_dimension_conflict",
                    "note": (
                        "A linha 3 × 2 publica referência 76,20 × 49,80, mas as colunas "
                        "Largura e Espessura contêm 76,20 e 50,80. Ambos os textos são "
                        "preservados; dimensions usa somente as colunas dimensionais explícitas."
                    ),
                },
                {
                    "tables": ["A.1", "A.2", "A.3"],
                    "kind": "footnote_cross_reference",
                    "note": (
                        "As notas a remetem a 4.1.3, numeração ausente no exemplar. "
                        "A regra de massas orientativas está em 4.3.3. "
                        "Esta observação não altera o texto publicado."
                    ),
                },
                {
                    "tables": ["A.1", "A.2"],
                    "kind": "metric_commercial_designation",
                    "note": (
                        "A nota b indica denominação comercial em milímetros: 11 linhas "
                        "de chatas com largura 130,00 e duas redondas de 11,50 e 12,00. "
                        "source_inches é null nessas linhas; a referência original permanece."
                    ),
                },
                {
                    "kind": "nominal_mass_and_corner_geometry",
                    "note": (
                        "Massas tabuladas não são substituídas por área ideal vezes densidade. "
                        "B.1.2 não controla raios de chatas; B.6 fornece faixas de raios para "
                        "quadradas, sem um raio nominal único. Não se infere raio pela massa."
                    ),
                },
            ],
        },
        "records": records,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf", type=Path, help="Local primary publication; never copied")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    if args.pdf.resolve() == args.output.resolve():
        raise ValueError("The snapshot output cannot overwrite the primary PDF")
    snapshot = build_snapshot(args.pdf)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8", newline="\n",
    )
    print(f"Extracted {len(snapshot['records'])} rows: {snapshot['summary']}")
    print(f"Raw records SHA-256: {snapshot['audit']['raw_records_sha256']}")


if __name__ == "__main__":
    main()
