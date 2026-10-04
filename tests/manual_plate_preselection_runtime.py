"""FreeCAD GUI probe for the 1.1.4 preselection object contract.

Run with FreeCAD.exe tests/manual_plate_preselection_runtime.py. The script
records empty and explicitly set preselection states to a JSON file in TEMP.
Physical hover/click behavior is diagnosed by manual_plate_face_snap_probe.py.
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


RESULT = Path(tempfile.gettempdir()) / "steelstructures_plate_preselection_runtime.json"
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "freecad"))


def describe_preselection():
    item = Gui.Selection.getPreselection()
    result = {"type": type(item).__name__, "repr": repr(item),
              "attributes": [name for name in dir(item) if not name.startswith("_")]}
    for name in ("Object", "SubElementNames", "SubObjects", "PickedPoints",
                 "Document", "DocumentName", "ObjectName", "SubName", "Point"):
        try:
            value = getattr(item, name)
        except (AttributeError, ReferenceError, RuntimeError) as exc:
            result[name] = "ERROR: " + str(exc)
        else:
            result[name] = str(value)
    return result


def run():
    from SteelStructures.plate_planes import preselection_pick

    document = None
    try:
        Gui.activateWorkbench("DraftWorkbench")
        document = App.newDocument("PlatePreselectionRuntime")
        box = document.addObject("Part::Feature", "PreselectionBox")
        box.Shape = Part.makeBox(100, 80, 8)
        box.Placement.Base = App.Vector(0, 0, 120)
        document.recompute()
        view = Gui.activeDocument().activeView()
        view.viewAxonometric()
        view.fitAll()
        QtWidgets.QApplication.processEvents()
        center = box.Shape.Faces[5].CenterOfMass
        screen = tuple(int(value) for value in view.getPointOnScreen(center))
        main = Gui.getMainWindow()
        widgets = []
        for widget in main.findChildren(QtWidgets.QWidget):
            name = type(widget).__name__
            if widget.isVisible() and widget.width() > 100 and widget.height() > 100:
                origin = widget.mapToGlobal(QtCore.QPoint(0, 0))
                widgets.append({"class": name, "object_name": widget.objectName(),
                                "size": (widget.width(), widget.height()),
                                "global": (origin.x(), origin.y())})
        result = {"version": App.Version(), "screen": screen,
                  "object_info": str(view.getObjectInfo(screen)),
                  "preselection_empty": describe_preselection(),
                  "widgets": widgets}
        Gui.Selection.setPreselection(box, "Face6", center.x, center.y, center.z)
        result["preselection_set"] = describe_preselection()
        info, point = preselection_pick(Gui.Selection.getPreselection(), document)
        result["adapter_set"] = {"info": str(info), "point": str(point)}
        assert info["Component"] == "Face6" and abs(point.z - 128) < 1e-6
        Gui.Selection.clearPreselection()
        result["preselection_cleared"] = describe_preselection()
        assert preselection_pick(Gui.Selection.getPreselection(), document) == (
            None, None)
        RESULT.write_text(json.dumps(result, default=str), encoding="utf-8")
    except Exception:
        RESULT.write_text(json.dumps({"error": traceback.format_exc()}),
                          encoding="utf-8")
        App.Console.PrintError(traceback.format_exc())
    finally:
        if document is not None:
            App.closeDocument(document.Name)
        QtWidgets.QApplication.instance().quit()


QtCore.QTimer.singleShot(1000, run)
