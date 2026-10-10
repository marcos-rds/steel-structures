# SPDX-License-Identifier: LGPL-2.1-or-later
"""Pure point coordinate conversion; all lengths are normalized to mm by the UI.

No editor, plane discovery, projection or point confirmation lives here.
"""
from dataclasses import dataclass
from enum import Enum
import math


class CoordinateReference(Enum):
    GLOBAL = "Global"
    PLANE = "Plano"


class CoordinateMode(Enum):
    ABSOLUTE = "Absoluto"
    RELATIVE = "Relativo"


def coordinates(values, count=3):
    try:
        result = tuple(float(value) for value in values)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("Coordenadas inválidas.") from exc
    if len(result) != count or not all(math.isfinite(value) for value in result):
        raise ValueError("Informe todas as coordenadas com valores finitos.")
    return result


@dataclass(frozen=True)
class PointCandidate:
    """One unconfirmed world-space 3D point, never persistent geometry."""
    world: tuple

    def __post_init__(self):
        object.__setattr__(self, "world", coordinates(self.world))


@dataclass(frozen=True)
class PointInputPlane:
    """Immutable orthonormal frame copied from the defined plate Placement."""
    origin: tuple
    u: tuple
    v: tuple
    normal: tuple

    def __post_init__(self):
        for name in ("origin", "u", "v", "normal"):
            object.__setattr__(self, name, coordinates(getattr(self, name)))

    def vector(self, uv):
        return coordinates(a * uv[0] + b * uv[1] for a, b in zip(self.u, self.v))

    def local(self, world):
        delta = tuple(a - b for a, b in zip(world, self.origin))
        return coordinates(sum(a * b for a, b in zip(delta, axis))
                           for axis in (self.u, self.v, self.normal))


@dataclass(frozen=True)
class PointInputSpec:
    reference: CoordinateReference = CoordinateReference.GLOBAL
    mode: CoordinateMode = CoordinateMode.ABSOLUTE

    @property
    def component_count(self):
        return 3 if self.reference == CoordinateReference.GLOBAL else 2

    def validate_context(self, plane, last_point):
        if (not isinstance(self.reference, CoordinateReference)
                or not isinstance(self.mode, CoordinateMode)):
            raise ValueError("Sistema de coordenadas inválido.")
        if self.reference == CoordinateReference.PLANE and plane is None:
            raise ValueError("O plano da chapa ainda não foi definido.")
        if self.mode == CoordinateMode.RELATIVE and last_point is None:
            raise ValueError("O modo relativo exige um ponto anterior.")

    def candidate(self, values, *, plane=None, last_point=None):
        self.validate_context(plane, last_point)
        values = coordinates(values, self.component_count)
        relative = self.mode == CoordinateMode.RELATIVE
        if self.reference == CoordinateReference.GLOBAL:
            vector = values
            origin = coordinates(last_point) if relative else (0, 0, 0)
        else:
            vector = plane.vector(values)
            origin = coordinates(last_point) if relative else plane.origin
        return PointCandidate(tuple(a + b for a, b in zip(origin, vector)))

    def present(self, candidate, *, plane=None, last_point=None, tolerance=1e-5):
        """Re-express a candidate without reinterpreting numbers or projecting it."""
        self.validate_context(plane, last_point)
        world = candidate.world
        if self.reference == CoordinateReference.PLANE:
            if abs(plane.local(world)[2]) > tolerance:
                raise ValueError("O ponto está fora do plano da chapa.")
        if self.mode == CoordinateMode.RELATIVE:
            delta = tuple(a - b for a, b in zip(world, coordinates(last_point)))
            if self.reference == CoordinateReference.GLOBAL:
                return coordinates(delta)
            return tuple(sum(a * b for a, b in zip(delta, axis))
                         for axis in (plane.u, plane.v))
        if self.reference == CoordinateReference.GLOBAL:
            return world
        return plane.local(world)[:2]
