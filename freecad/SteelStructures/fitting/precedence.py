"""Pure precedence rules between persisted auto-fit and user adjustments."""

import math


def same_auto_state(current, previous):
    """Allow only serialization/rotation roundoff, never a changed reference."""
    if not previous or current.keys() != previous.keys():
        return False
    for name, value in current.items():
        old = previous[name]
        if name == "FixedPlaneNormal":
            if len(value) != len(old) or any(not math.isclose(a, b, rel_tol=0., abs_tol=1e-12)
                                             for a, b in zip(value, old)):
                return False
        elif value != old:
            return False
    return True


def slot_decision(*, action_present, plan_is_none, invalid_plan,
                  current_mode, current_state, previous_auto_state):
    """Return Apply, Clear, Preserve or ManualBlock for one member end."""
    auto_unchanged = same_auto_state(current_state, previous_auto_state)
    if action_present:
        if current_mode == "None" or auto_unchanged:
            return "Apply"
        return "ManualBlock"
    if previous_auto_state:
        if invalid_plan:
            return "Preserve"
        if auto_unchanged:
            return "Clear"
        if not auto_unchanged:
            return "ManualBlock"
    return "Preserve"
