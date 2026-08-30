# SPDX-License-Identifier: LGPL-2.1-or-later
"""Application controller for member end adjustments; no Qt dependencies."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

from ..member_adjustment_geometry import (
    DEFAULT_TOLERANCE,
    axis_geometry,
    closest_point_on_member_axis,
    intersect_infinite_axis_with_plane,
)
from ..member_adjustment_reference import (
    linear_reference_from_link,
    plane_reference_from_link,
    unpack_link_sub,
    would_create_adjustment_cycle,
)
from ..member_plane_cut import global_plane_to_member_local


GEOMETRY_MODES = ("LengthLimit", "PlaneCut")
END_CHOICES = ("Auto", "Start", "End")


class AdjustmentValidationError(ValueError):
    """An anticipated user-correctable adjustment configuration error."""


@dataclass(frozen=True)
class AdjustmentProposal:
    member: object
    geometry_mode: str = "LengthLimit"
    end_choice: str = "Auto"
    gap: float = 0.0
    keep_reference: bool = True
    reference: object = None


@dataclass(frozen=True)
class ResolvedAdjustment:
    member: object
    geometry_mode: str
    adjusted_end: str
    gap: float
    keep_reference: bool
    reference_object: object
    subelement: str
    station: float
    fixed_reference_offset: float
    fixed_plane_normal: tuple[float, float, float] | None
    message: str


def _point(value):
    return float(value.x), float(value.y), float(value.z)


def _quantity(value):
    return float(getattr(value, "Value", value))


def is_structural_member(obj) -> bool:
    proxy = getattr(obj, "Proxy", None)
    return (
        obj is not None
        and getattr(obj, "TypeId", "") == "Part::FeaturePython"
        and proxy is not None
        and proxy.__class__.__name__ == "StructuralMemberProxy"
        and proxy.__class__.__module__.endswith(".member")
    )


def member_display_name(member) -> str:
    label = str(getattr(member, "Label", "") or getattr(member, "Name", "Membro"))
    profile = str(getattr(member, "Profile", "") or "")
    return label if not profile or profile in label else f"{label} — {profile}"


def reference_display_name(reference) -> str:
    unpacked = unpack_link_sub(reference)
    if unpacked is None:
        return "Nenhuma referência selecionada"
    obj, subelement = unpacked
    return f"{getattr(obj, 'Label', getattr(obj, 'Name', 'Objeto'))} — {subelement}"


def _axis(member):
    result = axis_geometry(_point(member.StartPoint), _point(member.EndPoint), DEFAULT_TOLERANCE)
    if result is None:
        raise AdjustmentValidationError("O membro possui eixo nominal nulo.")
    return result


def _reference_geometry(member, reference, geometry_mode):
    unpacked = unpack_link_sub(reference)
    if unpacked is None:
        raise AdjustmentValidationError("Selecione uma Face plana ou uma Edge reta.")
    reference_object, subelement = unpacked
    if would_create_adjustment_cycle(member, reference_object):
        raise AdjustmentValidationError("A referência criaria uma dependência circular.")
    axis = _axis(member)
    if subelement.startswith("Face"):
        plane = plane_reference_from_link(reference)
        if plane is None:
            raise AdjustmentValidationError("A Face selecionada não é plana ou está inválida.")
        point = intersect_infinite_axis_with_plane(
            axis.start, axis.end, plane.point_global, plane.normal_global,
            DEFAULT_TOLERANCE,
        )
        if point is None:
            raise AdjustmentValidationError("O plano é paralelo ao eixo do membro.")
        return reference_object, subelement, point, plane.normal_global, "Face plana selecionada"
    if subelement.startswith("Edge"):
        if geometry_mode == "PlaneCut":
            raise AdjustmentValidationError("Recortar pelo plano exige uma Face plana.")
        line = linear_reference_from_link(reference, DEFAULT_TOLERANCE)
        if line is None:
            raise AdjustmentValidationError("A Edge selecionada não é reta ou está inválida.")
        point = closest_point_on_member_axis(
            axis.start, axis.end, line.point_global, line.direction_global,
            DEFAULT_TOLERANCE,
        )
        if point is None:
            raise AdjustmentValidationError("A aresta é paralela ao eixo do membro.")
        return reference_object, subelement, point, None, "Aresta reta selecionada"
    raise AdjustmentValidationError("Selecione explicitamente uma Face ou Edge.")


def _station(axis, point):
    return sum((float(value) - origin) * direction
               for value, origin, direction in zip(point, axis.start, axis.direction))


def resolve_adjusted_end(axis, station: float, choice: str,
                         tolerance: float = DEFAULT_TOLERANCE) -> str:
    if choice in ("Start", "End"):
        return choice
    if choice != "Auto":
        raise AdjustmentValidationError("Escolha Automático, Início ou Fim.")
    start_distance = abs(float(station))
    end_distance = abs(float(station) - axis.length)
    scale = max(axis.length, abs(float(station)), 1.0)
    if abs(start_distance - end_distance) <= tolerance * scale:
        raise AdjustmentValidationError(
            "Não foi possível determinar a extremidade. Escolha Início ou Fim."
        )
    return "Start" if start_distance < end_distance else "End"


def validate_proposal(proposal: AdjustmentProposal) -> ResolvedAdjustment:
    member = proposal.member
    if not is_structural_member(member):
        raise AdjustmentValidationError("Selecione um membro estrutural.")
    if proposal.geometry_mode not in GEOMETRY_MODES:
        raise AdjustmentValidationError("Tipo de ajuste inválido.")
    if proposal.end_choice not in END_CHOICES:
        raise AdjustmentValidationError("Extremidade inválida.")
    gap = float(proposal.gap)
    if not isfinite(gap):
        raise AdjustmentValidationError("Gap inválido.")
    reference_object, subelement, point, plane_normal, message = _reference_geometry(
        member, proposal.reference, proposal.geometry_mode
    )
    axis = _axis(member)
    station = _station(axis, point)
    adjusted_end = resolve_adjusted_end(axis, station, proposal.end_choice)
    fixed_offset = station if adjusted_end == "Start" else axis.length - station
    fixed_normal = None
    if proposal.geometry_mode == "PlaneCut":
        import FreeCAD as App
        local = global_plane_to_member_local(
            member.Placement, App.Vector, point, plane_normal, DEFAULT_TOLERANCE
        )
        if local is None:
            raise AdjustmentValidationError("Não foi possível converter o plano para o membro.")
        fixed_normal = local[1]
    return ResolvedAdjustment(
        member, proposal.geometry_mode, adjusted_end, gap,
        bool(proposal.keep_reference), reference_object, subelement,
        station, fixed_offset, fixed_normal, message,
    )


def freeze_adjustment_reference(member, reference, geometry_mode, slot,
                                gap=0.0) -> ResolvedAdjustment:
    """Resolve one current reference into a reusable Fixed adjustment state."""
    if slot not in ("Start", "End"):
        raise AdjustmentValidationError("Escolha Início ou Fim para congelar o ajuste.")
    return validate_proposal(AdjustmentProposal(
        member=member, geometry_mode=geometry_mode, end_choice=slot,
        gap=gap, keep_reference=False, reference=reference,
    ))


class MemberAdjustmentController:
    """Validate temporary UI state and mutate one member only inside accept()."""

    def __init__(self, document, member=None):
        self.document = document
        self.member = member if is_structural_member(member) else None

    def set_member(self, member):
        if not is_structural_member(member):
            raise AdjustmentValidationError("Selecione um membro estrutural.")
        self.member = member

    def validate(self, *, geometry_mode, end_choice, gap, keep_reference, reference):
        return validate_proposal(AdjustmentProposal(
            self.member, geometry_mode, end_choice, gap, keep_reference, reference
        ))

    def validate_existing_fixed(self, *, geometry_mode, end_choice, gap):
        obj = self.member
        if end_choice not in ("Start", "End"):
            raise AdjustmentValidationError("Escolha Início ou Fim.")
        prefix = end_choice
        if obj is None or str(getattr(obj, prefix + "AdjustmentMode", "")) != "Fixed":
            raise AdjustmentValidationError("Selecione uma referência geométrica.")
        current_geometry = str(getattr(obj, prefix + "AdjustmentGeometryMode"))
        if geometry_mode != current_geometry:
            raise AdjustmentValidationError(
                "Selecione uma nova referência para alterar o tipo ou a extremidade do ajuste fixo."
            )
        normal = None
        if geometry_mode == "PlaneCut":
            value = getattr(obj, prefix + "FixedPlaneNormal")
            normal = _point(value)
        axis = _axis(obj)
        offset = _quantity(getattr(obj, prefix + "FixedReferenceOffset"))
        station = offset if prefix == "Start" else axis.length - offset
        return ResolvedAdjustment(
            obj, geometry_mode, prefix, float(gap), False,
            None, "", station, offset, normal, "Ajuste fixo",
        )

    def apply(self, resolved: ResolvedAdjustment):
        if resolved.member is not self.member:
            raise AdjustmentValidationError("O membro-alvo foi alterado.")
        doc = self.document
        doc.openTransaction("Recortar / Ajustar membro")
        try:
            obj = resolved.member
            prefix = resolved.adjusted_end
            setattr(obj, prefix + "AdjustmentGeometryMode", resolved.geometry_mode)
            setattr(obj, prefix + "AdjustmentGap", resolved.gap)
            if resolved.keep_reference:
                setattr(obj, prefix + "AdjustmentMode", "Associative")
                setattr(obj, prefix + "AdjustmentReference", (
                    resolved.reference_object, [resolved.subelement]
                ))
            else:
                setattr(obj, prefix + "AdjustmentMode", "Fixed")
                setattr(obj, prefix + "AdjustmentReference", None)
                setattr(obj, prefix + "FixedReferenceOffset", resolved.fixed_reference_offset)
                if resolved.fixed_plane_normal is not None:
                    import FreeCAD as App
                    setattr(obj, prefix + "FixedPlaneNormal", App.Vector(*resolved.fixed_plane_normal))
            doc.recompute()
            shape = getattr(obj, "Shape", None)
            if shape is None or (hasattr(shape, "isNull") and shape.isNull()):
                raise AdjustmentValidationError("O ajuste resultou em geometria vazia.")
            doc.commitTransaction()
        except Exception:
            doc.abortTransaction()
            raise
        return resolved

    def remove_adjustment(self, slot):
        if self.member is None:
            raise AdjustmentValidationError("Selecione um membro estrutural.")
        if slot not in ("Start", "End"):
            raise AdjustmentValidationError("Escolha Início ou Fim para remover o ajuste.")
        self.document.openTransaction("Remover ajuste do membro")
        try:
            setattr(self.member, slot + "AdjustmentMode", "None")
            setattr(self.member, slot + "AdjustmentReference", None)
            self.document.recompute()
            self.document.commitTransaction()
        except Exception:
            self.document.abortTransaction()
            raise


__all__ = [
    "AdjustmentProposal", "AdjustmentValidationError", "END_CHOICES",
    "GEOMETRY_MODES", "MemberAdjustmentController", "ResolvedAdjustment",
    "freeze_adjustment_reference", "is_structural_member", "member_display_name",
    "reference_display_name", "resolve_adjusted_end", "validate_proposal",
]
