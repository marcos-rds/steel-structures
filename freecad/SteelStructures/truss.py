"""Parametric truss owner: hidden registry, explicit structural regeneration.

Definition -> parent -> StructuralMember -> ordinary role group is the native
DAG. Hidden parent registries are organizational links, not reverse dependencies.
"""
from dataclasses import asdict
import FreeCAD as App
from . import profile_catalog
from .member import create_member
from .member_batch import (apply_result, item_values, lock_controlled,
                           prepared_item,
                           prepare_member, signature, controlled_state, validate_adjustment_dependencies)
from .paths import TRUSS_ICON
from .trusses.models import SCHEMA_VERSION, ROLES, CONTINUITIES
from .trusses.realization import build_candidate, plan_regeneration, reference_frame, input_reference_frame
from .trusses.serialization import encode_state, decode_state, dumps, loads
from .trusses.preset_contracts import PRESETS
from .trusses.drivers import DRIVERS
from .truss_reference import resolve_linked_reference, reference_containers
from .gusset_plate import (apply_gusset_result, create_gusset_plate,
                           outline_signature)

ROLE_LABELS = {"TOP_CHORD": "Banzo superior", "BOTTOM_CHORD": "Banzo inferior",
               "VERTICAL": "Montantes", "DIAGONAL": "Diagonais", "END_POST": "Fechamentos"}
PROPERTY_CONFIG = {"EnvelopeType": "envelope_type", "Span": "span", "Height": "height",
                   "ApexPosition": "apex_position", "PanelCount": "panel_count",
                   "TopologyPreset": "topology_preset", "TopChordContinuity": "top_continuity",
                   "BottomChordContinuity": "bottom_continuity",
                   "LeftEndHeight": "left_end_height", "RightEndHeight": "right_end_height",
                   "LinkEndHeights": "link_end_heights", "ReferenceAlignment": "reference_alignment",
                   "DefaultGussetThickness": "default_gusset_thickness"}


def default_config():
    # Modeling defaults from the existing Gerdau catalog, not member sizing.
    chord = profile_catalog.ref_for_designation('U 4" x 8,04')
    angle = profile_catalog.ref_for_designation('L 40 x 4')
    return dict(envelope_type="Parallel", span=10000., height=2000., apex_position=.5,
                left_end_height=0., right_end_height=0., link_end_heights=True,
                reference_alignment="BottomChord", reference_surface="OuterFace",
                panel_count=6, topology_preset="Pratt", top_continuity="Continuous",
                bottom_continuity="Continuous", left_panels=None, right_panels=None,
                start=[0.,0.,0.], end=[10000.,0.,0.], plane_normal=[0.,-1.,0.],
                connection_intents={}, default_gusset_thickness=10.,
                role_specs={role: dict(profile_ref=asdict(chord if role in ("TOP_CHORD","BOTTOM_CHORD") else angle),
                                      insertion="centroid", rotation=(-90. if role=="TOP_CHORD" else 90. if role=="BOTTOM_CHORD" else 180. if role=="END_POST_LEFT" else 0.),
                                      section_geometry_mode="Detailed", color=([.2,.45,.85] if role in ("TOP_CHORD","BOTTOM_CHORD") else [1.,.8,.15] if role=="DIAGONAL" else [1.,.5,.1]),
                                      assembly="Single",
                                      physical_fit=("None" if role in ("TOP_CHORD", "BOTTOM_CHORD") else "ToChord"),
                                      physical_fit_gap=0.0)
                            for role in ROLES+("END_POST_LEFT","END_POST_RIGHT")})


def _value(value):
    return float(value.Value) if hasattr(value, "Value") else value


def config_from_object(obj, resolve_reference=True):
    config = loads(getattr(obj, "C2Configuration", "") or "{}")
    config.update({key: _value(getattr(obj, prop)) for prop,key in PROPERTY_CONFIG.items()})
    config["panelization_mode"] = str(obj.PanelizationMode)
    origin = obj.Placement.Base
    x = obj.Placement.Rotation.multVec(App.Vector(1,0,0))
    end = origin.add(x*float(config["span"]))
    normal = obj.Placement.Rotation.multVec(App.Vector(0,0,1))
    config.update(start=list(origin), end=list(end), plane_normal=list(normal),
                  role_specs=loads(obj.RoleSpecs), left_panels=obj.LeftPanels,
                  right_panels=obj.RightPanels)
    if config.get("reference_linked"):
        link = getattr(obj, "ReferenceSource", None)
        if not link or link[0] is None:
            if resolve_reference:
                raise ValueError("Fonte vinculada removida; último estado aplicado preservado.")
            config["reference_source"] = ""
        else:
            config["reference_source"] = link[0].Name
    return resolve_linked_reference(obj.Document, config, obj) if resolve_reference else config


def ensure_c2_properties(obj):
    """Additive migration: preserve C1 applied state until a successful apply."""
    fields=(("App::PropertyString","C2Configuration","Interno"),
            ("App::PropertyEnumeration","TopologyMode","Alma"),
            ("App::PropertyEnumeration","ReferenceMode","Referência"),
            ("App::PropertyBool","ReferenceLinked","Referência"),
            ("App::PropertyLinkSub","ReferenceSource","Referência"),
            ("App::PropertyLinkList","ReferenceContainers","Referência"))
    for kind,name,group in fields:
        if name not in obj.PropertiesList: obj.addProperty(kind,name,group)
    for name,options,default in (("TopologyPreset",list(PRESETS),"Warren"),
                               ("PanelizationMode",list(DRIVERS),"ByPanelCount"),
                               ("TopologyMode",["Preset","Custom"],"Preset"),
                               ("ReferenceMode",["TwoPoints","DraftLine","DraftRectangle","ThreePoints"],"TwoPoints")):
        old=str(getattr(obj,name,""))
        setattr(obj,name,options)
        setattr(obj,name,old if old in options else default)
    for name in ("TopologyMode","ReferenceMode","ReferenceLinked"):
        obj.setEditorMode(name,1)
    for name in ("C2Configuration","ReferenceSource","ReferenceContainers"):
        obj.setEditorMode(name,2)
    ensure_support_properties(obj)


def ensure_support_properties(obj):
    """Additive migration: legacy documents keep their accepted bottom reference."""
    fields = (("App::PropertyLength", "LeftEndHeight", "Geometria", 0., "Altura da extremidade esquerda"),
              ("App::PropertyLength", "RightEndHeight", "Geometria", 0., "Altura da extremidade direita"),
              ("App::PropertyBool", "LinkEndHeights", "Geometria", True, "Vincular alturas (esquerda controla direita)"))
    for kind, name, group, default, description in fields:
        if name not in obj.PropertiesList:
            obj.addProperty(kind, name, group, description)
            setattr(obj, name, default)
    if "ReferenceAlignment" not in obj.PropertiesList:
        obj.addProperty("App::PropertyEnumeration", "ReferenceAlignment", "Referência",
                        "Face externa física do banzo inferior ou superior nas extremidades")
        obj.ReferenceAlignment = ["BottomChord", "TopChordSupports"]
        obj.ReferenceAlignment = "BottomChord"
    if "NominalSpan" not in obj.PropertiesList:
        obj.addProperty("App::PropertyLength", "NominalSpan", "Geometria", "Vão nominal calculado do banzo inferior")
        obj.NominalSpan = obj.Span
    obj.setEditorMode("NominalSpan", 1)
    obj.setEditorMode("RightEndHeight", 1 if obj.LinkEndHeights else 0)


def ensure_gusset_registry(obj):
    """Additive C6-B ownership migration; never materializes missing plates."""
    if "GeneratedGussetPlates" not in obj.PropertiesList:
        obj.addProperty("App::PropertyLinkListHidden", "GeneratedGussetPlates", "Interno")
    obj.setEditorMode("GeneratedGussetPlates", 2)


def ensure_gusset_defaults(obj):
    """Additive owner migration for the last accepted per-truss plate default."""
    if "DefaultGussetThickness" not in obj.PropertiesList:
        obj.addProperty("App::PropertyLength", "DefaultGussetThickness", "Gusset")
        obj.DefaultGussetThickness = 10.
    obj.setEditorMode("DefaultGussetThickness", 1)


def set_config(obj, config):
    origin,x,y,z = input_reference_frame(config)
    proxy = obj.Proxy
    previous = proxy._updating
    proxy._updating = True
    try:
        ensure_c2_properties(obj)
        ensure_gusset_defaults(obj)
        for prop,key in PROPERTY_CONFIG.items():
            setattr(obj, prop, config.get(key, {"left_end_height": 0., "right_end_height": 0.,
                    "link_end_heights": True, "reference_alignment": "BottomChord"}.get(key)))
        obj.setEditorMode("RightEndHeight", 1 if obj.LinkEndHeights else 0)
        obj.NominalSpan = config.get("nominal_span", config["span"])
        obj.Placement = App.Placement(App.Vector(*origin), App.Rotation(
            App.Vector(*x), App.Vector(*y), App.Vector(*z), "ZXY"))
        obj.RoleSpecs = dumps(config["role_specs"])
        obj.PanelizationMode = config.get("panelization_mode", "ByPanelCount")
        obj.TopologyMode = config.get("topology_mode", "Preset")
        obj.ReferenceMode = config.get("reference_mode", "TwoPoints")
        obj.ReferenceLinked = config.get("reference_linked", False)
        source = obj.Document.getObject(config.get("reference_source", "")) if config.get("reference_source") else None
        obj.ReferenceSource = (source, [config.get("reference_edge", "Edge1")]) if source is not None and obj.ReferenceLinked else None
        obj.ReferenceContainers = reference_containers(source) if source is not None and obj.ReferenceLinked else []
        excluded=set(PROPERTY_CONFIG.values())|{"start","end","plane_normal","role_specs","left_panels","right_panels"}
        obj.C2Configuration = dumps({k:v for k,v in config.items() if k not in excluded})
    finally:
        proxy._updating = previous


def bound_children(obj, state):
    members = list(obj.GeneratedMembers)
    if len({child.Name for child in members}) != len(members):
        raise ValueError("Registro contém filhos duplicados.")
    result = {}
    for key,name in state["bindings"].items():
        child = obj.Document.getObject(name)
        if (child is None or child not in members or getattr(child, "GenerationOwner", None) != obj
                or getattr(child, "GenerationKey", None) != key):
            raise ValueError("Binding inconsistente: "+key)
        result[key] = child
    if set(state["bindings"].values()) != {child.Name for child in members}:
        raise ValueError("Registro e bindings discordam.")
    return result


def bound_gusset_plates(obj):
    plates = (list(obj.GeneratedGussetPlates)
              if "GeneratedGussetPlates" in obj.PropertiesList else [])
    # Recover generated children whose hidden registry was lost/corrupted. The
    # explicit next apply will either re-register or remove them transactionally.
    for candidate in getattr(getattr(obj, "Document", None), "Objects", ()):
        if (candidate not in plates and getattr(candidate, "ParentTruss", None) == obj
                and getattr(candidate, "GeneratedByTruss", False)
                and "NodeKey" in getattr(candidate, "PropertiesList", ())):
            plates.append(candidate)
    if len({plate.Name for plate in plates}) != len(plates):
        raise ValueError("Registro contém chapas Gusset duplicadas.")
    result = {}
    for plate in plates:
        node_key = getattr(plate, "NodeKey", "")
        if (not node_key or node_key in result or getattr(plate, "ParentTruss", None) != obj
                or getattr(plate, "StableKey", "") != node_key+":gusset-plate"):
            raise ValueError("Binding inconsistente de chapa Gusset: "+getattr(plate, "Name", ""))
        result[node_key] = plate
    return result


def prepare_gusset_plates(candidate):
    """Resolve every pure outline and OCC solid before document mutation."""
    from .trusses.gussets import preliminary_gusset_outlines
    from .trusses.gusset_freecad import build_gusset_shape
    outlines, diagnostics = preliminary_gusset_outlines(candidate)
    if diagnostics:
        raise ValueError(" ".join(dict.fromkeys(value.message for value in diagnostics)))
    result = {}
    for outline in outlines:
        if (outline.attachment is not None
                and outline.attachment.kind == "NominalFallback"):
            continue
        if outline.spec.node_key in result:
            raise ValueError("Mais de uma chapa preliminar foi resolvida para o mesmo NodeKey.")
        result[outline.spec.node_key] = (outline, build_gusset_shape(outline))
    return result


def conflicts_for(obj, children, candidate):
    conflicts = {}
    after = {item.key for item in candidate.items}
    groups = list(obj.RoleGroups)
    groups += [child for group in groups for child in group.Group
               if getattr(child, "AssemblyInterconnectorGroup", False)]
    for key,child in children.items():
        if child.ControlledState and controlled_state(child) != child.ControlledState:
            conflicts[key] = "Propriedade controlada alterada diretamente: "+child.Label
        if child.ExpressionEngine:
            conflicts[key] = "Expressões em membro gerado exigem revisão: "+child.Label
        if key not in after:
            from .fitting.freecad_adapter import has_manual_adjustment
            if any(ref not in groups for ref in child.InList):
                conflicts[key] = "Filho removido possui referências externas: "+child.Label
            if (child.StartExtension.Value or child.EndExtension.Value
                    or child.OffsetX.Value or child.OffsetY.Value
                    or has_manual_adjustment(child)):
                conflicts[key] = "Remoção descartaria extensões/ajustes manuais: "+child.Label
    return conflicts


def resynchronize_accepted_snapshots(obj):
    """Repair snapshots made stale by document Undo/Redo, without hiding edits.

    FreeCAD restores persistent properties transactionally, while Python proxy
    caches are not part of that transaction. A child is resynchronized only
    when its current controlled inputs exactly match the realization described
    by the currently restored AppliedState. A real external edit therefore
    remains different and continues to be reported by ``conflicts_for``.
    """
    if obj is None or not getattr(obj, "AppliedState", ""):
        return 0
    state = decode_state(obj.AppliedState)
    candidate = build_candidate(state["candidate"]["config"])
    children = bound_children(obj, state)
    prepared = prepare_batch(candidate, children)
    repaired = 0
    for item in candidate.items:
        child = children[item.key]
        current = controlled_state(child)
        expected_color = tuple(item.spec.color)
        if len(tuple(child.ViewObject.ShapeColor)) == 4:
            expected_color += (1.,)
        expected = controlled_state(prepared[item.key], expected_color)
        if current != expected:
            continue
        if child.ControlledState != current:
            child.ControlledState = current
            repaired += 1
        child.Proxy._last_generated_result = prepared[item.key]
        child.Proxy._generated_prepared_signature = None
        lock_controlled(child)
    return repaired


def prepare_batch(candidate, children):
    validate_adjustment_dependencies(children.values())
    prepared = {}
    for item in candidate.items:
        child = children.get(item.key)
        values = item_values(item)
        if child is not None and hasattr(child, "AssemblySectionTransform"):
            values.setdefault("AssemblySectionTransform", "")  # Double -> Single clears previous T.
        prepared[item.key] = prepared_item(item, child, values)
    if (candidate.config.get("reference_alignment") == "TopChordSupports"
            or candidate.config.get("reference_surface") == "OuterFace"):
        from .trusses.support_alignment_freecad import validate_support_alignment
        validate_support_alignment(candidate, prepared)
    return prepared


def apply_existing_batch(obj, candidate, children, prepared,
                         gusset_plates=None, prepared_gussets=None):
    """No OCC after the first mutation. Rebuild backups from inputs, never child.Shape."""
    gusset_plates = gusset_plates or {}
    prepared_gussets = prepared_gussets or {}
    backups = {key: getattr(child.Proxy, "_last_generated_result", None) or prepare_member(child)
               for key,child in children.items()}
    colors = {key: tuple(child.ViewObject.ShapeColor) for key,child in children.items()}
    fit_fields = ("PhysicalFitPlan", "PhysicalFitAutoState", "PhysicalFitStatus")
    fit_backups = {key: {name: getattr(child, name) for name in fit_fields
                         if name in child.PropertiesList} for key, child in children.items()}
    plate_fields = ("SchemaVersion", "StableKey", "NodeKey", "GeneratedByTruss", "Thickness",
                    "EdgeMargin", "MemberOverlap", "Side", "AttachmentMode",
                    "ChordContact", "TransversePlacement", "AttachmentOffset",
                    "AttachmentStatus", "AttachmentSurface", "PlateArea", "Volume", "ParentTruss",
                    "GenerationStatus", "SourceSignature")
    plate_backups = {key: dict(Shape=plate.Shape.copy(), **{
        name: getattr(plate, name) for name in plate_fields if name in plate.PropertiesList})
        for key, plate in gusset_plates.items()}
    owner_fields = ("AppliedState", "LeftPanels", "RightPanels", "GeneratedMembers",
                    "GeneratedGussetPlates", "NeedsRegeneration",
                    "GenerationState", "GenerationMessage", "SchemaVersion", "Placement", "RoleSpecs") + tuple(PROPERTY_CONFIG)
    owner_fields += tuple(name for name in ("NominalSpan", "C2Configuration", "TopologyMode", "ReferenceMode", "ReferenceLinked",
                                           "ReferenceSource", "ReferenceContainers", "PanelizationMode") if hasattr(obj,name))
    owner_backup = {name: getattr(obj, name) for name in owner_fields}
    try:
        for item in candidate.items:
            apply_result(children[item.key], prepared[item.key], item.spec.color)
        for child in children.values():
            child.ControlledState = controlled_state(child)
        for node_key, plate in gusset_plates.items():
            outline, shape = prepared_gussets[node_key]
            apply_gusset_result(plate, obj, outline, shape)
        set_config(obj, candidate.config)
        accept_state(obj, candidate, children, gusset_plates)
    except Exception:
        for key,child in children.items():
            apply_result(child, backups[key], colors[key])
            for name, value in fit_backups[key].items():
                setattr(child, name, value)
            child.ControlledState = controlled_state(child)
        for key, plate in gusset_plates.items():
            proxy = plate.Proxy
            previous = getattr(proxy, "_updating", False)
            proxy._updating = True
            try:
                for name, value in plate_backups[key].items():
                    setattr(plate, name, value)
            finally:
                proxy._updating = previous
        for name,value in owner_backup.items():
            setattr(obj, name, value)
        raise


def restore_copied_children(obj):
    """Complete a shallow native copy, without copying external references.

    Draft copies this FeaturePython without dependencies. Only an exact copy
    of another live truss's registries is eligible; ordinary restore and damaged
    or partially copied graphs must keep their existing validation contract.
    The caller's native copy transaction owns all newly created objects.
    """
    members = list(obj.GeneratedMembers)
    if not members:
        return
    source = getattr(members[0], "GenerationOwner", None)
    if (source is None or source == obj or source.Document != obj.Document
            or not isinstance(getattr(source, "Proxy", None), StructuralTrussProxy)
            or any(getattr(child, "GenerationOwner", None) != source for child in members)
            or members != list(source.GeneratedMembers)
            or list(obj.RoleGroups) != list(source.RoleGroups)
            or list(obj.GeneratedGussetPlates) != list(source.GeneratedGussetPlates)
            or obj.AppliedState != source.AppliedState):
        return
    state = decode_state(obj.AppliedState)
    bound_children(source, state)
    plates = list(bound_gusset_plates(source).values())
    groups = list(obj.RoleGroups)
    subgroups = []
    for group in groups:
        for child in group.Group:
            if child in members:
                continue
            if (not getattr(child, "AssemblyInterconnectorGroup", False)
                    or any(member not in members for member in child.Group)):
                raise ValueError("Grupo da treliça contém objetos externos; cópia não aplicada.")
            if child not in subgroups:
                subgroups.append(child)
    originals = members + plates + groups + subgroups
    if len(set(originals)) != len(originals):
        raise ValueError("Agregado da treliça contém registros duplicados.")
    before = {child.Name for child in obj.Document.Objects}
    try:
        copied = obj.Document.copyObject(originals, False)
        mapping = dict(zip(originals, copied))
        if len(copied) != len(originals):
            raise ValueError("Cópia incompleta dos filhos da treliça.")
        for child in members:
            mapping[child].GenerationOwner = obj
        for plate in plates:
            mapping[plate].ParentTruss = obj
        # copyObject copies document properties, but not the generated children's
        # presentation. In particular, default colors would invalidate their
        # accepted ControlledState. Preserve them rather than accepting new inputs.
        for original, target in mapping.items():
            for name in ("ShapeColor", "LineColor", "PointColor", "Transparency",
                         "LineWidth", "PointSize", "DrawStyle", "DisplayMode"):
                if hasattr(original.ViewObject, name) and hasattr(target.ViewObject, name):
                    setattr(target.ViewObject, name, getattr(original.ViewObject, name))
        # Group visibility propagates to its contents; restore individual states last.
        for original in groups + subgroups + members + plates:
            mapping[original].ViewObject.Visibility = original.ViewObject.Visibility
        bindings = {child.GenerationKey: child.Name for child in copied
                    if getattr(child, "GenerationOwner", None) == obj}
        if set(bindings) != set(state["bindings"]):
            raise ValueError("Cópia inconsistente dos bindings da treliça.")
        state["bindings"] = bindings
        obj.GeneratedMembers = [mapping[child] for child in members]
        obj.GeneratedGussetPlates = [mapping[plate] for plate in plates]
        obj.RoleGroups = [mapping[group] for group in groups]
        obj.AppliedState = dumps(state)
        obj.Proxy._copied_names = {child.Name: mapping[child].Name for child in originals}
        # Native copying can restore the ViewProvider before this callback.
        # Its persisted visibility cache must follow the newly copied children.
        view_proxy = getattr(obj.ViewObject, "Proxy", None)
        if hasattr(view_proxy, "_remap_hidden_children"):
            view_proxy._remap_hidden_children()
    except Exception:
        obj.GeneratedMembers = members
        obj.GeneratedGussetPlates = list(source.GeneratedGussetPlates)
        obj.RoleGroups = groups
        obj.AppliedState = source.AppliedState
        for child in reversed(list(obj.Document.Objects)):
            if child.Name not in before:
                obj.Document.removeObject(child.Name)
        raise


class StructuralTrussProxy:
    def __init__(self, obj):
        self._updating = True
        obj.Proxy = self
        properties = (("App::PropertyInteger", "SchemaVersion", "Sistema"),
                      ("App::PropertyString", "DisplayName", "Identificação"),
                      ("App::PropertyPlacement", "Placement", "Referência"),
                      ("App::PropertyEnumeration", "EnvelopeType", "Geometria"),
                      ("App::PropertyLength", "Span", "Geometria"),
                      ("App::PropertyLength", "Height", "Geometria"),
                      ("App::PropertyFloat", "ApexPosition", "Geometria"),
                      ("App::PropertyEnumeration", "PanelizationMode", "Geometria"),
                      ("App::PropertyInteger", "PanelCount", "Geometria"),
                      ("App::PropertyInteger", "LeftPanels", "Geometria"),
                      ("App::PropertyInteger", "RightPanels", "Geometria"),
                      ("App::PropertyEnumeration", "TopologyPreset", "Alma"),
                      ("App::PropertyEnumeration", "TopChordContinuity", "Continuidade"),
                      ("App::PropertyEnumeration", "BottomChordContinuity", "Continuidade"),
                      ("App::PropertyBool", "NeedsRegeneration", "Geração"),
                      ("App::PropertyString", "GenerationState", "Geração"),
                      ("App::PropertyString", "GenerationMessage", "Geração"),
                      ("App::PropertyString", "RoleSpecs", "Interno"),
                      ("App::PropertyString", "AppliedState", "Interno"),
                      ("App::PropertyLinkListHidden", "GeneratedMembers", "Interno"),
                      ("App::PropertyLinkListHidden", "RoleGroups", "Interno"))
        for kind,name,group in properties:
            obj.addProperty(kind, name, group)
        obj.SchemaVersion = SCHEMA_VERSION
        obj.EnvelopeType = ["Parallel", "DuoPitch"]
        obj.PanelizationMode = ["ByPanelCount"]
        obj.TopologyPreset = ["Warren", "Pratt"]
        obj.TopChordContinuity = list(CONTINUITIES)
        obj.BottomChordContinuity = list(CONTINUITIES)
        obj.DisplayName = "Treliça"
        obj.GenerationState = "Pending"
        for name in ("SchemaVersion", "LeftPanels", "RightPanels", "NeedsRegeneration", "GenerationState",
                     "GenerationMessage", "PanelizationMode", "TopologyPreset", "EnvelopeType",
                     "PanelCount", "TopChordContinuity", "BottomChordContinuity"):
            obj.setEditorMode(name, 1)
        for name in ("RoleSpecs", "AppliedState", "GeneratedMembers", "RoleGroups"):
            obj.setEditorMode(name, 2)
        ensure_c2_properties(obj)
        ensure_gusset_registry(obj)
        ensure_gusset_defaults(obj)
        self._updating = False

    def execute(self, obj):
        if self._updating or not obj.AppliedState:
            return
        self._updating = True
        try:
            if obj.SchemaVersion not in (1, 2, 3, 4, SCHEMA_VERSION):
                raise ValueError("SchemaVersion não suportada.")
            state = decode_state(obj.AppliedState)
            applied = build_candidate(state["candidate"]["config"])
            requested = config_from_object(obj)
            candidate = build_candidate(requested, applied)
            children = bound_children(obj, state)
            gusset_plates = bound_gusset_plates(obj)
            from .trusses.gussets import preliminary_gusset_outlines
            outlines, plate_diagnostics = preliminary_gusset_outlines(candidate)
            if plate_diagnostics:
                raise ValueError(" ".join(dict.fromkeys(d.message for d in plate_diagnostics)))
            desired_gussets = {value.spec.node_key: value for value in outlines
                               if (value.attachment is None
                                   or value.attachment.kind != "NominalFallback")}
            plan = plan_regeneration(candidate, applied, state["bindings"], conflicts_for(obj, children, candidate))
            if plan.conflicts:
                raise ValueError("; ".join(action.reason for action in plan.conflicts))
            if plan.structural:
                support_keys = ("left_end_height", "right_end_height", "link_end_heights", "reference_alignment")
                structural_keys = ("envelope_type", "topology_mode", "topology_preset", "panel_count",
                                   "top_continuity", "bottom_continuity", "role_specs")
                if (candidate.config["envelope_type"] == "DuoPitch"
                        and any(candidate.config.get(k) != applied.config.get(k) for k in support_keys)
                        and requested.get("custom_topology") == applied.config.get("custom_topology")
                        and all(candidate.config.get(k) == applied.config.get(k) for k in structural_keys)):
                    # Reuse the atomic preparation/application path. Native recompute
                    # owns this change; never nest a transaction or recompute here.
                    apply_truss(obj.Document, candidate.config, obj, _recompute=False, _transaction=False)
                    return
                obj.NeedsRegeneration = True
                obj.GenerationState = "Pending"
                obj.GenerationMessage = "Alteração estrutural pendente. Dê duplo clique na treliça e confirme no Gerador."
                return
            if set(gusset_plates) != set(desired_gussets):
                obj.NeedsRegeneration = True
                obj.GenerationState = "Pending"
                obj.GenerationMessage = "Alteração de chapas pendente. Confirme no Gerador."
                return
            plates_changed = any(gusset_plates[key].SourceSignature != outline_signature(outline)
                                 for key, outline in desired_gussets.items())
            if any(action.action != "UNCHANGED" for action in plan.actions) or plates_changed:
                prepared = prepare_batch(candidate, children)
                prepared_gussets = prepare_gusset_plates(candidate)
                apply_existing_batch(obj, candidate, children, prepared,
                                     gusset_plates, prepared_gussets)
            obj.NeedsRegeneration = False
            obj.GenerationState = "Valid"
            obj.GenerationMessage = "; ".join(candidate.warnings)
        except Exception as exc:
            obj.NeedsRegeneration = True
            obj.GenerationState = "Conflict"
            obj.GenerationMessage = str(exc)
        finally:
            self._updating = False

    def onChanged(self, obj, prop):
        if getattr(self, "_updating", True):
            return
        if prop == "DisplayName" and obj.DisplayName:
            obj.Label = obj.DisplayName
        if prop in ("LeftEndHeight", "RightEndHeight", "LinkEndHeights") and hasattr(obj, "LinkEndHeights"):
            self._updating = True
            try:
                if obj.LinkEndHeights:
                    obj.RightEndHeight = obj.LeftEndHeight
                obj.setEditorMode("RightEndHeight", 1 if obj.LinkEndHeights else 0)
            finally:
                self._updating = False

    def onDocumentRestored(self, obj):
        self._updating = True
        try:
            ensure_c2_properties(obj)
            ensure_gusset_registry(obj)
            ensure_gusset_defaults(obj)
            restore_copied_children(obj)
        finally:
            self._updating = False
        for name in ("TopologyPreset", "EnvelopeType", "PanelCount", "TopChordContinuity",
                     "BottomChordContinuity", "PanelizationMode", "LeftPanels", "RightPanels"):
            obj.setEditorMode(name, 1)
        if obj.SchemaVersion not in (1, 2, 3, 4, SCHEMA_VERSION):
            obj.GenerationState = "UnsupportedSchema"
            obj.NeedsRegeneration = True

    def dumps(self):
        return None

    def loads(self, state):
        self._updating = False


class StructuralTrussViewProvider:
    def __init__(self, view):
        view.Proxy = self
        self.attach(view)

    def attach(self, view):
        from pivy import coin
        self.Object = view.Object
        # App::FeaturePython has no built-in display mode. An empty mode makes
        # native isVisible()/Space work without adding any aggregate geometry.
        if view.SwitchNode.getNumChildren() == 0:
            view.addDisplayMode(coin.SoGroup(), "Group")
        if not hasattr(self, "_hidden_children"):
            self._hidden_children = {}
        self._remap_hidden_children()
        self._visibility_updating = False

    def _remap_hidden_children(self):
        owner = getattr(self, "Object", None)
        mapping = getattr(getattr(owner, "Proxy", None), "_copied_names", {})
        self._hidden_children = {mapping.get(name, name): visible
                                 for name, visible in self._hidden_children.items()}

    def getDisplayModes(self, view):
        return ["Group"]

    def getDefaultDisplayMode(self):
        return "Group"

    def setDisplayMode(self, mode):
        return "Group"

    def onChanged(self, view, prop):
        if prop != "Visibility" or getattr(self, "_visibility_updating", False):
            return
        self._visibility_updating = True
        try:
            children = ([child for child in getattr(view.Object, "GeneratedMembers", ())
                         if getattr(child, "GenerationOwner", view.Object) == view.Object]+
                        [child for child in getattr(view.Object, "GeneratedGussetPlates", ())
                         if getattr(child, "ParentTruss", view.Object) == view.Object])
            if not view.Visibility:
                if not hasattr(self, "_hidden_children"):
                    self._hidden_children = {}
                for child in children:
                    self._hidden_children.setdefault(child.Name, bool(child.ViewObject.Visibility))
                    child.ViewObject.Visibility = False
            else:
                previous = getattr(self, "_hidden_children", {})
                for child in children:
                    if child.Name in previous:
                        child.ViewObject.Visibility = previous[child.Name]
                self._hidden_children = {}
        finally:
            self._visibility_updating = False

    def getIcon(self):
        return TRUSS_ICON

    def claimChildren(self):
        return (list(self.Object.RoleGroups)+
                list(getattr(self.Object, "GeneratedGussetPlates", ())))

    def onDelete(self, view, subelements):
        """Remove this aggregate in the native Delete/Undo transaction.

        Ownership checks protect an independently copied truss, including a
        stale registry. Never recompute while FreeCAD is removing objects.
        """
        owner = view.Object
        document = owner.Document
        members = [child for child in owner.GeneratedMembers
                   if getattr(child, "GenerationOwner", None) == owner]
        plates = [child for child in getattr(owner, "GeneratedGussetPlates", ())
                  if getattr(child, "ParentTruss", None) == owner]
        owned = set(members+plates)
        groups = []
        for group in owner.RoleGroups:
            if any(other != owner and group in getattr(other, "RoleGroups", ())
                   for other in document.Objects):
                continue
            subgroups = [child for child in group.Group
                         if getattr(child, "AssemblyInterconnectorGroup", False)
                         and all(member in owned for member in child.Group)]
            # A role group containing unrelated objects is not ours to delete.
            if all(child in owned or child in subgroups for child in group.Group):
                groups.extend(subgroups)
                groups.append(group)
        for child in dict.fromkeys(members+plates+groups):
            document.removeObject(child.Name)
        return True

    def doubleClicked(self, view):
        from .interactive.truss_controller import open_truss_panel
        try:
            open_truss_panel(view.Object.Document, view.Object)
        except Exception as exc:
            # FreeCAD falls back to the default Label editor when an object
            # double-click handler escapes or returns false. A truss always
            # owns this gesture, including when its candidate has a diagnostic.
            App.Console.PrintWarning(
                "Steel Structures: não foi possível abrir o Gerador de Treliças: "
                + str(exc) + "\n"
            )
        return True

    def setupContextMenu(self, view, menu):
        action = menu.addAction("Atualizar Treliça")
        action.triggered.connect(lambda: self.doubleClicked(view))

    def dumps(self):
        return {"hidden_children": getattr(self, "_hidden_children", {})}

    def loads(self, state):
        self._hidden_children = dict((state or {}).get("hidden_children", {}))
        self._remap_hidden_children()
        self._visibility_updating = False


def accept_state(obj, candidate, children, gusset_plates=None):
    obj.GeneratedMembers = [children[key] for key in sorted(children)]
    if gusset_plates is not None:
        ensure_gusset_registry(obj)
        obj.GeneratedGussetPlates = [gusset_plates[key] for key in sorted(gusset_plates)]
    encoded = encode_state(candidate, {key: children[key].Name for key in sorted(children)})
    obj.SchemaVersion = decode_state(encoded)["schema_version"]
    obj.AppliedState = encoded
    obj.LeftPanels, obj.RightPanels = candidate.stations.left_panels, candidate.stations.right_panels
    obj.NeedsRegeneration = False
    obj.GenerationState = "Valid"
    obj.GenerationMessage = "; ".join(candidate.warnings)


def snapshot_regeneration(obj, children, plates):
    """Detached rollback state for structural changes inside native recompute.

    Native recompute cannot open a nested transaction. Retain the original
    objects until the candidate is validated, including group membership and
    enum options changed by profile application. Links retain object identity.
    """
    objects = [obj] + list(children.values()) + list(plates.values())
    for group in obj.RoleGroups:
        objects.append(group)
        objects.extend(child for child in group.Group
                       if getattr(child, "AssemblyInterconnectorGroup", False))
    def detached(value):
        if isinstance(value, list):
            return list(value)
        if isinstance(value, dict):
            return dict(value)
        if hasattr(value, "Value"):
            return value.Value
        copy = getattr(value, "copy", None)
        return copy() if callable(copy) else value
    snapshots = []
    for current in dict.fromkeys(objects):
        values, enums, modes = {}, {}, {}
        for name in current.PropertiesList:
            if name in ("Proxy", "ExpressionEngine"):
                continue
            values[name] = detached(getattr(current, name))
            if current.getTypeIdOfProperty(name) == "App::PropertyEnumeration":
                enums[name] = list(current.getEnumerationsOfProperty(name))
            mode = current.getEditorMode(name)
            modes[name] = (mode if isinstance(mode, int) else
                           int("ReadOnly" in mode) + 2*int("Hidden" in mode))
        view = current.ViewObject
        view_values = {name: detached(getattr(view, name)) for name in
                       ("Visibility", "ShapeColor", "LineColor", "PointColor", "Transparency",
                        "LineWidth", "PointSize", "DrawStyle", "DisplayMode") if hasattr(view, name)}
        caches = []
        for proxy in (getattr(current, "Proxy", None), getattr(view, "Proxy", None)):
            if hasattr(proxy, "__dict__"):
                caches.append((proxy, {key: detached(value) for key, value in proxy.__dict__.items()}))
        snapshots.append((current, values, enums, modes, view_values, caches))
    return {"names": {value.Name for value in obj.Document.Objects}, "objects": snapshots}


def restore_regeneration(document, snapshot):
    """Restore without recompute; original objects have not been removed yet."""
    proxies = [(proxy, values) for record in snapshot["objects"] for proxy, values in record[-1]]
    for proxy, _ in proxies:
        if hasattr(proxy, "_updating"):
            proxy._updating = True
        if hasattr(proxy, "_visibility_updating"):
            proxy._visibility_updating = True
    try:
        for current, values, enums, modes, _view_values, _caches in snapshot["objects"]:
            for name in tuple(current.PropertiesList):
                if name not in values and name not in ("Proxy", "ExpressionEngine"):
                    current.removeProperty(name)
            for name, choices in enums.items():
                setattr(current, name, choices)
            for name, value in values.items():
                setattr(current, name, value)
            for name, mode in modes.items():
                current.setEditorMode(name, mode)
        # Group visibility propagates: restore individual visibility last.
        for current, _values, _enums, _modes, view_values, _caches in snapshot["objects"]:
            for name, value in view_values.items():
                if name != "Visibility":
                    setattr(current.ViewObject, name, value)
        groups = [record for record in snapshot["objects"] if "Group" in record[1]]
        others = [record for record in snapshot["objects"] if "Group" not in record[1]]
        for current, _values, _enums, _modes, view_values, _caches in groups + others:
            if "Visibility" in view_values:
                current.ViewObject.Visibility = view_values["Visibility"]
        for current in reversed(list(document.Objects)):
            if current.Name not in snapshot["names"]:
                document.removeObject(current.Name)
    finally:
        for proxy, values in proxies:
            proxy.__dict__.clear()
            proxy.__dict__.update(values)


def apply_truss(document, config, obj=None, *, _recompute=True, _transaction=True):
    """Explicit one-transaction create/regenerate; one final document recompute."""
    config = resolve_linked_reference(document, config, obj)
    state = decode_state(obj.AppliedState) if obj is not None else None
    applied = build_candidate(state["candidate"]["config"]) if state else None
    candidate = build_candidate(config, applied)
    children = bound_children(obj, state) if state else {}
    gusset_plates = bound_gusset_plates(obj) if state else {}
    conflicts = conflicts_for(obj, children, candidate) if obj else {}
    plan = plan_regeneration(candidate, applied, state["bindings"] if state else {}, conflicts)
    if plan.conflicts:
        raise ValueError("; ".join(a.reason for a in plan.conflicts))
    prepared = prepare_batch(candidate, children)
    prepared_gussets = prepare_gusset_plates(candidate)
    source = document.getObject(config.get("reference_source", "")) if config.get("reference_source") else None
    source_visibility = bool(source.ViewObject.Visibility) if source is not None else None
    rollback = snapshot_regeneration(obj, children, gusset_plates) if obj is not None and not _transaction else None
    obsolete = []
    if _transaction:
        document.openTransaction("Atualizar Treliça" if obj else "Criar Treliça")
    try:
        if obj is None:
            obj = document.addObject("App::FeaturePython", "StructuralTruss")
            StructuralTrussProxy(obj)
            StructuralTrussViewProvider(obj.ViewObject)
            obj.DisplayName = obj.Label = "Treliça"+obj.Name.removeprefix("StructuralTruss")
        ensure_gusset_registry(obj)
        obj.Proxy._updating = True
        set_config(obj, candidate.config)
        result = {}
        for item in candidate.items:
            child = children.get(item.key)
            if child is None:
                values = item_values(item)
                child = create_member(document, values["StartPoint"], values["EndPoint"], values["Profile"],
                                      insertion=values["Insertion"], rotation=values["Rotation"],
                                      section_geometry_mode=item.spec.section_geometry_mode,
                                      display_name=ROLE_LABELS[item.role], recompute=False)
                child.addProperty("App::PropertyLink", "GenerationOwner", "Geração")
                child.addProperty("App::PropertyString", "GenerationKey", "Geração")
                child.addProperty("App::PropertyString", "GenerationStatus", "Geração")
                child.addProperty("App::PropertyString", "ControlledState", "Interno")
                child.setEditorMode("ControlledState", 2)
                child.setEditorMode("GenerationStatus", 1)
                child.GenerationOwner, child.GenerationKey = obj, item.key
            for name, value in (("RunKey", item.run_key), ("AssemblyKey", item.assembly_key),
                                ("ComponentKey", item.component_key),
                                ("AssemblyElementKind", item.element_kind),
                                ("InterconnectorKey", item.interconnector_key),
                                ("InterconnectorSlotKey", dumps(item.slot_key) if item.slot_key else ""),
                                ("GeneratedElementKey", item.generated_element_key or item.component_key)):
                if name not in child.PropertiesList:
                    child.addProperty("App::PropertyString", name, "Geração")
                setattr(child, name, value)
                child.setEditorMode(name, 1)
            if item.spec.assembly != "Single" or getattr(child, "AssemblySectionTransform", ""):
                from .trusses.assemblies import component_label
                child.DisplayName = child.Label = component_label(item, candidate.runs)
            apply_result(child, prepared[item.key], item.spec.color)
            child.ControlledState = controlled_state(child)
            result[item.key] = child
        plate_result = {}
        for node_key, (outline, shape) in prepared_gussets.items():
            plate = gusset_plates.get(node_key)
            if plate is None:
                plate = create_gusset_plate(document, obj, outline, shape)
            else:
                apply_gusset_result(plate, obj, outline, shape)
            plate_result[node_key] = plate
        groups = {getattr(group, "TrussRole", ""): group for group in obj.RoleGroups}
        for role in ROLES:
            members = [result[i.key] for i in candidate.items if i.role == role]
            if not members and role not in groups:
                continue
            if role not in groups:
                group = document.addObject("App::DocumentObjectGroup", "TrussRoleGroup")
                group.addProperty("App::PropertyString", "TrussRole", "Geração")
                group.TrussRole = role
                group.Label = ROLE_LABELS[role]
                group.setEditorMode("TrussRole", 2)
                groups[role] = group
            connectors = [result[i.key] for i in candidate.items if i.role == role and i.element_kind == "Interconnector"]
            subgroup = next((g for g in groups[role].Group if getattr(g, "AssemblyInterconnectorGroup", False)), None)
            if connectors:
                if subgroup is None:
                    subgroup = document.addObject("App::DocumentObjectGroup", "TrussInterconnectors")
                    subgroup.addProperty("App::PropertyBool", "AssemblyInterconnectorGroup", "Geração")
                    subgroup.AssemblyInterconnectorGroup = True
                    subgroup.setEditorMode("AssemblyInterconnectorGroup", 2)
                    subgroup.Label = "Interconectores"
                subgroup.Group = connectors
                groups[role].Group = [m for m in members if m not in connectors]+[subgroup]
                if not groups[role].ViewObject.Visibility:
                    subgroup.ViewObject.Visibility = False
                    for child in connectors:
                        child.ViewObject.Visibility = False
            else:
                groups[role].Group = members
                if subgroup is not None:
                    obsolete.append(subgroup)
        obj.RoleGroups = [groups[role] for role in ROLES if role in groups]
        for key,child in children.items():
            if key not in result:
                obsolete.append(child)
        for node_key, plate in gusset_plates.items():
            if node_key not in plate_result:
                obsolete.append(plate)
        accept_state(obj, candidate, result, plate_result)
        if not obj.ViewObject.Visibility:
            obj.ViewObject.Proxy.onChanged(obj.ViewObject, "Visibility")
        if _recompute:
            document.recompute()
        for child in result.values():
            if ("Invalid" in child.State or child.Shape.isNull() or not child.Shape.isValid()
                    or child.Shape.Volume <= 0 or child.GenerationStatus != "Valid"):
                raise ValueError("Falha ao aplicar membro: "+child.Name)
        for plate in plate_result.values():
            expected_volume = _value(plate.PlateArea)*_value(plate.Thickness)
            if ("Invalid" in plate.State or plate.Shape.isNull() or not plate.Shape.isValid()
                    or plate.Shape.Volume <= 0 or plate.GenerationStatus != "Valid"
                    or abs(plate.Shape.Volume-expected_volume) > max(1e-5, expected_volume*1e-9)
                    or abs(_value(plate.Volume)-plate.Shape.Volume) > max(1e-5, plate.Shape.Volume*1e-9)):
                raise ValueError("Falha ao aplicar chapa Gusset: "+plate.Name)
        # Deletion is the final irreversible step in the native-recompute path;
        # every candidate solid and registry has already passed validation.
        for child in obsolete:
            document.removeObject(child.Name)
        obj.Proxy._updating = False
        if source is not None:
            source.ViewObject.Visibility = False
        if _transaction:
            document.commitTransaction()
        return obj
    except Exception:
        if rollback is not None:
            restore_regeneration(document, rollback)
        if obj is not None:
            obj.Proxy._updating = False
        if _transaction:
            document.abortTransaction()
        for child in children.values():
            restored = document.getObject(child.Name)
            if restored is not None:
                restored.Proxy._generated_prepared_signature = None
                restored.Proxy._last_generated_result = None
        if source is not None and source_visibility is not None:
            source.ViewObject.Visibility = source_visibility
        if _recompute:
            document.recompute()
        raise
