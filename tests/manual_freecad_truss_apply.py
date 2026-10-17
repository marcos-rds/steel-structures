"""Native TaskView Apply, transactions and external conflict gate, FreeCAD 1.1.4."""
import copy
import json
import os
from pathlib import Path
import sys
import traceback


def run(output):
    import FreeCAD as App
    import FreeCADGui as Gui
    import Draft
    import DraftTools  # Install the native Draft Snapper as in the workbench.
    from PySide import QtWidgets
    from freecad.SteelStructures import truss
    from freecad.SteelStructures.interactive import truss_controller as controllers
    from freecad.SteelStructures.interactive.truss_topology_editor import TopologyEditor
    from freecad.SteelStructures.trusses.assemblies import configure_assembly
    from freecad.SteelStructures.trusses.interconnector_options import default_connector
    from freecad.SteelStructures.trusses.preset_contracts import compatible_presets
    from freecad.SteelStructures.trusses.serialization import decode_state
    checks = []
    def check(name, condition):
        if not condition:
            raise AssertionError(name)
        checks.append(name)
        (output/"checks.json").write_text(json.dumps(checks,indent=2))
    def settle(panel):
        QtWidgets.QApplication.processEvents()
        panel._preview_timer.stop()
    def open_panel(owner=None):
        panel=controllers.open_truss_panel(doc,owner)
        settle(panel)
        return panel
    def names():
        return tuple(o.Name for o in doc.Objects)
    def counters():
        return (doc.UndoCount, observer.count)
    def value(**changes):
        cfg=truss.default_config()
        cfg.update(span=2400.,end=[2400.,0.,0.],height=1000.,panel_count=6)
        cfg.update(changes)
        return cfg
    class Observer:
        count=0
        def slotRecomputedDocument(self,current):
            if current is doc:
                self.count+=1
    doc=App.newDocument("TrussApplyGate")
    doc.UndoMode=1
    observer=Observer()
    App.addDocumentObserver(observer)
    # Exercise native Task View button dispatch, not just panel.apply().
    panel=open_panel()
    check("new_default_pratt", panel.session.config["topology_preset"]=="Pratt"
        and all("Pratt" in compatible_presets(kind) for kind in ("Parallel","DuoPitch")))
    panel.height.setValue(1000.)
    panel.span.setValue(2400.)
    settle(panel)
    box=panel.form.window().findChild(QtWidgets.QDialogButtonBox)
    button=box.button(QtWidgets.QDialogButtonBox.Apply) if box else None
    check("native_apply_button", button is not None)
    before=counters()
    button.click()
    settle(panel)
    owner=panel.session.owner
    check("first_apply_creates_and_keeps_open", owner is not None and not panel._closed and not panel.session.closed)
    check("first_apply_one_transaction_recompute", counters()==(before[0]+1,before[1]+1))
    check("first_apply_clean",not panel.session.pending_changes and not panel.session.needs_application)
    registry=names()
    before=counters()
    check("noop_apply_returns_success",panel.apply())
    check("noop_has_no_transaction_recompute",counters()==before and names()==registry)
    panel._pick_points()
    check("noop_apply_stops_capture",panel.apply() and not panel.controller._point_callbacks
        and panel.controller._view is None and counters()==before)
    panel.height.setValue(1200.)
    settle(panel)
    before=counters()
    button.click()
    settle(panel)
    check("second_apply_same_owner",panel.session.owner is owner and owner.Height.Value==1200. and names()==registry)
    check("second_apply_one_transaction_recompute",counters()==(before[0]+1,before[1]+1))
    check("baseline_and_realized_rebased", panel.session.baseline_config["height"]==1200.
        and panel.session.realized_config["height"]==1200. and panel.session.applied_state==owner.AppliedState)
    panel.height.setValue(1400.)
    settle(panel)
    panel.reject()
    check("required_cancel_keeps_1200",owner.Height.Value==1200.)
    doc.undo()
    check("undo_second_apply",owner.Height.Value==1000.)
    doc.redo()
    check("redo_second_apply",owner.Height.Value==1200.)
    # OK with no pending changes must not create an Undo record or recompute.
    owner.ViewObject.Proxy.doubleClicked(owner.ViewObject)
    panel=controllers._active_panel
    settle(panel)
    before=counters()
    check("double_click_ok_no_changes",panel.accept() and panel.session.closed)
    check("ok_no_changes_no_transaction_recompute",counters()==before)
    panel=open_panel(owner)
    panel.height.setValue(1300.)
    settle(panel)
    before=counters()
    check("ok_applies_and_closes",panel.accept() and owner.Height.Value==1300.)
    check("ok_one_transaction_recompute",counters()==(before[0]+1,before[1]+1))
    # Invalid draft never mutates persistent state.
    panel=open_panel(owner)
    panel.left_end_height.setValue(2000.)
    panel.envelope_type.setCurrentIndex(panel.envelope_type.findData("DuoPitch"))
    settle(panel)
    applied=owner.AppliedState
    before=counters()
    check("invalid_apply_rejected",not panel.apply() and not panel._closed)
    check("invalid_apply_preserves_document",owner.AppliedState==applied and counters()==before and names()==registry)
    panel.reject()
    # Force a failure inside the existing native transaction; it must roll back.
    panel=open_panel(owner)
    panel.height.setValue(1600.)
    settle(panel)
    before=counters()
    original_apply=truss.apply_result
    attempts=[]
    def fail_second(*args,**kwargs):
        attempts.append(1)
        if len(attempts)==2:
            raise ValueError("Injected native regeneration failure")
        return original_apply(*args,**kwargs)
    truss.apply_result=fail_second
    try:
        check("native_failure_rejected",not panel.apply())
    finally:
        truss.apply_result=original_apply
    check("native_failure_rollback",owner.AppliedState==applied and owner.Height.Value==1300.
        and names()==registry and doc.UndoCount==before[0] and not panel._closed)
    check("native_failure_retry",panel.apply() and owner.Height.Value==1600.)
    panel.reject()
    # Redo from a baseline opened after Undo is an external change too.
    doc.undo()
    panel=open_panel(owner)
    doc.redo()
    before=counters()
    check("external_redo_conflict",not panel.apply() and counters()==before and panel.session.conflict_reason)
    panel.reject()
    # Compound/interconnector/Gusset state and Custom remain editable after Apply.
    cfg=value(topology_preset="Warren")
    cfg["role_specs"]["TOP_CHORD"]=configure_assembly(cfg["role_specs"]["TOP_CHORD"],
        "SpacedPair",240.,interconnectors=(default_connector("Battens"),))
    cfg["connection_intents"]={"B_S_MAIN_1_3":dict(form="Gusset",gusset=dict(plate_thickness=12.))}
    composite=truss.apply_truss(doc,cfg)
    panel=open_panel(composite)
    check("existing_warren_preserved",panel.session.config["topology_preset"]=="Warren")
    roles=copy.deepcopy(panel.session.config["role_specs"])
    intents=copy.deepcopy(panel.session.config["connection_intents"])
    child_names=tuple(c.Name for c in composite.GeneratedMembers)
    plate_names=tuple(p.Name for p in composite.GeneratedGussetPlates)
    panel.height.setValue(1200.)
    settle(panel)
    check("composite_apply",panel.apply())
    check("composite_connectors_gussets_preserved",panel.session.config["role_specs"]==roles
        and panel.session.config["connection_intents"]==intents
        and tuple(c.Name for c in composite.GeneratedMembers)==child_names
        and tuple(p.Name for p in composite.GeneratedGussetPlates)==plate_names)
    before=counters()
    check("composite_apply_noop",panel.apply() and counters()==before)
    editor=TopologyEditor(panel)
    editor.show()
    settle(panel)
    edge=next(e for e in panel.controller.last_candidate.graph.edges if e.role=="DIAGONAL")
    panel.apply_topology_edit("remove_edge",key=edge.key)
    editor.canvas.refresh_candidate()
    check("editor_shared_custom",editor.panel.session is panel.session and panel.session.config["topology_mode"]=="Custom")
    editor.close()
    editor.deleteLater()
    check("custom_apply",panel.apply() and composite.TopologyMode=="Custom")
    before=counters()
    check("custom_apply_noop",panel.apply() and counters()==before)
    panel._update_preview3d()
    panel.reject()
    check("preview_and_callbacks_released",panel.controller._preview is None and not panel.controller._point_callbacks
        and panel.controller._view is None and not panel.controller._gusset_visibility)
    panel=open_panel(composite)
    check("custom_reopen_preserved",panel.session.config["topology_mode"]=="Custom" and not panel.session.pending_changes)
    panel.reject()
    # Associative and snapshot sources survive repeated application.
    for linked in (False,True):
        line=Draft.make_line(App.Vector(0,0,0),App.Vector(2400,0,0))
        doc.recompute()
        ref=truss.apply_truss(doc,value(reference_mode="DraftLine",reference_source=line.Name,
            reference_edge="Edge1",reference_linked=linked))
        panel=open_panel(ref)
        for height in (1100.,1200.):
            panel.height.setValue(height)
            settle(panel)
            check("reference_apply_"+str(linked)+str(height),panel.apply())
        check("reference_preserved_"+str(linked),panel.session.config["reference_linked"]==linked
            and panel.session.config["reference_source"]==line.Name)
        panel.reject()
    # Undo while open blocks stale draft, even if later Redo restores prior state.
    panel=open_panel(owner)
    panel.height.setValue(1400.)
    settle(panel)
    check("pre_undo_apply",panel.apply())
    doc.undo()
    before=counters()
    check("undo_external_conflict",not panel.apply() and not panel._closed and panel.session.conflict_reason)
    check("conflict_no_transaction",counters()==before)
    doc.redo()
    check("redo_does_not_clear_conflict",not panel.apply())
    panel.reject()
    panel=open_panel(owner)
    owner.Proxy._updating=True
    owner.Height=1500.
    owner.Proxy._updating=False
    before=counters()
    check("requested_property_conflict",not panel.apply() and counters()==before)
    panel.reject()
    # Active document switch is recoverable by returning to the session document.
    panel=open_panel(owner)
    other=App.newDocument("OtherTrussApplyGate")
    check("document_switch_blocks_apply",not panel.apply())
    App.setActiveDocument(doc.Name)
    settle(panel)
    check("reactivate_document_resumes",panel.apply())
    panel.reject()
    App.closeDocument(other.Name)
    # Creation Undo removes owner; never create a replacement silently.
    panel=open_panel()
    panel.span.setValue(2400.)
    settle(panel)
    check("creation_for_remove_gate",panel.apply())
    removed_name=panel.session.owner.Name
    doc.undo()
    before=counters()
    check("owner_removed_blocks_apply",doc.getObject(removed_name) is None and not panel.apply() and counters()==before)
    panel.reject()
    removed=truss.apply_truss(doc,value())
    panel=open_panel(removed)
    doc.removeObject(removed.Name)
    before=counters()
    check("explicit_owner_removal_blocks_apply",not panel.apply() and counters()==before)
    panel.reject()
    # Persistence and closed-document disposal with Coin/Gussets active.
    path=output/"apply_session.FCStd"
    doc.saveAs(str(path))
    saved_name=owner.Name
    saved_composite=composite.Name
    App.removeDocumentObserver(observer)
    name=doc.Name
    App.closeDocument(name)
    doc=App.openDocument(str(path))
    doc.UndoMode=1
    owner=doc.getObject(saved_name)
    panel=open_panel(owner)
    check("save_reopen_clean",panel._valid and not panel.session.pending_changes and owner.Height.Value==1500.)
    panel.reject()
    panel=open_panel(doc.getObject(saved_composite))
    panel._update_preview3d()
    check("gussets_hidden_for_coin",bool(panel.controller._gusset_visibility))
    panel._pick_points()
    check("capture_active_before_close",bool(panel.controller._point_callbacks))
    doc_name=doc.Name
    App.closeDocument(doc_name)
    check("closed_document_blocks_apply",not panel.apply())
    panel.reject()
    check("closed_document_cleanup",panel.controller._preview is None and not panel.controller._point_callbacks
        and panel.controller._view is None
        and not panel.controller._gusset_visibility)
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
            result=run(out)
        except Exception:
            result=dict(ok=False,error=traceback.format_exc())
            App.Console.PrintError(result["error"])
        (out/"result.json").write_text(json.dumps(result,indent=2))
        for name in tuple(App.listDocuments()):
            App.closeDocument(name)
        QtCore.QTimer.singleShot(0,QtWidgets.QApplication.quit)
    QtCore.QTimer.singleShot(500,launch)
