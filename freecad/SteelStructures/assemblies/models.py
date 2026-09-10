"""Immutable contracts. Section X=u, Y=v, longitudinal Z=w; u×v=w.

The caller supplies u. Existing trusses supply -their plane normal (C1/C2).
No global axis or camera is inferred. Spacing measures insertion-axis distance.
"""
from dataclasses import dataclass
from enum import Enum
from ..profiles.models import ProfileRef
from ..profiles.geometry import SectionGeometryMode
from .transforms import SectionTransform
from .interconnectors import InterconnectorSpec
from ..regeneration import RegenerationAction, RegenerationPlan


class BehaviorMode(str, Enum):
    SINGLE = "Single"
    MULTI_COMPONENT = "MultiComponent"


class AssemblyInsertion(str, Enum):
    CENTER = "Center"
    SYMMETRIC_PAIR = "SymmetricPair"
    NEAR_SIDE = "NearSide"  # reserved, rejected in C3-A
    FAR_SIDE = "FarSide"


@dataclass(frozen=True)
class AssemblyComponentSpec:
    component_key: str
    profile_ref: ProfileRef
    section_geometry_mode: SectionGeometryMode = SectionGeometryMode.DETAILED
    section_transform: SectionTransform = SectionTransform()
    transverse_translation: tuple = (0., 0.)
    insertion_reference: str = "centroid"
    color: tuple = (.72, .72, .76)

    def __post_init__(self):
        object.__setattr__(self, "transverse_translation", tuple(self.transverse_translation))
        object.__setattr__(self, "color", tuple(self.color))
        object.__setattr__(self, "section_geometry_mode", SectionGeometryMode(self.section_geometry_mode))


@dataclass(frozen=True)
class MemberAssemblySpec:
    assembly_key: str
    behavior_mode: BehaviorMode
    assembly_insertion: AssemblyInsertion
    components: tuple
    component_spacing: float | None = None
    interconnectors: tuple = ()

    def __post_init__(self):
        object.__setattr__(self, "components", tuple(self.components))
        object.__setattr__(self, "interconnectors", tuple(self.interconnectors))
        object.__setattr__(self, "behavior_mode", BehaviorMode(self.behavior_mode))
        object.__setattr__(self, "assembly_insertion", AssemblyInsertion(self.assembly_insertion))
        from .validation import validate_spec
        validate_spec(self)


@dataclass(frozen=True)
class MemberFrame:
    u: tuple
    v: tuple
    w: tuple

    def __post_init__(self):
        for name in ("u", "v", "w"):
            object.__setattr__(self, name, tuple(getattr(self, name)))
        from .validation import validate_frame
        validate_frame(self)

    @classmethod
    def from_axis(cls, nominal_axis, section_u):
        from .validation import vector, unit, cross
        a, b = (vector(p) for p in nominal_axis)
        w = unit(tuple(y-x for x, y in zip(a, b)))
        u = unit(vector(section_u))
        return cls(u, cross(w, u), w)


@dataclass(frozen=True)
class ComponentRealization:
    stable_identity: tuple
    component_key: str
    profile_ref: ProfileRef
    start_global: tuple
    end_global: tuple
    orientation: MemberFrame
    insertion_reference: str
    section_transform: SectionTransform
    section_geometry_mode: SectionGeometryMode
    color: tuple


@dataclass(frozen=True)
class AssemblyRealization:
    spec: MemberAssemblySpec
    nominal_axis: tuple
    member_frame: MemberFrame
    components: tuple
    interconnectors: tuple[InterconnectorSpec, ...] = ()
    distributions: tuple = ()

    @property
    def elements(self):
        return self.components + self.interconnectors
