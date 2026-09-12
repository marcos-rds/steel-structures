"""Pure precedence rules between persisted auto-fit and user adjustments."""


def slot_decision(*, action_present, plan_is_none, invalid_plan,
                  current_mode, current_state, previous_auto_state):
    """Return Apply, Clear, Preserve or ManualBlock for one member end."""
    auto_unchanged = bool(previous_auto_state and current_state == previous_auto_state)
    if action_present:
        if current_mode == "None" or auto_unchanged:
            return "Apply"
        return "ManualBlock"
    if previous_auto_state:
        if invalid_plan:
            return "Preserve"
        if auto_unchanged and plan_is_none:
            return "Clear"
        if not auto_unchanged:
            return "ManualBlock"
    return "Preserve"
