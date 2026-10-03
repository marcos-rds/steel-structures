"""FreeCAD adapter applying pure plans through StructuralMember end adjustments."""

import json
import FreeCAD as App

from .models import FitActionMode, PhysicalFitMode
from .serialization import loads as load_plan
from .precedence import slot_decision, same_auto_state


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


def automatic_state(child):
    """Read provenance, recovering old lost slots only from their persisted plan.

    Early C5-B compared serialized normals exactly and discarded the snapshot
    on roundoff. Recovery requires every actual input to match that same saved
    automatic action; a user reference or changed cut never qualifies.
    This is a read-only classification, including during regeneration planning.
    """
    try:
        previous = json.loads(getattr(child, "PhysicalFitAutoState", "") or "{}")
        text = getattr(child, "PhysicalFitPlan", "")
        plan = load_plan(text) if text else None
    except (ValueError, TypeError):
        return {}
    if plan is None:
        return previous
    for action in (plan.start_action, plan.end_action):
        if action is None or action.source.value not in ("AutoFit", "ConnectionIntent"):
            continue
        prefix = action.end.value
        if prefix in previous or getattr(child, prefix+"AdjustmentReference", None):
            continue
        constraints = (action,) + tuple(a for a in plan.additional_actions if a.end == action.end)
        effective = max(constraints, key=lambda a: a.reference_offset+a.gap)
        values = {name: getattr(child, name) for name in ("StartPoint", "EndPoint", "Rotation")}
        values["Rotation"] = _plain(values["Rotation"])
        desired = _desired(values, effective)
        expected = {name: _plain(desired[prefix+name]) for name in FIELDS}
        if same_auto_state(_slot_state(child, prefix), expected):
            previous[prefix] = expected
    return previous


def has_manual_adjustment(child):
    """Recognize exact automatic provenance; changed fields/refs remain manual."""
    previous = automatic_state(child)
    for prefix in ("Start", "End"):
        if str(getattr(child, prefix+"AdjustmentMode", "None")) == "None":
            continue
        if (getattr(child, prefix+"AdjustmentReference", None)
                or not same_auto_state(_slot_state(child, prefix), previous.get(prefix))):
            return True
    return False


def composed_plane_cuts(obj, placement):
    """Feed composed automatic planes into the existing finite planar clipper."""
    text = getattr(obj, "PhysicalFitPlan", "")
    if not text:
        return (), set()
    plan = load_plan(text)
    if not plan.additional_actions:
        return (), set()
    from ..member_plane_cut import PlaneCutSpec, global_plane_to_member_local
    previous = automatic_state(obj)
    cuts, ends = [], set()
    axis = obj.EndPoint.sub(obj.StartPoint)
    axis.normalize()
    actions = tuple(a for a in (plan.start_action, plan.end_action) if a) + plan.additional_actions
    for action in actions:
        prefix = action.end.value
        if (not same_auto_state(_slot_state(obj, prefix), previous.get(prefix))
                or getattr(obj, prefix+"AdjustmentReference", None)):
            continue
        inward = axis if prefix == "Start" else axis*-1.
        endpoint = obj.StartPoint if prefix == "Start" else obj.EndPoint
        point = endpoint.add(inward*(action.reference_offset+action.gap))
        normal = action.plane_normal if action.mode == FitActionMode.PLANE_CUT else tuple(axis)
        local = global_plane_to_member_local(placement, App.Vector, tuple(point), normal)
        if local is None:
            raise ValueError("Plano composto de extremidade inválido.")
        origin, normal_local = local
        station = sum(a*b for a,b in zip(origin, normal_local))/normal_local[2]
        cuts.append(PlaneCutSpec(prefix, normal_local, origin, station))
        ends.add(prefix)
    return tuple(cuts), ends


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
    previous = automatic_state(child) if child is not None else {}
    merged = dict(values)
    next_state = {}
    messages = [diagnostic.message for diagnostic in plan.diagnostics]
    invalid = any(d.severity == "Warning" for d in plan.diagnostics)
    actions = {"Start": plan.start_action, "End": plan.end_action}
    for prefix, action in actions.items():
        previous_slot = previous.get(prefix)
        current_mode = str(getattr(child, prefix+"AdjustmentMode")) if child is not None else "None"
        current_state = _slot_state(child, prefix) if child is not None else {}
        if child is not None and getattr(child, prefix+"AdjustmentReference", None):
            current_state["ManualReference"] = True
        decision = slot_decision(
            action_present=action is not None, plan_is_none=plan.mode == PhysicalFitMode.NONE,
            invalid_plan=invalid, current_mode=current_mode, current_state=current_state,
            previous_auto_state=previous_slot,
        )
        if action is not None:
            if decision == "Apply":
                constraints = (action,) + tuple(a for a in plan.additional_actions if a.end == action.end)
                effective = max(constraints, key=lambda a: a.reference_offset+a.gap)
                desired = _desired(merged, effective)
                merged.update(desired)
                snapshot = {}
                for name in FIELDS:
                    snapshot[name] = _plain(desired[prefix+name])
                next_state[prefix] = snapshot
            elif decision == "ManualBlock":
                if previous_slot:
                    next_state[prefix] = previous_slot
                messages.append("Ajuste manual existente bloqueia o ajuste físico automático nesta ponta.")
        elif previous_slot:
            if decision == "Preserve":
                next_state[prefix] = previous_slot
            elif decision == "Clear":
                merged[prefix+"AdjustmentMode"] = "None"
            elif decision == "ManualBlock":
                next_state[prefix] = previous_slot
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
