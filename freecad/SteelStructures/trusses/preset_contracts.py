"""Declared geometric contracts, not structural design recommendations."""
from dataclasses import dataclass


@dataclass(frozen=True)
class PresetContract:
    label: str
    minimum_panels: int = 4
    panel_multiple: int = 1
    mandatory: tuple = ()
    internal_nodes: str = "None"
    closure: str = "ParallelEndPostsOrSharedPitchSupports"
    angle_family: str = ""


PRESETS = {
    "Warren": PresetContract("Warren", angle_family="DIAGONAL"),
    "Pratt": PresetContract("Pratt", angle_family="DIAGONAL"),
    "WarrenVerticals": PresetContract("Warren com montantes", angle_family="DIAGONAL"),
    "Howe": PresetContract("Pratt reversa / Howe", angle_family="DIAGONAL"),
    "X": PresetContract("X", internal_nodes="OptionalPanelIntersection", angle_family="DIAGONAL"),
    "K": PresetContract("K", internal_nodes="HalfHeightAtInteriorStations"),
    "Fink": PresetContract("Fink básico", panel_multiple=2, mandatory=("pivot",)),
    "Fan": PresetContract("Fan", panel_multiple=2, mandatory=("pivot",)),
    "KingPost": PresetContract("King Post", panel_multiple=2, mandatory=("pivot",)),
    "QueenPost": PresetContract("Queen Post", minimum_panels=6, panel_multiple=3),
    "Custom": PresetContract("Custom (alma vazia)", closure="ChordsOnly"),
}


def compatible_presets(kind):
    common = ("Warren", "WarrenVerticals", "Pratt", "Howe", "X")
    return common + (("K",) if kind == "Parallel" else
                     ("Fink", "Fan", "KingPost", "QueenPost")) + ("Custom",)


def validate_preset(definition, plan, preset):
    if preset not in compatible_presets(definition.kind):
        raise ValueError("Padrão incompatível com o envelope selecionado.")
    if preset not in PRESETS:
        raise ValueError("Padrão de treliça desconhecido.")
    contract = PRESETS[preset]
    if plan.panel_count < contract.minimum_panels or plan.panel_count % contract.panel_multiple:
        raise ValueError(f"{contract.label}: mínimo {contract.minimum_panels} painéis; múltiplo de {contract.panel_multiple}.")
    for fraction in contract.mandatory:
        if fraction == "pivot":
            fraction = definition.apex_position if definition.kind == "DuoPitch" else .5
        if not any(abs(s.x / definition.span - fraction) <= 1e-8 for s in plan.stations):
            raise ValueError(f"{contract.label}: exige estação em {fraction * 100:g}% do vão.")
