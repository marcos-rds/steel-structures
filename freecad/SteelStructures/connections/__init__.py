"""Pure semantic connection contracts and resolvers."""

from .models import (CONNECTION_INTENT_SCHEMA_VERSION, GUSSET_PLATE_SCHEMA_VERSION, ConnectionDiagnostic,
                     ConnectionFitDirective, ConnectionForm, ConnectionIntent,
                     ConnectionParticipant, EndParticipant, ThroughParticipant,
                     ChordJointParticipant, ChordBreakParticipant,
                     ChordClosureParticipant, ConnectionResolution, DirectFitPolicy,
                     FasteningIntent, GussetFitSpec, GussetSide, GussetChordContact,
                     GussetAccessibility, GussetAttachmentCandidate,
                     GussetAttachmentSlot, GussetAttachmentSlotKind,
                     GussetContactWindow, GussetSectionMaterial2D,
                     GussetSlotPlacement,
                     GussetAttachmentMode, GussetSurfaceClass, PriorityMember,
                     GussetPlateFrame, GussetPlateSpec, GussetCorridor,
                     GussetSupportLine, GussetConnectionSurface,
                     GussetAttachmentResidual, GussetAttachmentPlane,
                     GussetResidualStatus, GussetOutline, GussetOutlineEdge)
from .attachment import (attachment_side_options, attachment_warning_messages,
                         compact_connection_messages, gusset_attachment_candidates,
                         resolve_gusset_attachment)
from .slots import (derive_attachment_slots, derive_surface_band_slot,
                    derive_surface_band_slots, flat_contact_intervals,
                    material_envelope_support, material_intervals,
                    slab_contact_window, slot_placements)
from .gusset import (build_gusset_outline, extrusion_limits, outline_extrusion_limits,
                     polygon_area, semantic_outline_regularization,
                     validate_gusset_spec)
from .resolver import (resolve_chord_joints, resolve_connection,
                       resolve_connection_participants)
from .serialization import dumps, loads
from .validation import validate_intent

__all__ = [
    "CONNECTION_INTENT_SCHEMA_VERSION", "GUSSET_PLATE_SCHEMA_VERSION", "ConnectionDiagnostic",
    "ConnectionFitDirective", "ConnectionForm", "ConnectionIntent",
    "EndParticipant", "ThroughParticipant", "ChordJointParticipant",
    "ChordBreakParticipant", "ChordClosureParticipant", "ConnectionParticipant",
    "ConnectionResolution", "DirectFitPolicy",
    "FasteningIntent", "GussetFitSpec", "GussetSide", "GussetAttachmentMode",
    "GussetChordContact",
    "GussetAccessibility", "GussetAttachmentCandidate",
    "GussetAttachmentSlot", "GussetAttachmentSlotKind", "GussetContactWindow",
    "GussetSectionMaterial2D", "GussetSlotPlacement",
    "GussetSurfaceClass", "PriorityMember",
    "GussetPlateFrame", "GussetPlateSpec", "GussetCorridor", "GussetSupportLine",
    "GussetConnectionSurface", "GussetAttachmentResidual", "GussetAttachmentPlane",
    "GussetResidualStatus", "GussetOutline", "GussetOutlineEdge",
    "resolve_gusset_attachment", "attachment_warning_messages",
    "attachment_side_options", "gusset_attachment_candidates",
    "compact_connection_messages",
    "derive_attachment_slots", "derive_surface_band_slot", "derive_surface_band_slots",
    "flat_contact_intervals", "material_envelope_support", "material_intervals", "slab_contact_window",
    "slot_placements",
    "build_gusset_outline", "extrusion_limits", "outline_extrusion_limits",
    "polygon_area", "semantic_outline_regularization", "validate_gusset_spec",
    "resolve_chord_joints", "resolve_connection", "resolve_connection_participants",
    "dumps", "loads",
    "validate_intent",
]
