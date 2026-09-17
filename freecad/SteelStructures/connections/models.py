"""Pure, versioned contracts for structural connection intent."""

from dataclasses import dataclass
from enum import Enum


CONNECTION_INTENT_SCHEMA_VERSION = 1


class ConnectionForm(str, Enum):
    GEOMETRIC_ONLY = "GeometricOnly"
    DIRECT = "Direct"
    GUSSET = "Gusset"


class FasteningIntent(str, Enum):
    UNSPECIFIED = "Unspecified"
    WELDED = "Welded"
    BOLTED = "Bolted"
    MIXED = "Mixed"


class DirectFitPolicy(str, Enum):
    INDEPENDENT = "Independent"
    BALANCED_MITER = "BalancedMiter"
    PRIORITY = "Priority"


class PriorityMember(str, Enum):
    AUTOMATIC = "Automatic"
    PARTICIPANT_A = "ParticipantA"
    PARTICIPANT_B = "ParticipantB"


class GussetSide(str, Enum):
    CENTER = "Center"
    FACE_A = "FaceA"
    FACE_B = "FaceB"


@dataclass(frozen=True)
class GussetFitSpec:
    plate_thickness: float = 0.0
    normal_clearance: float = 0.0
    axial_clearance: float = 0.0
    side: GussetSide = GussetSide.CENTER


@dataclass(frozen=True)
class ConnectionIntent:
    intent_key: str
    node_key: str
    form: ConnectionForm = ConnectionForm.GEOMETRIC_ONLY
    fastening: FasteningIntent = FasteningIntent.UNSPECIFIED
    direct_policy: DirectFitPolicy = DirectFitPolicy.INDEPENDENT
    participant_run_keys: tuple[str, ...] = ()
    priority_member: PriorityMember = PriorityMember.AUTOMATIC
    gusset: GussetFitSpec = GussetFitSpec()
    schema_version: int = CONNECTION_INTENT_SCHEMA_VERSION
    priority_run_key: str = ""


@dataclass(frozen=True)
class ConnectionParticipant:
    participant_key: str
    node_key: str
    run_key: str
    role: str
    end: str
    axis: tuple
    assembly: str = "Single"
    component_keys: tuple[str, ...] = ()
    geometry_key: str = ""
    continuous_through: bool = False
    run_keys: tuple[str, ...] = ()
    run_ends: tuple[tuple[str, str], ...] = ()

    @property
    def physical_run_keys(self):
        return self.run_keys or (self.run_key,)


@dataclass(frozen=True)
class EndParticipant(ConnectionParticipant):
    """One physical run ending at the node."""


@dataclass(frozen=True)
class ThroughParticipant(ConnectionParticipant):
    """Physical continuity through a stable topology node."""


@dataclass(frozen=True)
class ChordJointParticipant(ConnectionParticipant):
    """Two incident chord runs sharing one physical miter plane."""
    branches: tuple[EndParticipant, ...] = ()


@dataclass(frozen=True)
class ChordBreakParticipant(ChordJointParticipant):
    """Two angular branches of one chord, retaining their physical run IDs."""


@dataclass(frozen=True)
class ChordClosureParticipant(ChordJointParticipant):
    """Two distinct chord roles closing one terminal topology node."""


@dataclass(frozen=True)
class ConnectionDiagnostic:
    code: str
    severity: str
    message: str


@dataclass(frozen=True)
class ConnectionFitDirective:
    run_key: str
    end: str
    kind: str
    reference_key: str
    target_run_key: str = ""
    target_run_keys: tuple[str, ...] = ()
    reference_offset: float = 0.0
    plane_origin: tuple | None = None
    plane_normal: tuple | None = None


@dataclass(frozen=True)
class ConnectionResolution:
    intent: ConnectionIntent
    participants: tuple[ConnectionParticipant, ...]
    directives: tuple[ConnectionFitDirective, ...] = ()
    diagnostics: tuple[ConnectionDiagnostic, ...] = ()
    gusset_plane: "GussetPlane | None" = None


@dataclass(frozen=True)
class GussetPlane:
    """Reserved transverse slab; dimensions remain independent of axial setbacks."""
    origin: tuple
    normal: tuple
    plate_thickness: float
    normal_clearance: float
