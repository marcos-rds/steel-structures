# SPDX-License-Identifier: LGPL-2.1-or-later
"""Native visibility/picking evidence; called by the isolated visualization gate."""
import json


def color_counts(path):
    """Count unattenuated reference colors in a controlled front-view strip."""
    from PySide import QtGui
    image = QtGui.QImage(str(path)).convertToFormat(QtGui.QImage.Format_RGBA8888)
    bits = image.bits()
    if hasattr(bits, "setsize"):
        bits.setsize(image.sizeInBytes())
    data = bytes(bits)
    counts = {"axis": 0, "endpoint": 0}
    for y in range(image.height()//2-20, image.height()//2+21):
        for x in range(100, image.width()-100):
            index = y*image.bytesPerLine()+4*x
            rgb = data[index:index+3]
            for key, target in (("axis", (85,200,208)), ("endpoint", (255,71,20))):
                if all(abs(a-b) <= 3 for a,b in zip(rgb, target)):
                    counts[key] += 1
    return counts


def run(out, check, api, helpers):
    import FreeCAD as App
    import FreeCADGui as Gui
    from pivy import coin
    from PySide import QtCore, QtWidgets
    from freecad.SteelStructures.member import create_member
    snapshot, base_flush, pump_until = helpers

    def flush():
        base_flush()
        QtWidgets.QApplication.sendPostedEvents(None, QtCore.QEvent.DeferredDelete)
        base_flush()

    doc = App.newDocument("ReferencePriority")
    doc.UndoMode = 1
    member = create_member(doc, App.Vector(), App.Vector(1000,0,0), "W 150 x 13,0")
    member.ViewObject.ShapeColor = (.1,.2,.7)
    slab = doc.addObject("Part::Box", "OpaqueContext")
    slab.Length, slab.Width, slab.Height = 1400,150,400
    slab.Placement.Base = App.Vector(-200,-250,-200)
    slab.ViewObject.ShapeColor = (.65,.15,.8)
    doc.recompute()
    view = Gui.getDocument(doc.Name).activeView()
    view.setAnimationEnabled(False)
    view.setCameraOrientation(App.Rotation(App.Vector(1,0,0),90).Q)
    view.fitAll()
    camera = view.getCameraNode()
    camera.height = 900
    camera.position.setValue(500,-3000,0)
    camera.nearDistance, camera.farDistance = 1,10000
    api.activate()
    api.toggle("axes", True)
    api.toggle("endpoints", True)
    api.refresh_now()
    session = api.service._sessions[doc.Name]
    layer = session.layers[0]
    scene = view.getSceneGraph()

    # Native scene-only fixture outside ObjectGroup. It remains visible even
    # under Structural, providing a real opaque/translucent depth obstruction.
    obstruction = coin.SoSeparator()
    obstruction.ref()
    pick = coin.SoPickStyle()
    pick.style = coin.SoPickStyle.UNPICKABLE
    obstruction.addChild(pick)
    material = coin.SoMaterial()
    material.diffuseColor.setValue(.65,.15,.8)
    obstruction.addChild(material)
    transform = coin.SoTranslation()
    transform.translation.setValue(500,-450,0)
    obstruction.addChild(transform)
    cube = coin.SoCube()
    cube.width, cube.height, cube.depth = 1400,150,400
    obstruction.addChild(cube)
    scene.addChild(obstruction)
    rows = []

    def capture(name):
        flush()
        before = snapshot(doc)
        undo, dirty = doc.UndoCount, Gui.getDocument(doc.Name).Modified
        reads, updates = session.geometry_reads, layer.geometry_updates
        path = out/("on-top-"+name+".png")
        view.saveImage(str(path), 1000,600)
        counts = color_counts(path)
        rows.append(dict(case=name, colors=counts))
        check(name+" render has no model/history/cache writes", snapshot(doc)==before
              and doc.UndoCount==undo and Gui.getDocument(doc.Name).Modified==dirty
              and session.geometry_reads==reads and layer.geometry_updates==updates)
        return counts

    try:
        # Saving establishes a clean data/GUI baseline before a visual-only mode.
        doc.saveAs(str(out/"on-top-before.FCStd"))
        Gui.runCommand("Std_Save", 0)
        flush()
        original = snapshot(doc)
        clean = not Gui.getDocument(doc.Name).Modified
        undo = doc.UndoCount
        for mode in ("physical", "structural", "xray"):
            api.set_mode(mode)
            api.refresh_now()
            check(mode+" uses effective reference priority", layer.on_top==(mode!="physical")
                  and bool(layer.depth.test.getValue())==(mode=="physical"))
            check(mode+" attachment is single batch", layer.node==(
                layer.root if mode=="physical" else layer._annotation)
                and (mode=="physical" or layer._annotation.getChild(0)==layer.root))
            for transparency in (0,65):
                slab.ViewObject.Transparency = transparency  # Explicit fixture edit.
                material.transparency = transparency/100
                api.refresh_now()
                counts = capture(mode+"-"+str(transparency))
                if mode=="physical":
                    check("physical preserves ordinary occlusion "+str(transparency),counts=={"axis":0,"endpoint":0})
                else:
                    check(mode+" full color above geometry "+str(transparency),counts["axis"]>300 and counts["endpoint"]>50)
            if mode=="xray":
                Gui.Selection.addSelection(slab)
                counts = capture("xray-selected")
                check("references stay above native selection",counts["axis"]>300 and counts["endpoint"]>50)
                Gui.Selection.clearSelection()
                screen = view.getPointOnScreen(App.Vector(500,-250,0))
                info = view.getObjectInfo((int(screen[0]),int(screen[1])))
                check("top references do not intercept physical picking",info is not None and info.get("Object")==slab.Name)
                Gui.Selection.setPreselection(slab,info["Component"],float(info["x"]),float(info["y"]),float(info["z"]))
                counts = capture("xray-preselected")
                check("references stay above native preselection",counts["axis"]>300 and counts["endpoint"]>50)
                Gui.Selection.clearSelection()

        api.toggle("axes", False)
        api.refresh_now()
        counts = capture("points-only")
        check("points-only toggle remains independent",counts["axis"]==0 and counts["endpoint"]>50)
        api.toggle("axes", True)
        api.toggle("endpoints", False)
        api.refresh_now()
        counts = capture("axes-only")
        check("axes-only toggle remains independent",counts["axis"]>300 and counts["endpoint"]==0)
        api.toggle("axes", False)
        api.refresh_now()
        check("both toggles off leave no top graphics",capture("both-off")=={"axis":0,"endpoint":0})

        for _ in range(10):
            for mode in ("physical","structural","xray"):
                api.set_mode(mode)
                api.refresh_now()
        api.set_mode("physical")
        api.refresh_now()
        slab.ViewObject.Transparency = 0
        material.transparency = 0
        api.refresh_now()
        check("return to physical restores depth and previous toggles",not layer.on_top
              and layer.depth.test.getValue() and api.state()==(True,True))
        check("return to physical has no residual top graphics",capture("physical-restored")=={"axis":0,"endpoint":0})
        check("priority did not alter parameters or Undo",snapshot(doc)==original and doc.UndoCount==undo and clean)
        api.set_mode("xray")
        api.refresh_now()
        node, annotation, batch = layer.node, layer._annotation, layer.root
        annotation.ref()  # Inspect after the service releases its own native pin.
        try:
            api.deactivate()
            check("deactivation removes effective annotation attachment",layer.node is None and layer.root is None
                  and scene.findChild(node)<0 and annotation.getNumChildren()==0)
        finally:
            annotation.unref()
        check("native context branch survives cleanup",scene.findChild(obstruction)>=0)
    finally:
        api.deactivate()
        if scene.findChild(obstruction)>=0:
            scene.removeChild(obstruction)
        obstruction.unref()
        App.closeDocument(doc.Name)
        flush()
    (out/"on-top-colors.json").write_text(json.dumps(rows,indent=2),encoding="utf-8")
    overlap = run_projected_references(out, check, api, helpers)
    return dict(color_cases=len(rows), projected_references=overlap, status="passed")


def run_projected_references(out, check, api, helpers):
    """Projection coincidence is presentation only, never structural topology."""
    import FreeCAD as App
    import FreeCADGui as Gui
    from PySide import QtCore, QtWidgets
    from freecad.SteelStructures.member import create_member
    snapshot, base_flush, _pump_until = helpers
    doc = App.newDocument("ProjectedReferences")
    doc.UndoMode = 1
    a = create_member(doc, App.Vector(), App.Vector(1000,0,0), "W 150 x 13,0")
    b = create_member(doc, App.Vector(0,400,0), App.Vector(1000,400,0), "W 150 x 13,0")
    name_a, name_b = a.Name, b.Name
    doc.recompute()
    view = Gui.getDocument(doc.Name).activeView()
    view.setAnimationEnabled(False)
    view.setCameraOrientation(App.Rotation(App.Vector(1,0,0),90).Q)
    view.fitAll()
    view.getCameraNode().height = 900
    view.getCameraNode().position.setValue(500,-3000,0)
    intersection_volume = a.Shape.common(b.Shape).Volume
    base_flush()
    snapshot(doc)  # Settle lazy native view/shape presentation before baseline.
    original, undo = snapshot(doc), doc.UndoCount
    snapper = getattr(Gui, "Snapper", None)
    try:
        api.activate()
        api.toggle("axes", True)
        api.toggle("endpoints", True)
        api.refresh_now()
        session = api.service._sessions[doc.Name]
        axes = tuple(session.axes.values())
        check("projected members retain separate identities and world axes", len(axes)==2
              and {axis.key for axis in axes}=={name_a,name_b}
              and abs(axes[0].start[1]-axes[1].start[1])==400)
        p = view.getPointOnScreen(App.Vector(*axes[0].start))
        q = view.getPointOnScreen(App.Vector(*axes[1].start))
        check("distinct references coincide only in front projection", abs(p[0]-q[0])<1 and abs(p[1]-q[1])<1
              and intersection_volume < 1e-7)
        for mode in ("physical", "structural", "xray", "physical"):
            api.set_mode(mode)
            api.refresh_now()
            layer = session.layers[0]
            check("projected "+mode+" preserves two segments and four ends",
                  len(layer.coordinates.point.getValues())==4
                  and list(layer._lines[0].numVertices.getValues())==[2,2]
                  and all(marker.numPoints.getValue()==4 for marker in layer._markers))
            current = snapshot(doc)
            (out/"projected-snapshot.json").write_text(json.dumps(dict(before=original,after=current),indent=2),encoding="utf-8")
            check("projected "+mode+" creates no objects properties or connectivity", current==original)
            check("projected "+mode+" preserves Undo and global Snapper", doc.UndoCount==undo
                  and getattr(Gui,"Snapper",None) is snapper)
        view.saveImage(str(out/"projected-distinct-references.png"),1000,600)

        # Deliver deletion and same-Name creation in the same queued UI batch.
        doc.removeObject(name_a)
        foreign = doc.addObject("Part::Box", name_a)
        check("replacement fixture really reuses member Name", foreign.Name==name_a)
        doc.recompute()
        api.refresh_now()
        check("same-batch foreign replacement removes stale axis and replay", set(session.axes)=={name_b}
              and name_a not in session.trusted and name_a not in session.rejected)
        check("foreign replacement redraws only surviving nominal endpoints",
              len(session.layers[0].coordinates.point.getValues())==2)
    finally:
        api.deactivate()
        App.closeDocument(doc.Name)
        base_flush()
        QtWidgets.QApplication.sendPostedEvents(None,QtCore.QEvent.DeferredDelete)
        base_flush()
    return dict(distinct_axes=2, endpoints=4, status="passed")
