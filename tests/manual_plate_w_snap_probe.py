"""Interactive FreeCAD 1.1.4 probe for point-defined planes on a W profile.

Run from the repository root with FreeCAD.exe tests/manual_plate_w_snap_probe.py.
The generated member has a top flange at z=150 and the Work Plane is z=0.
In Auto, snap three noncollinear points of the flange. Compare the same snaps
with the cursor inside and outside the profile. The Report View logs 3D points.
Close the task panel when finished.
"""

import sys
from pathlib import Path

import FreeCAD as App
import FreeCADGui as Gui
import Part

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "freecad"))

from SteelStructures.interactive.plate_controller import PlateController
from SteelStructures.interactive.plate_task_panel import PlateTaskPanel
from SteelStructures.plate_planes import screen_coordinates


class DiagnosticView:
    def __init__(self, native):
        self.native = native
        self.controller = None

    def __getattr__(self, name):
        return getattr(self.native, name)

    def addEventCallback(self, kind, handler):
        if kind != "SoMouseButtonEvent":
            return self.native.addEventCallback(kind, handler)

        def report(event):
            if event.get("State") != "DOWN" or event.get("Button") != "BUTTON1":
                return handler(event)
            screen = screen_coordinates(event.get("Position"))
            before = self.controller.point_count
            result = handler(event)
            App.Console.PrintMessage(
                "Chapa W: cursor=%s; snapInfo=%s; snapType=%s; "
                "estado=%s; ponto3D=%s; aceito=%s; pendentes=%s\n" %
                (screen, self.controller._last_snap_info,
                 getattr(Gui.Snapper, "cursorMode", None),
                 self.controller.plane_state,
                 self.controller._last_effective_point,
                 self.controller.point_count > before,
                 self.controller._pending_world_points))
            return result

        return self.native.addEventCallback(kind, report)


Gui.activateWorkbench("DraftWorkbench")
doc = App.newDocument("PlateWPointPlaneProbe")
section = [(-50, -30), (50, -30), (50, -24), (5, -24),
           (5, 24), (50, 24), (50, 30), (-50, 30),
           (-50, 24), (-5, 24), (-5, -24), (-50, -24)]
wire = Part.makePolygon([App.Vector(0, y, z) for y, z in section + section[:1]])
member = doc.addObject("Part::Feature", "WProfile")
member.Shape = Part.Face(wire).extrude(App.Vector(100, 0, 0))
member.Placement.Base = App.Vector(0, 0, 120)
doc.recompute()
native = Gui.activeDocument().activeView()
native.viewTop()
native.fitAll()
view = DiagnosticView(native)
controller = PlateController(doc, view=view, placement=App.Placement())
view.controller = controller
panel = PlateTaskPanel(controller, lambda _panel, _accepted: Gui.Control.closeDialog())
Gui.Control.showDialog(panel)
App.Console.PrintMessage(
    "Chapa W: Work Plane z=0; flange z=150. "
    "Auto: snap em tres pontos nao colineares da flange. "
    "P1/P2 ficam pendentes; P3 define o plano.\n")
