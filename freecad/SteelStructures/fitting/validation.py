"""Validation shared by fitting resolvers and persistence adapters."""

import math
from .models import FIT_PLAN_SCHEMA_VERSION, FitActionMode, FitEnd, PhysicalFitPlan


TOLERANCE = 1e-7


def _finite_vector(value):
    return (value is not None and len(value) == 3
            and all(math.isfinite(float(component)) for component in value))


def validate_nominal_member(member):
    if not member.member_key or not member.run_key:
        raise ValueError("O membro de fitting requer identidades estáveis.")
    if not _finite_vector(member.start) or not _finite_vector(member.end):
        raise ValueError("O eixo nominal do membro deve ter coordenadas finitas.")
    if math.dist(member.start, member.end) <= TOLERANCE:
        raise ValueError("O eixo nominal do membro é degenerado.")
    if member.start_node_key == member.end_node_key:
        raise ValueError("O eixo nominal não pode referenciar o mesmo nó nas duas pontas.")


def validate_reference(reference):
    if not reference.reference_key or not _finite_vector(reference.origin):
        raise ValueError("A referência de fitting é inválida.")
    if reference.kind in ("Line", "Edge"):
        if not _finite_vector(reference.direction) or math.sqrt(sum(v*v for v in reference.direction)) <= TOLERANCE:
            raise ValueError("A linha de referência é degenerada.")
    elif reference.kind in ("Plane", "Face"):
        if not _finite_vector(reference.normal) or math.sqrt(sum(v*v for v in reference.normal)) <= TOLERANCE:
            raise ValueError("A normal do plano de referência é degenerada.")
    else:
        raise ValueError("Tipo de referência de fitting não suportado.")


def validate_plan(plan: PhysicalFitPlan):
    if plan.schema_version != FIT_PLAN_SCHEMA_VERSION:
        raise ValueError("Versão de PhysicalFitPlan não suportada.")
    if not plan.plan_key or not plan.member_key or not plan.run_key:
        raise ValueError("PhysicalFitPlan requer identidades estáveis.")
    for expected, action in ((FitEnd.START, plan.start_action), (FitEnd.END, plan.end_action)):
        if action is None:
            continue
        if action.end != expected:
            raise ValueError("A ação de fitting foi atribuída à ponta incorreta.")
        if not math.isfinite(action.gap) or action.gap < 0:
            raise ValueError("O gap axial deve ser maior ou igual a zero.")
        if action.reference_key == plan.member_key:
            raise ValueError("Uma referência de fitting não pode ser circular.")
        if action.mode == FitActionMode.PLANE_CUT:
            if not _finite_vector(action.plane_origin) or not _finite_vector(action.plane_normal):
                raise ValueError("PlaneCut requer origem e normal finitas.")
            if math.sqrt(sum(v*v for v in action.plane_normal)) <= TOLERANCE:
                raise ValueError("A normal de PlaneCut é degenerada.")
    return plan
