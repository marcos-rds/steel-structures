"""Resolve nominal axes without changing topology, documents or endpoint fits."""
import math
from .models import (AssemblyRealization, ComponentRealization,
                     RegenerationAction, RegenerationPlan)
from .validation import validate_spec, validate_frame, vector, unit


def resolve_logical_member(item, assembly_spec):
    """Bridge from a nominal run realization, preserving its existing frame.

    Does not mutate the item, TopologyGraph, run keys, Span or Height. Component
    transforms in the assembly spec are authoritative (no implicit extra roll).
    """
    from .models import MemberFrame
    axis = (item.start_global, item.end_global)
    return resolve_member_assembly(axis, MemberFrame.from_axis(axis, item.section_u_global), assembly_spec)


def resolve_member_assembly(nominal_axis, member_frame, assembly_spec):
    validate_spec(assembly_spec)
    validate_frame(member_frame)
    a, b = (vector(p) for p in nominal_axis)
    w = unit(tuple(y-x for x, y in zip(a, b)))
    if math.dist(w, member_frame.w) > 1e-8:
        raise ValueError("Frame longitudinal diverge do eixo nominal.")
    items = []
    for c in assembly_spec.components:
        dx, dy = c.transverse_translation
        shift = tuple(dx*u+dy*v for u, v in zip(member_frame.u, member_frame.v))
        items.append(ComponentRealization(
            (assembly_spec.assembly_key, c.component_key), c.component_key, c.profile_ref,
            tuple(x+d for x, d in zip(a, shift)), tuple(x+d for x, d in zip(b, shift)),
            member_frame, c.insertion_reference, c.section_transform, c.section_geometry_mode, c.color))
    from .interconnectors import resolve_interconnectors
    interconnectors, distributions = resolve_interconnectors((a, b), tuple(items), assembly_spec)
    return AssemblyRealization(assembly_spec, (a, b), member_frame, tuple(items), interconnectors, distributions)


def plan_regeneration(candidate, applied=None, bindings=None, conflicts=None):
    """C1/C2 action vocabulary; independent of truss topology and its schema."""
    before = {c.stable_identity: c for c in applied.elements} if applied else {}
    after = {c.stable_identity: c for c in candidate.elements}
    bindings, conflicts = bindings or {}, conflicts or {}
    actions = []
    for key in sorted(before.keys() | after.keys()):
        action = ("CONFLICT" if key in conflicts else "REMOVE_EXISTING" if key not in after
                  else "CREATE_NEW" if key not in before else "UNCHANGED" if before[key] == after[key]
                  else "UPDATE_EXISTING")
        actions.append(RegenerationAction(key, action, bindings.get(key, ""), conflicts.get(key, "")))
    structural = (applied is None or before.keys() != after.keys()
                  or applied.spec.behavior_mode != candidate.spec.behavior_mode)
    return RegenerationPlan(tuple(actions), structural)
