"""Pure editor mappings; family restrictions do not belong to attachment."""
from dataclasses import replace
from .. import profile_catalog
from ..assemblies import InterconnectorSpec, DistributionSpec

KINDS = (("None", "Nenhum"), ("SpacerPlate", "Chapas espaçadoras"), ("Battens", "Presilhas"),
         ("SingleLacing", "Treliçamento simples"), ("DoubleLacing", "Treliçamento duplo"))


def is_lacing(kind):
    return kind in ("SingleLacing", "DoubleLacing")


def compatible_profile(profile, kind):
    flat = profile.geometry_type == "solid_section" and profile.geometry_variant == "rectangular"
    return flat or (is_lacing(kind) and profile.geometry_type == "equal_angle")


def default_connector(kind, key="WEB"):
    designation = "L 40 x 4" if is_lacing(kind) else "Barra Chata 50,8x6,35"
    return InterconnectorSpec(key, kind, ("A", "B"), profile_catalog.ref_for_designation(designation),
        attachment_plane="InnerFaces" if kind == "SpacerPlate" else "FaceA")


def quantity_to_stations(kind, quantity):
    return quantity+1 if is_lacing(kind) else quantity


def stations_to_quantity(kind, count):
    return count-1 if is_lacing(kind) else count


def edited_connector(previous, kind, plane, mode, quantity, spacing, start, end, start_side):
    if kind == "None":
        return None
    profile = profile_catalog.get(profile_catalog.selection_for_ref(previous.profile_ref)[2]).definition
    if not compatible_profile(profile, kind):
        raise ValueError("Selecione um perfil compatível com o tipo de interconector.")
    distribution = DistributionSpec(mode, quantity_to_stations(kind, quantity) if mode == "ByCount" else None,
                                    spacing if mode == "ByTargetSpacing" else None,
                                    previous.distribution.station_keys)
    return replace(previous, kind=kind, distribution=distribution, start_offset=start, end_offset=end,
                   start_side=start_side if kind == "SingleLacing" else "A",
                   attachment_plane="InnerFaces" if kind == "SpacerPlate" else plane)
