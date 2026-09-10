"""Nominal longitudinal stations, in mm. Count means stations, not bays.

Slots are ordinal identities, never coordinates. Explicit persisted slot keys
can be supplied by a controller. A sole station lies at the usable midpoint;
two or more stations include both offset boundaries. Target spacing uses ceil
to partition the usable length (actual spacing is no larger than the target).
"""
from dataclasses import dataclass
import math
from .validation import finite

LENGTH_TOLERANCE = 1e-8
MAX_STATIONS = 10000  # Resource limit, not a structural design recommendation.


@dataclass(frozen=True)
class DistributionSpec:
    mode: str = "ByCount"
    station_count: int | None = 4
    target_spacing: float | None = None
    station_keys: tuple = ()

    def __post_init__(self):
        object.__setattr__(self, "station_keys", tuple(self.station_keys))
        if self.mode not in ("ByCount", "ByTargetSpacing"):
            raise ValueError("Modo de distribuição não suportado.")
        if self.mode == "ByCount":
            if type(self.station_count) is not int or not 1 <= self.station_count <= MAX_STATIONS:
                raise ValueError("Quantidade de estações deve ser um inteiro positivo dentro do limite de geração.")
            if self.target_spacing is not None:
                raise ValueError("Distribuição por quantidade não aceita espaçamento alvo residual.")
        elif (self.station_count is not None or not finite(self.target_spacing)
              or self.target_spacing <= 0):
            raise ValueError("Distribuição por espaçamento requer espaçamento positivo e quantidade automática.")
        if (any(not isinstance(k, str) or not k.strip() for k in self.station_keys)
                or len(set(self.station_keys)) != len(self.station_keys)):
            raise ValueError("Chaves de estação devem ser únicas e não vazias.")


@dataclass(frozen=True)
class LongitudinalStation:
    key: str
    position: float


@dataclass(frozen=True)
class StationDistribution:
    stations: tuple
    effective_length: float
    effective_spacing: float
    effective_count: int
    messages: tuple = ()


def resolve_stations(nominal_length, distribution, start_offset=0., end_offset=0., *, minimum_count=1):
    if not isinstance(distribution, DistributionSpec):
        raise ValueError("Distribuição de estações inválida.")
    if (not finite(nominal_length) or nominal_length <= LENGTH_TOLERANCE
            or any(not finite(v) or v < 0 for v in (start_offset, end_offset))):
        raise ValueError("Comprimento nominal e afastamentos devem ser finitos; afastamentos não podem ser negativos.")
    length = nominal_length-start_offset-end_offset
    if length <= LENGTH_TOLERANCE:
        raise ValueError("Os afastamentos não deixam comprimento útil para interconectores.")
    if distribution.mode == "ByCount":
        count = distribution.station_count
    else:
        ratio = length/distribution.target_spacing
        if not math.isfinite(ratio) or ratio > MAX_STATIONS-1:
            raise ValueError("Espaçamento gera estações demais; aumente o espaçamento alvo.")
        count = max(1, math.ceil(ratio))+1
    if count < minimum_count:
        raise ValueError("Treliçamento requer pelo menos duas estações para formar um intervalo.")
    keys = distribution.station_keys or tuple(f"S{i:04d}" for i in range(count))
    if len(keys) != count:
        raise ValueError("Quantidade de chaves de estação diverge da distribuição; revise os slots persistidos.")
    spacing = length/(count-1) if count > 1 else 0.
    stations = tuple(LongitudinalStation(key, start_offset+i*spacing if count > 1
                                        else start_offset+length/2) for i, key in enumerate(keys))
    message = ("Estação única no meio do comprimento útil.",) if count == 1 else ()
    return StationDistribution(stations, length, spacing, count, message)
