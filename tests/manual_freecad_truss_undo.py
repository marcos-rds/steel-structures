"""Native Undo/Redo versus a shared truss draft, isolated FreeCAD 1.1.4 gate."""
from copy import deepcopy
import json
import math
import os
from pathlib import Path
import sys
import traceback


def run(output):
    import FreeCAD as App
    import FreeCADGui as Gui
    import DraftTools  # Install the same native Snapper as the workbench.
    from PySide import QtWidgets
    from freecad.SteelStructures import truss
    from freecad.SteelStructures.interactive import truss_controller as controllers
    from freecad.SteelStructures.interactive.truss_topology_editor import TopologyEditor
    from freecad.SteelStructures.trusses.serialization import decode_state

    checks, snapshots = [], {}

    def check(name, condition):
        if not condition:
            raise AssertionError(name)
        checks.append(name)
        (output / "checks.json").write_text(json.dumps(checks, indent=2))

    def settle(panel):
        QtWidgets.QApplication.processEvents()
        panel._preview_timer.stop()

    def new_document(suffix):
        document = App.newDocument("TrussUndoGate" + suffix)
        document.UndoMode = 1
        return document

    def native_history(document, command):
        App.setActiveDocument(document.Name)
        Gui.runCommand(command, 0)
        QtWidgets.QApplication.processEvents()

    def open_panel(document, owner=None):
        panel = controllers.open_truss_panel(document, owner)
        settle(panel)
        return panel

    def snapshot(label, document, owner_name, panel=None):
        owner = document.getObject(owner_name) if owner_name else None
        members = {}
        if owner is not None:
            for child in owner.GeneratedMembers:
                members[child.Name] = dict(
                    key=child.GenerationKey, base=list(child.Placement.Base),
                    rotation=list(child.Placement.Rotation.Q),
                    volume=round(child.Shape.Volume, 9),
                    valid=child.Shape.isValid(), null=child.Shape.isNull())
        state = dict(
            document=dict(
                owner_name=owner_name, owner_exists=owner is not None,
                objects=sorted(obj.Name for obj in document.Objects),
                requested=(truss.config_from_object(owner, resolve_reference=False)
                           if owner is not None else None),
                applied_state=owner.AppliedState if owner is not None else None,
                generated_members=members,
                undo_count=document.UndoCount, redo_count=document.RedoCount),
            session=(dict(identity=panel.session.identity, closed=panel.session.closed,
                          draft=deepcopy(panel.session.config),
                          baseline=panel.session.baseline_config,
                          applied_state=panel.session.applied_state,
                          conflict=panel.session.conflict_reason,
                          valid=panel.session.valid,
                          coin_present=panel.controller._preview is not None)
                     if panel is not None else None))
        snapshots[label] = state
        (output / "snapshots.json").write_text(json.dumps(snapshots, indent=2))
        return deepcopy(state["document"])

    def same_realization(actual, expected):
        # History counts intentionally differ across native Undo/Redo.
        if not all(actual[key] == expected[key] for key in (
            "owner_name", "owner_exists", "objects", "requested", "applied_state",
        )):
            return False
        actual_members, expected_members = actual["generated_members"], expected["generated_members"]
        if actual_members.keys() != expected_members.keys():
            return False
        for name, member in actual_members.items():
            previous = expected_members[name]
            if any(member[key] != previous[key] for key in member if key != "volume"):
                return False
            # OCC's native BRep restore may differ by a few ulps in volume.
            if not math.isclose(member["volume"], previous["volume"], rel_tol=1e-12, abs_tol=1e-6):
                return False
        return True

    def effective_apply(label, document, panel):
        before = document.UndoCount
        check(label + "_success", panel.apply())
        settle(panel)
        check(label + "_one_native_transaction", document.UndoCount == before + 1
              and document.RedoCount == 0)
        owner = panel.session.owner
        check(label + "_owner_and_clean", owner is panel.controller.object
              and owner.Document is document and not panel.session.pending_changes
              and not panel.session.needs_application and not panel.session.closed)
        return snapshot(label, document, owner.Name, panel)

    def create(label, document):
        panel = open_panel(document)
        panel.span.setValue(2400.)
        panel.height.setValue(1000.)
        settle(panel)
        check(label + "_new_pratt", panel.session.config["topology_preset"] == "Pratt")
        state = effective_apply(label, document, panel)
        return panel, panel.session.owner.Name, state

    def edit_web(label, document, panel, action, **arguments):
        before = snapshot(label + "_before", document, panel.session.owner.Name, panel)
        editor = TopologyEditor(panel)
        try:
            editor.show()
            settle(panel)
            check(label + "_shared_session", editor.panel.session is panel.session)
            panel.apply_topology_edit(action, **arguments)
            editor.canvas.refresh_candidate()
            check(label + "_custom_draft", panel.session.config["topology_mode"] == "Custom"
                  and panel.session.pending_changes and panel._valid)
        finally:
            editor.close()
            editor.deleteLater()
        settle(panel)
        after = snapshot(label + "_draft", document, panel.session.owner.Name, panel)
        check(label + "_draft_has_no_persistent_write", after == before)

    def conflict(label, document, owner_name, panel):
        before = snapshot(label + "_before_detection", document, owner_name, panel)
        check(label + "_refresh_rejects_stale_draft", not panel._refresh())
        check(label + "_coin_removed", panel.controller._preview is None)
        box = next((box for box in panel.form.window().findChildren(QtWidgets.QDialogButtonBox)
                    if box.button(QtWidgets.QDialogButtonBox.Apply) is not None), None)
        check(label + "_native_apply_ok_disabled", box is not None
              and not box.button(QtWidgets.QDialogButtonBox.Apply).isEnabled()
              and not box.button(QtWidgets.QDialogButtonBox.Ok).isEnabled())
        if label == "C":
            panel.form.grab().save(str(output / "C_conflict_panel.png"))
            Gui.activeDocument().activeView().saveImage(str(output / "C_current_document.png"), 900, 650, "Current")
        check(label + "_apply_blocked", not panel.apply() and not panel.session.closed)
        check(label + "_document_unchanged_by_detection",
              snapshot(label + "_after_detection", document, owner_name, panel) == before)

    def cancel(label, document, owner_name, panel):
        before = snapshot(label + "_before_cancel", document, owner_name, panel)
        check(label + "_cancel_success", panel.reject())
        QtWidgets.QApplication.processEvents()
        after = snapshot(label + "_after_cancel", document, owner_name, panel)
        check(label + "_cancel_preserves_configuration_state_and_history", after == before)
        check(label + "_resources_released", panel.session.closed and panel._closed
              and panel.controller._preview is None and not panel.controller._point_callbacks
              and panel.controller._view is None and not panel.controller._gusset_visibility
              and controllers._active_panel is None)

    # A: applied Pratt -> remove a diagonal in Editar Alma -> Apply -> native Undo.
    document = new_document("ABC")
    panel, owner_name, pratt = create("A_create_pratt", document)
    edge = next(edge for edge in panel.controller.last_candidate.graph.edges
                if edge.role == "DIAGONAL")
    edit_web("A_remove_diagonal", document, panel, "remove_edge", key=edge.key)
    custom = effective_apply("A_apply_custom", document, panel)
    check("A_custom_exact_graph_saved", custom["requested"]["topology_mode"] == "Custom"
          and not any(value["key"] == edge.key
                      for value in decode_state(custom["applied_state"])["candidate"]["graph"]["edges"]))
    panel._update_preview3d()
    check("A_coin_present_before_undo", panel.controller._preview is not None)
    native_history(document, "Std_Undo")
    restored = snapshot("A_native_undo", document, owner_name, panel)
    check("A_undo_recovers_exact_pratt", same_realization(restored, pratt)
          and restored["undo_count"] == custom["undo_count"] - 1
          and restored["redo_count"] == custom["redo_count"] + 1)
    conflict("A", document, owner_name, panel)
    native_history(document, "Std_Redo")
    check("B_same_open_session_redo_recovers_custom",same_realization(
        snapshot("B_same_session_redo", document, owner_name, panel),custom))
    check("B_same_session_conflict_remains_blocked",not panel.apply() and panel.session.conflict_reason)
    native_history(document, "Std_Undo")
    cancel("A", document, owner_name, panel)

    # B: reopening restored Pratt does not authorize overwriting a native Redo.
    panel = open_panel(document, document.getObject(owner_name))
    panel._update_preview3d()
    check("B_coin_present_before_redo", panel.controller._preview is not None)
    before_redo = snapshot("B_before_redo", document, owner_name, panel)
    native_history(document, "Std_Redo")
    restored = snapshot("B_native_redo", document, owner_name, panel)
    check("B_redo_recovers_exact_custom", same_realization(restored, custom)
          and restored["undo_count"] == before_redo["undo_count"] + 1
          and restored["redo_count"] == before_redo["redo_count"] - 1)
    conflict("B", document, owner_name, panel)
    cancel("B", document, owner_name, panel)

    # C: an unapplied Custom diagonal is not part of native document history.
    panel = open_panel(document, document.getObject(owner_name))
    check("C_reopens_exact_custom", panel.session.config["custom_topology"]
          == custom["requested"]["custom_topology"])
    edit_web("C_add_draft_diagonal", document, panel, "add_edge",
             start=edge.start_node_key, end=edge.end_node_key)
    panel._update_preview3d()
    check("C_coin_present_before_undo", panel.controller._preview is not None)
    before_undo = snapshot("C_before_undo", document, owner_name, panel)
    native_history(document, "Std_Undo")
    restored = snapshot("C_native_undo", document, owner_name, panel)
    check("C_undo_targets_last_native_apply", same_realization(restored, pratt)
          and restored["undo_count"] == before_undo["undo_count"] - 1
          and restored["redo_count"] == before_undo["redo_count"] + 1)
    conflict("C", document, owner_name, panel)
    cancel("C", document, owner_name, panel)
    native_history(document, "Std_Redo")
    check("C_redo_after_cancel_recovers_custom", same_realization(
        snapshot("C_redo_after_cancel", document, owner_name), custom))
    App.closeDocument(document.Name)

    # D: multiple Apply records; Undo followed by Cancel preserves the native result.
    document = new_document("D")
    panel, owner_name, _ = create("D_create", document)
    panel.height.setValue(1200.)
    settle(panel)
    height_1200 = effective_apply("D_apply_1200", document, panel)
    panel.height.setValue(1400.)
    settle(panel)
    height_1400 = effective_apply("D_apply_1400", document, panel)
    panel.height.setValue(1600.)
    settle(panel)
    panel._update_preview3d()
    native_history(document, "Std_Undo")
    restored = snapshot("D_native_undo", document, owner_name, panel)
    check("D_undo_recovers_1200", same_realization(restored, height_1200)
          and restored["undo_count"] == height_1400["undo_count"] - 1
          and restored["redo_count"] == height_1400["redo_count"] + 1)
    conflict("D", document, owner_name, panel)
    cancel("D", document, owner_name, panel)
    App.closeDocument(document.Name)

    # E: Undo creation removes the owner; Apply must not silently recreate it.
    document = new_document("E")
    panel, owner_name, created = create("E_create", document)
    panel.height.setValue(1200.)
    settle(panel)
    panel._update_preview3d()
    native_history(document, "Std_Undo")
    removed = snapshot("E_native_undo_creation", document, owner_name, panel)
    check("E_owner_and_children_removed", not removed["owner_exists"] and not removed["objects"]
          and removed["undo_count"] == created["undo_count"] - 1
          and removed["redo_count"] == created["redo_count"] + 1)
    conflict("E", document, owner_name, panel)
    cancel("E", document, owner_name, panel)
    App.closeDocument(document.Name)

    # F: a native property edit can change the request without changing AppliedState.
    document = new_document("F")
    panel, owner_name, initial = create("F_create", document)
    panel.height.setValue(1400.)
    settle(panel)
    panel._update_preview3d()
    document.openTransaction("External height edit during truss session")
    try:
        document.getObject(owner_name).Height = 900.
        document.commitTransaction()
    except Exception:
        document.abortTransaction()
        raise
    external = snapshot("F_external_property", document, owner_name, panel)
    check("F_requested_and_realized_remain_distinct", external["requested"]["height"] == 900.
          and external["applied_state"] == initial["applied_state"]
          and panel.session.config["height"] == 1400.
          and external["undo_count"] == initial["undo_count"] + 1)
    conflict("F", document, owner_name, panel)
    cancel("F", document, owner_name, panel)
    App.closeDocument(document.Name)
    return dict(ok=True, version=App.Version()[:3], checks=checks,
                snapshots=str(output / "snapshots.json"))


if os.environ.get("SS_DUOPITCH_ROOT"):
    import FreeCAD as App
    from PySide import QtCore, QtWidgets
    root = Path(os.environ["SS_DUOPITCH_ROOT"])
    out = Path(os.environ["SS_DUOPITCH_OUT"])
    sys.path.insert(0, str(root))
    import freecad
    freecad.__path__.insert(0, str(root / "freecad"))

    def launch():
        try:
            result = run(out)
        except Exception:
            result = dict(ok=False, error=traceback.format_exc())
            App.Console.PrintError(result["error"])
        (out / "result.json").write_text(json.dumps(result, indent=2))
        for name in tuple(App.listDocuments()):
            App.closeDocument(name)
        QtCore.QTimer.singleShot(0, QtWidgets.QApplication.quit)

    QtCore.QTimer.singleShot(500, launch)
