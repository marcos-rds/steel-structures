# SPDX-License-Identifier: LGPL-2.1-or-later
"""Generate the static Tuper hollow-section catalog from an audited snapshot."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path


EXPECTED_RAW = {"chs": 1239, "rhs": 1190, "shs": 678}
EXPECTED_UNIQUE = {"chs": 1131, "rhs": 1190, "shs": 678}
EXPECTED_DUPLICATES = 0
PDF_SHA256 = "89e6b3e838fedc8a842a01d9cf84a4b2ab48002e81ff70637253792e357a3cd5"
CORRECTIONS_PATH = (Path(__file__).resolve().parents[1] / "freecad" /
                    "SteelStructures" / "catalog_sources" /
                    "tuper_hollow_2024_source_corrections.json")


def _dimension_number(value):
    number = float(value)
    text = f"{number:.0f}" if number.is_integer() else f"{number:.2f}"
    return text.replace(".", ",")


def _thickness_number(value):
    return f"{float(value):.10f}".rstrip("0").rstrip(".").replace(".", ",")


def _slug_number(value):
    return f"{float(value):.10f}".rstrip("0").rstrip(".").replace(".", "-")


def _source_text(value):
    """Normalize only audited typography/decoding artifacts in source labels.

    Numeric fields and dimensional keys are never changed here.  The allowed
    repairs are recorded in ``snapshot.audit.text_normalization``.
    """
    return (value.replace("Ã˜", "Ø").replace("TÃ©cnica", "Técnica")
            .replace("”", '"').replace("�", "")) if value else value


def _normalize_extracted_text(value):
    """Recursively apply the audited source-label normalization."""
    if isinstance(value, dict):
        return {key: _normalize_extracted_text(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_normalize_extracted_text(item) for item in value]
    return _source_text(value) if isinstance(value, str) else value


def _key(record):
    return (
        record["family"], record.get("d_mm"), record.get("h_mm"),
        record.get("b_mm"), record["t_mm"],
    )


def _sort_key(record):
    order = {"shs": 0, "rhs": 1, "chs": 2}
    return (
        order[record["family"]], record.get("h_mm", record.get("d_mm", 0.0)),
        record.get("b_mm", 0.0), record["t_mm"], record["page"],
    )


class DuplicateCommercialConflict(ValueError):
    """A normalized geometry has contradictory commercial data."""


def _normalized_inches(value):
    if not value:
        return None
    text = _source_text(value).replace("Ø", "").casefold()
    # Extraction alternates spaces and dots as mixed-number separators
    # ("3 1/2" and "3.1/2"). They carry no distinct commercial meaning.
    return re.sub(r"[^0-9a-z/]", "", text)


def _material_signature(record):
    return (float(record["source_weight_p_kg_per_6m"]), record["availability"])


def load_source_corrections(path=CORRECTIONS_PATH):
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if payload.get("source_revision") != "2024":
        raise ValueError("source corrections vinculadas a revisão inesperada")
    if payload.get("source_pdf_sha256") != PDF_SHA256:
        raise ValueError("source corrections não correspondem ao SHA-256 da fonte")
    return payload


def _matches(record, selector):
    return all(record.get(key) == value for key, value in selector.items())


def _records_fingerprint(records):
    canonical = sorted(
        records,
        key=lambda record: json.dumps(
            record, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        ),
    )
    return hashlib.sha256(json.dumps(
        canonical, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")).hexdigest()


def apply_source_corrections(raw_records, correction_payload=None):
    """Apply only declared, source-bound errata before commercial reconciliation."""
    payload = correction_payload or load_source_corrections()
    records = [dict(record) for record in raw_records]
    applied = []
    for correction in payload["corrections"]:
        if (correction.get("source_catalog") != payload["source_catalog"] or
                correction.get("source_revision") != payload["source_revision"] or
                correction.get("source_pdf_sha256") != PDF_SHA256):
            raise ValueError(f"source correction sem vínculo completo: {correction.get('id')}")
        matched = [record for record in records if _matches(record, correction["selector"])]
        expected_matches = correction["expected_matches"]
        if len(matched) != expected_matches:
            raise ValueError(
                f"source correction {correction['id']} esperava {expected_matches} "
                f"ocorrências, encontrou {len(matched)}"
            )
        actual_fingerprint = _records_fingerprint(matched)
        if actual_fingerprint != correction.get("matched_records_sha256"):
            raise ValueError(
                f"source correction {correction['id']} encontrou contexto divergente: "
                f"sha256={actual_fingerprint}"
            )
        action = correction["action"]
        if action == "exclude_records":
            records = [record for record in records
                       if not _matches(record, correction["selector"])]
        elif action == "replace_dimensions":
            replacement = correction["normalized_correction"]
            for record in matched:
                record.update(replacement)
                record["source_correction_id"] = correction["id"]
        else:
            raise ValueError(f"ação de source correction desconhecida: {action}")
        applied.append({"id": correction["id"], "matched_records": len(matched)})
    return records, applied


def reconcile_duplicates(raw_records):
    """Reject material conflicts and merge compatible optional metadata."""
    grouped = defaultdict(list)
    for record in raw_records:
        grouped[_key(record)].append(record)
    reconciled = {}
    for key, occurrences in grouped.items():
        signatures = {_material_signature(record) for record in occurrences}
        inches = {_normalized_inches(record.get("source_inches"))
                  for record in occurrences if record.get("source_inches")}
        if len(signatures) > 1 or len(inches) > 1:
            details = "; ".join(
                f"page={record.get('page')}, p={record.get('source_weight_p_kg_per_6m')}, "
                f"availability={record.get('availability')!r}, "
                f"inches={record.get('source_inches')!r}"
                for record in occurrences
            )
            raise DuplicateCommercialConflict(
                f"commercial duplicate conflict: family={key[0]}, key={key!r}; {details}"
            )
        ordered = sorted(occurrences, key=_sort_key)
        merged = dict(ordered[0])
        merged["source_pages"] = sorted({record["page"] for record in occurrences})
        designations = sorted({record.get("source_designation") for record in occurrences
                               if record.get("source_designation")})
        inch_aliases = sorted({record.get("source_inches") for record in occurrences
                               if record.get("source_inches")})
        conditions = set()
        for record in occurrences:
            for field in ("source_condition", "source_conditions",
                          "source_notes", "conditions_text"):
                value = record.get(field)
                if isinstance(value, (list, tuple)):
                    conditions.update(item for item in value if item)
                elif value:
                    conditions.add(value)
        merged["source_designations"] = designations
        merged["source_inches_aliases"] = inch_aliases
        merged["source_conditions"] = sorted(conditions)
        if inch_aliases:
            merged["source_inches"] = inch_aliases[0]
        reconciled[key] = merged
    return reconciled


def validate_snapshot(payload):
    if payload.get("raw_summary") != EXPECTED_RAW:
        raise ValueError(f"contagens brutas inesperadas: {payload.get('raw_summary')!r}")
    if payload.get("summary") != EXPECTED_UNIQUE:
        raise ValueError(f"contagens finais inesperadas: {payload.get('summary')!r}")
    if payload.get("duplicate_key_count") != EXPECTED_DUPLICATES:
        raise ValueError("quantidade inesperada de chaves duplicadas")
    raw = payload.get("raw_records", ())
    raw_digest = hashlib.sha256(json.dumps(
        raw, ensure_ascii=False, separators=(",", ":"),
    ).encode("utf-8")).hexdigest()
    if payload.get("audit", {}).get("raw_records_sha256") != raw_digest:
        raise ValueError("raw_records_sha256 diverge dos registros brutos")
    corrected, applied = apply_source_corrections(raw)
    occurrences = {}
    for record in corrected:
        key = _key(record)
        occurrences[key] = occurrences.get(key, 0) + 1
    winners = reconcile_duplicates(corrected)
    if sum(value - 1 for value in occurrences.values()) != EXPECTED_DUPLICATES:
        raise ValueError("duplicatas após erratas não conferem")
    records = payload.get("records", ())
    if len(records) != sum(EXPECTED_UNIQUE.values()):
        raise ValueError("quantidade total final não confere")
    if {_key(record): record for record in records} != winners:
        raise ValueError("snapshot diverge da reconciliação comercial determinística")
    if payload.get("source_corrections_applied") != applied:
        raise ValueError("auditoria de source corrections diverge da aplicação declarada")
    for record in records:
        if abs(record["mass_per_meter_kg_m"] - record["source_weight_p_kg_per_6m"] / 6.0) > 1e-12:
            raise ValueError(f"massa divergente de p/6 em {_key(record)!r}")


def _profile(record):
    family = record["family"]
    t = record["t_mm"]
    if family == "chs":
        d = record["d_mm"]
        dimensions = {"d": d, "t": t}
        designation = f"CHS {_dimension_number(d)}x{_thickness_number(t)}"
        profile_id = f"chs-{_slug_number(d)}x{_slug_number(t)}"
        source_dimensions = {"d": d}
    else:
        h, b = max(record["h_mm"], record["b_mm"]), min(record["h_mm"], record["b_mm"])
        dimensions = ({"b": h, "t": t} if family == "shs"
                      else {"h": h, "b": b, "t": t})
        prefix = family.upper()
        designation = (
            f"{prefix} {_dimension_number(h)}x{_dimension_number(b)}"
            f"x{_thickness_number(t)}"
        )
        profile_id = f"{family}-{_slug_number(h)}x{_slug_number(b)}x{_slug_number(t)}"
        source_dimensions = {
            "l1": record["source_l1_mm"], "l2": record["source_l2_mm"],
        }
    source_designation = _source_text(record["source_designation"])
    aliases = [designation.replace("x", "×"), source_designation]
    if record.get("source_inches"):
        aliases.append(record["source_inches"])
    return {
        "id": profile_id,
        "designation": designation,
        "equivalent_designation": record.get("source_inches"),
        "aliases": list(dict.fromkeys(aliases)),
        "catalog_markers": [],
        "availability_status": record["availability"],
        "geometry_status": "released",
        "series_id": family,
        "geometry_type": "hollow_section",
        "geometry": dimensions,
        "physical_properties": {"mass_per_length": record["source_weight_p_kg_per_6m"] / 6.0},
        "section_properties": {},
        "centroid": {},
        "source_metadata": {
            "source_page": record["page"],
            "source_weight_p_kg_per_6m": record["source_weight_p_kg_per_6m"],
            "source_weight_basis_mm": 6000.0,
            "source_designation": source_designation,
            "source_inches": record.get("source_inches"),
            "source_dimensions": source_dimensions,
            "source_pages": record.get("source_pages", [record["page"]]),
            "source_correction_id": record.get("source_correction_id"),
            "source_designations": record.get("source_designations", [source_designation]),
            "source_inches_aliases": record.get("source_inches_aliases", []),
            "source_conditions": record.get("source_conditions", []),
            "availability_note": ("Sob consulta na tabela-fonte" if record["availability"] == "consultation" else None),
        },
    }


def build_catalog(snapshot):
    validate_snapshot(snapshot)
    profiles = [_profile(record) for record in sorted(snapshot["records"], key=_sort_key)]
    if len({profile["id"] for profile in profiles}) != len(profiles):
        raise ValueError("IDs de perfil duplicados após normalização")
    if len({profile["designation"] for profile in profiles}) != len(profiles):
        raise ValueError("designações duplicadas após normalização")
    return {
        "schema_version": 2,
        "catalog": {
            "id": "arcelormittal-tuper-hollow-2024",
            "name": "ArcelorMittal Tuper — Perfis Tubulares 2024",
            "catalog_version": "2024",
            "manufacturer": {"id": "arcelormittal-tuper", "name": "ArcelorMittal Tuper"},
            "source": {
                "source_name": _source_text(snapshot["source_title"]),
                "source_revision": "2024",
                "source_url": snapshot["source_url"],
                "source_date": "2024",
                "notes": (
                    "Dimensões e peso p publicados pela fabricante; massa linear calculada como p/6. "
                    "Propriedades geométricas calculadas pela Steel Structures. Condições gerais e "
                    "disponibilidade devem ser consultadas na publicação; nenhuma norma de produto é inferida."
                ),
            },
            "standard_references": [],
            "material_notes": "Condições gerais da publicação-fonte; não inferidas individualmente por perfil.",
            "supply_condition_definitions": [
                {
                    "code": "RA",
                    "description": "Rebarba Interna Alta, Sem Remoção",
                    "availability": "normal",
                    "source_page": 17,
                },
                {
                    "code": "RIR",
                    "description": "Rebarba Interna Removida",
                    "availability": "special_consultation",
                    "source_page": 17,
                },
                {
                    "code": "RIC",
                    "description": "Rebarba Interna Controlada",
                    "availability": "special_consultation",
                    "source_page": 17,
                },
            ],
        },
        "units": {"length": "mm", "mass_per_length": "kg/m", "area": "mm2"},
        "categories": [{"id": "tubular", "name": "Aço Tubular"}],
        "series": [
            {"id": "shs", "category_id": "tubular", "name": "SHS — Tubo quadrado", "family": "SHS", "geometry_type": "hollow_section", "geometry_variant": "square", "geometry_notes": "Dimensões comerciais Tuper; representação CAD usa convenção própria documentada."},
            {"id": "rhs", "category_id": "tubular", "name": "RHS — Tubo retangular", "family": "RHS", "geometry_type": "hollow_section", "geometry_variant": "rectangular", "geometry_notes": "Designação pública H×B×t com H≥B; ordem L1/L2 preservada nos metadados da fonte."},
            {"id": "chs", "category_id": "tubular", "name": "CHS — Tubo redondo", "family": "CHS", "geometry_type": "hollow_section", "geometry_variant": "circular", "geometry_notes": "Diâmetro externo e espessura comerciais Tuper."},
        ],
        "profiles": profiles,
        "generation_audit": {
            "source_pdf_sha256": PDF_SHA256,
            "source_pages": snapshot["source_pages"],
            "raw_counts": EXPECTED_RAW,
            "final_counts": EXPECTED_UNIQUE,
            "duplicate_key_count": EXPECTED_DUPLICATES,
            "duplicate_resolution": "explicit_source_errata_then_conflict_audit",
            "source_corrections": snapshot["source_corrections_applied"],
        },
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--snapshot-output", type=Path)
    args = parser.parse_args()
    data = args.source.read_bytes()
    snapshot = _normalize_extracted_text(json.loads(data.decode("utf-8")))
    corrected, applied = apply_source_corrections(snapshot["raw_records"])
    records = reconcile_duplicates(corrected)
    snapshot["records"] = sorted(records.values(), key=_sort_key)
    snapshot["summary"] = dict(Counter(record["family"] for record in snapshot["records"]))
    snapshot["duplicate_key_count"] = sum(
        count - 1 for count in Counter(_key(record) for record in corrected).values()
    )
    snapshot["source_corrections_applied"] = applied
    catalog = build_catalog(snapshot)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.snapshot_output:
        args.snapshot_output.parent.mkdir(parents=True, exist_ok=True)
        raw_bytes = json.dumps(
            snapshot["raw_records"], ensure_ascii=False, separators=(",", ":"),
        ).encode("utf-8")
        digest = hashlib.sha256(raw_bytes).hexdigest()
        stored_snapshot = dict(snapshot)
        stored_snapshot["source"] = "Tabela-Tecnica-de-Produtos-Tuper-2024.pdf"
        stored_snapshot["audit"] = {
            "source_pdf_sha256": PDF_SHA256,
            "raw_records_sha256": digest,
            "extraction_rule": (
                "raw extraction -> explicit source errata -> normalization -> "
                "duplicate/conflict audit; compatible metadata merged deterministically"
            ),
            "source_corrections_file": CORRECTIONS_PATH.name,
            "source_corrections_applied": applied,
            "text_normalization": [
                "mojibake Ã˜ -> Ø",
                "mojibake TÃ©cnica -> Técnica",
                "curly closing inch quote U+201D -> ASCII quote",
                "replacement character U+FFFD removed from source labels",
            ],
        }
        args.snapshot_output.write_text(
            json.dumps(stored_snapshot, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"snapshot_sha256={digest}")
    print(f"profiles={len(catalog['profiles'])}")


if __name__ == "__main__":
    main()
