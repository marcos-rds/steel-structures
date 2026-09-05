# SPDX-License-Identifier: LGPL-2.1-or-later
"""Parametric structural member document object."""

from __future__ import annotations

from typing import Tuple

import FreeCAD as App
import Part

from . import profile_catalog
from .member_adjustment_geometry import (
    axis_geometry,
    closest_point_on_member_axis,
    intersect_infinite_axis_with_plane,
    normalized_vector,
)
from .member_adjustment_reference import (
    linear_reference_from_link,
    plane_reference_from_link,
    unpack_link_sub,
    would_create_adjustment_cycle,
)
from .member_axis_source import resolve_axis_source
from .member_plane_cut import (
    PlaneCutSpec,
    build_plane_cuts,
    global_plane_to_member_local,
    is_orthogonal_plane,
)
from .paths import OBJECT_ICON
from .profiles.freecad_geometry import section_geometry_to_face
from .profiles.geometry import (
    SectionGeometryMode, build_parallel_flange_i_section, build_section_geometry,
)
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


def _section_geometry(profile: profile_catalog.Profile, mode=SectionGeometryMode.DETAILED):
    """Resolve every constructible catalog profile through the typed core."""
    definition = getattr(profile, "definition", None)
    if definition is not None:
        return build_section_geometry(definition, mode)
    return build_parallel_flange_i_section(
        d=profile.d, bf=profile.bf, tw=profile.tw, tf=profile.tf
    )


def _section_face(profile: profile_catalog.Profile, mode=SectionGeometryMode.DETAILED) -> Part.Face:
    return section_geometry_to_face(_section_geometry(profile, mode))


def insertion_options(profile: profile_catalog.Profile):
    options = profile_catalog.insertion_options(profile)
    if options:
        return options
    return tuple(item.label for item in section_insertion_references(_section_geometry(profile)))


def _insertion_translation(profile: profile_catalog.Profile, insertion: str,
                           geometry_mode=SectionGeometryMode.DETAILED) -> Tuple[float, float]:
    return _geometry_insertion_translation(_section_geometry(profile, geometry_mode), insertion)


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
        self._syncing_axis_source = False
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
        legacy_names = {
            "EndAdjustmentMode", "AdjustedEnd", "AdjustmentGeometryMode",
            "AdjustmentReference", "AdjustmentGap", "FixedReferenceOffset",
            "FixedPlaneNormal",
        }
        legacy_present = legacy_names.issubset(set(obj.PropertiesList))
        legacy = None
        if legacy_present:
            legacy = {
                "mode": str(obj.EndAdjustmentMode), "end": str(obj.AdjustedEnd),
                "geometry": str(obj.AdjustmentGeometryMode),
                "reference": obj.AdjustmentReference,
                "gap": _quantity_value(obj.AdjustmentGap),
                "offset": _quantity_value(obj.FixedReferenceOffset),
                "normal": App.Vector(obj.FixedPlaneNormal),
            }
        group_geometry = "Geometria"
        group_axis = "Eixo nominal"
        group_section = "Seção"
        group_identity = "Identificação"
        group_quantities = "Quantitativos"
        group_start_adjustment = "Ajuste inicial"
        group_end_adjustment = "Ajuste final"
        group_adjustment_results = "Resultados dos ajustes"

        created_axis_mode = _add_property(obj, "App::PropertyEnumeration", "AxisDefinitionMode", "Definição", group_axis, "Define o eixo por pontos independentes ou por uma linha vinculada.")
        _add_property(obj, "App::PropertyLinkSub", "AxisSource", "Linha de origem", group_axis, "Draft Line que define continuamente o eixo nominal.")
        created_start = _add_property(obj, "App::PropertyVector", "StartPoint", "Ponto inicial", group_geometry, "Ponto inicial do eixo do elemento.")
        created_end = _add_property(obj, "App::PropertyVector", "EndPoint", "Ponto final", group_geometry, "Ponto final do eixo do elemento.")
        created_length = _add_property(obj, "App::PropertyLength", "Length", "Length", group_geometry, "Comprimento editável do elemento. Ao alterar, o ponto inicial é mantido e o ponto final é deslocado ao longo da direção atual.")
        created_insertion = _add_property(obj, "App::PropertyEnumeration", "Insertion", "Inserção", group_geometry, "Posição do eixo em relação à seção.")
        created_rotation = _add_property(obj, "App::PropertyAngle", "Rotation", "Rotação da seção", group_geometry, "Rotação da seção em torno do eixo longitudinal do membro.")
        created_offset_x = _add_property(obj, "App::PropertyDistance", "OffsetX", "Deslocamento X local", group_geometry, "Deslocamento no eixo X local da seção.")
        created_offset_y = _add_property(obj, "App::PropertyDistance", "OffsetY", "Deslocamento Y local", group_geometry, "Deslocamento no eixo Y local da seção.")
        created_start_ext = _add_property(obj, "App::PropertyDistance", "StartExtension", "Extensão inicial", group_geometry, "Prolongamento além do ponto inicial.")
        created_end_ext = _add_property(obj, "App::PropertyDistance", "EndExtension", "Extensão final", group_geometry, "Prolongamento além do ponto final.")

        created_slots = {}
        for prefix, group in (("Start", group_start_adjustment), ("End", group_end_adjustment)):
            created_slots[prefix] = {
                "mode": _add_property(obj, "App::PropertyEnumeration", prefix + "AdjustmentMode", "Modo", group, "Modo independente do ajuste desta extremidade."),
                "geometry": _add_property(obj, "App::PropertyEnumeration", prefix + "AdjustmentGeometryMode", "Modo geométrico", group, "Limita o comprimento ou recorta pelo plano."),
                "gap": _add_property(obj, "App::PropertyDistance", prefix + "AdjustmentGap", "Folga", group, "Recuo adicional; valores negativos prolongam o membro."),
                "offset": _add_property(obj, "App::PropertyDistance", prefix + "FixedReferenceOffset", "Deslocamento da referência fixa", group, "Posição longitudinal da referência fixa com folga zero."),
                "normal": _add_property(obj, "App::PropertyVector", prefix + "FixedPlaneNormal", "Normal fixa do plano", group, "Normal do PlaneCut fixo no sistema local do membro."),
            }
            _add_property(obj, "App::PropertyLinkSub", prefix + "AdjustmentReference", "Referência", group, "Face plana ou aresta reta explícita deste ajuste associativo.")
        created_effective_start = _add_property(obj, "App::PropertyVector", "EffectiveStartPoint", "Ponto inicial efetivo", group_adjustment_results, "Ponto inicial efetivo sobre o eixo longitudinal.")
        created_effective_end = _add_property(obj, "App::PropertyVector", "EffectiveEndPoint", "Ponto final efetivo", group_adjustment_results, "Ponto final efetivo sobre o eixo longitudinal.")
        created_adjusted_length = _add_property(obj, "App::PropertyLength", "AdjustedLength", "Comprimento ajustado", group_adjustment_results, "Distância axial entre os pontos efetivos.")

        created_category = _add_property(obj, "App::PropertyEnumeration", "ProfileCategory", "Categoria do perfil", group_section, "Categoria tecnológica do perfil.")
        created_series = _add_property(obj, "App::PropertyEnumeration", "ProfileSeries", "Série do perfil", group_section, "Série ou família comercial do perfil.")
        created_profile = _add_property(obj, "App::PropertyEnumeration", "Profile", "Perfil", group_section, "Perfil estrutural do catálogo.")
        created_section_geometry_mode = _add_property(
            obj, "App::PropertyEnumeration", "SectionGeometryMode", "Geometria da seção",
            group_section,
            "Detailed gera raios/filetes; Simplified usa cantos simplificados. As propriedades técnicas do perfil não são alteradas.",
        )
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
        _add_property(obj, "App::PropertyFloat", "CatalogArea", "Área técnica da seção (cm²)", group_quantities, "Área técnica efetiva; pode ser publicada ou calculada conforme o contrato do perfil e não é a área da BRep.")
        _add_property(obj, "App::PropertyString", "CatalogSource", "Fonte do catálogo", group_quantities, "Documento de origem dos dados.")

        # Enumeration options are assigned only after all dependent properties
        # exist. This prevents the onChanged race reported in FreeCAD 1.1.3.
        current_insertion = str(obj.Insertion) if not created_insertion else ""
        _set_enum(obj, "AxisDefinitionMode", ("Independent", "Linked"), "Independent" if created_axis_mode else None)
        _set_enum(obj, "ElementType", ELEMENT_TYPES, "Membro" if created_type else None)
        _set_enum(obj, "Material", MATERIALS, "ASTM A572 Grau 50" if created_material else None)
        _set_enum(obj, "SectionGeometryMode", ("Detailed", "Simplified"),
                  "Detailed" if created_section_geometry_mode else None)
        for prefix in ("Start", "End"):
            created = created_slots[prefix]
            _set_enum(obj, prefix + "AdjustmentMode", ("None", "Associative", "Fixed"), "None" if created["mode"] else None)
            _set_enum(obj, prefix + "AdjustmentGeometryMode", ("LengthLimit", "PlaneCut"), "LengthLimit" if created["geometry"] else None)

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

        available_profiles = profile_catalog.property_designations(
            selected_category, selected_series, current_profile,
        )
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
        for prefix in ("Start", "End"):
            created = created_slots[prefix]
            if created["gap"]:
                setattr(obj, prefix + "AdjustmentGap", 0.0)
            if created["offset"]:
                setattr(obj, prefix + "FixedReferenceOffset", 0.0)
            if created["normal"]:
                setattr(obj, prefix + "FixedPlaneNormal", App.Vector(0.0, 0.0, 0.0))
        if created_effective_start:
            obj.EffectiveStartPoint = App.Vector(obj.StartPoint)
        if created_effective_end:
            obj.EffectiveEndPoint = App.Vector(obj.EndPoint)
        if created_adjusted_length:
            obj.AdjustedLength = App.Vector(obj.EndPoint).sub(App.Vector(obj.StartPoint)).Length
        if created_mark:
            obj.Mark = ""
        if created_phase:
            obj.Phase = ""
        if created_display_name:
            obj.DisplayName = obj.Label

        if legacy is not None and legacy["mode"] != "None" and any(
                value for slot in created_slots.values() for value in slot.values()):
            prefix = "Start" if legacy["end"] == "Start" else "End"
            if prefix == "Start":
                obj.EndAdjustmentMode = "None"
            setattr(obj, prefix + "AdjustmentMode", legacy["mode"])
            setattr(obj, prefix + "AdjustmentGeometryMode", legacy["geometry"])
            setattr(obj, prefix + "AdjustmentReference", legacy["reference"])
            setattr(obj, prefix + "AdjustmentGap", legacy["gap"])
            setattr(obj, prefix + "FixedReferenceOffset", legacy["offset"])
            setattr(obj, prefix + "FixedPlaneNormal", legacy["normal"])
        if legacy_present:
            for name in legacy_names - {"EndAdjustmentMode"}:
                try:
                    obj.setEditorMode(name, 2)
                except Exception:
                    pass

        self._update_catalog_properties(obj)
        self._update_axis_editor_mode(obj)

    def _update_axis_editor_mode(self, obj):
        linked = str(getattr(obj, "AxisDefinitionMode", "Independent")) == "Linked"
        for name in ("StartPoint", "EndPoint", "Length"):
            try:
                obj.setEditorMode(name, 1 if linked else 0)
            except (AttributeError, RuntimeError):
                pass

    def _sync_axis_from_source(self, obj):
        if str(getattr(obj, "AxisDefinitionMode", "Independent")) != "Linked":
            return False
        resolved = resolve_axis_source(getattr(obj, "AxisSource", None))
        if resolved is None:
            return False
        current_start = App.Vector(obj.StartPoint)
        current_end = App.Vector(obj.EndPoint)
        if (current_start.sub(resolved.start).Length <= LENGTH_TOLERANCE
                and current_end.sub(resolved.end).Length <= LENGTH_TOLERANCE):
            return True
        self._syncing_axis_source = True
        self._syncing_length = True
        try:
            obj.StartPoint = App.Vector(resolved.start)
            obj.EndPoint = App.Vector(resolved.end)
            self._sync_length_from_points(obj)
            self._placement_from_points_pending = True
        finally:
            self._syncing_length = False
            self._syncing_axis_source = False
        return True

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
        # Also upgrades legacy and single-end objects when they are recomputed.
        required_properties = {
            "ProfileCategory", "DisplayName", "Length",
            "SectionGeometryMode",
            "StartAdjustmentMode", "StartAdjustmentGeometryMode",
            "StartAdjustmentReference", "StartAdjustmentGap",
            "StartFixedReferenceOffset", "StartFixedPlaneNormal",
            "EndAdjustmentMode", "EndAdjustmentGeometryMode",
            "EndAdjustmentReference", "EndAdjustmentGap",
            "EndFixedReferenceOffset", "EndFixedPlaneNormal",
            "EffectiveStartPoint", "EffectiveEndPoint", "AdjustedLength",
        }
        if not required_properties.issubset(set(obj.PropertiesList)):
            self._updating = True
            try:
                self._setup_properties(obj)
            finally:
                self._updating = False

        self._update_axis_editor_mode(obj)
        self._sync_axis_from_source(obj)

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

        direction = App.Vector(axis)
        direction.normalize()

        axis_data = axis_geometry(
            (start.x, start.y, start.z), (end.x, end.y, end.z), LENGTH_TOLERANCE
        )

        def fail():
            obj.Shape = Part.Shape()
            obj.MemberLength = base_length
            obj.EffectiveStartPoint = start
            obj.EffectiveEndPoint = start
            obj.AdjustedLength = 0.0
            obj.TotalMass = 0.0
            return False

        def resolve_slot(prefix):
            mode = str(getattr(obj, prefix + "AdjustmentMode"))
            geometry_mode = str(getattr(obj, prefix + "AdjustmentGeometryMode"))
            gap = _quantity_value(getattr(obj, prefix + "AdjustmentGap"))
            default_station = (-max(0.0, _quantity_value(obj.StartExtension))
                               if prefix == "Start" else
                               base_length + max(0.0, _quantity_value(obj.EndExtension)))
            if mode == "None":
                return {"mode": mode, "geometry": geometry_mode,
                        "station": default_station, "plane": None}
            if mode == "Fixed":
                offset = _quantity_value(getattr(obj, prefix + "FixedReferenceOffset"))
                station = offset if prefix == "Start" else base_length - offset
                plane = None
                if geometry_mode == "PlaneCut":
                    normal = App.Vector(getattr(obj, prefix + "FixedPlaneNormal"))
                    values = (normal.x, normal.y, normal.z)
                    if normalized_vector(values, LENGTH_TOLERANCE) is None:
                        values = (0.0, 0.0, 1.0)
                    plane = {"local_normal": values, "global": None}
            elif mode == "Associative":
                reference = getattr(obj, prefix + "AdjustmentReference")
                unpacked = unpack_link_sub(reference)
                if unpacked is None or would_create_adjustment_cycle(obj, unpacked[0]):
                    return None
                subelement = unpacked[1]
                plane_reference = None
                reference_point = None
                if subelement.startswith("Face"):
                    plane_reference = plane_reference_from_link(reference)
                    if plane_reference is not None:
                        reference_point = intersect_infinite_axis_with_plane(
                            axis_data.start, axis_data.end,
                            plane_reference.point_global, plane_reference.normal_global,
                            LENGTH_TOLERANCE,
                        )
                elif geometry_mode == "LengthLimit" and subelement.startswith("Edge"):
                    line = linear_reference_from_link(reference, LENGTH_TOLERANCE)
                    if line is not None:
                        reference_point = closest_point_on_member_axis(
                            axis_data.start, axis_data.end,
                            line.point_global, line.direction_global, LENGTH_TOLERANCE,
                        )
                if reference_point is None:
                    return None
                station = sum((value - origin) * component for value, origin, component
                              in zip(reference_point, axis_data.start, axis_data.direction))
                plane = ({"local_normal": None, "global": plane_reference}
                         if geometry_mode == "PlaneCut" else None)
            else:
                return None
            station += gap if prefix == "Start" else -gap
            return {"mode": mode, "geometry": geometry_mode,
                    "station": station, "plane": plane}

        start_slot, end_slot = resolve_slot("Start"), resolve_slot("End")
        if start_slot is None or end_slot is None:
            fail()
            return
        start_station, end_station = start_slot["station"], end_slot["station"]
        total_length = end_station - start_station
        if total_length <= LENGTH_TOLERANCE:
            fail()
            return
        effective_start = start.add(direction * start_station)
        effective_end = start.add(direction * end_station)
        obj.EffectiveStartPoint = effective_start
        obj.EffectiveEndPoint = effective_end
        obj.AdjustedLength = total_length
        try:
            profile = profile_catalog.get(str(obj.Profile))
        except KeyError:
            fail()
            return

        geometry = _section_geometry(profile, str(obj.SectionGeometryMode))
        face = section_geometry_to_face(geometry)
        tx, ty = _geometry_insertion_translation(geometry, str(obj.Insertion))
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

        cuts = []
        for prefix, slot in (("Start", start_slot), ("End", end_slot)):
            plane = slot["plane"]
            if plane is None:
                continue
            point_local = None
            local_normal = plane["local_normal"]
            if plane["global"] is not None:
                global_plane = plane["global"]
                local = global_plane_to_member_local(
                    shape_placement, App.Vector,
                    global_plane.point_global, global_plane.normal_global,
                    LENGTH_TOLERANCE,
                )
                if local is None:
                    fail()
                    return
                point_local, local_normal = local
            normal = normalized_vector(local_normal, LENGTH_TOLERANCE)
            if normal is None or abs(normal[2]) <= LENGTH_TOLERANCE:
                fail()
                return
            if not is_orthogonal_plane(normal, LENGTH_TOLERANCE):
                cuts.append(PlaneCutSpec(prefix, normal, point_local))
        if cuts:
            cut_result = build_plane_cuts(
                Part, App.Vector, face, total_length, cuts, LENGTH_TOLERANCE
            )
            if cut_result is None:
                fail()
                return
            solid = cut_result.shape
        else:
            solid = face.extrude(App.Vector(0.0, 0.0, total_length))

        obj.Shape = solid
        self._set_placement(obj, shape_placement)
        self._placement_from_points_pending = False
        obj.MemberLength = base_length
        if cuts and cut_result.section_area > LENGTH_TOLERANCE:
            equivalent_length = float(solid.Volume) / cut_result.section_area
            obj.TotalMass = profile.mass_per_m * equivalent_length / 1000.0
        else:
            obj.TotalMass = profile.mass_per_m * total_length / 1000.0
        self._update_catalog_properties(obj)

    def onChanged(self, obj, prop):
        if (getattr(self, "_updating", False) or getattr(self, "_syncing_length", False)
                or getattr(self, "_syncing_placement", False)
                or getattr(self, "_syncing_axis_source", False)):
            return
        if prop == "Placement":
            if str(getattr(obj, "AxisDefinitionMode", "Independent")) == "Linked":
                self._placement_from_points_pending = True
                return
            try:
                self._sync_points_from_placement(obj)
            except (AttributeError, RuntimeError, TypeError, ValueError):
                pass
            return
        if prop in ("Length", "StartPoint", "EndPoint"):
            if str(getattr(obj, "AxisDefinitionMode", "Independent")) == "Linked":
                return
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
            if prop == "AxisDefinitionMode":
                self._update_axis_editor_mode(obj)
            elif prop == "Rotation":
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
        self._syncing_axis_source = False
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
    axis_source=None,
    link_axis: bool = False,
    section_geometry_mode: str = "Detailed",
):
    obj = document.addObject("Part::FeaturePython", "StructuralMember")
    StructuralMemberProxy(obj)
    StructuralMemberViewProvider(obj.ViewObject)

    profile = profile_catalog.get(designation)
    obj.StartPoint = start
    obj.EndPoint = end
    if link_axis and resolve_axis_source(axis_source) is not None:
        obj.AxisDefinitionMode = "Linked"
        obj.AxisSource = axis_source
    else:
        obj.AxisDefinitionMode = "Independent"
        obj.AxisSource = None
    obj.ProfileCategory = profile.category
    obj.ProfileSeries = profile.series
    obj.Profile = profile_catalog.property_designation(profile.designation)
    obj.SectionGeometryMode = section_geometry_mode if section_geometry_mode in (
        "Detailed", "Simplified") else "Detailed"
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
