# SPDX-License-Identifier: LGPL-2.1-or-later
"""Isolated FreeCAD 1.1.4 gate; not imported by unittest discovery.

Run scripts/run_structural_reference_visualization_gate.py. Evidence screenshots
require visual review; API assertions do not certify contrast or depth perception.
"""
import hashlib
import json
import math
import os
from pathlib import Path
import sys
import time
import traceback


def pump_until(predicate, timeout=8.0):
    """Dispatch real queued observers; elapsed time is only a failure watchdog."""
    from PySide import QtCore, QtWidgets
    deadline = time.perf_counter() + timeout
    while True:
        QtWidgets.QApplication.sendPostedEvents(None, 0)
        QtWidgets.QApplication.processEvents(QtCore.QEventLoop.AllEvents, 20)
        if predicate():
            return
        if time.perf_counter() >= deadline:
            raise AssertionError("Queued reference update did not reach its expected state")


def flush_events():
    from PySide import QtCore
    completed = []
    QtCore.QTimer.singleShot(0, lambda: completed.append(True))
    pump_until(lambda: bool(completed))


def vec(value):
    return tuple(float(v) for v in value)


def near(a, b):
    return sum((x-y)**2 for x, y in zip(vec(a), vec(b)))**.5 < 1e-6


def snapshot(document):
    """Physical/parametric data and presentation, excluding Python/Coin caches."""
    from freecad.SteelStructures.member_batch import INPUTS, OUTPUTS
    def plain(value):
        if hasattr(value, "Name"):
            return value.Name
        if hasattr(value, "Value"):
            return float(value.Value)
        if isinstance(value, (str, bool, int, float, type(None))):
            return value
        try:
            return [plain(v) for v in value]
        except TypeError:
            return repr(value)
    rows = {}
    for obj in document.Objects:
        row = dict(properties=list(obj.PropertiesList), label=obj.Label,
                   inputs={p: plain(getattr(obj, p)) for p in (*INPUTS, *OUTPUTS)
                           if hasattr(obj, p)})
        if hasattr(obj, "Placement"):
            row["placement"] = list(obj.Placement.toMatrix().A)
        if hasattr(obj, "Shape"):
            shape = obj.Shape
            row["geometry"] = dict(null=shape.isNull(), valid=not shape.isNull() and shape.isValid())
            row["brep"] = (None if shape.isNull() else
                           hashlib.sha256(shape.exportBrepToString().encode()).hexdigest())
            row["volume"] = (None if shape.isNull() else
                             round(shape.Volume, 7) if shape.Solids else 0.)
        view = obj.ViewObject
        row["visual"] = {p: plain(getattr(view, p)) for p in
                         ("Visibility", "Transparency", "DisplayMode", "ShapeColor",
                          "LineColor", "PointColor", "LineWidth", "PointSize", "Selectable")
                         if hasattr(view, p)}
        rows[obj.Name] = row
    return rows


def coin_nodes(root):
    yield root
    if hasattr(root, "getNumChildren"):
        for index in range(root.getNumChildren()):
            yield from coin_nodes(root.getChild(index))


def visual_refinement_gallery(out, check, api):
    """Test-owned manual transparency, never a production presentation mode."""
    import FreeCAD as App
    import FreeCADGui as Gui
    from freecad.SteelStructures import profile_catalog, truss
    from freecad.SteelStructures.member import create_member
    profiles = list(profile_catalog.profiles().values())
    channel = next(p.designation for p in profiles
                   if p.definition.geometry_type == "channel_section"
                   and p.definition.geometry_variant == "tapered_flange")
    doc = App.newDocument("ReferenceVisualPortals")
    members = []
    for origin, profile in ((0, "W 150 x 13,0"), (5200, channel)):
        for a, b in (((origin, 0, 0), (origin, 0, 2800)),
                     ((origin+4000, 0, 0), (origin+4000, 0, 2800)),
                     ((origin, 0, 2800), (origin+4000, 0, 2800))):
            members.append(create_member(doc, App.Vector(*a), App.Vector(*b), profile))
    exposed = create_member(doc, App.Vector(700, 0, -700), App.Vector(3500, 0, -700), "W 150 x 13,0")
    exposed.OffsetY = 200
    members.append(exposed)
    doc.recompute()
    api.activate()
    api.toggle("axes", True)
    api.toggle("endpoints", True)
    pump_until(lambda: len(api.service._sessions[doc.Name].axes) == len(members))
    view = Gui.getDocument(doc.Name).activeView()
    view.setAnimationEnabled(False)  # Isolated gallery: comparable settled views.
    view.setCameraOrientation(App.Rotation(App.Vector(1, 0, 0), 90).Q)
    view.fitAll()
    flush_events()
    original = snapshot(doc)
    view.saveImage(str(out / "visual-W-U-opaque.png"), 1800, 1000)
    for mode in ("structural", "xray"):
        api.set_mode(mode)
        api.refresh_now()
        view.saveImage(str(out / ("visual-W-U-"+mode+".png")),1800,1000)
    api.set_mode("physical")
    api.refresh_now()
    for obj in members:
        obj.ViewObject.Transparency = 70  # Explicit test action, like user editing.
    flush_events()
    view.saveImage(str(out / "visual-W-U-manual-transparency.png"), 1800, 1000)
    for obj in members:
        obj.ViewObject.Transparency = 0
    flush_events()
    check("visual W/U gallery restores its manual transparency", snapshot(doc) == original)
    api.deactivate()
    App.closeDocument(doc.Name)

    doc = App.newDocument("ReferenceVisualTruss")
    config = truss.default_config()
    config.update(span=6000., end=[6000., 0., 0.], height=1400., panel_count=6)
    owner = truss.apply_truss(doc, config)
    members = list(owner.GeneratedMembers)
    api.activate()
    api.toggle("axes", True)
    api.toggle("endpoints", True)
    pump_until(lambda: len(api.service._sessions[doc.Name].axes) == len(members))
    view = Gui.getDocument(doc.Name).activeView()
    view.setAnimationEnabled(False)
    view.setCameraOrientation(App.Rotation(App.Vector(1, 0, 0), 90).Q)
    view.fitAll()
    flush_events()
    view.saveImage(str(out / "visual-truss-opaque.png"), 1800, 800)
    for mode in ("structural", "xray"):
        api.set_mode(mode)
        api.refresh_now()
        view.saveImage(str(out / ("visual-truss-"+mode+".png")),1800,800)
    api.set_mode("physical")
    api.refresh_now()
    for obj in members:
        obj.ViewObject.Transparency = 70
    flush_events()
    view.saveImage(str(out / "visual-truss-manual-transparency.png"), 1800, 800)
    for obj in members:
        obj.ViewObject.Transparency = 0
    api.deactivate()
    check("visual gallery removes its reference sessions", not api.service._sessions)
    App.closeDocument(doc.Name)


def run(out):
    import FreeCAD as App
    import FreeCADGui as Gui
    import Part
    from PySide import QtCore, QtWidgets
    from pivy import coin
    from freecad.SteelStructures.member import create_member
    from freecad.SteelStructures import truss
    from freecad.SteelStructures.interactive import structural_reference_view as api
    from freecad.SteelStructures.interactive.structural_reference_commands import (
        StructuralReferenceCommand,
    )

    qss = os.environ.get("SS_STRUCTURAL_REFERENCE_QSS")
    if qss:
        path = Path(qss)
        QtCore.QDir.addSearchPath("qss", str(path.parent))
        QtWidgets.QApplication.instance().setStyleSheet(path.read_text(encoding="utf-8"))
    checks, errors, metrics = [], [], {}
    toolbar = None
    original_hook = sys.excepthook
    sys.excepthook = lambda kind, value, trace: errors.append(
        "".join(traceback.format_exception(kind, value, trace)))
    def check(label, condition):
        if not condition:
            raise AssertionError(label)
        checks.append(label)
        (out / "checks.json").write_text(json.dumps(checks, indent=2), encoding="utf-8")
    def session(doc):
        return api.service._sessions[doc.Name]
    def layers(doc):
        return list(session(doc).layers)
    def nominal(obj):
        parent = obj.getGlobalPlacement().multiply(obj.Placement.inverse())
        return parent.multVec(obj.StartPoint), parent.multVec(obj.EndPoint)
    def axis_matches(doc, obj):
        axis = session(doc).axes.get(obj.Name)
        a, b = nominal(obj)
        return axis is not None and near(axis.start, a) and near(axis.end, b)
    def wait_axis(doc, obj):
        try:
            pump_until(lambda: axis_matches(doc, obj))
        except AssertionError:
            from freecad.SteelStructures.structural_reference import resolve_member_axis
            (out / "axis-diagnostic.json").write_text(json.dumps(dict(
                object=obj.Name, state=list(obj.State), transacting=doc.Transacting,
                reason=resolve_member_axis(obj).reason,
                start=list(obj.StartPoint), end=list(obj.EndPoint),
                effective_start=list(obj.EffectiveStartPoint), effective_end=list(obj.EffectiveEndPoint),
                length=float(obj.MemberLength.Value), placement=list(obj.Placement.toMatrix().A),
                rejected=session(doc).rejected), indent=2), encoding="utf-8")
            raise
    def make(doc, start, end, **kwargs):
        return create_member(doc, App.Vector(*start), App.Vector(*end),
                             "W 150 x 13,0", **kwargs)
    def commands_match(document):
        return tuple(actions[kind].isChecked() for kind in ("axes", "endpoints")) == api.state(document)
    def coordinate_count(document):
        return [layer.coordinates.point.getNum() for layer in layers(document)]
    def alloff():
        return (not api.service._sessions and not api.service._observing
                and api.service._flush_timer is None and api.service._view_timer is None)
    try:
        from freecad.SteelStructures import init_gui  # noqa: F401 - real GUI composition
        Gui.activateWorkbench("SteelStructuresWorkbench")
        flush_events()
        commands = {kind: StructuralReferenceCommand(kind) for kind in api.COMMANDS}
        actions = {kind: Gui.Command.get(name).getAction()[0] for kind, name in api.COMMANDS.items()}
        api.deactivate()
        check("registered command callbacks inactive outside workbench lifecycle", all(
            not command.IsActive() for command in commands.values()))
        check("native actions are checkable and initially unchecked", all(
            action.isCheckable() and not action.isChecked() for action in actions.values()))
        doc = App.newDocument("ReferenceVisualization")
        doc.UndoMode = 1
        a = make(doc, (0, 0, 0), (2000, 0, 0))
        b = make(doc, (0, 600, 0), (0, 2600, 0))
        c = make(doc, (800, 600, 0), (800, 600, 1800))
        d = make(doc, (1600, 600, 0), (2100, 1100, 1600), rotation=23,
                 insertion="Face superior")
        d.OffsetX, d.OffsetY = 12, -7
        d.StartAdjustmentMode = "Fixed"
        d.StartAdjustmentGeometryMode = "PlaneCut"
        d.StartFixedReferenceOffset = 100
        d.StartFixedPlaneNormal = App.Vector(.3, 0, 1)
        parent = doc.addObject("App::Part", "TransformedParent")
        parent.addObject(d)
        parent.Placement = App.Placement(App.Vector(300, 500, 200),
                                         App.Rotation(App.Vector(1, 2, 3), 31))
        outer = doc.addObject("App::Part", "OuterParent")
        outer.addObject(parent)
        outer.Placement = App.Placement(App.Vector(100, -200, 80),
                                        App.Rotation(App.Vector(0, 0, 1), 17))
        external = doc.addObject("Part::Feature", "ExternalContext")
        external.Shape = Part.makeBox(400, 250, 100, App.Vector(700, 1700, 0))
        doc.recompute()
        names = [o.Name for o in (a, b, c, d)]
        # Warm the native App::Part display cache before taking an invariant
        # baseline. FreeCAD lazily adds _Part_ShapeCache on first render.
        Gui.getDocument(doc.Name).activeView().fitAll()
        Gui.updateGui()
        flush_events()
        doc.saveAs(str(out / "before.FCStd"))
        # App.saveAs persists the data document; the native GUI Save also
        # acknowledges pending view-provider changes in GuiDocument.Modified.
        flush_events()
        Gui.runCommand("Std_Save", 0)
        flush_events()
        # Snapshot's shape queries also initialize native container/TopoDS caches.
        # Stabilize them before the comparison and prove the baseline repeats.
        snapshot(doc)
        original = snapshot(doc)
        check("native snapshot baseline is stable before activation", snapshot(doc) == original)
        undo, clean = doc.UndoCount, not Gui.getDocument(doc.Name).Modified
        check("fixture saved clean", clean)
        api.activate()
        check("activation defaults to no overlays", api.state(doc) == (False, False))
        check("registered commands active for live 3D document", all(
            command.IsActive() for command in commands.values()))
        pump_until(lambda: all(action.isEnabled() for action in actions.values()))
        actions["axes"].trigger()
        actions["endpoints"].trigger()
        pump_until(lambda: doc.Name in api.service._sessions
                   and all(name in session(doc).axes for name in names) and bool(layers(doc)))
        check("native QAction trigger drives the actual service", api.state(doc) == (True, True))
        check("native QAction checks reflect document state", commands_match(doc))
        for obj in (a, b, c, d):
            check(obj.Name + " nominal endpoints in world frame", axis_matches(doc, obj))
        check("PlaneCut preserves nominal endpoint separate from physical", not near(
            nominal(d)[0], d.getGlobalPlacement().Base))
        check("external Part is not an axis source", external.Name not in session(doc).axes)
        toggle_state = snapshot(doc)
        (out / "toggle-before.json").write_text(json.dumps(original, indent=2), encoding="utf-8")
        (out / "toggle-after.json").write_text(json.dumps(toggle_state, indent=2), encoding="utf-8")
        check("toggle preserves all fixture data and visual properties", toggle_state == original)
        check("toggle creates no Undo or document dirty flag", doc.UndoCount == undo
              and not Gui.getDocument(doc.Name).Modified)
        defined_markers = coin.SoMarkerSet.getNumDefinedMarkers()
        for cycle in range(20):
            owned = [(layer.scene_graph, layer.node) for layer in layers(doc)]
            actions["axes"].trigger()
            actions["endpoints"].trigger()
            flush_events()
            check("cycle %d all-off releases observers and timers" % cycle, alloff())
            check("cycle %d all-off detaches owned roots" % cycle, all(
                scene.findChild(root) < 0 for scene, root in owned))
            check("cycle %d QAction checks reset" % cycle, commands_match(doc))
            actions["axes"].trigger()
            actions["endpoints"].trigger()
            pump_until(lambda: len(session(doc).axes) == 4 and bool(layers(doc)))
        check("twenty toggle cycles preserve data/Undo/dirty state", snapshot(doc) == original
              and doc.UndoCount == undo and not Gui.getDocument(doc.Name).Modified)
        check("repeated layers reuse their registered circular bitmaps",
              coin.SoMarkerSet.getNumDefinedMarkers() == defined_markers)
        for layer in layers(doc):
            scale = api._display_scale()
            check("refined axis width and clean dash match display scale", all(
                math.isclose(style.lineWidth.getValue(), width*scale, abs_tol=1e-6)
                and style.linePattern.getValue() == api.AXIS_PATTERN
                and style.linePatternScaleFactor.getValue() == max(1, round(2*scale))
                for style, width in zip(layer._line_styles, (4.5, 2.5))))
            check("endpoints use three shared circular contour/fill passes", len(layer._markers) == 3
                  and all(node.markerIndex.getNum() == 1 for node in layer._markers)
                  and all((int(round(size*scale)) | 1) in api._CIRCLE_MARKERS
                          for size in api.ENDPOINT_DIAMETERS))
            nodes = list(coin_nodes(layer.root))
            check("overlay explicitly unpickable", any(node.isOfType(coin.SoPickStyle.getClassTypeId())
                  and node.style.getValue() == coin.SoPickStyle.UNPICKABLE for node in nodes))
            check("overlay has no on-top annotation", not any(
                node.isOfType(coin.SoAnnotation.getClassTypeId()) for node in nodes))
            check("overlay explicitly preserves depth testing", any(
                node.isOfType(coin.SoDepthBuffer.getClassTypeId())
                and bool(node.test.getValue()) and not bool(node.getField("write").getValue()) for node in nodes))
            check("axis and endpoint switches independently on", layer.line_switch.whichChild.getValue()
                  != coin.SO_SWITCH_NONE and layer.point_switch.whichChild.getValue() != coin.SO_SWITCH_NONE)
        Gui.Selection.clearSelection()
        Gui.Selection.addSelection(a)
        api.toggle("axes", False)
        check("toggle preserves native selection", [o.Name for o in Gui.Selection.getSelection()] == [a.Name])
        check("axis toggle leaves endpoints on", api.state(doc) == (False, True))
        api.toggle("axes", True)
        Gui.Selection.clearSelection()
        reads = session(doc).geometry_reads
        cached = dict(session(doc).axes)
        a.ViewObject.Visibility = False
        pump_until(lambda: coordinate_count(doc) == [6] * len(layers(doc)))
        check("member visibility filters batch without rereading axes", session(doc).geometry_reads == reads
              and all(session(doc).axes[name] is value for name, value in cached.items()))
        parent.ViewObject.Visibility = False
        pump_until(lambda: coordinate_count(doc) == [4] * len(layers(doc)))
        check("parent visibility filters descendant without geometry resolve", session(doc).geometry_reads == reads)
        a.ViewObject.Visibility = True
        parent.ViewObject.Visibility = True
        pump_until(lambda: coordinate_count(doc) == [8] * len(layers(doc)))
        check("visibility restore reuses the nominal cache", session(doc).geometry_reads == reads)
        view = Gui.getDocument(doc.Name).activeView()
        view.viewTop()
        view.fitAll()
        flush_events()
        pos = view.getPointOnScreen(App.Vector(1000, 0, 75))
        hits = view.getObjectsInfo((int(pos[0]), int(pos[1]))) or []
        check("physical member remains mouse-pickable under overlay", any(
            hit.get("Object") == a.Name for hit in hits))
        view.saveImage(str(out / "top-depth.png"), 1600, 900)
        view.viewAxonometric()
        view.fitAll()
        view.saveImage(str(out / "axonometric.png"), 1600, 900)
        # Expose the nominal axis beside a deliberately eccentric section,
        # preserving ordinary depth testing. This is presentation evidence,
        # not an X-Ray implementation or a visual approval assertion.
        old_offset = a.OffsetX.Value
        a.OffsetX = 220
        doc.recompute()
        flush_events()
        view.viewTop()
        view.fitAll()
        view.saveImage(str(out / "eccentric-axis-visible.png"), 1600, 900)
        Gui.getMainWindow().grab().save(str(out / "workbench-controls.png"))
        a.OffsetX = old_offset
        doc.recompute()
        flush_events()

        unchanged = session(doc).axes[b.Name]
        doc.openTransaction("Change nominal endpoint")
        a.EndPoint = App.Vector(2400, 0, 0)
        doc.recompute()
        doc.commitTransaction()
        wait_axis(doc, a)
        check("queued update preserves unrelated axis record", session(doc).axes[b.Name] is unchanged)
        doc.undo()
        a = doc.getObject(names[0])
        wait_axis(doc, a)
        check("Undo refreshes without manual recompute", near(a.EndPoint, (2000, 0, 0)))
        doc.redo()
        a = doc.getObject(names[0])
        wait_axis(doc, a)
        check("Redo refreshes without manual recompute", near(a.EndPoint, (2400, 0, 0)))
        parent.Placement.Base = App.Vector(1000, 500, 200)
        doc.recompute()
        wait_axis(doc, d)
        check("parent move invalidates descendant world axis", axis_matches(doc, d))
        old_axis = session(doc).axes[a.Name]
        a.Label = "Nome personalizado extenso sem mudança geométrica"
        a.ViewObject.ShapeColor = (.3, .5, .7)
        flush_events()
        check("label/color preserves cached geometric value", session(doc).axes[a.Name] == old_axis)
        deleted = b.Name
        doc.openTransaction("Delete member")
        doc.removeObject(deleted)
        doc.commitTransaction()
        pump_until(lambda: deleted not in session(doc).axes)
        check("delete clears axis", deleted not in session(doc).axes)
        check("delete shrinks aggregate coordinates without stale tail", coordinate_count(doc) == [6] * len(layers(doc)))
        for layer in layers(doc):
            check("delete shrinks line and marker arrays", all(
                node.numVertices.getNum() == 3 for node in coin_nodes(layer.root)
                if node.isOfType(coin.SoLineSet.getClassTypeId())) and all(
                node.numPoints.getValue() == 6 for node in coin_nodes(layer.root)
                if node.isOfType(coin.SoMarkerSet.getClassTypeId())))
        doc.undo()
        b = doc.getObject(deleted)
        wait_axis(doc, b)
        check("Undo deletion readquires member", axis_matches(doc, b))

        gui_doc = Gui.getDocument(doc.Name)
        before_views = list(gui_doc.mdiViewsOfType("Gui::View3DInventor"))
        mdi = Gui.getMainWindow().findChild(QtWidgets.QMdiArea)
        original_window = mdi.activeSubWindow()
        second = gui_doc.createView("Gui::View3DInventor")
        second_window = mdi.activeSubWindow()
        pump_until(lambda: len(layers(doc)) == len(before_views) + 1)
        check("new 3D view receives its own overlay", len(layers(doc)) == len(before_views)+1)
        second.viewAxonometric()
        second.fitAll()
        second.saveImage(str(out / "second-view.png"), 1200, 800)
        mdi.setActiveSubWindow(original_window)
        pump_until(lambda: gui_doc.activeView() == before_views[0])
        check("second viewport is inactive before closure", mdi.activeSubWindow() != second_window)
        second_window.close()
        pump_until(lambda: len(layers(doc)) == len(before_views))
        check("closing a view cleans only its layer", len(layers(doc)) == len(before_views))

        other = App.newDocument("ReferenceOtherDocument")
        other_member = make(other, (0, 0, 0), (1000, 200, 300))
        check("new document starts with its own flags off", api.state(other) == (False, False))
        pump_until(lambda: commands_match(other))
        check("QAction checks follow newly active document", commands_match(other))
        actions["endpoints"].trigger()
        pump_until(lambda: bool(layers(other)))
        check("document toggles remain independent", api.state(doc) == (True, True)
              and api.state(other) == (False, True))
        check("configured documents retain independent view layers", bool(layers(doc)) and bool(layers(other)))
        App.setActiveDocument(doc.Name)
        pump_until(lambda: bool(layers(doc)) and bool(layers(other)))
        pump_until(lambda: commands_match(doc))
        check("QAction checks follow restored document flags", commands_match(doc))
        check("reactivation restores flags and data", api.state(doc) == (True, True)
              and axis_matches(doc, a))
        App.closeDocument(other.Name)
        pump_until(lambda: "ReferenceOtherDocument" not in api.service._sessions)
        check("closed document releases session", "ReferenceOtherDocument" not in api.service._sessions)

        # Persistence fixture starts from valid recomputed sources. Native
        # Touched flags left by replay are tested above, not serialized as a
        # claim that a new GUI session can certify unknown pending geometry.
        doc.recompute()
        flush_events()
        expected = snapshot(doc)
        expected_shapes = {obj.Name: obj.Shape.copy() for obj in doc.Objects if hasattr(obj, "Shape")}
        doc.saveAs(str(out / "active-overlay.FCStd"))
        check("save with overlay preserves objects and physical properties", snapshot(doc) == expected)
        api.deactivate()
        check("deactivate removes all sessions", not api.service._sessions)
        App.closeDocument(doc.Name)
        restored = App.openDocument(str(out / "active-overlay.FCStd"))
        actual = snapshot(restored)
        (out / "fcstd-before.json").write_text(json.dumps(expected, indent=2), encoding="utf-8")
        (out / "fcstd-after.json").write_text(json.dumps(actual, indent=2), encoding="utf-8")
        def without_brep(rows):
            result = {name: {key: value for key, value in row.items() if key != "brep"}
                      for name, row in rows.items()}
            for row in result.values():
                # FreeCAD's lazily synthesized App::Part cache is not persisted.
                row["properties"] = [p for p in row["properties"] if p != "_Part_ShapeCache"]
            return result
        def restored_equal(a, b, color=False):
            if isinstance(a, dict) and isinstance(b, dict):
                return a.keys() == b.keys() and all(restored_equal(
                    a[key], b[key], key.endswith("Color")) for key in a)
            if isinstance(a, list) and isinstance(b, list):
                return len(a) == len(b) and all(restored_equal(x, y, color) for x, y in zip(a, b))
            if isinstance(a, (int, float)) and isinstance(b, (int, float)):
                # Native FCStd stores view colors at 8-bit precision and
                # normalizes quaternions. Toggle tests above remain exact.
                return math.isclose(a, b, rel_tol=1e-9, abs_tol=1/255+1e-7 if color else 1e-6)
            return a == b
        check("FCStd contains no overlay objects or properties", restored_equal(
            without_brep(actual), without_brep(expected)))
        for name, shape in expected_shapes.items():
            restored_shape = restored.getObject(name).Shape
            check(name + " FCStd physical solid unchanged", shape.cut(restored_shape).Volume < 1e-5
                  and restored_shape.cut(shape).Volume < 1e-5)
        api.activate()
        check("reopened document has no persisted mode flags", api.state(restored) == (False, False))
        api.toggle("axes", True)
        pump_until(lambda: all(name in session(restored).axes for name in names))
        check("reopened document rebuilds references from physical members", len(session(restored).axes) == 4)
        owned = [(layer.scene_graph, layer.node) for layer in layers(restored)]
        Gui.activateWorkbench("PartWorkbench")
        pump_until(alloff)
        check("real workbench Deactivated releases sessions and observers", alloff())
        check("deactivation detaches only owned roots", all(scene.findChild(root) < 0 for scene, root in owned))
        Gui.activateWorkbench("SteelStructuresWorkbench")
        flush_events()
        check("real workbench reactivation leaves modes off", api.state(restored) == (False, False))
        api.deactivate()
        check("deactivation is idempotent", not api.service._sessions)
        App.closeDocument(restored.Name)

        # This is a real Draft Line and a genuinely linked parametric member;
        # refusal must not change either object or masquerade as Independent.
        import Draft
        linked_doc = App.newDocument("ReferenceLinkedExcluded")
        source = Draft.make_line(App.Vector(0, 0, 0), App.Vector(1800, 200, 0))
        linked_doc.recompute()
        linked = create_member(linked_doc, source.Start, source.End, "W 150 x 13,0",
                               axis_source=source, link_axis=True)
        linked_doc.recompute()
        snapshot(linked_doc)
        linked_before = snapshot(linked_doc)
        api.activate()
        api.toggle("axes", True)
        pump_until(lambda: linked.Name in session(linked_doc).rejected)
        check("real Linked member is refused with explicit reason", str(linked.AxisDefinitionMode) == "Linked"
              and linked.Name not in session(linked_doc).axes
              and "vinculado" in session(linked_doc).rejected[linked.Name].lower())
        check("Linked refusal preserves source and physical member", snapshot(linked_doc) == linked_before)
        api.deactivate()
        App.closeDocument(linked_doc.Name)

        pending_doc = App.newDocument("ReferenceReuseName")
        pending_member = make(pending_doc, (0, 0, 0), (500, 0, 0))
        reused_document_name = pending_doc.Name
        api.activate()
        api.toggle("axes", True)
        check("toggle schedules a deferred refresh", api.service._flush_timer is not None
              and api.service._flush_timer.isActive())
        api.deactivate()  # Deliberately before returning to the Qt queue.
        flush_events()
        check("pending refresh cannot resurrect deactivated session", alloff())
        App.closeDocument(pending_doc.Name)
        replacement_doc = App.newDocument(reused_document_name)
        replacement_member = make(replacement_doc, (7000, 500, 0), (7800, 500, 0))
        check("native document Name was reused for fixture", replacement_doc.Name == reused_document_name)
        api.activate()
        check("replacement document has no stale flags", api.state(replacement_doc) == (False, False))
        api.toggle("axes", True)
        wait_axis(replacement_doc, replacement_member)
        check("same-name replacement resolves new geometry", near(
            session(replacement_doc).axes[replacement_member.Name].start, (7000, 500, 0)))
        replacement_member.EndPoint = App.Vector(8000, 500, 0)
        # Closing with a pending dirty update must not retain any Qt callback
        # capable of querying the closed object's wrapper.
        api.deactivate()
        App.closeDocument(replacement_doc.Name)
        flush_events()
        check("queued dirty update dies with session and document", alloff())

        generated = App.newDocument("ReferenceTruss")
        generated.UndoMode = 1
        config = truss.default_config()
        config.update(span=6000., end=[6000., 0., 0.], height=1600., panel_count=4)
        owner = truss.apply_truss(generated, config)
        children = list(owner.GeneratedMembers)
        api.activate()
        api.toggle("axes", True)
        pump_until(lambda: len(session(generated).axes) == len(children))
        check("valid truss physical children supply axes without a second graph", all(
            axis_matches(generated, child) for child in children))
        old_truss_axes = dict(session(generated).axes)
        owner_name = owner.Name
        changed_config = dict(config, height=1850.)
        truss.apply_truss(generated, changed_config, owner)
        pump_until(lambda: all(axis_matches(generated, child) for child in owner.GeneratedMembers)
                   and session(generated).axes != old_truss_axes)
        check("truss reapply updates accepted physical child axes", owner.GenerationState == "Valid")
        updated_truss_axes = dict(session(generated).axes)
        # Only fingerprints of these previously accepted clean states authorize
        # replay. Unknown pending trusses remain refused by the reader tests.
        metrics["truss_replay"] = []
        for label, replay, target in (("Undo", generated.undo, old_truss_axes),
                                      ("Redo", generated.redo, updated_truss_axes)):
            replay()
            owner = generated.getObject(owner_name)
            children = list(owner.GeneratedMembers)
            pump_until(lambda: session(generated).axes == target)
            native_pending = any("Touched" in obj.State for obj in (owner, *children))
            check("truss " + label + " known replay updates without recompute", session(generated).axes == target)
            metrics["truss_replay"].append(dict(action=label, native_touched=native_pending,
                state="known clean fingerprint restored; no recompute"))
        api.deactivate()
        App.closeDocument(generated.Name)

        # Use real generated physical members to measure the shared owner-read
        # context. Instrument only the read boundary, forwarding unchanged data.
        from freecad.SteelStructures import structural_reference as reader
        truss_perf = App.newDocument("ReferenceTrussPerformance")
        large_config = truss.default_config()
        large_config.update(span=60000., end=[60000., 0., 0.], height=2500., panel_count=50)
        for spec in large_config["role_specs"].values():
            spec.update(physical_fit="None", section_geometry_mode="Simplified")
        started = time.perf_counter()
        large_owner = truss.apply_truss(truss_perf, large_config)
        create_ms = (time.perf_counter()-started)*1000
        child_count = len(large_owner.GeneratedMembers)
        owner_reads = []
        original_read_owner = reader._read_owner
        def counted_read_owner(owner, document, **kwargs):
            owner_reads.append(owner.Name)
            return original_read_owner(owner, document, **kwargs)
        reader._read_owner = counted_read_owner
        try:
            api.activate()
            started = time.perf_counter()
            api.toggle("axes", True)
            api.toggle("endpoints", True)
            pump_until(lambda: len(session(truss_perf).axes) == child_count and bool(layers(truss_perf)), timeout=30)
            overlay_ms = (time.perf_counter()-started)*1000
        finally:
            reader._read_owner = original_read_owner
        check("large truss fixture exercises at least one hundred physical children", child_count >= 100)
        check("one shared batch context reads generated owner once", owner_reads == [large_owner.Name])
        metrics["truss_performance"] = dict(panels=50, physical_children=child_count,
            create_ms=create_ms, initial_overlay_ms=overlay_ms, owner_reads=len(owner_reads),
            resolved_axes=session(truss_perf).geometry_reads)
        api.deactivate()
        App.closeDocument(truss_perf.Name)

        metrics["performance"] = []
        for count in (100, 1000):
            perf_doc = App.newDocument("ReferencePerformance" + str(count))
            started = time.perf_counter()
            members = [make(perf_doc, ((i % 50)*300, (i//50)*300, 0),
                            ((i % 50)*300, (i//50)*300, 2000),
                            section_geometry_mode="Simplified", recompute=False) for i in range(count)]
            perf_doc.recompute()
            create_ms = (time.perf_counter()-started)*1000
            api.activate()
            started = time.perf_counter()
            api.toggle("axes", True)
            api.toggle("endpoints", True)
            pump_until(lambda: len(session(perf_doc).axes) == count and bool(layers(perf_doc)), timeout=30)
            init_ms = (time.perf_counter()-started)*1000
            retained = session(perf_doc).axes[members[-1].Name]
            started = time.perf_counter()
            members[0].EndPoint = members[0].EndPoint + App.Vector(0, 0, 10)
            perf_doc.recompute()
            wait_axis(perf_doc, members[0])
            update_ms = (time.perf_counter()-started)*1000
            check(str(count) + " members have one axis each", len(session(perf_doc).axes) == count)
            check(str(count) + " edit retains unrelated cached axis", session(perf_doc).axes[members[-1].Name] is retained)
            metrics["performance"].append(dict(members=count, create_ms=create_ms,
                initial_overlay_ms=init_ms, one_edit_with_recompute_ms=update_ms,
                coin_nodes=sum(len(list(coin_nodes(layer.root))) for layer in layers(perf_doc))))
            started=time.perf_counter()
            api.set_mode("xray")
            api.refresh_now()
            metrics["performance"][-1]["xray_initial_ms"]=(time.perf_counter()-started)*1000
            presentation=layers(perf_doc)[0].presentation
            metrics["performance"][-1]["reference_top_nodes"]=len(list(coin_nodes(layers(perf_doc)[0].node)))
            metrics["performance"][-1]["xray_copy_nodes"]=len(list(coin_nodes(presentation.clone)))
            copies=presentation.copy_updates
            for j in range(3):
                Gui.Selection.setPreselection(members[j],"Face1",0.,0.,0.)
                api.refresh_now()
                Gui.Selection.clearSelection()  # Native API also clears preselection.
                api.refresh_now()
            check(str(count)+" preselection does not rebuild xray copy",presentation.copy_updates==copies)
            api.deactivate()
            App.closeDocument(perf_doc.Name)
        api.activate()
        check("commands inactive without an active document", App.ActiveDocument is None
              and all(not command.IsActive() for command in commands.values()))
        api.deactivate()
        check("final shutdown has no sessions observers or timers", alloff())
        screen = QtWidgets.QApplication.primaryScreen()
        metrics["screen"] = dict(dpr=screen.devicePixelRatio(), logical_dpi=screen.logicalDotsPerInch())
        visual_refinement_gallery(out, check, api)
        from tests.manual_structural_display_modes import run as run_display_modes
        metrics["display_modes"] = run_display_modes(out, check, api, (snapshot, flush_events, pump_until))
        from tests.manual_structural_reference_on_top import run as run_on_top
        metrics["reference_on_top"] = run_on_top(out, check, api, (snapshot, flush_events, pump_until))
        origins = {name: str(Path(module.__file__).resolve()) for name,module in tuple(sys.modules.items())
                   if (name.startswith("freecad.SteelStructures") or name=="SteelStructures"
                       or name.startswith("SteelStructures.") or name in (
                           "tests.manual_structural_display_modes", "tests.manual_structural_reference_on_top"))
                   and getattr(module,"__file__",None)}
        (out/"module-origins.json").write_text(json.dumps(origins,indent=2),encoding="utf-8")
        source_root = Path(os.environ["SS_STRUCTURAL_REFERENCE_ROOT"]).resolve()
        check("all loaded workbench modules originate in the isolated source tree", bool(origins)
              and all(Path(path).is_relative_to(source_root) for path in origins.values()))
        check("no Python/Qt callback errors", not errors)
        return dict(ok=True, version=App.Version()[:3], theme=os.environ.get("SS_STRUCTURAL_REFERENCE_THEME"),
                    checks=checks, callback_errors=errors, metrics=metrics,
                    visual_review="Screenshots require separate inspection; physical overlay and transient display modes.")
    finally:
        api.deactivate()
        if toolbar is not None:
            Gui.getMainWindow().removeToolBar(toolbar)
            toolbar.deleteLater()
        sys.excepthook = original_hook
        (out / "callback-errors.json").write_text(json.dumps(errors, indent=2), encoding="utf-8")
        (out / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")


if os.environ.get("SS_STRUCTURAL_REFERENCE_ROOT"):
    import FreeCAD as App
    from PySide import QtCore, QtWidgets
    root = Path(os.environ["SS_STRUCTURAL_REFERENCE_ROOT"])
    out = Path(os.environ["SS_STRUCTURAL_REFERENCE_OUT"])
    sys.path.insert(0, str(root))
    import freecad
    freecad.__path__.insert(0, str(root / "freecad"))
    def launch():
        try:
            result = run(out)
        except Exception:
            result = dict(ok=False, error=traceback.format_exc())
        (out / "result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        for name in tuple(App.listDocuments()):
            App.closeDocument(name)
        QtCore.QTimer.singleShot(0, QtWidgets.QApplication.instance().quit)
    QtCore.QTimer.singleShot(0, launch)
