"""Piecewise linear envelopes; DuoPitch has shared, zero-height supports."""
import math


def validate_envelope(definition):
    if definition.kind not in ("Parallel", "DuoPitch"):
        raise ValueError("Forma de treliça não suportada no C1.")
    if not all(math.isfinite(v) and v > 0 for v in (definition.span, definition.height)):
        raise ValueError("Vão e altura devem ser positivos e finitos.")
    if not math.isfinite(definition.apex_position) or not 0 < definition.apex_position < 1:
        raise ValueError("Posição do ápice deve estar entre 0 e 1.")


def paths(definition):
    validate_envelope(definition)
    span, height = definition.span, definition.height
    bottom = ((0., 0., 0.), (span, 0., 0.))
    top = (((0., height, 0.), (span, height, 0.)) if definition.kind == "Parallel"
           else ((0., 0., 0.), (span * definition.apex_position, height, 0.), (span, 0., 0.)))
    return {"top": top, "bottom": bottom}


def top_height(definition, x):
    if definition.kind == "Parallel":
        return definition.height
    apex = definition.span * definition.apex_position
    if x <= apex:
        return definition.height * x / apex
    return definition.height * (definition.span - x) / (definition.span - apex)
