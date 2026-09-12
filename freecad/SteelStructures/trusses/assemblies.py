"""Role-to-assembly bridge. All section geometry/transforms remain in C3-A.

Role rotation rotates the entire assembly frame, including insertion axes.
Component T acts within that frame: global = nominal + R_role (d + T(p-q)).
Single retains the historical member Rotation path byte-for-byte in inputs.
"""
from dataclasses import asdict, replace
import json
import math
from .. import profile_catalog
from ..profiles.models import ProfileRef
from ..profiles.validation import ProfileNotFoundError
from ..assemblies.models import MemberFrame
from ..assemblies.presets import single, double_angle, double_channel, spaced_pair
from ..assemblies.transforms import SectionTransform
from ..assemblies.serialization import dumps, loads
from ..assemblies.resolver import resolve_member_assembly

ASSEMBLY_MODES = (
    ("Single", "Simples"),
    ("DoubleAngle", "Dupla cantoneira"),
    ("DoubleChannelInward", "U duplo — bocas para dentro"),
    ("DoubleChannelOutward", "U duplo — bocas para fora"),
    ("SpacedPair", "Par espaçado"),
)


def component_label(item, runs):
    labels = {"TOP_CHORD": "Banzo superior", "BOTTOM_CHORD": "Banzo inferior",
              "DIAGONAL": "Diagonal", "VERTICAL": "Montante", "END_POST": "Fechamento"}
    peers = [r.key for r in runs if r.role == item.role]
    number = peers.index(item.run_key)+1
    label = f"{labels[item.role]} {number:02d}"
    if item.element_kind == "Interconnector":
        return label+" / "+item.element_label
    return label if item.spec.assembly == "Single" else f"{label} / {item.component_key}"


def compatible_modes(profile):
    family = profile.geometry_type
    return tuple(key for key, _ in ASSEMBLY_MODES if key in ("Single", "SpacedPair")
                 or key == "DoubleAngle" and family == "equal_angle"
                 or key.startswith("DoubleChannel") and family in ("channel_section", "cold_formed_channel"))


def role_profile(spec):
    ref = ProfileRef(**spec["profile_ref"])
    try:
        _, _, designation = profile_catalog.selection_for_ref(ref)
    except (KeyError, ProfileNotFoundError) as exc:
        raise ValueError("Perfil da composição não está disponível no catálogo.") from exc
    if not designation:
        raise ValueError("Perfil da composição não está disponível no catálogo.")
    return profile_catalog.get(designation).definition


def configure_assembly(role, mode, spacing=100., insertion="SymmetricPair", transforms=None, interconnectors=None):
    """Return a detached role configuration for the editor and scripting API."""
    result = dict(role)
    if mode not in compatible_modes(role_profile(role)):
        raise ValueError("Composição incompatível com o perfil. Selecione um perfil compatível ou Simples.")
    result["assembly"] = mode
    if mode == "Single":
        result.pop("assembly_spec", None)
        return result
    ref = ProfileRef(**role["profile_ref"])
    if mode == "DoubleAngle":
        assembly = double_angle("ASSEMBLY", ref, spacing)
    elif mode.startswith("DoubleChannel"):
        assembly = double_channel("ASSEMBLY", ref, spacing,
                                  "inward" if mode.endswith("Inward") else "outward")
    else:
        assembly = spaced_pair("ASSEMBLY", ref, spacing)
    if transforms is not None:
        if len(transforms) != 2:
            raise ValueError("Defina a orientação dos dois componentes.")
        assembly = replace(assembly, components=tuple(replace(c, section_transform=t)
                           for c, t in zip(assembly.components, transforms)))
    if interconnectors is None:
        interconnectors = (loads(json.dumps(role["assembly_spec"])).interconnectors
                           if role.get("assembly_spec") else ())
    assembly = replace(assembly, assembly_insertion=insertion, interconnectors=tuple(interconnectors))
    result["assembly_spec"] = json.loads(dumps(assembly))
    # Material/profile/insertion/color are controlled by the role, canonicalized below.
    result["assembly_spec"] = json.loads(dumps(role_assembly_spec(result)))
    return result


def role_assembly_spec(role):
    """Common role fields are authoritative; assembly stores relative arrangement."""
    mode = role.get("assembly", "Single")
    ref = ProfileRef(**role["profile_ref"])
    if mode == "Single":
        if role.get("assembly_spec") is not None:
            raise ValueError("Composição Simples não aceita uma definição dupla residual.")
        assembly = single("ASSEMBLY", ref)
    else:
        if mode not in dict(ASSEMBLY_MODES):
            raise ValueError("Composição não suportada.")
        if mode not in compatible_modes(role_profile(role)):
            raise ValueError("Composição incompatível com o perfil. Selecione um perfil compatível ou Simples.")
        if not role.get("assembly_spec"):
            raise ValueError("Configure a composição e a distância entre eixos.")
        assembly = loads(json.dumps(role["assembly_spec"]))
        if (assembly.assembly_key != "ASSEMBLY" or assembly.behavior_mode != "MultiComponent"
                or {c.component_key for c in assembly.components} != {"A", "B"}):
            raise ValueError("A composição do role deve conter os componentes A e B.")
        if assembly.component_spacing is None:
            raise ValueError("Defina a distância entre os eixos da composição.")
        for component in assembly.components:
            sign = -1 if component.component_key == "A" else 1
            expected = (sign*assembly.component_spacing/2, 0.)
            if math.dist(component.transverse_translation, expected) > 1e-8:
                raise ValueError("Este editor requer eixos A/B simétricos na direção transversal do conjunto.")
        if mode.startswith("DoubleChannel"):
            preset = double_channel("ASSEMBLY", ref, assembly.component_spacing,
                "inward" if mode.endswith("Inward") else "outward")
            expected = {c.component_key: c.section_transform for c in preset.components}
            if any(c.section_transform != expected[c.component_key] for c in assembly.components):
                raise ValueError("A disposição dos componentes diverge das bocas selecionadas. Reconfigure a composição.")
    return replace(assembly, components=tuple(replace(c, profile_ref=ref,
        section_geometry_mode=role["section_geometry_mode"], insertion_reference=role["insertion"],
        color=tuple(role["color"])) for c in sorted(assembly.components, key=lambda c: c.component_key)))


def assembly_frame(nominal_axis, section_u, rotation):
    frame = MemberFrame.from_axis(nominal_axis, section_u)
    c, s = math.cos(math.radians(rotation)), math.sin(math.radians(rotation))
    u = tuple(c*x+s*y for x, y in zip(frame.u, frame.v))
    v = tuple(-s*x+c*y for x, y in zip(frame.u, frame.v))
    return MemberFrame(u, v, frame.w)


def expand_run(item):
    """A keeps the C1/C2 binding alias (run key); metadata carries full identity."""
    role = asdict(item.spec)
    assembly = role_assembly_spec(role)
    if item.spec.assembly == "Single":
        return (replace(item, run_key=item.key, assembly_key="ASSEMBLY", component_key="A"),)
    axis = (item.start_global, item.end_global)
    frame = assembly_frame(axis, item.section_u_global, item.spec.rotation)
    realization = resolve_member_assembly(axis, frame, assembly)
    items = []
    for component in realization.components:
        key = item.key if component.component_key == "A" else json.dumps(
            (item.key, assembly.assembly_key, component.component_key), separators=(",", ":"))
        items.append(replace(item, key=key, run_key=item.key, assembly_key=assembly.assembly_key,
            component_key=component.component_key, start_global=component.start_global,
            end_global=component.end_global, section_u_global=frame.u,
            section_transform=asdict(component.section_transform),
            spec=replace(item.spec, rotation=0.)))
    items.extend(interconnector_items(item, realization.interconnectors, assembly.assembly_key))
    return tuple(items)


def interconnector_items(item, connectors, assembly_key="ASSEMBLY"):
    """Materialize connector members while preserving their C4 identities."""
    items = []
    for connector in connectors:
        identity = (item.key,)+connector.stable_identity
        # Rendered physical members have their own profile and frame, but no
        # new topology endpoints. start/end node keys remain run provenance.
        items.append(replace(item, key=json.dumps(identity, separators=(",", ":")),
            run_key=item.key, assembly_key=assembly_key, component_key="",
            element_kind="Interconnector", interconnector_key=connector.interconnector_key,
            slot_key=connector.slot_key, generated_element_key=connector.generated_element_key,
            element_label=connector.label.split(" / Face")[0]+(" / 2" if identity[-1] == "SECONDARY" else ""),
            start_global=connector.start_global, end_global=connector.end_global,
            section_u_global=connector.orientation.u, section_transform=asdict(connector.section_transform),
            spec=replace(item.spec, profile_ref=asdict(connector.profile_ref), rotation=0.,
                         insertion=connector.insertion_reference, color=connector.color,
                         section_geometry_mode=connector.section_geometry_mode.value)))
    return tuple(items)
