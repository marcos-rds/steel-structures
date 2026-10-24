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


def dot(a, b):
    return sum(x*y for x, y in zip(a, b))


def subtract(a, b):
    return tuple(x-y for x, y in zip(a, b))


def _point(value):
    result = tuple(float(v) for v in value)
    if len(result) != 3 or not all(math.isfinite(v) for v in result):
        raise MiterValidationError("O eixo contém coordenadas inválidas.")
    return result


def resolve_miter(start_a, end_a, start_b, end_b):
    """Resolve terminal rays only; never turn an interior T/crossing into an end."""
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
    ends, inward = [], []
    stations = (ta, tb)
    for axis, station in zip(axes, stations):
        if station <= tolerance:
            end, direction = "Start", axis.direction
        elif station >= axis.length-tolerance:
            end, direction = "End", tuple(-d for d in axis.direction)
        else:
            raise MiterValidationError(
                "Interseção no interior de um membro; aparo de ponta não suportado.")
        ends.append(end)
        inward.append(direction)
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
    return MiterPlan(point, normal, tuple(ends), stations, tuple(inward), angle, tolerance)
