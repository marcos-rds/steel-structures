"""Pure, versioned contracts for structural connection intent."""

from dataclasses import dataclass
from enum import Enum
import math


CONNECTION_INTENT_SCHEMA_VERSION = 4
GUSSET_PLATE_SCHEMA_VERSION = 3


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


class GussetAttachmentMode(str, Enum):
    AUTO = "Auto"
    OUTER = "Outer"
    INNER = "Inner"
    CENTER = "Center"


class GussetChordContact(str, Enum):
    AUTO = "Auto"
    TRUSS_INTERIOR = "TrussInterior"
    TRUSS_EXTERIOR = "TrussExterior"


class GussetSurfaceClass(str, Enum):
    OUTER = "Outer"
    INNER = "Inner"


class GussetAccessibility(str, Enum):
    OUTER_EXPOSED = "OuterExposed"
    OPEN_RECESS = "OpenRecess"
    ASSEMBLY_GAP = "AssemblyGap"
    SURFACE_BAND = "SurfaceBand"
    ENCLOSED_VOID = "EnclosedVoid"
    UNSUPPORTED = "Unsupported"


class GussetAttachmentSlotKind(str, Enum):
    OUTER_HALFSPACE = "OuterHalfspace"
    OPEN_RECESS = "OpenRecess"
    BETWEEN_COMPONENTS = "BetweenComponents"
    SURFACE_BAND = "SurfaceBand"
    ENCLOSED_VOID = "EnclosedVoid"
    UNSUPPORTED = "Unsupported"


class GussetSlotPlacement(str, Enum):
    NEAR_A = "NearA"
    CENTER = "Center"
    NEAR_B = "NearB"


@dataclass(frozen=True)
class GussetFitSpec:
    plate_thickness: float = 0.0
    normal_clearance: float = 0.0
    axial_clearance: float = 0.0
    side: GussetSide = GussetSide.CENTER
    edge_margin: float = 25.0
    member_overlap: float = 150.0
    attachment_mode: GussetAttachmentMode = GussetAttachmentMode.AUTO
    chord_contact: GussetChordContact = GussetChordContact.AUTO
    transverse_placement: str = ""

    def __post_init__(self):
        object.__setattr__(self, "side", GussetSide(self.side))
        object.__setattr__(self, "attachment_mode",
                           GussetAttachmentMode(self.attachment_mode))
        object.__setattr__(self, "chord_contact",
                           GussetChordContact(self.chord_contact))
        if not isinstance(self.transverse_placement, str):
            raise ValueError("Posição transversal deve identificar uma opção física.")


@dataclass(frozen=True)
class GussetPlateFrame:
    """Right-handed local plate frame; x/y lie in the truss plane."""
    origin: tuple
    x_axis: tuple
    y_axis: tuple
    normal: tuple

    def __post_init__(self):
        for name in ("origin", "x_axis", "y_axis", "normal"):
            object.__setattr__(self, name, tuple(getattr(self, name)))


@dataclass(frozen=True)
class GussetPlateSpec:
    """Pure preliminary plate contract. It deliberately contains no OCC data."""
    stable_key: str
    node_key: str
    plate_thickness: float
    edge_margin: float = 25.0
    member_overlap: float = 150.0
    side: GussetSide = GussetSide.CENTER
    attachment_mode: GussetAttachmentMode = GussetAttachmentMode.AUTO
    chord_contact: GussetChordContact = GussetChordContact.AUTO
    transverse_placement: str = ""
    participant_keys: tuple[str, ...] = ()
    component_keys: tuple[str, ...] = ()
    frame: GussetPlateFrame | None = None
    schema_version: int = GUSSET_PLATE_SCHEMA_VERSION

    def __post_init__(self):
        object.__setattr__(self, "side", GussetSide(self.side))
        object.__setattr__(self, "attachment_mode",
                           GussetAttachmentMode(self.attachment_mode))
        object.__setattr__(self, "chord_contact",
                           GussetChordContact(self.chord_contact))
        if not isinstance(self.transverse_placement, str):
            raise ValueError("Posição transversal deve identificar uma opção física.")
        object.__setattr__(self, "participant_keys", tuple(self.participant_keys))
        object.__setattr__(self, "component_keys", tuple(self.component_keys))


@dataclass(frozen=True)
class GussetCorridor:
    """In-plane physical envelope of one component along one incident branch."""
    participant_key: str
    component_key: str
    direction: tuple
    transverse_low: float
    transverse_high: float

    def __post_init__(self):
        object.__setattr__(self, "direction", tuple(self.direction))


@dataclass(frozen=True)
class GussetSupportLine:
    """Physical boundary expressed as ``normal . point <= offset``.

    The normal points to the side that the preliminary plate must not cross.
    Support lines are transient pure geometry derived from transformed section
    envelopes, and therefore do not duplicate GussetPlateSpec persistence.
    """
    participant_key: str
    direction: tuple
    normal: tuple
    offset: float
    kind: str = "ChordOuterBoundary"

    def __post_init__(self):
        object.__setattr__(self, "direction", tuple(self.direction))
        object.__setattr__(self, "normal", tuple(self.normal))


class GussetResidualStatus(str, Enum):
    CONTACT = "Contact"
    GAP = "Gap"
    INTERFERENCE = "Interference"
    NO_COMPATIBLE_SURFACE = "NoCompatibleSurface"


@dataclass(frozen=True)
class GussetConnectionSurface:
    """Pure longitudinal planar surface derived from one section edge."""
    participant_key: str
    run_key: str
    component_key: str
    surface_id: str
    role: str
    participant_end: str
    plane_normal: tuple
    signed_offset: float
    section_edge: tuple
    side: GussetSide
    outward_sign: int
    angular_error_degrees: float
    contact_extent: float = 0.0
    surface_role: str = "LongitudinalSectionEdge"
    surface_class: GussetSurfaceClass = GussetSurfaceClass.OUTER
    recess_depth: float = 0.0
    component_axis_offset: float = 0.0
    free_space: float | None = None
    component_band_low: float = 0.0
    component_band_high: float = 0.0

    def __post_init__(self):
        object.__setattr__(self, "plane_normal", tuple(self.plane_normal))
        object.__setattr__(self, "section_edge",
                           tuple(tuple(point) for point in self.section_edge))
        object.__setattr__(self, "side", GussetSide(self.side))
        object.__setattr__(self, "surface_class",
                           GussetSurfaceClass(self.surface_class))
        if (len(self.plane_normal) != 3
                or not all(math.isfinite(value) for value in self.plane_normal)
                or abs(sum(value*value for value in self.plane_normal)-1.) > 1e-6):
            raise ValueError("A normal da superfície de ligação deve ser unitária.")
        if self.outward_sign not in (-1, 1):
            raise ValueError("O lado da superfície de ligação deve ser A ou B.")
        if self.side != (GussetSide.FACE_A if self.outward_sign > 0
                         else GussetSide.FACE_B):
            raise ValueError("Classificação lateral inconsistente na superfície de ligação.")
        if (not math.isfinite(self.signed_offset)
                or not math.isfinite(self.angular_error_degrees)
                or self.angular_error_degrees < 0.
                or not math.isfinite(self.contact_extent)
                or self.contact_extent < 0.
                or not math.isfinite(self.recess_depth)
                or self.recess_depth < 0.
                or not math.isfinite(self.component_axis_offset)
                or (self.free_space is not None
                    and (not math.isfinite(self.free_space) or self.free_space < 0.))):
            raise ValueError("Métrica inválida na superfície de ligação.")
        if (not math.isfinite(self.component_band_low)
                or not math.isfinite(self.component_band_high)
                or self.component_band_high < self.component_band_low):
            raise ValueError("Envelope transversal inválido na superfície de ligação.")


@dataclass(frozen=True)
class GussetContactWindow:
    """Collision-free in-section extent for one plate slab, without OCC data."""
    stable_key: str
    local_axis: tuple
    intervals: tuple[tuple[float | None, float | None], ...]
    contact_surface_ids: tuple[str, ...] = ()
    diagnostics: tuple[str, ...] = ()

    def __post_init__(self):
        object.__setattr__(self, "local_axis", tuple(self.local_axis))
        object.__setattr__(self, "intervals", tuple(tuple(value)
                                                    for value in self.intervals))
        object.__setattr__(self, "contact_surface_ids",
                           tuple(self.contact_surface_ids))
        object.__setattr__(self, "diagnostics", tuple(self.diagnostics))
        if not self.stable_key or len(self.local_axis) != 3:
            raise ValueError("Janela de contato inválida.")
        for low, high in self.intervals:
            if ((low is not None and not math.isfinite(low))
                    or (high is not None and not math.isfinite(high))
                    or (low is not None and high is not None and high <= low)):
                raise ValueError("Intervalo inválido na janela de contato.")


@dataclass(frozen=True)
class GussetSectionMaterial2D:
    """Transformed nominal section material in (plate-normal, local-axis)."""
    participant_key: str
    component_key: str
    outer: tuple[tuple[float, float], ...]
    holes: tuple[tuple[tuple[float, float], ...], ...] = ()
    local_axis: tuple = (1., 0., 0.)

    def __post_init__(self):
        object.__setattr__(self, "outer", tuple(tuple(point)
                                                for point in self.outer))
        object.__setattr__(self, "holes", tuple(tuple(tuple(point)
                                                      for point in path)
                                                for path in self.holes))
        object.__setattr__(self, "local_axis", tuple(self.local_axis))
        if (not self.participant_key or not self.component_key
                or len(self.outer) < 3
                or len(self.local_axis) != 3
                or any(len(point) != 2 or not all(math.isfinite(v) for v in point)
                       for path in (self.outer,)+self.holes for point in path)):
            raise ValueError("Material 2D de seção inválido.")


@dataclass(frozen=True)
class GussetAttachmentSlot:
    """Semantic free-space region available to the complete plate thickness."""
    stable_key: str
    participant_key: str
    component_keys: tuple[str, ...]
    kind: GussetAttachmentSlotKind
    normal: tuple
    boundary_a_surface_id: str = ""
    boundary_b_surface_id: str = ""
    free_low: float | None = None
    free_high: float | None = None
    available_clear_width: float | None = None
    open_accessibility: bool = True
    allowed_placements: tuple[GussetSlotPlacement, ...] = ()
    contact_surface_ids: tuple[str, ...] = ()
    local_axis: tuple = ()
    diagnostics: tuple[str, ...] = ()
    access_sign: int = 0

    def __post_init__(self):
        object.__setattr__(self, "kind", GussetAttachmentSlotKind(self.kind))
        object.__setattr__(self, "normal", tuple(self.normal))
        object.__setattr__(self, "component_keys", tuple(self.component_keys))
        object.__setattr__(self, "allowed_placements", tuple(
            GussetSlotPlacement(value) for value in self.allowed_placements))
        object.__setattr__(self, "contact_surface_ids",
                           tuple(self.contact_surface_ids))
        object.__setattr__(self, "local_axis", tuple(self.local_axis))
        object.__setattr__(self, "diagnostics", tuple(self.diagnostics))
        if self.access_sign not in (-1, 0, 1):
            raise ValueError("Direção de acesso do slot inválida.")
        if (not self.stable_key or not self.participant_key
                or len(self.normal) != 3
                or not all(math.isfinite(value) for value in self.normal)):
            raise ValueError("Slot de apoio inválido.")
        for value in (self.free_low, self.free_high,
                      self.available_clear_width):
            if value is not None and not math.isfinite(value):
                raise ValueError("Métrica inválida no slot de apoio.")
        if (self.available_clear_width is not None
                and self.available_clear_width < 0.):
            raise ValueError("Largura livre inválida no slot de apoio.")
        if (self.free_low is not None and self.free_high is not None
                and self.free_high <= self.free_low):
            raise ValueError("Região livre inválida no slot de apoio.")


@dataclass(frozen=True)
class GussetAttachmentCandidate:
    """One physically usable pure placement, independent of OCC topology."""
    stable_key: str
    attachment_mode: GussetAttachmentMode
    plane_normal: tuple
    signed_offset: float
    accessibility: GussetAccessibility
    extrusion_sign: int
    allowed_sides: tuple[GussetSide, ...]
    surface_semantic_id: str = ""
    surface_class: GussetSurfaceClass | None = None
    governing_participant_key: str = ""
    governing_component_key: str = ""
    free_space: float | None = None
    diagnostics: tuple[str, ...] = ()
    slot_id: str = ""
    placement: GussetSlotPlacement | None = None
    plate_low: float | None = None
    plate_high: float | None = None
    contact_window: GussetContactWindow | None = None
    contact_direction: int = 0
    contact_band: float | None = None
    outline_band: float | None = None

    def __post_init__(self):
        object.__setattr__(self, "attachment_mode",
                           GussetAttachmentMode(self.attachment_mode))
        object.__setattr__(self, "accessibility",
                           GussetAccessibility(self.accessibility))
        object.__setattr__(self, "plane_normal", tuple(self.plane_normal))
        object.__setattr__(self, "allowed_sides",
                           tuple(GussetSide(value) for value in self.allowed_sides))
        object.__setattr__(self, "diagnostics", tuple(self.diagnostics))
        if self.placement is not None:
            object.__setattr__(self, "placement",
                               GussetSlotPlacement(self.placement))
        if self.surface_class is not None:
            object.__setattr__(self, "surface_class",
                               GussetSurfaceClass(self.surface_class))
        if self.contact_direction not in (-1, 0, 1):
            raise ValueError("Direção do ContactBand candidato inválida.")
        if (not self.stable_key or len(self.plane_normal) != 3
                or not all(math.isfinite(value) for value in self.plane_normal)
                or abs(sum(value*value for value in self.plane_normal)-1.) > 1e-6
                or not math.isfinite(self.signed_offset)
                or (self.free_space is not None
                    and (not math.isfinite(self.free_space) or self.free_space < 0.))
                or self.extrusion_sign not in (-1, 0, 1)
                or (self.contact_band is not None
                    and not math.isfinite(self.contact_band))
                or (self.outline_band is not None
                    and not math.isfinite(self.outline_band))
                or not self.allowed_sides):
            raise ValueError("Placement candidato da chapa é inválido.")
        if ((self.plate_low is None) != (self.plate_high is None)
                or (self.plate_low is not None
                    and (not math.isfinite(self.plate_low)
                         or not math.isfinite(self.plate_high)
                         or self.plate_high <= self.plate_low))):
            raise ValueError("Slab candidato da chapa é inválido.")


@dataclass(frozen=True)
class GussetOutlineEdge:
    start: tuple
    end: tuple
    kind: str
    participant_key: str = ""
    direction: tuple = ()

    def __post_init__(self):
        object.__setattr__(self, "start", tuple(self.start))
        object.__setattr__(self, "end", tuple(self.end))
        object.__setattr__(self, "direction", tuple(self.direction))


@dataclass(frozen=True)
class GussetAttachmentResidual:
    participant_key: str
    role: str
    status: GussetResidualStatus
    residual: float | None
    surface_id: str = ""
    message: str = ""

    def __post_init__(self):
        object.__setattr__(self, "status", GussetResidualStatus(self.status))
        if self.residual is not None and not math.isfinite(self.residual):
            raise ValueError("Residual transversal deve ser finito.")
        if ((self.status == GussetResidualStatus.NO_COMPATIBLE_SURFACE)
                != (self.residual is None)):
            raise ValueError("Residual incompatível com o status de contato.")


@dataclass(frozen=True)
class GussetAttachmentPlane:
    """Resolved physical plate placement along the local truss normal."""
    normal: tuple
    signed_offset: float
    plate_low: float
    plate_high: float
    governing_participant_key: str = ""
    governing_component_key: str = ""
    governing_surface_id: str = ""
    attachment_side: GussetSide = GussetSide.CENTER
    contact_sign: int = 0
    kind: str = "NominalFallback"
    status: str = "Warning"
    residuals: tuple[GussetAttachmentResidual, ...] = ()
    diagnostics: tuple[str, ...] = ()
    requested_mode: GussetAttachmentMode = GussetAttachmentMode.AUTO
    governing_surface_class: GussetSurfaceClass | None = None
    candidates: tuple[GussetAttachmentCandidate, ...] = ()
    governing_slot_id: str = ""
    placement_kind: GussetSlotPlacement | None = None
    contact_window: GussetContactWindow | None = None

    def __post_init__(self):
        object.__setattr__(self, "normal", tuple(self.normal))
        object.__setattr__(self, "attachment_side", GussetSide(self.attachment_side))
        object.__setattr__(self, "requested_mode",
                           GussetAttachmentMode(self.requested_mode))
        if self.governing_surface_class is not None:
            object.__setattr__(self, "governing_surface_class",
                               GussetSurfaceClass(self.governing_surface_class))
        object.__setattr__(self, "residuals", tuple(self.residuals))
        object.__setattr__(self, "diagnostics", tuple(self.diagnostics))
        object.__setattr__(self, "candidates", tuple(self.candidates))
        if self.placement_kind is not None:
            object.__setattr__(self, "placement_kind",
                               GussetSlotPlacement(self.placement_kind))
        if (len(self.normal) != 3 or not all(math.isfinite(value) for value in self.normal)
                or abs(sum(value*value for value in self.normal)-1.) > 1e-6):
            raise ValueError("A normal do plano de montagem deve ser unitária.")
        if (not all(math.isfinite(value) for value in
                    (self.signed_offset, self.plate_low, self.plate_high))
                or self.plate_high <= self.plate_low):
            raise ValueError("Intervalo transversal inválido para a chapa.")
        if self.contact_sign not in (-1, 0, 1):
            raise ValueError("Sinal de contato inválido para o plano de montagem.")


@dataclass(frozen=True)
class GussetOutline:
    spec: GussetPlateSpec
    points: tuple[tuple[float, float], ...]
    area: float
    attachment: GussetAttachmentPlane | None = None
    semantic_edges: tuple[GussetOutlineEdge, ...] = ()

    def __post_init__(self):
        object.__setattr__(self, "points", tuple(tuple(point) for point in self.points))
        object.__setattr__(self, "semantic_edges", tuple(self.semantic_edges))


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
    node_key: str = ""


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
    side: GussetSide = GussetSide.CENTER
