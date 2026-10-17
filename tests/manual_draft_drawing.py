"""Actual native Draft commands inside Steel Structures; no command wrappers."""
import json
import os
from pathlib import Path
import sys
import traceback


def run(root,out,phase):
    import FreeCAD as App
    import FreeCADGui as Gui
    from PySide import QtCore,QtGui,QtWidgets
    from PySide6 import QtTest
    checks,errors=[],[]
    old_hook=sys.excepthook
    def hook(kind,error,trace):
        errors.append(''.join(traceback.format_exception(kind,error,trace)))
        (out/'qt_errors.txt').write_text('\n'.join(errors),encoding='utf8')
    sys.excepthook=hook
    def check(name,condition):
        if not condition: raise AssertionError(name)
        checks.append(name)
        (out/'checks.json').write_text(json.dumps(checks,indent=2))
    def pump():
        for _ in range(8): QtWidgets.QApplication.processEvents()
        QtTest.QTest.qWait(30)
        QtCore.QCoreApplication.sendPostedEvents(None,QtCore.QEvent.DeferredDelete)
        if errors: raise AssertionError('\n'.join(errors))
    def cancel():
        tool=getattr(App,'activeDraftCommand',None)
        if tool is not None: tool.finish()
        pump()
    def open_native(command):
        Gui.Selection.clearSelection()
        Gui.runCommand(command)
        pump()
        tool=App.activeDraftCommand
        check(command+'_native_active',tool is not None and tool.__class__.__module__.startswith('draftguitools.')
              and bool(Gui.Control.activeDialog()))
        tool.ui.continueCmd.setChecked(False)
        Gui.getMainWindow().grab().save(str(out/(command+'_task.png')))
        return tool
    def numeric(tool,point,relative=False,global_axes=True,enter=False):
        ui=tool.ui
        QtWidgets.QApplication.setActiveWindow(Gui.getMainWindow())
        ui.isGlobal.setChecked(global_axes)
        ui.isRelative.setChecked(relative)
        for field,value in zip((ui.xValue,ui.yValue,ui.zValue),point):
            field.setFocus()
            field.setText(QtCore.QLocale().toString(float(value),'g',17)+' mm')
        pump()
        if enter:
            field=ui.zValue if ui.zValue.isEnabled() else ui.yValue
            field.setFocus()
            QtTest.QTest.keyClick(field,QtCore.Qt.Key_Return)
        else: ui.pointButton.click()
        pump()
    def viewport():
        return next(w for w in Gui.getMainWindow().findChildren(QtWidgets.QWidget)
                    if w.inherits('SIM::Coin3D::Quarter::QuarterWidget') and w.isVisible())
    def move(point,modifiers=QtCore.Qt.NoModifier):
        widget=viewport()
        event=QtGui.QMouseEvent(QtCore.QEvent.MouseMove,QtCore.QPointF(point),
            QtCore.QPointF(widget.mapToGlobal(point)),QtCore.Qt.NoButton,QtCore.Qt.NoButton,modifiers)
        QtWidgets.QApplication.sendEvent(widget,event)
        pump()
    def escaped(tool):
        widget=viewport()
        widget.setFocus()
        QtTest.QTest.keyClick(widget,QtCore.Qt.Key_Escape)
        pump()
        check(tool.featureName+'_escape_cleanup',App.activeDraftCommand is None and not Gui.Control.activeDialog())
    try:
        check('fresh_without_Draft_workbench','DraftWorkbench' not in sys.modules)
        sys.path.insert(0,str(root))
        import freecad
        freecad.__path__.insert(0,str(root/'freecad'))
        baseline=os.environ.get('SS_DRAW_BASELINE')
        if baseline:
            import importlib.util
            spec=importlib.util.spec_from_file_location('freecad.SteelStructures.init_gui',baseline)
            module=importlib.util.module_from_spec(spec)
            sys.modules[spec.name]=module
            spec.loader.exec_module(module)
        else:
            import freecad.SteelStructures.init_gui
        import hashlib
        loaded=sys.modules['freecad.SteelStructures.init_gui']
        (out/'loaded_init_gui.json').write_text(json.dumps(dict(path=loaded.__file__,
            sha256=hashlib.sha256(Path(loaded.__file__).read_bytes()).hexdigest(),baseline=bool(baseline)),indent=2))
        Gui.activateWorkbench('SteelStructuresWorkbench')
        pump()
        check('SteelStructures_direct',Gui.activeWorkbench().name()=='SteelStructuresWorkbench'
              and 'DraftWorkbench' not in sys.modules)
        qss=os.environ.get('SS_DRAW_QSS')
        if qss:
            path=Path(qss)
            QtCore.QDir.addSearchPath('qss',str(path.parent))
            QtWidgets.QApplication.instance().setStyleSheet(path.read_text(encoding='utf8'))
        import WorkingPlane
        from draftutils import params
        from freecad.SteelStructures import commands
        from freecad.SteelStructures.interactive import truss_controller as trusses
        from freecad.SteelStructures.member_axis_source import resolve_axis_source
        from freecad.SteelStructures.truss_reference import source_geometry,selection_reference
        names=('Draft_Line','Draft_Wire','Draft_Rectangle')
        check('official_ids_available',all(name in Gui.listCommands() for name in names))
        bar=(next(w for w in Gui.getMainWindow().findChildren(QtWidgets.QToolBar) if w.windowTitle()=='Desenho Draft')
             if not baseline else None)
        native=[Gui.Command.get(name).getAction()[0] for name in names]
        if bar is not None:
            check('native_actions_in_toolbar',bar.actions()==native and all(not a.icon().isNull() and a.toolTip() for a in native))
        # Keep the QAction wrappers which own the QMenu references alive while
        # traversing FreeCAD's dynamically composed workbench menu.
        menu_bar=Gui.getMainWindow().menuBar()
        top_actions=menu_bar.actions()
        menu_action=next(a for a in top_actions if a.text().replace('&','')=='Steel Structures')
        menu=menu_action.menu()
        menu_actions=menu.actions()
        if not baseline:
            submenu_action=next(a for a in menu_actions if a.text().replace('&','')=='Desenho Draft')
            submenu=submenu_action.menu()
            check('native_actions_in_submenu',submenu.actions()==native)
        doc=App.newDocument('NativeDraftDrawing')
        doc.UndoMode=1
        Gui.activeDocument().activeView().viewTop()
        Gui.updateGui()
        pump()
        if bar is not None: bar.grab().save(str(out/'drawing_toolbar.png'))
        Gui.getMainWindow().grab().save(str(out/'workbench.png'))
        if phase=='interface':
            check('toolbar_visible',bar is not None and bar.isVisible())
            return dict(ok=True,checks=checks,version=App.Version(),phase=phase)
        wp=WorkingPlane.get_working_plane(update=False)
        initial=wp.get_parameters(),dict(wp._stored)
        shortcuts={key:params.get_param('inCommandShortcut'+key) for key in ('Relative','Global','RestrictX','RestrictY','RestrictZ','Close','Exit')}
        if phase=='drawing':
            objects={}
            for name in names:
                before=set(o.Name for o in doc.Objects)
                tool=open_native(name)
                numeric(tool,(0,0,0))
                numeric(tool,(2000,1000 if name=='Draft_Rectangle' else 0,0),enter=name=='Draft_Line')
                if name=='Draft_Wire':
                    numeric(tool,(0,1000,0),relative=True)
                    tool.ui.closeButton.click()
                    pump()
                created=[o for o in doc.Objects if o.Name not in before]
                check(name+'_normal_Draft_object',len(created)==1 and created[0].Proxy.__class__.__module__.startswith('draftobjects.')
                      and created[0].Shape.isValid() and not created[0].Shape.isNull())
                obj=objects[name]=created[0]
                object_name=obj.Name
                check(name+'_finished',App.activeDraftCommand is None and not Gui.Control.activeDialog())
                if name=='Draft_Line':
                    axis=resolve_axis_source(obj)
                    check('line_numeric_coordinates_and_reference',axis is not None and (axis.end-App.Vector(2000,0,0)).Length<1e-6)
                elif name=='Draft_Wire':
                    check('wire_relative_closed',obj.Closed and len(obj.Shape.Edges)==3)
                else:
                    check('rectangle_dimensions',abs(obj.Length.Value-2000)<1e-6 and abs(obj.Height.Value-1000)<1e-6)
                    geometry=source_geometry(obj,'DraftRectangle','Edge1',[0,0,1])
                    check('rectangle_truss_reference',geometry['span']>0 and geometry['height']>0)
                count=len(doc.Objects)
                doc.undo()
                pump()
                check(name+'_undo',len(doc.Objects)==count-1)
                doc.redo()
                doc.recompute()
                pump()
                objects[name]=doc.getObject(object_name)
                check(name+'_redo',len(doc.Objects)==count)
                before=set(o.Name for o in doc.Objects)
                escaped(open_native(name))
                check(name+'_cancel_no_objects',set(o.Name for o in doc.Objects)==before)
            # A native Line's endpoint, snapped graphically in the native tool.
            line=objects['Draft_Line']
            Gui.activeDocument().activeView().fitAll()
            tool=open_native('Draft_Line')
            Gui.Snapper.toggle_snap('Lock',True)
            Gui.Snapper.toggle_snap('Endpoint',True)
            target=line.Start
            screen=Gui.activeDocument().activeView().getPointOnScreen(target)
            point=QtCore.QPoint(int(screen[0]),viewport().height()-int(screen[1]))
            move(point,QtCore.Qt.ControlModifier)
            check('native_endpoint_snap',tool.point is not None and (tool.point-target).Length<1e-5)
            QtTest.QTest.mouseClick(viewport(),QtCore.Qt.LeftButton,QtCore.Qt.ControlModifier,pos=point)
            pump()
            move(point+QtCore.QPoint(90,60))
            focus=QtWidgets.QApplication.focusWidget()
            QtTest.QTest.keyClicks(focus,params.get_param('inCommandShortcutRestrictX'))
            pump()
            check('native_x_constraint',tool.ui.mask=='x' and Gui.Snapper.mask=='x')
            move(point+QtCore.QPoint(120,90))
            check('constraint_keeps_y',abs(tool.point.y-tool.node[-1].y)<1e-5)
            escaped(tool)
            # Tilted native working plane, local numeric entry.
            frame=App.Placement(App.Vector(100,200,300),App.Rotation(App.Vector(0,1,0),30))
            wp.align_to_placement(frame,_hist_add=False)
            before=set(o.Name for o in doc.Objects)
            tool=open_native('Draft_Line')
            numeric(tool,(0,0,0),global_axes=False)
            numeric(tool,(1500,0,0),global_axes=False)
            obj=next(o for o in doc.Objects if o.Name not in before)
            axis=resolve_axis_source(obj)
            check('tilted_work_plane_local_coordinates',(axis.start-frame.Base).Length<1e-5
                  and (axis.end-frame.multVec(App.Vector(1500,0,0))).Length<1e-5)
            wp.set_parameters(initial[0]);wp._stored=initial[1];wp._update_all(_hist_add=False)
            Gui.runCommand('Draft_SelectPlane');pump();cancel()
            check('native_work_plane_command',not Gui.Control.activeDialog())
            # Use the native drawing results through existing selection adapters.
            for name in ('Draft_Line','Draft_Rectangle'):
                Gui.Selection.clearSelection();Gui.Selection.addSelection(objects[name])
                selected=selection_reference(Gui.Selection.getSelectionEx())
                check(name+'_supported_selection_reference',selected[0] is objects[name])
            Gui.Selection.clearSelection()
            tool=open_native('Draft_Rectangle')
            other=App.newDocument('DraftOther')
            pump()
            cancel()
            check('document_switch_cancel',not Gui.Control.activeDialog() and not other.Objects)
            App.closeDocument(other.Name);App.setActiveDocument(doc.Name)
            tool=open_native('Draft_Wire')
            App.closeDocument(doc.Name);pump();cancel()
            check('document_close_no_task',not Gui.Control.activeDialog() and App.activeDraftCommand is None)
        else:
            # Forward handoff from each existing Steel Structures tool.
            for command in names:
                for source in ('SteelStructures_CreateTruss','SteelStructures_CreateMember','SteelStructures_CreateColumn','SteelStructures_CreatePlate'):
                    Gui.Selection.clearSelection();Gui.runCommand(source);pump()
                    panel=trusses._active_panel if source.endswith('Truss') else None
                    member=commands._active_member_tool if source.endswith(('Member','Column')) else None
                    plate=commands._active_plate_session if source.endswith('Plate') else None
                    if panel is not None:
                        panel._update_preview3d();panel._pick_points()
                    native_tool=open_native(command)
                    check(source+'_to_'+command,Gui.Control.activeDialog() and
                          (panel is None or panel._closed and panel.controller._preview is None and not panel.controller._point_callbacks)
                          and (member is None or not member.is_active())
                          and (plate is None or plate._closed))
                    escaped(native_tool)
                    # The inverse path explicitly finishes Draft, then opens SS.
                    Gui.runCommand(source);pump()
                    check(command+'_back_to_'+source,bool(Gui.Control.activeDialog()))
                    if source.endswith('Truss'): trusses.close_truss_panel()
                    elif source.endswith('Plate'): commands.close_plate_panel()
                    else: commands.close_member_tool()
                    pump()
                    check(source+'_inverse_cleanup',not Gui.Control.activeDialog() and App.activeDraftCommand is None)
        check('shortcuts_unchanged',shortcuts=={key:params.get_param('inCommandShortcut'+key) for key in shortcuts})
        check('workbench_remains_SteelStructures',Gui.activeWorkbench().name()=='SteelStructuresWorkbench')
        check('no_qt_callback_error',not errors)
        return dict(ok=True,checks=checks,version=App.Version(),phase=phase)
    finally:
        sys.excepthook=old_hook


if os.environ.get('SS_DRAW_ROOT'):
    import FreeCAD as App
    from PySide import QtCore,QtWidgets
    root=Path(os.environ['SS_DRAW_ROOT'])
    out=Path(os.environ['SS_DRAW_OUT'])
    def launch():
        try: result=run(root,out,os.environ['SS_DRAW_PHASE'])
        except Exception: result=dict(ok=False,error=traceback.format_exc())
        if not result['ok']: App.Console.PrintError(result['error'])
        cleanup_errors=[]
        old_hook=sys.excepthook
        sys.excepthook=lambda kind,error,trace:cleanup_errors.append(''.join(traceback.format_exception(kind,error,trace)))
        command=getattr(App,'activeDraftCommand',None)
        if command is not None:
            try: command.finish()
            except Exception: cleanup_errors.append(traceback.format_exc())
        for _ in range(8): QtWidgets.QApplication.processEvents()
        for name in tuple(App.listDocuments()):
            try: App.closeDocument(name)
            except Exception: cleanup_errors.append(traceback.format_exc())
        for _ in range(8): QtWidgets.QApplication.processEvents()
        sys.excepthook=old_hook
        result['cleanup_errors']=cleanup_errors
        if cleanup_errors:
            result['ok']=False
            App.Console.PrintError('\n'.join(cleanup_errors))
        (out/'result.json').write_text(json.dumps(result,indent=2))
        QtCore.QTimer.singleShot(0,QtWidgets.QApplication.quit)
    QtCore.QTimer.singleShot(800,launch)
