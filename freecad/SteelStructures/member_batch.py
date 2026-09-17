"""Detached evaluation of the EXISTING member pipeline for atomic batch owners.

The snapshot is an in-memory property adapter, never a document object. Its
execute uses StructuralMemberProxy's normal section/adjustment/OCC pipeline.
No second extrusion or fitting implementation lives here. Outputs are applied
only after the caller has validated the complete batch.
"""
from types import SimpleNamespace
import math
import json
import FreeCAD as App
from . import member, profile_catalog
from .profiles.models import ProfileRef
from .profiles.insertion import section_insertion_references

INPUTS = ("StartPoint", "EndPoint", "Profile", "ProfileCategory", "ProfileSeries", "Insertion",
          "Rotation", "SectionGeometryMode", "OffsetX", "OffsetY", "StartExtension", "EndExtension",
          "AxisDefinitionMode", "AxisSource") + tuple(
    prefix+suffix for prefix in ("Start", "End") for suffix in
    ("AdjustmentMode", "AdjustmentGeometryMode", "AdjustmentReference", "AdjustmentGap",
     "FixedReferenceOffset", "FixedPlaneNormal"))
ADJUSTMENT_INPUTS = tuple(prefix+suffix for prefix in ("Start", "End") for suffix in
    ("AdjustmentMode", "AdjustmentGeometryMode", "AdjustmentReference", "AdjustmentGap",
     "FixedReferenceOffset", "FixedPlaneNormal"))
OUTPUTS = ("EffectiveStartPoint", "EffectiveEndPoint", "AdjustedLength", "MemberLength", "TotalMass",
           "Manufacturer", "ProfileFamily", "MassPerMeter", "CatalogArea", "CatalogSource")
CONTROLLED = ("StartPoint", "EndPoint", "ProfileCategory", "ProfileSeries", "Profile", "Insertion",
              "Rotation", "SectionGeometryMode", "AxisDefinitionMode", "AxisSource")


def _copy(value):
    if isinstance(value, App.Vector):
        return App.Vector(value)
    if hasattr(value, "Value"):
        return SimpleNamespace(Value=float(value.Value))
    return value


class MemberInputSnapshot(SimpleNamespace):
    def setEditorMode(self, *args):
        pass


def snapshot(obj=None, values=None):
    defaults = dict(StartPoint=App.Vector(), EndPoint=App.Vector(0,0,1000),
                    ProfileCategory="", ProfileSeries="", DisplayName="", Length=1000.,
                    Insertion="Centroide", SectionGeometryMode="Detailed",
                    AxisDefinitionMode="Independent", AxisSource=None,
                    Placement=App.Placement(), ExpressionEngine=(), GenerationOwner=None)
    for name in ("Rotation", "OffsetX", "OffsetY", "StartExtension", "EndExtension"):
        defaults[name] = SimpleNamespace(Value=0.)
    for prefix in ("Start", "End"):
        defaults.update({prefix+"AdjustmentMode": "None", prefix+"AdjustmentGeometryMode": "LengthLimit",
                         prefix+"AdjustmentReference": None, prefix+"AdjustmentGap": SimpleNamespace(Value=0.),
                         prefix+"FixedReferenceOffset": SimpleNamespace(Value=0.),
                         prefix+"FixedPlaneNormal": App.Vector()})
    defaults.update({name: "" for name in OUTPUTS})
    if obj is not None:
        defaults.update({name: _copy(getattr(obj, name)) for name in INPUTS if hasattr(obj, name)})
        if hasattr(obj, "AssemblySectionTransform"):
            defaults["AssemblySectionTransform"] = str(obj.AssemblySectionTransform)
        defaults["ReferenceTarget"] = obj
        for name in ("PhysicalFitPlan", "PhysicalFitAutoState", "PhysicalFitStatus"):
            if hasattr(obj, name):
                defaults[name] = str(getattr(obj, name))
    defaults.update(values or {})
    for name in ("Rotation", "OffsetX", "OffsetY", "StartExtension", "EndExtension"):
        if not hasattr(defaults[name], "Value"):
            defaults[name] = SimpleNamespace(Value=float(defaults[name]))
    defaults["PropertiesList"] = tuple(defaults)
    return MemberInputSnapshot(**defaults)


def prepare_member(obj=None, values=None):
    result = snapshot(obj, values)
    proxy = member.StructuralMemberProxy.__new__(member.StructuralMemberProxy)
    proxy.__setstate__(None)
    proxy._placement_from_points_pending = True
    proxy.execute(result)
    shape = getattr(result, "Shape", None)
    if shape is None or shape.isNull() or not shape.isValid() or shape.Volume <= 1e-7:
        raise ValueError("Membro candidato inválido; verifique perfil, eixo e ajustes das extremidades.")
    return result


def item_values(item):
    ref = ProfileRef(**item.spec.profile_ref)
    category, series, designation = profile_catalog.selection_for_ref(ref)
    if not designation:
        raise ValueError("Perfil não disponível: "+str(ref))
    profile = profile_catalog.get(designation)
    geometry = member._section_geometry(profile, item.spec.section_geometry_mode)
    references = section_insertion_references(geometry)
    insertion = next((r.label for r in references if item.spec.insertion in (r.id, r.label)), None)
    if insertion is None:
        raise ValueError("Inserção incompatível com o perfil: "+item.spec.insertion)
    start, end = App.Vector(*item.start_global), App.Vector(*item.end_global)
    w = end.sub(start)
    w.normalize()
    base = member._member_frame_rotation(w)
    u0, v0 = base.multVec(App.Vector(1,0,0)), base.multVec(App.Vector(0,1,0))
    desired_u = App.Vector(*item.section_u_global)
    angle = (math.degrees(math.atan2(desired_u.dot(v0), desired_u.dot(u0))) + item.spec.rotation) % 360.
    values = dict(StartPoint=start, EndPoint=end, ProfileCategory=category, ProfileSeries=series,
                Profile=profile_catalog.property_designation(designation), Insertion=insertion,
                Rotation=angle, SectionGeometryMode=item.spec.section_geometry_mode,
                AxisDefinitionMode="Independent", AxisSource=None)
    if getattr(item, "section_transform", None) is not None:
        values["AssemblySectionTransform"] = json.dumps(item.section_transform, sort_keys=True)
    return values


def prepared_item(item, child=None, values=None):
    values = dict(values) if values is not None else item_values(item)
    from .fitting.freecad_adapter import fitting_inputs, attach_prepared_metadata
    values, plan_text, state_text, status = fitting_inputs(item, child, values)
    if plan_text is not None:
        values.update(PhysicalFitPlan=plan_text, PhysicalFitAutoState=state_text)
    result = prepare_member(child, values)
    attach_prepared_metadata(result, plan_text, state_text, status)
    return result


def signature(obj):
    values = []
    for name in INPUTS:
        value = getattr(obj, name)
        if isinstance(value, App.Vector):
            value = (value.x, value.y, value.z)
        elif hasattr(value, "Value"):
            value = float(value.Value)
        else:
            value = str(value)
        values.append(value)
    if hasattr(obj, "AssemblySectionTransform"):
        values.append(str(obj.AssemblySectionTransform))
    values.append(getattr(obj, "PhysicalFitPlan", ""))
    return tuple(values)


def apply_fit_properties(obj, result):
    """Restore optional fitting output from current or legacy detached snapshots."""
    if hasattr(result, "PhysicalFitPlan"):
        for name, label in (("PhysicalFitPlan", "Plano de fitting"),
                            ("PhysicalFitAutoState", "Estado automático"),
                            ("PhysicalFitStatus", "Diagnóstico de fitting")):
            if name not in obj.PropertiesList:
                obj.addProperty("App::PropertyString", name, "Ajuste físico", label)
            setattr(obj, name, getattr(result, name, ""))
        obj.setEditorMode("PhysicalFitPlan", 2)
        obj.setEditorMode("PhysicalFitAutoState", 2)
        obj.setEditorMode("PhysicalFitStatus", 1)


def apply_result(obj, result, color=None):
    proxy = obj.Proxy
    proxy._updating = True
    try:
        # Set enum lists before selecting across profile series; callbacks are guarded.
        for name in ("ProfileCategory", "ProfileSeries", "Profile", "Insertion"):
            value = getattr(result, name)
            if name == "ProfileCategory":
                options = profile_catalog.categories()
            elif name == "ProfileSeries":
                options = profile_catalog.series_for_category(result.ProfileCategory)
            elif name == "Profile":
                options = profile_catalog.property_designations(result.ProfileCategory, result.ProfileSeries)
            else:
                options = member.insertion_options(profile_catalog.get(result.Profile))
            member._set_enum(obj, name, options, value)
        for name in CONTROLLED:
            if name in ("ProfileCategory", "ProfileSeries", "Profile", "Insertion"):
                continue
            value = getattr(result, name)
            setattr(obj, name, getattr(value, "Value", value))
        for name in ADJUSTMENT_INPUTS:
            value = getattr(result, name)
            setattr(obj, name, getattr(value, "Value", value))
        for name in OUTPUTS:
            setattr(obj, name, getattr(result, name, ""))
        if hasattr(result, "AssemblySectionTransform"):
            if "AssemblySectionTransform" not in obj.PropertiesList:
                obj.addProperty("App::PropertyString", "AssemblySectionTransform", "Assembly")
            obj.AssemblySectionTransform = result.AssemblySectionTransform
            obj.setEditorMode("AssemblySectionTransform", 1)
        apply_fit_properties(obj, result)
        obj.Length = result.MemberLength
        obj.Shape = result.Shape
        obj.Placement = App.Placement(result.Placement)
        proxy._remember_placement(obj)
        proxy._last_section_rotation = member._quantity_value(obj.Rotation)
        proxy._last_valid_length = result.MemberLength
        proxy._placement_from_points_pending = False
        if color is not None:
            obj.ViewObject.ShapeColor = tuple(color)
        if hasattr(obj, "GenerationStatus"):
            obj.GenerationStatus = "Valid"
        proxy._generated_prepared_signature = signature(obj)
        proxy._last_generated_result = result
        lock_controlled(obj)
    finally:
        proxy._updating = False


def lock_controlled(obj):
    for name in CONTROLLED + ("Length", "Placement", "GenerationOwner", "GenerationKey"):
        if name in obj.PropertiesList:
            obj.setEditorMode(name, 1)
    if getattr(obj, "GenerationOwner", None) is not None:
        for name in ("ShapeColor", "ShapeAppearance"):
            if name in obj.ViewObject.PropertiesList:
                obj.ViewObject.setEditorMode(name, 1)


def execute_generated_member(obj):
    proxy = obj.Proxy
    if obj.ExpressionEngine or (obj.ControlledState and controlled_state(obj) != obj.ControlledState):
        obj.GenerationStatus = "Conflict: propriedade controlada alterada diretamente; Shape anterior preservada."
        return
    if getattr(proxy, "_generated_prepared_signature", None) == signature(obj):
        proxy._generated_prepared_signature = None
        lock_controlled(obj)
        return
    try:
        result = prepare_member(obj)
        apply_result(obj, result)
        obj.ControlledState = controlled_state(obj)
        proxy._generated_prepared_signature = None
    except Exception as exc:
        # A generated child's manual fitting can fail without destroying its last Shape.
        obj.GenerationStatus = "Erro: "+str(exc)
        App.Console.PrintWarning("Steel Structures: "+str(exc)+"\n")


def controlled_state(child, color=None):
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
    if color is None:
        color = child.ViewObject.ShapeColor
    result["Color"] = [math.floor(v*255+.5) for v in color]
    # Placement is controlled as well; record numeric quaternion, never display text.
    result["Placement"] = [round(v, 8) for v in list(child.Placement.Base)+list(child.Placement.Rotation.Q)]
    if hasattr(child, "AssemblySectionTransform"):
        result["AssemblySectionTransform"] = str(child.AssemblySectionTransform)
    return json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)



def validate_adjustment_dependencies(children):
    """Shared preflight for an atomic batch of existing physical members."""
    from .member_adjustment_reference import unpack_link_sub, would_create_adjustment_cycle
    for child in children:
        for prefix in ("Start", "End"):
            if str(getattr(child, prefix+"AdjustmentMode")) != "Associative":
                continue
            # Python caches disappear on restore. Validate persisted references
            # and geometry without requiring a previous detached result.
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
