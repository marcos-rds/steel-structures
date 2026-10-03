"""Small proof presets. Spacing is between insertion axes, NOT face clearance."""
from .models import AssemblyComponentSpec, MemberAssemblySpec
from .transforms import SectionTransform


def single(assembly_key, profile_ref, **component_options):
    return MemberAssemblySpec(assembly_key, "Single", "Center",
                              (AssemblyComponentSpec("A", profile_ref, **component_options),))


def spaced_pair(assembly_key, profile_ref, component_spacing,
                transforms=(SectionTransform(), SectionTransform()), insertion_reference="centroid"):
    if len(transforms) != 2:
        raise ValueError("SpacedPair requer duas transformações.")
    return MemberAssemblySpec(assembly_key, "MultiComponent", "SymmetricPair", tuple(
        AssemblyComponentSpec(key, profile_ref, section_transform=transform,
                              transverse_translation=(sign*component_spacing/2, 0.),
                              insertion_reference=insertion_reference,
                              color=color)
        for key, sign, transform, color in zip(("A", "B"), (-1, 1), transforms,
                                              ((.25, .55, .85), (.95, .65, .2)))), component_spacing)


def double_angle(assembly_key, profile_ref, component_spacing):
    """Canonical L opens +X,+Y; left L mirrored, toes outward, heels central."""
    return spaced_pair(assembly_key, profile_ref, component_spacing,
                       (SectionTransform(reflect_x=True), SectionTransform()))


def double_channel(assembly_key, profile_ref, component_spacing, mouths="outward"):
    """Canonical U opens +X: outward is ][; inward is []."""
    if mouths not in ("outward", "inward"):
        raise ValueError("Disposição de bocas inválida.")
    transforms = (SectionTransform(reflect_x=True), SectionTransform())
    return spaced_pair(assembly_key, profile_ref, component_spacing,
                       transforms if mouths == "outward" else transforms[::-1])
