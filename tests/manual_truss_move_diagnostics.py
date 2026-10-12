"""Real-GUI Draft Move diagnostic, including a control without this workbench.

Launch in an isolated FreeCAD profile with TRUSS_COPY_ROOT/TRUSS_COPY_RUN set.
TRUSS_MOVE_CONTROL=1 uses only a native Draft Wire (no Steel Structures import).
TRUSS_MOVE_TRACE=0 disables test-only profiling. Inspect FreeCAD.log as well as
result.json: functional checks passing do NOT imply absence of native warnings.
No command implementation, timer queue or installed FreeCAD file is patched.
"""
import json
import math
import os
from pathlib import Path
import sys
import traceback


def launch():
    import FreeCAD as App
    import FreeCADGui as Gui
    from PySide import QtCore, QtWidgets
    from pivy import coin
    import Draft

    out = Path(os.environ["TRUSS_COPY_RUN"])
    out.mkdir(parents=True, exist_ok=True)
    control = os.environ.get("TRUSS_MOVE_CONTROL") == "1"
    trace = os.environ.get("TRUSS_MOVE_TRACE", "1") != "0"
    events, checks = [], []
    stage = "setup"
    doc = None
    pending = None
    result = dict(ok=False, control=control, traced=trace, checks=checks, previews=[])

    def begin(name):
        nonlocal stage
        stage = name
        App.Console.PrintMessage("TRUSS_MOVE_STAGE " + name + "\n")

    def profile(frame, event, arg):
        if event == "c_call" and getattr(arg, "__name__", "") == "recompute":
            events.append(dict(stage=stage, event=event, name="recompute",
                               stack=traceback.format_stack(frame, limit=12)))
        elif event in ("call", "return") and frame.f_code.co_name == "doTasks":
            from draftutils.todo import ToDo
            events.append(dict(stage=stage, event=event, name="doTasks",
                               after=[str(item[1]) for item in ToDo.afteritinerary]))

    def check(name, condition):
        if not condition:
            raise AssertionError(name)
        checks.append(name)

    def finish(error=None):
        sys.setprofile(None)
        result["steel_imported"] = any("SteelStructures" in name for name in sys.modules)
        if error:
            result["error"] = error
            App.Console.PrintError(error)
        (out / "events.json").write_text(json.dumps(events, indent=2), encoding="utf-8")
        (out / "result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        for name in tuple(App.listDocuments()):
            App.closeDocument(name)
        QtCore.QTimer.singleShot(0, QtWidgets.QApplication.quit)

    def owners():
        if control:
            return list(doc.Objects)
        return [obj for obj in doc.Objects if isinstance(getattr(obj, "Proxy", None), truss.StructuralTrussProxy)]

    def valid(obj):
        if control:
            return not obj.Shape.isNull() and obj.Shape.isValid()
        from freecad.SteelStructures.trusses.serialization import decode_state
        truss.bound_children(obj, decode_state(obj.AppliedState))
        return obj.GenerationState == "Valid" and all(
            child.GenerationOwner == obj and child.Shape.isValid() and child.Shape.Volume > 0
            for child in obj.GeneratedMembers)

    def verify_gui():
        nonlocal doc
        try:
            name, copy, cancel, source, before_count, start, ghost_switch = pending
            check(name + "_command_finished", App.activeDraftCommand is None and not Gui.Control.activeDialog())
            check(name + "_ghost_removed", Gui.activeDocument().activeView().getSceneGraph().findChild(ghost_switch) < 0)
            current = owners()
            check(name + "_all_valid", all(valid(obj) for obj in current))
            if cancel:
                check(name + "_unchanged", len(current) == before_count and source.Placement.Base == start)
            elif copy:
                target = current[-1]
                check(name + "_owner_position", len(current) == before_count+1
                      and (target.Placement.Base-start-vector).Length < 1e-6 and source.Placement.Base == start)
                if not control:
                    check(name + "_independent_members", all(
                        not set(target.GeneratedMembers).intersection(obj.GeneratedMembers) for obj in current[:-1]))
                    old = {child.GenerationKey: child for child in source.GeneratedMembers}
                    check(name + "_member_positions", all(
                        (child.StartPoint-old[child.GenerationKey].StartPoint-vector).Length < 1e-6
                        for child in target.GeneratedMembers))
            else:
                check(name + "_position", len(current) == before_count
                      and (source.Placement.Base-start-vector).Length < 1e-6)
            if operations:
                QtCore.QTimer.singleShot(50, start_gui)
                return
            begin("gui_undo_redo")
            count = len(doc.Objects)
            doc.undo(); doc.recompute()
            doc.redo(); doc.recompute()
            check("gui_copy_undo_redo", len(doc.Objects) == count and all(valid(obj) for obj in owners()))
            begin("gui_save_reopen")
            path = out / "native-moves.FCStd"
            doc.saveAs(str(path)); App.closeDocument(doc.Name)
            doc = App.openDocument(str(path)); doc.recompute()
            check("gui_save_reopen", len(doc.Objects) == count and all(valid(obj) for obj in owners()))
            result["ok"] = True
            finish()
        except Exception:
            finish(traceback.format_exc())

    def start_gui():
        nonlocal pending
        try:
            name, copy, cancel = operations.pop(0)
            begin(name)
            source = owners()[-1]
            start = App.Vector(source.Placement.Base)
            Gui.Selection.clearSelection(); Gui.Selection.addSelection(source)
            Gui.runCommand("Draft_Move")
            command = App.activeDraftCommand
            command.ui.isCopy.setChecked(copy)
            command.ui.continueMode = False
            command.set_ghosts()
            ghost = command.ghosts[0]
            action = coin.SoGetBoundingBoxAction(coin.SbViewportRegion(800, 600))
            action.apply(ghost.rootsep)
            result["previews"].append(dict(stage=name, empty=bool(action.getBoundingBox().isEmpty())))
            pending = (name, copy, cancel, source, len(owners()), start, ghost.switch)
            command.numericInput(0, 0, 0)
            if cancel:
                command.finish()
            else:
                command.numericInput(vector.x, vector.y, vector.z)
            QtCore.QTimer.singleShot(600, verify_gui)
        except Exception:
            finish(traceback.format_exc())

    try:
        Gui.activateWorkbench("DraftWorkbench")
        doc = App.newDocument("NativeMoveDiagnostics")
        doc.UndoMode = 1
        vector = App.Vector(125, 2800, 400)
        if trace:
            sys.setprofile(profile)
        begin("create")
        if control:
            points = [App.Vector(i*10, 500*math.sin(i*.1), 0) for i in range(2500)]
            source = Draft.make_wire(points, closed=False, face=False)
            doc.recompute()
        else:
            from freecad.SteelStructures import truss
            config = truss.default_config()
            config.update(span=2400., height=700., end=[2400., 0., 0.], panel_count=4)
            source = truss.apply_truss(doc, config)
            begin("api_move")
            Draft.move([source], vector, copy=False); doc.recompute()
            begin("api_copy")
            copied = Draft.move([source], vector, copy=True); doc.recompute()
            check("api_copy_valid", valid(source) and valid(copied))
            for name, obj in (("property_original", source), ("property_copy", copied)):
                begin(name)
                obj.Height = obj.Height.Value + 50.; doc.recompute()
                check(name, valid(obj))
            for name, obj in (("regenerate_original", source), ("regenerate_copy", copied)):
                begin(name)
                config = truss.config_from_object(obj); config["panel_count"] = 6
                truss.apply_truss(doc, config, obj)
                check(name, valid(obj))
        check("created_valid", all(valid(obj) for obj in owners()))
        operations = [("gui_move", False, False), ("gui_copy_1", True, False),
                      ("gui_copy_2", True, False), ("gui_copy_3", True, False),
                      ("gui_cancel", True, True)]
        QtCore.QTimer.singleShot(50, start_gui)
    except Exception:
        finish(traceback.format_exc())


if os.environ.get("TRUSS_COPY_ROOT") and os.environ.get("TRUSS_COPY_RUN"):
    sys.path.insert(0, os.environ["TRUSS_COPY_ROOT"])
    import freecad
    freecad.__path__.insert(0, str(Path(os.environ["TRUSS_COPY_ROOT"]) / "freecad"))
    from PySide import QtCore
    QtCore.QTimer.singleShot(500, launch)
