# SPDX-License-Identifier: LGPL-2.1-or-later
"""Persistent, source-neutral parametric StructuralPlate FreeCAD object."""

from __future__ import annotations

from contextlib import contextmanager

import FreeCAD as App

from .member_adjustment_reference import would_create_adjustment_cycle
from .plate_freecad_geometry import build_plate_shape
from .plate_geometry import PlateContour2D
from .plate_sources import reference_containers, resolve_plate_source


PLATE_SCHEMA_VERSION = 1
SOURCE_MODES = ("DraftRectangle", "DraftWire", "InteractivePolygon",
                "InteractiveRectangle", "Sketch", "Face")
_DRAFT_MODES = frozenset(("DraftRectangle", "DraftWire"))
_SCHEMA = (
    ("App::PropertyInteger", "SchemaVersion", "Identidade", "Versão do esquema da Chapa Estrutural."),
    ("App::PropertyString", "DisplayName", "Identidade", "Nome exibido no documento."),
    ("App::PropertyLength", "Thickness", "Geometria", "Espessura positiva na direção Z local."),
    ("App::PropertyDistance", "Offset", "Geometria", "Posição assinada da face de referência em Z local."),
    ("App::PropertyBool", "ReverseExtrusion", "Geometria", "Extrudar para o lado -Z local da face de referência."),
    ("App::PropertyString", "ContourData", "Geometria", "Contorno 2D local versionado."),
    ("App::PropertyEnumeration", "SourceMode", "Origem", "Modo de origem do contorno."),
    ("App::PropertyBool", "KeepSourceLink", "Origem", "Atualizar a chapa quando a origem mudar."),
    ("App::PropertyLink", "SourceObject", "Origem", "Objeto Draft vinculado."),
    ("App::PropertyString", "SourceSubElement", "Origem", "Subelemento reservado para origem futura."),
    ("App::PropertyLinkList", "SourceContainers", "Origem", "Dependências de Placement dos contêineres da origem."),
    ("App::PropertyArea", "GrossArea", "Resultados", "Área bruta do contorno."),
    ("App::PropertyVolume", "EnvelopeVolume", "Resultados", "Volume do sólido simples."),
    ("App::PropertyString", "GenerationStatus", "Resultados", "Estado do último recompute."),
)
_REQUIRED_PROPERTIES = frozenset(item[1] for item in _SCHEMA)
_READ_ONLY = ("SchemaVersion", "ContourData", "SourceMode", "SourceSubElement",
              "GrossArea", "EnvelopeVolume", "GenerationStatus")
_RECOMPUTE_PROPERTIES = ("Thickness", "Offset", "ReverseExtrusion", "ContourData", "SourceMode",
                         "KeepSourceLink", "SourceObject", "Placement")


def _number(value):
    return float(getattr(value, "Value", value))


def _placement_signature(placement):
    try:
        base = placement.Base
        return (base.x, base.y, base.z, tuple(placement.Rotation.Q))
    except (AttributeError, ReferenceError, RuntimeError, TypeError):
        return None


def _copy_placement(placement):
    try:
        return App.Placement(placement)
    except (AttributeError, ReferenceError, RuntimeError, TypeError):
        return placement.copy()


@contextmanager
def _preserve_placement(obj):
    """Protect against FreeCAD Shape/property writes resetting native Placement."""
    saved = _copy_placement(obj.Placement)
    signature = _placement_signature(saved)
    try:
        yield
    finally:
        if _placement_signature(obj.Placement) != signature:
            obj.Placement = saved


def _refresh_mode(obj, default="InteractivePolygon"):
    current = str(getattr(obj, "SourceMode", ""))
    obj.SourceMode = list(SOURCE_MODES)
    obj.SourceMode = current if current in SOURCE_MODES else default


def _check_source_cycle(obj, source, containers):
    if source is obj or would_create_adjustment_cycle(obj, source):
        raise ValueError("A origem da chapa criaria um ciclo de dependências.")
    for container in containers:
        if container is obj:
            raise ValueError("O contêiner da origem criaria um ciclo de dependências.")
        # A container containing both source and plate already moves both
        # together. Linking to it would create an App::Part dependency cycle.
        owner_parents = reference_containers(obj)
        if container in owner_parents:
            continue
        if would_create_adjustment_cycle(obj, container):
            raise ValueError("O contêiner da origem depende da chapa.")


def _active_containers(obj, containers):
    owner_parents = reference_containers(obj)
    return [container for container in containers if container not in owner_parents]


def _source_placement_in_plate_parent(obj, global_placement):
    """Convert source world frame to the plate's parent-local Placement."""
    owner_parent = obj.getGlobalPlacement().multiply(obj.Placement.inverse())
    return owner_parent.inverse().multiply(global_placement)


class StructuralPlateProxy:
    """Regenerate a simple local BRep from one versioned arbitrary contour."""

    def __init__(self, obj):
        self._updating = True
        self._view_provider = None
        obj.Proxy = self
        try:
            self._setup_properties(obj, refresh_mode=True)
        finally:
            self._updating = False

    def _setup_properties(self, obj, refresh_mode=False):
        created = {}
        for kind, name, group, description in _SCHEMA:
            created[name] = name not in obj.PropertiesList
            if created[name]:
                obj.addProperty(kind, name, group, description)
        if created["SchemaVersion"]:
            obj.SchemaVersion = PLATE_SCHEMA_VERSION
        if created["DisplayName"]:
            obj.DisplayName = obj.Label
        if created["Thickness"]:
            obj.Thickness = 10.0
        if created["Offset"]:
            obj.Offset = 0.0
        if created["ReverseExtrusion"]:
            # Additive, compatible property: older schema-1 documents retain
            # their original positive-Z extrusion when restored.
            obj.ReverseExtrusion = False
        if created["ContourData"]:
            obj.ContourData = ""
        if created["SourceMode"] or refresh_mode:
            _refresh_mode(obj)
        if created["KeepSourceLink"]:
            obj.KeepSourceLink = False
        if created["SourceSubElement"]:
            obj.SourceSubElement = ""
        if created["SourceContainers"]:
            obj.SourceContainers = []
        if created["GenerationStatus"]:
            obj.GenerationStatus = "Pending"
        for name in _READ_ONLY:
            obj.setEditorMode(name, 1)
        obj.setEditorMode("SourceContainers", 2)

    def _ensure_schema(self, obj, refresh_mode=False):
        if not refresh_mode and _REQUIRED_PROPERTIES.issubset(set(obj.PropertiesList)):
            return True
        previous = getattr(self, "_updating", False)
        self._updating = True
        try:
            with _preserve_placement(obj):
                self._setup_properties(obj, refresh_mode=refresh_mode)
            return _REQUIRED_PROPERTIES.issubset(set(obj.PropertiesList))
        finally:
            self._updating = previous

    def execute(self, obj):
        if getattr(self, "_updating", False):
            return
        self._updating = True
        try:
            self._ensure_schema(obj)
            if int(obj.SchemaVersion) != PLATE_SCHEMA_VERSION:
                raise ValueError("Versão do esquema da chapa não suportada.")
            mode = str(obj.SourceMode)
            if mode not in SOURCE_MODES:
                raise ValueError("Modo de origem da chapa inválido.")
            if bool(obj.KeepSourceLink):
                if mode not in _DRAFT_MODES:
                    raise ValueError("Vínculo disponível somente para origem Draft nesta etapa.")
                source = obj.SourceObject
                if source is None:
                    raise ValueError("Origem vinculada removida; última geometria válida preservada.")
                resolved = resolve_plate_source(source, mode)
                _check_source_cycle(obj, source, resolved.containers)
                contour = resolved.contour
                desired_placement = _source_placement_in_plate_parent(obj, resolved.placement)
                active_containers = _active_containers(obj, resolved.containers)
            else:
                contour = PlateContour2D.from_data(str(obj.ContourData))
                desired_placement = _copy_placement(obj.Placement)
                active_containers = []
            thickness = _number(obj.Thickness)
            offset = _number(obj.Offset)
            shape = build_plate_shape(contour, thickness, offset, bool(obj.ReverseExtrusion))
            area = contour.area
            volume = area * thickness
            # All computation and validation precede mutation. A bad linked
            # source leaves the last Shape, contour and placement untouched.
            with _preserve_placement(obj):
                obj.Shape = shape
            obj.Placement = desired_placement
            obj.ContourData = contour.to_data()
            obj.GrossArea = area
            obj.EnvelopeVolume = volume
            if not obj.KeepSourceLink and obj.SourceObject is not None:
                # Switching a linked plate to snapshot freezes the last
                # normalized contour/plane and removes FreeCAD dependencies.
                obj.SourceObject = None
                obj.SourceSubElement = ""
            obj.SourceContainers = active_containers
            obj.GenerationStatus = "Valid"
        except Exception as exc:
            try:
                obj.GenerationStatus = "Erro: " + str(exc)
            except Exception:
                pass
            try:
                App.Console.PrintError("Steel Structures: erro ao atualizar Chapa Estrutural: "
                                       + str(exc) + "\n")
            except Exception:
                pass
        finally:
            self._updating = False

    def onChanged(self, obj, prop):
        if getattr(self, "_updating", False):
            return
        if not self._ensure_schema(obj):
            return
        self._updating = True
        try:
            if prop == "DisplayName":
                if obj.Label != str(obj.DisplayName):
                    obj.Label = str(obj.DisplayName)
            elif prop == "Label":
                if obj.DisplayName != str(obj.Label):
                    obj.DisplayName = str(obj.Label)
            elif prop in _RECOMPUTE_PROPERTIES:
                self._updating = False
                self.execute(obj)
        finally:
            self._updating = False

    def onDocumentRestored(self, obj):
        self._ensure_schema(obj, refresh_mode=True)
        self.execute(obj)

    def __getstate__(self):
        return None

    def __setstate__(self, _state):
        self._updating = False
        self._view_provider = None


def create_plate(document, contour, placement=None, thickness=10.0, offset=0.0,
                 source_mode="InteractivePolygon", source_object=None,
                 keep_source_link=False, display_name=None, reverse_extrusion=False):
    """Create one plate from a normalized contour or a supported Draft object.

    The caller owns the FreeCAD transaction. No source is deleted or hidden here.
    """
    if document is None or not callable(getattr(document, "addObject", None)):
        raise ValueError("Documento FreeCAD válido é obrigatório.")
    if source_mode not in SOURCE_MODES:
        raise ValueError("Modo de origem da chapa inválido.")
    if source_mode in ("Sketch", "Face"):
        raise ValueError("Origem Sketch/Face reservada para incremento futuro.")
    if keep_source_link and (source_mode not in _DRAFT_MODES or source_object is None):
        raise ValueError("Vínculo exige uma origem Draft Rectangle ou Wire.")
    resolved = None
    if source_object is not None:
        if source_mode not in _DRAFT_MODES:
            raise ValueError("Objeto de origem só é aceito em modo Draft.")
        resolved = resolve_plate_source(source_object, source_mode)
        contour, placement = resolved.contour, resolved.placement
    if not isinstance(contour, PlateContour2D):
        contour = PlateContour2D.from_points(contour)
    if placement is None:
        placement = App.Placement()
    build_plate_shape(contour, thickness, offset, reverse_extrusion)
    obj = None
    try:
        obj = document.addObject("Part::FeaturePython", "StructuralPlate")
        proxy = StructuralPlateProxy(obj)
        view_object = getattr(obj, "ViewObject", None)
        if view_object is not None:
            from .plate_view import StructuralPlateViewProvider
            proxy._view_provider = StructuralPlateViewProvider(view_object)
        proxy._updating = True
        try:
            obj.ContourData = contour.to_data()
            obj.Placement = _copy_placement(placement)
            obj.Thickness = thickness
            obj.Offset = offset
            obj.ReverseExtrusion = bool(reverse_extrusion)
            obj.SourceMode = source_mode
            obj.KeepSourceLink = bool(keep_source_link)
            obj.SourceObject = source_object if keep_source_link else None
            obj.SourceContainers = (_active_containers(obj, resolved.containers)
                                    if keep_source_link and resolved else [])
            if display_name is not None:
                obj.DisplayName = str(display_name)
                obj.Label = str(display_name)
        finally:
            proxy._updating = False
        document.recompute()
        if obj.GenerationStatus != "Valid":
            raise ValueError(obj.GenerationStatus)
        return obj
    except Exception:
        if obj is not None:
            document.removeObject(obj.Name)
        raise


__all__ = ["PLATE_SCHEMA_VERSION", "SOURCE_MODES", "StructuralPlateProxy", "create_plate"]
