"""Strict assembly boundaries; unsupported future semantics never silently apply."""
import math
from ..profiles.models import ProfileRef
from .transforms import SectionTransform


def finite(value):
    return not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(value)


def vector(value):
    result = tuple(value)
    if len(result) != 3 or not all(finite(x) for x in result):
        raise ValueError("Vetor deve ter três coordenadas finitas.")
    return result


def unit(v):
    length = math.sqrt(sum(x*x for x in v))
    if length < 1e-8:
        raise ValueError("Eixo degenerado.")
    return tuple(x/length for x in v)


def cross(a, b):
    return (a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0])


def validate_frame(frame):
    for v in (frame.u, frame.v, frame.w):
        vector(v)
        if not math.isclose(sum(x*x for x in v), 1., abs_tol=1e-8):
            raise ValueError("Frame deve ser ortonormal.")
    if math.dist(cross(frame.u, frame.v), frame.w) > 1e-8:
        raise ValueError("Frame deve ser destro e ortonormal.")


def validate_spec(spec):
    from .models import AssemblyComponentSpec
    if not isinstance(spec.assembly_key, str) or not spec.assembly_key.strip():
        raise ValueError("AssemblyKey obrigatório.")
    if spec.interconnectors:
        raise ValueError("Interconnectors reservados para C4.")
    if spec.assembly_insertion not in ("Center", "SymmetricPair"):
        raise ValueError("Inserção de assembly ainda não suportada.")
    if not spec.components or any(not isinstance(c, AssemblyComponentSpec) for c in spec.components):
        raise ValueError("Componentes inválidos.")
    keys = [c.component_key for c in spec.components]
    if any(not isinstance(k, str) or not k.strip() for k in keys) or len(set(keys)) != len(keys):
        raise ValueError("ComponentKeys devem ser únicos e não vazios.")
    if (spec.behavior_mode == "Single") != (len(keys) == 1):
        raise ValueError("BehaviorMode incompatível com componentes.")
    for c in spec.components:
        if (not isinstance(c.profile_ref, ProfileRef)
                or any(not isinstance(k, str) or not k.strip()
                       for k in (c.profile_ref.catalog_id, c.profile_ref.profile_id))
                or not isinstance(c.section_transform, SectionTransform)
                or not isinstance(c.insertion_reference, str) or not c.insertion_reference):
            raise ValueError("Especificação de componente inválida.")
        if len(c.transverse_translation) != 2 or not all(finite(x) for x in c.transverse_translation):
            raise ValueError("Translação transversal inválida.")
        if len(c.color) != 3 or not all(finite(x) and 0 <= x <= 1 for x in c.color):
            raise ValueError("Cor inválida.")
    if spec.component_spacing is not None:
        if not finite(spec.component_spacing) or spec.component_spacing < 0 or len(keys) != 2:
            raise ValueError("ComponentSpacing requer par e distância não negativa.")
        if not math.isclose(math.dist(*(c.transverse_translation for c in spec.components)),
                            spec.component_spacing, abs_tol=1e-8):
            raise ValueError("ComponentSpacing diverge da distância entre eixos de inserção.")
    if spec.assembly_insertion == "SymmetricPair":
        if len(keys) != 2 or any(abs(sum(c.transverse_translation[i] for c in spec.components)) > 1e-8
                                 for i in (0, 1)):
            raise ValueError("SymmetricPair requer translações opostas.")
