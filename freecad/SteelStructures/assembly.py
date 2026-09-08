"""Explicit FreeCAD adapter for reusable assemblies; no truss/UI dependency.

The caller supplies an owner (a dedicated App::FeaturePython is sufficient).
Its hidden registry is organizational; children depend on the owner through
GenerationOwner, never the reverse. No automatic topology regeneration occurs.
All OCC evaluation completes before opening the mutation transaction.
"""
from dataclasses import asdict
import json
from types import SimpleNamespace
import FreeCAD as App
from .assemblies.models import MemberFrame
from .assemblies.resolver import resolve_member_assembly, plan_regeneration
from .assemblies.serialization import dumps, loads
from .member import create_member
from .member_batch import (item_values, prepare_member, apply_result, controlled_state,
                           validate_adjustment_dependencies)


def _identity(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def component_values(item):
    """Reuse normal member profile/insertion/frame resolution, with no axis offsets."""
    spec = SimpleNamespace(profile_ref=asdict(item.profile_ref),
                           insertion=item.insertion_reference, rotation=0.,
                           section_geometry_mode=item.section_geometry_mode.value)
    proxy_item = SimpleNamespace(spec=spec, start_global=item.start_global,
                                 end_global=item.end_global, section_u_global=item.orientation.u)
    values = item_values(proxy_item)
    values["AssemblySectionTransform"] = json.dumps(asdict(item.section_transform), sort_keys=True)
    return values


def _applied(owner):
    raw = getattr(owner, "AssemblyState", "")
    if not raw:
        return None, {}
    data = json.loads(raw)
    if data["schema_version"] != 1:
        raise ValueError("Estado de assembly não suportado.")
    result = resolve_member_assembly(data["nominal_axis"], MemberFrame(**data["member_frame"]),
                                     loads(data["spec"]))
    return result, {tuple(key): name for key, name in data["bindings"]}


def prepare_assembly(owner, nominal_axis, member_frame, spec):
    """Read-only planning/preflight. No document object is added or changed."""
    candidate = resolve_member_assembly(nominal_axis, member_frame, spec)
    applied, bindings = _applied(owner)
    children, conflicts = {}, {}
    registry = list(getattr(owner, "AssemblyMembers", []))
    if len({c.Name for c in registry}) != len(registry) or set(bindings.values()) != {c.Name for c in registry}:
        raise ValueError("Registro de assembly inconsistente.")
    after = {c.stable_identity for c in candidate.components}
    for key, name in bindings.items():
        child = owner.Document.getObject(name)
        if (child is None or child not in registry or getattr(child, "GenerationOwner", None) != owner
                or getattr(child, "GenerationKey", "") != _identity(key)
                or getattr(child, "AssemblyKey", "") != key[0]
                or getattr(child, "ComponentKey", "") != key[1]):
            raise ValueError("Binding inconsistente: "+str(key))
        children[key] = child
        if child.ExpressionEngine or controlled_state(child) != child.ControlledState:
            conflicts[key] = "Propriedade controlada alterada diretamente: "+name
        if key not in after:
            if (child.InList or child.StartExtension.Value or child.EndExtension.Value
                    or child.OffsetX.Value or child.OffsetY.Value
                    or str(child.StartAdjustmentMode) != "None" or str(child.EndAdjustmentMode) != "None"):
                conflicts[key] = "Remoção descartaria ajustes ou referências: "+name
    validate_adjustment_dependencies(children.values())
    plan = plan_regeneration(candidate, applied, bindings, conflicts)
    if plan.conflicts:
        raise ValueError("; ".join(a.reason for a in plan.conflicts))
    prepared = {c.stable_identity: prepare_member(children.get(c.stable_identity), component_values(c))
                for c in candidate.components}
    return candidate, plan, children, prepared


def apply_assembly(owner, nominal_axis, member_frame, spec, *, allow_structural=False):
    """Update stable objects. Structural transitions require explicit caller intent.

    The owner stores a versioned pure spec and accepted realization inputs; this
    is also usable by a future logical-run controller outside StructuralTruss.
    """
    candidate, plan, children, prepared = prepare_assembly(owner, nominal_axis, member_frame, spec)
    if plan.structural and not allow_structural:
        raise ValueError("RegenerationPlan estrutural requer aplicação explícita.")
    document = owner.Document
    document.openTransaction("Atualizar assembly")
    try:
        for kind, name in (("App::PropertyString", "AssemblyState"),
                           ("App::PropertyLinkListHidden", "AssemblyMembers")):
            if name not in owner.PropertiesList:
                owner.addProperty(kind, name, "Assembly")
                owner.setEditorMode(name, 2)
        result = {}
        for component in candidate.components:
            key = component.stable_identity
            child = children.get(key)
            if child is None:
                values = component_values(component)
                child = create_member(document, values["StartPoint"], values["EndPoint"], values["Profile"],
                                      insertion=values["Insertion"], rotation=values["Rotation"],
                                      section_geometry_mode=values["SectionGeometryMode"],
                                      display_name=spec.assembly_key+" / "+component.component_key, recompute=False)
                for kind, name in (("App::PropertyLink", "GenerationOwner"),
                                   ("App::PropertyString", "GenerationKey"),
                                   ("App::PropertyString", "GenerationStatus"),
                                   ("App::PropertyString", "ControlledState"),
                                   ("App::PropertyString", "AssemblyKey"),
                                   ("App::PropertyString", "ComponentKey")):
                    child.addProperty(kind, name, "Assembly")
                    child.setEditorMode(name, 1 if name != "ControlledState" else 2)
                child.GenerationOwner = owner
                child.GenerationKey = _identity(key)
                child.AssemblyKey, child.ComponentKey = key
            apply_result(child, prepared[key], component.color)
            child.ControlledState = controlled_state(child)
            result[key] = child
        owner.AssemblyMembers = list(result.values())
        owner.AssemblyState = json.dumps(dict(schema_version=1, spec=dumps(spec),
                                              nominal_axis=candidate.nominal_axis,
                                              member_frame=asdict(member_frame),
                                              bindings=[(key, child.Name) for key, child in result.items()]),
                                         ensure_ascii=False, sort_keys=True, allow_nan=False)
        for key, child in children.items():
            if key not in result:
                document.removeObject(child.Name)
        document.recompute()
        for child in result.values():
            if ("Invalid" in child.State or child.Shape.isNull() or not child.Shape.isValid()
                    or child.Shape.Volume <= 0 or child.GenerationStatus != "Valid"):
                raise ValueError("Componente inválido: "+child.Name)
        document.commitTransaction()
        return result
    except Exception:
        document.abortTransaction()
        # Python caches are not part of FreeCAD's transaction undo data.
        for child in children.values():
            restored = document.getObject(child.Name)
            if restored is not None:
                restored.Proxy._generated_prepared_signature = None
                restored.Proxy._last_generated_result = None
        document.recompute()
        raise
