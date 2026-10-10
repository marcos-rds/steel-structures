"""Native local-tracker gate, then unified public-command gate. No monkeypatch."""
from collections import Counter
import faulthandler
import hashlib
import json
import os
from pathlib import Path
import sys
import time
import traceback

sys.dont_write_bytecode = True
ROOT = Path(os.environ["PLATE_UNIFIED_ROOT"])
RUN = Path(os.environ["PLATE_UNIFIED_RUN"])
STAGE = os.environ["PLATE_UNIFIED_STAGE"]
CYCLES = int(os.environ["PLATE_UNIFIED_CYCLES"])
EVENTS = (RUN / "events.jsonl").open("a", encoding="utf-8", buffering=1)
FAULT = (RUN / "fault.log").open("a", encoding="utf-8")
faulthandler.enable(file=FAULT, all_threads=True)
result = dict(ok=False, stage=STAGE, cycles=CYCLES, pid=os.getpid(), checks=[], real_coin_events={})


def log(phase, **values):
    EVENTS.write(json.dumps(dict(time=time.time(), pid=os.getpid(), phase=phase, **values)) + "\n")
    EVENTS.flush()
    os.fsync(EVENTS.fileno())


def passed(name):
    result["checks"].append(name)
    log("check_passed", name=name)
    save()


def save():
    (RUN / "result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")


log("entry_before_gui_imports")
import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtCore, QtGui, QtWidgets
from PySide6 import QtTest
log("gui_imported", version=App.Version())
result["version"] = App.Version()
from draftutils import params as draft_params
result["draft_shortcut_audit"] = {key: draft_params.get_param("inCommandShortcut" + key)
                                 for key in ("Relative", "Global", "Continue", "Undo", "Close", "Wipe", "Length", "RestrictX", "RestrictY", "RestrictZ", "MakeFace", "Exit", "AddHold", "Recenter", "Snap", "Copy", "SetWP", "SelectEdge", "SubelementMode")}


def pump():
    for _ in range(12):
        QtWidgets.QApplication.processEvents()


def viewer():
    QtWidgets.QApplication.setActiveWindow(Gui.getMainWindow())
    mdi = Gui.getMainWindow().findChild(QtWidgets.QMdiArea)
    window = mdi.activeSubWindow()
    if window is None:
        # Hidden native tests can retain a FreeCAD active view without Qt MDI
        # activation. There is exactly one Coin viewer in this isolated test.
        candidates = [w for w in Gui.getMainWindow().findChildren(QtWidgets.QWidget)
                      if w.inherits("SIM::Coin3D::Quarter::QuarterWidget")]
        log("harness_viewer_without_mdi_activation", viewers=len(candidates),
            mdi_areas=[dict(name=area.objectName(), windows=len(area.subWindowList()))
                       for area in Gui.getMainWindow().findChildren(QtWidgets.QMdiArea)])
        assert len(candidates) == 1, "Harness requires one unambiguous Coin viewer"
        widget = candidates[0]
    else:
        widget = next(w for w in window.findChildren(QtWidgets.QWidget)
                      if w.inherits("SIM::Coin3D::Quarter::QuarterWidget"))
    QtWidgets.QApplication.setActiveWindow(Gui.getMainWindow())
    widget.setFocus()
    return widget


def move(point=None, modifiers=QtCore.Qt.NoModifier):
    widget = viewer()
    point = widget.rect().center() if point is None else point
    event = QtGui.QMouseEvent(QtCore.QEvent.MouseMove, QtCore.QPointF(point),
                             QtCore.QPointF(widget.mapToGlobal(point)), QtCore.Qt.NoButton,
                             QtCore.Qt.NoButton, modifiers)
    QtWidgets.QApplication.sendEvent(widget, event)
    pump()
    return point


def click(point):
    QtTest.QTest.mouseClick(viewer(), QtCore.Qt.LeftButton, pos=point)
    pump()


def escape():
    QtTest.QTest.keyClick(viewer(), QtCore.Qt.Key_Escape)
    pump()


def panel_key(key):
    viewport = viewer()
    viewport.setFocus()
    pump()
    assert viewport.hasFocus()
    QtTest.QTest.keyClicks(viewport, key)
    pump()


def native_graphical_key(tool, key):
    """Do not force viewport focus after Draft has presented a mouse point."""
    count = result.get("native_programmatic_focus_keys", 0)
    # Draft deliberately delays mouse re-entry after a real numeric keystroke.
    if not tool.ui.mouse:
        QtTest.QTest.qWait(int(draft_params.get_param("MouseDelay") * 1000) + 100)
    move(QtCore.QPoint(120 + count * 3, 150 + count * 2))
    focus = QtWidgets.QApplication.focusWidget()
    from freecad.SteelStructures.interactive.plate_panel_shortcuts import editable_focus
    assert editable_focus(focus), "Harness must reproduce Draft's automatic field focus"
    assert not tool._coordinate_focus.protects(focus) and tool.ui.mouse
    QtTest.QTest.keyClicks(focus, key)
    pump()
    result["native_programmatic_focus_keys"] = count + 1


def numeric(tool, coordinates, relative=False, global_axes=False, enter=False):
    """Use native Draft fields and validation/conversion, not numericInput directly."""
    ui = tool.ui
    QtWidgets.QApplication.setActiveWindow(Gui.getMainWindow())
    ui.isGlobal.setChecked(global_axes)
    ui.isRelative.setChecked(relative)
    for field, value in zip((ui.xValue, ui.yValue, ui.zValue), coordinates):
        field.setFocus()
        assert field.hasFocus(), "Native field lacks Qt focus"
        field.setText(QtCore.QLocale().toString(float(value), "g", 17) + " mm")
    pump()
    if enter:
        field = ui.zValue if ui.zValue.isEnabled() else ui.yValue
        field.setFocus()
        QtTest.QTest.keyClick(field, QtCore.Qt.Key_Return)
    else:
        ui.pointButton.click()
    pump()


def wp_state(wp):
    return wp.get_parameters(), dict(wp._stored), repr(wp._history)


def clean(tool, scene, switch=None):
    from draftutils.todo import ToDo
    assert tool.call is None and tool._state == "FINISHED"
    assert not tool._observer_installed
    assert App.activeDraftCommand is None and not Gui.Control.activeDialog()
    if switch is not None:
        assert scene.findChild(switch) < 0
    assert not ToDo.itinerary and not ToDo.commitlist and not ToDo.afteritinerary


def plates(doc):
    return [obj for obj in doc.Objects if getattr(obj, "ContourData", None)]


def validate_plate(doc, expected=1):
    found = plates(doc)
    assert len(found) == expected, [obj.Name for obj in doc.Objects]
    assert len(doc.Objects) == expected, "Persistent intermediate Draft/preview object"
    for obj in found:
        assert obj.Shape.isValid() and not obj.Shape.isNull() and obj.Shape.Volume > 0
    return found


def remove_plates(doc):
    Gui.Selection.clearSelection()
    for obj in plates(doc):
        doc.removeObject(obj.Name)
    doc.recompute()
    pump()


def tracker_gate(doc, wp):
    from draftguitools import gui_trackers
    from freecad.SteelStructures.interactive.draft_plate_rectangle_tool import StructuralPlateRectangleTool
    from freecad.SteelStructures.interactive.plate_rectangle_tracker import PlateRectangleTracker
    original = gui_trackers.rectangleTracker
    original_init = original.__init__
    expected_source = ROOT / "freecad/SteelStructures/interactive/plate_rectangle_tracker.py"
    assert Path(PlateRectangleTracker.__init__.__code__.co_filename).resolve() == expected_source.resolve()
    result["tracker_sha256"] = hashlib.sha256(expected_source.read_bytes()).hexdigest()
    events = Counter()

    class TracedRectangle(StructuralPlateRectangleTool):
        def action(self, event):
            events[event.get("Type")] += 1
            return super().action(event)

    initial = wp_state(wp)
    for cycle in range(CYCLES):
        mode = ("escape_empty", "escape_preview", "mouse_create", "numeric_create")[cycle % 4]
        log("before_tracker_activate", cycle=cycle, mode=mode)
        tool = TracedRectangle()
        tool.Activated()
        pump()
        assert type(tool.rect) is PlateRectangleTracker
        assert tool.rect.coords.point.getNum() == 5
        assert gui_trackers.rectangleTracker is original and original.__init__ is original_init
        tool.ui.continueCmd.setChecked(False)
        scene, switch = tool.view.getSceneGraph(), tool.rect.switch
        if mode == "numeric_create":
            numeric(tool, (0, 0, 0), global_axes=True)
            assert len(tool.node) == 1
            tool.ui.isRelative.setChecked(True)
            tool.ui.isRelative.setChecked(False)
            numeric(tool, (40, 25, 0), global_axes=True, enter=True)
        else:
            center = move()
            if mode != "escape_empty":
                click(center)
                assert len(tool.node) == 1
                opposite = center + QtCore.QPoint(80, 60)
                move(opposite)
                assert tool.rect.Visible
            if mode == "mouse_create":
                click(opposite)
            else:
                escape()
        clean(tool, scene, switch)
        assert wp_state(wp) == initial
        if mode.endswith("create"):
            validate_plate(doc)
            remove_plates(doc)
        else:
            assert not doc.Objects
        count = sum(events.values())
        move()
        assert sum(events.values()) == count
        passed("tracker_%02d_%s" % (cycle, mode))
    assert all(events[kind] for kind in ("SoLocation2Event", "SoMouseButtonEvent", "SoKeyboardEvent"))
    result["real_coin_events"] = dict(events)


def integrated_gate(doc, wp):
    from freecad.SteelStructures import commands
    from freecad.SteelStructures.interactive.plate_rectangle_tracker import PlateRectangleTracker
    from draftguitools import gui_trackers
    native_tracker = gui_trackers.rectangleTracker
    assert "SteelStructures_CreatePlateRectangle" not in Gui.listCommands()
    initial = wp_state(wp)

    def opened(shape="Rectangle"):
        assert not Gui.Control.activeDialog() and App.activeDraftCommand is None
        Gui.Selection.clearSelection()
        Gui.runCommand("SteelStructures_CreatePlate")
        result["public_command_activations"] = result.get("public_command_activations", 0) + 1
        pump()
        session = commands._active_plate_session
        assert session is not None and session.tool is App.activeDraftCommand
        if session.shape != shape:
            combo = session.tool.shape_combo
            combo.setCurrentIndex(combo.findData(shape))
            pump()
        assert session.shape == shape and session.tool.is_active()
        assert session.panel is None and session.tool.ui.sourceCmd is session.tool
        assert session.tool.call is not None
        assert session.tool.options.layout().itemAt(
            session.tool.options.layout().count() - 1).widget() is session.tool.options.status
        if shape == "Polygon":
            for row, column, button in ((0, 0, session.tool.ui.pointButton),
                                        (0, 1, session.tool.ui.undoButton),
                                        (1, 0, session.tool.ui.closeButton),
                                        (1, 1, session.tool.ui.wipeButton)):
                assert session.tool.point_actions.itemAtPosition(row, column).widget() is button
        else:
            assert session.tool.point_actions.count() == 1
        if shape == "Rectangle":
            assert type(session.tool.rect) is PlateRectangleTracker
            assert session.tool.rect.coords.point.getNum() == 5
            assert gui_trackers.rectangleTracker is native_tracker
            result["unified_tracker_runtime"] = dict(
                type=type(session.tool.rect).__name__, vectors=session.tool.rect.coords.point.getNum(),
                constructor=PlateRectangleTracker.__init__.__code__.co_filename,
                native_global_unchanged=True)
        session.tool.ui.continueCmd.setChecked(False)
        return session, session.tool

    def automatic(tool):
        assert not hasattr(tool, "advanced_button"), "Redundant polygon advanced entry"
        # A user selects this combo with focus in the live task panel. Keep
        # the hidden harness focused too, as numeric() does for Draft fields.
        QtWidgets.QApplication.setActiveWindow(Gui.getMainWindow())
        tool.plane_combo.setFocus()
        assert tool.plane_combo.hasFocus()
        tool.plane_combo.setCurrentIndex(tool.plane_combo.findData("Auto"))
        pump()
        session = commands._active_plate_session
        assert session.plane == "Auto" and session.tool is None
        assert App.activeDraftCommand is None and tool._state == "FINISHED" and tool.call is None
        panel = session.panel
        assert panel.footer_form.layout().itemAt(0).widget() is panel.status
        assert panel.coordinate_input.candidate_status.isHidden()
        for row, column, button in ((0, 0, panel.coordinate_input.add_button),
                                    (0, 1, panel.undo_button), (1, 0, panel.close_button),
                                    (1, 1, panel.clear_button)):
            assert panel.point_actions.itemAtPosition(row, column).widget() is button
        assert panel.controller._callbacks and panel.controller.placement is None
        assert panel.controller._selected_plane_face is None
        assert panel.controller._selected_face_placement is None
        assert wp_state(wp) == initial
        assert panel.coordinate_input.global_coordinates.isChecked()
        assert not panel.coordinate_input.global_coordinates.isEnabled()
        task_box = panel.input_form
        while task_box is not None and not task_box.inherits("Gui::TaskView::TaskBox"):
            task_box = task_box.parentWidget()
        assert task_box is not None
        task_box.grab().save(str(RUN / "automatic_input.png"))
        task_box.parentWidget().grab().save(str(RUN / "automatic_panel.png"))
        return session, panel

    def automatic_numeric(panel, coordinates):
        widget = panel.coordinate_input
        QtWidgets.QApplication.setActiveWindow(Gui.getMainWindow())
        for field, value in zip(widget.fields, coordinates):
            field.setFocus()
            assert field.hasFocus()
            field.setText(str(float(value)) + " mm")
        pump()
        assert widget.add_button.isEnabled()
        widget.add_button.click()
        pump()

    def clean_automatic(controller):
        assert controller._teardown_done and not controller._callbacks
        assert not controller._capturing and controller.preview._scene is None
        assert commands._active_plate_session is None
        assert App.activeDraftCommand is None and not Gui.Control.activeDialog()
        assert wp_state(wp) == initial

    session, tool = opened()
    tool.options.thickness.setValue(7.5)
    tool.options.offset.setValue(-2.5)
    old = tool
    tool.shape_combo.setCurrentIndex(tool.shape_combo.findData("Polygon"))
    pump()
    assert session.tool is not old and old._state == "FINISHED"
    tool = session.tool
    assert tool.options.thickness.value() == 7.5 and tool.options.offset.value() == -2.5
    numeric(tool, (0, 0, 0))
    tool.shape_combo.setCurrentIndex(tool.shape_combo.findData("Rectangle"))
    pump()
    assert session.shape == "Polygon" and session.tool is tool and len(tool.node) == 1
    tool.restart_button.click()
    pump()
    assert tool.node == []
    tool.shape_combo.setCurrentIndex(tool.shape_combo.findData("Rectangle"))
    pump()
    assert session.shape == "Rectangle" and session.tool is not tool
    assert session.tool.options.thickness.value() == 7.5 and session.tool.options.offset.value() == -2.5
    session.tool.ui.panel.reject()
    pump()
    assert not doc.Objects and wp_state(wp) == initial
    passed("shape_switch_blocked_then_explicit_restart")

    session, tool = opened("Polygon")
    numeric(tool, (0, 0, 0))
    numeric(tool, (40, 0, 0))
    tool.ui.closeButton.click()
    pump()
    assert tool.is_active() and not plates(doc)
    tool.ui.undoButton.click()
    pump()
    assert len(tool.node) == 1
    tool.ui.wipeButton.click()
    pump()
    assert not tool.node
    for point in ((0, 0, 0), (40, 0, 0), (40, 25, 0), (0, 25, 0)):
        numeric(tool, point)
    tool.ui.closeButton.click()
    pump()
    clean(tool, tool.view.getSceneGraph())
    validate_plate(doc)
    remove_plates(doc)
    passed("polygon_numeric_close_undo_clear_invalid_open")

    session, tool = opened("Polygon")
    for point in ((0, 0, 0), (40, 25, 0), (0, 25, 0), (40, 0, 0)):
        numeric(tool, point)
    tool.ui.closeButton.click()
    pump()
    assert tool.is_active() and not plates(doc)
    escape()
    assert not doc.Objects
    passed("polygon_self_intersection_rejected_and_escape")

    session, tool = opened("Polygon")
    center = viewer().rect().center()
    for point in (center, center + QtCore.QPoint(100, 0), center + QtCore.QPoint(50, 80)):
        move(point)
        click(point)
    assert len(tool.node) == 3
    tool.ui.closeButton.click()
    pump()
    validate_plate(doc)
    remove_plates(doc)
    passed("polygon_mouse_close")

    session, tool = opened("Polygon")
    center = viewer().rect().center()
    for point in (center, center + QtCore.QPoint(100, 0), center + QtCore.QPoint(50, 80), center):
        move(point)
        click(point)
    validate_plate(doc)
    remove_plates(doc)
    passed("polygon_mouse_repeated_first_closes")

    session, tool = opened("Polygon")
    for point in ((0, 0, 0), (40, 0, 0), (20, 25, 0), (0, 0, 0)):
        numeric(tool, point)
    validate_plate(doc)
    remove_plates(doc)
    passed("polygon_repeated_first_closes")

    session, tool = opened("Polygon")
    numeric(tool, (0, 0, 0))
    numeric(tool, (30, 20, 0))
    escape()
    assert not doc.Objects
    passed("polygon_open_escape_no_plate")

    session, tool = opened()
    numeric(tool, (0, 0, 0), global_axes=True)
    tool.ui.isRelative.setChecked(False)
    tool.ui.isRelative.setChecked(True)
    numeric(tool, (40, 25, 0), relative=True, global_axes=True, enter=True)
    validate_plate(doc)
    remove_plates(doc)
    passed("rectangle_numeric_relative_global_enter_p2_toggle")

    session, tool = opened()
    center = move()
    click(center)
    tool.ui.isRelative.setChecked(False)
    tool.ui.isRelative.setChecked(True)
    tool.ui.isGlobal.setChecked(True)
    tool.ui.isGlobal.setChecked(False)
    move(center + QtCore.QPoint(90, 65))
    first_preview = tuple(tool.point)
    move(center + QtCore.QPoint(110, 75))
    assert tuple(tool.point) != first_preview and tool.rect.Visible and tool.ui.mouse
    click(center + QtCore.QPoint(110, 75))
    validate_plate(doc)
    remove_plates(doc)
    passed("rectangle_graphical_p2_moves_after_relative_global_toggles")

    for shape in ("Rectangle", "Polygon"):
        session, tool = opened(shape)
        tool.options.thickness.setValue(7)
        tool.options.offset.setValue(-2)
        tool.ui.continueCmd.setChecked(True)
        callback, panel, tracker = tool.call, tool.ui.panel, tool.rect
        for count in range(3):
            for index, point in enumerate(((0, 0, 0), (40, 0, 0), (0, 25, 0)) if shape == "Polygon"
                                           else ((0, 0, 0), (40, 25, 0))):
                numeric(tool, point, enter=True)
            if shape == "Polygon":
                tool.ui.closeButton.click()
                pump()
            assert tool.is_active() and not tool.node
            assert tool.call == callback and tool.ui.panel is panel and tool.rect is tracker
            assert len(plates(doc)) == count + 1
            assert tool.last_created.Thickness.Value == 7 and tool.last_created.Offset.Value == -2
        tool.finish()
        pump()
        validate_plate(doc, 3)
        remove_plates(doc)
    passed("consecutive_creation_same_owner_thickness_offset_both_shapes")

    frame = App.Placement(App.Vector(10, -20, 30), App.Rotation(App.Vector(0, 1, 0), 35))
    wp.align_to_placement(frame, _hist_add=False)
    tilted = wp_state(wp)
    for shape in ("Rectangle", "Polygon"):
        for global_axes in (False, True):
            session, tool = opened(shape)
            points = ((0, 0, 0), (40, 0, 0), (0, 25, 0)) if shape == "Polygon" else ((0, 0, 0), (40, 25, 0))
            for point in points:
                value = tuple(frame.multVec(App.Vector(*point))) if global_axes else point
                numeric(tool, value, global_axes=global_axes)
            if shape == "Polygon":
                tool.ui.closeButton.click()
                pump()
            created = validate_plate(doc)[0]
            assert created.Placement.Base == frame.Base
            assert created.Placement.Rotation.isSame(frame.Rotation, 1e-8)
            assert wp_state(wp) == tilted
            remove_plates(doc)
    wp.set_parameters(initial[0])
    wp._stored = initial[1]
    wp._update_all(_hist_add=False)
    passed("tilted_current_wp_local_global_polygon_rectangle_restore")

    import Part
    snap_object = doc.addObject("Part::Feature", "SnapReference")
    snap_object.Shape = Part.makePolygon([App.Vector(20, 20, 0), App.Vector(50, 20, 0), App.Vector(50, 50, 0)])
    doc.recompute()
    view = Gui.activeDocument().activeView()
    view.fitAll()
    session, tool = opened("Polygon")
    Gui.Snapper.toggle_snap("Lock", True)
    Gui.Snapper.toggle_snap("Endpoint", True)
    target = App.Vector(20, 20, 0)
    screen = view.getPointOnScreen(target)
    position = QtCore.QPoint(int(screen[0]), viewer().height() - int(screen[1]))
    move(position, QtCore.Qt.ControlModifier)
    assert tool.point is not None and (tool.point - target).Length < 1e-5, (tool.point, target)
    click(position)
    assert len(tool.node) == 1
    move(position + QtCore.QPoint(80, 60))
    from draftutils import params
    panel_key(params.get_param("inCommandShortcutRestrictX"))
    pump()
    assert tool.ui.mask == "x" and Gui.Snapper.mask == "x"
    move(position + QtCore.QPoint(110, 70))
    assert abs(tool.point.y - tool.node[-1].y) < 1e-5
    escape()
    doc.removeObject(snap_object.Name)
    pump()
    passed("native_endpoint_snap_and_keyboard_x_constraint_real_coin")

    import Part
    reference = doc.addObject("Part::Feature", "PlaneReference")
    reference.Shape = Part.makeBox(30, 20, 8)
    reference.Placement = App.Placement(App.Vector(10, -20, 30), App.Rotation(App.Vector(0, 1, 0), 35))
    doc.recompute()
    Gui.Selection.clearSelection()
    Gui.Selection.addSelection(reference, "Face6")
    Gui.runCommand("SteelStructures_CreatePlate")
    pump()
    session = commands._active_plate_session
    tool = session.tool
    assert session.plane == "Face" and tool.placement.Rotation != App.Rotation()
    face_frame = App.Placement(tool.placement)
    tool.plane_combo.setCurrentIndex(tool.plane_combo.findData("WorkPlane"))
    pump()
    tool = session.tool
    assert session.plane == "WorkPlane" and tool.placement == App.Placement()
    tool.plane_combo.setCurrentIndex(tool.plane_combo.findData("Face"))
    pump()
    tool = session.tool
    assert session.plane == "Face" and tool.placement == face_frame
    tool.ui.continueCmd.setChecked(False)
    numeric(tool, (0, 0, 0))
    numeric(tool, (20, 15, 0))
    assert len(plates(doc)) == 1 and len(doc.Objects) == 2
    plate = plates(doc)[0]
    assert plate.SourceObject is None
    assert wp_state(wp) == initial
    remove_plates(doc)

    # Preselection remains the default; Auto explicitly releases that reference.
    Gui.Selection.clearSelection()
    Gui.Selection.addSelection(reference, "Face6")
    Gui.runCommand("SteelStructures_CreatePlate")
    pump()
    session = commands._active_plate_session
    session.tool.shape_combo.setCurrentIndex(session.tool.shape_combo.findData("Polygon"))
    pump()
    assert session.plane == "Face"
    session, panel = automatic(session.tool)
    previous = panel.controller
    panel.plane_mode.setCurrentIndex(panel.plane_mode.findData("Face"))
    pump()
    assert previous._teardown_done and not previous._callbacks
    tool = session.tool
    assert session.panel is None and session.plane == "Face" and tool.placement == face_frame
    tool.ui.continueCmd.setChecked(False)
    for point in ((0, 0, 0), (20, 0, 0), (0, 15, 0)):
        numeric(tool, point)
    tool.ui.closeButton.click()
    pump()
    assert len(plates(doc)) == 1 and wp_state(wp) == initial
    assert plates(doc)[0].SourceObject is None
    remove_plates(doc)
    doc.removeObject(reference.Name)
    passed("selected_face_polygon_rectangle_auto_roundtrip_temporary_wp_restore")

    session, tool = opened()
    tool.advanced_button.click()
    pump()
    assert session.tool is None and App.activeDraftCommand is None and session.panel is not None
    panel = session.panel
    assert panel.controller._callbacks
    panel.reverse.setChecked(True)
    panel.offset.setValue(2)
    for point in ((0, 0, 0), (40, 0, 20), (40, 25, 20)):
        panel.controller.add_point(App.Vector(*point))
    assert panel.controller.contour is not None
    panel.accept()
    pump()
    validate_plate(doc)
    created = plates(doc)[0]
    assert created.ReverseExtrusion
    local_shape = created.Shape.copy()
    local_shape.Placement = App.Placement()
    assert abs(local_shape.BoundBox.ZMin + 8) < 1e-5 and abs(local_shape.BoundBox.ZMax - 2) < 1e-5
    remove_plates(doc)
    passed("advanced_rectangle_3p_isolated_capture")

    for name, rotation in (("XY", App.Rotation()),
                           ("XZ", App.Rotation(App.Vector(1, 0, 0), 90)),
                           ("YZ", App.Rotation(App.Vector(0, 1, 0), 90)),
                           ("tilted", App.Rotation(App.Vector(1, 2, 3), 37))):
        session, tool = opened("Polygon")
        session, panel = automatic(tool)
        frame = App.Placement(App.Vector(10, -20, 128), rotation)
        controller = panel.controller
        for index, local in enumerate(((0, 0, 0), (20, 0, 0), (40, 0, 0),
                                       (40, 25, 0), (0, 25, 0))):
            automatic_numeric(panel, tuple(frame.multVec(App.Vector(*local))))
            assert controller.point_count == index + 1
            if index < 3:
                assert controller.placement is None
                assert not panel.coordinate_input.global_coordinates.isEnabled()
            else:
                assert controller.plane_state == "PLANE_DEFINED"
                assert panel.coordinate_input.global_coordinates.isEnabled()
        automatic_numeric(panel, tuple(frame.multVec(App.Vector(0, 0, 8))))
        assert controller.point_count == 5 and "fora do plano" in panel.status.text()
        panel.close_button.click()
        pump()
        # Closed contours also require an explicit restart before switching.
        panel.plane_mode.setCurrentIndex(panel.plane_mode.findData("WorkPlane"))
        pump()
        assert session.panel is panel and panel.plane_mode.currentData() == "Auto"
        assert panel.accept()
        pump()
        created = validate_plate(doc)[0]
        assert (created.Placement.Base - frame.Base).Length < 1e-7
        assert created.Placement.Rotation.isSame(rotation, 1e-8)
        assert abs(created.Shape.Volume - 10000) < 1e-5
        clean_automatic(controller)
        remove_plates(doc)
        passed("automatic_polygon_" + name + "_collinear_numeric_coplanarity")

    reference = doc.addObject("Part::Feature", "AutoSnapReference")
    targets = [App.Vector(*point) for point in ((20, 20, 128), (60, 20, 128),
                                               (60, 60, 128), (20, 60, 128))]
    reference.Shape = Part.makePolygon(targets)
    doc.recompute()
    Gui.activeDocument().activeView().viewTop()
    Gui.activeDocument().activeView().fitAll()
    session, tool = opened("Polygon")
    session, panel = automatic(tool)
    controller = panel.controller
    Gui.Snapper.toggle_snap("Lock", True)
    Gui.Snapper.toggle_snap("Endpoint", True)
    for index, target in enumerate(targets):
        screen = Gui.activeDocument().activeView().getPointOnScreen(target)
        position = QtCore.QPoint(int(screen[0]), viewer().height() - int(screen[1]))
        move(position, QtCore.Qt.ControlModifier)
        assert controller.candidate is not None, panel.status.text()
        assert (App.Vector(*controller.candidate.world) - target).Length < 1e-5
        from freecad.SteelStructures.interactive.coordinate_input_widget import length_value
        assert isinstance(panel.coordinate_input.fields[0], QtWidgets.QLineEdit)
        shown = App.Vector(*(length_value(field.text()) for field in panel.coordinate_input.fields))
        assert (shown - target).Length < 1e-5
        assert not panel.coordinate_input.editing
        if index == 1:
            panel.coordinate_input.relative.setChecked(True)
            pump()
            assert not panel.coordinate_input.editing, "Absolute to Relative froze graphical input"
            assert (App.Vector(*controller.candidate.world) - target).Length < 1e-5
            panel.coordinate_input.relative.setChecked(False)
            pump()
        click(position)
        assert controller.point_count == index + 1, panel.status.text()
        assert abs(controller._world_points()[-1].z - 128) < 1e-5
        if index == 0:
            assert panel.status.text() == "Defina a direção."
        elif index == 1:
            assert panel.status.text() == "Defina o plano."
        else:
            assert panel.status.text() == "Adicione vértices ou feche o contorno."
    panel.close_button.click()
    pump()
    assert panel.accept()
    pump()
    assert len(plates(doc)) == 1
    clean_automatic(controller)
    remove_plates(doc)
    doc.removeObject(reference.Name)
    passed("automatic_real_endpoint_snap_before_after_plane_off_wp")

    # Real geometric depth without snap must come from native picking, never WP.
    reference = doc.addObject("Part::Feature", "AutoHoverReference")
    reference.Shape = Part.makeBox(100, 100, 20, App.Vector(0, 0, 128))
    doc.recompute()
    view = Gui.activeDocument().activeView()
    view.viewTop()
    view.fitAll()
    session, tool = opened("Polygon")
    session, panel = automatic(tool)
    controller = panel.controller
    original_snaps = tuple(Gui.Snapper.active_snaps)
    for snap in original_snaps:
        Gui.Snapper.toggle_snap(snap)
    target = App.Vector(50, 50, 148)
    screen = view.getPointOnScreen(target)
    position = QtCore.QPoint(int(screen[0]), viewer().height() - int(screen[1]))
    move(position)
    assert Gui.Snapper.cursorMode == "passive"
    assert controller.candidate is not None, panel.status.text()
    assert abs(controller.candidate.world[2] - 148) < 1e-5
    assert controller._last_pick_info["Object"] == reference.Name
    assert controller.point_count == 0 and controller.placement is None
    move(QtCore.QPoint(5, 5))
    assert controller.candidate is None and controller.point_count == 0
    assert panel.status.text() == "Use geometria, snap ou XYZ."
    for point in ((0, 0, 128), (40, 0, 128), (40, 25, 128)):
        automatic_numeric(panel, point)
    move(QtCore.QPoint(5, 5))
    assert controller.candidate is not None and abs(controller.candidate.world[2] - 128) < 1e-5
    # Real hover and active endpoint snaps above the plane must be rejected,
    # rather than silently projected onto it.
    move(position)
    assert controller.candidate is None and controller.point_count == 3
    assert controller._last_pick_info["z"] > 147
    Gui.Snapper.toggle_snap("Lock", True)
    Gui.Snapper.toggle_snap("Endpoint", True)
    screen = view.getPointOnScreen(App.Vector(100, 100, 148))
    snap_position = QtCore.QPoint(int(screen[0]), viewer().height() - int(screen[1]))
    move(snap_position, QtCore.Qt.ControlModifier)
    assert Gui.Snapper.cursorMode != "passive"
    assert controller.candidate is None and controller.point_count == 3
    assert controller._last_effective_point.z > 147
    for snap in tuple(Gui.Snapper.active_snaps):
        Gui.Snapper.toggle_snap(snap)
    for snap in original_snaps:
        if snap not in Gui.Snapper.active_snaps:
            Gui.Snapper.toggle_snap(snap)
    panel.reject()
    pump()
    clean_automatic(controller)
    doc.removeObject(reference.Name)
    passed("automatic_real_hover_without_snap_and_empty_depth_unavailable")

    camera_type = view.getCameraType()
    for name, rotation in (("XY", App.Rotation()),
                           ("XZ", App.Rotation(App.Vector(1, 0, 0), 90)),
                           ("YZ", App.Rotation(App.Vector(0, 1, 0), 90)),
                           ("tilted", App.Rotation(App.Vector(1, 2, 3), 37))):
        for camera_type_test in ("Orthographic", "Perspective"):
            view.setCameraType(camera_type_test)
            view.setCameraOrientation(rotation.Q)
            QtTest.QTest.qWait(App.ParamGet("User parameter:BaseApp/Preferences/View").GetInt("AnimationDuration", 500) + 100)
            session, tool = opened("Polygon")
            session, panel = automatic(tool)
            controller = panel.controller
            frame = App.Placement(App.Vector(10, -20, 128), rotation)
            for point in ((0, 0, 0), (40, 0, 0), (40, 25, 0)):
                automatic_numeric(panel, tuple(frame.multVec(App.Vector(*point))))
            points_before = controller._world_points()
            callbacks = list(controller._callbacks)
            previous_candidate = None
            for position in (QtCore.QPoint(50, 50), QtCore.QPoint(85, 75)):
                move(position)
                assert Gui.Snapper.cursorMode == "passive"
                assert controller._last_pick_info is None
                assert controller.candidate is not None, (name, camera_type_test, panel.status.text())
                world = App.Vector(*controller.candidate.world)
                assert abs(controller.placement.inverse().multVec(world).z) < 1e-6
                screen = view.getPointOnScreen(world)
                assert abs(screen[0] - position.x()) <= 2
                assert abs(screen[1] - (viewer().height() - position.y())) <= 2
                shown = App.Vector(*(length_value(field.text()) for field in panel.coordinate_input.fields))
                assert (shown - world).Length <= .02
                preview_point = controller.preview._root.getChild(
                    controller.preview._root.getNumChildren() - 1).getChild(2).point[1].getValue()
                assert (App.Vector(*preview_point) - world).Length < .002
                if previous_candidate is not None:
                    assert (previous_candidate - world).Length > 1e-5
                previous_candidate = world
            assert controller._world_points() == points_before and controller._callbacks == callbacks
            # Same candidate in local absolute/relative and global relative.
            for global_axes, relative in ((False, False), (False, True), (True, True), (True, False)):
                panel.coordinate_input.global_coordinates.setChecked(global_axes)
                panel.coordinate_input.relative.setChecked(relative)
                move(QtCore.QPoint(90, 80))
                assert controller.candidate is not None and not panel.coordinate_input.editing
                assert panel.coordinate_input.fields[2].isReadOnly() == (not global_axes)
            if camera_type_test == "Orthographic":
                # Look parallel to the plane: no arbitrary or forced fallback.
                view.setCameraOrientation(rotation.multiply(App.Rotation(App.Vector(0, 1, 0), 90)).Q)
                QtTest.QTest.qWait(App.ParamGet("User parameter:BaseApp/Preferences/View").GetInt("AnimationDuration", 500) + 100)
                move(QtCore.QPoint(60, 60))
                assert controller.candidate is None, (name, Gui.Snapper.cursorMode,
                    tuple(view.getViewDirection()), controller.candidate,
                    controller._last_pick_info, controller._last_preselection_info)
            panel.reject()
            pump()
            clean_automatic(controller)
            passed("automatic_empty_ray_" + name + "_" + camera_type_test)
    view.setCameraType(camera_type)
    view.viewTop()

    session, tool = opened("Polygon")
    session, panel = automatic(tool)
    controller = panel.controller
    for point in ((0, 0, 128), (40, 0, 128), (40, 25, 128)):
        automatic_numeric(panel, point)
    panel.close_button.click()
    pump()
    assert controller.contour is not None and not controller._callbacks
    panel.undo_button.click()
    pump()
    assert controller.point_count == 2 and controller.plane_state == "FIRST_DIRECTION"
    assert controller.contour is None and controller._callbacks
    assert not panel.coordinate_input.global_coordinates.isEnabled()
    automatic_numeric(panel, (40, 25, 128))
    callback_tokens = list(controller._callbacks)
    panel.clear_button.click()
    pump()
    assert controller.point_count == 0 and controller.plane_state == "NO_PLANE"
    assert controller._callbacks == callback_tokens
    assert not panel.undo_button.isEnabled() and not panel.clear_button.isEnabled()
    assert not panel.close_button.isEnabled()
    assert not any(field.text() for field in panel.coordinate_input.fields)
    panel.reject()
    pump()
    clean_automatic(controller)
    passed("automatic_undo_closed_to_pending_plane_clear_reuses_callbacks")

    for shape in ("Rectangle", "Polygon"):
        session, tool = opened(shape)
        tool.options.thickness.setValue(6)
        tool.options.offset.setValue(2)
        tool.options.reverse.setChecked(True)
        points = ((0, 0, 0), (40, 25, 0)) if shape == "Rectangle" else ((0, 0, 0), (40, 0, 0), (0, 25, 0))
        for point in points:
            numeric(tool, point)
        if shape == "Polygon":
            tool.ui.closeButton.click()
            pump()
        created = validate_plate(doc)[0]
        assert created.ReverseExtrusion and created.Thickness.Value == 6 and created.Offset.Value == 2
        assert abs(created.Shape.BoundBox.ZMin + 4) < 1e-5 and abs(created.Shape.BoundBox.ZMax - 2) < 1e-5
        remove_plates(doc)
    passed("native_polygon_rectangle_reverse_extrusion_ui")

    session, tool = opened("Polygon")
    tool.options.reverse.setChecked(True)
    session, panel = automatic(tool)
    assert panel.reverse.isChecked()
    for point in ((0, 0, 128), (40, 0, 128), (40, 25, 128)):
        automatic_numeric(panel, point)
    panel.close_button.click()
    pump()
    assert panel.controller.preview._solid_signature[-1] is True
    panel.reverse.setChecked(False)
    pump()
    assert panel.controller.preview._solid_signature[-1] is False
    panel.reverse.setChecked(True)
    pump()
    assert panel.accept()
    pump()
    assert validate_plate(doc)[0].ReverseExtrusion
    remove_plates(doc)
    passed("automatic_reverse_state_survives_plane_switch_and_changes_solid_preview")

    keys = result["draft_shortcut_audit"]
    from freecad.SteelStructures.interactive.plate_panel_shortcuts import draft_shortcut_keys, point_shortcut_key
    point_key = point_shortcut_key(draft_shortcut_keys())
    result["plate_point_shortcut"] = point_key
    session, tool = opened("Polygon")
    assert not hasattr(tool, "select_face_button")
    native_shortcuts = tool._shortcuts
    for control, action in ((tool.ui.isRelative, "Relative"), (tool.ui.isGlobal, "Global"),
                            (tool.ui.continueCmd, "Continue")):
        before = control.isChecked()
        native_graphical_key(tool, keys[action])
        assert control.isChecked() != before, action
        native_graphical_key(tool, keys[action])
        assert control.isChecked() == before, action
    field = tool.ui.xValue
    # Direct keyboard numeric input still starts in Draft's automatic focus.
    move(QtCore.QPoint(140, 190))
    field = QtWidgets.QApplication.focusWidget()
    assert not tool._coordinate_focus.protects(field)
    QtTest.QTest.keyClicks(field, "12")
    pump()
    assert tool._coordinate_focus.protects(field) and "12" in field.text()
    field = tool.ui.xValue
    QtTest.QTest.mouseClick(field, QtCore.Qt.LeftButton)
    field.selectAll()
    before = tool.ui.isRelative.isChecked()
    QtTest.QTest.keyClicks(field, keys["Relative"])
    pump()
    assert tool.ui.isRelative.isChecked() == before and not tool.node
    for field, value in zip((tool.ui.xValue, tool.ui.yValue, tool.ui.zValue), (0, 0, 0)):
        field.setFocus()
        field.setText(str(value) + " mm")
    native_graphical_key(tool, point_key)
    assert len(tool.node) == 1, (tool.ui.pointButton.text(), tool.ui.pointButton.isVisible(),
                                 tool.ui.pointButton.isEnabled(),
                                 [(key, shortcut.isEnabled()) for shortcut, _, key in tool._shortcuts._bindings])
    numeric(tool, (40, 0, 0))
    native_graphical_key(tool, keys["Undo"])
    assert len(tool.node) == 1
    call = tool.call
    native_graphical_key(tool, keys["Wipe"])
    assert tool.node == [] and tool.call == call and tool.is_active()
    for point in ((0, 0, 0), (40, 0, 0), (0, 25, 0)):
        numeric(tool, point)
    native_graphical_key(tool, keys["Close"])
    assert validate_plate(doc)[0].Shape.isValid() and native_shortcuts._disposed
    remove_plates(doc)
    passed("native_shortcuts_single_execution_typing_guard_clear_all_and_dispose")

    session, tool = opened("Rectangle")
    assert tool.restart_button.isHidden()
    numeric(tool, (0, 0, 0))
    assert len(tool.node) == 1 and not tool.restart_button.isHidden()
    callback = tool.call
    tool.restart_button.click()
    pump()
    assert tool.node == [] and tool.restart_button.isHidden() and tool.call == callback
    session.finish()
    pump()
    passed("rectangle_restart_only_after_first_point_preserves_capture")

    session, tool = opened("Polygon")
    session, panel = automatic(tool)
    widget = panel.coordinate_input
    auto_shortcuts = panel._shortcuts
    from freecad.SteelStructures.interactive.point_input import PointCandidate
    assert not hasattr(panel, "select_face_button")
    assert not hasattr(panel, "extrusion_hint")
    controller = panel.controller
    widget.fields[0].setFocus()
    QtTest.QTest.keyClicks(widget.fields[0], keys["Relative"])
    assert widget.fields[0].text() == keys["Relative"] and controller.point_count == 0
    widget.clear()
    widget.fields[0].clearFocus()
    panel_key(point_key)  # Disabled: no candidate.
    assert controller.point_count == 0
    candidate = PointCandidate((-14.4817123456789, 0, 128))
    controller.set_candidate(candidate)
    panel_key(point_key)
    assert controller.point_count == 1 and controller.last_point == candidate.world
    automatic_numeric(panel, (40, 0, 128))
    automatic_numeric(panel, (40, 25, 128))
    for control, action in ((widget.relative, "Relative"), (widget.global_coordinates, "Global")):
        before = control.isChecked()
        panel_key(keys[action])
        assert control.isChecked() != before, action
        panel_key(keys[action])
        assert control.isChecked() == before, action
        assert not widget.editing and controller._callbacks
    panel_key(keys["Close"])
    assert controller.contour is not None and not widget.add_button.isEnabled()
    panel_key(keys["Undo"])
    assert controller.contour is None and controller.point_count == 2 and controller._callbacks
    callbacks = list(controller._callbacks)
    panel_key(keys["Wipe"])
    assert controller.point_count == 0 and controller._callbacks == callbacks
    assert widget.global_coordinates.isChecked() and not widget.global_coordinates.isEnabled()
    panel.reject()
    pump()
    assert auto_shortcuts._disposed
    clean_automatic(controller)
    passed("automatic_shortcuts_single_execution_full_precision_clear_all_and_dispose")

    # Face selection owns only a Selection observer between point engines.
    planar = doc.addObject("Part::Feature", "DuringCommandPlane")
    planar.Shape = Part.makeBox(40, 30, 8)
    planar.Placement = App.Placement(App.Vector(10, 20, 30), App.Rotation(App.Vector(0, 1, 0), 35))
    curved = doc.addObject("Part::Feature", "RejectedCurvedPlane")
    curved.Shape = Part.makeCylinder(10, 20)
    doc.recompute()
    for capture in ("native", "automatic"):
        session, tool = opened("Polygon")
        if capture == "automatic":
            session, panel = automatic(tool)
            previous = panel.controller
            automatic_numeric(panel, (0, 0, 128))
            panel.plane_mode.setCurrentIndex(panel.plane_mode.findData("Face"))
            pump()
            assert session.face_picker is None and previous.point_count == 1
            panel.restart_button.click()
            pump()
            panel = session.panel
            previous = panel.controller
            panel.plane_mode.setCurrentIndex(panel.plane_mode.findData("Face"))
        else:
            numeric(tool, (0, 0, 0))
            tool.plane_combo.setCurrentIndex(tool.plane_combo.findData("Face"))
            pump()
            assert session.face_picker is None and len(tool.node) == 1
            tool.restart_button.click()
            pump()
            tool.plane_combo.setCurrentIndex(tool.plane_combo.findData("Face"))
        pump()
        picker = session.face_picker
        assert picker is not None and picker._selection_observer
        assert session.tool is None and session.panel is None and App.activeDraftCommand is None
        if capture == "automatic":
            assert previous._teardown_done and not previous._callbacks
        Gui.Selection.addSelection(curved, "Face1")
        pump()
        assert session.face_picker is picker and "plana" in picker.status.text()
        Gui.Selection.clearSelection()
        Gui.Selection.addSelection(planar, "Face6")
        pump()
        assert picker._closed and not picker._selection_observer and not picker._document_observer
        assert session.face_picker is None and session.plane == "Face"
        tool = session.tool
        assert tool.is_active() and tool.options.status.text() == "Plano definido."
        assert tool.face_label.text() == planar.Label + " — Face6"
        assert tool.change_face_button.isVisibleTo(tool._base_widget)
        assert tool.node == []  # Face click belongs exclusively to selection.
        captured_frame = App.Placement(session._plane_placement)
        tool.change_face_button.click()
        pump()
        assert session.face_picker is not None and session.tool is None
        session.face_picker.reject()
        pump()
        tool = session.tool
        assert session.plane == "Face" and session._plane_placement == captured_frame
        assert tool.face_label.text() == planar.Label + " — Face6" and tool.node == []
        assert tool.placement == session._plane_placement
        tool.ui.continueCmd.setChecked(False)
        for point in ((0, 0, 0), (20, 0, 0), (0, 15, 0)):
            numeric(tool, point)
        tool.ui.closeButton.click()
        pump()
        assert plates(doc)[0].SourceObject is None and not plates(doc)[0].KeepSourceLink
        assert wp_state(wp) == initial
        remove_plates(doc)
    for _index in range(3):
        session, tool = opened()
        tool.plane_combo.setCurrentIndex(tool.plane_combo.findData("Face"))
        pump()
        picker = session.face_picker
        if _index == 0:
            escape()
        else:
            picker.reject()
        pump()
        assert picker._closed and not picker._selection_observer
        assert commands._active_plate_session is session and session.tool.is_active()
        assert session.plane == "WorkPlane"
        session.finish()
        pump()
        assert commands._active_plate_session is None and not Gui.Control.activeDialog()
        assert wp_state(wp) == initial
    doc.removeObject(planar.Name)
    doc.removeObject(curved.Name)
    passed("select_face_during_native_auto_reject_curved_accept_planar_restart_cancel")

    session, tool = opened("Polygon")
    numeric(tool, (0, 0, 0))
    tool.plane_combo.setCurrentIndex(tool.plane_combo.findData("Auto"))
    pump()
    assert session.tool is tool and tool.plane_combo.currentData() == "WorkPlane" and len(tool.node) == 1
    tool.restart_button.click()
    pump()
    session, panel = automatic(tool)
    panel.controller.add_point(App.Vector(1, 2, 3))
    panel.plane_mode.setCurrentIndex(panel.plane_mode.findData("WorkPlane"))
    pump()
    assert session.panel is panel and panel.controller.point_count == 1 and panel.plane_mode.currentData() == "Auto"
    panel.mode.setCurrentIndex(panel.mode.findData("InteractiveRectangle"))
    pump()
    assert session.shape == "Polygon" and panel.mode.currentData() == "InteractivePolygon"
    panel.restart_button.click()
    pump()
    assert session.panel is panel and not session.panel.controller.point_count
    assert not panel.controller._teardown_done and panel.controller._callbacks
    previous = session.panel.controller
    session.panel.plane_mode.setCurrentIndex(session.panel.plane_mode.findData("WorkPlane"))
    pump()
    assert session.panel is None and session.tool.is_active()
    assert previous._teardown_done and not previous._callbacks
    session.finish()
    pump()
    passed("automatic_switch_blocked_restart_and_return_preserve_exclusive_capture")

    session, tool = opened("Polygon")
    session, panel = automatic(tool)
    previous = panel.controller
    panel.mode.setCurrentIndex(panel.mode.findData("InteractiveRectangle"))
    pump()
    assert previous._teardown_done and not previous._callbacks
    assert session.panel is None and session.shape == "Rectangle" and session.plane == "WorkPlane"
    assert type(session.tool.rect) is PlateRectangleTracker
    session.finish()
    pump()
    passed("automatic_shape_switch_to_common_rectangle_2p")

    for index in range(CYCLES):
        session, tool = opened("Polygon")
        session, panel = automatic(tool)
        previous = panel.controller
        if index % 2:
            automatic_numeric(panel, (1, 2, 128))
        escape()
        clean_automatic(previous)
        assert not doc.Objects
    passed("automatic_cancel_reopen_no_callback_preview_wp_residue")

    import Draft
    for shape in ("Rectangle", "Wire"):
        source = (Draft.make_rectangle(40, 25) if shape == "Rectangle" else
                  Draft.make_wire([App.Vector(0, 0, 0), App.Vector(40, 0, 0), App.Vector(0, 25, 0)], closed=True))
        doc.recompute()
        Gui.Selection.clearSelection()
        Gui.Selection.addSelection(source)
        Gui.runCommand("SteelStructures_CreatePlate")
        pump()
        panel = commands._active_plate_panel
        assert panel is not None and commands._active_plate_session is None
        assert not panel.controller._callbacks and panel.coordinate_input is None
        panel.link.setChecked(True)
        panel.reverse.setChecked(True)
        assert panel.accept()
        pump()
        plate = plates(doc)[0]
        assert plate.SourceObject is source and plate.KeepSourceLink
        assert plate.ReverseExtrusion
        assert str(plate.SourceMode) == "Draft" + shape
        assert plate.Shape.isValid() and not Gui.Control.activeDialog()
        remove_plates(doc)
        doc.removeObject(source.Name)
    passed("preselected_draft_rectangle_wire_optional_links_preserved")

    for shape in ("Polygon", "Rectangle"):
        session, tool = opened(shape)
        task_box = tool._base_widget
        while task_box is not None and not task_box.inherits("Gui::TaskView::TaskBox"):
            task_box = task_box.parentWidget()
        task_box.grab().save(str(RUN / (shape.lower() + "_input.png")))
        Gui.getMainWindow().grab().save(str(RUN / (shape.lower() + "_window.png")))
        tool.finish()
        pump()
    passed("task_panel_screenshots")

    for index in range(CYCLES):
        session, tool = opened("Polygon" if index % 2 else "Rectangle")
        if index % 3:
            numeric(tool, (0, 0, 0))
        escape()
        assert not doc.Objects and commands._active_plate_session is None
        assert wp_state(wp) == initial
    passed("repeated_cancel_reopen_and_wp_restore")

    session, tool = opened()
    class ForeignPanel:
        def __init__(self):
            self.form = QtWidgets.QWidget()
        def getStandardButtons(self):
            return int(QtWidgets.QDialogButtonBox.Cancel.value)
        def reject(self):
            Gui.Control.closeDialog()
            return True
    tool.finish()
    Gui.Control.closeDialog()
    foreign = ForeignPanel()
    Gui.Control.showDialog(foreign)
    pump()
    assert Gui.Control.activeDialog()
    Gui.Control.closeDialog()
    passed("foreign_panel_survives_old_teardown")

    for advanced in (False, True):
        session, tool = opened("Polygon")
        if advanced:
            session, _panel = automatic(tool)
            previous = session.panel.controller
            close_callback = session.panel.on_close
            def traced_close(*args):
                log("advanced_close_callback_enter")
                try:
                    close_callback(*args)
                except BaseException:
                    log("advanced_close_callback_error", error=traceback.format_exc())
                    raise
                log("advanced_close_callback_leave")
            session.panel.on_close = traced_close
        Gui.runCommand("Draft_Line")
        pump()
        result["replacement_debug"] = dict(advanced=advanced, old_state=tool._state,
                session_closed=session._closed, has_panel=session.panel is not None,
                new_command=type(App.activeDraftCommand).__name__,
                attached=tool._panel_is_attached(), old_active=tool.is_active())
        if session.panel is not None:
            from shiboken6 import isValid
            result["replacement_debug"].update(panel_closed=session.panel._closed,
                    panel_closing=session.panel._closing, form_valid=isValid(session.panel.input_form),
                    controller_closed=previous.closed, callbacks=len(previous._callbacks),
                    teardown=previous._teardown_done, on_close=str(session.panel.on_close))
        save()
        assert commands._active_plate_session is None
        replacement = App.activeDraftCommand
        assert replacement is not None and replacement is not tool
        assert Gui.Control.activeDialog() and replacement.ui.sourceCmd is replacement
        move()
        assert replacement.point is not None
        if advanced:
            assert previous.closed and previous._teardown_done and not previous._callbacks
        replacement.finish()
        pump()
        assert not doc.Objects and not Gui.Control.activeDialog()
    passed("replacement_draft_line_native_and_advanced")

    session, tool = opened()
    tool.advanced_button.click()
    pump()
    previous = session.panel.controller
    Gui.Control.closeDialog()
    foreign = ForeignPanel()
    Gui.Control.showDialog(foreign)
    pump()
    assert Gui.Control.activeDialog() and previous._teardown_done and not previous._callbacks
    assert commands._active_plate_session is None
    Gui.Control.closeDialog()
    passed("advanced_destroyed_panel_foreign_ownership")

    session, tool = opened("Polygon")
    session, _panel = automatic(tool)
    previous = session.panel.controller
    Gui.runCommand("Std_ViewCreate")
    pump()
    assert commands._active_plate_session is None
    assert previous._teardown_done and not previous._callbacks and not Gui.Control.activeDialog()
    passed("advanced_view_switch_releases_capture")

    original_document_name = doc.Name
    extra = App.newDocument("AdvancedDocumentClose")
    Gui.runCommand("SteelStructures_CreatePlate")
    pump()
    session = commands._active_plate_session
    session.tool.advanced_button.click()
    pump()
    previous = session.panel.controller
    App.closeDocument(extra.Name)
    pump()
    assert commands._active_plate_session is None
    assert previous._teardown_done and not previous._callbacks and not Gui.Control.activeDialog()
    App.setActiveDocument(original_document_name)
    pump()
    passed("advanced_document_close_does_not_access_dead_scene")

    session, tool = opened()
    numeric(tool, (0, 0, 0))
    Gui.runCommand("Std_ViewCreate")
    pump()
    assert tool._state == "FINISHED" and App.activeDraftCommand is None
    assert not Gui.Control.activeDialog()
    passed("view_switch_cancels_owner_safely")

    session, tool = opened()
    numeric(tool, (0, 0, 0))
    App.closeDocument(doc.Name)
    pump()
    assert tool._state == "FINISHED" and not Gui.Control.activeDialog()
    assert commands._active_plate_session is None
    passed("document_close_cancels_owner_safely")


def geometry_gate(doc, wp):
    import unittest
    sys.path.insert(0, str(ROOT / "freecad"))
    suite = unittest.defaultTestLoader.loadTestsFromName("tests.test_plate_native")
    with (RUN / "native_unittest.txt").open("w", encoding="utf-8") as stream:
        outcome = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
    result["native_unittest"] = dict(tests=outcome.testsRun, skipped=len(outcome.skipped),
                                      failures=len(outcome.failures), errors=len(outcome.errors))
    assert outcome.wasSuccessful() and outcome.testsRun == 15 and not outcome.skipped
    passed("fifteen_native_plate_geometry_reverse_persistence_links_undo_redo")
    suite = unittest.defaultTestLoader.loadTestsFromName("tests.test_coordinate_input_widget")
    with (RUN / "numeric_unittest.txt").open("w", encoding="utf-8") as stream:
        outcome = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
    result["numeric_unittest"] = dict(tests=outcome.testsRun, skipped=len(outcome.skipped),
                                    failures=len(outcome.failures), errors=len(outcome.errors))
    assert outcome.wasSuccessful() and outcome.testsRun == 30 and not outcome.skipped
    passed("thirty_native_numeric_candidate_focus_xyz_section_ray_tests")


def qt_inputfield_gate(doc, wp):
    """Separate a Draft-only control from the native metric-sample hypothesis."""
    from shiboken6 import isValid, getCppPointer
    assert not any(name.startswith("freecad.SteelStructures") for name in sys.modules)
    result["steelstructures_imported"] = False
    for index in range(CYCLES):
        if STAGE == "qt_sample":
            parent = QtWidgets.QWidget()
            sample = Gui.UiLoader().createWidget("Gui::InputField")
            assert isValid(sample), "UiLoader returned an invalid metric sample"
            sample.setParent(parent)
            sample.hide()
            log("sample_created", cycle=index, pointer=getCppPointer(sample)[0])
            sample.destroyed.connect(lambda *_args, cycle=index: log("sample_destroyed", cycle=cycle))
            sample.deleteLater()
            pump()
            parent.deleteLater()
            del sample, parent
            pump()
        log("before_pure_draft_line", cycle=index)
        Gui.runCommand("Draft_Line")
        pump()
        tool = App.activeDraftCommand
        assert tool is not None and Gui.Control.activeDialog(), "Draft Line failed to create its panel"
        for name in ("xValue", "yValue", "zValue"):
            field = getattr(tool.ui, name)
            assert isValid(field)
            log("draft_inputfield_created", cycle=index, name=name, pointer=getCppPointer(field)[0])
            field.destroyed.connect(lambda *_args, cycle=index, name=name:
                                    log("draft_inputfield_destroyed", cycle=cycle, name=name))
        tool.finish()
        pump()
        assert App.activeDraftCommand is None and not Gui.Control.activeDialog()
        passed(STAGE + "_%02d" % index)
    assert not any(name.startswith("freecad.SteelStructures") for name in sys.modules)


def regression_gate(doc, wp):
    """Proportional smoke of shared Draft UI and adjacent public commands."""
    from freecad.SteelStructures import commands
    from freecad.SteelStructures.member import create_member
    from freecad.SteelStructures.plate import create_plate
    from freecad.SteelStructures.plate_geometry import PlateContour2D
    initial = wp_state(wp)
    for _ in range(3):
        Gui.runCommand("Draft_Wire")
        pump()
        assert App.activeDraftCommand is not None and Gui.Control.activeDialog()
        App.activeDraftCommand.finish()
        pump()
        assert App.activeDraftCommand is None and not Gui.Control.activeDialog()
    passed("standalone_draft_polyline_three_open_cancel_inputfield_cycles")

    def cancel_plate(automatic=False, first_point=False):
        Gui.runCommand("SteelStructures_CreatePlate")
        pump()
        session = commands._active_plate_session
        assert session is not None and session.tool is not None
        if automatic:
            combo = session.tool.shape_combo
            combo.setCurrentIndex(combo.findData("Polygon"))
            pump()
            combo = session.tool.plane_combo
            combo.setCurrentIndex(combo.findData("Auto"))
            pump()
            assert session.panel is not None and session.panel.controller._callbacks
        elif first_point:
            numeric(session.tool, (0, 0, 0), global_axes=True)
            assert len(session.tool.node) == 1
        commands.close_plate_panel()
        pump()
        assert commands._active_plate_session is None and not Gui.Control.activeDialog()
        assert App.activeDraftCommand is None and not doc.Objects
        assert wp_state(wp) == initial

    for command in ("SteelStructures_CreateMember", "SteelStructures_CreateColumn"):
        cancel_plate(automatic=command == "SteelStructures_CreateColumn")
        Gui.runCommand(command)
        pump()
        tool = commands._active_member_tool
        assert tool is not None and tool.is_active() and Gui.Control.activeDialog()
        commands.close_member_tool()
        pump()
        assert commands._active_member_tool is None
        assert App.activeDraftCommand is None and not Gui.Control.activeDialog()
        assert not doc.Objects and wp_state(wp) == initial
        passed(command + "_open_cancel_after_plate")
    cancel_plate(first_point=True)
    Gui.runCommand("SteelStructures_CreateGrid")
    pump()
    assert commands._active_grid_panel is not None and doc.Objects
    commands.close_grid_panel()
    pump()
    assert commands._active_grid_panel is None and not doc.Objects
    assert not Gui.Control.activeDialog()
    passed("grid_public_command_cancel_transaction")
    doc.UndoMode = 1
    doc.openTransaction("Shared member and plate persistence smoke")
    member = create_member(doc, App.Vector(0, 0, 0), App.Vector(400, 100, 1200),
                           "W 150 x 13,0")
    column = create_member(doc, App.Vector(1000, 0, 0), App.Vector(1000, 0, 1800),
                           "W 150 x 13,0", element_type="Pilar")
    contour = PlateContour2D.from_points([(0, 0), (80, 0), (80, 40), (0, 40)], closed=True)
    plate = create_plate(doc, contour, thickness=8, offset=-2)
    plate.ReverseExtrusion = True
    doc.recompute()
    for obj in (member, column, plate):
        assert not obj.Shape.isNull() and obj.Shape.isValid() and obj.Shape.Volume > 0
    names = [obj.Name for obj in (member, column, plate)]
    volumes = [obj.Shape.Volume for obj in (member, column, plate)]
    doc.commitTransaction()
    doc.undo()
    assert not doc.Objects
    doc.redo()
    doc.recompute()
    assert len(doc.Objects) == 3
    path = RUN / "shared_plate_member.FCStd"
    doc.saveAs(str(path))
    App.closeDocument(doc.Name)
    restored = App.openDocument(str(path))
    try:
        restored.recompute()
        for name, volume in zip(names, volumes):
            obj = restored.getObject(name)
            assert obj is not None and obj.Shape.isValid()
            assert abs(obj.Shape.Volume - volume) < 1e-5
        assert restored.getObject(names[-1]).ReverseExtrusion
        assert not Gui.Control.activeDialog() and App.activeDraftCommand is None
        passed("member_column_plate_occ_recompute_undo_redo_save_reopen")
    finally:
        App.closeDocument(restored.Name)
    sys.path.insert(0, str(ROOT / "freecad"))
    from tests.manual_grid_placement_persistence import run as grid_persistence
    grid_persistence()
    passed("grid_existing_placement_save_reopen_probe")


def run():
    doc = None
    try:
        assert Path(App.getUserAppDataDir()).resolve() == (RUN / "home").resolve()
        assert not any(name.startswith("freecad.SteelStructures") for name in sys.modules)
        sys.path.insert(0, str(ROOT))
        import freecad
        freecad.__path__.insert(0, str(ROOT / "freecad"))
        if STAGE in ("integrated", "regression"):
            import freecad.SteelStructures.init_gui
            Gui.activateWorkbench("SteelStructuresWorkbench")
        else:
            Gui.activateWorkbench("DraftWorkbench")
        pump()
        import WorkingPlane
        doc = App.newDocument("PlateUnifiedNativeGate")
        Gui.activeDocument().activeView().viewTop()
        pump()
        wp = WorkingPlane.get_working_plane(update=False)
        log("document_created", name=doc.Name)
        document_name = doc.Name
        {"tracker": tracker_gate, "integrated": integrated_gate, "geometry": geometry_gate,
         "regression": regression_gate, "qt_native": qt_inputfield_gate,
         "qt_sample": qt_inputfield_gate}[STAGE](doc, wp)
        if document_name in App.listDocuments():
            App.closeDocument(document_name)
        pump()
        result["ok"] = True
        log("completed")
    except Exception:
        result["error"] = traceback.format_exc()
        log("python_error", traceback=result["error"])
        App.Console.PrintError(result["error"])
    finally:
        command = getattr(App, "activeDraftCommand", None)
        if command is not None:
            command.finish()
            pump()
        for name in tuple(App.listDocuments()):
            App.closeDocument(name)
        pump()
        save()
        log("before_application_quit", ok=result["ok"])
        QtCore.QTimer.singleShot(0, QtWidgets.QApplication.quit)


save()
QtCore.QTimer.singleShot(800, run)
