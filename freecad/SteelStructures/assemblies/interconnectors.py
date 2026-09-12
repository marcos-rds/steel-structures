"""Physical axis-to-axis connectors. No topology, face fitting or global plane.

Battens occupy stations. SingleLacing alternates A->B / B->A across bays;
StartSide refers to the first/second key of component_pair, not list order.
DoubleLacing emits both independent diagonals; crossing is not a node.
"""
from dataclasses import dataclass
import math
from ..profiles.models import ProfileRef
from ..profiles.geometry import SectionGeometryMode
from .transforms import SectionTransform
from .distribution import DistributionSpec, resolve_stations, LENGTH_TOLERANCE
from .validation import finite, unit, cross, vector


@dataclass(frozen=True)
class InterconnectorSpec:
    interconnector_key: str
    kind: str
    component_pair: tuple
    profile_ref: ProfileRef
    section_geometry_mode: SectionGeometryMode = SectionGeometryMode.DETAILED
    section_transform: SectionTransform = SectionTransform()
    insertion_reference: str = "centroid"
    color: tuple = (.65, .75, .65)
    start_offset: float = 0.
    end_offset: float = 0.
    distribution: DistributionSpec = DistributionSpec()
    start_side: str = "A"
    attachment_plane: str = "AxisToAxis"

    def __post_init__(self):
        object.__setattr__(self, "component_pair", tuple(self.component_pair))
        object.__setattr__(self, "color", tuple(self.color))
        object.__setattr__(self, "section_geometry_mode", SectionGeometryMode(self.section_geometry_mode))
        if not isinstance(self.interconnector_key, str) or not self.interconnector_key.strip():
            raise ValueError("Defina uma chave estável para o conjunto de interconectores.")
        if self.kind not in ("None", "SpacerPlate", "Battens", "SingleLacing", "DoubleLacing"):
            raise ValueError("Tipo de interconector não suportado.")
        if (len(self.component_pair) != 2 or any(not isinstance(k, str) or not k.strip() for k in self.component_pair)
                or self.component_pair[0] == self.component_pair[1]):
            raise ValueError("Interconectores requerem dois componentes distintos.")
        if (not isinstance(self.profile_ref, ProfileRef)
                or any(not isinstance(k, str) or not k.strip() for k in
                       (self.profile_ref.catalog_id, self.profile_ref.profile_id))
                or not isinstance(self.section_transform, SectionTransform)
                or not isinstance(self.insertion_reference, str) or not self.insertion_reference):
            raise ValueError("Perfil, inserção ou transformação do interconector inválido.")
        if len(self.color) != 3 or not all(finite(v) and 0 <= v <= 1 for v in self.color):
            raise ValueError("Cor do interconector inválida.")
        if any(not finite(v) or v < 0 for v in (self.start_offset, self.end_offset)):
            raise ValueError("Afastamentos dos interconectores devem ser finitos e não negativos.")
        if not isinstance(self.distribution, DistributionSpec):
            raise ValueError("Distribuição do interconector inválida.")
        if self.start_side not in ("A", "B") or (self.kind != "SingleLacing" and self.start_side != "A"):
            raise ValueError("Lado inicial A/B se aplica somente ao treliçamento simples.")
        if self.attachment_plane not in ("AxisToAxis", "InnerFaces", "FaceA", "FaceB", "Both"):
            raise ValueError("Plano de ligação não suportado.")
        if (self.kind == "SpacerPlate") != (self.attachment_plane == "InnerFaces"):
            raise ValueError("Chapas espaçadoras usam somente a posição entre faces internas.")


@dataclass(frozen=True)
class InterconnectorRealization:
    stable_identity: tuple
    interconnector_key: str
    kind: str
    slot_key: tuple
    generated_element_key: str
    profile_ref: ProfileRef
    start_global: tuple
    end_global: tuple
    orientation: object
    insertion_reference: str
    section_transform: SectionTransform
    section_geometry_mode: SectionGeometryMode
    color: tuple
    label: str
    attachment_plane: str = "AxisToAxis"


def validate_pair(components, pair, nominal_axis):
    """Validate even independently supplied resolved physical axes."""
    if len(components) != 2:
        raise ValueError("Interconectores nesta etapa suportam assemblies de dois componentes.")
    by_key = {c.component_key: c for c in components}
    if len(pair) != 2 or pair[0] == pair[1] or any(k not in by_key for k in pair):
        raise ValueError("Selecione dois componentes existentes e distintos para os interconectores.")
    a, b = (by_key[k] for k in pair)
    origin, end = (vector(p) for p in nominal_axis)
    length = math.dist(origin, end)
    w = unit(tuple(y-x for x, y in zip(origin, end)))
    for c in (a, b):
        start, finish = vector(c.start_global), vector(c.end_global)
        direction = unit(tuple(y-x for x, y in zip(start, finish)))
        if math.dist(direction, w) > LENGTH_TOLERANCE:
            raise ValueError("Eixos dos componentes devem ser paralelos e ter o mesmo sentido longitudinal.")
        if not math.isclose(math.dist(start, finish), length, rel_tol=0., abs_tol=LENGTH_TOLERANCE):
            raise ValueError("Comprimentos dos componentes devem corresponder ao comprimento nominal.")
        if abs(sum((x-y)*z for x, y, z in zip(start, origin, w))) > LENGTH_TOLERANCE:
            raise ValueError("Extremos dos componentes devem partir da mesma estação nominal.")
    separation = tuple(y-x for x, y in zip(a.start_global, b.start_global))
    normal = cross(separation, w)
    if math.sqrt(sum(v*v for v in normal)) <= LENGTH_TOLERANCE:
        raise ValueError("Eixos coincidentes não permitem interconectores.")
    return a, b, w, unit(normal), length


def resolve_interconnectors(nominal_axis, components, assembly_spec):
    elements, distributions = [], []
    for spec in sorted(assembly_spec.interconnectors, key=lambda s: s.interconnector_key):
        a, b, w, normal, length = validate_pair(components, spec.component_pair, nominal_axis)
        if spec.kind == "None":
            continue
        distribution = resolve_stations(length, spec.distribution, spec.start_offset, spec.end_offset,
                                        minimum_count=1 if spec.kind in ("Battens", "SpacerPlate") else 2)
        distributions.append((spec.interconnector_key, distribution))
        from .attachment import attach_elements, section_support
        # C4-A payloads keep their nominal station semantics explicitly.
        if spec.attachment_plane != "AxisToAxis":
            margin_start = margin_end = 0.
            # Hold the initial count for maximum-spacing mode: shortening the
            # station span only reduces spacing and avoids count oscillations.
            fixed = DistributionSpec(station_count=distribution.effective_count,
                                     station_keys=tuple(s.key for s in distribution.stations))
            for _ in range(100):
                # Attachment to the component faces may translate a connector
                # along the host axis.  Measure the final attached envelope,
                # otherwise the last connector can remain inside a fitted end.
                trial = attach_elements(
                    nominal_axis,
                    components,
                    spec,
                    _station_elements(a, b, w, normal, spec, assembly_spec, distribution),
                )
                from .attachment import dot
                first, last = distribution.stations[0].position, distribution.stations[-1].position
                bounds = []
                for c in trial:
                    low, high = section_support(c, w)
                    positions = [dot(tuple(x-y for x, y in zip(p, a.start_global)), w)
                                 for p in (c.start_global, c.end_global)]
                    bounds.append((min(positions)+low-first, max(positions)+high-last))
                required_start = max(0., max(-low for low, _ in bounds))
                required_end = max(0., max(high for _, high in bounds))
                if (required_start <= margin_start+1e-8 and
                        required_end <= margin_end+1e-8):
                    break
                margin_start = max(margin_start, required_start)
                margin_end = max(margin_end, required_end)
                distribution = resolve_stations(length, fixed,
                    spec.start_offset+margin_start, spec.end_offset+margin_end,
                    minimum_count=1 if spec.kind in ("Battens", "SpacerPlate") else 2)
            else:
                raise ValueError("Não foi possível acomodar o envelope longitudinal dos interconectores.")
            distributions[-1] = (spec.interconnector_key, distribution)
        resolved = _station_elements(a, b, w, normal, spec, assembly_spec, distribution)
        elements.extend(attach_elements(nominal_axis, components, spec, resolved))
    return tuple(elements), tuple(distributions)


def _station_elements(a, b, w, normal, spec, assembly_spec, distribution):
    from .models import MemberFrame
    elements = []
    def point(c, station):
        return tuple(x+station.position*y for x, y in zip(c.start_global, w))
    def emit(c1, s1, c2, s2, slot, branch, number):
        start, end = point(c1, s1), point(c2, s2)
        # Section X lies in the connector plane; Y is its normal. Thus a
        # flat bar's width lies in-plane, using the normal member adapter.
        direction = unit(tuple(y-x for x, y in zip(start, end)))
        frame = MemberFrame.from_axis((start, end), cross(normal, direction))
        identity = (assembly_spec.assembly_key, "Interconnector", spec.interconnector_key,
                    spec.kind, *slot, branch)
        label = ("Chapa espaçadora" if spec.kind == "SpacerPlate" else
                 "Presilha" if spec.kind == "Battens" else "Treliçamento")+f" {number:02d}"
        elements.append(InterconnectorRealization(identity, spec.interconnector_key, spec.kind,
            slot, branch, spec.profile_ref, start, end, frame, spec.insertion_reference,
            spec.section_transform, spec.section_geometry_mode, spec.color, label))
    stations = distribution.stations
    if spec.kind in ("Battens", "SpacerPlate"):
        for i, station in enumerate(stations):
            emit(a, station, b, station, (station.key,), "Batten", i+1)
    else:
        for i, (s1, s2) in enumerate(zip(stations, stations[1:])):
            slot = (s1.key, s2.key)
            if spec.kind == "SingleLacing":
                c1, c2 = (a, b) if (i+(spec.start_side == "B")) % 2 == 0 else (b, a)
                emit(c1, s1, c2, s2, slot, "Lace", i+1)
            else:
                emit(a, s1, b, s2, slot, "LaceA", 2*i+1)
                emit(b, s1, a, s2, slot, "LaceB", 2*i+2)
    return tuple(elements)
