"""FreeCAD GUI smoke probe for point-defined planes and deterministic teardown.

Run with FreeCAD.exe tests/manual_plate_gui_lifecycle.py. The JSON result in
the system temporary directory reports native GUI checks. Physical mouse snap
and preview behavior still require manual observation.
"""

import json
import sys
import tempfile
import traceback
from pathlib import Path

import FreeCAD as App
import FreeCADGui as Gui
import Part
from PySide import QtCore, QtWidgets
from pivy import coin


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "freecad"))
RESULT_PATH = Path(tempfile.gettempdir()) / "steelstructures_plate_gui_lifecycle_070a.json"


class RecordingView:
    def __init__(self, native, preview_scene):
        self.native = native
        self.preview_scene = preview_scene
        self.handlers = {}

    def __getattr__(self, name):
        return getattr(self.native, name)

    def getSceneGraph(self):
        return self.preview_scene

    def addEventCallback(self, kind, handler):
        self.handlers[kind] = handler
        return self.native.addEventCallback(kind, handler)


def run():
    from SteelStructures.interactive.plate_controller import (
        FIRST_DIRECTION, NO_PLANE, PLANE_DEFINED, PlateController)
    from SteelStructures.interactive.plate_task_panel import PlateTaskPanel
    from SteelStructures.plate_planes import PlateFaceReference

    doc = None
    outcome = {"ok": False, "checks": []}
    try:
        Gui.activateWorkbench("DraftWorkbench")
        doc = App.newDocument("PlatePointPlaneGuiProbe")
        native = Gui.activeDocument().activeView()
        scene = native.getSceneGraph()
        for mode, count, escape in (
            ("InteractivePolygon", 0, False),
            ("InteractivePolygon", 1, False),
            ("InteractivePolygon", 2, True),
            ("InteractivePolygon", 3, True),
            ("InteractiveRectangle", 1, False),
            ("InteractiveRectangle", 2, True),
            ("InteractiveRectangle", 0, False),
        ):
            root = coin.SoSeparator()
            scene.addChild(root)
            view = RecordingView(native, root)
            controller = PlateController(doc, view=view, placement=App.Placement())
            if mode == "InteractiveRectangle":
                controller.set_mode(mode)
            panel = PlateTaskPanel(controller, lambda _panel, _accepted:
                                   Gui.Control.closeDialog())
            Gui.Control.showDialog(panel)
            QtWidgets.QApplication.processEvents()
            assert controller._capturing
            points = (App.Vector(0, 0, 128), App.Vector(20, 0, 128),
                      App.Vector(25, 10, 128))
            for point in points[:count]:
                controller.add_point(point)
            expected = (NO_PLANE if count == 0 or count == 1 else
                        FIRST_DIRECTION if count == 2 else PLANE_DEFINED)
            assert controller.plane_state == expected
            controller.update_preview(8, 0, App.Vector(30, 10, 128))
            if escape:
                view.handlers["SoKeyboardEvent"]({"Key": "ESCAPE", "State": "DOWN"})
                assert controller.closed
                QtWidgets.QApplication.processEvents()
            else:
                panel.reject()
                QtWidgets.QApplication.processEvents()
            assert panel._closed and controller._teardown_done
            assert root.getNumChildren() == 0
            assert not Gui.Control.activeDialog()
            scene.removeChild(root)
            outcome["checks"].append({"mode": mode, "points": count,
                                      "escape": escape, "state": expected})

        for name, points in (
            ("XY", ((0, 0, 0), (20, 0, 0), (20, 10, 0))),
            ("XZ", ((0, 0, 0), (0, 0, 20), (10, 0, 20))),
            ("YZ", ((0, 0, 0), (0, 0, 20), (0, 10, 20))),
            ("inclined", ((2, 3, 4), (12, 3, 7), (15, 9, 8))),
        ):
            controller = PlateController(doc, view=native, placement=App.Placement())
            for point in points:
                controller.add_point(App.Vector(*point))
            assert controller.plane_state == PLANE_DEFINED
            controller.close_outline()
            plate = controller.create(6, 2)
            doc.recompute()
            assert plate.Shape.isValid()
            assert abs(plate.Shape.Volume - plate.GrossArea.Value * 6) < 1e-5
            outcome["checks"].append({"plane": name, "volume": plate.Shape.Volume})
        # The graphical round-trip also exercises the real ViewProvider,
        # which is absent from standalone FreeCAD geometry tests.
        saved_name = plate.Name
        saved_contour = plate.ContourData
        saved_vertices = sorted(tuple(vertex.Point) for vertex in plate.Shape.Vertexes)
        persistence_path = Path(__file__).resolve().parents[1] / "test-results" / (
            "plate_gui_persistence_" + "".join(App.Version()[:3]) + ".FCStd")
        persistence_path.parent.mkdir(exist_ok=True)
        try:
            doc.saveAs(str(persistence_path))
            App.closeDocument(doc.Name)
            doc = App.openDocument(str(persistence_path))
            doc.recompute()
            restored = doc.getObject(saved_name)
            assert restored.Proxy.__class__.__name__ == "StructuralPlateProxy"
            assert restored.ViewObject.Proxy.__class__.__name__ == "StructuralPlateViewProvider"
            assert restored.ContourData == saved_contour
            actual = sorted(tuple(vertex.Point) for vertex in restored.Shape.Vertexes)
            assert len(actual) == len(saved_vertices)
            assert all(App.Vector(a).sub(App.Vector(b)).Length < 1e-6
                       for a, b in zip(actual, saved_vertices))
            outcome["checks"].append({"gui_proxy_save_reopen": True})
            native = Gui.activeDocument().activeView()
        finally:
            if persistence_path.exists():
                persistence_path.unlink()
        box = doc.addObject("Part::Feature", "SnapProbeBox")
        box.Shape = Part.makeBox(40, 30, 8)
        box.Placement.Base = App.Vector(0, 0, 120)
        doc.recompute()
        top = next("Face%d" % index for index, face in enumerate(box.Shape.Faces, 1)
                   if face.normalAt(0, 0).z > .9)
        face_controller = PlateController(
            doc, view=native, placement=App.Placement(),
            plane_face=PlateFaceReference(box, top))
        face_controller.set_mode("InteractiveRectangle")
        face_controller.add_point(App.Vector(2, 3, 128))
        face_controller.add_point(App.Vector(20, 15, 128))
        assert face_controller.plane_state == PLANE_DEFINED
        assert len(face_controller.contour.vertices) == 4
        outcome["checks"].append({"selected_face_rectangle_points": 2,
                                  "plane": face_controller._plane_kind})
        face_controller.cancel()
        work_controller = PlateController(
            doc, view=native, placement=App.Placement(), plane_mode="WorkPlane")
        work_controller.set_mode("InteractiveRectangle")
        work_controller.add_point(App.Vector(2, 3, 0))
        work_controller.add_point(App.Vector(20, 15, 0))
        assert len(work_controller.contour.vertices) == 4
        outcome["checks"].append({"work_plane_rectangle_points": 2})
        work_controller.cancel()
        native.viewAxonometric()
        native.fitAll()
        QtWidgets.QApplication.processEvents()
        screen = tuple(int(value) for value in
                       native.getPointOnScreen(App.Vector(0, 0, 128)))
        controller = PlateController(doc, view=native, placement=App.Placement())
        original_to_wp = Gui.Snapper.toWP
        snapped = controller._snap_point({"Position": screen})
        assert Gui.Snapper.toWP == original_to_wp
        outcome["checks"].append({
            "native_snap_screen": screen,
            "native_snap_point": tuple(snapped) if snapped is not None else None,
            "native_snap_mode": getattr(Gui.Snapper, "cursorMode", None),
            "native_snap_info": str(controller._last_snap_info),
            "projection_restored": True,
        })
        controller.cancel()
        outcome["ok"] = True
    except Exception:
        outcome["error"] = traceback.format_exc()
        App.Console.PrintError(outcome["error"])
    finally:
        if doc is not None:
            App.closeDocument(doc.Name)
        RESULT_PATH.write_text(json.dumps(outcome, indent=2), encoding="utf-8")
        App.Console.PrintMessage("StructuralPlate GUI probe: " + str(outcome) + "\n")
        QtCore.QTimer.singleShot(0, QtWidgets.QApplication.quit)


QtCore.QTimer.singleShot(700, run)
