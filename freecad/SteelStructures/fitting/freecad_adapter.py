"""FreeCAD adapter applying pure plans through StructuralMember end adjustments."""

import json
import FreeCAD as App

from .models import FitActionMode, PhysicalFitMode
from .serialization import loads as load_plan
from .precedence import slot_decision


FIELDS = ("AdjustmentMode", "AdjustmentGeometryMode", "AdjustmentGap",
          "FixedReferenceOffset", "FixedPlaneNormal")


def _plain(value):
    if isinstance(value, App.Vector):
        return [float(value.x), float(value.y), float(value.z)]
    if hasattr(value, "Value"):
        return float(value.Value)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return str(value)


def _slot_state(source, prefix):
    return {name: _plain(getattr(source, prefix+name)) for name in FIELDS}


def _local_normal(values, normal):
    start, end = App.Vector(values["StartPoint"]), App.Vector(values["EndPoint"])
    direction = end.sub(start)
    direction.normalize()
    from ..member import _member_frame_rotation
    alignment = _member_frame_rotation(direction)
    roll = App.Rotation(App.Vector(0, 0, 1), float(values["Rotation"]))
    rotation = alignment.multiply(roll)
    return rotation.inverted().multVec(App.Vector(*normal))


def _desired(values, action):
    prefix = action.end.value
    result = {
        prefix+"AdjustmentMode": "Fixed",
        prefix+"AdjustmentGeometryMode": action.mode.value,
        prefix+"AdjustmentGap": float(action.gap),
        prefix+"FixedReferenceOffset": float(action.reference_offset),
        prefix+"FixedPlaneNormal": App.Vector(),
    }
    if action.mode == FitActionMode.PLANE_CUT:
        result[prefix+"FixedPlaneNormal"] = _local_normal(values, action.plane_normal)
    return result


def fitting_inputs(item, child, values):
    """Merge auto-fit with current inputs; a changed prior snapshot is manual."""
    if item.physical_fit_plan is None:
        return values, None, None, ""
    plan = load_plan(json.dumps(item.physical_fit_plan, ensure_ascii=False))
    previous = {}
    if child is not None and getattr(child, "PhysicalFitAutoState", ""):
        try:
            previous = json.loads(child.PhysicalFitAutoState)
        except (TypeError, ValueError):
            previous = {}
    merged = dict(values)
    next_state = {}
    messages = [diagnostic.message for diagnostic in plan.diagnostics]
    invalid = any(d.severity == "Warning" for d in plan.diagnostics)
    actions = {"Start": plan.start_action, "End": plan.end_action}
    for prefix, action in actions.items():
        previous_slot = previous.get(prefix)
        current_mode = str(getattr(child, prefix+"AdjustmentMode")) if child is not None else "None"
        current_state = _slot_state(child, prefix) if child is not None else {}
        decision = slot_decision(
            action_present=action is not None, plan_is_none=plan.mode == PhysicalFitMode.NONE,
            invalid_plan=invalid, current_mode=current_mode, current_state=current_state,
            previous_auto_state=previous_slot,
        )
        if action is not None:
            if decision == "Apply":
                desired = _desired(merged, action)
                merged.update(desired)
                snapshot = {}
                for name in FIELDS:
                    snapshot[name] = _plain(desired[prefix+name])
                next_state[prefix] = snapshot
            elif decision == "ManualBlock":
                messages.append("Ajuste manual existente bloqueia o ajuste físico automático nesta ponta.")
        elif previous_slot:
            if decision == "Preserve":
                next_state[prefix] = previous_slot
            elif decision == "Clear":
                merged[prefix+"AdjustmentMode"] = "None"
            elif decision == "ManualBlock":
                messages.append("Ajuste manual existente bloqueia o ajuste físico automático nesta ponta.")
    state_text = json.dumps(next_state, ensure_ascii=False, sort_keys=True,
                            separators=(",", ":"), allow_nan=False) if next_state else ""
    status = " ".join(dict.fromkeys(messages))
    from .serialization import dumps as dump_plan
    return merged, dump_plan(plan), state_text, status


def attach_prepared_metadata(result, plan_text, state_text, status):
    if plan_text is not None:
        result.PhysicalFitPlan = plan_text
        result.PhysicalFitAutoState = state_text
        result.PhysicalFitStatus = status or "Ajuste físico automático válido."
