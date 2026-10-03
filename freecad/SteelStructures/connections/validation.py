"""Validation for pure connection-intent values."""

import math

from .models import CONNECTION_INTENT_SCHEMA_VERSION, ConnectionIntent


def validate_intent(intent: ConnectionIntent):
    if intent.schema_version != CONNECTION_INTENT_SCHEMA_VERSION:
        raise ValueError("Versão de ConnectionIntent não suportada.")
    if not intent.intent_key or not intent.node_key:
        raise ValueError("ConnectionIntent requer identidades estáveis.")
    if not isinstance(intent.priority_run_key, str):
        raise ValueError("A prioridade deve identificar um participante por chave estável.")
    if len(set(intent.participant_run_keys)) != len(intent.participant_run_keys):
        raise ValueError("Participantes da ligação não podem ser duplicados.")
    for name, value in (("espessura da chapa", intent.gusset.plate_thickness),
                        ("clearance normal", intent.gusset.normal_clearance),
                        ("clearance axial", intent.gusset.axial_clearance),
                        ("margem de borda", intent.gusset.edge_margin),
                        ("sobreposição nos membros", intent.gusset.member_overlap)):
        if not math.isfinite(value) or value < 0:
            raise ValueError(name.capitalize()+" deve ser finito e maior ou igual a zero.")
    return intent
