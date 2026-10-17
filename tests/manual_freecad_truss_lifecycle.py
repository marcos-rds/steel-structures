"""Native TaskView replacement and Undo lifecycle diagnostics, FreeCAD 1.1.4."""
import json
import os
from pathlib import Path
import sys
import traceback


def run_baseline(output):
    """Load only committed panel/controller in an isolated native process."""
    import importlib.util
    import FreeCAD as App
    import FreeCADGui as Gui
    import DraftTools
    from PySide import QtCore, QtWidgets
    for module in ("truss_task_panel", "truss_controller"):
        name="freecad.SteelStructures.interactive."+module
        path=Path(os.environ["SS_TRUSS_LIFECYCLE_BASELINE"])/(module+".py")
        spec=importlib.util.spec_from_file_location(name,path)
        loaded=importlib.util.module_from_spec(spec)
        sys.modules[name]=loaded
        spec.loader.exec_module(loaded)
    controllers=sys.modules["freecad.SteelStructures.interactive.truss_controller"]
    def drain():
        for _ in range(5):
            QtWidgets.QApplication.processEvents()
            QtCore.QCoreApplication.sendPostedEvents(None,QtCore.QEvent.DeferredDelete)
    doc=App.newDocument("TrussCommittedLifecycle")
    panel=controllers.open_truss_panel(doc)
    drain()
    panel._preview_timer.stop()
    panel._update_preview3d()
    preview=panel.controller._preview
    scene,node=preview.scene_graph,preview.node
    Gui.draftToolBar.selectplane()
    drain()
    first_collision=panel.form is not None and controllers._active_panel is panel
    Gui.draftToolBar.selectplane()
    drain()
    observed=dict(baseline="68dc4b4 panel/controller; current unchanged geometry adapters",
        first_wp_collides=first_collision,form_is_none=panel.form is None,
        active_same=controllers._active_panel is panel,controller_closed=panel.controller.closed,
        coin_index=scene.findChild(node),wp_task_open=bool(Gui.Control.activeDialog()))
    (output/"baseline_observation.json").write_text(json.dumps(observed,indent=2))
    reproduced=first_collision and observed["form_is_none"] and observed["active_same"] and not observed["controller_closed"] and observed["coin_index"]>=0
    App.activeDraftCommand.finish()
    panel.controller.cancel()
    controllers._active_panel=None
    return dict(ok=reproduced,version=App.Version()[:3],observation=observed)


def run(output):
    import FreeCAD as App
    import FreeCADGui as Gui
    import DraftTools
    from PySide import QtCore, QtWidgets
    import shiboken6
    from freecad.SteelStructures import truss
    from freecad.SteelStructures.interactive import truss_controller as controllers
    doc=App.newDocument("TrussLifecycleGate")
    doc.UndoMode=1
    checks=[]
    def check(name, condition):
        if not condition:
            raise AssertionError(name)
        checks.append(name)
        (output/"checks.json").write_text(json.dumps(checks,indent=2))
    def drain():
        for _ in range(5):
            QtWidgets.QApplication.processEvents()
            QtCore.QCoreApplication.sendPostedEvents(None,QtCore.QEvent.DeferredDelete)
    def open_panel(owner=None):
        Gui.Selection.clearSelection()
        panel=controllers.open_truss_panel(doc,owner)
        drain()
        panel._preview_timer.stop()
        panel.span.setValue(2400.)
        panel._preview_timer.stop()
        panel._update_preview3d()
        check("live_preview",panel.controller._preview is not None)
        return panel
    def resources(panel):
        preview=panel.controller._preview
        return (preview.scene_graph,preview.node,panel.form,panel._preview_timer)
    def cleaned(label,panel,held):
        drain()
        scene,node,form,timer=held
        check(label+"_session_closed",panel._closed and panel.session.closed and panel.controller.closed)
        check(label+"_session_invalid",not panel.session.valid and panel._on_close is None and panel._point_picker is None)
        check(label+"_released_global",controllers._active_panel is None and App.activeDraftCommand is not panel)
        check(label+"_coin_detached",scene.findChild(node)==-1 and panel.controller._preview is None)
        check(label+"_capture_released",not panel.controller._point_callbacks and panel.controller._view is None
            and not panel.controller._gusset_visibility)
        check(label+"_qt_deleted",panel.form is None and not shiboken6.isValid(form) and not shiboken6.isValid(timer))
        panel.reject()
        panel.finish()
        check(label+"_idempotent",controllers._active_panel is None)
    def screenshot(name):
        view=Gui.activeDocument().activeView()
        view.saveImage(str(output/(name+".png")),900,650,"Current")

    panel=open_panel()
    held=resources(panel)
    panel._pick_points()
    check("wp_capture_before",len(panel.controller._point_callbacks)==3)
    tokens=list(panel.controller._point_callbacks)
    removals=[]
    native_view=panel.controller._view
    class ObservedView:
        def removeEventCallback(self,kind,token):
            native_view.removeEventCallback(kind,token)
            removals.append((kind,token))
    panel.controller._view=ObservedView()
    panel.form.grab().save(str(output/"before_wp_panel.png"))
    screenshot("before_wp")
    # Exact WP toolbar entry point reported by the user.
    Gui.draftToolBar.selectplane()
    drain()
    wp=App.activeDraftCommand
    check("wp_first_activation_takes_over",type(wp).__name__=="Draft_SelectPlane" and Gui.Control.activeDialog())
    cleaned("wp_creation",panel,held)
    check("wp_native_callbacks_removed",removals==tokens)
    check("wp_not_closed_by_old_teardown",App.activeDraftCommand is wp and Gui.Control.activeDialog())
    wp.taskd.form.grab().save(str(output/"after_wp_panel.png"))
    screenshot("after_wp")
    wp.finish()
    drain()
    screenshot("after_wp_close")
    check("creation_cancel_has_no_objects",not doc.Objects and doc.UndoCount==0)
    panel=open_panel()
    held=resources(panel)
    panel.reject()
    cleaned("normal_cancel",panel,held)

    # Applied owner must survive a command handoff, with only the draft discarded.
    panel=open_panel()
    panel.height.setValue(1000.)
    check("first_apply",panel.apply())
    owner=panel.session.owner
    panel.height.setValue(1200.)
    check("second_apply",panel.apply() and owner.Height.Value==1200.)
    panel.height.setValue(1400.)
    panel._preview_timer.stop()
    panel._update_preview3d()
    held=resources(panel)
    undo_count=doc.UndoCount
    Gui.draftToolBar.selectplane()
    cleaned("wp_after_apply",panel,held)
    check("handoff_preserves_applies",owner.Height.Value==1200. and doc.UndoCount==undo_count)
    App.activeDraftCommand.finish()
    drain()
    owner.ViewObject.Proxy.doubleClicked(owner.ViewObject)
    panel=controllers._active_panel
    drain()
    panel._preview_timer.stop()
    check("double_click_reopen",panel._valid and panel.session.owner is owner)
    panel.reject()
    drain()

    # Arbitrary external TaskView removal: destruction fallback must not close successor.
    panel=open_panel(owner)
    held=resources(panel)
    Gui.Control.closeDialog()
    class OtherTask:
        def __init__(self):
            self.form=QtWidgets.QWidget()
            self.form.setWindowTitle("Lifecycle replacement gate")
    replacement=OtherTask()
    Gui.Control.showDialog(replacement)
    cleaned("external_task",panel,held)
    check("successor_task_still_open",Gui.Control.activeDialog() and replacement.form is not None)
    screenshot("other_task")
    Gui.Control.closeDialog()
    drain()

    panel=open_panel(owner)
    held=resources(panel)
    QtCore.QTimer.singleShot(0,Gui.Control.closeDialog)
    panel._open_topology_editor()
    cleaned("modal_editor_external_close",panel,held)

    panel=open_panel(owner)
    held=resources(panel)
    QtCore.QTimer.singleShot(0,Gui.Control.closeDialog)
    panel._edit_role("TOP_CHORD")
    cleaned("modal_profile_external_close",panel,held)

    # Another actual Draft command uses the same standard finish handoff.
    panel=open_panel(owner)
    held=resources(panel)
    Gui.runCommand("Draft_Line",0)
    drain()
    line=App.activeDraftCommand
    check("draft_line_took_over",line is not panel and line is not None and Gui.Control.activeDialog())
    cleaned("draft_line",panel,held)
    line.finish()
    drain()

    panel=open_panel(owner)
    other=App.newDocument("TrussLifecycleOther")
    drain()
    check("switch_no_cross_document_apply",not panel.apply() and owner.Height.Value==1200.)
    App.setActiveDocument(doc.Name)
    drain()
    check("switch_back_same_session",controllers._active_panel is panel and panel.apply())
    held=resources(panel)
    panel.reject()
    cleaned("switch_back_cancel",panel,held)
    App.setActiveDocument(other.Name)
    doc=other
    panel=open_panel()
    held=resources(panel)
    panel._pick_points()
    App.closeDocument(doc.Name)
    cleaned("document_close",panel,held)
    check("document_close_task_gone",not Gui.Control.activeDialog())
    doc=App.newDocument("TrussLifecycleReopen")
    panel=open_panel()
    check("new_document_reopens",panel.session.document is doc and panel.session.owner is None and panel._valid)
    held=resources(panel)
    panel.reject()
    cleaned("final_cancel",panel,held)
    return dict(ok=True,version=App.Version()[:3],checks=checks)


if os.environ.get("SS_DUOPITCH_ROOT"):
    import FreeCAD as App
    from PySide import QtCore, QtWidgets
    root=Path(os.environ["SS_DUOPITCH_ROOT"])
    out=Path(os.environ["SS_DUOPITCH_OUT"])
    sys.path.insert(0,str(root))
    import freecad
    freecad.__path__.insert(0,str(root/"freecad"))
    def launch():
        try:
            result=run_baseline(out) if os.environ.get("SS_TRUSS_LIFECYCLE_BASELINE") else run(out)
        except Exception:
            result=dict(ok=False,error=traceback.format_exc())
            App.Console.PrintError(result["error"])
        (out/"result.json").write_text(json.dumps(result,indent=2))
        for name in tuple(App.listDocuments()):
            App.closeDocument(name)
        QtCore.QTimer.singleShot(0,QtWidgets.QApplication.quit)
    QtCore.QTimer.singleShot(500,launch)
