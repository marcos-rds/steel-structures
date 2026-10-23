# SPDX-License-Identifier: LGPL-2.1-or-later
"""Real FreeCAD regression scenario and Qt/Coin gate for adjustment Stage 1.

Use scripts/run_member_adjustment_stage1_gate.py; no user document is modified.
Reproduction mode records the original defect before production is changed.
"""
import json
import os
from pathlib import Path
import sys
import traceback


def risk_probe(out, check, fixed):
    import FreeCAD as App
    import Part
    from freecad.SteelStructures import truss, member
    from freecad.SteelStructures.member_batch import ADJUSTMENT_INPUTS
    from freecad.SteelStructures.interactive.member_adjustment_controller import MemberAdjustmentController
    from freecad.SteelStructures.trusses.physical_mass import read_physical_mass

    def plain(value):
        if isinstance(value, App.Vector):
            return list(value)
        if hasattr(value, "Value"):
            return float(value.Value)
        if isinstance(value, (tuple, list)):
            return [plain(v) for v in value]
        if hasattr(value, "Name"):
            return value.Name
        return value

    def state(obj, owner=None):
        result = dict(properties={key: plain(getattr(obj, key)) for key in ADJUSTMENT_INPUTS},
            volume=obj.Shape.Volume, bbox=[getattr(obj.Shape.BoundBox, key) for key in ("XMin", "YMin", "ZMin", "XMax", "YMax", "ZMax")],
            placement=list(obj.Placement.toMatrix().A), start=list(obj.StartPoint), end=list(obj.EndPoint),
            adjusted=float(obj.AdjustedLength.Value), mass=float(obj.TotalMass), status=getattr(obj, "GenerationStatus", None))
        if owner is not None:
            mass = read_physical_mass(owner)
            result.update(parent_state=owner.AppliedState, parent_status=owner.GenerationState,
                children=[o.Name for o in owner.GeneratedMembers], physical_mass=mass.mass_kg,
                physical_available=mass.available, physical_diagnostics=list(mass.diagnostics))
        return result

    cases = []
    for generated in (False, True):
        for geometry in ("LengthLimit", "PlaneCut"):
            for keep in (False, True):
                doc = App.newDocument("AdjustmentRisk")
                doc.UndoMode = 1
                owner = None
                if generated:
                    config = truss.default_config()
                    config.update(span=6000., end=[6000., 0., 0.], height=1600., panel_count=4)
                    owner = truss.apply_truss(doc, config)
                    obj = next(o for o in owner.GeneratedMembers if o.GenerationKey.startswith("DIAGONAL"))
                else:
                    obj = member.create_member(doc, App.Vector(), App.Vector(3000, 0, 0), "W 150 x 13,0")
                axis = obj.EndPoint.sub(obj.StartPoint)
                length = axis.Length
                axis.normalize()
                normal = axis
                if geometry == "PlaneCut":
                    normal = axis.add(obj.Placement.Rotation.multVec(App.Vector(.3, 0, 0)))
                reference = doc.addObject("Part::Feature", "ExternalReference")
                reference.Shape = Part.makePlane(2000, 2000, obj.StartPoint.add(axis * (length * .25)), normal)
                doc.recompute()
                before = state(obj, owner)
                undo_before = doc.UndoCount
                controller = MemberAdjustmentController(doc, obj)
                resolved = controller.validate(geometry_mode=geometry, end_choice="Start", gap=2 * length,
                    keep_reference=keep, reference=(reference, ["Face1"]))
                accepted, error = False, None
                try:
                    controller.apply(resolved)
                    accepted = True
                except Exception as exc:
                    error = str(exc)
                after = state(obj, owner)
                undo_after = doc.UndoCount
                record = dict(generated=generated, geometry=geometry, associative=keep,
                    accepted=accepted, error=error, before=before, after=after,
                    undo_before=undo_before, undo_after=undo_after)
                path = out / ("risk_" + str(len(cases)) + ".FCStd")
                name, parent_name = obj.Name, owner.Name if owner else None
                doc.saveAs(str(path))
                App.closeDocument(doc.Name)
                doc = App.openDocument(str(path))
                doc.recompute()
                obj = doc.getObject(name)
                owner = doc.getObject(parent_name) if parent_name else None
                record["restored"] = state(obj, owner)
                label = str((generated, geometry, keep))
                if fixed:
                    check("invalid rejected " + label, not accepted)
                    check("invalid preserves properties " + label, after["properties"] == before["properties"])
                    check("invalid preserves Shape " + label, after["volume"] == before["volume"] and after["bbox"] == before["bbox"])
                    check("invalid creates no Undo " + label, undo_before == undo_after)
                    check("invalid restores FCStd " + label, record["restored"]["properties"] == before["properties"])
                    check("invalid preserves all outputs/owner " + label, before == after)
                    check("invalid restored geometry " + label, abs(record["restored"]["volume"] - before["volume"]) < 1e-6)
                else:
                    check("baseline behavior " + label, accepted == generated)
                    if generated:
                        check("baseline child mutated despite failed geometry " + label,
                              after["properties"] != before["properties"] and str(after["status"]).startswith("Erro:"))
                        check("baseline preserves old Shape " + label, after["volume"] == before["volume"])
                        check("baseline persists invalid child " + label,
                              record["restored"]["properties"] == after["properties"])
                cases.append(record)
                App.closeDocument(doc.Name)
    (out / "risk-cases.json").write_text(json.dumps(cases, indent=2), encoding="utf-8")
    return cases


def run(out):
    import FreeCAD as App
    from PySide import QtCore, QtWidgets
    qss = os.environ.get("SS_ADJUST_QSS")
    if qss:
        path = Path(qss)
        QtCore.QDir.addSearchPath("qss", str(path.parent))
        QtWidgets.QApplication.instance().setStyleSheet(path.read_text(encoding="utf-8"))
    checks, qt_errors = [], []
    old = sys.excepthook
    sys.excepthook = lambda kind, error, trace: qt_errors.append("".join(traceback.format_exception(kind, error, trace)))

    def check(label, condition):
        if not condition:
            raise AssertionError(label)
        checks.append(label)
        (out / "checks.json").write_text(json.dumps(checks, indent=2), encoding="utf-8")

    try:
        phase = os.environ["SS_ADJUST_PHASE"]
        cases = risk_probe(out, check, phase != "reproduction") if phase != "preview-sync" else []
        if phase == "preview-sync":
            automatic_preview_probe(out, check)
        if phase == "stage1":
            automatic_preview_probe(out, check)
            ui_probe(out, check)
        check("no Qt callback errors", not qt_errors)
        return dict(ok=True, version=App.Version()[:3], phase=os.environ["SS_ADJUST_PHASE"],
                    theme=os.environ["SS_ADJUST_THEME"], checks=checks,
                    invalid_accepted=sum(row["accepted"] for row in cases), cases=len(cases))
    finally:
        sys.excepthook = old


def wait_preview_poll(panel):
    """Observe a real timer dispatch and its completed slots, not elapsed time.

    The runner's process watchdog fails a stalled event loop; it never grants
    success. A destroyed timer releases the loop for the close/delete checks.
    """
    import shiboken6
    from PySide import QtCore
    timer = panel._preview_timer
    if not shiboken6.isValid(timer):
        if not panel._closed:
            raise AssertionError("Preview timer destroyed before panel cleanup")
        return
    if not timer.isActive():
        raise AssertionError("Preview timer unexpectedly inactive")
    loop = QtCore.QEventLoop()
    timer.timeout.connect(loop.quit, QtCore.Qt.QueuedConnection)
    timer.destroyed.connect(loop.quit)
    try:
        loop.exec()
    finally:
        if shiboken6.isValid(timer):
            timer.timeout.disconnect(loop.quit)
            timer.destroyed.disconnect(loop.quit)


def assert_preview_current(out, panel, label, check, render=False):
    """Compare fresh BRep, panel state, exported Shape, Coin and rendered pixels."""
    import hashlib
    import math
    import FreeCAD as App
    import FreeCADGui as Gui
    from pivy import coin
    from PySide import QtGui
    from freecad.SteelStructures.interactive.member_adjustment_preview import MemberAdjustmentPreview
    expected = panel.controller.evaluate(panel._validate()).result
    actual = panel._candidate.result if panel._candidate else None
    preview = panel._preview
    near = lambda a, b: math.isclose(float(a), float(b), rel_tol=1e-8, abs_tol=1e-6)
    row = dict(label=label, expected_volume=expected.Shape.Volume,
               actual_volume=actual.Shape.Volume if actual else None,
               preview_volume=preview.shape.Volume if preview and preview.shape else None,
               signature=repr(panel._watch_state), timer_active=panel._preview_timer.isActive())
    with (out / "preview-sync.jsonl").open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(row) + "\n")
    check(label + " candidate", actual is not None and near(actual.Shape.Volume, expected.Shape.Volume))
    global_shape = expected.Shape.copy()
    global_shape.Placement = App.Placement(expected.Placement)
    check(label + " exported Shape", preview is not None and near(preview.shape.Volume, global_shape.Volume)
          and preview.shape.cut(global_shape).Volume < 1e-5 and global_shape.cut(preview.shape).Volume < 1e-5)
    scene, node = preview.scene_graph, preview.node
    check(label + " attached Coin", scene.findChild(node) >= 0)
    # Traverse the actual branch against a separately exported fresh candidate.
    data = coin.SoInput()
    data.setBuffer(global_shape.writeInventor())
    expected_node = coin.SoDB.readAll(data)
    def bounds(branch):
        action = coin.SoGetBoundingBoxAction(coin.SbViewportRegion(800, 600))
        action.apply(branch)
        box = action.getBoundingBox()
        return list(box.getMin().getValue()) + list(box.getMax().getValue())
    check(label + " Coin geometry", all(abs(a-b) < 1e-4 for a, b in zip(bounds(node), bounds(expected_node))))
    if render:
        view = Gui.activeDocument().activeView()
        view.redraw()
        actual_path = out / (label + "-actual.png")
        absent_path = out / (label + "-without-preview.png")
        expected_path = out / (label + "-expected.png")
        view.saveImage(str(actual_path), 800, 600, "White")
        transient = MemberAdjustmentPreview(scene)
        scene.removeChild(node)
        try:
            view.redraw()
            view.saveImage(str(absent_path), 800, 600, "White")
            transient.update(panel.controller.member, expected)
            view.redraw()
            view.saveImage(str(expected_path), 800, 600, "White")
        finally:
            transient.clear()
            scene.addChild(node)
        def pixels(path):
            image = QtGui.QImage(str(path))
            if image.isNull():
                raise AssertionError("Native viewport capture failed")
            return hashlib.sha256(image.constBits().tobytes()).hexdigest()
        check(label + " viewport pixels", pixels(actual_path) == pixels(expected_path))
        check(label + " visible preview pixels", pixels(actual_path) != pixels(absent_path))


def automatic_preview_probe(out, check):
    """Deterministic regression for changed global supports with equal hashes."""
    import FreeCAD as App
    import FreeCADGui as Gui
    import Part
    import shiboken6
    from PySide import QtCore, QtWidgets
    from freecad.SteelStructures import member, truss
    from freecad.SteelStructures.interactive.member_adjustment_controller import MemberAdjustmentController
    from freecad.SteelStructures.interactive.member_adjustment_task_panel import MemberAdjustmentTaskPanel

    original_signature = MemberAdjustmentTaskPanel._reference_signature
    def collided_signature(panel):
        value = original_signature(panel)
        if value is None:
            return None
        # Model the observed native hash equality; retain every other component.
        geometry = tuple((*row[:2], 0, *row[3:]) for row in value[4])
        return (*value[:4], geometry, *value[5:])

    doc = App.newDocument("AdjustmentAutoPreview")
    doc.UndoMode = 1
    independent = member.create_member(doc, App.Vector(), App.Vector(1000, 0, 0), "W 150 x 13,0")
    config = truss.default_config()
    config.update(span=6000., start=[0., 2500., 0.], end=[6000., 2500., 0.], height=1600., panel_count=4)
    owner = truss.apply_truss(doc, config)
    child = next(o for o in owner.GeneratedMembers if o.GenerationKey.startswith("DIAGONAL"))
    axis = child.EndPoint.sub(child.StartPoint)
    end_ref = doc.addObject("Part::Feature", "FixedEnd")
    end_ref.Shape = Part.makePlane(1500, 1500, child.StartPoint.add(axis*.8), axis)
    tool = MemberAdjustmentController(doc, child)
    tool.apply(tool.validate(geometry_mode="PlaneCut", end_choice="End", gap=15,
                            keep_reference=False, reference=(end_ref, ["Face1"])))
    panel = None
    try:
        for collision in (True, False):
            MemberAdjustmentTaskPanel._reference_signature = collided_signature if collision else original_signature
            for number, obj in enumerate((independent, child)):
                # Reopen after cancellation, exercising a new timer and observer.
                for session in range(2):
                    def closed(panel, _accepted):
                        if panel.form is not None:
                            Gui.Control.closeDialog()
                    panel = MemberAdjustmentTaskPanel(doc, obj, closed)
                    Gui.Control.showDialog(panel)
                    direction = obj.EndPoint.sub(obj.StartPoint)
                    point = obj.StartPoint.add(direction*.2)
                    direction.normalize()
                    ref = doc.addObject("Part::Feature", "SyncReference")
                    ref.Shape = Part.makePlane(1500, 1500, point, direction)
                    ref.ViewObject.Visibility = False
                    transverse = obj.Placement.Rotation.multVec(App.Vector(1, 0, 0))
                    edge_ref = doc.addObject("Part::Feature", "SyncEdge")
                    edge_ref.Shape = Part.makeLine(point.sub(transverse*100), point.add(transverse*100))
                    edge_ref.ViewObject.Visibility = False
                    doc.recompute()
                    panel.end_choice.setCurrentText("Início")
                    panel.geometry_mode.setCurrentText("Limitar comprimento")
                    panel.keep_reference.setChecked(True)
                    panel._begin_capture("reference")
                    Gui.Selection.clearSelection()
                    Gui.Selection.addSelection(doc.Name, ref.Name, "Face1")
                    QtWidgets.QApplication.processEvents()
                    before = (obj.Shape.Volume, tuple(obj.StartPoint), tuple(obj.EndPoint), doc.UndoCount,
                              tuple(o.Name for o in doc.Objects))
                    view = Gui.activeDocument().activeView()
                    view.viewAxonometric()
                    view.fitAll()
                    for step, (distance, gap) in enumerate(((20., 15.), (-30., -5.), (0., 0.))):
                        label = "sync-%s-%s-%s-%s" % (collision, number, session, step)
                        panel.gap.setValue(gap)
                        panel.geometry_mode.setCurrentText("Recortar pelo plano" if step == 1 else "Limitar comprimento")
                        if step == 1:
                            ref.Shape = Part.makePlane(1500, 1500, point, direction.add(transverse*.2))
                        moved = App.Placement(ref.Placement)
                        moved.Base = direction * distance
                        ref.Placement = moved
                        doc.recompute()
                        wait_preview_poll(panel)
                        assert_preview_current(out, panel, label, check, render=(step == 0))
                        check(label + " original/Undo/tree", before == (
                            obj.Shape.Volume, tuple(obj.StartPoint), tuple(obj.EndPoint), doc.UndoCount,
                            tuple(o.Name for o in doc.Objects)))
                    panel._begin_capture("reference")
                    Gui.Selection.clearSelection()
                    Gui.Selection.addSelection(doc.Name, edge_ref.Name, "Edge1")
                    QtWidgets.QApplication.processEvents()
                    for edge_step in range(2):
                        moved = App.Placement(edge_ref.Placement)
                        moved.Base = direction * (20 if edge_step == 0 else -10)
                        edge_ref.Placement = moved
                        doc.recompute()
                        wait_preview_poll(panel)
                        label = "edge-%s-%s-%s-%s" % (collision, number, session, edge_step)
                        assert_preview_current(out, panel, label, check, render=(edge_step == 0))
                        check(label + " original/Undo/tree", before == (
                            obj.Shape.Volume, tuple(obj.StartPoint), tuple(obj.EndPoint), doc.UndoCount,
                            tuple(o.Name for o in doc.Objects)))
                    old = panel._preview
                    node, scene = old.node, old.scene_graph
                    if session:
                        # Deliver Esc through the real form event filter.
                        from PySide6 import QtTest
                        panel.gap.setFocus()
                        QtTest.QTest.keyClick(panel.gap, QtCore.Qt.Key_Escape)
                    else:
                        panel.reject()
                    QtWidgets.QApplication.processEvents()
                    check("sync cleanup %s-%s-%s" % (collision, number, session), panel._closed
                          and panel._selection_observer is None and scene.findChild(node) < 0
                          and (not shiboken6.isValid(panel._preview_timer) or not panel._preview_timer.isActive()))
                    panel = None
    finally:
        if panel is not None:
            panel.reject()
        MemberAdjustmentTaskPanel._reference_signature = original_signature
        App.closeDocument(doc.Name)


def ui_probe(out, check):
    import math
    import FreeCAD as App
    import FreeCADGui as Gui
    import Part
    import shiboken6
    from PySide import QtCore, QtWidgets
    from PySide6 import QtTest
    from freecad.SteelStructures import member, truss, profile_catalog, commands
    from freecad.SteelStructures.member_batch import ADJUSTMENT_INPUTS
    from freecad.SteelStructures.interactive.member_adjustment_task_panel import MemberAdjustmentTaskPanel
    from freecad.SteelStructures.interactive.member_adjustment_controller import MemberAdjustmentController, AdjustmentValidationError
    from freecad.SteelStructures.trusses.physical_mass import read_physical_mass

    def drain():
        QtWidgets.QApplication.processEvents()

    def near(a, b):
        return math.isclose(float(a), float(b), rel_tol=1e-8, abs_tol=1e-6)

    def snapshot(obj):
        def plain(value):
            # FCStd XML normalizes sub-picometer float noise.
            if isinstance(value, App.Vector):
                return tuple(round(v, 9) for v in value)
            if hasattr(value, "Value"):
                return round(float(value.Value), 9)
            return str(value)
        return (tuple(plain(getattr(obj, key)) for key in ADJUSTMENT_INPUTS), obj.Shape.Volume,
                list(obj.Placement.toMatrix().A), list(obj.StartPoint), list(obj.EndPoint),
                [float(obj.AdjustedLength.Value), float(obj.MemberLength.Value), float(obj.TotalMass)])

    def same(a, b):
        return (a[0] == b[0] and near(a[1], b[1]) and all(near(x, y) for x, y in zip(a[2], b[2]))
                and all(near(x, y) for x, y in zip(a[3] + a[4] + a[5], b[3] + b[4] + b[5])))

    def check_shape(label, actual, expected):
        keys = ("XMin", "YMin", "ZMin", "XMax", "YMax", "ZMax")
        with (out / "shape-comparisons.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(dict(label=label, actual_volume=actual.Volume, expected_volume=expected.Volume,
                actual_bbox=[getattr(actual.BoundBox, k) for k in keys],
                expected_bbox=[getattr(expected.BoundBox, k) for k in keys])) + "\n")
        check(label + " volume", near(actual.Volume, expected.Volume))
        def center(shape):
            return sum((s.CenterOfMass * s.Volume for s in shape.Solids), App.Vector()) / shape.Volume
        check(label + " center", center(actual).sub(center(expected)).Length < 1e-6)
        # Inventor export caches a mesh; curved OCC bounds may differ by microns.
        # Boolean symmetric difference below verifies the actual solid instead.
        check(label + " bbox", all(abs(getattr(actual.BoundBox, k) - getattr(expected.BoundBox, k)) < .01
              for k in ("XMin", "YMin", "ZMin", "XMax", "YMax", "ZMax")))
        check(label + " symmetric difference", actual.cut(expected).Volume < 1e-5 and expected.cut(actual).Volume < 1e-5)

    def grab(widget, name):
        drain()
        check("capture " + name, widget.grab().save(str(out / (name + ".png"))))

    def show(obj):
        def closed(panel, _accepted):
            if panel.form is not None:
                Gui.Control.closeDialog()
        panel = MemberAdjustmentTaskPanel(doc, obj, closed)
        Gui.Control.showDialog(panel)
        drain()
        return panel

    def configure(panel, obj, geometry="PlaneCut", slot="End", keep=True, edge=False,
                  inclined=True, fraction=None):
        axis = obj.EndPoint.sub(obj.StartPoint)
        length = axis.Length
        axis.normalize()
        point = obj.StartPoint.add(axis * (length * (fraction if fraction is not None else (.2 if slot == "Start" else .8))))
        normal = axis.add(obj.Placement.Rotation.multVec(App.Vector(.4, 0, 0))) if geometry == "PlaneCut" and inclined else axis
        ref = doc.addObject("Part::Feature", "UiReference")
        if edge:
            direction = obj.Placement.Rotation.multVec(App.Vector(1, 0, 0))
            ref.Shape = Part.makeLine(point.sub(direction * 100), point.add(direction * 100))
        else:
            ref.Shape = Part.makePlane(1200, 1200, point, normal)
        ref.ViewObject.Visibility = False
        doc.recompute()
        panel.end_choice.setCurrentText("Início" if slot == "Start" else "Fim")
        panel.geometry_mode.setCurrentText("Recortar pelo plano" if geometry == "PlaneCut" else "Limitar comprimento")
        panel.keep_reference.setChecked(keep)
        panel.gap.setValue(10)
        panel._begin_capture("reference")
        Gui.Selection.clearSelection()
        Gui.Selection.addSelection(doc.Name, ref.Name, "Edge1" if edge else "Face1")
        drain()
        check("reference captured", panel.reference is not None)
        return ref

    doc = App.newDocument("AdjustmentStage1Ui")
    doc.UndoMode = 1
    Gui.getMainWindow().resize(1500, 1000)
    targets = []
    rhs = next(p for p in profile_catalog.profiles().values() if p.definition.geometry_type == "hollow_section"
               and p.definition.geometry_variant == "rectangular")
    simple = next(p for p in profile_catalog.profiles().values() if p.definition.geometry_variant == "simple_u")
    for index, (profile, direction) in enumerate((("W 150 x 13,0", (1000, 0, 0)),
            (rhs.designation, (0, 0, 1000)), (simple.designation, (300, 400, 866.0254037844386)),
            ("W 150 x 13,0", (0, 1000, 0)))):
        start = App.Vector(index * 1600, 0, 0)
        obj = member.create_member(doc, start, start.add(App.Vector(*direction)), profile,
                                   element_type="Pilar" if index == 1 else "Membro", rotation=23)
        targets.append(obj)
    targets[0].OffsetX, targets[0].OffsetY = 12., -7.
    targets[0].StartExtension, targets[0].EndExtension = 30., 20.
    targets[3].SectionGeometryMode = "Simplified"
    # A full user section rotation through Placement must survive evaluation.
    rigid = App.Placement(App.Vector(), App.Rotation(App.Vector(0, 0, 1), 31))
    targets[1].Placement = targets[1].Placement.multiply(rigid)
    doc.recompute()
    config = truss.default_config()
    config.update(span=6000., start=[0., 2500., 0.], end=[6000., 2500., 0.], height=1600., panel_count=4)
    owner = truss.apply_truss(doc, config)
    child = next(o for o in owner.GeneratedMembers if o.GenerationKey.startswith("DIAGONAL"))
    targets.extend((child, child))
    Gui.activeDocument().activeView().viewAxonometric()
    Gui.activeDocument().activeView().fitAll()
    modes = (("PlaneCut", "End", True, False), ("PlaneCut", "Start", False, False),
             ("LengthLimit", "End", False, True), ("LengthLimit", "Start", True, False),
             ("PlaneCut", "End", False, False), ("LengthLimit", "Start", True, False))
    references = []
    for index, (obj, (geometry, slot, keep, edge)) in enumerate(zip(targets, modes)):
        panel = show(obj)
        ref = configure(panel, obj, geometry, slot, keep, edge)
        references.append(ref)
        check("candidate valid " + str(index), panel._candidate is not None and panel.isValid())
        old = snapshot(obj)
        names = tuple(o.Name for o in doc.Objects)
        undo = doc.UndoCount
        visibility = obj.ViewObject.Visibility
        check("source hidden only in Coin " + str(index), obj.ViewObject.SwitchNode.whichChild.getValue() == -1 and visibility)
        for gap in (0, -5, 15):
            panel.gap.setValue(gap)
            drain()
            check("preview preserves original " + str((index, gap)), same(snapshot(obj), old))
            check("preview preserves tree/Undo " + str((index, gap)), names == tuple(o.Name for o in doc.Objects) and undo == doc.UndoCount)
        if keep and not edge:
            before_volume = panel._candidate.result.Shape.Volume
            moved = App.Placement(ref.Placement)
            moved.Base = moved.Base.add(obj.Placement.Rotation.multVec(App.Vector(0, 0, 20)))
            ref.Placement = moved
            doc.recompute()
            wait_preview_poll(panel)
            assert_preview_current(out, panel, "reference-" + str(index), check)
            (out / ("reference-update-" + str(index) + ".json")).write_text(json.dumps(dict(
                error=panel._last_error, message=panel.validation_message.text(),
                before=before_volume, after=panel._candidate.result.Shape.Volume if panel._candidate else None,
                watch=str(panel._watch_state))), encoding="utf-8")
            check("external reference updates preview " + str(index), panel._candidate is not None
                  and not near(before_volume, panel._candidate.result.Shape.Volume))
            old = snapshot(obj)  # This recompute may legitimately update an existing associative slot.
        preview = panel._preview
        node, scene = preview.node, preview.scene_graph
        expected = preview.shape.copy()
        grab(panel.form, "panel-" + str(index))
        if index == 0:
            grab(Gui.getMainWindow(), "task-view")
            Gui.Selection.clearSelection()
            Gui.Selection.addSelection(obj)
            Gui.runCommand("Std_ViewFitSelection")
            Gui.Selection.clearSelection()
            Gui.activeDocument().activeView().saveImage(str(out / "candidate-viewport.png"), 1400, 900, "White")
            Gui.activeDocument().activeView().saveImage(str(out / "candidate-viewport-theme.png"), 1400, 900, "Current")
            Gui.activeDocument().activeView().fitAll()
        undo = doc.UndoCount
        check("OK succeeds " + str(index), panel.accept())
        drain()
        check_shape("preview equals committed " + str(index), obj.Shape, expected)
        check("OK cleanup " + str(index), panel._closed and panel._preview is None
              and (not shiboken6.isValid(panel._preview_timer) or not panel._preview_timer.isActive())
              and scene.findChild(node) < 0 and obj.ViewObject.Visibility == visibility)
        check("OK one Undo " + str(index), doc.UndoCount == undo + 1)
        doc.undo()
        doc.recompute()
        (out / ("undo-" + str(index) + ".json")).write_text(json.dumps(dict(before=old, after=snapshot(obj)), indent=2), encoding="utf-8")
        check("Undo restores original " + str(index), same(snapshot(obj), old))
        doc.redo()
        doc.recompute()
        check_shape("Redo restores candidate " + str(index), obj.Shape, expected)

    for label, target, geometry, fraction in (("perpendicular cut", targets[2], "PlaneCut", .8),
                                               ("axial extension", targets[3], "LengthLimit", 1.5)):
        old = snapshot(target)
        panel = show(target)
        configure(panel, target, geometry, "End", False, inclined=False, fraction=fraction)
        expected = panel._preview.shape.copy()
        check(label + " accepted", panel.accept())
        drain()
        check_shape(label, target.Shape, expected)
        if geometry == "LengthLimit":
            check("extended candidate keeps nominal length", near(target.MemberLength.Value, old[5][1])
                  and target.AdjustedLength.Value > target.MemberLength.Value)
        doc.undo()
        doc.recompute()
        check(label + " Undo", same(old, snapshot(target)))

    mass = read_physical_mass(owner)
    check("adjusted truss physical mass available", mass.available)
    check("adjusted truss physical mass equals solids", near(mass.mass_kg,
          sum(o.Shape.Volume for o in owner.GeneratedMembers) * 7.85e-6))
    # Re-evaluation and rollback must also protect failure after the transaction starts.
    for obj in (targets[1], child):
        controller = MemberAdjustmentController(doc, obj)
        before, undo = snapshot(obj), doc.UndoCount
        resolved = controller.validate_existing_fixed(geometry_mode="PlaneCut",
                    end_choice="Start" if obj is targets[1] else "End", gap=11)
        def fail_after_recompute(_candidate):
            raise AdjustmentValidationError("Injected late recompute failure")
        controller._verify_applied = fail_after_recompute
        rejected = False
        try:
            controller.apply(resolved)
        except AdjustmentValidationError:
            rejected = True
        doc.recompute()
        check("late failure rollback " + obj.Name, rejected and same(before, snapshot(obj)) and undo == doc.UndoCount)
    # Removal uses the same candidate pipeline and remains one reversible action.
    controller = MemberAdjustmentController(doc, child)
    before = snapshot(child)
    candidate = controller.evaluate_removal("Start")
    undo = doc.UndoCount
    controller.remove_adjustment("Start")
    check("removal candidate matches", near(child.Shape.Volume, candidate.result.Shape.Volume))
    check("removal keeps opposite slot", str(child.EndAdjustmentMode) == "Fixed" and doc.UndoCount == undo + 1)
    doc.undo()
    doc.recompute()
    check("removal Undo restores both slots", same(before, snapshot(child)))
    doc.redo()
    doc.recompute()
    doc.undo()
    doc.recompute()

    # Save and restore actual accepted adjustments (including both child slots).
    saved = {o.Name: snapshot(o) for o in targets}
    target_names, ref_names, owner_name = [o.Name for o in targets], [r.Name for r in references], owner.Name
    path = out / "valid-adjustments.FCStd"
    doc.saveAs(str(path))
    App.closeDocument(doc.Name)
    doc = App.openDocument(str(path))
    doc.UndoMode = 1
    doc.recompute()
    targets = [doc.getObject(name) for name in target_names]
    references = [doc.getObject(name) for name in ref_names]
    owner, child = doc.getObject(owner_name), targets[-1]
    for name, state in saved.items():
        (out / ("restored-" + name + ".json")).write_text(json.dumps(dict(before=state, after=snapshot(doc.getObject(name))), indent=2), encoding="utf-8")
        check("accepted FCStd restored " + name, same(state, snapshot(doc.getObject(name))))
    check("accepted FCStd truss mass", near(read_physical_mass(owner).mass_kg, mass.mass_kg))
    for index in (0, 1):
        before = snapshot(targets[index])
        ref = references[index]
        moved = App.Placement(ref.Placement)
        moved.Base = moved.Base.add(targets[index].Placement.Rotation.multVec(App.Vector(0, 0, 20)))
        ref.Placement = moved
        doc.recompute()
        check("restored association mode " + str(index), (not near(before[1], targets[index].Shape.Volume)) == (index == 0))

    # The replay guard must preserve ordinary user transforms, roll and length.
    moved_member = member.create_member(doc, App.Vector(100, 200, 300), App.Vector(100, 200, 1300), "W 150 x 13,0")
    moved_member.StartAdjustmentMode = "Fixed"
    moved_member.StartFixedReferenceOffset = 100
    doc.recompute()
    for operation in ("Placement", "Rotation", "Length"):
        old = snapshot(moved_member)
        doc.openTransaction("Native regression " + operation)
        if operation == "Placement":
            delta = App.Placement(App.Vector(30, 40, 50), App.Rotation(App.Vector(0, 1, 0), 15))
            moved_member.Placement = delta.multiply(moved_member.Placement)
        else:
            setattr(moved_member, operation, float(getattr(moved_member, operation).Value) + 35)
        doc.recompute()
        doc.commitTransaction()
        new = snapshot(moved_member)
        doc.undo()
        doc.recompute()
        check("user transform Undo " + operation, same(old, snapshot(moved_member)))
        doc.redo()
        doc.recompute()
        check("user transform Redo " + operation, same(new, snapshot(moved_member)))

    obj = targets[0]
    for mode in ("cancel", "escape", "close", "destroy", "invalid", "hidden", "target", "deleted-reference", "visibility", "display-mode"):
        App.Console.PrintMessage("Stage1 lifecycle: " + mode + "\n")
        if mode == "hidden":
            obj.ViewObject.Visibility = False
        panel = show(obj)
        ref = configure(panel, obj)
        original = snapshot(obj)
        undo = doc.UndoCount
        visibility = obj.ViewObject.Visibility
        preview = panel._preview
        node, scene = preview.node, preview.scene_graph
        if mode == "invalid":
            panel.gap.setValue(100000)
            drain()
            check("invalid removes preview", panel._preview is None and panel._candidate is None)
            check("invalid OK disabled", not panel.isValid() and not panel.accept())
            grab(Gui.getMainWindow(), "task-view-invalid")
            panel.reject()
        elif mode == "escape":
            panel.gap.setFocus()
            QtTest.QTest.keyClick(panel.gap, QtCore.Qt.Key_Escape)
        elif mode == "close":
            panel.form.close()
        elif mode == "destroy":
            Gui.Control.closeDialog()
        elif mode == "target":
            panel._begin_capture("member")
            Gui.Selection.clearSelection()
            Gui.Selection.addSelection(doc.Name, targets[2].Name)
            check("target switch restores original", scene.findChild(node) < 0 and obj.ViewObject.SwitchNode.whichChild.getValue() != -1)
            panel.reject()
        elif mode == "deleted-reference":
            doc.removeObject(ref.Name)
            doc.recompute()
            wait_preview_poll(panel)
            check("deleted reference clears candidate", panel._preview is None and not panel.isValid())
            check("deleted reference cannot confirm", not panel.accept())
            panel.reject()
        elif mode == "visibility":
            obj.ViewObject.Visibility = False
            visibility = False
            wait_preview_poll(panel)
            panel.reject()
        elif mode == "display-mode":
            previous_mode = obj.ViewObject.DisplayMode
            obj.ViewObject.DisplayMode = "Wireframe"
            wait_preview_poll(panel)
            panel.reject()
            check("display mode preserved", obj.ViewObject.DisplayMode == "Wireframe")
            obj.ViewObject.DisplayMode = previous_mode
        else:
            box = panel.form.window().findChild(QtWidgets.QDialogButtonBox)
            box.button(QtWidgets.QDialogButtonBox.Cancel).click()
        drain()
        check("cleanup " + mode, panel._closed and panel._preview is None and scene.findChild(node) < 0)
        check("timer/selection cleanup " + mode, panel._selection_observer is None
              and (not shiboken6.isValid(panel._preview_timer) or not panel._preview_timer.isActive()))
        check("cancel state " + mode, same(snapshot(obj), original) and undo == doc.UndoCount
              and obj.ViewObject.Visibility == visibility)
        if mode in ("hidden", "visibility"):
            check("hidden source stays hidden", obj.ViewObject.SwitchNode.whichChild.getValue() == -1)
            obj.ViewObject.Visibility = True

    # Exercise the actual command ownership/close callback as well as the form.
    Gui.Selection.clearSelection()
    Gui.Selection.addSelection(obj)
    commands.AdjustMemberCommand().Activated()
    panel = commands._active_adjustment_panel
    check("public command opens existing target", panel is not None and panel.controller.member is obj)
    ref = configure(panel, obj)
    preview = panel._preview
    node, scene = preview.node, preview.scene_graph
    check("public command close succeeds", commands.close_adjustment_panel())
    drain()
    check("public command ownership cleanup", commands._active_adjustment_panel is None
          and panel._closed and scene.findChild(node) < 0)

    doomed = member.create_member(doc, App.Vector(), App.Vector(0, 0, 1000), "W 150 x 13,0")
    panel = show(doomed)
    configure(panel, doomed)
    preview = panel._preview
    node, scene = preview.node, preview.scene_graph
    doc.removeObject(doomed.Name)
    doc.recompute()
    wait_preview_poll(panel)
    check("deleted target cleanup", panel._closed and panel._preview is None and scene.findChild(node) < 0)

    panel = show(obj)
    configure(panel, obj)
    old_preview = panel._preview
    node, scene = old_preview.node, old_preview.scene_graph
    Gui.activeDocument().createView("Gui::View3DInventor")
    wait_preview_poll(panel)
    check("active 3D view moves preview", panel._preview is not None
          and panel._preview.scene_graph != scene and scene.findChild(node) < 0)
    panel.reject()

    # Closing a document while the task is open must not retain nodes/timers.
    App.Console.PrintMessage("Stage1 lifecycle: document close\n")
    panel = show(obj)
    configure(panel, obj)
    preview = panel._preview
    node, scene = preview.node, preview.scene_graph
    App.closeDocument(doc.Name)
    wait_preview_poll(panel)
    check("document close cleanup", panel._closed and panel._preview is None and scene.findChild(node) < 0)


if os.environ.get("SS_ADJUST_ROOT"):
    import FreeCAD as App
    from PySide import QtCore, QtWidgets
    root = Path(os.environ["SS_ADJUST_ROOT"])
    out = Path(os.environ["SS_ADJUST_OUT"])
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
        QtCore.QTimer.singleShot(0, QtWidgets.QApplication.quit)

    QtCore.QTimer.singleShot(500, launch)
