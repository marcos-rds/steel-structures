"""C1 value objects. Distances are millimetres, angles are degrees."""
from dataclasses import dataclass, field

SCHEMA_VERSION = 2
GENERATOR_VERSION = 1
ROLES = ("TOP_CHORD", "BOTTOM_CHORD", "VERTICAL", "DIAGONAL", "END_POST")
CONTINUITIES = ("Continuous", "SegmentAtBreaks", "SegmentAtEveryNode")


@dataclass(frozen=True)
class EnvelopeDefinition:
    kind: str
    span: float
    height: float
    apex_position: float = 0.5


@dataclass(frozen=True)
class Station:
    key: str
    x: float
    mandatory: bool = False
    branch: str = "MAIN"


@dataclass(frozen=True)
class StationPlan:
    stations: tuple
    panel_count: int
    left_panels: int = 0
    right_panels: int = 0


@dataclass(frozen=True)
class TopologyNode:
    key: str
    position_local: tuple
    affiliations: tuple
    classification: str
    optional_station_key: str = ""


@dataclass(frozen=True)
class TopologyEdge:
    key: str
    start_node_key: str
    end_node_key: str
    role: str
    chord_affiliation: str = ""


@dataclass(frozen=True)
class TopologyGraph:
    nodes: tuple
    edges: tuple

    def node(self, key):
        return next(node for node in self.nodes if node.key == key)

    def edge(self, key):
        return next(edge for edge in self.edges if edge.key == key)

    @property
    def incidence(self):
        return {n.key: tuple(e.key for e in self.edges if n.key in
                            (e.start_node_key, e.end_node_key)) for n in self.nodes}

    @property
    def adjacency(self):
        result = {n.key: [] for n in self.nodes}
        for e in self.edges:
            result[e.start_node_key].append(e.end_node_key)
            result[e.end_node_key].append(e.start_node_key)
        return {key: tuple(sorted(values)) for key, values in result.items()}


@dataclass(frozen=True)
class MemberSpec:
    profile_ref: dict
    insertion: str = "centroid"
    rotation: float = 0.0
    section_geometry_mode: str = "Detailed"
    color: tuple = (0.72, 0.72, 0.76)
    assembly: str = "Single"
    physical_fit: str = "None"


@dataclass(frozen=True)
class PhysicalRun:
    key: str
    role: str
    edge_keys: tuple
    start_node_key: str
    end_node_key: str


@dataclass(frozen=True)
class RealizationItem:
    key: str
    role: str
    start_node_key: str
    end_node_key: str
    start_local: tuple
    end_local: tuple
    start_global: tuple
    end_global: tuple
    section_u_global: tuple
    spec: MemberSpec


@dataclass(frozen=True)
class Candidate:
    config: dict
    stations: StationPlan
    graph: TopologyGraph
    runs: tuple
    items: tuple
    warnings: tuple = ()


@dataclass(frozen=True)
class RegenerationAction:
    key: str
    action: str
    existing_binding: str = ""
    reason: str = ""


@dataclass(frozen=True)
class RegenerationPlan:
    actions: tuple
    structural: bool

    @property
    def conflicts(self):
        return tuple(a for a in self.actions if a.action == "CONFLICT")
