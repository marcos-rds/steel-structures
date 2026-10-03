"""Strict deterministic persistence for PhysicalFitPlan."""

from dataclasses import asdict
import json
from .models import (
    FIT_PLAN_SCHEMA_VERSION, FitAction, FitActionMode, FitDiagnostic, FitEnd,
    FitSource, PhysicalFitMode, PhysicalFitPlan,
)
from .validation import validate_plan


def dumps(plan):
    validate_plan(plan)
    return json.dumps(asdict(plan), ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False)


def _action(value):
    if value is None:
        return None
    value = dict(value)
    value["end"] = FitEnd(value["end"])
    value["mode"] = FitActionMode(value["mode"])
    value["source"] = FitSource(value.get("source", "AutoFit"))
    for key in ("plane_origin", "plane_normal"):
        if value.get(key) is not None:
            value[key] = tuple(value[key])
    return FitAction(**value)


def loads(text):
    value = json.loads(text, parse_constant=lambda token: (_ for _ in ()).throw(ValueError(token)))
    if value.get("schema_version") not in (1, FIT_PLAN_SCHEMA_VERSION):
        raise ValueError("Versão de PhysicalFitPlan não suportada.")
    plan = PhysicalFitPlan(
        plan_key=value["plan_key"], member_key=value["member_key"], run_key=value["run_key"],
        mode=PhysicalFitMode(value["mode"]), start_action=_action(value.get("start_action")),
        end_action=_action(value.get("end_action")),
        diagnostics=tuple(FitDiagnostic(**item) for item in value.get("diagnostics", ())),
        schema_version=value["schema_version"],
        additional_actions=tuple(_action(item) for item in value.get("additional_actions", ())),
    )
    return validate_plan(plan)
