# SPDX-License-Identifier: LGPL-2.1-or-later
"""Pure endpoint encounter for a fixed, separating common-plane miter."""
from dataclasses import dataclass
import math

from .member_adjustment_geometry import axis_geometry


class MiterValidationError(ValueError):
    """A pair outside the deliberately restricted miter domain."""


@dataclass(frozen=True)
class MiterPlan:
    point: tuple
    normal: tuple
    ends: tuple
    stations: tuple
    inward: tuple
    angle_degrees: float
    length_tolerance: float
    trim_lengths: tuple = (0., 0.)


@dataclass(frozen=True)
class MiterEncounter:
    point: tuple
    stations: tuple
    axes: tuple
    automatic_ends: tuple
    length_tolerance: float

    def excess(self, index, end):
        if end not in ("Start", "End"):
            raise MiterValidationError("Escolha Início ou Fim para o aparo.")
        station = self.stations[index]
        return max(0., station if end == "Start" else self.axes[index].length-station)


def dot(a, b):
    return sum(x*y for x, y in zip(a, b))


def subtract(a, b):
    return tuple(x-y for x, y in zip(a, b))


def _point(value):
    result = tuple(float(v) for v in value)
    if len(result) != 3 or not all(math.isfinite(v) for v in result):
        raise MiterValidationError("O eixo contém coordenadas inválidas.")
    return result


def inspect_miter(start_a, end_a, start_b, end_b):
    """Intersect support axes without assigning intent to an interior encounter."""
    points = tuple(_point(p) for p in (start_a, end_a, start_b, end_b))
    axes = (axis_geometry(*points[:2]), axis_geometry(*points[2:]))
    if any(a is None for a in axes):
        raise MiterValidationError("O membro possui eixo nominal nulo.")
    if any(not all(math.isfinite(v) for v in (a.length, *a.direction)) for a in axes):
        raise MiterValidationError("Eixos com escala numérica inválida para o encontro.")
    a, b = axes
    scale = max(a.length, b.length, 1.)
    # mm: 100× the kernel's usual 1e-7 floor, plus relative/input precision.
    tolerance = max(1e-5, scale*1e-9, 32*math.ulp(max(abs(v) for p in points for v in p)))
    if tolerance > min(a.length, b.length)*1e-4:
        raise MiterValidationError("Coordenadas ou comprimentos sem precisão suficiente para o encontro.")
    cosine = dot(a.direction, b.direction)
    denominator = 1.-cosine*cosine
    if denominator <= 1e-12:  # |sin(angle)| <= 1e-6: ill-conditioned intersection.
        raise MiterValidationError("Membros paralelos, colineares ou quase paralelos não são suportados.")
    offset = subtract(b.start, a.start)
    ta = (dot(offset, a.direction)-cosine*dot(offset, b.direction))/denominator
    tb = (cosine*dot(offset, a.direction)-dot(offset, b.direction))/denominator
    qa = tuple(p+ta*d for p, d in zip(a.start, a.direction))
    qb = tuple(p+tb*d for p, d in zip(b.start, b.direction))
    if not all(math.isfinite(v) for v in (ta, tb, *qa, *qb)):
        raise MiterValidationError("Interseção sem precisão numérica suficiente.")
    distance = math.sqrt(dot(subtract(qa, qb), subtract(qa, qb)))
    if distance > tolerance:
        raise MiterValidationError(
            "Os eixos não se encontram no mesmo plano (distância %.6g mm)." % distance)
    point = tuple((x+y)*.5 for x, y in zip(qa, qb))
    ends = []
    stations = (ta, tb)
    for axis, station in zip(axes, stations):
        if station <= tolerance:
            end = "Start"
        elif station >= axis.length-tolerance:
            end = "End"
        else:
            end = None
        ends.append(end)
    return MiterEncounter(point, stations, axes, tuple(ends), tolerance)


def resolve_miter(start_a, end_a, start_b, end_b, *, ends=(None, None), allow_trim=(False, False)):
    """Interior encounters require an explicit retained-side choice AND consent."""
    if len(ends) != 2 or len(allow_trim) != 2:
        raise MiterValidationError("Informe as duas extremidades e autorizações separadamente.")
    encounter = inspect_miter(start_a, end_a, start_b, end_b)
    selected, inward, trims = [], [], []
    for index, (axis, automatic, requested, allowed) in enumerate(
            zip(encounter.axes, encounter.automatic_ends, ends, allow_trim)):
        if automatic is None:
            if requested not in ("Start", "End"):
                raise MiterValidationError(
                    "Interseção no interior do membro %s; escolha a extremidade a aparar e autorize o aparo."
                    % ("A" if index == 0 else "B"))
            end = requested
            if not allowed:
                raise MiterValidationError("Autorize explicitamente o aparo do membro %s, %s."
                    % ("A" if index == 0 else "B", "Início" if end == "Start" else "Fim"))
            trims.append(encounter.excess(index, end))
        else:
            if requested is not None and requested != automatic:
                raise MiterValidationError("A extremidade escolhida inverteria a parte preservada do membro.")
            end = automatic
            trims.append(0.)
        selected.append(end)
        inward.append(axis.direction if end == "Start" else tuple(-d for d in axis.direction))
    delta = subtract(*inward)
    length = math.sqrt(dot(delta, delta))
    if length <= 1e-6:
        raise MiterValidationError("Não há bissetriz separadora estável para estas extremidades.")
    normal = tuple(v/length for v in delta)
    if next((v for v in normal if abs(v) > 1e-12), 1.) < 0:
        normal = tuple(-v for v in normal)
    signs = tuple(dot(normal, direction) for direction in inward)
    if signs[0]*signs[1] >= 0 or min(abs(v) for v in signs) <= 1e-6:
        raise MiterValidationError("Os interiores dos membros não ficam em semiespaços opostos estáveis.")
    angle = math.degrees(math.acos(max(-1., min(1., dot(*inward)))))
    return MiterPlan(encounter.point, normal, tuple(selected), encounter.stations, tuple(inward),
                     angle, encounter.length_tolerance, tuple(trims))
