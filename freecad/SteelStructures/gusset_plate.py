"""Persistent generated preliminary gusset plate.

The parent StructuralTruss/ConnectionIntent remains authoritative.  This
FeaturePython object only materializes and exposes that accepted state; it is
not a StructuralMember and ordinary execute never changes child cardinality.
"""

import json

import FreeCAD as App

from .trusses.gusset_freecad import build_gusset_shape

GUSSET_OBJECT_SCHEMA_VERSION = 2
GUSSET_COLOR = (0.45, 0.20, 0.65)
GUSSET_TRANSPARENCY = 35


def _quantity(value):
    return float(value.Value) if hasattr(value, "Value") else float(value)


def outline_signature(outline):
    frame = outline.spec.frame
    attachment = outline.attachment
    value = dict(
        stable_key=outline.spec.stable_key,
        node_key=outline.spec.node_key,
        plate_thickness=outline.spec.plate_thickness,
        edge_margin=outline.spec.edge_margin,
        member_overlap=outline.spec.member_overlap,
        side=outline.spec.side.value,
        attachment_mode=outline.spec.attachment_mode.value,
        chord_contact=outline.spec.chord_contact.value,
        transverse_placement=outline.spec.transverse_placement,
        participant_keys=outline.spec.participant_keys,
        component_keys=outline.spec.component_keys,
        frame=dict(origin=frame.origin, x_axis=frame.x_axis,
                   y_axis=frame.y_axis, normal=frame.normal),
        points=outline.points,
        attachment=(None if attachment is None else dict(
            signed_offset=attachment.signed_offset,
            plate_low=attachment.plate_low, plate_high=attachment.plate_high,
            governing_participant_key=attachment.governing_participant_key,
            governing_component_key=attachment.governing_component_key,
            governing_surface_id=attachment.governing_surface_id,
            attachment_side=attachment.attachment_side.value,
            contact_sign=attachment.contact_sign, kind=attachment.kind,
            status=attachment.status,
            requested_mode=attachment.requested_mode.value,
            governing_surface_class=(attachment.governing_surface_class.value
                                     if attachment.governing_surface_class else ""),
            residuals=tuple((value.participant_key, value.status.value,
                             value.residual, value.surface_id)
                            for value in attachment.residuals))),
    )
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False)


def plate_label(node_key):
    return ("Chapa de ligação — Cumeeira" if "APEX" in node_key.upper()
            else "Chapa de ligação — Nó "+node_key)


def ensure_gusset_properties(obj):
    properties = (
        ("App::PropertyInteger", "SchemaVersion", "Identificação"),
        ("App::PropertyString", "StableKey", "Identificação"),
        ("App::PropertyString", "NodeKey", "Identificação"),
        ("App::PropertyBool", "GeneratedByTruss", "Identificação"),
        ("App::PropertyString", "DisplayName", "Identificação"),
        ("App::PropertyLength", "Thickness", "Gusset"),
        ("App::PropertyLength", "EdgeMargin", "Gusset"),
        ("App::PropertyLength", "MemberOverlap", "Gusset"),
        ("App::PropertyEnumeration", "Side", "Gusset"),
        ("App::PropertyEnumeration", "AttachmentMode", "Gusset"),
        ("App::PropertyEnumeration", "ChordContact", "Gusset"),
        ("App::PropertyString", "TransversePlacement", "Gusset"),
        ("App::PropertyLength", "AttachmentOffset", "Gusset"),
        ("App::PropertyString", "AttachmentStatus", "Gusset"),
        ("App::PropertyString", "AttachmentSurface", "Gusset"),
        ("App::PropertyArea", "PlateArea", "Resultados"),
        ("App::PropertyVolume", "Volume", "Resultados"),
        ("App::PropertyLink", "ParentTruss", "Vínculos"),
        ("App::PropertyString", "GenerationStatus", "Geração"),
        ("App::PropertyString", "SourceSignature", "Interno"),
    )
    for kind, name, group in properties:
        if name not in obj.PropertiesList:
            obj.addProperty(kind, name, group)
    current_side = str(getattr(obj, "Side", "Center"))
    obj.Side = ["Center", "FaceA", "FaceB"]
    obj.Side = current_side if current_side in ("Center", "FaceA", "FaceB") else "Center"
    current_mode = str(getattr(obj, "AttachmentMode", "Auto"))
    obj.AttachmentMode = ["Auto", "Outer", "Inner", "Center"]
    obj.AttachmentMode = (current_mode if current_mode in
                          ("Auto", "Outer", "Inner", "Center") else "Auto")
    current_contact = str(getattr(obj, "ChordContact", "Auto"))
    obj.ChordContact = ["Auto", "TrussInterior", "TrussExterior"]
    obj.ChordContact = (current_contact if current_contact in
                        ("Auto", "TrussInterior", "TrussExterior") else "Auto")
    for name in ("SchemaVersion", "StableKey", "NodeKey", "GeneratedByTruss",
                 "Thickness", "EdgeMargin", "MemberOverlap", "Side", "AttachmentMode",
                 "ChordContact", "TransversePlacement",
                 "PlateArea",
                 "AttachmentOffset", "AttachmentStatus", "AttachmentSurface",
                 "Volume", "ParentTruss", "GenerationStatus"):
        obj.setEditorMode(name, 1)
    obj.setEditorMode("SourceSignature", 2)


def apply_gusset_result(obj, parent, outline, shape=None):
    """Apply an already-resolved outline/solid without changing document cardinality."""
    shape = shape if shape is not None else build_gusset_shape(outline)
    proxy = obj.Proxy
    previous = getattr(proxy, "_updating", False)
    proxy._updating = True
    try:
        ensure_gusset_properties(obj)
        obj.SchemaVersion = GUSSET_OBJECT_SCHEMA_VERSION
        obj.StableKey = outline.spec.stable_key
        obj.NodeKey = outline.spec.node_key
        obj.GeneratedByTruss = True
        obj.Thickness = outline.spec.plate_thickness
        obj.EdgeMargin = outline.spec.edge_margin
        obj.MemberOverlap = outline.spec.member_overlap
        obj.Side = outline.spec.side.value
        obj.AttachmentMode = outline.spec.attachment_mode.value
        obj.ChordContact = outline.spec.chord_contact.value
        obj.TransversePlacement = outline.spec.transverse_placement
        attachment = outline.attachment
        obj.AttachmentOffset = attachment.signed_offset if attachment is not None else 0.
        obj.AttachmentStatus = attachment.status if attachment is not None else "NominalLegacy"
        obj.AttachmentSurface = (attachment.governing_surface_id
                                 if attachment is not None else "")
        obj.PlateArea = outline.area
        obj.Volume = shape.Volume
        obj.ParentTruss = parent
        obj.SourceSignature = outline_signature(outline)
        obj.Shape = shape
        obj.GenerationStatus = "Valid"
    finally:
        proxy._updating = previous


class StructuralGussetPlateProxy:
    def __init__(self, obj):
        self._updating = True
        obj.Proxy = self
        ensure_gusset_properties(obj)
        obj.SchemaVersion = GUSSET_OBJECT_SCHEMA_VERSION
        obj.GeneratedByTruss = True
        obj.GenerationStatus = "Pending"
        self._updating = False

    def execute(self, obj):
        if self._updating:
            return
        parent = getattr(obj, "ParentTruss", None)
        if parent is None or not getattr(parent, "AppliedState", ""):
            obj.GenerationStatus = "Pending: treliça de origem indisponível."
            return
        try:
            from .trusses.serialization import decode_state
            from .trusses.realization import build_candidate
            from .trusses.gussets import preliminary_gusset_outlines
            state = decode_state(parent.AppliedState)
            candidate = build_candidate(state["candidate"]["config"])
            outlines, diagnostics = preliminary_gusset_outlines(candidate)
            outline = next((value for value in outlines
                            if value.spec.stable_key == obj.StableKey), None)
            if outline is None:
                message = next((value.message for value in diagnostics
                                if value.node_key == obj.NodeKey),
                               "Chapa não pertence mais ao estado aceito; regenere a treliça.")
                obj.GenerationStatus = "Pending: "+message
                return
            signature = outline_signature(outline)
            expected_volume = outline.area*outline.spec.plate_thickness
            controlled_match = (
                obj.StableKey == outline.spec.stable_key
                and obj.NodeKey == outline.spec.node_key
                and obj.ParentTruss == parent
                and abs(_quantity(obj.Thickness)-outline.spec.plate_thickness) <= 1e-8
                and abs(_quantity(obj.EdgeMargin)-outline.spec.edge_margin) <= 1e-8
                and abs(_quantity(obj.MemberOverlap)-outline.spec.member_overlap) <= 1e-8
                and str(obj.Side) == outline.spec.side.value
                and str(obj.AttachmentMode) == outline.spec.attachment_mode.value
                and str(obj.ChordContact) == outline.spec.chord_contact.value
                and str(obj.TransversePlacement) == outline.spec.transverse_placement
                and abs(_quantity(obj.AttachmentOffset)-(
                    outline.attachment.signed_offset if outline.attachment else 0.)) <= 1e-8
                and obj.AttachmentStatus == (
                    outline.attachment.status if outline.attachment else "NominalLegacy")
                and obj.AttachmentSurface == (
                    outline.attachment.governing_surface_id if outline.attachment else "")
                and abs(_quantity(obj.PlateArea)-outline.area) <= 1e-6
                and abs(_quantity(obj.Volume)-expected_volume) <= max(1e-6, expected_volume*1e-10))
            if (obj.SourceSignature == signature and controlled_match and not obj.Shape.isNull()
                    and obj.Shape.isValid() and obj.Shape.Volume > 0.):
                obj.GenerationStatus = "Valid"
                return
            apply_gusset_result(obj, parent, outline)
        except Exception as exc:
            obj.GenerationStatus = "Erro: "+str(exc)
            App.Console.PrintWarning("Steel Structures: "+str(exc)+"\n")

    def onChanged(self, obj, prop):
        if not getattr(self, "_updating", True) and prop == "DisplayName" and obj.DisplayName:
            obj.Label = obj.DisplayName

    def onDocumentRestored(self, obj):
        self._updating = True
        try:
            ensure_gusset_properties(obj)
        finally:
            self._updating = False
        if obj.SchemaVersion not in (1, GUSSET_OBJECT_SCHEMA_VERSION):
            obj.GenerationStatus = "UnsupportedSchema"

    def dumps(self):
        return None

    def loads(self, state):
        self._updating = False


class StructuralGussetPlateViewProvider:
    def __init__(self, view):
        view.Proxy = self
        view.ShapeColor = GUSSET_COLOR
        view.Transparency = GUSSET_TRANSPARENCY

    def attach(self, view):
        self.ViewObject = view
        self.Object = view.Object

    def updateData(self, obj, prop):
        pass

    def onChanged(self, view, prop):
        pass

    def getDisplayModes(self, view):
        return []

    def getDefaultDisplayMode(self):
        return "Flat Lines"

    def setDisplayMode(self, mode):
        return mode

    def claimChildren(self):
        return []

    def doubleClicked(self, view):
        return True

    def dumps(self):
        return None

    def loads(self, state):
        return None


def create_gusset_plate(document, parent, outline, shape=None):
    obj = document.addObject("Part::FeaturePython", "StructuralGussetPlate")
    StructuralGussetPlateProxy(obj)
    # FreeCADCmd has no ViewObject; the persistent geometry/lifecycle remains
    # fully available and the view provider is attached when a GUI exists.
    if getattr(obj, "ViewObject", None) is not None:
        StructuralGussetPlateViewProvider(obj.ViewObject)
    label = plate_label(outline.spec.node_key)
    obj.DisplayName = label
    obj.Label = label
    apply_gusset_result(obj, parent, outline, shape)
    return obj


__all__ = ["GUSSET_OBJECT_SCHEMA_VERSION", "StructuralGussetPlateProxy",
           "StructuralGussetPlateViewProvider", "apply_gusset_result",
           "create_gusset_plate", "outline_signature", "plate_label"]
