"""Immutable, OCC-independent physical fitting contracts."""

from dataclasses import dataclass
from enum import Enum


FIT_PLAN_SCHEMA_VERSION = 2


class PhysicalFitMode(str, Enum):
    NONE = "None"
    TO_CHORD = "ToChord"
    GUSSET_AWARE = "GussetAware"
    CUSTOM = "Custom"


class FitEnd(str, Enum):
    START = "Start"
    END = "End"


class FitActionMode(str, Enum):
    NONE = "None"
    LENGTH_LIMIT = "LengthLimit"
    PLANE_CUT = "PlaneCut"


class FitSource(str, Enum):
    AUTO_FIT = "AutoFit"
    USER_OVERRIDE = "UserOverride"
    CONNECTION_INTENT = "ConnectionIntent"


@dataclass(frozen=True)
class FitDiagnostic:
    code: str
    severity: str
    message: str


@dataclass(frozen=True)
class GeometryReference:
    """Stable pure geometry; adapters may originate this from faces or edges."""

    reference_key: str
    kind: str
    origin: tuple[float, float, float]
    direction: tuple[float, float, float] | None = None
    normal: tuple[float, float, float] | None = None


@dataclass(frozen=True)
class NominalMember:
    member_key: str
    run_key: str
    role: str
    start_node_key: str
    end_node_key: str
    start: tuple[float, float, float]
    end: tuple[float, float, float]
    element_kind: str = "Component"


@dataclass(frozen=True)
class FittingPolicy:
    mode: PhysicalFitMode = PhysicalFitMode.NONE
    gap: float = 0.0
    prefer_plane_cut: bool = True
    source: FitSource = FitSource.AUTO_FIT
    # Reserved for GussetAware. These clearances are intentionally not axial gap.
    normal_clearance: float | None = None
    plate_thickness: float | None = None
    side_clearance: float | None = None


@dataclass(frozen=True)
class FitAction:
    end: FitEnd
    mode: FitActionMode
    reference_key: str
    gap: float = 0.0
    reference_offset: float = 0.0
    plane_origin: tuple[float, float, float] | None = None
    plane_normal: tuple[float, float, float] | None = None
    source: FitSource = FitSource.AUTO_FIT


@dataclass(frozen=True)
class PhysicalFitPlan:
    plan_key: str
    member_key: str
    run_key: str
    mode: PhysicalFitMode
    start_action: FitAction | None = None
    end_action: FitAction | None = None
    diagnostics: tuple[FitDiagnostic, ...] = ()
    schema_version: int = FIT_PLAN_SCHEMA_VERSION
    additional_actions: tuple[FitAction, ...] = ()
