# SPDX-License-Identifier: LGPL-2.1-or-later
"""Minimal parametric FreeCAD object for a structural grid."""

from __future__ import annotations

from contextlib import contextmanager

import FreeCAD as App
import Part

from .grid_geometry import build_grid_geometry


IDENTIFICATION_OPTIONS = ("Numeric", "Alphabetic", "Custom")
_DATA_PROPERTY_SCHEMA = (
    ("App::PropertyString", "GridType", "Identity", "Tipo estável do objeto."),
    ("App::PropertyInteger", "SchemaVersion", "Identity", "Versão do esquema de propriedades."),
    ("App::PropertyString", "DisplayName", "Identity", "Nome exibido na árvore do documento."),
    ("App::PropertyFloatList", "XSpacings", "Grid", "Espaçamentos consecutivos entre eixos, armazenados em milímetros."),
    ("App::PropertyFloatList", "YSpacings", "Grid", "Espaçamentos consecutivos entre eixos, armazenados em milímetros."),
    ("App::PropertyLength", "XStartExtension", "Grid", "Extensão da linha de eixo."),
    ("App::PropertyLength", "XEndExtension", "Grid", "Extensão da linha de eixo."),
    ("App::PropertyLength", "YStartExtension", "Grid", "Extensão da linha de eixo."),
    ("App::PropertyLength", "YEndExtension", "Grid", "Extensão da linha de eixo."),
    ("App::PropertyEnumeration", "XAxisIdentification", "Identification", "Esquema de identificação dos eixos."),
    ("App::PropertyEnumeration", "YAxisIdentification", "Identification", "Esquema de identificação dos eixos."),
    ("App::PropertyStringList", "XAxisLabels", "Identification", "Identificadores dos eixos."),
    ("App::PropertyStringList", "YAxisLabels", "Identification", "Identificadores dos eixos."),
    ("App::PropertyLength", "OverallLengthX", "Results", "Resultado calculado do grid."),
    ("App::PropertyLength", "OverallLengthY", "Results", "Resultado calculado do grid."),
    ("App::PropertyLength", "DisplayedLengthX", "Results", "Resultado calculado do grid."),
    ("App::PropertyLength", "DisplayedLengthY", "Results", "Resultado calculado do grid."),
    ("App::PropertyInteger", "XAxisCount", "Results", "Resultado calculado do grid."),
    ("App::PropertyInteger", "YAxisCount", "Results", "Resultado calculado do grid."),
    ("App::PropertyInteger", "IntersectionCount", "Results", "Resultado calculado do grid."),
    ("App::PropertyVectorList", "IntersectionPoints", "Results", "Resultado calculado do grid."),
    ("App::PropertyStringList", "IntersectionKeys", "Results", "Resultado calculado do grid."),
)
REQUIRED_GRID_DATA_PROPERTIES = frozenset(item[1] for item in _DATA_PROPERTY_SCHEMA)
_GEOMETRY_PROPERTIES = {
    "XSpacings",
    "YSpacings",
    "XStartExtension",
    "XEndExtension",
    "YStartExtension",
    "YEndExtension",
    "XAxisIdentification",
    "YAxisIdentification",
    "XAxisLabels",
    "YAxisLabels",
}
_READ_ONLY_PROPERTIES = (
    "GridType",
    "SchemaVersion",
    "OverallLengthX",
    "OverallLengthY",
    "DisplayedLengthX",
    "DisplayedLengthY",
    "XAxisCount",
    "YAxisCount",
    "IntersectionCount",
    "IntersectionPoints",
    "IntersectionKeys",
)


def _add_property(obj, property_type: str, name: str, group: str, description: str) -> bool:
    """Add one property if absent and report whether it was created."""
    if name in obj.PropertiesList:
        return False
    obj.addProperty(property_type, name, group, description)
    return True


def _millimetres(value) -> float:
    return float(getattr(value, "Value", value))


def _length_list(values) -> list[float]:
    return [_millimetres(value) for value in values]


def _set_enumeration(obj, name: str, selected: str) -> None:
    setattr(obj, name, list(IDENTIFICATION_OPTIONS))
    setattr(obj, name, selected)


def _restore_enumeration(obj, name: str, default: str) -> None:
    """Restore all options while preserving a valid existing selection."""
    current = str(getattr(obj, name, ""))
    _set_enumeration(obj, name, current if current in IDENTIFICATION_OPTIONS else default)


def _console_error(message: str) -> None:
    try:
        App.Console.PrintError(f"Steel Structures: erro ao atualizar Grid Estrutural: {message}\n")
    except Exception:
        pass


def _placement_signature(placement):
    """Return a numeric signature without retaining mutable FreeCAD objects."""
    try:
        base = placement.Base
        rotation = placement.Rotation
        quaternion = tuple(float(value) for value in rotation.Q)
        return (float(base.x), float(base.y), float(base.z), quaternion)
    except (AttributeError, ReferenceError, RuntimeError, TypeError, ValueError):
        return None


def _copy_placement(placement):
    """Make an independent copy using APIs supported by different FreeCAD builds."""
    copier = getattr(placement, "copy", None)
    if callable(copier):
        try:
            return copier()
        except (AttributeError, ReferenceError, RuntimeError, TypeError):
            pass
    try:
        return App.Placement(placement)
    except (AttributeError, ReferenceError, RuntimeError, TypeError):
        try:
            base = placement.Base
            rotation = placement.Rotation
            return App.Placement(App.Vector(base.x, base.y, base.z), App.Rotation(*rotation.Q))
        except (AttributeError, ReferenceError, RuntimeError, TypeError, ValueError):
            return None


@contextmanager
def _preserve_placement(obj):
    """Defend FreeCAD's persisted Placement against schema/Shape side effects."""
    try:
        original = obj.Placement
    except (AttributeError, ReferenceError, RuntimeError, TypeError):
        yield
        return
    signature = _placement_signature(original)
    saved = _copy_placement(original)
    try:
        yield
    finally:
        if signature is None or saved is None:
            return
        try:
            current_signature = _placement_signature(obj.Placement)
        except (AttributeError, ReferenceError, RuntimeError, TypeError):
            current_signature = None
        if current_signature != signature:
            obj.Placement = saved


def _build_compound(result):
    """Build only valid grid edges; visual intersections belong to Coin."""
    edges = []
    for axis in result.x_axes + result.y_axes:
        if axis.start != axis.end:
            edges.append(Part.makeLine(App.Vector(*axis.start), App.Vector(*axis.end)))
    return Part.makeCompound(edges)


class StructuralGridProxy:
    """FreeCAD adapter around the pure structural-grid geometry contract."""

    def __init__(self, obj):
        self._updating = True
        self._schema_ready = False
        self._view_provider = None
        obj.Proxy = self
        try:
            self._setup_properties(obj, refresh_enumerations=True)
            self._schema_ready = True
        finally:
            self._updating = False

    @staticmethod
    def _object_properties(obj):
        try:
            return set(obj.PropertiesList)
        except (AttributeError, ReferenceError, RuntimeError, TypeError):
            return None

    def _schema_complete(self, obj) -> bool:
        properties = self._object_properties(obj)
        return properties is not None and REQUIRED_GRID_DATA_PROPERTIES.issubset(properties)

    def _setup_properties(self, obj, refresh_enumerations=False) -> None:
        created = {name: _add_property(obj, property_type, name, group, description)
                   for property_type, name, group, description in _DATA_PROPERTY_SCHEMA}

        if created["GridType"]:
            obj.GridType = "StructuralGrid"
        if created["SchemaVersion"]:
            obj.SchemaVersion = 1
        if created["DisplayName"]:
            obj.DisplayName = obj.Label
        if created["XSpacings"]:
            obj.XSpacings = [6000.0, 6000.0]
        if created["YSpacings"]:
            obj.YSpacings = [5000.0, 5000.0]
        for name in ("XStartExtension", "XEndExtension", "YStartExtension", "YEndExtension"):
            if created[name]:
                setattr(obj, name, 1000.0)
        if created["XAxisIdentification"] or refresh_enumerations:
            _restore_enumeration(obj, "XAxisIdentification", "Numeric")
        if created["YAxisIdentification"] or refresh_enumerations:
            _restore_enumeration(obj, "YAxisIdentification", "Alphabetic")
        if created["XAxisLabels"]:
            obj.XAxisLabels = []
        if created["YAxisLabels"]:
            obj.YAxisLabels = []

        properties = self._object_properties(obj) or set()
        for name in _READ_ONLY_PROPERTIES:
            if name in properties:
                obj.setEditorMode(name, 1)

    def _ensure_grid_schema(self, obj, refresh_enumerations=False) -> bool:
        if not refresh_enumerations and self._schema_complete(obj):
            self._schema_ready = True
            return True
        previous = getattr(self, "_updating", False)
        self._updating = True
        try:
            with _preserve_placement(obj):
                self._setup_properties(obj, refresh_enumerations=refresh_enumerations)
            self._schema_ready = self._schema_complete(obj)
            return self._schema_ready
        except (AttributeError, ReferenceError, RuntimeError, TypeError):
            self._schema_ready = False
            return False
        finally:
            self._updating = previous

    def execute(self, obj) -> None:
        if getattr(self, "_updating", False):
            return
        if not self._ensure_grid_schema(obj):
            return
        self._updating = True
        try:
            with _preserve_placement(obj):
                self._execute_local(obj)
        except Exception as exc:
            _console_error(str(exc))
        finally:
            self._updating = False

    def _execute_local(self, obj) -> None:
        """Rebuild results and Shape strictly in the Grid's local coordinates."""
        try:
            x_scheme = str(obj.XAxisIdentification).lower()
            y_scheme = str(obj.YAxisIdentification).lower()
            result = build_grid_geometry(
                _length_list(obj.XSpacings),
                _length_list(obj.YSpacings),
                _millimetres(obj.XStartExtension),
                _millimetres(obj.XEndExtension),
                _millimetres(obj.YStartExtension),
                _millimetres(obj.YEndExtension),
                x_scheme,
                y_scheme,
                list(obj.XAxisLabels) if x_scheme == "custom" else None,
                list(obj.YAxisLabels) if y_scheme == "custom" else None,
            )
            shape = _build_compound(result)
            x_labels = [axis.identifier for axis in result.x_axes]
            y_labels = [axis.identifier for axis in result.y_axes]
            points = [App.Vector(*item.point) for item in result.intersections]
            keys = [f"{x_labels[item.x_index]}/{y_labels[item.y_index]}" for item in result.intersections]
            overall_length_x = result.overall_length_x
            overall_length_y = result.overall_length_y
            displayed_length_x = result.displayed_length_x
            displayed_length_y = result.displayed_length_y
            x_axis_count = len(result.x_axes)
            y_axis_count = len(result.y_axes)
            intersection_count = len(result.intersections)

            obj.OverallLengthX = overall_length_x
            obj.OverallLengthY = overall_length_y
            obj.DisplayedLengthX = displayed_length_x
            obj.DisplayedLengthY = displayed_length_y
            obj.XAxisCount = x_axis_count
            obj.YAxisCount = y_axis_count
            obj.IntersectionCount = intersection_count
            obj.IntersectionPoints = points
            obj.IntersectionKeys = keys
            if x_scheme != "custom":
                obj.XAxisLabels = x_labels
            if y_scheme != "custom":
                obj.YAxisLabels = y_labels
            obj.Shape = shape
        except Exception:
            raise

    def onChanged(self, obj, prop: str) -> None:
        if getattr(self, "_updating", False):
            return
        if not self._ensure_grid_schema(obj):
            return
        self._updating = True
        try:
            if prop == "DisplayName" and "DisplayName" in obj.PropertiesList:
                value = str(obj.DisplayName)
                if obj.Label != value:
                    obj.Label = value
            elif prop == "Label" and "DisplayName" in obj.PropertiesList:
                value = str(obj.Label)
                if obj.DisplayName != value:
                    obj.DisplayName = value
            elif prop in _GEOMETRY_PROPERTIES:
                self._updating = False
                self.execute(obj)
        except Exception as exc:
            _console_error(str(exc))
        finally:
            self._updating = False

    def onDocumentRestored(self, obj):
        with _preserve_placement(obj):
            if not self._ensure_grid_schema(obj, refresh_enumerations=True):
                return
            self.execute(obj)

    def __setstate__(self, _state):
        self._updating = False
        self._schema_ready = False
        self._view_provider = None

    def __getstate__(self):
        # Runtime adapters and their Coin nodes are rebuilt by FreeCAD.
        return None


def create_grid(
    document,
    x_spacings=None,
    y_spacings=None,
    x_start_extension=1000.0,
    x_end_extension=1000.0,
    y_start_extension=1000.0,
    y_end_extension=1000.0,
    x_identification="Numeric",
    y_identification="Alphabetic",
    x_labels=None,
    y_labels=None,
    display_name=None,
):
    """Create and recompute one ``Part::FeaturePython`` structural grid."""
    if document is None or not callable(getattr(document, "addObject", None)):
        raise ValueError("A valid FreeCAD document is required.")
    try:
        obj = document.addObject("Part::FeaturePython", "StructuralGrid")
        proxy = StructuralGridProxy(obj)
        view_object = getattr(obj, "ViewObject", None)
        if view_object is not None:
            from .grid_view import StructuralGridViewProvider
            proxy._view_provider = StructuralGridViewProvider(view_object)
        proxy._updating = True
        try:
            if x_spacings is not None:
                obj.XSpacings = list(x_spacings)
            if y_spacings is not None:
                obj.YSpacings = list(y_spacings)
            obj.XStartExtension = x_start_extension
            obj.XEndExtension = x_end_extension
            obj.YStartExtension = y_start_extension
            obj.YEndExtension = y_end_extension
            _set_enumeration(obj, "XAxisIdentification", x_identification)
            _set_enumeration(obj, "YAxisIdentification", y_identification)
            if x_labels is not None:
                obj.XAxisLabels = list(x_labels)
            if y_labels is not None:
                obj.YAxisLabels = list(y_labels)
            if display_name is not None:
                obj.DisplayName = str(display_name)
                obj.Label = str(display_name)
        finally:
            proxy._updating = False
        recompute = getattr(document, "recompute", None)
        if callable(recompute):
            recompute()
        else:
            proxy.execute(obj)
        return obj
    except Exception:
        partial = locals().get("obj")
        name = getattr(partial, "Name", None)
        remove = getattr(document, "removeObject", None)
        if name is not None and callable(remove):
            try:
                remove(name)
            except Exception:
                pass
        raise


__all__ = ["StructuralGridProxy", "create_grid"]
