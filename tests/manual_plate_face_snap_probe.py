"""Manual FreeCAD GUI probe for 3D points in Auto mode.

Run with FreeCAD.exe tests/manual_plate_face_snap_probe.py from the repository
root. Move over the TOP FACE of the generated box and click once in the plate
Polygon tool. Report View prints native pick, Draft snap, effective 3D point
and plane state for every click.
The captured Work Plane is intentionally z=0 while the top face is z=128.
Cancel the tool when finished.
"""

import sys
import time
from pathlib import Path

import FreeCAD as App
import FreeCADGui as Gui
import Part
from PySide import QtWidgets


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "freecad"))

from SteelStructures.interactive.plate_controller import PlateController
from SteelStructures.interactive.plate_task_panel import PlateTaskPanel
from SteelStructures.plate_planes import (preselection_pick, screen_coordinates,
                                          view_pick)


def preselection_state():
    item = Gui.Selection.getPreselection()
    result = {"type": type(item).__name__}
    for name in ("DocumentName", "ObjectName", "Object", "SubElementNames",
                 "PickedPoints"):
        try:
            result[name] = str(getattr(item, name))
        except (AttributeError, ReferenceError, RuntimeError) as exc:
            result[name] = "indisponível: " + str(exc)
    info, point = preselection_pick(item, doc)
    result["parsed"] = (str(info), str(point))
    if point is not None:
        try:
            result["point_on_screen"] = tuple(native.getPointOnScreen(point))
        except (AttributeError, RuntimeError):
            result["point_on_screen"] = "indisponível"
    return result


class ProbeView:
    def __init__(self, native):
        self.native = native
        self.controller = None
        self._last_move_log = 0.0

    def __getattr__(self, name):
        return getattr(self.native, name)

    def addEventCallback(self, kind, handler):
        if kind not in ("SoLocation2Event", "SoMouseButtonEvent"):
            return self.native.addEventCallback(kind, handler)

        def report_event(event):
            click = kind == "SoMouseButtonEvent"
            if click and (event.get("State") != "DOWN"
                          or event.get("Button") != "BUTTON1"):
                return handler(event)
            if not click and time.monotonic() - self._last_move_log < .2:
                return handler(event)
            if not click:
                self._last_move_log = time.monotonic()
            position = event.get("Position")
            screen = screen_coordinates(position)
            before_preselection = preselection_state()
            picked, point = view_pick(self.native, position, doc)
            try:
                all_hits = self.native.getObjectsInfo(screen) if screen else None
            except (AttributeError, ReferenceError, RuntimeError):
                all_hits = None
            before = self.controller.point_count
            result = handler(event)
            snapper = Gui.Snapper
            App.Console.PrintMessage(
                "Chapa %s: callback=%s; preselection_before=%s; "
                "preselection_after=%s; getObjectInfo=%s; pick_point=%s; "
                "getObjectsInfo=%s; "
                "snap=%s; snapInfo=%s; snapType=%s; accepted=%s; "
                "plane=%s; state=%s; preselection=%s; pick=%s; "
                "effective=%s; pending=%s\n" %
                ("click" if click else "move", position,
                 before_preselection, preselection_state(), picked, point, all_hits,
                 getattr(snapper, "spoint", None), self.controller._last_snap_info,
                 getattr(snapper, "cursorMode", None),
                 self.controller.point_count > before, self.controller._plane_kind,
                 self.controller.plane_state,
                 self.controller._last_preselection_info,
                 self.controller._last_pick_info,
                 self.controller._last_effective_point,
                 self.controller._pending_world_points))
            return result

        return self.native.addEventCallback(kind, report_event)


Gui.activateWorkbench("DraftWorkbench")
doc = App.newDocument("PlateFaceSnapProbe")
box = doc.addObject("Part::Feature", "SnapFaceBox")
box.Shape = Part.makeBox(100, 80, 8)
box.Placement.Base = App.Vector(0, 0, 120)
doc.recompute()
native = Gui.activeDocument().activeView()
native.viewAxonometric()
native.fitAll()
view = ProbeView(native)
controller = PlateController(doc, view=view, placement=App.Placement())
view.controller = controller
panel = PlateTaskPanel(controller, lambda _panel, _accepted: Gui.Control.closeDialog())
Gui.Control.showDialog(panel)
viewer = next((widget for widget in Gui.getMainWindow().findChildren(
    QtWidgets.QGraphicsView) if widget.isVisible() and widget.width() > 500), None)
App.Console.PrintMessage(
    "Chapa probe: controller=%s, view=%s, viewport=%s, DPR=%s\n" %
    (sys.modules[PlateController.__module__].__file__, native,
     (viewer.viewport().width(), viewer.viewport().height()) if viewer else None,
     viewer.devicePixelRatioF() if viewer else None))
App.Console.PrintMessage(
    "Chapa: clique no interior da face superior (z=128), longe de arestas; "
    "o Report View registra picks aceitos e rejeitados. Cancele ao terminar.\n")
