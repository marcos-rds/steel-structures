# SPDX-License-Identifier: LGPL-2.1-or-later
"""Pure presentation data for structural profile catalog interfaces."""

from __future__ import annotations

from dataclasses import dataclass

from .models import ProfileDefinition


@dataclass(frozen=True)
class PresentationRow:
    label: str
    value: str
    tooltip: str | None = None


@dataclass(frozen=True)
class PresentationGroup:
    title: str
    rows: tuple[PresentationRow, ...]


_DIMENSION_LABELS = {
    "d": "d", "bf": "bf", "tw": "tw", "tf": "tf",
    "h": "h", "d_prime": "d'", "b": "b", "t": "t",
    "bw": "bw", "D": "D", "tn": "tn", "ri": "ri",
    "r1": "r1", "r2": "r2", "flange_angle": "Ângulo da mesa",
    "tl": "TL",
}
_PROPERTY_SPECS = {
    "ix": ("Ix", 1e-4, "cm⁴", "Momento de inércia em torno do eixo X-X"),
    "wx": ("Wx", 1e-3, "cm³", "Módulo resistente elástico no eixo X-X"),
    "zx": ("Zx", 1e-3, "cm³", "Módulo resistente plástico no eixo X-X"),
    "rx": ("rx", 0.1, "cm", "Raio de giração no eixo X-X"),
    "iy": ("Iy", 1e-4, "cm⁴", "Momento de inércia em torno do eixo Y-Y"),
    "wy": ("Wy", 1e-3, "cm³", "Módulo resistente elástico no eixo Y-Y"),
    "zy": ("Zy", 1e-3, "cm³", "Módulo resistente plástico no eixo Y-Y"),
    "ry": ("ry", 0.1, "cm", "Raio de giração no eixo Y-Y"),
    "rt": ("rt", 0.1, "cm", "Raio efetivo para flambagem lateral com torção"),
    "it": ("It", 1e-4, "cm⁴", "Constante de torção"),
    "cw": ("Cw", 1e-6, "cm⁶", "Constante de empenamento"),
    "x0": ("x0", 0.1, "cm", "Distância do centro de torção ao centroide, na direção X"),
    "r0": ("r0", 0.1, "cm", "Raio polar em relação ao centro de torção"),
    "rz_min": ("rz mín.", 0.1, "cm", "Raio de giração mínimo"),
    "slenderness_flange": ("bf / 2tf", 1.0, "", None),
    "slenderness_web": ("d' / tw", 1.0, "", None),
}


def format_number(value: float, decimals: int | None = None) -> str:
    """Format a number for pt-BR without changing its stored value."""
    if decimals is None:
        decimals = 0 if float(value).is_integer() else min(2, len(f"{value:.6f}".rstrip("0").split(".")[-1]))
    text = f"{value:,.{decimals}f}"
    return text.replace(",", "\0").replace(".", ",").replace("\0", ".")


def format_engineering_value(value: float, scale: float, unit: str, decimals=None) -> str:
    rendered = format_number(value * scale, decimals)
    return f"{rendered} {unit}".rstrip()


def profile_dimension_rows(profile: ProfileDefinition) -> tuple[PresentationRow, ...]:
    if profile.geometry_type == "solid_section":
        labels = {
            "circular": (("d", "Diâmetro (D)"),),
            "square": (("b", "Lado (B)"),),
            "rectangular": (("b", "Largura (B)"), ("t", "Espessura (t)")),
        }
        return tuple(PresentationRow(
            label, format_engineering_value(profile.geometry[key], 1.0, "mm")
        ) for key, label in labels[profile.geometry_variant])
    if (profile.geometry_type, profile.geometry_variant) == ("hollow_section", "rectangular"):
        from .hollow_sections import normalize_hollow_profile_definition
        profile = normalize_hollow_profile_definition(profile)
    rows = []
    for key, value in profile.geometry.items():
        if key not in _DIMENSION_LABELS:
            continue
        unit = "°" if key == "flange_angle" else "mm"
        rows.append(PresentationRow(
            _DIMENSION_LABELS[key], format_engineering_value(value, 1.0, unit)
        ))
    return tuple(rows)


def profile_preview_dimension_rows(profile: ProfileDefinition) -> tuple[PresentationRow, ...]:
    """Return only the principal dimensions annotated by the supported preview."""
    if (profile.geometry_type, profile.geometry_variant) == ("hollow_section", "rectangular"):
        from .hollow_sections import normalize_hollow_profile_definition
        profile = normalize_hollow_profile_definition(profile)
    key = (profile.geometry_type, profile.geometry_variant)
    keys_by_geometry = {
        ("i_section", "parallel_flange"): ("d", "bf", "tw", "tf"),
        ("i_section", "tapered_flange"): ("d", "bf", "tw", "tf"),
        ("equal_angle", "equal_leg"): ("b", "t"),
        ("channel_section", "tapered_flange"): ("d", "bf", "tw", "tf"),
        ("tee_section", "standard_tee"): ("d", "bf", "tw", "tf"),
        ("cold_formed_channel", "stiffened_u"): ("bw", "bf", "D", "t", "ri"),
        ("hollow_section", "square"): ("b", "t"),
        ("hollow_section", "rectangular"): ("h", "b", "t"),
        ("hollow_section", "circular"): ("d", "t"),
        ("solid_section", "circular"): ("d",),
        ("solid_section", "square"): ("b",),
        ("solid_section", "rectangular"): ("b", "t"),
    }
    if key not in keys_by_geometry:
        return ()
    hollow_labels = {"b": "B", "h": "H", "d": "ØD", "t": "t"}
    return tuple(
        PresentationRow(
            hollow_labels.get(key, key)
            if profile.geometry_type in ("hollow_section", "solid_section") else key,
            format_engineering_value(profile.geometry[key], 1.0, "mm"),
        )
        for key in keys_by_geometry[key] if key in profile.geometry
    )


def _property_rows(profile, keys):
    rows = []
    for key in keys:
        if key not in profile.section_properties:
            continue
        label, scale, unit, tooltip = _PROPERTY_SPECS[key]
        rows.append(PresentationRow(
            label, format_engineering_value(profile.section_properties[key], scale, unit), tooltip
        ))
    return tuple(rows)


def profile_property_groups(profile: ProfileDefinition) -> tuple[PresentationGroup, ...]:
    physical = profile.physical_properties
    is_ue = (profile.geometry_type, profile.geometry_variant) == (
        "cold_formed_channel", "stiffened_u"
    )
    is_solid = profile.geometry_type == "solid_section"
    physical_rows = []
    if physical.mass_per_length_kg_m is not None:
        physical_rows.append(PresentationRow(
            "Massa linear", format_engineering_value(
                physical.mass_per_length_kg_m, 1.0, "kg/m",
                3 if is_solid else (2 if is_ue else 1),
            ),
            ("Massa calculada para fixture de desenvolvimento"
             if is_solid and getattr(profile.catalog.source, "source_type", None)
             == "development_fixture" else None),
        ))
    if physical.area_mm2 is not None:
        physical_rows.append(PresentationRow(
            "Área", format_engineering_value(
                physical.area_mm2, 0.01, "cm²", 2 if is_ue or is_solid else 1
            ),
            ("Área técnica calculada; independente da representação CAD"
             if profile.geometry_type == "hollow_section" else None),
        ))
    if physical.surface_area_per_length_m2_m is not None:
        physical_rows.append(PresentationRow(
            "Superfície", format_engineering_value(physical.surface_area_per_length_m2_m, 1.0, "m²/m", 2)
        ))
    groups = [PresentationGroup("Físicas", tuple(physical_rows))]
    property_groups = (
        (("Propriedades geométricas", ("ix", "iy", "wx", "wy", "rx", "ry")),)
        if profile.geometry_type == "hollow_section" else
        (("Eixo X-X", ("ix", "wx", "zx", "rx")),
         ("Eixo Y-Y", ("iy", "wy", "zy", "ry")))
    ) + (("Torção / estabilidade", (
        "rt", "it", "cw", "x0", "r0", "slenderness_flange", "slenderness_web"
    )),)
    for title, keys in property_groups:
        rows = _property_rows(profile, keys)
        if rows:
            groups.append(PresentationGroup(title, rows))
    centroid = []
    if profile.centroid_from_top_flange_face is not None:
        centroid.append(PresentationRow(
            "Distância da face superior ao centroide",
            format_engineering_value(profile.centroid_from_top_flange_face, 0.1, "cm"),
            "Distância vertical oficial Gerdau medida desde a face externa da mesa",
        ))
    elif "x" in profile.centroid:
        centroid.append(PresentationRow(
            "Xg" if is_ue else "x do centroide",
            format_engineering_value(profile.centroid["x"], 0.1, "cm"),
            "Distância do centroide à face externa da alma" if is_ue else None,
        ))
        if (profile.geometry_type, profile.geometry_variant) == ("equal_angle", "equal_leg"):
            centroid.append(PresentationRow(
                "y do centroide",
                format_engineering_value(profile.centroid["x"], 0.1, "cm"),
                "Valor derivado pela simetria da cantoneira de abas iguais",
            ))
        elif "y" in profile.centroid:
            centroid.append(PresentationRow(
                "y do centroide",
                format_engineering_value(profile.centroid["y"], 0.1, "cm"),
            ))
    rz_rows = _property_rows(profile, ("rz_min",))
    centroid.extend(rz_rows)
    if centroid:
        groups.append(PresentationGroup(
            "Centroide" if profile.geometry_type == "hollow_section"
            else "Centroide / propriedades adicionais",
            tuple(centroid),
        ))
    return tuple(group for group in groups if group.rows)


def _compact_catalog_name(profile: ProfileDefinition) -> str:
    name = profile.catalog.source.source_name
    prefix = f"{profile.manufacturer.name} - " if profile.manufacturer else ""
    if name.startswith(prefix):
        name = name[len(prefix):]
    return name.replace(" - ", " — ")


def _source_property_triplet(values) -> str:
    rendered = []
    for key in ("iy", "wy", "ry"):
        label, scale, unit, _tooltip = _PROPERTY_SPECS[key]
        rendered.append(f"{label} {format_engineering_value(values[key], scale, unit)}")
    return " · ".join(rendered)


def profile_source_groups(profile: ProfileDefinition) -> tuple[PresentationGroup, ...]:
    """Build compact operational source summaries from complete catalog data."""
    source = profile.catalog.source
    source_tooltip = "\n".join(value for value in (
        source.source_name,
        f"URL: {source.source_url}" if source.source_url else None,
        source.notes,
    ) if value)
    key = (profile.geometry_type, profile.geometry_variant)
    if getattr(source, "source_type", None) == "development_fixture":
        metadata = profile.source_metadata
        density = getattr(metadata, "density_kg_m3", None)
        mass_rows = (
            PresentationRow("Massa linear", "Calculada para a fixture"),
        )
        if density is not None:
            mass_rows += (PresentationRow(
                "Densidade adotada", format_engineering_value(density, 1.0, "kg/m³"),
            ),)
        return (
            PresentationGroup("Fonte", (
                PresentationRow(
                    "Origem", "Steel Structures — fixture de desenvolvimento", source_tooltip,
                ),
                PresentationRow("Escopo", "Dados sintéticos para validação funcional"),
            ) + mass_rows),
            PresentationGroup("Geometria", (
                PresentationRow("Definição", "Seção maciça nominal ideal", profile.geometry_notes),
                PresentationRow("Propriedades", "Calculadas pela Steel Structures nos eixos locais"),
            )),
        )
    if profile.geometry_type == "hollow_section" and profile.property_provenance:
        provenance = profile.property_provenance.get("area")
        calculated_rows = (
            PresentationRow("Tipo das propriedades", "Calculadas pela Steel Structures"),
            PresentationRow(
                "Convenção de cálculo",
                provenance.calculation_convention if provenance else "Calculada",
                provenance.note if provenance else None,
            ),
            PresentationRow(
                "Escopo", "Propriedades geométricas; não certificação do produto"
            ),
        )
    else:
        calculated_rows = ()
    if key == ("cold_formed_channel", "stiffened_u"):
        return (
            PresentationGroup("Fonte", (
                PresentationRow("Organismo", "ABNT", source_tooltip),
                PresentationRow("Norma", "ABNT NBR 6355"),
                PresentationRow("Edição", "2012"),
                PresentationRow("Anexo", "A — informativo"),
                PresentationRow("Figura", "A.3"),
                PresentationRow("Tabela", "A.3"),
                PresentationRow("Condição", "Aço sem revestimento"),
            )),
            PresentationGroup("Geometria", (
                PresentationRow("Definição", "Perfil U enrijecido formado a frio", profile.geometry_notes),
                PresentationRow("Propriedades", "Seção bruta — método linear normativo"),
            )),
        )
    source_rows = []
    if profile.manufacturer is not None:
        source_rows.append(PresentationRow("Fabricante", profile.manufacturer.name))
    if profile.catalog.issuer is not None:
        source_rows.append(PresentationRow("Organismo", profile.catalog.issuer.name))
    source_rows.append(PresentationRow("Catálogo", _compact_catalog_name(profile), source_tooltip))
    if source.source_revision:
        source_rows.append(PresentationRow("Revisão", source.source_revision))
    if profile.equivalent_designation:
        source_rows.append(PresentationRow("Designação imperial", profile.equivalent_designation))
    if profile.catalog_markers:
        source_rows.append(PresentationRow(
            "Marcadores do catálogo", ", ".join(profile.catalog_markers)
        ))
    if profile.availability_status == "made_to_order":
        source_rows.append(PresentationRow("Disponibilidade", "Sob encomenda"))
    elif profile.availability_status == "consultation":
        source_rows.append(PresentationRow("Disponibilidade", "Sob consulta"))
    if profile.source_metadata is not None:
        metadata = profile.source_metadata
        if metadata.source_page is not None:
            source_rows.append(PresentationRow("Página da fonte", str(metadata.source_page)))
        if metadata.source_weight_p_kg_per_6m is not None:
            source_rows.append(PresentationRow(
                "Peso publicado p (barra de 6 m)",
                format_engineering_value(metadata.source_weight_p_kg_per_6m, 1.0, "kg/6 m", 3),
                "Massa linear do perfil calculada como p/6",
            ))
        if metadata.source_designation:
            source_rows.append(PresentationRow("Designação na fonte", metadata.source_designation))
        if metadata.source_inches:
            source_rows.append(PresentationRow("Designação em polegadas", metadata.source_inches))
    if profile.catalog.supply_condition_definitions:
        for condition in profile.catalog.supply_condition_definitions:
            availability = (
                "condição normal" if condition.availability == "normal"
                else "condição especial sob consulta"
            )
            source_rows.append(PresentationRow(
                f"Condição geral {condition.code}",
                f"{condition.description} — {availability}",
                f"Glossário geral do catálogo, página {condition.source_page}; não atribuído automaticamente a este perfil.",
            ))
    if profile.geometry_type == "i_section" and profile.geometry_variant == "parallel_flange":
        if profile.catalog.standard_references:
            source_rows.append(PresentationRow(
                "Normas", "; ".join(profile.catalog.standard_references)
            ))
        if profile.catalog.material_notes:
            source_rows.append(PresentationRow(
                "Material", "ASTM A572 Grau 50", profile.catalog.material_notes
            ))

    geometry_rows = []
    notes = profile.geometry_notes
    if key == ("i_section", "parallel_flange"):
        geometry_rows.append(PresentationRow(
            "Definição", "Contorno nominal sem raio R", notes
        ))
    elif key == ("i_section", "tapered_flange"):
        dimensions = profile.geometry
        geometry_rows.extend((
            PresentationRow("Origem", "BIM oficial Gerdau — Revit", notes),
            PresentationRow(
                "Definição",
                f"SA {format_number(dimensions['flange_angle'])}° · "
                f"r1 {format_number(dimensions['r1'])} mm · "
                f"r2 {format_number(dimensions['r2'])} mm · TL por tipo",
                notes,
            ),
            PresentationRow(
                "Referência CAD", "DWG não utilizado na geometria estrutural", notes
            ),
        ))
    elif key == ("channel_section", "tapered_flange"):
        dimensions = profile.geometry
        geometry_rows.extend((
            PresentationRow("Origem", "BIM oficial Gerdau — Revit", notes),
            PresentationRow(
                "Definição",
                f"SA {format_number(dimensions['flange_angle'])}° · "
                f"r1 {format_number(dimensions['r1'])} mm · "
                f"r2 {format_number(dimensions['r2'])} mm",
                notes,
            ),
        ))
    elif key == ("equal_angle", "equal_leg"):
        geometry_rows.append(PresentationRow(
            "Definição", "Contorno nominal sem raios", notes
        ))
    elif key == ("tee_section", "standard_tee"):
        geometry_rows.extend((
            PresentationRow("Definição", "Seção nominal retangular", notes),
            PresentationRow("Concordância", "Não parametrizada na fonte", notes),
        ))

    technical_rows = []
    if profile.geometry_status == "pending_technical_review":
        technical_rows.extend((
            PresentationRow("Status", "Geometria em revisão técnica", notes),
            PresentationRow("Motivo", "Inconsistência entre fontes Gerdau", notes),
        ))
    override = profile.section_property_override
    if override is not None:
        technical_rows.extend((
            PresentationRow("Usado", _source_property_triplet(profile.section_properties)),
            PresentationRow(
                "Publicado", _source_property_triplet(profile.reported_section_properties)
            ),
            PresentationRow(
                "Status", "Propriedades efetivas calculadas da geometria nominal Revit",
                override.note,
            ),
            PresentationRow(
                "Confirmação", "Aguardando eventual esclarecimento da Gerdau",
                override.note,
            ),
        ))
    if profile.ref.profile_id == "t-0.875x0.125":
        technical_rows.extend((
            PresentationRow("Iy publicado", "0,33 cm⁴"),
            PresentationRow("Iy geométrico nominal", "aprox. 0,296 cm⁴"),
            PresentationRow(
                "Status", "Incompatibilidade conhecida; aguardando esclarecimento oficial",
                notes,
            ),
        ))

    groups = [PresentationGroup("Fonte", tuple(source_rows) + calculated_rows)]
    if geometry_rows:
        groups.append(PresentationGroup("Geometria", tuple(geometry_rows)))
    if technical_rows:
        title = (
            "Observação técnica — eixo Y-Y"
            if override is not None or profile.ref.profile_id == "t-0.875x0.125"
            else "Observação técnica"
        )
        groups.append(PresentationGroup(title, tuple(technical_rows)))
    return tuple(groups)


def profile_source_rows(profile: ProfileDefinition) -> tuple[PresentationRow, ...]:
    """Compatibility flattening for non-widget consumers."""
    return tuple(row for group in profile_source_groups(profile) for row in group.rows)


def profile_basic_rows(profile: ProfileDefinition, series_name: str) -> tuple[PresentationRow, ...]:
    rows = [PresentationRow("Série", series_name)]
    if profile.manufacturer is not None:
        rows.append(PresentationRow("Fabricante", profile.manufacturer.name))
    elif profile.catalog.issuer is not None:
        rows.append(PresentationRow("Organismo", profile.catalog.issuer.name))
    return tuple(rows)


__all__ = [
    "PresentationGroup", "PresentationRow", "format_engineering_value", "format_number",
    "profile_basic_rows", "profile_dimension_rows", "profile_preview_dimension_rows",
    "profile_property_groups", "profile_source_groups", "profile_source_rows",
]
