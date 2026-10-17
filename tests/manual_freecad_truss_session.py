"""Isolated FreeCAD 1.1.4 Qt/session gate. No user documents are touched."""
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
    from PySide import QtWidgets
    from freecad.SteelStructures import truss
    from freecad.SteelStructures.interactive import truss_controller as controllers
    from freecad.SteelStructures.interactive.truss_task_panel import TrussTaskPanel
    from freecad.SteelStructures.interactive.truss_topology_editor import TopologyEditor
    from freecad.SteelStructures.trusses.assemblies import configure_assembly
    from freecad.SteelStructures.trusses.interconnector_options import default_connector

    checks = []
    def check(name, condition):
        if not condition:
            raise AssertionError(name)
        checks.append(name)
        (output/"checks.json").write_text(json.dumps(checks, indent=2))

    doc = App.newDocument("TrussSessionGate")
    value = truss.default_config()
    value.update(span=2400., end=[2400.,0.,0.], height=700., panel_count=6)
    value["role_specs"]["TOP_CHORD"] = configure_assembly(
        value["role_specs"]["TOP_CHORD"], "SpacedPair", 240.,
        interconnectors=(default_connector("Battens"),))
    value["connection_intents"] = {"B_S_MAIN_1_3": dict(form="Gusset",
        gusset=dict(plate_thickness=12., edge_margin=31., member_overlap=163.))}
    owner = truss.apply_truss(doc, value)
    before = owner.AppliedState
    members = tuple(o.Name for o in doc.Objects)
    panel = controllers.open_truss_panel(doc, owner)
    QtWidgets.QApplication.processEvents()
    panel._preview_timer.stop()
    check("shared_session", panel.session is panel.controller.session)
    (output/"initial_state.json").write_text(json.dumps(dict(valid=panel._valid, message=panel.message.text(),
        differences={key: [panel.session._clean_config.get(key), panel.session.config.get(key)]
        for key in set(panel.session._clean_config)|set(panel.session.config)
        if panel.session._clean_config.get(key)!=panel.session.config.get(key)}),indent=2))
    check("unchanged_edit_clean", panel._valid and not panel.session.pending_changes)
    try:
        controllers.open_truss_panel(doc)
    except ValueError:
        check("other_owner_rejected", True)
    else:
        check("other_owner_rejected", False)
    baseline = panel.session.baseline_config
    advanced = copy.deepcopy(panel.get_config()["role_specs"])
    for height in (800.,900.,700.):
        panel.height.setValue(height)
        panel._preview_timer.stop()
        check("successive_height_"+str(height), panel._valid and panel.session.config["height"]==height)
        check("advanced_preserved_"+str(height), panel.get_config()["role_specs"]==advanced)
    check("baseline_immutable", panel.session.baseline_config == baseline)
    editor = TopologyEditor(panel)
    editor.show()
    QtWidgets.QApplication.processEvents()
    editor.canvas.refresh_candidate()
    check("current_editor_shares_draft", editor.panel.session is panel.session)
    edge = next(e for e in panel.controller.last_candidate.graph.edges if e.role=="DIAGONAL")
    panel.apply_topology_edit("remove_edge",key=edge.key)
    editor.canvas.refresh_candidate()
    check("custom_edit_shared", panel.session.config["topology_mode"]=="Custom"
        and not any(e.key==edge.key for e in panel.session.validated_candidate.graph.edges))
    editor.grab().save(str(output/"editor.png"))
    editor.close()
    editor.deleteLater()
    panel._refresh()
    panel._update_preview3d()
    check("coin_preview_created", panel.controller._preview is not None)
    panel.form.grab().save(str(output/"panel.png"))
    panel.reject()
    QtWidgets.QApplication.processEvents()
    check("cancel_closes_session_and_coin", panel.session.closed and panel.controller._preview is None)
    check("cancel_preserves_persistence", owner.AppliedState==before and tuple(o.Name for o in doc.Objects)==members)
    previous_identity = panel.session.identity
    consumed = owner.ViewObject.Proxy.doubleClicked(owner.ViewObject)
    panel = controllers._active_panel
    panel._preview_timer.stop()
    check("double_click_opens_session", consumed and panel.session.owner is owner)
    check("reopen_fresh_session", panel.session.identity != previous_identity
        and panel.session.baseline_config["topology_mode"]!="Custom")
    check("unchanged_accept", panel.accept())
    check("accept_closes_session", panel.session.closed)
    # Snapshot and associative reference correction, loaded without resolution.
    line = Draft.make_line(App.Vector(0,0,0),App.Vector(2400,0,0))
    doc.recompute()
    ref = truss.default_config()
    ref.update(span=2400.,end=[2400.,0.,0.],height=700.,panel_count=6,
        reference_mode="DraftLine",reference_source=line.Name,reference_edge="Edge1",reference_linked=True)
    linked = truss.apply_truss(doc,ref)
    doc.removeObject(line.Name)
    panel = controllers.open_truss_panel(doc,linked)
    panel._preview_timer.stop()
    check("invalid_source_opens", not panel._valid and panel.session.validated_candidate is None)
    panel.keep_reference_link.setChecked(False)
    panel._preview_timer.stop()
    check("snapshot_correction", panel._valid and panel.session.validated_candidate is not None)
    panel.reject()
    controller = controllers.TrussController(doc)
    panel = TrussTaskPanel(doc,controller,value)
    panel._preview_timer.stop()
    check("new_truss_session", panel.session.owner is None and panel._valid)
    check("new_truss_accept", panel.accept() and controller.object is not None)
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
