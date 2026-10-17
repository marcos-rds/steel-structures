"""Actual modal action and current-quantity gate in isolated FreeCAD 1.1.4."""
from copy import deepcopy
import json
import os
from pathlib import Path
import sys
import traceback


def run(output):
    import FreeCAD as App
    import FreeCADGui as Gui
    import DraftTools
    import Part
    import shiboken6
    from PySide import QtCore,QtGui,QtWidgets
    from PySide6 import QtTest
    from freecad.SteelStructures import truss
    from freecad.SteelStructures.interactive import truss_controller as controllers
    from freecad.SteelStructures.trusses.assemblies import configure_assembly
    from freecad.SteelStructures.trusses.interconnector_options import default_connector
    from freecad.SteelStructures.trusses.physical_mass import read_physical_mass
    qss=os.environ.get("SS_TRUSS_EDITOR_QSS")
    if qss:
        path=Path(qss)
        QtCore.QDir.addSearchPath("qss",str(path.parent))
        QtWidgets.QApplication.instance().setStyleSheet(path.read_text(encoding="utf8"))
    checks,errors=[],[]
    old_hook=sys.excepthook
    def qt_error(kind,error,trace):
        errors.append("".join(traceback.format_exception(kind,error,trace)))
        (output/"qt_errors.txt").write_text("\n".join(errors))
    sys.excepthook=qt_error
    def check(name,condition):
        if not condition: raise AssertionError(name)
        checks.append(name)
        (output/"checks.json").write_text(json.dumps(checks,indent=2))
    def drain():
        QtWidgets.QApplication.processEvents()
        QtCore.QCoreApplication.sendPostedEvents(None,QtCore.QEvent.DeferredDelete)
    def settle(panel):
        drain()
        if not panel._closed: panel._preview_timer.stop()
    def open_panel(document,owner=None):
        panel=controllers.open_truss_panel(document,owner)
        settle(panel)
        return panel
    def modal(label,panel,action):
        failures,held=[],[]
        def callback():
            editor=panel._topology_editor
            try:
                held.extend((editor,editor.canvas))
                check(label+"_actual_modal",editor.isModal())
                panel._preview_timer.stop()
                action(editor)
            except Exception:
                if editor is not None and shiboken6.isValid(editor):
                    editor.grab().save(str(output/(label+"_failure.png")))
                failures.append(traceback.format_exc())
            finally:
                if editor is not None and shiboken6.isValid(editor) and editor.isVisible(): editor.reject()
        QtCore.QTimer.singleShot(0,callback)
        (output/(label+"_before.json")).write_text(json.dumps(dict(valid=panel._valid,session_valid=panel.session.valid,
            conflict=panel.session.conflict_reason,enabled=panel.editor_button.isEnabled(),closed=panel._closed,
            message=panel.message.text()),indent=2))
        panel.editor_button.click()
        drain()
        if failures: raise AssertionError("\n".join(failures))
        check(label+"_modal_released",held and all(not shiboken6.isValid(widget) for widget in held)
              and panel._topology_editor is None)
        check(label+"_no_qt_callback_errors",not errors)
    def current(editor,label):
        fields=editor.fields
        check(label+"_current_mass",fields.mass_status.isHidden()
              and fields.information_values["mass"].text().endswith(" kg")
              and fields.information_values["linear_mass"].text().endswith(" kg/m"))
    def pending(editor,label):
        fields=editor.fields
        check(label+"_pending_mass",fields.mass_status.text()=="Aguardando aplicação"
              and all(fields.information_values[key].text()=="—" for key in ("mass","linear_mass")))
    doc=App.newDocument("ModalEditorActions")
    doc.UndoMode=1
    class Observer:
        count=0
        def slotRecomputedDocument(self,document):
            if document is doc: self.count+=1
    observer=Observer()
    App.addDocumentObserver(observer)
    try:
        # New owner, repeated Apply, native focus/partial entry, terminal Cancel.
        panel=open_panel(doc)
        panel.span.setValue(2400.)
        panel.height.setValue(1000.)
        panel.panel_count.setValue(6)
        settle(panel)
        def create(editor):
            pending(editor,"new")
            before=(doc.UndoCount,observer.count)
            editor.apply_button.click()
            current(editor,"new_after_apply")
            owner=panel.session.owner
            check("new_apply_keeps_editor_session",owner is not None and not panel._closed and editor.isVisible()
                  and (doc.UndoCount,observer.count)==(before[0]+1,before[1]+1))
            before=(doc.UndoCount,observer.count)
            for _ in range(3): editor.apply_button.click()
            check("repeat_apply_no_transaction_recompute",before==(doc.UndoCount,observer.count)
                  and panel.session.owner is owner)
            controls=editor.fields.controls
            controls["height"].setValue(1100.)
            pending(editor,"geometry_edit")
            editor.apply_button.click()
            current(editor,"geometry_applied")
            check("same_owner_multiple_apply",panel.session.owner is owner and owner.Height.Value==1100.)
            # Selection, tabs, focus, pan and color cannot hide confirmed mass.
            candidate=panel.session.validated_candidate
            node=candidate.graph.nodes[0].key
            editor.select_node(node)
            editor.tabs.setCurrentIndex(1)
            editor.tabs.setCurrentIndex(0)
            editor.canvas.horizontalScrollBar().setValue(1)
            controls["height"].setFocus()
            editor.fields.sync()
            current(editor,"navigation_focus")
            color=deepcopy(panel.session.config["role_specs"])
            panel.session.config["role_specs"]["TOP_CHORD"]["color"]=[.2,.3,.4]
            panel._refresh()
            current(editor,"color_only")
            panel.session.config["role_specs"]=color
            panel._refresh()
            check("mass_labels_bold_values_normal",editor.fields.mass_information.labels["mass"].font().bold()
                  and not editor.fields.information_values["mass"].font().bold()
                  and editor.fields.information_values["mass"].font().pointSizeF()==editor.fields.information_values["nodes"].font().pointSizeF())
            check("units_only_in_values",[label.text() for label in editor.fields.mass_information.labels.values()]==["Peso total:","Peso linear:"])
            drain()
            check("three_actions_native_order",editor.cancel_button.x()<editor.apply_button.x()<editor.ok_button.x()
                  and not hasattr(editor,"back_button")
                  and editor.apply_button.x()-editor.cancel_button.geometry().right()
                      >editor.ok_button.x()-editor.apply_button.geometry().right())
            check("snapshot_reference_summary_removed",editor.fields.reference_summary.isHidden()
                  and not editor.fields.reference_summary.text())
            for width,height in ((1100,850),(620,480)):
                editor.resize(width,height)
                drain()
                check("all_actions_fit_"+str(width),all(editor.rect().contains(QtCore.QRect(button.mapTo(editor,QtCore.QPoint()),button.size()))
                    for button in (editor.cancel_button,editor.apply_button,editor.ok_button)))
                editor.grab().save(str(output/("modal_actions_"+str(width)+".png")))
            editor.resize(1100,850)
            # Apply cannot accept an unconfirmed invalid mirror field.
            spin=controls["height"]
            QtWidgets.QApplication.setActiveWindow(editor)
            spin.setFocus()
            spin.lineEdit().selectAll()
            QtTest.QTest.keyClicks(spin,"1e")
            before=(owner.AppliedState,doc.UndoCount,observer.count)
            editor.apply_button.click()
            check("invalid_editor_apply_stays_modal",editor.isVisible() and not panel._closed and spin.lineEdit().text()=="1e"
                  and before==(owner.AppliedState,doc.UndoCount,observer.count))
            QtTest.QTest.keyClick(spin,QtCore.Qt.Key_Escape)
            current(editor,"invalid_input_repaired")
            # Confirming a second spacing must not throw from a Qt slot while
            # the first spacing is still incomplete.
            controls["driver"].setCurrentIndex(controls["driver"].findData("CustomSpacingList"))
            spacing=editor.fields.spacing_editor
            original_spacings=spacing.values()
            first,second=spacing._spins[:2]
            first.setFocus()
            first.lineEdit().selectAll()
            QtTest.QTest.keyClicks(first,"1e")
            second.setFocus()
            second.lineEdit().selectAll()
            QtTest.QTest.keyClicks(second,"399.9 mm")
            QtTest.QTest.keyClick(second,QtCore.Qt.Key_Return)
            check("multiple_spacing_edits_have_no_callback_error",not errors and first.lineEdit().text()=="1e")
            first.setFocus()
            QtTest.QTest.keyClick(first,QtCore.Qt.Key_Escape)
            spacing.set_values(original_spacings)
            controls["driver"].setCurrentIndex(controls["driver"].findData("ByPanelCount"))
            current(editor,"spacings_repaired")
            controls["height"].setValue(1300.)
            pending(editor,"draft_before_cancel")
            editor.cancel_button.click()
        modal("new_apply_cancel",panel,create)
        owner=panel.session.owner
        (output/"after_cancel.json").write_text(json.dumps(dict(height=owner.Height.Value,closed=panel._closed,
            session_closed=panel.session.closed,controller_closed=panel.controller.closed,
            active_panel=controllers._active_panel is None,active_dialog=repr(Gui.Control.activeDialog()),
            callbacks=bool(panel.controller._point_callbacks),preview=repr(panel.controller._preview)),indent=2))
        check("cancel_after_apply_preserves_document",owner.Height.Value==1100. and not panel._closed
              and not panel.session.closed and not panel.controller.closed and Gui.Control.activeDialog()
              and panel.session.config["height"]==1100. and panel.height.value()==1100.)
        # The opening checkpoint includes a preexisting unapplied TaskPanel draft.
        panel.height.setValue(1200.)
        identity=panel.session.identity
        before=(doc.UndoCount,observer.count)
        def cancel_changed(editor):
            editor.fields.controls["height"].setValue(1300.)
            pending(editor,"cancel_changed")
            info=editor.fields.mass_information
            for width in (1100,620):
                editor.resize(width,650)
                drain()
                editor.fields.geometry_scroll.ensureWidgetVisible(info.status_box,0,0)
                drain()
                editor.grab().save(str(output/("pending_"+str(width)+".png")))
                editor.fields.information_box.grab().save(str(output/("pending_information_"+str(width)+".png")))
                check("pending_clock_visible_"+str(width),info.clock.isVisible() and info.status.isVisible())
                values=info.values
                box=info.status_box.geometry()
                check("pending_status_no_overlap_"+str(width),all(not box.intersects(value.geometry()) for value in values.values()))
                if not info._below:
                    check("pending_status_centered",abs(box.center().y()-(values["mass"].geometry().top()+values["linear_mass"].geometry().bottom())/2)<3)
            editor.cancel_button.click()
        modal("cancel_changed",panel,cancel_changed)
        check("cancel_preserves_preopening_draft",not panel._closed and panel.session.identity==identity
              and panel.session.config["height"]==1200. and panel.height.value()==1200. and owner.Height.Value==1100.
              and before==(doc.UndoCount,observer.count))
        def x_changed(editor):
            editor.fields.controls["height"].setValue(1400.)
            editor.close()
        modal("window_x",panel,x_changed)
        check("x_is_cancel",not panel._closed and panel.session.config["height"]==1200. and panel.height.value()==1200.)
        for i in range(2): modal("reopen_"+str(i),panel,lambda editor:editor.cancel_button.click())
        def ok(editor): editor.ok_button.click()
        before=(doc.UndoCount,observer.count)
        modal("ok_pending",panel,ok)
        check("ok_applies_only_editor_closes",owner.Height.Value==1200. and not panel._closed and not panel.session.closed
              and (doc.UndoCount,observer.count)==(before[0]+1,before[1]+1))
        before=(doc.UndoCount,observer.count)
        modal("ok_clean",panel,ok)
        check("ok_clean_no_transaction_recompute",before==(doc.UndoCount,observer.count) and not panel._closed)
        panel.reject()
        panel=open_panel(doc)
        panel.span.setValue(2400.)
        panel.height.setValue(1000.)
        modal("new_ok",panel,ok)
        check("new_ok_materializes_owner",not panel._closed and panel.session.owner is not None)
        panel.reject()
        count=len(doc.Objects)
        panel=open_panel(doc)
        modal("new_cancel",panel,lambda editor:editor.cancel_button.click())
        check("new_cancel_leaves_no_objects",not panel._closed and panel.session.owner is None and len(doc.Objects)==count)
        panel.reject()
        # Composite, Gusset, Custom and rollback inside the real modal.
        cfg=truss.default_config()
        cfg.update(span=2400.,end=[2400.,0.,0.],height=1000.,panel_count=6)
        cfg["role_specs"]["TOP_CHORD"]=configure_assembly(cfg["role_specs"]["TOP_CHORD"],"SpacedPair",240.,
            interconnectors=(default_connector("Battens"),))
        cfg["connection_intents"]={"B_S_MAIN_1_3":dict(form="Gusset",gusset=dict(plate_thickness=12.))}
        composite=truss.apply_truss(doc,cfg)
        panel=open_panel(doc,composite)
        def advanced(editor):
            current(editor,"composite_initial")
            editor.select_node("B_S_MAIN_1_3")
            editor.gusset_margin.setValue(editor.gusset_margin.value()+5.)
            pending(editor,"gusset_margin")
            editor.apply_button.click()
            current(editor,"gusset_applied")
            check("gusset_and_connectors_survive",len(composite.GeneratedGussetPlates)==1
                  and any(child.AssemblyElementKind=="Interconnector" for child in composite.GeneratedMembers))
            panel.session.config["role_specs"]["TOP_CHORD"]=configure_assembly(
                panel.session.config["role_specs"]["TOP_CHORD"],"SpacedPair",260.,
                interconnectors=(default_connector("Battens"),))
            panel._refresh()
            pending(editor,"composition_changed")
            editor.apply_button.click()
            current(editor,"composition_applied")
            check("composition_edit_keeps_owner_and_gusset",panel.session.owner is composite
                  and len(composite.GeneratedGussetPlates)==1)
            # Failed physical calculation is distinct from a draft.
            child=composite.GeneratedMembers[0]
            original=child.Shape.copy()
            child.Shape=Part.Shape()
            child.purgeTouched()
            editor.fields.sync()
            check("calculation_failure_is_unavailable",editor.fields.information_values["mass"].text()=="Indisponível"
                  and editor.fields.mass_status.isHidden() and "Shape" in editor.fields.information_values["mass"].toolTip())
            editor.fields.controls["height"].setValue(1020.)
            check("failure_not_hidden_by_pending_draft",editor.fields.information_values["mass"].text()=="Indisponível")
            editor.fields.controls["height"].setValue(1000.)
            child.Shape=original
            child.purgeTouched()
            current_mass=read_physical_mass(composite).mass_kg
            editor.fields.sync()
            current(editor,"physical_repaired")
            # Actual apply failure rolls back, keeps modal and permits retry.
            editor.fields.controls["height"].setValue(1150.)
            before=(composite.AppliedState,doc.UndoCount,observer.count)
            original_apply=truss.apply_result
            attempts=[]
            def fail(*args,**kwargs):
                attempts.append(1)
                if len(attempts)==2: raise ValueError("Injected modal apply failure")
                return original_apply(*args,**kwargs)
            truss.apply_result=fail
            try: editor.ok_button.click()
            finally: truss.apply_result=original_apply
            check("failed_ok_keeps_modal_and_rolls_back",editor.isVisible() and not panel._closed
                  and composite.AppliedState==before[0] and doc.UndoCount==before[1])
            editor.apply_button.click()
            current(editor,"retry_applied")
            check("retry_updates_mass",read_physical_mass(composite).mass_kg!=current_mass)
            edge=next(edge for edge in panel.session.validated_candidate.graph.edges if edge.role=="DIAGONAL")
            panel.apply_topology_edit("remove_edge",key=edge.key)
            pending(editor,"custom_edit")
            editor.apply_button.click()
            current(editor,"custom_applied")
            check("custom_same_owner",panel.session.owner is composite and composite.TopologyMode=="Custom")
            editor.cancel_button.click()
        modal("advanced",panel,advanced)
        # Capture a complete, already-Custom draft with composite profiles and
        # a Gusset, then mutate nested structures and the reconciliation graph.
        panel.session.config["role_specs"]["TOP_CHORD"]=configure_assembly(
            panel.session.config["role_specs"]["TOP_CHORD"],"SpacedPair",280.,
            interconnectors=(default_connector("Battens"),))
        panel._refresh()
        draft=deepcopy(panel.session.config)
        history=deepcopy(panel.controller.last_candidate.config)
        realized=(composite.AppliedState,doc.UndoCount,observer.count)
        baseline=deepcopy(panel.session._baseline)
        def nested_cancel(editor):
            panel.session.config["role_specs"]["TOP_CHORD"]["color"]=[.8,.2,.1]
            panel.session.config["role_specs"]["TOP_CHORD"]=configure_assembly(
                panel.session.config["role_specs"]["TOP_CHORD"],"SpacedPair",320.,
                interconnectors=(default_connector("Battens"),))
            editor.select_node("B_S_MAIN_1_3")
            editor.gusset_margin.setValue(editor.gusset_margin.value()+7.)
            edge=next(edge for edge in panel.session.validated_candidate.graph.edges if edge.role=="DIAGONAL")
            panel.apply_topology_edit("remove_edge",key=edge.key)
            editor.fields.controls["height"].setValue(1230.)
            editor.cancel_button.click()
        modal("nested_cancel",panel,nested_cancel)
        check("deep_checkpoint_restores_custom_composite_gusset",panel.session.config==draft
              and panel.controller.last_candidate.config==history and panel.session._baseline==baseline
              and realized==(composite.AppliedState,doc.UndoCount,observer.count) and not panel._closed)
        panel.reject()
        # An incomplete TaskPanel edit is a valid opening checkpoint too.
        panel=open_panel(doc,composite)
        panel.height.lineEdit().setText("1e")
        panel.height.lineEdit().setModified(True)
        panel._refresh()
        def partial(editor):
            (output/"partial_state.json").write_text(json.dumps(dict(valid=panel._valid,source=panel.height.lineEdit().text(),
                source_modified=panel.height.lineEdit().isModified(),mirror=editor.fields.controls["height"].lineEdit().text(),
                message=panel.message.text()),indent=2))
            check("partial_open_is_repairable",not panel._valid and panel.height.lineEdit().text()=="1e")
            editor.fields.controls["height"].setValue(1350.)
            editor.close()
        modal("partial_open",panel,partial)
        check("cancel_restores_partial_taskpanel",panel.height.lineEdit().text()=="1e"
              and panel.height.lineEdit().isModified() and not panel._valid and not panel._closed)
        panel.reject()
        panel=open_panel(doc,composite)
        panel.driver.setCurrentIndex(panel.driver.findData("CustomSpacingList"))
        panel.spacing_editor._spins[0].lineEdit().setText("1e")
        panel.spacing_editor._spins[0].lineEdit().setModified(True)
        panel._refresh()
        before_partial=(composite.AppliedState,doc.UndoCount,observer.count)
        for action in ("cancel","x"):
            def partial_spacing(editor):
                check("partial_spacing_repairable_"+action,not panel._valid and editor.isVisible())
                editor.fields.controls["height"].setValue(1360.)
                if action=="cancel": editor.cancel_button.click()
                else: editor.close()
            modal("partial_spacing_"+action,panel,partial_spacing)
            first=panel.spacing_editor._spins[0]
            check("partial_spacing_restored_"+action,first.lineEdit().text()=="1e" and first.lineEdit().isModified()
                  and not panel._valid and not panel._closed
                  and before_partial==(composite.AppliedState,doc.UndoCount,observer.count))
        panel.reject()
        applied_mass=read_physical_mass(composite).mass_kg
        doc.undo()
        doc.recompute()
        check("native_undo_restores_other_mass",read_physical_mass(composite).available and read_physical_mass(composite).mass_kg!=applied_mass)
        doc.redo()
        doc.recompute()
        check("native_redo_restores_applied_mass",abs(read_physical_mass(composite).mass_kg-applied_mass)<1e-8)
        panel=open_panel(doc,composite)
        def conflict(editor):
            doc.undo()
            before=(doc.UndoCount,observer.count)
            editor.apply_button.click()
            check("external_undo_conflict_keeps_editor",panel.session.conflict_reason and editor.isVisible()
                  and before==(doc.UndoCount,observer.count))
            check("conflict_mass_unavailable",editor.fields.information_values["mass"].text()=="Indisponível")
            editor.cancel_button.click()
        modal("external_conflict",panel,conflict)
        check("cancel_preserves_conflict_and_panel",not panel._closed and bool(panel.session.conflict_reason) and not panel._valid)
        panel.reject()
        # A linked Draft source may move without changing owner properties.
        # Cancel must detect that external input, not reinstate old coordinates.
        import Draft
        line=Draft.make_line(App.Vector(0,0,0),App.Vector(2400,0,0))
        doc.recompute()
        cfg=truss.default_config()
        cfg.update(span=2400.,end=[2400.,0.,0.],height=1000.,reference_mode="DraftLine",
                   reference_source=line.Name,reference_edge="Edge1",reference_linked=True)
        linked=truss.apply_truss(doc,cfg)
        panel=open_panel(doc,linked)
        before_link=(linked.AppliedState,doc.UndoCount,observer.count)
        def source_changed(editor):
            editor.fields.controls["height"].setValue(1200.)
            line.Start=App.Vector(40,0,0)
            line.End=App.Vector(2440,0,0)
            editor.close()
        modal("external_source",panel,source_changed)
        (output/"external_source_state.json").write_text(json.dumps(dict(closed=panel._closed,conflict=panel.session.conflict_reason,
            valid=panel._valid,height=panel.session.config["height"],before=before_link,
            after=(linked.AppliedState,doc.UndoCount,observer.count),x=line.Start.x),indent=2))
        check("cancel_does_not_overwrite_external_source",not panel._closed and bool(panel.session.conflict_reason)
              and not panel._valid and panel.session.config["height"]==1200.
              and before_link==(linked.AppliedState,doc.UndoCount,observer.count) and line.Start.x==40.)
        panel.reject()
        # A switch leaves the panel/draft; closure or Draft handoff ends them.
        panel=open_panel(doc,owner)
        other=App.newDocument("ModalEditorOther")
        App.setActiveDocument(doc.Name)
        modal("document_switch",panel,lambda editor:App.setActiveDocument(other.Name))
        check("switch_preserves_session",not panel._closed)
        App.setActiveDocument(doc.Name)
        panel.reject()
        App.closeDocument(other.Name)
        panel=open_panel(doc,owner)
        def working_plane(editor):
            from draftguitools.gui_selectplane import Draft_SelectPlane
            Draft_SelectPlane().Activated()
        modal("working_plane",panel,working_plane)
        check("working_plane_releases_editor_panel",panel._closed and controllers._active_panel is None
              and panel.controller._preview is None and not panel.controller._point_callbacks)
        command=getattr(App,"activeDraftCommand",None)
        if command is not None: command.finish()
        panel=open_panel(doc,owner)
        modal("document_close",panel,lambda editor:App.closeDocument(doc.Name))
        check("document_close_releases_session",panel._closed and panel.session.closed and controllers._active_panel is None)
        check("no_qt_callbacks_or_editor",not errors and not any(widget.windowTitle()=="Editor de Treliças" for widget in QtWidgets.QApplication.topLevelWidgets()))
        return dict(ok=True,version=App.Version()[:3],checks=checks)
    finally:
        App.removeDocumentObserver(observer)
        sys.excepthook=old_hook


if os.environ.get("SS_DUOPITCH_ROOT"):
    import FreeCAD as App
    from PySide import QtCore,QtWidgets
    root=Path(os.environ["SS_DUOPITCH_ROOT"])
    out=Path(os.environ["SS_DUOPITCH_OUT"])
    sys.path.insert(0,str(root))
    import freecad
    freecad.__path__.insert(0,str(root/"freecad"))
    def launch():
        try: result=run(out)
        except Exception:
            result=dict(ok=False,error=traceback.format_exc())
            App.Console.PrintError(result["error"])
        (out/"result.json").write_text(json.dumps(result,indent=2))
        for name in tuple(App.listDocuments()): App.closeDocument(name)
        QtCore.QTimer.singleShot(0,QtWidgets.QApplication.quit)
    QtCore.QTimer.singleShot(500,launch)
