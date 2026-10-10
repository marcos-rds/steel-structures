# SPDX-License-Identifier: LGPL-2.1-or-later
"""Creation session for a plate whose only geometry is a planar local contour."""

from __future__ import annotations

import math

import FreeCAD as App
import FreeCADGui as Gui

from ..plate_geometry import PlateContour2D
from ..plate_planes import (placement_from_face, placement_from_points,
                            preselection_pick, view_pick)
from ..plate_sources import is_draft_rectangle, is_draft_wire, resolve_plate_source
from .plate_preview import PlatePreview
from .point_input import PointCandidate, PointInputPlane


SOURCE_MODES = ("DraftRectangle", "DraftWire")
INTERACTIVE_MODES = ("InteractivePolygon", "InteractiveRectangle")
PLANE_MODES = ("Auto", "WorkPlane")
NO_PLANE = "NO_PLANE"
FIRST_DIRECTION = "FIRST_DIRECTION"
PLANE_DEFINED = "PLANE_DEFINED"


def _rectangle_vertices(first, opposite):
    x1, y1 = first
    x2, y2 = opposite
    return ((x1, y1), (x2, y1), (x2, y2), (x1, y2))


def _three_point_rectangle(first, second, third, placement):
    """Orthogonal rectangle from the first edge and P3's signed width."""
    inverse = placement.inverse()
    p1, p2, p3 = (inverse.multVec(App.Vector(point))
                  for point in (first, second, third))
    return _rectangle_vertices((p1.x, p1.y), (p2.x, p3.y))


def selected_plate_source(selection, document):
    """Return a single whole Draft object, or no source for point creation."""
    items = tuple(selection or ())
    if len(items) != 1:
        return None, None
    source = getattr(items[0], "Object", None)
    if source is None or getattr(source, "Document", None) is not document:
        return None, None
    if is_draft_rectangle(source):
        return source, "DraftRectangle"
    if is_draft_wire(source):
        return source, "DraftWire"
    return None, None


def working_plane_placement():
    """Capture Draft's current plane once; +Z is its normal."""
    import WorkingPlane

    plane = WorkingPlane.get_working_plane()
    origin = App.Vector(plane.position)
    u = App.Vector(plane.u)
    v = App.Vector(plane.v)
    normal = App.Vector(plane.axis)
    if min(u.Length, v.Length, normal.Length) <= 1e-12:
        raise ValueError("Plano de trabalho inválido.")
    rotation = App.Rotation(u, v, normal, "ZXY")
    return App.Placement(origin, rotation)


class PlateController:
    """Own transient preview, native snap callbacks and one creation transaction."""

    def __init__(self, document, source=None, source_mode=None, view=None,
                 factory=None, placement=None, plane_mode="Auto", plane_face=None):
        from ..plate import create_plate

        self.document = document
        self.source = source
        self.mode = source_mode or "InteractivePolygon"
        self._factory = factory or create_plate
        self._view = view or Gui.activeDocument().activeView()
        self._work_plane_placement = (
            placement if placement is not None else
            (working_plane_placement() if source is None else None))
        if plane_mode not in PLANE_MODES:
            raise ValueError("Modo de plano da chapa inválido.")
        self.plane_mode = plane_mode
        self._selected_plane_face = plane_face if source is None else None
        self._selected_face_placement = (
            placement_from_face(plane_face) if source is None and plane_face is not None
            and plane_mode == "Auto"
            else None)
        self._last_snap_info = None
        self._last_pick_info = None
        self._last_preselection_info = None
        self._last_effective_point = None
        self.placement = None
        self.plane_state = NO_PLANE
        self._plane_kind = "Pending"
        self._pending_world_points = []
        if source is None:
            self._reset_interactive_plane()
        self.contour = None
        self.points = []
        self._callbacks = []
        self._capturing = False
        self.closed = False
        self._teardown_done = False
        self.on_change = None
        self.on_error = None
        self.on_cancel = None
        self.on_candidate = None
        self.reverse_extrusion = False
        self.candidate = None
        # The widget owns editing state, including incomplete text.
        self.numeric_editing = None
        self.preview = PlatePreview(self._view)
        if source is not None:
            self._resolve_source()

    def _notify(self):
        self.candidate = None
        if self.on_change is not None:
            self.on_change()

    def _error(self, message):
        if self.on_error is not None:
            self.on_error(str(message))
        else:
            App.Console.PrintWarning("Steel Structures: " + str(message) + "\n")

    def _resolve_source(self):
        resolved = resolve_plate_source(self.source, self.mode)
        self.contour = resolved.contour
        self.placement = resolved.placement
        self.points.clear()

    @property
    def point_count(self):
        return (len(self.points) if self.plane_state == PLANE_DEFINED
                else len(self._pending_world_points))

    @property
    def last_point(self):
        if not self.point_count:
            return None
        point = self._world_points()[-1]
        return (point.x, point.y, point.z)

    @property
    def input_plane(self):
        if self.plane_state != PLANE_DEFINED:
            return None
        origin = self.placement.multVec(App.Vector(0, 0, 0))
        axes = [self.placement.Rotation.multVec(App.Vector(*axis))
                for axis in ((1, 0, 0), (0, 1, 0), (0, 0, 1))]
        return PointInputPlane((origin.x, origin.y, origin.z),
                               *((axis.x, axis.y, axis.z) for axis in axes))

    def set_candidate(self, candidate):
        """Validate preview input without discovering a plane or adding points."""
        if self.closed or self.source is not None or self.contour is not None:
            return
        if candidate is not None:
            if not isinstance(candidate, PointCandidate):
                raise ValueError("Candidato de ponto inválido.")
            if self.plane_state == PLANE_DEFINED:
                self._local_point(candidate.world)
        self.candidate = candidate
        if self.on_candidate is not None:
            self.on_candidate(candidate)

    def clear_points(self):
        """Reset just the trace, preserving capture ownership and plane policy."""
        if self.closed or self.source is not None:
            return
        self.contour = None
        self.points.clear()
        self._reset_interactive_plane()
        self.preview.clear()
        self._notify()

    def undo_point(self):
        """Replay the remaining confirmed points through the approved plane algorithm."""
        if self.closed or self.source is not None or self.mode != "InteractivePolygon":
            return
        remaining = self._world_points()[:-1]
        self.clear_points()
        for point in remaining:
            self.add_point(point, close_on_first=False)

    def _reset_interactive_plane(self):
        self._pending_world_points.clear()
        selected = self.plane_mode == "Auto" and self._selected_face_placement is not None
        self.placement = (self._selected_face_placement if selected
                          else self._work_plane_placement if self.plane_mode == "WorkPlane"
                          else None)
        self.plane_state = PLANE_DEFINED if self.placement is not None else NO_PLANE
        self._plane_kind = ("Face" if selected else
                            "WorkPlane" if self.plane_state == PLANE_DEFINED else "Pending")

    def set_plane_mode(self, mode):
        if self.source is not None or mode not in PLANE_MODES:
            raise ValueError("Modo de plano indisponível.")
        if self.point_count or self.contour is not None:
            raise ValueError("Defina o modo de plano antes do primeiro ponto.")
        if mode == self.plane_mode:
            return
        if mode == "Auto" and self._selected_plane_face is not None:
            self._selected_face_placement = placement_from_face(self._selected_plane_face)
        self.plane_mode = mode
        self._reset_interactive_plane()
        self.preview.clear()
        self._notify()

    def set_mode(self, mode):
        if mode not in INTERACTIVE_MODES or self.source is not None:
            raise ValueError("Modo de criação indisponível.")
        if mode == self.mode:
            return
        self.mode = mode
        self.points.clear()
        self.contour = None
        self._reset_interactive_plane()
        self.preview.clear()
        self._notify()

    def _local_point(self, point):
        local = self.placement.inverse().multVec(App.Vector(point))
        # Once defined, the plate Placement is the sole plane test.
        if abs(local.z) > 1e-5:
            if self._plane_kind == "WorkPlane":
                raise ValueError("O ponto está fora do plano de trabalho da chapa.")
            raise ValueError("O ponto está fora do plano da chapa.")
        return (float(local.x), float(local.y))

    def _world_points(self):
        if self.plane_state != PLANE_DEFINED:
            return [App.Vector(point) for point in self._pending_world_points]
        return [self.placement.multVec(App.Vector(x, y, 0)) for x, y in self.points]

    def _close_tolerance(self, position):
        # Estimate ten screen pixels in model units at the current view depth.
        try:
            x, y = position[0], position[1]
            a = self._view.getPoint(int(x), int(y))
            b = self._view.getPoint(int(x) + 10, int(y))
            return max(1e-5, App.Vector(a).sub(App.Vector(b)).Length)
        except (AttributeError, TypeError, RuntimeError):
            return 1e-3

    def add_point(self, world_point, *, screen_position=None, close_on_first=True):
        if self.source is not None or self.closed:
            raise RuntimeError("Coleta de pontos indisponível.")
        raw = App.Vector(world_point)
        checked = PointCandidate((raw.x, raw.y, raw.z))
        point = App.Vector(*checked.world)
        if self.plane_state != PLANE_DEFINED:
            pending = self._pending_world_points
            if pending and point.sub(pending[-1]).Length <= 1e-7:
                raise ValueError("Vértices consecutivos devem ser diferentes.")
            if not pending:
                pending.append(point)
                self._notify()
                return
            if len(pending) == 1:
                pending.append(point)
                self.plane_state = FIRST_DIRECTION
                self._notify()
                return
            frame = placement_from_points(pending[0], pending[1], point)
            if frame is None:
                if self.mode == "InteractiveRectangle":
                    raise ValueError("O terceiro ponto deve definir a largura do retângulo.")
                pending.append(point)
                self._notify()
                return
            if self.mode == "InteractiveRectangle":
                corners = _three_point_rectangle(pending[0], pending[1], point, frame)
                contour = PlateContour2D.from_points(corners, closed=True)
                local_points = [corners[0], corners[1], corners[2]]
            else:
                local_points = []
                inverse = frame.inverse()
                for world in (*pending, point):
                    local = inverse.multVec(world)
                    if abs(local.z) > 1e-5:
                        raise ValueError("O ponto está fora do plano da chapa.")
                    local_points.append((float(local.x), float(local.y)))
                contour = None
            self.placement = frame
            self.points = local_points
            pending.clear()
            self.plane_state = PLANE_DEFINED
            self._plane_kind = "Points"
            self.contour = contour
            if contour is not None:
                self.stop_capture()
            self._notify()
            return

        xy = self._local_point(point)
        if self.mode == "InteractivePolygon" and len(self.points) >= 3:
            first = self.points[0]
            distance = ((xy[0] - first[0]) ** 2 + (xy[1] - first[1]) ** 2) ** 0.5
            tolerance = (self._close_tolerance(screen_position)
                         if screen_position is not None else 1e-3)
            if not close_on_first and distance <= 1e-7:
                raise ValueError("Use Fechar contorno para concluir o polígono.")
            if close_on_first and distance <= tolerance:
                self.close_outline()
                return
        if self.points:
            previous = self.points[-1]
            if abs(xy[0] - previous[0]) <= 1e-7 and abs(xy[1] - previous[1]) <= 1e-7:
                raise ValueError("Vértices consecutivos devem ser diferentes.")
        if self.mode == "InteractiveRectangle":
            if not self.points:
                self.points.append(xy)
            else:
                self.contour = PlateContour2D.from_points(
                    _rectangle_vertices(self.points[0], xy), closed=True)
                self.points = [self.points[0], xy]
                self.stop_capture()
        else:
            self.points.append(xy)
        self._notify()

    def close_outline(self):
        if self.mode != "InteractivePolygon" or self.source is not None:
            raise ValueError("Somente o polígono interativo pode ser fechado.")
        if self.plane_state != PLANE_DEFINED or len(self.points) < 3:
            raise ValueError("Defina pelo menos três vértices antes de fechar o contorno.")
        # Validation includes the final edge. An invalid closing edge leaves
        # the point sequence open so the user can continue or cancel.
        candidate = PlateContour2D.from_points(tuple(self.points), closed=True)
        self.contour = candidate
        self.stop_capture()
        self._notify()

    def update_preview(self, thickness, offset, cursor=None):
        if self.closed:
            return
        if cursor is None and self.candidate is not None:
            cursor = App.Vector(*self.candidate.world)
        if cursor is not None and self.plane_state == PLANE_DEFINED:
            self._local_point(cursor)
        if self.contour is not None:
            self.preview.solid(self.contour, self.placement, thickness, offset,
                               reverse_extrusion=self.reverse_extrusion)
        elif (self.mode == "InteractiveRectangle" and self.plane_state != PLANE_DEFINED
              and self.point_count == 2 and cursor is not None):
            first, second = self._pending_world_points
            frame = placement_from_points(first, second, cursor)
            if frame is None:
                self.preview.outline(self._world_points(), cursor)
            else:
                corners = _three_point_rectangle(first, second, cursor, frame)
                closed = corners + (corners[0],)
                self.preview.outline([frame.multVec(App.Vector(x, y, 0))
                                      for x, y in closed])
        elif (self.mode == "InteractiveRectangle" and self.plane_state == PLANE_DEFINED
              and len(self.points) == 1 and cursor is not None):
            corners = _rectangle_vertices(self.points[0], self._local_point(cursor))
            closed = corners + (corners[0],)
            self.preview.outline([self.placement.multVec(App.Vector(x, y, 0))
                                  for x, y in closed])
        elif self.point_count:
            self.preview.outline(self._world_points(), cursor)
        else:
            self.preview.clear()

    def _snap_point(self, event):
        snapper = getattr(Gui, "Snapper", None)
        if snapper is None:
            raise ValueError("Ferramenta de snap Draft indisponível.")
        previous = self._world_points()[-1] if self.point_count else None
        if self.plane_mode == "Auto" and hasattr(snapper, "toWP"):
            # Draft projects object snaps to the active Work Plane inside
            # snapToEndpoints/snapToMidpoint/etc. Bypass only that projection
            # during this synchronous call; always restore the shared Snapper.
            previous_override = vars(snapper).get("toWP")
            had_override = "toWP" in vars(snapper)
            try:
                snapper.toWP = lambda point: point
                point = snapper.snap(event["Position"], lastpoint=previous, active=True)
            finally:
                if had_override:
                    snapper.toWP = previous_override
                else:
                    del snapper.toWP
        else:
            point = snapper.snap(event["Position"], lastpoint=previous, active=True)
        self._last_snap_info = getattr(snapper, "snapInfo", None)
        return None if point is None else App.Vector(point)

    def _current_preselection(self):
        selection = getattr(Gui, "Selection", None)
        getter = getattr(selection, "getPreselection", None)
        if getter is None:
            return None, None
        try:
            return preselection_pick(getter(), self.document)
        except (AttributeError, ReferenceError, RuntimeError):
            return None, None

    def _event_point(self, snapped, position):
        """Use snap coordinates; replace only a passive Work Plane projection.

        Native pick/preselection is a source of a 3D *point*, never a plane.
        An active Draft snap retains its exact returned coordinates.
        """
        self._last_effective_point = snapped
        self._last_pick_info = None
        self._last_preselection_info = None
        if self.plane_mode == "WorkPlane":
            return snapped
        snapper = getattr(Gui, "Snapper", None)
        if getattr(snapper, "cursorMode", None) not in (None, "passive"):
            return snapped
        pre_info, pre_point = self._current_preselection()
        pick_info, picked = view_pick(self._view, position, self.document)
        self._last_preselection_info = pre_info
        self._last_pick_info = pick_info
        point = picked if picked is not None else pre_point
        if point is None and self.plane_state == PLANE_DEFINED:
            point = self._point_on_defined_plane(position)
        if point is None:
            raise ValueError("Não foi possível obter um ponto 3D real neste local.")
        self._last_effective_point = point
        return point

    def _point_on_defined_plane(self, position):
        """Empty-space fallback using Draft's ray construction, after P3 only."""
        from draftgeoutils.geometry import project_point_on_plane
        from ..plate_planes import screen_coordinates

        pixels = screen_coordinates(position)
        if pixels is None or self.placement is None:
            return None
        try:
            point = self._view.getPoint(*pixels)
            if self._view.getCameraType() == "Perspective":
                camera = self._view.getCameraNode().getField("position").getValue()
                direction = point.sub(App.Vector(*camera))
            else:
                direction = self._view.getViewDirection()
            if direction.Length <= 1e-12:
                return None
            normal = self.placement.Rotation.multVec(App.Vector(0, 0, 1))
            candidate = project_point_on_plane(point, self.placement.Base, normal,
                                               direction, force_projection=False)
            if candidate is None or not all(math.isfinite(v) for v in
                                             (candidate.x, candidate.y, candidate.z)):
                return None
            # Perspective intersections behind the eye are not visible rays.
            if self._view.getCameraType() == "Perspective" and candidate.sub(
                    App.Vector(*camera)).dot(direction) <= 0:
                return None
            return candidate
        except (AttributeError, ReferenceError, RuntimeError, TypeError, ValueError):
            return None

    def start_capture(self, thickness, offset):
        if (self.closed or self.source is not None or self.contour is not None
                or self._capturing):
            return
        self._capturing = True
        view = self._view

        def move(event):
            if (self.closed or not self._capturing
                    or (self.numeric_editing is not None and self.numeric_editing())):
                return
            try:
                point = self._snap_point(event)
                if self.closed:
                    return
                if point is not None:
                    point = self._event_point(point, event.get("Position"))
                    self.set_candidate(PointCandidate((point.x, point.y, point.z)))
                    self.update_preview(thickness(), offset())
                else:
                    self.set_candidate(None)
                    self.update_preview(thickness(), offset())
            except (ValueError, KeyError, RuntimeError):
                if not self.closed:
                    self.set_candidate(None)
                    self.update_preview(thickness(), offset())

        def click(event):
            if (self.closed or not self._capturing or event.get("State") != "DOWN"
                    or event.get("Button") != "BUTTON1"
                    or (self.numeric_editing is not None and self.numeric_editing())):
                return
            try:
                point = self._snap_point(event)
                if self.closed:
                    return
                if point is not None:
                    point = self._event_point(point, event.get("Position"))
                    self.set_candidate(PointCandidate((point.x, point.y, point.z)))
                    self.add_point(self.candidate.world,
                                   screen_position=event.get("Position"))
                    if not self.closed:
                        self.update_preview(thickness(), offset())
            except (ValueError, KeyError, RuntimeError) as exc:
                if not self.closed:
                    self._error(exc)

        def key(event):
            if (not self.closed and event.get("Key") == "ESCAPE"
                    and event.get("State") == "DOWN"):
                # A native view callback must return before the task dialog
                # and its scene graph can be destroyed. The panel schedules
                # the actual teardown on the next Qt event-loop turn.
                self.closed = True
                if self.on_cancel is not None:
                    self.on_cancel()
                else:
                    self.cancel()

        try:
            snapper = getattr(Gui, "Snapper", None)
            if snapper is not None:
                snapper.show()
            for kind, handler in (("SoLocation2Event", move),
                                  ("SoMouseButtonEvent", click),
                                  ("SoKeyboardEvent", key)):
                self._callbacks.append((kind, view.addEventCallback(kind, handler)))
        except Exception:
            self.stop_capture()
            raise

    def stop_capture(self):
        if not self._capturing:
            return
        self._capturing = False
        callbacks, self._callbacks = self._callbacks, []
        for kind, token in callbacks:
            try:
                self._view.removeEventCallback(kind, token)
            except (AttributeError, RuntimeError):
                pass
        snapper = getattr(Gui, "Snapper", None)
        if snapper is not None and hasattr(snapper, "off"):
            snapper.off()

    def create(self, thickness, offset, keep_source_link=False, reverse_extrusion=False):
        if self.source is not None:
            # A Draft object may have changed while its task panel was open.
            self._resolve_source()
        if self.contour is None:
            raise ValueError("Feche o contorno antes de criar a chapa.")
        if float(thickness) <= 0:
            raise ValueError("A espessura deve ser positiva.")
        self.document.openTransaction("Criar Chapa Estrutural")
        old_visibility = None
        try:
            plate = self._factory(
                self.document, self.contour, placement=self.placement,
                thickness=float(thickness), offset=float(offset),
                source_mode=self.mode, source_object=self.source,
                keep_source_link=bool(keep_source_link and self.source is not None),
                reverse_extrusion=bool(reverse_extrusion))
            if self.source is not None:
                old_visibility = bool(self.source.ViewObject.Visibility)
                self.source.ViewObject.Visibility = False
            self.document.commitTransaction()
        except Exception:
            self.document.abortTransaction()
            if self.source is not None and old_visibility is not None:
                try:
                    self.source.ViewObject.Visibility = old_visibility
                except (AttributeError, ReferenceError, RuntimeError):
                    pass
            raise
        self.cancel()
        try:
            Gui.Selection.clearSelection()
            Gui.Selection.addSelection(plate)
        except (AttributeError, RuntimeError):
            pass
        return plate

    def cancel(self):
        if self._teardown_done:
            return
        self.closed = True
        self.candidate = None
        try:
            self.stop_capture()
        finally:
            self.preview.remove()
            self._teardown_done = True
