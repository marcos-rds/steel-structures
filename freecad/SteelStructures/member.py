# SPDX-License-Identifier: LGPL-2.1-or-later
"""Parametric structural member document object."""

from __future__ import annotations

from typing import Tuple

import FreeCAD as App
import Part

from . import profile_catalog
from .member_adjustment_geometry import (
    closest_point_on_member_axis,
    intersect_infinite_axis_with_plane,
    normalized_vector,
    physical_extents,
)
from .member_adjustment_reference import (
    linear_reference_from_link,
    plane_reference_from_link,
    unpack_link_sub,
    would_create_adjustment_cycle,
)
from .member_plane_cut import (
    build_plane_cut,
    global_plane_to_member_local,
    is_orthogonal_plane,
)
from .paths import OBJECT_ICON
from .profiles.freecad_geometry import section_geometry_to_face
from .profiles.geometry import build_parallel_flange_i_section, build_section_geometry
from .profiles.insertion import insertion_translation as _geometry_insertion_translation
from .profiles.insertion import section_insertion_references

INSERTION_OPTIONS = [
    "Centroide",
    "Face esquerda",
    "Face direita",
    "Face superior",
    "Face inferior",
    "Canto superior esquerdo",
    "Canto superior direito",
    "Canto inferior esquerdo",
    "Canto inferior direito",
]

ELEMENT_TYPES = ["Membro", "Pilar", "Viga", "Contraventamento"]
MATERIALS = ["ASTM A572 Grau 50", "ASTM A36", "Personalizado"]
LENGTH_TOLERANCE = 1e-7
FRAME_TOLERANCE = 1e-7


def _quantity_value(value) -> float:
    return float(getattr(value, "Value", value))


def _has_expression(obj, property_name: str) -> bool:
    try:
        return bool(obj.getExpression(property_name))
    except (AttributeError, RuntimeError, TypeError):
        try:
            return any(item[0] == property_name for item in obj.ExpressionEngine)
        except (AttributeError, TypeError):
            return False
EMPTY_SERIES = "— Nenhuma série cadastrada —"
EMPTY_PROFILE = "— Nenhum perfil cadastrado —"


def _add_property(obj, property_type: str, name: str, label: str, group: str, description: str) -> bool:
    """Add a property when missing and return True only when it was created."""
    if name in obj.PropertiesList:
        return False
    obj.addProperty(property_type, name, group, description)
    # FreeCAD uses the final argument as the tooltip; the displayed property
    # label is set separately to keep internal names stable between versions.
    try:
        obj.setPropertyStatus(name, "")
    except Exception:
        pass
    return True


def _set_enum(obj, name: str, options, preferred: str | None = None, empty_text: str | None = None):
    options = list(options)
    if not options and empty_text:
        options = [empty_text]
    current = str(getattr(obj, name)) if name in obj.PropertiesList else ""
    setattr(obj, name, options)
    selected = preferred if preferred in options else current if current in options else (options[0] if options else "")
    if selected:
        setattr(obj, name, selected)


def _i_section_face(profile: profile_catalog.Profile) -> Part.Face:
    """Create the legacy W/HP Face through the common section geometry core."""
    # The compatibility facade intentionally exposes only constructible W/HP
    # profiles.  Their typed geometry contract is parallel-flange I-section;
    # avoid manufacturing a partial ProfileDefinition solely for this bridge.
    geometry = build_parallel_flange_i_section(
        d=profile.d, bf=profile.bf, tw=profile.tw, tf=profile.tf
    )
    return section_geometry_to_face(geometry)


def _section_geometry(profile: profile_catalog.Profile):
    """Resolve every constructible catalog profile through the typed core."""
    definition = getattr(profile, "definition", None)
    if definition is not None:
        return build_section_geometry(definition)
    return build_parallel_flange_i_section(
        d=profile.d, bf=profile.bf, tw=profile.tw, tf=profile.tf
    )


def _section_face(profile: profile_catalog.Profile) -> Part.Face:
    return section_geometry_to_face(_section_geometry(profile))


def insertion_options(profile: profile_catalog.Profile):
    options = profile_catalog.insertion_options(profile)
    if options:
        return options
    return tuple(item.label for item in section_insertion_references(_section_geometry(profile)))


def _insertion_translation(profile: profile_catalog.Profile, mode: str) -> Tuple[float, float]:
    return _geometry_insertion_translation(_section_geometry(profile), mode)


def _member_frame_rotation(direction: App.Vector) -> App.Rotation:
    """Map the local section frame onto a deterministic structural frame.

    The section width, height and extrusion axes are local +X, +Y and +Z.
    Away from global Z, local +Y follows the projection of global Z onto the
    section plane.  Nearly vertical members retain the historical shortest-arc
    alignment, including the approved identity orientation for +Z columns.
    """
    longitudinal = App.Vector(direction)
    longitudinal.normalize()
    global_up = App.Vector(0.0, 0.0, 1.0)
    section_vertical = global_up.sub(longitudinal * global_up.dot(longitudinal))
    if section_vertical.Length <= FRAME_TOLERANCE:
        return App.Rotation(global_up, longitudinal)

    section_vertical.normalize()
    section_transverse = section_vertical.cross(longitudinal)
    section_transverse.normalize()
    return App.Rotation(
        section_transverse, section_vertical, longitudinal, "ZXY"
    )


def _copy_placement(placement):
    """Return a detached Placement value for change-delta tracking."""
    return App.Placement(placement)


class StructuralMemberProxy:
    """Geometry and parametric behavior for a structural member."""

    def __init__(self, obj):
        self._updating = True
        self._syncing_length = False
        self._syncing_placement = False
        self._placement_from_points_pending = True
        self._last_placement = None
        self._last_section_rotation = 0.0
        self._last_valid_length = None
        obj.Proxy = self
        self._setup_properties(obj)
        self._last_section_rotation = _quantity_value(obj.Rotation)
        self._updating = False

    def _remember_placement(self, obj):
        self._last_placement = _copy_placement(obj.Placement)

    def _set_placement(self, obj, placement):
        self._syncing_placement = True
        try:
            obj.Placement = placement
            self._remember_placement(obj)
        finally:
            self._syncing_placement = False

    def _sync_points_from_placement(self, obj):
        """Apply a user's rigid Placement delta to the global axis points."""
        current = _copy_placement(obj.Placement)
        previous = self._last_placement
        if previous is None:
            self._last_placement = current
            return False
        delta = current.multiply(previous.inverse())
        self._syncing_placement = True
        self._syncing_length = True
        try:
            obj.StartPoint = delta.multVec(App.Vector(obj.StartPoint))
            obj.EndPoint = delta.multVec(App.Vector(obj.EndPoint))
            self._sync_length_from_points(obj)
            self._last_placement = current
            self._placement_from_points_pending = False
        finally:
            self._syncing_length = False
            self._syncing_placement = False
        return True

    def _apply_section_rotation_change(self, obj):
        """Rotate the section around the member's existing local Z axis."""
        current = _quantity_value(obj.Rotation)
        delta_angle = current - self._last_section_rotation
        if self._placement_from_points_pending or abs(delta_angle) <= 1e-12:
            self._last_section_rotation = current
            return
        delta_roll = App.Placement(
            App.Vector(0.0, 0.0, 0.0),
            App.Rotation(App.Vector(0.0, 0.0, 1.0), delta_angle),
        )
        self._set_placement(obj, obj.Placement.multiply(delta_roll))
        self._last_section_rotation = current

    def _setup_properties(self, obj):
        """Create missing properties and migrate objects from v0.1.0."""
        group_geometry = "Geometria"
        group_section = "Seção"
        group_identity = "Identificação"
        group_quantities = "Quantitativos"
        group_adjustment = "Ajuste de extremidade"

        created_start = _add_property(obj, "App::PropertyVector", "StartPoint", "Ponto inicial", group_geometry, "Ponto inicial do eixo do elemento.")
        created_end = _add_property(obj, "App::PropertyVector", "EndPoint", "Ponto final", group_geometry, "Ponto final do eixo do elemento.")
        created_length = _add_property(obj, "App::PropertyLength", "Length", "Length", group_geometry, "Comprimento editável do elemento. Ao alterar, o ponto inicial é mantido e o ponto final é deslocado ao longo da direção atual.")
        created_insertion = _add_property(obj, "App::PropertyEnumeration", "Insertion", "Inserção", group_geometry, "Posição do eixo em relação à seção.")
        created_rotation = _add_property(obj, "App::PropertyAngle", "Rotation", "Rotação da seção", group_geometry, "Rotação da seção em torno do eixo longitudinal do membro.")
        created_offset_x = _add_property(obj, "App::PropertyDistance", "OffsetX", "Deslocamento X local", group_geometry, "Deslocamento no eixo X local da seção.")
        created_offset_y = _add_property(obj, "App::PropertyDistance", "OffsetY", "Deslocamento Y local", group_geometry, "Deslocamento no eixo Y local da seção.")
        created_start_ext = _add_property(obj, "App::PropertyDistance", "StartExtension", "Extensão inicial", group_geometry, "Prolongamento além do ponto inicial.")
        created_end_ext = _add_property(obj, "App::PropertyDistance", "EndExtension", "Extensão final", group_geometry, "Prolongamento além do ponto final.")

        created_adjustment_mode = _add_property(obj, "App::PropertyEnumeration", "EndAdjustmentMode", "Modo", group_adjustment, "Modo do ajuste longitudinal de extremidade.")
        created_adjusted_end = _add_property(obj, "App::PropertyEnumeration", "AdjustedEnd", "Extremidade ajustada", group_adjustment, "Extremidade nominal afetada pelo ajuste.")
        created_adjustment_gap = _add_property(obj, "App::PropertyDistance", "AdjustmentGap", "Folga", group_adjustment, "Recuo adicional em relação à referência; valores negativos prolongam o membro.")
        created_fixed_offset = _add_property(obj, "App::PropertyDistance", "FixedReferenceOffset", "Deslocamento da referência fixa", group_adjustment, "Posição longitudinal da referência com folga zero, medida a partir da extremidade nominal ajustada.")
        created_effective_start = _add_property(obj, "App::PropertyVector", "EffectiveStartPoint", "Ponto inicial efetivo", group_adjustment, "Ponto inicial efetivo sobre o eixo longitudinal.")
        created_effective_end = _add_property(obj, "App::PropertyVector", "EffectiveEndPoint", "Ponto final efetivo", group_adjustment, "Ponto final efetivo sobre o eixo longitudinal.")
        created_adjusted_length = _add_property(obj, "App::PropertyLength", "AdjustedLength", "Comprimento ajustado", group_adjustment, "Distância axial entre os pontos efetivos.")
        _add_property(obj, "App::PropertyLinkSub", "AdjustmentReference", "Referência", group_adjustment, "Face plana ou aresta reta explícita utilizada pelo ajuste associativo.")
        created_geometry_mode = _add_property(obj, "App::PropertyEnumeration", "AdjustmentGeometryMode", "Modo geométrico", group_adjustment, "Define se a referência limita o comprimento ou recorta por plano.")
        created_fixed_plane_normal = _add_property(obj, "App::PropertyVector", "FixedPlaneNormal", "Normal fixa do plano", group_adjustment, "Normal unitária do PlaneCut fixo no sistema local do membro.")

        created_category = _add_property(obj, "App::PropertyEnumeration", "ProfileCategory", "Categoria do perfil", group_section, "Categoria tecnológica do perfil.")
        created_series = _add_property(obj, "App::PropertyEnumeration", "ProfileSeries", "Série do perfil", group_section, "Série ou família comercial do perfil.")
        created_profile = _add_property(obj, "App::PropertyEnumeration", "Profile", "Perfil", group_section, "Perfil estrutural do catálogo.")
        _add_property(obj, "App::PropertyString", "Manufacturer", "Fabricante", group_section, "Fabricante do perfil.")
        _add_property(obj, "App::PropertyString", "ProfileFamily", "Família", group_section, "Família técnica do perfil.")
        created_material = _add_property(obj, "App::PropertyEnumeration", "Material", "Material", group_section, "Material atribuído ao elemento.")

        created_type = _add_property(obj, "App::PropertyEnumeration", "ElementType", "Tipo", group_identity, "Classificação funcional do elemento.")
        created_display_name = _add_property(obj, "App::PropertyString", "DisplayName", "Nome", group_identity, "Nome apresentado na árvore do documento.")
        created_mark = _add_property(obj, "App::PropertyString", "Mark", "Marca", group_identity, "Marca ou identificação da peça.")
        created_phase = _add_property(obj, "App::PropertyString", "Phase", "Fase", group_identity, "Fase de modelagem ou montagem.")

        _add_property(obj, "App::PropertyLength", "MemberLength", "Comprimento", group_quantities, "Comprimento geométrico calculado entre os pontos inicial e final, sem extensões.")
        _add_property(obj, "App::PropertyFloat", "MassPerMeter", "Massa linear (kg/m)", group_quantities, "Massa linear informada no catálogo.")
        _add_property(obj, "App::PropertyFloat", "TotalMass", "Massa total (kg)", group_quantities, "Massa linear multiplicada pelo comprimento.")
        _add_property(obj, "App::PropertyFloat", "CatalogArea", "Área do catálogo (cm²)", group_quantities, "Área geométrica informada no catálogo.")
        _add_property(obj, "App::PropertyString", "CatalogSource", "Fonte do catálogo", group_quantities, "Documento de origem dos dados.")

        # Enumeration options are assigned only after all dependent properties
        # exist. This prevents the onChanged race reported in FreeCAD 1.1.3.
        current_insertion = str(obj.Insertion) if not created_insertion else ""
        _set_enum(obj, "ElementType", ELEMENT_TYPES, "Membro" if created_type else None)
        _set_enum(obj, "Material", MATERIALS, "ASTM A572 Grau 50" if created_material else None)
        _set_enum(obj, "EndAdjustmentMode", ("None", "Associative", "Fixed"), "None" if created_adjustment_mode else None)
        _set_enum(obj, "AdjustedEnd", ("Start", "End"), "Start" if created_adjusted_end else None)
        _set_enum(obj, "AdjustmentGeometryMode", ("LengthLimit", "PlaneCut"), "LengthLimit" if created_geometry_mode else None)

        current_profile = str(obj.Profile) if not created_profile and str(obj.Profile) else ""
        if current_profile:
            try:
                current_data = profile_catalog.get(current_profile)
                current_profile = profile_catalog.property_designation(current_data.designation)
                preferred_category = current_data.category
                preferred_series = current_data.series
            except KeyError:
                preferred_category = "Aço laminado"
                preferred_series = "Perfis W"
        else:
            preferred_category = "Aço laminado"
            preferred_series = "Perfis W"

        category_preference = preferred_category if created_category else None
        _set_enum(obj, "ProfileCategory", profile_catalog.categories(), category_preference)
        selected_category = str(obj.ProfileCategory)

        available_series = profile_catalog.series_for_category(selected_category)
        series_preference = preferred_series if created_series else None
        _set_enum(obj, "ProfileSeries", available_series, series_preference, EMPTY_SERIES)
        selected_series = str(obj.ProfileSeries)

        available_profiles = profile_catalog.property_designations(selected_category, selected_series)
        profile_preference = current_profile if current_profile in available_profiles else None
        _set_enum(obj, "Profile", available_profiles, profile_preference, EMPTY_PROFILE)
        try:
            selected_profile = profile_catalog.get(str(obj.Profile))
            available_insertions = insertion_options(selected_profile)
        except KeyError:
            available_insertions = tuple(INSERTION_OPTIONS)
        insertion_preference = current_insertion if current_insertion in available_insertions else None
        _set_enum(
            obj, "Insertion", available_insertions,
            insertion_preference or ("Centroide" if created_insertion else None),
        )

        for prop in ("Manufacturer", "ProfileFamily", "MemberLength", "MassPerMeter", "TotalMass", "CatalogArea", "CatalogSource", "EffectiveStartPoint", "EffectiveEndPoint", "AdjustedLength"):
            obj.setEditorMode(prop, 1)

        if created_start:
            obj.StartPoint = App.Vector(0.0, 0.0, 0.0)
        if created_end:
            obj.EndPoint = App.Vector(0.0, 0.0, 3000.0)
        if created_length:
            length = App.Vector(obj.EndPoint).sub(App.Vector(obj.StartPoint)).Length
            obj.Length = length
            self._last_valid_length = length
        if created_rotation:
            obj.Rotation = 0.0
        if created_offset_x:
            obj.OffsetX = 0.0
        if created_offset_y:
            obj.OffsetY = 0.0
        if created_start_ext:
            obj.StartExtension = 0.0
        if created_end_ext:
            obj.EndExtension = 0.0
        if created_adjustment_gap:
            obj.AdjustmentGap = 0.0
        if created_fixed_offset:
            obj.FixedReferenceOffset = 0.0
        if created_effective_start:
            obj.EffectiveStartPoint = App.Vector(obj.StartPoint)
        if created_effective_end:
            obj.EffectiveEndPoint = App.Vector(obj.EndPoint)
        if created_adjusted_length:
            obj.AdjustedLength = App.Vector(obj.EndPoint).sub(App.Vector(obj.StartPoint)).Length
        if created_fixed_plane_normal:
            obj.FixedPlaneNormal = App.Vector(0.0, 0.0, 0.0)
        if created_mark:
            obj.Mark = ""
        if created_phase:
            obj.Phase = ""
        if created_display_name:
            obj.DisplayName = obj.Label

        self._update_catalog_properties(obj)

    def _sync_length_from_points(self, obj):
        length = App.Vector(obj.EndPoint).sub(App.Vector(obj.StartPoint)).Length
        if length <= LENGTH_TOLERANCE:
            return False
        obj.MemberLength = length
        if not _has_expression(obj, "Length"):
            obj.Length = length
        self._last_valid_length = length
        return True

    def _sync_endpoint_from_length(self, obj):
        requested = _quantity_value(obj.Length)
        axis = App.Vector(obj.EndPoint).sub(App.Vector(obj.StartPoint))
        if requested <= LENGTH_TOLERANCE or axis.Length <= LENGTH_TOLERANCE:
            if self._last_valid_length and self._last_valid_length > LENGTH_TOLERANCE:
                obj.Length = self._last_valid_length
            App.Console.PrintWarning("Steel Structures: comprimento ou direção inválida.\n")
            return False
        direction = App.Vector(axis)
        direction.normalize()
        obj.EndPoint = App.Vector(obj.StartPoint).add(direction * requested)
        obj.MemberLength = requested
        self._last_valid_length = requested
        return True

    def _refresh_series_and_profiles(self, obj):
        category = str(obj.ProfileCategory)
        _set_enum(obj, "ProfileSeries", profile_catalog.series_for_category(category), empty_text=EMPTY_SERIES)
        series = str(obj.ProfileSeries)
        _set_enum(
            obj, "Profile", profile_catalog.property_designations(category, series),
            empty_text=EMPTY_PROFILE,
        )

    def _refresh_profiles(self, obj):
        category = str(obj.ProfileCategory)
        series = str(obj.ProfileSeries)
        _set_enum(
            obj, "Profile", profile_catalog.property_designations(category, series),
            empty_text=EMPTY_PROFILE,
        )

    def _refresh_insertions(self, obj):
        try:
            profile = profile_catalog.get(str(obj.Profile))
        except KeyError:
            return
        _set_enum(obj, "Insertion", insertion_options(profile))

    def _update_catalog_properties(self, obj):
        required = {"Profile", "Manufacturer", "ProfileFamily", "MassPerMeter", "CatalogArea", "CatalogSource"}
        if not required.issubset(set(obj.PropertiesList)):
            return
        designation = str(obj.Profile)
        if not designation:
            return
        try:
            profile = profile_catalog.get(designation)
        except KeyError:
            return
        obj.Manufacturer = profile.manufacturer
        obj.ProfileFamily = profile.family
        obj.MassPerMeter = profile.mass_per_m
        obj.CatalogArea = profile.area_cm2
        obj.CatalogSource = profile.source

    def execute(self, obj):
        # Also upgrades objects saved with v0.1.0 when they are recomputed.
        required_properties = {
            "ProfileCategory", "DisplayName", "Length", "EndAdjustmentMode",
            "AdjustedEnd", "AdjustmentGap", "FixedReferenceOffset",
            "EffectiveStartPoint", "EffectiveEndPoint", "AdjustedLength",
            "AdjustmentReference",
            "AdjustmentGeometryMode", "FixedPlaneNormal",
        }
        if not required_properties.issubset(set(obj.PropertiesList)):
            self._updating = True
            try:
                self._setup_properties(obj)
            finally:
                self._updating = False

        start = App.Vector(obj.StartPoint)
        end = App.Vector(obj.EndPoint)
        axis = end.sub(start)
        base_length = axis.Length

        if base_length <= LENGTH_TOLERANCE:
            obj.Shape = Part.Shape()
            obj.MemberLength = 0.0
            obj.EffectiveStartPoint = start
            obj.EffectiveEndPoint = start
            obj.AdjustedLength = 0.0
            obj.TotalMass = 0.0
            return

        # normalize() mutates the vector in FreeCAD. Do not rely on its return
        # value, which differs between FreeCAD/Python bindings.
        direction = App.Vector(axis)
        direction.normalize()

        mode = str(obj.EndAdjustmentMode)
        geometry_mode = str(obj.AdjustmentGeometryMode)
        reference_point = None
        reference_plane = None
        if mode == "Associative":
            unpacked_reference = unpack_link_sub(obj.AdjustmentReference)
            if (unpacked_reference is None
                    or would_create_adjustment_cycle(obj, unpacked_reference[0])):
                obj.Shape = Part.Shape()
                obj.MemberLength = base_length
                obj.EffectiveStartPoint = start
                obj.EffectiveEndPoint = start
                obj.AdjustedLength = 0.0
                obj.TotalMass = 0.0
                return
            subelement = unpacked_reference[1]
            if subelement.startswith("Face"):
                reference_plane = plane_reference_from_link(obj.AdjustmentReference)
                if reference_plane is not None:
                    reference_point = intersect_infinite_axis_with_plane(
                        (start.x, start.y, start.z), (end.x, end.y, end.z),
                        reference_plane.point_global, reference_plane.normal_global,
                        LENGTH_TOLERANCE,
                    )
            elif geometry_mode == "LengthLimit" and subelement.startswith("Edge"):
                line = linear_reference_from_link(obj.AdjustmentReference, LENGTH_TOLERANCE)
                if line is not None:
                    reference_point = closest_point_on_member_axis(
                        (start.x, start.y, start.z), (end.x, end.y, end.z),
                        line.point_global, line.direction_global, LENGTH_TOLERANCE,
                    )
            if reference_point is None:
                obj.Shape = Part.Shape()
                obj.MemberLength = base_length
                obj.EffectiveStartPoint = start
                obj.EffectiveEndPoint = start
                obj.AdjustedLength = 0.0
                obj.TotalMass = 0.0
                return

        extents = physical_extents(
            (start.x, start.y, start.z), (end.x, end.y, end.z),
            mode=mode, adjusted_end=str(obj.AdjustedEnd),
            reference_offset=_quantity_value(obj.FixedReferenceOffset),
            gap=_quantity_value(obj.AdjustmentGap),
            start_extension=_quantity_value(obj.StartExtension),
            end_extension=_quantity_value(obj.EndExtension),
            reference_point=reference_point,
            tolerance=LENGTH_TOLERANCE,
        )
        effective_start = App.Vector(*extents.start)
        effective_end = App.Vector(*extents.end)
        obj.EffectiveStartPoint = effective_start
        obj.EffectiveEndPoint = effective_end if extents.valid else effective_start
        obj.AdjustedLength = extents.length
        if not extents.valid:
            obj.Shape = Part.Shape()
            obj.MemberLength = base_length
            obj.TotalMass = 0.0
            return
        total_length = extents.length
        try:
            profile = profile_catalog.get(str(obj.Profile))
        except KeyError:
            obj.Shape = Part.Shape()
            obj.MemberLength = base_length
            obj.TotalMass = 0.0
            return

        face = _section_face(profile)
        tx, ty = _insertion_translation(profile, str(obj.Insertion))
        face.translate(App.Vector(tx + obj.OffsetX.Value, ty + obj.OffsetY.Value, 0.0))

        # Keep the shape local and drive position/orientation through the
        # Part::Feature Placement. This fixes members remaining vertical when
        # the end point is in X/Y and makes the custom section rotation work.
        alignment = _member_frame_rotation(direction)
        roll = App.Rotation(App.Vector(0.0, 0.0, 1.0), float(obj.Rotation.Value))
        combined_rotation = alignment.multiply(roll)
        base = effective_start
        if self._placement_from_points_pending or self._last_placement is None:
            shape_placement = App.Placement(base, combined_rotation)
        else:
            # Preserve the full user rotation. Only the base follows the global
            # start point and extension; profile changes cannot reset Placement.
            preserved = _copy_placement(obj.Placement)
            preserved.Base = base
            shape_placement = preserved

        plane_cut_active = geometry_mode == "PlaneCut" and mode in ("Associative", "Fixed")
        plane_cut_oblique = False
        local_plane_point = (0.0, 0.0, 0.0)
        if plane_cut_active:
            if mode == "Associative":
                local_plane = global_plane_to_member_local(
                    shape_placement, App.Vector,
                    reference_plane.point_global, reference_plane.normal_global,
                    LENGTH_TOLERANCE,
                )
                if local_plane is None:
                    obj.Shape = Part.Shape()
                    obj.MemberLength = base_length
                    obj.TotalMass = 0.0
                    return
                local_plane_point, local_normal = local_plane
            else:
                stored_normal = App.Vector(obj.FixedPlaneNormal)
                local_normal = (stored_normal.x, stored_normal.y, stored_normal.z)
                if normalized_vector(local_normal, LENGTH_TOLERANCE) is None:
                    local_normal = (0.0, 0.0, 1.0)

            normalized_normal = normalized_vector(local_normal, LENGTH_TOLERANCE)
            if normalized_normal is None or abs(normalized_normal[2]) <= LENGTH_TOLERANCE:
                obj.Shape = Part.Shape()
                obj.MemberLength = base_length
                obj.TotalMass = 0.0
                return
            plane_cut_oblique = not is_orthogonal_plane(normalized_normal, LENGTH_TOLERANCE)
        if plane_cut_oblique:
            cut_station = 0.0 if str(obj.AdjustedEnd) == "Start" else total_length
            cut_result = build_plane_cut(
                Part, App.Vector, face, total_length, cut_station, normalized_normal,
                str(obj.AdjustedEnd), LENGTH_TOLERANCE, point_local=local_plane_point,
            )
            if cut_result is None:
                obj.Shape = Part.Shape()
                obj.MemberLength = base_length
                obj.TotalMass = 0.0
                return
            solid = cut_result.shape
        else:
            solid = face.extrude(App.Vector(0.0, 0.0, total_length))

        obj.Shape = solid
        self._set_placement(obj, shape_placement)
        self._placement_from_points_pending = False
        obj.MemberLength = base_length
        if plane_cut_oblique and cut_result.section_area > LENGTH_TOLERANCE:
            equivalent_length = float(solid.Volume) / cut_result.section_area
            obj.TotalMass = profile.mass_per_m * equivalent_length / 1000.0
        else:
            obj.TotalMass = profile.mass_per_m * total_length / 1000.0
        self._update_catalog_properties(obj)

    def onChanged(self, obj, prop):
        if (getattr(self, "_updating", False) or getattr(self, "_syncing_length", False)
                or getattr(self, "_syncing_placement", False)):
            return
        if prop == "Placement":
            try:
                self._sync_points_from_placement(obj)
            except (AttributeError, RuntimeError, TypeError, ValueError):
                pass
            return
        if prop in ("Length", "StartPoint", "EndPoint"):
            self._syncing_length = True
            try:
                if prop == "Length":
                    self._sync_endpoint_from_length(obj)
                else:
                    self._sync_length_from_points(obj)
                self._placement_from_points_pending = True
            except (AttributeError, RuntimeError, TypeError, ValueError):
                pass
            finally:
                self._syncing_length = False
            return
        self._updating = True
        try:
            if prop == "Rotation":
                self._apply_section_rotation_change(obj)
            elif prop == "ProfileCategory" and "ProfileSeries" in obj.PropertiesList:
                self._refresh_series_and_profiles(obj)
                self._update_catalog_properties(obj)
                self._refresh_insertions(obj)
            elif prop == "ProfileSeries" and "Profile" in obj.PropertiesList:
                self._refresh_profiles(obj)
                self._update_catalog_properties(obj)
                self._refresh_insertions(obj)
            elif prop == "Profile":
                self._update_catalog_properties(obj)
                self._refresh_insertions(obj)
            elif prop == "DisplayName" and "DisplayName" in obj.PropertiesList:
                value = str(obj.DisplayName).strip()
                if value and obj.Label != value:
                    obj.Label = value
            elif prop == "Label" and "DisplayName" in obj.PropertiesList:
                if str(obj.DisplayName) != obj.Label:
                    obj.DisplayName = obj.Label
        except (AttributeError, KeyError, RuntimeError):
            # During document restore FreeCAD can emit changes while a legacy
            # object is still receiving its newly added properties.
            pass
        finally:
            self._updating = False

    def onDocumentRestored(self, obj):
        self._updating = True
        try:
            self._setup_properties(obj)
            self._syncing_length = True
            try:
                self._sync_length_from_points(obj)
            finally:
                self._syncing_length = False
            self._placement_from_points_pending = False
            self._last_section_rotation = _quantity_value(obj.Rotation)
            self._remember_placement(obj)
        finally:
            self._updating = False

    def dumps(self):
        return None

    def loads(self, state):
        return None

    def __getstate__(self):
        return None

    def __setstate__(self, state):
        self._updating = False
        self._syncing_length = False
        self._syncing_placement = False
        self._placement_from_points_pending = False
        self._last_placement = None
        self._last_section_rotation = 0.0
        self._last_valid_length = None


class StructuralMemberViewProvider:
    def __init__(self, view_object):
        view_object.Proxy = self

    def getIcon(self):
        return OBJECT_ICON

    def attach(self, view_object):
        self.ViewObject = view_object
        self.Object = view_object.Object

    def updateData(self, obj, prop):
        pass

    def onChanged(self, view_object, prop):
        pass

    def getDisplayModes(self, view_object):
        return []

    def getDefaultDisplayMode(self):
        return "Flat Lines"

    def setDisplayMode(self, mode):
        return mode

    def claimChildren(self):
        return []

    def dumps(self):
        return None

    def loads(self, state):
        return None

    def __getstate__(self):
        return None

    def __setstate__(self, state):
        return None


def create_member(
    document,
    start: App.Vector,
    end: App.Vector,
    designation: str,
    element_type: str = "Membro",
    insertion: str = "Centroide",
    rotation: float = 0.0,
    color=(0.72, 0.72, 0.76),
    display_name: str | None = None,
):
    obj = document.addObject("Part::FeaturePython", "StructuralMember")
    StructuralMemberProxy(obj)
    StructuralMemberViewProvider(obj.ViewObject)

    profile = profile_catalog.get(designation)
    obj.StartPoint = start
    obj.EndPoint = end
    obj.ProfileCategory = profile.category
    obj.ProfileSeries = profile.series
    obj.Profile = profile_catalog.property_designation(profile.designation)
    obj.ElementType = element_type if element_type in ELEMENT_TYPES else "Membro"
    valid_insertions = insertion_options(profile)
    obj.Insertion = insertion if insertion in valid_insertions else valid_insertions[0]
    obj.Rotation = rotation

    final_name = (display_name or f"{obj.ElementType} - {designation}").strip()
    obj.DisplayName = final_name
    obj.Label = final_name

    obj.ViewObject.ShapeColor = tuple(float(component) for component in color)
    obj.ViewObject.LineColor = (0.15, 0.15, 0.15)
    document.recompute()
    return obj
