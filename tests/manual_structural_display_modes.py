# SPDX-License-Identifier: LGPL-2.1-or-later
"""Native display mode checks, called by the existing isolated visualization gate."""
import json
import time


def run(out, check, api, helpers):
    import FreeCAD as App
    import FreeCADGui as Gui
    import Part
    import MeshPart
    from PySide import QtCore, QtWidgets
    from pivy import coin
    from freecad.SteelStructures import truss
    from freecad.SteelStructures.member import create_member
    from freecad.SteelStructures.grid import create_grid
    from freecad.SteelStructures.interactive.structural_reference_modes import MODE_COMMANDS
    snapshot, base_flush, pump_until = helpers
    def flush_events():
        base_flush()
        QtWidgets.QApplication.sendPostedEvents(None,QtCore.QEvent.DeferredDelete)
        base_flush()
    original_check=check
    def check(label,condition):
        App.Console.PrintLog("DISPLAY CHECK: "+label+"\n")
        original_check(label,condition)

    doc = App.newDocument("StructuralDisplayModes")
    doc.UndoMode = 1
    members = [create_member(doc, App.Vector(*a), App.Vector(*b), "W 150 x 13,0") for a,b in (
        ((0,0,0),(0,0,2500)),((3500,0,0),(3500,0,2500)),((0,0,2500),(3500,0,2500)))]
    members[0].ViewObject.ShapeColor = (.8,.2,.1)
    members[1].ViewObject.Transparency = 40
    members[2].ViewObject.ShapeColor = (.1,.2,.7)
    parent = doc.addObject("App::Part","ModeParent")
    parent.addObject(members[2])
    parent.Placement.Base = App.Vector(100,100,0)
    box = doc.addObject("Part::Box","ExternalBox")
    box.Length,box.Width,box.Height = 1200,500,700
    box.Placement.Base = App.Vector(1200,200,0)
    box.ViewObject.ShapeColor = (.2,.8,.3)
    box.ViewObject.DiffuseColor = [(.2,.8,.3),(.8,.2,.3)] * 3
    box_name=box.Name
    mesh=doc.addObject("Mesh::Feature","ExternalMesh")
    mesh.Mesh=MeshPart.meshFromShape(Shape=Part.makeBox(300,300,300,App.Vector(2500,300,200)),LinearDeflection=1,AngularDeflection=.5,Relative=False)
    mesh.ViewObject.ShapeColor=(.7,.6,.2)
    hidden = doc.addObject("Part::Box","HiddenBox")
    hidden.ViewObject.Visibility = False
    grid = create_grid(doc)
    doc.recompute()
    view = Gui.getDocument(doc.Name).activeView()
    view.setAnimationEnabled(False)
    view.setCameraOrientation(App.Rotation(App.Vector(1,0,0),90).Q)
    view.fitAll()
    view.getCameraNode().height=5000
    view.getCameraNode().position.setValue(1750,-15000,1250)
    flush_events()
    snapshot(doc)
    doc.saveAs(str(out/'modes-before.FCStd'))
    Gui.runCommand("Std_Save",0)
    flush_events()
    baseline = snapshot(doc)
    undo = doc.UndoCount
    api.activate()
    api.toggle("axes",True)  # The physical configuration must survive presets.
    api.refresh_now()
    s = api.service._sessions[doc.Name]
    def layer(): return s.layers[0]
    mode_actions = {mode: Gui.Command.get(name).getAction()[0] for mode,name in MODE_COMMANDS.items()}
    pump_until(lambda: all(action.isEnabled() for action in mode_actions.values()))
    def buttons_match(mode):
        return [a.isChecked() for a in mode_actions.values()] == [key==mode for key in MODE_COMMANDS]
    def setmode(mode):
        mode_actions[mode].trigger()
        api.refresh_now()
        check("mode applied " + mode, api.mode()==mode and all(l.presentation.mode==mode for l in s.layers))
        check("exclusive toolbar mode " + mode, buttons_match(mode))
        toolbar.grab().save(str(out/('mode-toolbar-'+mode+'.png')))
    from freecad.SteelStructures.interactive.structural_reference_commands import StructuralDisplayModeCommand
    check("three mode commands are checkable without transaction",all(
        StructuralDisplayModeCommand(mode).GetResources()["CmdType"]=="NoTransaction" and action.isCheckable()
        for mode,action in mode_actions.items()))
    toolbar=next(bar for bar in Gui.getMainWindow().findChildren(QtWidgets.QToolBar)
                 if bar.windowTitle()=="Steel Structures - Visualização")
    check("toolbar replaces selector with three modes and two independent toggles",
          toolbar.actions()==[*mode_actions.values(),*(Gui.Command.get(name).getAction()[0] for name in api.COMMANDS.values())]
          and "SteelStructures_StructuralDisplayMode" not in Gui.listCommands())
    check("three mode icons are distinct and present",all(not a.icon().isNull() for a in mode_actions.values())
          and len({a.icon().cacheKey() for a in mode_actions.values()})==3)
    check("initial physical button checked exclusively",buttons_match("physical"))
    setmode("structural")
    mode_actions["structural"].trigger()
    check("clicking active mode keeps it checked",api.mode()=="structural" and buttons_match("structural"))
    check("other mode buttons remain available for switching",all(a.isEnabled() for a in mode_actions.values()))
    check("structural initially enables both reference layers", api.state()==(True,True))
    check("structural masks physical and native selection branches per view", len(layer().presentation.wrappers)==2)
    view.saveImage(str(out/'mode-structural.png'),1600,1000)
    setmode("xray")
    check("xray copy created", layer().presentation.clone is not None)
    from freecad.SteelStructures.interactive.structural_reference_modes import _nodes
    p=layer().presentation
    source_nodes=list(_nodes(p.source))
    copied_nodes=list(_nodes(p.clone))
    def values(node,name):
        field=node.getField(name)
        return [field[i] for i in range(field.getNum())] if field is not None else None
    check("copy preserves native switches and hidden branches", [int(n.whichChild.getValue()) for n in source_nodes if n.isOfType(coin.SoSwitch.getClassTypeId())]==[int(n.whichChild.getValue()) for n in copied_nodes if n.isOfType(coin.SoSwitch.getClassTypeId())])
    check("copy preserves diffuse material arrays", [values(n,"diffuseColor") for n in source_nodes]==[values(n,"diffuseColor") for n in copied_nodes])
    check("copy includes external Part and Mesh solids", p.source.findChild(box.ViewObject.RootNode)>=0 and p.source.findChild(mesh.ViewObject.RootNode)>=0)
    check("mode buttons indicate current document preset", buttons_match("xray"))
    view.saveImage(str(out/'mode-xray.png'),1600,1000)
    revision = layer().presentation.copy_updates
    for _ in range(3):
        api.service._reconcile_views()
        api.refresh_now()
        view.redraw()
    check("stable scene does not rebuild xray copy", layer().presentation.copy_updates==revision)
    check("modes preserve physical and visual snapshot", snapshot(doc)==baseline)
    check("modes create no Undo and do not dirty document", doc.UndoCount==undo and not Gui.getDocument(doc.Name).Modified)
    check("hidden object remains hidden", not hidden.ViewObject.Visibility)
    check("external source transparency and color untouched", box.ViewObject.Transparency==0 and all(abs(a-b)<1e-6 for a,b in zip(box.ViewObject.ShapeColor,(.2,.8,.3))))
    check("preexisting transparency preserved", members[1].ViewObject.Transparency==40)
    setmode("physical")
    check("physical restores independent toggles", api.state()==(True,False))
    view.saveImage(str(out/'mode-physical.png'),1600,1000)
    check("physical restores native branches exactly", not layer().presentation.wrappers and snapshot(doc)==baseline)

    for _ in range(10):
        for mode in ("structural","xray","physical"):
            api.set_mode(mode)
            api.refresh_now()
    check("ten mode cycles preserve data Undo and clean state", snapshot(doc)==baseline and doc.UndoCount==undo and not Gui.getDocument(doc.Name).Modified)

    api.set_mode("xray")
    api.refresh_now()
    second = Gui.getDocument(doc.Name).createView("Gui::View3DInventor")
    second.setAnimationEnabled(False)
    second.setCamera(view.getCamera())
    api.refresh_now()
    check("two views receive independent xray wrappers and priority",len(s.layers)==2 and s.layers[0].presentation.scene!=s.layers[1].presentation.scene and all(l.presentation.mode=="xray" and l.on_top for l in s.layers))
    second.saveImage(str(out/'mode-xray-second.png'),1200,800)

    # Native source (INVISIBLE draw style) supplies picking. Copy is unpickable.
    screen = second.getPointOnScreen(App.Vector(1200,0,2500))
    picked = second.getObjectInfo((int(screen[0]),int(screen[1])))
    check("xray retains native physical picking", picked is not None and picked.get("Document")==doc.Name)
    Gui.Selection.addSelection(members[0])
    api.refresh_now()
    check("native selection retained in xray", members[0] in Gui.Selection.getSelection())
    api.set_mode("structural")
    api.refresh_now()
    check("structural retains selection state without rendering solids", members[0] in Gui.Selection.getSelection())
    second.saveImage(str(out/'mode-structural-selected.png'),1200,800)
    Gui.Selection.clearSelection()
    api.set_mode("xray")
    api.refresh_now()

    before_updates = [l.presentation.copy_updates for l in s.layers]
    box.ViewObject.ShapeColor=(.6,.2,.8)
    box.ViewObject.Transparency=90
    hidden.ViewObject.Visibility=True
    flush_events()
    api.refresh_now()
    check("user visual changes invalidate both viewport copies", all(l.presentation.copy_updates>n for l,n in zip(s.layers,before_updates)))
    api.set_mode("physical")
    api.refresh_now()
    check("physical preserves current user edits instead of old snapshot", box.ViewObject.Transparency==90 and all(abs(a-b)<1e-6 for a,b in zip(box.ViewObject.ShapeColor,(.6,.2,.8))) and hidden.ViewObject.Visibility)
    api.set_mode("xray")
    api.refresh_now()
    added=doc.addObject("Part::Box","AddedWhileXray")
    added.Placement.Base=App.Vector(0,1000,0)
    doc.recompute()
    api.refresh_now()
    check("native object insertion still targets original group", any(l.presentation.source.findChild(added.ViewObject.RootNode)>=0 for l in s.layers))
    doc.removeObject(added.Name)
    doc.recompute()
    api.refresh_now()
    check("native object deletion keeps mode functional",all(l.presentation.mode=="xray" for l in s.layers))
    name=members[0].Name
    doc.openTransaction("Move member in Xray")
    members[0].EndPoint += App.Vector(0,0,200)
    doc.recompute()
    doc.commitTransaction()
    api.refresh_now()
    changed = s.axes[name]
    doc.undo()
    api.refresh_now()
    check("Undo updates references and xray without manual recompute",s.axes[name]!=changed and api.mode()=="xray")
    doc.redo()
    api.refresh_now()
    check("Redo restores references and xray without manual recompute",s.axes[name]==changed and api.mode()=="xray")

    class Dialog:
        def __init__(self): self.form=QtWidgets.QWidget()
        def getStandardButtons(self): return 0
    dialog=Dialog()
    Gui.Control.showDialog(dialog)
    api.refresh_now()
    check("task dialog suspends masks and priority in every view",all(l.presentation.mode=="physical" and not l.on_top for l in s.layers) and api.mode()=="xray")
    Gui.Control.closeDialog()
    flush_events()
    api.refresh_now()
    check("closing task rebuilds requested mode and priority",all(l.presentation.mode=="xray" and l.on_top for l in s.layers))
    mdi=Gui.getMainWindow().findChild(QtWidgets.QMdiArea)
    second_window=mdi.activeSubWindow()
    another=Gui.getDocument(doc.Name).createView("Gui::View3DInventor")
    api.refresh_now()
    old_presentation=next(l.presentation for l in s.layers if l.view==second)
    second_window.close()
    flush_events()
    api.refresh_now()
    check("closing inactive xray viewport releases its pinned scene",old_presentation.scene is None and len(s.layers)==2)
    other=App.newDocument("OtherModeDocument")
    other.addObject("Part::Box","OtherBox")
    other.recompute()
    api.refresh_now()
    check("switch document restores previous document physical presentation", all(l.presentation.mode=="physical" and not l.on_top for l in s.layers) and api.mode()=="physical")
    check("mode checks follow new document",buttons_match("physical"))
    api.set_mode("structural")
    api.refresh_now()
    check("documents keep independent mode state",api.mode(other)=="structural" and api.mode(doc)=="xray")
    App.setActiveDocument(doc.Name)
    Gui.activeDocument().activeView()
    api.refresh_now()
    check("returning document restores its requested preset", all(l.presentation.mode=="xray" for l in s.layers))
    check("mode checks follow restored document",buttons_match("xray"))
    check("other document graphics restored while inactive", all(l.presentation.mode=="physical" and not l.on_top for l in api.service._sessions[other.Name].layers))
    filename=out/'modes-active.FCStd'
    before_save=snapshot(doc)
    doc.saveAs(str(filename))
    api.deactivate()
    check("deactivation releases mode resources", not api.service._sessions and not api.service._observing)
    check("deactivation retains latest data and appearance", snapshot(doc)==before_save)
    App.closeDocument(doc.Name)
    App.closeDocument(other.Name)
    flush_events()
    restored=App.openDocument(str(filename))
    api.activate()
    check("FCStd opens physical with no persisted preset",api.mode()=="physical" and api.state()==(False,False))
    check("FCStd preserves latest visual properties",restored.getObject(box_name).ViewObject.Transparency==90)
    api.set_mode("xray")
    api.refresh_now()
    check("xray reusable after FCStd restore",all(l.presentation.mode=="xray" for l in api.service._sessions[restored.Name].layers))
    App.closeDocument(restored.Name)
    api.refresh_now()
    flush_events()
    check("active xray document close removes session",not api.service._sessions)
    api.deactivate()
    return {"status":"passed"}
