# SPDX-License-Identifier: LGPL-2.1-or-later
"""Real FreeCAD 1.1.4 gate for the fixed bilateral miter MVP.

Run scripts/run_member_miter_joint_gate.py. Creates only isolated documents;
the full Python discovery suite never imports this manual native gate.
"""
import hashlib
import json
import math
import os
from pathlib import Path
import sys
import traceback


def near(a, b):
    return math.isclose(float(a), float(b), rel_tol=1e-8, abs_tol=1e-6)


def plain(value):
    import FreeCAD as App
    if isinstance(value, App.Vector):
        return [round(float(v), 9) for v in value]
    if hasattr(value, "Value"):
        return round(float(value.Value), 9)
    if isinstance(value, (tuple, list)):
        return [plain(v) for v in value]
    if hasattr(value, "Name"):
        return value.Name
    if isinstance(value, float):
        return round(value, 9)
    return value


def state(obj):
    from freecad.SteelStructures.member_batch import INPUTS, OUTPUTS
    shape = obj.Shape
    # Invalid-source fixtures deliberately reach the member's empty/invalid
    # Shape state before asking the miter controller to reject them. OCC does
    # not promise Volume/BoundBox access for that state. Preserve the native
    # flags and errors explicitly instead of inventing a zero-volume solid.
    geometry = {}
    for key, read in (("is_null", shape.isNull), ("is_valid", shape.isValid),
                      ("shape_type", lambda: str(shape.ShapeType))):
        try:
            geometry[key] = read()
        except (RuntimeError, ReferenceError) as exc:
            geometry[key] = None
            geometry[key + "_error"] = type(exc).__name__ + ": " + str(exc)
    valid = geometry["is_null"] is False and geometry["is_valid"] is True
    volume, bounds = None, None
    if valid:
        # A purportedly valid shape must still support both measurements.
        # Do not catch such failures: all valid-state assertions must fail.
        volume = round(float(shape.Volume), 9)
        bounds = [round(float(getattr(shape.BoundBox, key)), 9)
                  for key in ("XMin", "YMin", "ZMin", "XMax", "YMax", "ZMax")]
    return dict(inputs={key: plain(getattr(obj, key)) for key in INPUTS if hasattr(obj, key)},
        outputs={key: plain(getattr(obj, key)) for key in OUTPUTS if hasattr(obj, key)},
        placement=[round(float(v), 9) for v in obj.Placement.toMatrix().A],
        volume=volume, bounds=bounds, valid=valid, geometry=geometry,
        object_state=list(obj.State))


def same(a, b):
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(same(a[k], b[k]) for k in a)
    if isinstance(a, (tuple, list)) and isinstance(b, (tuple, list)):
        return len(a) == len(b) and all(same(x, y) for x, y in zip(a, b))
    if isinstance(a, (float, int)) and not isinstance(a, bool) and isinstance(b, (float, int)):
        return near(a, b)
    return a == b


def world_shape(obj):
    """Read a feature's Shape in the accumulated App::Part world frame."""
    shape = obj.Shape.copy()
    shape.Placement = obj.getGlobalPlacement()
    return shape


def assert_shape(check, label, actual, expected):
    check(label + " valid", actual.isValid() and not actual.isNull() and actual.Volume > 0)
    check(label + " volume", near(actual.Volume, expected.Volume))
    check(label + " symmetric difference", actual.cut(expected).Volume < 1e-5
          and expected.cut(actual).Volume < 1e-5)


def profiles():
    from freecad.SteelStructures import profile_catalog
    values = list(profile_catalog.profiles().values())
    result = {"W": "W 150 x 13,0"}
    result["U"] = next(p.designation for p in values if p.definition.geometry_variant == "simple_u")
    result["Ue"] = next(p.designation for p in values
                        if p.definition.geometry_type == "cold_formed_channel"
                        and p.definition.geometry_variant == "stiffened_u")
    for key, variant in (("RHS", "rectangular"), ("SHS", "square")):
        result[key] = next(p.designation for p in values if p.definition.geometry_type == "hollow_section"
                           and p.definition.geometry_variant == variant)
    result["RHS-other"] = next(p.designation for p in values
                               if p.definition.geometry_type == "hollow_section"
                               and p.definition.geometry_variant == "rectangular"
                               and p.designation != result["RHS"])
    return result


def pair(doc, profile, *, angle=90, ends=("Start", "Start"), rolls=(0, 0),
         second_profile=None, rigid=False):
    import FreeCAD as App
    from freecad.SteelStructures.member import create_member
    rays = [App.Vector(1, 0, 0), App.Vector(math.cos(math.radians(angle)), math.sin(math.radians(angle)), 0)]
    k = App.Vector(0, 0, 1)
    if rigid:
        rotation = App.Rotation(App.Vector(1, 2, 3), 37)
        rays, k = [rotation.multVec(v) for v in rays], rotation.multVec(k)
    result = []
    for ray, designation, end, roll in zip(rays, (profile, second_profile or profile), ends, rolls):
        start, finish = ray*50, ray*1000
        if end == "End":
            start, finish = finish, start
        obj = create_member(doc, start, finish, designation)
        direction = finish.sub(start)
        direction.normalize()
        frame = App.Rotation(k, direction.cross(k), direction, "ZXY")
        frame = frame.multiply(App.Rotation(App.Vector(0, 0, 1), roll))
        obj.Placement = App.Placement(obj.StartPoint, frame)
        result.append(obj)
    doc.recompute()
    return tuple(result)


def wait_poll(panel):
    """Wait for actual timer dispatch and completed slots, never elapsed time."""
    import shiboken6
    from PySide import QtCore
    if panel._closed:
        return
    timer = panel._preview_timer
    if not shiboken6.isValid(timer) or not timer.isActive():
        raise AssertionError("Miter preview timer unexpectedly unavailable")
    loop = QtCore.QEventLoop()
    timer.timeout.connect(loop.quit, QtCore.Qt.QueuedConnection)
    timer.destroyed.connect(loop.quit)
    try:
        loop.exec()
    finally:
        if shiboken6.isValid(timer):
            timer.timeout.disconnect(loop.quit)
            timer.destroyed.disconnect(loop.quit)


def candidate_probe(out, check):
    import FreeCAD as App
    from freecad.SteelStructures.interactive.member_miter_controller import MemberMiterController
    chosen = profiles()
    rows = []
    fixtures = [(name + "90", name, 90, ("Start", "Start"), (0, 0), False)
                for name in ("W", "U", "Ue", "RHS", "SHS")]
    fixtures += [("SHS60", "SHS", 60, ("Start", "Start"), (0, 0), False),
                 ("SHS135", "SHS", 135, ("Start", "Start"), (0, 0), False),
                 ("W60", "W", 60, ("Start", "Start"), (0, 0), False),
                 ("W120", "W", 120, ("Start", "Start"), (0, 0), False),
                 ("SHS_StartEnd", "SHS", 90, ("Start", "End"), (0, 0), False),
                 ("SHS_EndEnd", "SHS", 90, ("End", "End"), (0, 0), False),
                 ("SHS_rotated_plane", "SHS", 60, ("Start", "Start"), (0, 0), True),
                 ("W_roll_match", "W", 60, ("Start", "Start"), (23, -23), False)]
    for label, family, angle, ends, rolls, rigid in fixtures:
        doc = App.newDocument("MiterCandidate")
        doc.UndoMode = 1
        members = pair(doc, chosen[family], angle=angle, ends=ends, rolls=rolls, rigid=rigid)
        before = [state(o) for o in members]
        names, undo = [o.Name for o in doc.Objects], doc.UndoCount
        controller = MemberMiterController(doc, members=members)
        candidate = controller.evaluate()
        check(label + " evaluate untouched", same(before, [state(o) for o in members])
              and names == [o.Name for o in doc.Objects] and undo == doc.UndoCount)
        check(label + " ends", tuple(candidate.plan.ends) == ends)
        check(label + " angle", near(candidate.plan.angle_degrees, angle))
        check(label + " finite normal", all(math.isfinite(v) for v in candidate.plan.normal))
        reversed_candidate = MemberMiterController(doc, members=members[::-1]).evaluate()
        reverse_by_name = dict(zip((o.Name for o in reversed_candidate.members), reversed_candidate.global_shapes))
        for obj, shape in zip(candidate.members, candidate.global_shapes):
            assert_shape(check, label + " reversed selection " + obj.Name,
                         shape, reverse_by_name[obj.Name])
        expected = dict(zip((o.Name for o in candidate.members), candidate.global_shapes))
        controller.apply()
        check(label + " one Undo", doc.UndoCount == undo + 1)
        check(label + " no persistent helper", names == [o.Name for o in doc.Objects])
        for obj in members:
            assert_shape(check, label + " committed " + obj.Name, world_shape(obj), expected[obj.Name])
            prefix = ends[members.index(obj)]
            check(label + " fixed slot " + obj.Name,
                  str(getattr(obj, prefix + "AdjustmentMode")) == "Fixed"
                  and str(getattr(obj, prefix + "AdjustmentGeometryMode")) == "PlaneCut"
                  and not getattr(obj, prefix + "AdjustmentReference"))
        after = [state(o) for o in members]
        doc.undo()
        doc.recompute()
        check(label + " Undo restores both", same(before, [state(o) for o in members]))
        doc.redo()
        doc.recompute()
        check(label + " Redo restores both", same(after, [state(o) for o in members]))
        row = dict(label=label, profile=chosen[family], angle=angle, ends=ends,
                   volumes=[o.Shape.Volume for o in members])
        if label == "SHS90":
            names = [o.Name for o in members]
            path = out / "fixed-miter.FCStd"
            doc.saveAs(str(path))
            App.closeDocument(doc.Name)
            doc = App.openDocument(str(path))
            doc.recompute()
            restored = [doc.getObject(name) for name in names]
            check("FCStd restores both fixed members", same(after, [state(o) for o in restored]))
            # This MVP stores two local fixed cuts, not an associative pair.
            other = state(restored[1])
            placement = App.Placement(restored[0].Placement)
            placement.Base = placement.Base.add(App.Vector(100, 0, 0))
            restored[0].Placement = placement
            doc.recompute()
            check("fixed partner remains independent after move", same(other, state(restored[1])))
        rows.append(row)
        App.closeDocument(doc.Name)
    (out / "candidate-cases.json").write_text(json.dumps(rows, indent=2), encoding="utf-8")


def invalid_probe(out, check):
    import FreeCAD as App
    import Part
    from freecad.SteelStructures import truss
    from freecad.SteelStructures.interactive.member_miter_controller import MemberMiterController
    chosen, rows = profiles(), []
    cases = ("roll", "unequal", "skew", "parallel", "T", "crossing", "occupied", "linked", "opposite-invalid")
    for label in cases:
        doc = App.newDocument("MiterRejected")
        doc.UndoMode = 1
        a, b = pair(doc, chosen["W" if label == "roll" else "RHS"],
                    angle=60 if label == "roll" else 90, rolls=(23, 23) if label == "roll" else (0, 0),
                    second_profile=chosen["RHS-other"] if label == "unequal" else None)
        if label == "skew":
            delta = App.Placement(b.Placement)
            delta.Base.z += 20
            b.Placement = delta
        elif label == "parallel":
            b.StartPoint, b.EndPoint = App.Vector(50, 100, 0), App.Vector(1000, 100, 0)
        elif label == "T":
            a.StartPoint, a.EndPoint = App.Vector(-1000, 0, 0), App.Vector(1000, 0, 0)
        elif label == "crossing":
            a.StartPoint, a.EndPoint = App.Vector(-1000, 0, 0), App.Vector(1000, 0, 0)
            b.StartPoint, b.EndPoint = App.Vector(0, -1000, 0), App.Vector(0, 1000, 0)
        elif label == "occupied":
            a.StartAdjustmentMode, a.StartFixedReferenceOffset = "Fixed", 0
        elif label == "linked":
            source = doc.addObject("Part::Feature", "AxisSource")
            source.Shape = Part.makeLine(a.StartPoint, a.EndPoint)
            a.AxisSource, a.AxisDefinitionMode = (source, ["Edge1"]), "Linked"
        elif label == "opposite-invalid":
            a.EndAdjustmentMode, a.EndFixedReferenceOffset = "Fixed", 2000
        doc.recompute()
        before, undo, names = [state(o) for o in (a, b)], doc.UndoCount, [o.Name for o in doc.Objects]
        error = None
        try:
            MemberMiterController(doc, members=(a, b)).apply()
        except ValueError as exc:
            error = str(exc)
        check(label + " invalid rejected with diagnostic", bool(error))
        check(label + " invalid leaves both unchanged", same(before, [state(o) for o in (a, b)])
              and undo == doc.UndoCount and names == [o.Name for o in doc.Objects])
        rows.append(dict(label=label, error=error))
        App.closeDocument(doc.Name)
    doc = App.newDocument("MiterOwners")
    config = truss.default_config()
    config.update(span=6000., end=[6000., 0., 0.], height=1600., panel_count=4)
    owner = truss.apply_truss(doc, config)
    children = list(owner.GeneratedMembers)
    independent = pair(doc, chosen["SHS"])[0]
    for label, members in (("child-independent", (children[0], independent)), ("two-children", tuple(children[:2]))):
        before, undo = [state(o) for o in members], doc.UndoCount
        error = None
        try:
            MemberMiterController(doc, members=members).apply()
        except ValueError as exc:
            error = str(exc)
        check(label + " rejected", bool(error))
        check(label + " preserves outputs/Undo", same(before, [state(o) for o in members]) and undo == doc.UndoCount)
        rows.append(dict(label=label, error=error))
    App.closeDocument(doc.Name)
    (out / "invalid-cases.json").write_text(json.dumps(rows, indent=2), encoding="utf-8")


def transaction_probe(out, check):
    import FreeCAD as App
    import Part
    from freecad.SteelStructures.interactive import member_miter_controller as module
    chosen = profiles()
    doc = App.newDocument("MiterAtomicity")
    doc.UndoMode = 1
    members = pair(doc, chosen["SHS"])
    a, b = members
    # A valid adjustment on the opposite end must survive the bilateral cut.
    a.EndAdjustmentMode, a.EndFixedReferenceOffset = "Fixed", 100
    doc.recompute()
    controller = module.MemberMiterController(doc, members=members)
    candidate = controller.evaluate()
    before, undo = [state(o) for o in members], doc.UndoCount
    original_verify, calls = module.verify_adjustment_candidate, []
    def fail_second(obj, item):
        calls.append(obj.Name)
        original_verify(obj, item)
        if len(calls) == 2:
            raise ValueError("Injected failure after the first definitive verification")
    module.verify_adjustment_candidate = fail_second
    error = None
    try:
        controller.apply()
    except ValueError as exc:
        error = str(exc)
    finally:
        module.verify_adjustment_candidate = original_verify
    doc.recompute()
    check("late failure reached second member", len(calls) == 2 and bool(error))
    check("late failure rolls back both and Undo", same(before, [state(o) for o in members]) and undo == doc.UndoCount)
    controller.apply()
    check("opposite fixed slot retained", str(a.EndAdjustmentMode) == "Fixed" and near(a.EndFixedReferenceOffset.Value, 100))
    doc.undo()
    doc.recompute()
    check("opposite slot replay preserves both", same(before, [state(o) for o in members]))
    # A previously valid pair candidate is never permission to use old Shapes.
    controller.evaluate()
    b.OffsetX = 100
    doc.recompute()
    before, undo = [state(o) for o in members], doc.UndoCount
    error = None
    try:
        controller.apply()
    except ValueError as exc:
        error = str(exc)
    check("stale valid candidate cannot be confirmed", bool(error))
    check("stale rejection leaves source inputs and Undo", same(before, [state(o) for o in members]) and undo == doc.UndoCount)
    (out / "transaction-cases.json").write_text(json.dumps(dict(late_failure_calls=calls, stale_error=error), indent=2), encoding="utf-8")
    App.closeDocument(doc.Name)
    doc = App.newDocument("MiterOppositeAssociation")
    doc.UndoMode = 1
    a, b = pair(doc, chosen["SHS"])
    reference = doc.addObject("Part::Feature", "OppositeReference")
    reference.Shape = Part.makePlane(1000, 1000, App.Vector(900, 0, 0), App.Vector(1, 0, 0))
    a.EndAdjustmentMode = "Associative"
    a.EndAdjustmentGeometryMode = "LengthLimit"
    a.EndAdjustmentReference = (reference, ["Face1"])
    doc.recompute()
    before = [state(o) for o in (a, b)]
    module.MemberMiterController(doc, members=(a, b)).apply()
    check("opposite associative slot retained", str(a.EndAdjustmentMode) == "Associative"
          and a.EndAdjustmentReference[0] is reference)
    doc.undo()
    doc.recompute()
    check("opposite association Undo restores pair", same(before, [state(o) for o in (a, b)]))
    doc.redo()
    doc.recompute()
    path = out / "opposite-associative.FCStd"
    member_name, reference_name = a.Name, reference.Name
    doc.saveAs(str(path))
    App.closeDocument(doc.Name)
    doc = App.openDocument(str(path))
    doc.recompute()
    a, reference = doc.getObject(member_name), doc.getObject(reference_name)
    check("opposite association FCStd restores", str(a.StartAdjustmentMode) == "Fixed"
          and str(a.EndAdjustmentMode) == "Associative" and a.EndAdjustmentReference[0] is reference)
    old_length = a.AdjustedLength.Value
    placement = App.Placement(reference.Placement)
    placement.Base.x += 20
    reference.Placement = placement
    doc.recompute()
    check("restored opposite association still updates", near(a.AdjustedLength.Value, old_length + 20)
          and str(a.StartAdjustmentMode) == "Fixed")
    App.closeDocument(doc.Name)


def preview_nodes(preview):
    return [(item.scene_graph, item.node) for item in preview.previews] + [(preview.scene_graph, preview.node)]


def assert_ok_enabled(check, label, panel, enabled):
    from PySide import QtWidgets
    box = panel.form.window().findChild(QtWidgets.QDialogButtonBox)
    button = box.button(QtWidgets.QDialogButtonBox.Ok) if box is not None else None
    check(label + " native OK exists", button is not None)
    check(label + " native OK state", button.isEnabled() == enabled)


def assert_message_style(out, check, label, panel, severity):
    """Measure the status against the composed Task View, not form.grab()."""
    from collections import Counter
    import FreeCADGui as Gui
    from PySide import QtCore, QtGui, QtWidgets
    QtWidgets.QApplication.processEvents()
    QtWidgets.QApplication.sendPostedEvents(panel.form)
    status, window = panel.validation_message, Gui.getMainWindow()
    status.ensurePolished()
    pixmap = window.grab()
    image = pixmap.toImage().convertToFormat(QtGui.QImage.Format_RGB32)
    point = status.mapTo(window, QtCore.QPoint(0, 0))
    scale = pixmap.devicePixelRatio()
    left, top = int(point.x()*scale), int(point.y()*scale)
    right = min(image.width(), int((point.x()+status.width())*scale))
    bottom = min(image.height(), int((point.y()+status.height())*scale))
    colors = Counter(image.pixel(x, y) for y in range(max(0, top), bottom)
                     for x in range(max(0, left), right))
    check(label + " status pixels available", bool(colors))
    background = QtGui.QColor.fromRgba(colors.most_common(1)[0][0])
    foreground = status.palette().color(QtGui.QPalette.WindowText)
    rgb = lambda color: (color.redF(), color.greenF(), color.blueF())
    def luminance(color):
        channels = [v/12.92 if v <= .04045 else ((v+.055)/1.055)**2.4 for v in rgb(color)]
        return sum(v*w for v, w in zip(channels, (.2126, .7152, .0722)))
    low, high = sorted((luminance(foreground), luminance(background)))
    contrast = (high+.05)/(low+.05)
    actual_severity = status.property("miterMessageSeverity")
    row = dict(label=label, severity=actual_severity, text=status.text(),
               foreground=list(rgb(foreground)), background=list(rgb(background)), contrast=contrast)
    with (out / "message-styles.jsonl").open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(row) + "\n")
    check(label + " semantic severity", actual_severity == severity)
    check(label + " composed Task View contrast", contrast >= 4.5)
    if severity == "success":
        check(label + " success is green", foreground.green() > max(foreground.red(), foreground.blue()))
    elif severity == "error":
        check(label + " error is red", foreground.red() > max(foreground.green(), foreground.blue()))
    check(label + " window capture", pixmap.save(str(out / (label + "-window.png"))))


def assert_cleanup(check, label, panel, nodes):
    import shiboken6
    check(label + " preview removed", panel._closed and panel._preview is None
          and all(node is None or scene.findChild(node) < 0 for scene, node in nodes))
    check(label + " timer/observer removed", panel._selection_observer is None
          and (not shiboken6.isValid(panel._preview_timer) or not panel._preview_timer.isActive()))


class _RecomputeSentinel:
    """Native execute counter: pending unrelated features must stay pending."""
    def __init__(self, plane=False):
        self.calls = 0
        self.plane = plane

    def execute(self, obj):
        import FreeCAD as App
        import Part
        self.calls += 1
        obj.Shape = (Part.makePlane(1000, 1000, App.Vector(900, 0, 0), App.Vector(1, 0, 0))
                     if self.plane else Part.makeBox(10, 10, 10))


def abort_history_probe(out, check):
    """Native Part::Box control: first write discards an existing Redo branch.

    No Steel Structures class/controller participates in either transaction.
    This baseline separates platform history semantics from pair rollback.
    """
    import FreeCAD as App
    cases = []
    for mutate in (True, False):
        doc = App.newDocument("MiterNativeAbortControl")
        doc.UndoMode = 1
        obj = doc.addObject("Part::Box", "NativeBox")
        obj.addProperty("App::PropertyFloat", "ProbeValue")
        obj.ProbeValue = 0
        doc.recompute([obj])
        def snapshot(phase):
            return dict(phase=phase, value=float(obj.ProbeValue), length=float(obj.Length.Value),
                        width=float(obj.Width.Value), height=float(obj.Height.Value),
                        volume=float(obj.Shape.Volume), placement=list(obj.Placement.toMatrix().A),
                        state=list(obj.State), undo=doc.UndoCount, redo=doc.RedoCount)
        doc.openTransaction("Native control first write")
        obj.ProbeValue, obj.Length = 1, 15
        doc.recompute([obj])
        doc.commitTransaction()
        doc.undo()
        before_shape = obj.Shape.copy()
        rows = [snapshot("before-open")]
        doc.openTransaction("Native control aborted write")
        rows.append(snapshot("after-open"))
        if mutate:
            obj.ProbeValue, obj.Length = 2, 20
            doc.recompute([obj])
            rows.append(snapshot("after-write"))
        doc.abortTransaction()
        rows.append(snapshot("after-abort"))
        before, after = rows[0], rows[-1]
        check("native abort restores properties " + str(mutate), near(after["value"], before["value"])
              and all(near(after[key], before[key]) for key in ("length", "width", "height", "volume")))
        assert_shape(check, "native abort restores Shape " + str(mutate), obj.Shape, before_shape)
        check("native abort adds no Undo " + str(mutate), after["undo"] == before["undo"])
        check("native open alone preserves Redo " + str(mutate), rows[1]["redo"] == before["redo"] == 1)
        if mutate:
            check("native first write discards Redo", rows[2]["redo"] == after["redo"] == 0)
        else:
            check("native empty abort preserves Redo", after["redo"] == before["redo"])
        cases.append(dict(mutate=mutate, rows=rows))
        (out / "native-abort-baseline.json").write_text(json.dumps(cases, indent=2), encoding="utf-8")
        App.closeDocument(doc.Name)
    return dict(mutating_abort_clears_redo=cases[0]["rows"][-1]["redo"] == 0,
                empty_abort_preserves_redo=cases[1]["rows"][-1]["redo"] == 1)


def replay_probe(out, check, native_history):
    """Exercise real replay/reopening with NO caller recompute after history."""
    import FreeCAD as App
    import FreeCADGui as Gui
    from PySide import QtWidgets
    from freecad.SteelStructures.member import create_member
    from freecad.SteelStructures.interactive import member_miter_controller as module
    from freecad.SteelStructures.interactive.member_miter_task_panel import MemberMiterTaskPanel
    rows = []
    def record(label, **values):
        rows.append(dict(label=label, **values))
        (out / "replay-cases.json").write_text(json.dumps(rows, indent=2), encoding="utf-8")
    def show(members, through_command=False):
        def closed(panel, _accepted):
            if panel.form is not None:
                Gui.Control.closeDialog()
        if through_command:
            from freecad.SteelStructures import commands
            Gui.Selection.clearSelection()
            for obj in members:
                Gui.Selection.addSelection(obj)
            Gui.runCommand("SteelStructures_MiterMembers")
            panel = commands._active_miter_panel
            check("public command opens after Undo", panel is not None)
        else:
            panel = MemberMiterTaskPanel(doc, members=members, on_closed=closed)
            Gui.Control.showDialog(panel)
        QtWidgets.QApplication.processEvents()
        QtWidgets.QApplication.sendPostedEvents(panel.form)
        return panel
    def dismiss(panel, label):
        nodes = preview_nodes(panel._preview) if panel._preview is not None else []
        panel.reject()
        QtWidgets.QApplication.processEvents()
        assert_cleanup(check, label, panel, nodes)

    doc = App.newDocument("MiterReplayWithoutRecompute")
    doc.UndoMode = 1
    a, b = pair(doc, profiles()["SHS"])
    # An already cut A/B pair still has A.End free. C approaches that endpoint.
    c = create_member(doc, App.Vector(1000, 50, 0), App.Vector(1000, 1000, 0), str(a.Profile))
    ray, k = App.Vector(0, 1, 0), App.Vector(0, 0, 1)
    c.Placement = App.Placement(c.StartPoint, App.Rotation(k, ray.cross(k), ray, "ZXY"))
    outsider = doc.addObject("Part::FeaturePython", "UnrelatedPending")
    outsider.Proxy = _RecomputeSentinel()
    doc.recompute()  # Fixture construction only; never after Undo/Redo below.
    outsider.touch()
    outsider_calls = outsider.Proxy.calls
    baseline = [state(o) for o in (a, b)]
    other = App.newDocument("MiterUnrelatedDocument")
    other.UndoMode = 1
    other_obj = other.addObject("Part::FeaturePython", "OtherPending")
    other_obj.Proxy = _RecomputeSentinel()
    other.recompute()
    other_obj.touch()
    other_calls, other_state = other_obj.Proxy.calls, list(other_obj.State)
    other_history = (other.UndoCount, other.RedoCount)
    App.setActiveDocument(doc.Name)
    def scope(label):
        check(label + " unrelated pending feature untouched", outsider.Proxy.calls == outsider_calls
              and "Touched" in outsider.State)
        check(label + " unrelated document untouched", other_obj.Proxy.calls == other_calls
              and list(other_obj.State) == other_state and (other.UndoCount, other.RedoCount) == other_history)
    controller = module.MemberMiterController(doc, members=(a, b))
    for cycle in range(3):
        label = "replay cycle " + str(cycle)
        initial_undo = doc.UndoCount
        controller.apply()
        check(label + " first apply one action", doc.UndoCount == initial_undo + 1)
        scope(label + " apply")
        doc.undo()
        history = (doc.UndoCount, doc.RedoCount)
        record(label + " raw Undo", states=[list(o.State) for o in (a, b)], history=history,
               slots=[str(o.StartAdjustmentMode) for o in (a, b)])
        panel = show((a, b), through_command=(cycle == 0))
        check(label + " opens after Undo without manual recompute", panel.isValid() and panel._preview is not None)
        assert_ok_enabled(check, label + " after Undo", panel, True)
        check(label + " replay normalized without new history", same(baseline, [state(o) for o in (a, b)])
              and (doc.UndoCount, doc.RedoCount) == history)
        scope(label + " reopen after Undo")
        nodes = preview_nodes(panel._preview)
        check(label + " new apply after Undo", panel.accept())
        QtWidgets.QApplication.processEvents()
        assert_cleanup(check, label + " new application", panel, nodes)
        check(label + " new apply replaces Redo branch", doc.UndoCount == history[0] + 1 and doc.RedoCount == 0)
        scope(label + " new apply")
        doc.undo()
        panel = show((a, b))
        check(label + " second Undo can reopen", panel.isValid())
        dismiss(panel, label + " second Undo cancel")
        doc.redo()
        history = (doc.UndoCount, doc.RedoCount)
        record(label + " raw Redo", states=[list(o.State) for o in (a, b)], history=history,
               slots=[str(o.StartAdjustmentMode) for o in (a, b)])
        panel = show((a, b))
        diagnostic = panel._last_error or ""
        check(label + " Redo keeps occupied target rejected", not panel.isValid()
              and "ajuste" in diagnostic.lower() and "recompute" not in diagnostic.lower())
        assert_ok_enabled(check, label + " occupied after Redo", panel, False)
        check(label + " occupied open does not change history", (doc.UndoCount, doc.RedoCount) == history)
        dismiss(panel, label + " Redo occupied cancel")
        scope(label + " Redo reopen")
        if cycle == 2:
            occupied_pair = [state(o) for o in (a, b, c)]
            panel = show((a, c))
            check("free opposite end usable after Redo", panel.isValid() and tuple(panel._candidate.plan.ends) == ("End", "Start"))
            assert_ok_enabled(check, "free opposite after Redo", panel, True)
            nodes = preview_nodes(panel._preview)
            check("free opposite application after Redo", panel.accept())
            QtWidgets.QApplication.processEvents()
            assert_cleanup(check, "free opposite application", panel, nodes)
            check("free opposite application one action", doc.UndoCount == history[0] + 1)
            doc.undo()
            panel = show((a, c))
            check("free opposite Undo reopens without recompute", panel.isValid())
            check("free opposite Undo preserves earlier pair", same(occupied_pair, [state(o) for o in (a, b, c)]))
            dismiss(panel, "free opposite Undo cancel")
            scope("free opposite replay")
        doc.undo()  # Undo A/B. Next cycle must normalize its replay itself.

    controller.evaluate()
    before, history = [state(o) for o in (a, b)], (doc.UndoCount, doc.RedoCount)
    original_verify, calls = module.verify_adjustment_candidate, []
    def fail_second(obj, item):
        calls.append(obj.Name)
        original_verify(obj, item)
        if len(calls) == 2:
            raise ValueError("Injected replay-session verification failure")
    module.verify_adjustment_candidate = fail_second
    error = None
    try:
        controller.apply()
    except ValueError as exc:
        error = str(exc)
    finally:
        module.verify_adjustment_candidate = original_verify
    after_abort_history = (doc.UndoCount, doc.RedoCount)
    record("raw rollback", before_members=before, before_history=history,
           after_members=[state(o) for o in (a, b)], after_history=after_abort_history,
           native_history_baseline=native_history, error=error)
    panel = show((a, b))
    check("rollback reopens without caller recompute", len(calls) == 2 and bool(error) and panel.isValid())
    check("rollback restores both inputs and outputs", same(before, [state(o) for o in (a, b)]))
    check("rollback adds no Undo", doc.UndoCount == history[0])
    expected_redo = 0 if native_history["mutating_abort_clears_redo"] else history[1]
    check("rollback Redo matches demonstrated native policy", doc.RedoCount == expected_redo)
    check("rollback reopening does not change remaining history", (doc.UndoCount, doc.RedoCount) == after_abort_history)
    record("rollback normalized reopen", before_members=before, before_history=history,
           after_members=[state(o) for o in (a, b)], after_history=(doc.UndoCount, doc.RedoCount),
           expected_redo_from_native_baseline=expected_redo)
    dismiss(panel, "rollback reopen cancel")
    scope("rollback")
    App.closeDocument(doc.Name)
    App.closeDocument(other.Name)

    # A partial document recompute would execute dirty upstream supports too.
    # Their guard must therefore run before any selected-target normalization.
    doc = App.newDocument("MiterDirtySourceGuard")
    doc.UndoMode = 1
    members = pair(doc, profiles()["SHS"])
    source = doc.addObject("Part::FeaturePython", "OppositePendingSource")
    source.Proxy = _RecomputeSentinel(plane=True)
    outsider = doc.addObject("Part::FeaturePython", "UnrelatedPending")
    outsider.Proxy = _RecomputeSentinel()
    a, b = members
    a.EndAdjustmentMode, a.EndAdjustmentGeometryMode = "Associative", "LengthLimit"
    a.EndAdjustmentReference = (source, ["Face1"])
    doc.recompute()  # Build the source and pair once, before the guard scenario.
    panel = show(members)
    check("clean opposite source initially previews", panel.isValid() and panel._preview is not None)
    clean_nodes = preview_nodes(panel._preview)
    source.touch()  # Its plane stays identical and the child need not be Touched.
    outsider.touch()
    counts, history = (source.Proxy.calls, outsider.Proxy.calls), (doc.UndoCount, doc.RedoCount)
    raw_states = [list(obj.State) for obj in members]
    wait_poll(panel)
    diagnostic = panel._last_error or ""
    record("source touch without geometry change", child_states=raw_states,
           source_state=list(source.State), calls=list(counts), diagnostic=diagnostic)
    check("touched source invalidates both previews", not panel.isValid() and panel._preview is None
          and panel._candidate is None and all(node is None or scene.findChild(node) < 0 for scene, node in clean_nodes))
    assert_ok_enabled(check, "source touched during preview", panel, False)
    check("touched source cannot confirm old preview", not panel.accept())
    check("source touch polling does not execute source or outsider", (source.Proxy.calls, outsider.Proxy.calls) == counts
          and "Touched" in source.State and "Touched" in outsider.State
          and (doc.UndoCount, doc.RedoCount) == history)
    doc.recompute([source, *members])  # Explicit user normalization, not gate delay.
    wait_poll(panel)
    check("explicit source recompute restores preview", panel.isValid() and panel._preview is not None
          and source.Proxy.calls == counts[0] + 1 and outsider.Proxy.calls == counts[1]
          and "Touched" in outsider.State)
    assert_ok_enabled(check, "source normalized during task", panel, True)
    dismiss(panel, "source state recovery cancel")
    source.touch()
    outsider.touch()
    a.touch()
    before = [state(o) for o in members]
    counts, history = (source.Proxy.calls, outsider.Proxy.calls), (doc.UndoCount, doc.RedoCount)
    panel = show(members)
    diagnostic = panel._last_error or ""
    check("dirty source rejected before normalization", not panel.isValid() and "refer" in diagnostic.lower())
    assert_ok_enabled(check, "dirty source", panel, False)
    check("dirty source and outsider not executed", (source.Proxy.calls, outsider.Proxy.calls) == counts
          and "Touched" in source.State and "Touched" in outsider.State)
    check("dirty source refusal preserves pair/history", same(before, [state(o) for o in members])
          and (doc.UndoCount, doc.RedoCount) == history)
    dismiss(panel, "dirty source cancel")
    App.closeDocument(doc.Name)

    # FCStd opening is also an entry point: no manual recompute is inserted
    # between openDocument and constructing the task.
    doc = App.newDocument("MiterReopenWithoutRecompute")
    members = pair(doc, profiles()["SHS"])
    names = [o.Name for o in members]
    expected = [world_shape(o) for o in members]
    path = out / "free-pair-reopen.FCStd"
    doc.saveAs(str(path))
    App.closeDocument(doc.Name)
    doc = App.openDocument(str(path))
    members = tuple(doc.getObject(name) for name in names)
    history = (doc.UndoCount, doc.RedoCount)
    panel = show(members)
    check("FCStd task opens without manual recompute", panel.isValid())
    check("FCStd opening preview has no history", (doc.UndoCount, doc.RedoCount) == history)
    for obj, shape in zip(members, expected):
        assert_shape(check, "FCStd opening source preserved " + obj.Name, world_shape(obj), shape)
    dismiss(panel, "FCStd direct opening cancel")
    App.closeDocument(doc.Name)


def container_pair(doc, arrangement):
    """Construct convergent WORLD axes under distinct parent-local frames."""
    import FreeCAD as App
    members = pair(doc, profiles()["SHS"])
    common = App.Placement(App.Vector(350, -120, 220), App.Rotation(App.Vector(1, 2, 3), 31))
    if arrangement == "same-part":
        parent = doc.addObject("App::Part", "SharedPart")
        parent.Placement = common
        for obj in members:
            parent.addObject(obj)
    elif arrangement == "nested-part":
        parent = doc.addObject("App::Part", "OuterPart")
        parent.Placement = common
        inner = doc.addObject("App::Part", "InnerPart")
        parent.addObject(inner)
        inner.Placement = App.Placement(App.Vector(-40, 15, 50), App.Rotation(App.Vector(0, 1, 0), -23))
        for obj in members:
            inner.addObject(obj)
        common = parent.Placement.multiply(inner.Placement)
    else:
        parents = [doc.addObject("App::Part", "FirstPart"), doc.addObject("App::Part", "SecondPart")]
        parents[0].Placement = App.Placement(App.Vector(80, 30, -40), App.Rotation(App.Vector(1, 0, 1), 19))
        parents[1].Placement = App.Placement(App.Vector(-70, 90, 20), App.Rotation(App.Vector(0, 1, 1), -27))
        for obj, part in zip(members, parents):
            desired_world = common.multiply(obj.Placement)
            part.addObject(obj)
            # This is a normal rigid member move in its new parent-local frame.
            # The member callback updates its nominal local inputs accordingly.
            obj.Placement = part.Placement.inverse().multiply(desired_world)
        parent = parents[0]
    doc.recompute()
    return members, parent, common


def container_probe(out, check):
    import FreeCAD as App
    import FreeCADGui as Gui
    import Part
    from PySide import QtWidgets
    from freecad.SteelStructures.interactive.member_miter_controller import MemberMiterController
    from freecad.SteelStructures.interactive.member_miter_task_panel import MemberMiterTaskPanel
    rows = []
    for arrangement in ("same-part", "different-parts", "nested-part"):
        doc = App.newDocument("MiterContainers")
        doc.UndoMode = 1
        members, parent, common = container_pair(doc, arrangement)
        before = [state(o) for o in members]
        before_world = [world_shape(o) for o in members]
        names, undo = [o.Name for o in doc.Objects], doc.UndoCount
        controller = MemberMiterController(doc, members=members)
        candidate = controller.evaluate()
        expected_joint = common.multVec(App.Vector())
        check(arrangement + " world encounter", App.Vector(*candidate.plan.point).sub(expected_joint).Length < 1e-5)
        check(arrangement + " evaluation preserves local inputs", same(before, [state(o) for o in members])
              and names == [o.Name for o in doc.Objects] and undo == doc.UndoCount)
        expected = [s.copy() for s in candidate.global_shapes]
        controller.apply()
        check(arrangement + " one Undo", doc.UndoCount == undo + 1)
        for obj, shape in zip(members, expected):
            assert_shape(check, arrangement + " world committed " + obj.Name, world_shape(obj), shape)
        after = [state(o) for o in members]
        doc.undo()
        doc.recompute()
        check(arrangement + " Undo restores local pair", same(before, [state(o) for o in members]))
        for obj, shape in zip(members, before_world):
            assert_shape(check, arrangement + " Undo restores world " + obj.Name, world_shape(obj), shape)
        doc.redo()
        doc.recompute()
        check(arrangement + " Redo restores local pair", same(after, [state(o) for o in members]))
        for obj, shape in zip(members, expected):
            assert_shape(check, arrangement + " Redo restores world " + obj.Name, world_shape(obj), shape)
        member_names = [o.Name for o in members]
        path = out / (arrangement + ".FCStd")
        doc.saveAs(str(path))
        App.closeDocument(doc.Name)
        doc = App.openDocument(str(path))
        doc.recompute()
        members = tuple(doc.getObject(name) for name in member_names)
        check(arrangement + " FCStd restores local pair", same(after, [state(o) for o in members]))
        for obj, shape in zip(members, expected):
            assert_shape(check, arrangement + " FCStd restores world " + obj.Name, world_shape(obj), shape)
        rows.append(dict(arrangement=arrangement, point=list(expected_joint),
                         globals=[list(o.getGlobalPlacement().toMatrix().A) for o in members]))
        App.closeDocument(doc.Name)

    # A parent can move without touching any local member input. The task must
    # observe accumulated placement rather than relying on child State/hash.
    for arrangement in ("same-part", "different-parts", "nested-part"):
        doc = App.newDocument("MiterParentPreview")
        document_name = doc.Name
        doc.UndoMode = 1
        members, parent, common = container_pair(doc, arrangement)
        def closed(panel, _accepted):
            if panel.form is not None:
                Gui.Control.closeDialog()
        panel = MemberMiterTaskPanel(doc, members=members, on_closed=closed)
        Gui.Control.showDialog(panel)
        QtWidgets.QApplication.processEvents()
        QtWidgets.QApplication.sendPostedEvents(panel.form)
        check(arrangement + " initial parent preview valid", panel.isValid() and panel._preview is not None)
        for obj, preview, expected in zip(members, panel._preview.previews, panel._candidate.global_shapes):
            assert_shape(check, arrangement + " initial world preview " + obj.Name, preview.shape, expected)
        old_nodes = preview_nodes(panel._preview)
        before = [state(o) for o in members]
        child_states = [list(o.State) for o in members]
        delta = (common.Rotation.multVec(App.Vector(0, 0, 31)) if arrangement == "different-parts"
                 else App.Vector(21, -17, 33))
        parent.Placement = App.Placement(delta, App.Rotation()).multiply(parent.Placement)
        doc.recompute()
        after_states = [list(o.State) for o in members]
        wait_poll(panel)
        if arrangement == "different-parts":
            check(arrangement + " moved parent invalidates both", not panel.isValid()
                  and panel._candidate is None and panel._preview is None)
            assert_ok_enabled(check, arrangement + " moved parent", panel, False)
            check(arrangement + " stale parent preview cannot confirm", not panel.accept())
        else:
            check(arrangement + " moved parent preview remains valid", panel.isValid() and panel._preview is not None)
            fresh = MemberMiterController(doc, members=members).evaluate()
            for obj, native, expected in zip(members, panel._preview.previews, fresh.global_shapes):
                assert_shape(check, arrangement + " refreshed world preview " + obj.Name, native.shape, expected)
            check(arrangement + " refreshed world encounter", App.Vector(*panel._candidate.plan.point).sub(
                common.multVec(App.Vector()).add(delta)).Length < 1e-5)
        check(arrangement + " old world branches removed", all(node is None or scene.findChild(node) < 0
                                                               for scene, node in old_nodes))
        # Parent moves must not be converted into member-local edits by preview.
        check(arrangement + " preview preserves member local inputs", same(before, [state(o) for o in members]))
        rows.append(dict(arrangement=arrangement + "-parent-move", child_states_before=child_states,
                         child_states_after=after_states, diagnostic=panel._last_error))
        nodes = preview_nodes(panel._preview) if panel._preview is not None else old_nodes
        panel.reject()
        QtWidgets.QApplication.processEvents()
        assert_cleanup(check, arrangement + " parent preview cancel", panel, nodes)
        App.closeDocument(document_name)

    # The pre-existing member executor resolves a linked opposite support in
    # its own frame. A transformed parent makes that convention ambiguous, so
    # the MVP explicitly rejects it instead of silently treating it as world.
    doc = App.newDocument("MiterParentAssociation")
    members, _, _ = container_pair(doc, "same-part")
    reference = doc.addObject("Part::Feature", "LocalOppositeSupport")
    reference.Shape = Part.makePlane(1000, 1000, App.Vector(900, 0, 0), App.Vector(1, 0, 0))
    a, b = members
    a.EndAdjustmentMode, a.EndAdjustmentGeometryMode = "Associative", "LengthLimit"
    a.EndAdjustmentReference = (reference, ["Face1"])
    doc.recompute()
    before, undo = [state(o) for o in members], doc.UndoCount
    error = None
    try:
        MemberMiterController(doc, members=members).apply()
    except ValueError as exc:
        error = str(exc)
    check("transformed opposite association explicitly rejected", bool(error) and "associativ" in error.lower())
    check("transformed opposite association rejection preserves pair", same(before, [state(o) for o in members])
          and undo == doc.UndoCount)
    rows.append(dict(arrangement="transformed-opposite-association", error=error))
    App.closeDocument(doc.Name)
    (out / "container-cases.json").write_text(json.dumps(rows, indent=2), encoding="utf-8")


def ui_probe(out, check):
    import FreeCAD as App
    import FreeCADGui as Gui
    from PySide import QtCore, QtGui, QtWidgets
    from PySide6 import QtTest
    from pivy import coin
    from freecad.SteelStructures.interactive.member_miter_task_panel import MemberMiterTaskPanel
    chosen = profiles()
    def show(doc, members=()):
        def closed(panel, _accepted):
            if panel.form is not None:
                Gui.Control.closeDialog()
        panel = MemberMiterTaskPanel(doc, members=members, on_closed=closed)
        Gui.Control.showDialog(panel)
        QtWidgets.QApplication.processEvents()
        QtWidgets.QApplication.sendPostedEvents(panel.form)
        return panel
    for mode in ("accept", "cancel", "escape", "close", "native-close", "invalid", "delete", "view", "document-close", "document-switch", "capture"):
        doc = App.newDocument("MiterLifecycle")
        document_name = doc.Name
        doc.UndoMode = 1
        members = pair(doc, chosen["SHS"])
        panel = show(doc, () if mode == "capture" else members)
        if mode == "capture":
            check("empty panel invalid after mounting", not panel.isValid())
            assert_ok_enabled(check, "empty panel after mounting", panel, False)
            assert_message_style(out, check, "miter-info", panel, "info")
            for index, obj in enumerate(members):
                panel._begin_capture(index)
                assert_ok_enabled(check, "selection pending " + str(index), panel, False)
                Gui.Selection.clearSelection()
                Gui.Selection.addSelection(doc.Name, obj.Name)
                QtWidgets.QApplication.processEvents()
                assert_ok_enabled(check, "selection complete " + str(index), panel, index == 1)
            QtWidgets.QApplication.processEvents()
            check("interactive captures both members", tuple(panel.controller.members) == members)
            panel._begin_capture(0)
            assert_ok_enabled(check, "replace selection pending", panel, False)
            check("pending selection cannot confirm", not panel.accept())
            Gui.Selection.clearSelection()
            Gui.Selection.addSelection(doc.Name, members[0].Name)
            QtWidgets.QApplication.processEvents()
            assert_ok_enabled(check, "replacement selection complete", panel, True)
        check(mode + " bilateral candidate valid", panel.isValid() and panel._candidate is not None and panel._preview is not None)
        preview = panel._preview
        check(mode + " owns two previews", len(preview.previews) == 2)
        for obj, shape, native in zip(panel._candidate.members, panel._candidate.global_shapes, preview.previews):
            assert_shape(check, mode + " preview fidelity " + obj.Name, native.shape, shape)
            check(mode + " Coin attached " + obj.Name, native.scene_graph.findChild(native.node) >= 0)
            action = coin.SoGetBoundingBoxAction(coin.SbViewportRegion(800, 600))
            action.apply(native.node)
            check(mode + " Coin finite geometry " + obj.Name, not action.getBoundingBox().isEmpty())
        before, undo, names = [state(o) for o in members], doc.UndoCount, [o.Name for o in doc.Objects]
        nodes = preview_nodes(preview)
        if mode == "accept":
            assert_message_style(out, check, "miter-success", panel, "success")
            view = Gui.activeDocument().activeView()
            view.viewAxonometric()
            view.fitAll()
            view.redraw()
            panel.form.grab().save(str(out / "miter-panel.png"))
            # A transparent child grab omits the Task View backing surface.
            # Keep the composed window for theme/contrast inspection too.
            Gui.getMainWindow().grab().save(str(out / "miter-window.png"))
            view.saveImage(str(out / "miter-preview.png"), 1000, 700, "Current")
            image = QtGui.QImage(str(out / "miter-preview.png"))
            check("native viewport capture valid", not image.isNull())
            with_preview = hashlib.sha256(image.constBits().tobytes()).hexdigest()
            shape_nodes = [(item.scene_graph, item.node) for item in preview.previews]
            for scene, node in shape_nodes:
                scene.removeChild(node)
            try:
                view.redraw()
                view.saveImage(str(out / "miter-without-preview.png"), 1000, 700, "Current")
            finally:
                for scene, node in shape_nodes:
                    scene.addChild(node)
            image = QtGui.QImage(str(out / "miter-without-preview.png"))
            check("render includes candidate solids", with_preview != hashlib.sha256(image.constBits().tobytes()).hexdigest())
            expected = [item.shape.copy() for item in preview.previews]
            check("UI accepts bilateral transaction", panel.accept())
            QtWidgets.QApplication.processEvents()
            assert_cleanup(check, mode, panel, nodes)
            check("UI accept one Undo and no helper", doc.UndoCount == undo + 1 and names == [o.Name for o in doc.Objects])
            for obj, shape in zip(members, expected):
                assert_shape(check, "UI preview equals commit " + obj.Name, world_shape(obj), shape)
            doc.undo()
            doc.recompute()
            check("UI one Undo restores both", same(before, [state(o) for o in members]))
            doc.redo()
            doc.recompute()
            check("UI Redo keeps both nominal axes", all(same(before[i]["inputs"][key], state(obj)["inputs"][key])
                  for i, obj in enumerate(members) for key in ("StartPoint", "EndPoint")))
        else:
            if mode == "invalid":
                members[1].OffsetX = 100
                doc.recompute()
                before = [state(o) for o in members]
                wait_poll(panel)
                check("invalid clears entire preview", panel._preview is None and panel._candidate is None)
                check("invalid cannot confirm", not panel.isValid() and not panel.accept())
                assert_message_style(out, check, "miter-error", panel, "error")
                panel.reject()
            elif mode == "escape":
                panel.form.setFocus()
                QtTest.QTest.keyClick(panel.form, QtCore.Qt.Key_Escape)
            elif mode == "close":
                panel.form.close()
            elif mode == "native-close":
                Gui.Control.closeDialog()
            elif mode == "delete":
                doc.removeObject(members[1].Name)
                doc.recompute()
                wait_poll(panel)
                if not panel._closed:
                    check("deleted member disables OK", not panel.isValid())
                    panel.reject()
            elif mode == "view":
                Gui.activeDocument().createView("Gui::View3DInventor")
                wait_poll(panel)
                check("both previews move to active view", panel._preview is not None
                      and all(item.scene_graph != nodes[0][0] for item in panel._preview.previews)
                      and all(node is None or scene.findChild(node) < 0 for scene, node in nodes))
                nodes = preview_nodes(panel._preview)
                panel.reject()
            elif mode == "document-close":
                App.closeDocument(doc.Name)
                wait_poll(panel)
                if not panel._closed:
                    panel.reject()
            elif mode == "document-switch":
                other = App.newDocument("MiterOtherDocument")
                wait_poll(panel)
                check("other document clears pair preview", panel._preview is None and not panel.isValid())
                panel.reject()
                App.closeDocument(other.Name)
            else:
                panel.reject()
            QtWidgets.QApplication.processEvents()
            assert_cleanup(check, mode, panel, nodes)
            if mode not in ("delete", "document-close"):
                check(mode + " preserves both/Undo/tree", same(before, [state(o) for o in members])
                      and undo == doc.UndoCount and names == [o.Name for o in doc.Objects])
        if document_name in App.listDocuments():
            App.closeDocument(document_name)


def command_probe(check):
    import FreeCAD as App
    import FreeCADGui as Gui
    from PySide import QtWidgets
    from freecad.SteelStructures import commands, init_gui
    doc = App.newDocument("MiterCommand")
    doc.UndoMode = 1
    members = pair(doc, profiles()["SHS"])
    before, undo, names = [state(o) for o in members], doc.UndoCount, [o.Name for o in doc.Objects]
    Gui.Selection.clearSelection()
    for obj in members:
        Gui.Selection.addSelection(obj)
    commands.MiterMembersCommand().Activated()
    panel = commands._active_miter_panel
    check("public command uses both preselected members", panel is not None
          and tuple(panel.controller.members) == members and panel.isValid())
    nodes = preview_nodes(panel._preview)
    # Exercise the actual production workbench deactivation hook; no other
    # workbench/Draft session needs to be initialized for this owned task.
    init_gui.SteelStructuresWorkbench.Deactivated(None)
    QtWidgets.QApplication.processEvents()
    assert_cleanup(check, "workbench deactivation", panel, nodes)
    check("workbench deactivation releases command ownership", commands._active_miter_panel is None)
    check("deactivation preserves both/Undo/tree", same(before, [state(o) for o in members])
          and undo == doc.UndoCount and names == [o.Name for o in doc.Objects])
    App.closeDocument(doc.Name)


def run(out):
    import FreeCAD as App
    from PySide import QtCore, QtWidgets
    qss = os.environ.get("SS_MITER_QSS")
    if qss:
        path = Path(qss)
        QtCore.QDir.addSearchPath("qss", str(path.parent))
        QtWidgets.QApplication.instance().setStyleSheet(path.read_text(encoding="utf-8"))
    checks, callback_errors = [], []
    original_hook = sys.excepthook
    sys.excepthook = lambda kind, error, trace: callback_errors.append("".join(traceback.format_exception(kind, error, trace)))
    def check(label, condition):
        if not condition:
            raise AssertionError(label)
        checks.append(label)
        (out / "checks.json").write_text(json.dumps(checks, indent=2), encoding="utf-8")
    try:
        native_history = abort_history_probe(out, check)
        candidate_probe(out, check)
        invalid_probe(out, check)
        transaction_probe(out, check)
        replay_probe(out, check, native_history)
        container_probe(out, check)
        ui_probe(out, check)
        command_probe(check)
        check("no Python/Qt callback errors", not callback_errors)
        return dict(ok=True, version=App.Version()[:3], theme=os.environ.get("SS_MITER_THEME"),
                    checks=checks, callback_errors=callback_errors)
    finally:
        sys.excepthook = original_hook
        (out / "callback-errors.json").write_text(json.dumps(callback_errors, indent=2), encoding="utf-8")


if os.environ.get("SS_MITER_ROOT"):
    import FreeCAD as App
    from PySide import QtCore, QtWidgets
    root = Path(os.environ["SS_MITER_ROOT"])
    out = Path(os.environ["SS_MITER_OUT"])
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
