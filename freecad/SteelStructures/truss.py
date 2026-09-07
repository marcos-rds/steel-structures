"""Parametric truss owner: hidden registry, explicit structural regeneration.

Definition -> parent -> StructuralMember -> ordinary role group is the native
DAG. Hidden parent registries are organizational links, not reverse dependencies.
"""
from dataclasses import asdict
import math
import FreeCAD as App
from . import profile_catalog
from .member import create_member
from .member_adjustment_reference import unpack_link_sub, would_create_adjustment_cycle
from .member_batch import (CONTROLLED, apply_result, item_values, lock_controlled,
                           prepare_member, signature)
from .paths import TRUSS_ICON
from .trusses.models import SCHEMA_VERSION, ROLES, CONTINUITIES
from .trusses.realization import build_candidate, plan_regeneration, reference_frame
from .trusses.serialization import encode_state, decode_state, dumps, loads
from .trusses.preset_contracts import PRESETS
from .trusses.drivers import DRIVERS
from .truss_reference import resolve_linked_reference, reference_containers

ROLE_LABELS = {"TOP_CHORD": "Banzo superior", "BOTTOM_CHORD": "Banzo inferior",
               "VERTICAL": "Montantes", "DIAGONAL": "Diagonais", "END_POST": "Fechamentos"}
PROPERTY_CONFIG = {"EnvelopeType": "envelope_type", "Span": "span", "Height": "height",
                   "ApexPosition": "apex_position", "PanelCount": "panel_count",
                   "TopologyPreset": "topology_preset", "TopChordContinuity": "top_continuity",
                   "BottomChordContinuity": "bottom_continuity"}


def default_config():
    # Modeling defaults from the existing Gerdau catalog, not member sizing.
    chord = profile_catalog.ref_for_designation('U 4" x 8,04')
    angle = profile_catalog.ref_for_designation('L 40 x 4')
    return dict(envelope_type="Parallel", span=10000., height=2000., apex_position=.5,
                panel_count=6, topology_preset="Warren", top_continuity="Continuous",
                bottom_continuity="Continuous", left_panels=None, right_panels=None,
                start=[0.,0.,0.], end=[10000.,0.,0.], plane_normal=[0.,-1.,0.],
                role_specs={role: dict(profile_ref=asdict(chord if role in ("TOP_CHORD","BOTTOM_CHORD") else angle),
                                      insertion="centroid", rotation=(-90. if role=="TOP_CHORD" else 90. if role=="BOTTOM_CHORD" else 180. if role=="END_POST_LEFT" else 0.),
                                      section_geometry_mode="Detailed", color=([.2,.45,.85] if role in ("TOP_CHORD","BOTTOM_CHORD") else [1.,.8,.15] if role=="DIAGONAL" else [1.,.5,.1]),
                                      assembly="Single", physical_fit="None")
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


def set_config(obj, config):
    origin,x,y,z = reference_frame(config)
    proxy = obj.Proxy
    previous = proxy._updating
    proxy._updating = True
    try:
        ensure_c2_properties(obj)
        for prop,key in PROPERTY_CONFIG.items():
            setattr(obj, prop, config[key])
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


def controlled_state(child):
    result = {}
    for name in CONTROLLED:
        value = getattr(child, name)
        if isinstance(value, App.Vector):
            value = [round(v, 8) for v in value]
        elif hasattr(value, "Value"):
            value = round(float(value.Value), 8)
        else:
            value = str(value)
        result[name] = value
    result["Color"] = [math.floor(v*255+.5) for v in child.ViewObject.ShapeColor]
    # Placement is controlled as well; record numeric quaternion, never display text.
    result["Placement"] = [round(v, 8) for v in list(child.Placement.Base)+list(child.Placement.Rotation.Q)]
    return dumps(result)


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


def conflicts_for(obj, children, candidate):
    conflicts = {}
    after = {item.key for item in candidate.items}
    groups = list(obj.RoleGroups)
    for key,child in children.items():
        if child.ControlledState and controlled_state(child) != child.ControlledState:
            conflicts[key] = "Propriedade controlada alterada diretamente: "+child.Label
        if child.ExpressionEngine:
            conflicts[key] = "Expressões em membro gerado exigem revisão: "+child.Label
        if key not in after:
            if any(ref not in groups for ref in child.InList):
                conflicts[key] = "Filho removido possui referências externas: "+child.Label
            if (child.StartExtension.Value or child.EndExtension.Value
                    or child.OffsetX.Value or child.OffsetY.Value
                    or str(child.StartAdjustmentMode) != "None" or str(child.EndAdjustmentMode) != "None"):
                conflicts[key] = "Remoção descartaria extensões/ajustes manuais: "+child.Label
    return conflicts


def prepare_batch(candidate, children):
    for child in children.values():
        for prefix in ("Start", "End"):
            if str(getattr(child, prefix+"AdjustmentMode")) != "Associative":
                continue
            if getattr(child.Proxy, "_last_generated_result", None) is None:
                raise ValueError("Recompute o membro ajustado antes de Atualizar Treliça: "+child.Label)
            reference = unpack_link_sub(getattr(child, prefix+"AdjustmentReference"))
            if reference is None:
                raise ValueError("Referência de ajuste ausente: "+child.Label)
            target = reference[0]
            if would_create_adjustment_cycle(child.GenerationOwner, target):
                raise ValueError("Ajuste depende da própria treliça; revisão manual necessária: "+child.Label)
            queue, seen = [target], set()
            while queue:
                source = queue.pop()
                if source.Name in seen:
                    continue
                seen.add(source.Name)
                if any(state in source.State for state in ("Touched", "Invalid", "Recompute")):
                    raise ValueError("Recompute a origem do ajuste antes de Atualizar Treliça: "+source.Label)
                queue.extend(source.OutList)
    return {item.key: prepare_member(children.get(item.key), item_values(item)) for item in candidate.items}


def apply_existing_batch(obj, candidate, children, prepared):
    """No OCC after the first mutation. Rebuild backups from inputs, never child.Shape."""
    backups = {key: getattr(child.Proxy, "_last_generated_result", None) or prepare_member(child)
               for key,child in children.items()}
    colors = {key: tuple(child.ViewObject.ShapeColor) for key,child in children.items()}
    owner_fields = ("AppliedState", "LeftPanels", "RightPanels", "GeneratedMembers", "NeedsRegeneration",
                    "GenerationState", "GenerationMessage", "SchemaVersion", "Placement", "RoleSpecs") + tuple(PROPERTY_CONFIG)
    owner_fields += tuple(name for name in ("C2Configuration", "TopologyMode", "ReferenceMode", "ReferenceLinked",
                                           "ReferenceSource", "ReferenceContainers", "PanelizationMode") if hasattr(obj,name))
    owner_backup = {name: getattr(obj, name) for name in owner_fields}
    try:
        for item in candidate.items:
            apply_result(children[item.key], prepared[item.key], item.spec.color)
        for child in children.values():
            child.ControlledState = controlled_state(child)
        set_config(obj, candidate.config)
        accept_state(obj, candidate, children)
    except Exception:
        for key,child in children.items():
            apply_result(child, backups[key], colors[key])
            child.ControlledState = controlled_state(child)
        for name,value in owner_backup.items():
            setattr(obj, name, value)
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
        self._updating = False

    def execute(self, obj):
        if self._updating or not obj.AppliedState:
            return
        self._updating = True
        try:
            if obj.SchemaVersion not in (1, SCHEMA_VERSION):
                raise ValueError("SchemaVersion não suportada.")
            state = decode_state(obj.AppliedState)
            applied = build_candidate(state["candidate"]["config"])
            candidate = build_candidate(config_from_object(obj), applied)
            children = bound_children(obj, state)
            plan = plan_regeneration(candidate, applied, state["bindings"], conflicts_for(obj, children, candidate))
            if plan.conflicts:
                raise ValueError("; ".join(action.reason for action in plan.conflicts))
            if plan.structural:
                obj.NeedsRegeneration = True
                obj.GenerationState = "Pending"
                obj.GenerationMessage = "Alteração estrutural pendente. Dê duplo clique na treliça e confirme no Gerador."
                return
            if any(action.action != "UNCHANGED" for action in plan.actions):
                prepared = prepare_batch(candidate, children)
                apply_existing_batch(obj, candidate, children, prepared)
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

    def onDocumentRestored(self, obj):
        self._updating = True
        try:
            ensure_c2_properties(obj)
        finally:
            self._updating = False
        for name in ("TopologyPreset", "EnvelopeType", "PanelCount", "TopChordContinuity",
                     "BottomChordContinuity", "PanelizationMode", "LeftPanels", "RightPanels"):
            obj.setEditorMode(name, 1)
        if obj.SchemaVersion not in (1, SCHEMA_VERSION):
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
        self._visibility_updating = False

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
            children = list(getattr(view.Object, "GeneratedMembers", ()))
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
        return list(self.Object.RoleGroups)

    def doubleClicked(self, view):
        from .interactive.truss_controller import open_truss_panel
        open_truss_panel(view.Object.Document, view.Object)
        return True

    def setupContextMenu(self, view, menu):
        action = menu.addAction("Atualizar Treliça")
        action.triggered.connect(lambda: self.doubleClicked(view))

    def dumps(self):
        return {"hidden_children": getattr(self, "_hidden_children", {})}

    def loads(self, state):
        self._hidden_children = dict((state or {}).get("hidden_children", {}))
        self._visibility_updating = False


def accept_state(obj, candidate, children):
    obj.SchemaVersion = SCHEMA_VERSION
    obj.GeneratedMembers = [children[key] for key in sorted(children)]
    obj.AppliedState = encode_state(candidate, {key: children[key].Name for key in sorted(children)})
    obj.LeftPanels, obj.RightPanels = candidate.stations.left_panels, candidate.stations.right_panels
    obj.NeedsRegeneration = False
    obj.GenerationState = "Valid"
    obj.GenerationMessage = "; ".join(candidate.warnings)


def apply_truss(document, config, obj=None):
    """Explicit one-transaction create/regenerate; one final document recompute."""
    config = resolve_linked_reference(document, config, obj)
    state = decode_state(obj.AppliedState) if obj is not None else None
    applied = build_candidate(state["candidate"]["config"]) if state else None
    candidate = build_candidate(config, applied)
    children = bound_children(obj, state) if state else {}
    conflicts = conflicts_for(obj, children, candidate) if obj else {}
    plan = plan_regeneration(candidate, applied, state["bindings"] if state else {}, conflicts)
    if plan.conflicts:
        raise ValueError("; ".join(a.reason for a in plan.conflicts))
    prepared = prepare_batch(candidate, children)
    source = document.getObject(config.get("reference_source", "")) if config.get("reference_source") else None
    source_visibility = bool(source.ViewObject.Visibility) if source is not None else None
    document.openTransaction("Atualizar Treliça" if obj else "Criar Treliça")
    try:
        if obj is None:
            obj = document.addObject("App::FeaturePython", "StructuralTruss")
            StructuralTrussProxy(obj)
            StructuralTrussViewProvider(obj.ViewObject)
            obj.DisplayName = obj.Label = "Treliça"+obj.Name.removeprefix("StructuralTruss")
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
            apply_result(child, prepared[item.key], item.spec.color)
            child.ControlledState = controlled_state(child)
            result[item.key] = child
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
            groups[role].Group = members
        obj.RoleGroups = [groups[role] for role in ROLES if role in groups]
        for key,child in children.items():
            if key not in result:
                document.removeObject(child.Name)
        accept_state(obj, candidate, result)
        if not obj.ViewObject.Visibility:
            obj.ViewObject.Proxy.onChanged(obj.ViewObject, "Visibility")
        document.recompute()
        for child in result.values():
            if ("Invalid" in child.State or child.Shape.isNull() or not child.Shape.isValid()
                    or child.Shape.Volume <= 0 or child.GenerationStatus != "Valid"):
                raise ValueError("Falha ao aplicar membro: "+child.Name)
        obj.Proxy._updating = False
        if source is not None:
            source.ViewObject.Visibility = False
        document.commitTransaction()
        return obj
    except Exception:
        if obj is not None:
            obj.Proxy._updating = False
        document.abortTransaction()
        if source is not None and source_visibility is not None:
            source.ViewObject.Visibility = source_visibility
        document.recompute()
        raise
