"""Native single-line handoff, same truss session, and independent Draft Undo."""
from copy import deepcopy
import json
import os
from pathlib import Path
import sys
import traceback


def run(out):
    import FreeCAD as App
    import FreeCADGui as Gui
    import DraftTools
    import shiboken6
    from PySide import QtCore, QtWidgets
    from PySide6 import QtTest
    from freecad.SteelStructures.interactive import truss_controller as host
    from freecad.SteelStructures.interactive import truss_draft_reference as bridge
    import freecad.SteelStructures.init_gui
    Gui.activateWorkbench('SteelStructuresWorkbench')
    Gui.getMainWindow().show()
    Gui.Control.showTaskView()
    qss=os.environ.get('SS_TRUSS_EDITOR_QSS')
    if qss:
        path=Path(qss)
        QtCore.QDir.addSearchPath('qss',str(path.parent))
        QtWidgets.QApplication.instance().setStyleSheet(path.read_text(encoding='utf8'))
    checks,errors=[],[]
    old_hook=sys.excepthook
    def hook(kind,error,trace):
        errors.append(''.join(traceback.format_exception(kind,error,trace)))
        (out/'qt_errors.txt').write_text('\n'.join(errors),encoding='utf8')
    sys.excepthook=hook
    def check(name,value):
        if not value: raise AssertionError(name)
        checks.append(name)
        (out/'checks.json').write_text(json.dumps(checks,indent=2))
    def pump():
        for _ in range(8): QtWidgets.QApplication.processEvents()
        QtTest.QTest.qWait(40)
        QtCore.QCoreApplication.sendPostedEvents(None,QtCore.QEvent.DeferredDelete)
        if errors: raise AssertionError('\n'.join(errors))
    def panel():
        current=host._active_panel
        check('task_restored',current is not None and not current._closed and current.form is not None)
        current._preview_timer.stop()
        return current
    def begin(current,label):
        current.reference_mode.setCurrentIndex(current.reference_mode.findData('DraftLine'))
        pump()
        check(label+'_draft_actions_visible',current.draft_reference_actions.isVisible()
              and current.draw_reference_button.isVisible() and current.select_reference_button.isVisible()
              and not current.pick_button.isVisible())
        old_form=current.form
        previous_names={obj.Name for obj in current.document.Objects}
        current.draw_reference_button.click()
        pump()
        Gui.getMainWindow().grab().save(str(out/(label+'_native.png')))
        check(label+'_native_line_instance',isinstance(App.activeDraftCommand,bridge.ReferenceLine))
        check(label+'_old_widgets_destroyed',not shiboken6.isValid(old_form))
        check(label+'_session_suspended',not current.session.closed and current._suspended
              and current.controller._preview is None and not current.controller._point_callbacks
              and current._reference_source_observer.closed)
        tool=App.activeDraftCommand
        tool.previous_names=previous_names
        return tool
    def numeric(tool,point):
        ui=tool.ui
        QtWidgets.QApplication.setActiveWindow(Gui.getMainWindow())
        ui.isGlobal.setChecked(True)
        ui.isRelative.setChecked(False)
        for field,value in zip((ui.xValue,ui.yValue,ui.zValue),point):
            field.setFocus()
            field.setText(QtCore.QLocale().toString(float(value),'g',17)+' mm')
        pump()
        check('native_inputs_visible',ui.xValue.isVisible() and ui.pointButton.isVisible())
        ui.pointButton.click()
        pump()
    try:
        doc=App.newDocument('TrussDirectDraftReference')
        current=host.open_truss_panel(doc)
        pump()
        current._preview_timer.stop()
        check('two_points_only_original_action',current.reference_mode.currentData()=='TwoPoints'
              and current.pick_button.isVisible() and current.pick_button.text()=='Selecionar dois pontos'
              and not current.draft_reference_actions.isVisible() and not current.source_label.isVisible())
        check('alignment_is_only_chord_selector',current.reference_alignment_label.text()=='Banzo de referência'
              and not current.quick_controls.isAncestorOf(current.draw_reference_button))
        session=current.session
        baseline=session.baseline_config
        current.reference_mode.setCurrentIndex(current.reference_mode.findData('DraftLine'))
        pump()
        check('draft_without_source_is_discreet',current.source_label.text()=='Nenhuma linha selecionada')
        before_cancel=deepcopy(current.get_config())
        tool=begin(current,'empty_cancel')
        tool.ui.xValue.setFocus()
        QtTest.QTest.keyClick(tool.ui.xValue,QtCore.Qt.Key_Escape)
        pump()
        current=panel()
        check('empty_cancel_restores_mode_and_source',current.get_config()==before_cancel
              and current.reference_mode.currentData()=='DraftLine' and current.session is session)
        import Draft
        existing=Draft.make_line(App.Vector(0,0,0),App.Vector(10000,0,0))
        existing.Label='Eixo existente'
        doc.recompute()
        Gui.Selection.clearSelection()
        Gui.Selection.addSelection(existing)
        current.select_reference_button.click()
        current.keep_reference_link.setChecked(True)
        pump()
        check('existing_selection_reuses_source',current.get_config()['reference_source']==existing.Name
              and current.reference_mode.currentData()=='DraftLine' and current.get_config()['reference_linked'])
        check('existing_selection_caption',current.source_label.text()=='Referência selecionada: Eixo existente')
        existing.Label='Eixo renomeado'
        pump()
        check('label_updates_without_refresh',current.source_label.text()=='Referência selecionada: Eixo renomeado')
        current.reference_mode.setCurrentIndex(current.reference_mode.findData('TwoPoints'))
        pump()
        check('manual_mode_change_keeps_draft_object',doc.getObject(existing.Name) is existing
              and not current.draft_reference_actions.isVisible() and current.pick_button.isVisible())
        current.reference_mode.setCurrentIndex(current.reference_mode.findData('DraftLine'))
        Gui.Selection.clearSelection()
        Gui.Selection.addSelection(existing)
        current.select_reference_button.click()
        current.keep_reference_link.setChecked(True)
        pump()
        current.height.setValue(1375.125678)
        from freecad.SteelStructures.trusses.assemblies import configure_assembly
        from freecad.SteelStructures.trusses.interconnector_options import default_connector
        current.session.config['role_specs']['TOP_CHORD']=configure_assembly(
            current.session.config['role_specs']['TOP_CHORD'],'SpacedPair',240.,
            interconnectors=(default_connector('Battens'),))
        current.session.config['connection_intents']={'B_S_MAIN_1_3':dict(form='Gusset',gusset=dict(plate_thickness=12.))}
        current._refresh()
        pump()
        snapshot=deepcopy(current.get_config())
        check('compact_button_icon',not current.draw_reference_button.icon().isNull()
              and not current.select_reference_button.icon().isNull())
        check('actions_proportional',0.67 <= current.draw_reference_button.width()/current.select_reference_button.width() <= 1.5
              and current.draw_reference_button.height()==current.select_reference_button.height())
        current.form.grab().save(str(out/'compact.png'))
        tool=begin(current,'new')
        numeric(tool,(100,200,0))
        numeric(tool,(10100,200,0))
        (out/'completion_state.json').write_text(json.dumps(dict(
            finishing=tool.finishing,completed=tool.operation.completed,abandoned=tool.operation.abandoned,
            panel_closed=current._closed,session_closed=session.closed,
            active_command=type(App.activeDraftCommand).__name__,active_task=bool(Gui.Control.activeDialog()),
            active_document_same=App.ActiveDocument is doc,result=str(tool.operation.result),
            nodes=[list(point) for point in tool.node],objects=[obj.Name for obj in doc.Objects]),indent=2))
        current=panel()
        check('created_mode_matches_ui_and_session',current.reference_mode.currentData()=='DraftLine'
              and current.session.config['reference_mode']=='DraftLine' and current.keep_reference_link.isChecked())
        check('same_session_and_baseline',current.session is session and session.baseline_config==baseline)
        check('no_owner_automatically_created',current.controller.object is None)
        source=doc.getObject(current.get_config()['reference_source'])
        source_name=source.Name
        check('exact_native_object',bridge.is_draft_line(source) and current.get_config()['reference_linked'])
        check('created_source_caption',current.source_label.text()=='Referência selecionada: '+source.Label)
        check('coordinates_and_span',current.get_config()['start']==[100,200,0]
              and current.get_config()['end']==[10100,200,0] and abs(current.span.value()-10000)<1e-7)
        check('draft_parameters_preserved',current.get_config()['height']==snapshot['height']
              and current.get_config()['role_specs']==snapshot['role_specs']
              and current.get_config()['connection_intents']==snapshot['connection_intents'])
        check('baseline_still_unapplied',session.baseline_config==baseline and not bridge._operations)
        current.form.grab().save(str(out/'restored.png'))
        Gui.getMainWindow().grab().save(str(out/'restored_window.png'))
        doc.undo()
        pump()
        check('undo_caption_never_stale',current.source_label.text()=='Nenhuma linha selecionada')
        current._refresh()
        check('undo_source_detected',doc.getObject(source_name) is None and not current._valid)
        doc.redo()
        pump()
        check('redo_reference_revalidated',current._refresh())
        source=doc.getObject(source_name)
        check('redo_caption_restored',current.source_label.text()=='Referência selecionada: '+source.Label)
        check('apply_valid',current.apply())
        owner=current.controller.object
        owner_name=owner.Name
        applied=owner.AppliedState
        snapshot=deepcopy(current.get_config())
        tool=begin(current,'existing_cancel')
        numeric(tool,(50,60,0))
        widget=tool.ui.xValue
        widget.setFocus()
        QtTest.QTest.keyClick(widget,QtCore.Qt.Key_Escape)
        pump()
        current=panel()
        check('escape_restores_exact_draft',current.get_config()==snapshot and current.session is session)
        check('escape_keeps_owner_and_applied',current.controller.object is owner and owner.AppliedState==applied)
        check('escape_no_partial_object',{obj.Name for obj in doc.Objects}==tool.previous_names)
        tool=begin(current,'replacement')
        numeric(tool,(0,0,0))
        numeric(tool,(12000,0,0))
        current=panel()
        second=doc.getObject(current.get_config()['reference_source'])
        check('reference_replaced_not_copied',second is not source and bridge.is_draft_line(second))
        check('replacement_caption_and_mode',current.source_label.text()=='Referência selecionada: '+second.Label
              and current.reference_mode.currentData()=='DraftLine')
        check('same_owner_until_apply',current.controller.object is owner and owner.AppliedState==applied)
        check('apply_reuses_owner',current.apply() and current.controller.object.Name==owner_name)
        candidate=current.session.validated_candidate
        edge=next(edge for edge in candidate.graph.edges if edge.role=='BOTTOM_CHORD')
        a,b=(candidate.graph.node(key).position_local for key in (edge.start_node_key,edge.end_node_key))
        current.apply_topology_edit('add_node',point=tuple((x+y)/2 for x,y in zip(a,b)),edge_key=edge.key)
        snapshot=deepcopy(current.get_config())
        check('custom_draft_prepared',snapshot['topology_preset']=='Custom' and bool(snapshot['custom_topology']))
        tool=begin(current,'custom_cancel')
        tool.finish()
        pump()
        current=panel()
        check('custom_composition_gussets_preserved',current.get_config()==snapshot)
        current.reject()
        pump()
        check('generator_cancel_keeps_lines',doc.getObject(second.Name) is second)
        check('no_residual_session_callbacks',host._active_panel is None and not bridge._operations
              and current.controller._preview is None and not current.controller._point_callbacks
              and current._reference_source_observer.closed)
        Gui.Selection.clearSelection()
        current=host.open_truss_panel(doc)
        pump()
        current.envelope_type.setCurrentIndex(current.envelope_type.findData('DuoPitch'))
        current.reference_alignment.setCurrentIndex(current.reference_alignment.findData('TopChordSupports'))
        pump()
        snapshot=deepcopy(current.get_config())
        tool=begin(current,'duopitch_top_inclined')
        numeric(tool,(0,0,0))
        numeric(tool,(8000,0,1000))
        current=panel()
        config=current.get_config()
        check('duopitch_top_and_height_preserved',config['envelope_type']=='DuoPitch'
              and config['reference_alignment']=='TopChordSupports' and config['height']==snapshot['height'])
        check('inclined_line_candidate_valid',current._valid and config['end']==[8000,0,1000])
        current.reject()
        pump()
        current=host.open_truss_panel(doc,owner)
        pump()
        check('existing_owner_mode_and_caption',current.reference_mode.currentData()=='DraftLine'
              and current.source_label.text()=='Referência selecionada: '+second.Label)
        tool=begin(current,'external_close')
        Gui.Control.closeDialog()
        pump()
        check('external_close_does_not_resurrect',host._active_panel is None and not bridge._operations
              and session.closed and App.activeDraftCommand is None)
        current=host.open_truss_panel(doc,owner)
        pump()
        tool=begin(current,'document_switch')
        numeric(tool,(1,2,0))
        other=App.newDocument('TrussReferenceOther')
        pump()
        check('document_switch_cleans_session',host._active_panel is None and not bridge._operations
              and current.session.closed and App.activeDraftCommand is None)
        check('document_switch_no_accidental_line',not other.Objects)
        App.setActiveDocument(doc.Name)
        App.closeDocument(other.Name)
        current=host.open_truss_panel(doc,owner)
        pump()
        tool=begin(current,'queued_switch')
        numeric(tool,(1,2,0))
        # Deliberately switch before Draft's deferred creation queue executes.
        tool.numericInput(15000,2,0)
        other=App.newDocument('TrussReferenceQueuedOther')
        pump()
        check('queued_switch_no_cross_document_line',not other.Objects and not bridge._operations
              and host._active_panel is None and current.session.closed)
        App.setActiveDocument(doc.Name)
        App.closeDocument(other.Name)
        current=host.open_truss_panel(doc,owner)
        pump()
        tool=begin(current,'document_close')
        App.closeDocument(doc.Name)
        pump()
        check('document_close_cleans_session',host._active_panel is None and not bridge._operations
              and current.session.closed and App.activeDraftCommand is None)
        queued=App.newDocument('TrussReferenceQueuedClose')
        current=host.open_truss_panel(queued)
        pump()
        tool=begin(current,'queued_close')
        numeric(tool,(0,0,0))
        tool.numericInput(4000,0,0)
        App.closeDocument(queued.Name)
        pump()
        check('queued_last_document_close_cleans_session',host._active_panel is None
              and not bridge._operations and current.session.closed and App.ActiveDocument is None)
        return dict(ok=True,version=App.Version()[:3],checks=checks)
    finally:
        sys.excepthook=old_hook


if os.environ.get('SS_DUOPITCH_ROOT'):
    import FreeCAD as App
    from PySide import QtCore,QtWidgets
    root=Path(os.environ['SS_DUOPITCH_ROOT'])
    out=Path(os.environ['SS_DUOPITCH_OUT'])
    sys.path.insert(0,str(root))
    import freecad
    freecad.__path__.insert(0,str(root/'freecad'))
    def launch():
        try: result=run(out)
        except Exception:
            result=dict(ok=False,error=traceback.format_exc())
            App.Console.PrintError(result['error'])
        cleanup=[]
        try:
            command=getattr(App,'activeDraftCommand',None)
            if command is not None: command.finish()
            for _ in range(5): QtWidgets.QApplication.processEvents()
            for name in tuple(App.listDocuments()): App.closeDocument(name)
        except Exception: cleanup.append(traceback.format_exc())
        result['cleanup_errors']=cleanup
        if cleanup: result['ok']=False
        (out/'result.json').write_text(json.dumps(result,indent=2),encoding='utf8')
        QtCore.QTimer.singleShot(0,QtWidgets.QApplication.quit)
    QtCore.QTimer.singleShot(500,launch)
