"""Pure conversion of a declared topological relation into an end-fit plan."""

import math
from .models import (
    FitAction, FitActionMode, FitDiagnostic, FitEnd, FittingPolicy,
    GeometryReference, PhysicalFitMode, PhysicalFitPlan,
)
from .validation import TOLERANCE, validate_nominal_member, validate_plan, validate_reference


def _sub(a, b):
    return tuple(x-y for x, y in zip(a, b))


def _dot(a, b):
    return sum(x*y for x, y in zip(a, b))


def _cross(a, b):
    return (a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0])


def _unit(value):
    length = math.sqrt(_dot(value, value))
    return None if length <= TOLERANCE else tuple(component/length for component in value)


def _canonical(value):
    result = _unit(value)
    if result is None:
        return None
    first = next((component for component in result if abs(component) > TOLERANCE), 1.0)
    return tuple(-component for component in result) if first < 0 else result


def _selected_end(member, topology_node_key):
    if topology_node_key == member.start_node_key:
        return FitEnd.START
    if topology_node_key == member.end_node_key:
        return FitEnd.END
    raise ValueError("A ponta do membro não pertence ao nó topológico esperado.")


def _plan(member, policy, start_action=None, end_action=None, diagnostics=()):
    plan = PhysicalFitPlan(
        plan_key=f"{member.member_key}:physical-fit",
        member_key=member.member_key,
        run_key=member.run_key,
        mode=policy.mode,
        start_action=start_action,
        end_action=end_action,
        diagnostics=tuple(diagnostics),
    )
    return validate_plan(plan)


def resolve_physical_fit(member, target: GeometryReference | None,
                         policy: FittingPolicy, topology_node_key: str | None = None):
    """Resolve one declared member/target relation without mutating a document."""
    validate_nominal_member(member)
    if member.element_kind != "Component":
        return _plan(member, policy, diagnostics=(FitDiagnostic(
            "NON_PRIMARY", "Info", "Elementos internos da composição não recebem fitting de nó."),))
    if policy.gap < 0 or not math.isfinite(policy.gap):
        raise ValueError("O gap axial deve ser maior ou igual a zero.")
    if policy.mode == PhysicalFitMode.NONE:
        return _plan(member, policy)
    if policy.mode in (PhysicalFitMode.GUSSET_AWARE, PhysicalFitMode.CUSTOM):
        return _plan(member, policy, diagnostics=(FitDiagnostic(
            "MODE_NOT_IMPLEMENTED", "Warning", "Este modo de ajuste físico ainda não está implementado."),))
    if policy.mode != PhysicalFitMode.TO_CHORD:
        raise ValueError("Modo de fitting físico inválido.")
    if target is None:
        return _plan(member, policy, diagnostics=(FitDiagnostic(
            "MISSING_REFERENCE", "Warning", "Banzo de referência não encontrado; ajuste físico não aplicado."),))
    validate_reference(target)
    if topology_node_key is None:
        raise ValueError("ToChord requer o nó topológico declarado.")
    selected = _selected_end(member, topology_node_key)
    member_direction = _unit(_sub(member.end, member.start))
    if target.kind in ("Plane", "Face"):
        plane_normal = _canonical(target.normal)
    else:
        # A Line reference carries the truss-plane normal in ``normal``.
        if target.normal is None:
            raise ValueError("A linha do banzo requer a normal do plano da treliça.")
        plane_normal = _canonical(_cross(target.direction, target.normal))
    if plane_normal is None:
        return _plan(member, policy, diagnostics=(FitDiagnostic(
            "DEGENERATE_PLANE", "Warning", "Plano de fitting degenerado; ajuste físico não aplicado."),))
    incidence = abs(_dot(member_direction, plane_normal))
    diagnostics = []
    reference_offset = 0.0
    if incidence <= TOLERANCE:
        return _plan(member, policy, diagnostics=(FitDiagnostic(
            "MEMBER_PARALLEL_TO_PLANE", "Warning",
            "O membro é paralelo ao plano de fitting; último ajuste físico válido preservado."),))
    if not policy.prefer_plane_cut or abs(1.0-incidence) <= TOLERANCE:
        action_mode = FitActionMode.LENGTH_LIMIT
    else:
        action_mode = FitActionMode.PLANE_CUT
    intersection_parameter = (_dot(plane_normal, _sub(target.origin, member.start))
                              / _dot(plane_normal, member_direction))
    reference_offset = (intersection_parameter if selected == FitEnd.START
                        else math.dist(member.start, member.end)-intersection_parameter)
    action = FitAction(
        end=selected, mode=action_mode, reference_key=target.reference_key,
        gap=float(policy.gap), reference_offset=reference_offset,
        plane_origin=tuple(target.origin) if action_mode == FitActionMode.PLANE_CUT else None,
        plane_normal=plane_normal if action_mode == FitActionMode.PLANE_CUT else None,
        source=policy.source,
    )
    return _plan(member, policy,
                 start_action=action if selected == FitEnd.START else None,
                 end_action=action if selected == FitEnd.END else None,
                 diagnostics=diagnostics)
