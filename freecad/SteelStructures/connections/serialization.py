"""Strict deterministic serialization for ConnectionIntent."""

from dataclasses import asdict
import json

from .models import (CONNECTION_INTENT_SCHEMA_VERSION, ConnectionForm,
                     ConnectionIntent, DirectFitPolicy, FasteningIntent,
                     GussetAttachmentMode, GussetChordContact, GussetFitSpec,
                     GussetSide, PriorityMember)
from .validation import validate_intent


def dumps(intent):
    validate_intent(intent)
    return json.dumps(asdict(intent), ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False)


def loads(text):
    value = json.loads(text, parse_constant=lambda token: (_ for _ in ()).throw(ValueError(token)))
    if value.get("schema_version") not in (1, 2, 3, CONNECTION_INTENT_SCHEMA_VERSION):
        raise ValueError("Versão de ConnectionIntent não suportada.")
    gusset = dict(value.get("gusset", {}))
    gusset["side"] = GussetSide(gusset.get("side", "Center"))
    gusset["attachment_mode"] = GussetAttachmentMode(
        gusset.get("attachment_mode", "Auto"))
    gusset["chord_contact"] = GussetChordContact(
        gusset.get("chord_contact", "Auto"))
    gusset["transverse_placement"] = gusset.get("transverse_placement", "")
    intent = ConnectionIntent(
        intent_key=value["intent_key"], node_key=value["node_key"],
        form=ConnectionForm(value.get("form", "GeometricOnly")),
        fastening=FasteningIntent(value.get("fastening", "Unspecified")),
        direct_policy=DirectFitPolicy(value.get("direct_policy", "Independent")),
        participant_run_keys=tuple(value.get("participant_run_keys", ())),
        priority_member=PriorityMember(value.get("priority_member", "Automatic")),
        priority_run_key=value.get("priority_run_key", ""),
        gusset=GussetFitSpec(**gusset), schema_version=CONNECTION_INTENT_SCHEMA_VERSION)
    return validate_intent(intent)
