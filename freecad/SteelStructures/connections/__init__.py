"""Pure semantic connection contracts and resolvers."""

from .models import (CONNECTION_INTENT_SCHEMA_VERSION, ConnectionDiagnostic,
                     ConnectionFitDirective, ConnectionForm, ConnectionIntent,
                     ConnectionParticipant, EndParticipant, ThroughParticipant,
                     ChordJointParticipant, ChordBreakParticipant,
                     ChordClosureParticipant, ConnectionResolution, DirectFitPolicy,
                     FasteningIntent, GussetFitSpec, GussetSide, PriorityMember)
from .resolver import (resolve_chord_joints, resolve_connection,
                       resolve_connection_participants)
from .serialization import dumps, loads
from .validation import validate_intent

__all__ = [
    "CONNECTION_INTENT_SCHEMA_VERSION", "ConnectionDiagnostic",
    "ConnectionFitDirective", "ConnectionForm", "ConnectionIntent",
    "EndParticipant", "ThroughParticipant", "ChordJointParticipant",
    "ChordBreakParticipant", "ChordClosureParticipant", "ConnectionParticipant",
    "ConnectionResolution", "DirectFitPolicy",
    "FasteningIntent", "GussetFitSpec", "GussetSide", "PriorityMember",
    "resolve_chord_joints", "resolve_connection", "resolve_connection_participants",
    "dumps", "loads",
    "validate_intent",
]
