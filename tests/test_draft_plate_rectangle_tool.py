"""Adapter contracts under controlled Draft/Qt modules, without FreeCAD.

The native GUI probe covers Draft's coordinate conversion, snapping and Coin.
These tests exercise the plate adapter's geometry, ownership and transactions.
"""

import copy
import importlib.util
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch


PACKAGE = Path(__file__).resolve().parents[1] / "freecad" / "SteelStructures"


class Vector:
    def __init__(self, x=0, y=None, z=None):
        if y is None:
            x, y, z = tuple(x) if not isinstance(x, (int, float)) else (x, 0, 0)
        self.x, self.y, self.z = float(x), float(y), float(z)

    def __iter__(self):
        return iter((self.x, self.y, self.z))

    def __eq__(self, other):
        return isinstance(other, Vector) and tuple(self) == tuple(other)


class Frame:
    """Rigid frame with an origin and orthonormal axis vectors."""

    def __init__(self, base=(0, 0, 0), rotation=None, inverse=False):
        self.Base = Vector(base)
        self.Rotation = rotation or ((1, 0, 0), (0, 1, 0), (0, 0, 1))
        self.inverted = inverse

    def inverse(self):
        return Frame(self.Base, self.Rotation, not self.inverted)

    def multVec(self, point):
        point = tuple(point)
        base = tuple(self.Base)
        if self.inverted:
            delta = [point[index] - base[index] for index in range(3)]
            return Vector(tuple(sum(a * b for a, b in zip(delta, axis))
                                for axis in self.Rotation))
        return Vector(tuple(base[index] + sum(point[j] * self.Rotation[j][index]
                                              for j in range(3))
                            for index in range(3)))


class Signal:
    def __init__(self):
        self.slots = []

    def connect(self, slot):
        self.slots.append(slot)

    def disconnect(self, slot):
        self.slots.remove(slot)

    def emit(self, *args):
        for slot in list(self.slots):
            slot(*args)


class Widget:
    def __init__(self, *args):
        self.text = args[0] if args else ""
        self.destroyed = Signal()
        self.valueChanged = Signal()
        self.toggled = Signal()
        self.hidden = False
        self.number = 0
        self.checked = False
        self.valid = True
        self.tooltip = ""
        self.enabled = True
        self.parent = None
        self.qt_class = "QWidget"

    def parentWidget(self):
        return self.parent

    def inherits(self, name):
        return self.qt_class == name

    def layout(self):
        return self._layout

    def isVisibleTo(self, parent):
        return not self.hidden

    def setText(self, text):
        self.text = text

    def setToolTip(self, text):
        self.tooltip = text

    def setEnabled(self, enabled):
        self.enabled = bool(enabled)

    def hide(self):
        self.hidden = True

    def setValue(self, value):
        changed = self.number != value
        self.number = value
        if changed:
            self.valueChanged.emit(value)

    def value(self):
        return self.number

    def isChecked(self):
        return self.checked

    def setChecked(self, checked):
        changed = self.checked != bool(checked)
        self.checked = bool(checked)
        if changed:
            self.toggled.emit(self.checked)

    def __getattr__(self, name):
        if name.startswith("set") or name == "addRow":
            return lambda *args: None
        raise AttributeError(name)


class Plane:
    def __init__(self, frame=None):
        self.frame = frame or Frame()
        self.parameters = {
            "u": Vector(self.frame.Rotation[0]),
            "v": Vector(self.frame.Rotation[1]),
            "axis": Vector(self.frame.Rotation[2]),
            "position": Vector(self.frame.Base), "auto": True,
            "icon": "user-plane", "label": "User plane", "tip": "Saved tip",
        }
        self._stored = {"prior": "native snapshot"}
        self.updates = []
        self.alignments = []

    def get_parameters(self):
        return copy.deepcopy(self.parameters)

    def set_parameters(self, parameters):
        self.parameters = copy.deepcopy(parameters)
        self.frame = Frame(parameters["position"], (
            tuple(parameters["u"]), tuple(parameters["v"]), tuple(parameters["axis"])))

    def get_placement(self):
        return self.frame

    def align_to_placement(self, frame, _hist_add=True):
        self.frame = frame
        self.alignments.append(_hist_add)
        self.parameters.update(u=Vector(frame.Rotation[0]), v=Vector(frame.Rotation[1]),
                               axis=Vector(frame.Rotation[2]), position=Vector(frame.Base),
                               auto=False, icon="temporary", label="Temporary", tip="Temporary")

    def _save(self):
        self._stored = self.get_parameters()

    def _update_all(self, _hist_add=True):
        self.updates.append(_hist_add)


class Document:
    Name = "PlateDocument"

    def __init__(self):
        self.Objects = []
        self.transactions = []
        self.commits = self.aborts = 0

    def openTransaction(self, name):
        self.transactions.append(name)
        self._before_transaction = list(self.Objects)

    def commitTransaction(self):
        self.commits += 1

    def abortTransaction(self):
        self.aborts += 1
        self.Objects[:] = self._before_transaction


class View:
    def __init__(self):
        self.callbacks = {}
        self.removed = []

    def addEventCallback(self, event, callback):
        token = len(self.callbacks) + 1
        self.callbacks[token] = callback
        return token

    def removeEventCallback(self, event, token):
        self.removed.append(token)
        del self.callbacks[token]

    def getSceneGraph(self):
        return self


class Tracker:
    def __init__(self, plane):
        self.frame_at_creation = copy.deepcopy(plane.get_parameters())
        self.off_calls = self.finalize_calls = 0
        self.points = []
        self.coords = types.SimpleNamespace(point=types.SimpleNamespace(getNum=lambda: 5))

    def update(self, point):
        self.points.append(point)

    def setorigin(self, point):
        self.origin = point

    def on(self):
        pass

    def off(self):
        self.off_calls += 1

    def finalize(self):
        self.finalize_calls += 1


class DraftPlateRectangleTests(unittest.TestCase):
    def setUp(self):
        self.namespace = "_draft_plate_rectangle_test"
        self.timers = []
        self.created = []
        self.errors = []
        self.shown = []
        self.closed = []
        self.observers = []
        self.document = Document()
        self.view = View()
        self.active_view = self.view
        self.owner_views = [self.view]
        self.plane = Plane()
        self.active_plane = self.plane
        self.initial_parameters = self.plane.get_parameters()
        self.initial_stored = dict(self.plane._stored)
        self.face_frame = Frame((10, 20, 30), ((0, 1, 0), (0, 0, 1), (1, 0, 0)))
        self.face_calls = []
        self.trackers = []
        self.original_creations = 0
        self.native_actions = []
        self.native_numeric = []
        self.native_finishes = 0
        self.app = types.ModuleType("FreeCAD")
        self.app.Vector, self.app.Placement = Vector, Frame
        self.app.ActiveDocument = self.document
        self.app.activeDraftCommand = None
        self.documents = {self.document.Name: self.document}
        self.app.listDocuments = lambda: self.documents
        self.app.Console = types.SimpleNamespace(PrintError=self.errors.append)
        self.app.addDocumentObserver = self.observers.append
        self.app.removeDocumentObserver = self.observers.remove
        self.gui = types.ModuleType("FreeCADGui")
        self.gui.Selection = types.SimpleNamespace(clearSelection=lambda: None,
                                                    addSelection=lambda obj: None)
        self.gui.Control = types.SimpleNamespace(closeDialog=lambda: self.closed.append(True))
        self.gui.Snapper = types.SimpleNamespace(mask=None, off=lambda: None)
        self.gui.getDocument = lambda name: types.SimpleNamespace(
            mdiViewsOfType=lambda kind: self.owner_views)
        self.gui.getMainWindow = lambda: types.SimpleNamespace(findChild=lambda kind: None)
        self.wp = types.ModuleType("WorkingPlane")
        self.wp.get_working_plane = lambda update=True: self.active_plane
        self.todo = types.ModuleType("draftutils.todo")
        self.todo.ToDo = types.SimpleNamespace(itinerary=[])
        self.ui = self._make_ui()
        self.gui.draftToolBar = self.ui
        self.native_rectangle = self._make_rectangle()
        modules = self._make_modules()
        self.module_patch = patch.dict(sys.modules, modules)
        self.module_patch.start()
        self.addCleanup(self.module_patch.stop)
        self.geometry = self._load("plate_geometry", PACKAGE / "plate_geometry.py")
        self.module = self._load("interactive.draft_plate_rectangle_tool",
                                 PACKAGE / "interactive" / "draft_plate_rectangle_tool.py")

    def _load(self, name, path):
        fullname = self.namespace + "." + name
        spec = importlib.util.spec_from_file_location(fullname, path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[fullname] = module
        self.addCleanup(sys.modules.pop, fullname, None)
        spec.loader.exec_module(module)
        return module

    def _make_ui(self):
        ui = types.SimpleNamespace(
            panel=None, sourceCmd=None, continueMode=False, relative=False, global_axes=False,
            pointButton=Widget(), isRelative=Widget(), isGlobal=Widget(),
            labelx=Widget(), labely=Widget(), labelz=Widget(),
            makeFace=Widget(), continueCmd=Widget(), angleLock=Widget(), relative_calls=[])

        def point_ui(**kwargs):
            ui.title = kwargs["title"]
            ui.extra = kwargs["extra"]
            ui.baseWidget = Widget()
            task_box, task_panel = Widget(), Widget()
            task_box.qt_class = "Gui::TaskView::TaskBox"
            task_panel.qt_class = "Gui::TaskView::TaskPanel"
            task_box.parent = task_panel
            task_panel.items = [task_box]
            task_panel._layout = types.SimpleNamespace(
                indexOf=lambda widget: 0 if widget in task_panel.items else -1)
            ui.baseWidget.parent = task_box
            ui.panel = types.SimpleNamespace()
            self.todo.ToDo.itinerary.append((ui._show_dialog, ui.panel))

        def set_relative(value=None):
            ui.relative_calls.append(value)
            ui.relative = value != -2

        ui.pointUi = point_ui
        ui.extUi = lambda: None
        ui.checkSpecialChars = lambda text: None
        for name in ("xValue", "yValue", "zValue", "lengthValue", "radiusValue", "angleValue"):
            field = types.SimpleNamespace(textEdited=Signal())
            field.textEdited.connect(ui.checkSpecialChars)
            setattr(ui, name, field)
        ui._show_dialog = self.shown.append
        ui.setRelative = set_relative
        ui.reset_ui_values = lambda: None
        ui.offUi = lambda: self.todo.ToDo.itinerary.append((self.gui.Control.closeDialog, None))
        return ui

    def _make_rectangle(self):
        harness = self

        class Creator:
            def __init__(self):
                self.commitList = []

            def Activated(self, name):
                harness.app.activeDraftCommand = self
                self.node, self.pos = [], []
                self.point = self.constrain = self.support = None
                self.ui = harness.ui
                self.ui.sourceCmd = self
                self.ui.mouse = True
                self.planetrack = None
                self.wp = harness.active_plane
                self.wp._save()

            def finish(self):
                harness.native_finishes += 1
                self.node = []
                harness.app.activeDraftCommand = None
                self.ui.offUi()
                self.ui.sourceCmd = None
                self.wp._restore()

        class Rectangle(Creator):
            # Only the native adapter protocol is modeled here. Actual Draft
            # coordinate conversion and scene callbacks are covered natively.
            def action(self, arg):
                harness.native_actions.append(arg)
                if arg.get("Key") == "ESCAPE":
                    self.finish()
                elif "point" in arg:
                    self.appendPoint(arg["point"])

            def numericInput(self, x, y, z):
                harness.native_numeric.append((x, y, z))
                self.point = Vector(x, y, z)
                self.appendPoint(self.point)

            def appendPoint(self, point):
                self.node.append(point)
                if len(self.node) == 2:
                    self.rect.update(point)
                    self.createObject()
                else:
                    self.ui.setRelative()
                    self.rect.setorigin(point)
                    self.rect.on()
                    self.update_hints()

            def createObject(self):
                harness.original_creations += 1
                raise AssertionError("A Draft Rectangle must never be created")

            def update_hints(self):
                pass

        self.creator = Creator
        return Rectangle

    def _make_modules(self):
        modules = {}
        for name in (self.namespace, self.namespace + ".interactive", "draftguitools", "draftutils"):
            modules[name] = types.ModuleType(name)
            modules[name].__path__ = []
        modules[self.namespace].__path__ = [str(PACKAGE)]
        modules[self.namespace + ".interactive"].__path__ = [str(PACKAGE / "interactive")]
        paths = types.ModuleType(self.namespace + ".paths")
        paths.PLATE_ICON = "plate.svg"
        plate = types.ModuleType(self.namespace + ".plate")
        plate.create_plate = self._factory
        planes = types.ModuleType(self.namespace + ".plate_planes")

        def from_face(face):
            self.face_calls.append(face)
            return self.face_frame

        planes.placement_from_face = from_face
        qt = types.ModuleType("PySide")
        qt.QtCore = types.SimpleNamespace(QObject=object, QEvent=types.SimpleNamespace(Close=19),
                                         QTimer=types.SimpleNamespace(singleShot=lambda delay, callback:
                                                                     self.timers.append(callback)))
        qt.QtGui = types.SimpleNamespace(QIcon=lambda value: value)
        qt.QtWidgets = types.SimpleNamespace(QWidget=Widget, QGroupBox=Widget, QFormLayout=Widget,
                                            QLabel=Widget, QDoubleSpinBox=Widget, QCheckBox=Widget,
                                            QMdiArea=object,
                                            QApplication=types.SimpleNamespace(focusWidget=lambda: None))
        base = types.ModuleType("draftguitools.gui_base_original")
        base.Creator = self.creator
        rectangles = types.ModuleType("draftguitools.gui_rectangles")
        rectangles.Rectangle = self.native_rectangle
        trackers = types.ModuleType("draftguitools.gui_trackers")

        def tracker():
            result = Tracker(self.active_plane)
            self.trackers.append(result)
            return result

        trackers.rectangleTracker = tracker
        plate_tracker = types.ModuleType(self.namespace + ".interactive.plate_rectangle_tracker")
        plate_tracker.PlateRectangleTracker = tracker
        shortcuts = types.ModuleType(self.namespace + ".interactive.plate_panel_shortcuts")
        class Shortcuts:
            def __init__(self, *_args):
                self.bindings = []
                self.disposed = False
            def bind(self, control, key, callback=None, label=None):
                self.bindings.append((control, key))
                if not hasattr(self, "callbacks"):
                    self.callbacks = {}
                self.callbacks[key] = callback
                if label:
                    control.setText("%s (%s)" % (label, key))
            def dispose(self):
                self.disposed = True
        shortcuts.PanelShortcuts = Shortcuts
        class CoordinateFocus:
            def __init__(self, fields, changed, keys):
                self.editing = False
                self.disposed = False
            def protects(self, widget):
                return self.editing
            def set_editing(self, editing):
                self.editing = editing
            def dispose(self):
                self.disposed = True
        shortcuts.DraftCoordinateFocus = CoordinateFocus
        shortcuts.draft_shortcut_keys = lambda: dict(Relative="R", Global="G", Continue="T", Undo="I", Close="O", Wipe="W", RestrictX="X", RestrictY="Y", RestrictZ="Z", Length="L")
        shortcuts.point_shortcut_key = lambda keys: next((key for key in ("P", "V") if key not in keys.values()), "")
        shortcuts.editable_focus = lambda focus: False
        gui_utils = types.ModuleType("draftutils.gui_utils")
        gui_utils.get_3d_view = lambda: self.active_view
        shiboken = types.ModuleType("shiboken6")
        shiboken.isValid = lambda widget: widget.valid
        modules.update({
            "FreeCAD": self.app, "FreeCADGui": self.gui, "WorkingPlane": self.wp, "PySide": qt,
            "shiboken6": shiboken,
            self.namespace + ".paths": paths, self.namespace + ".plate": plate,
            self.namespace + ".plate_planes": planes,
            "draftguitools.gui_base_original": base, "draftguitools.gui_rectangles": rectangles,
            "draftguitools.gui_trackers": trackers, "draftutils.gui_utils": gui_utils,
            self.namespace + ".interactive.plate_rectangle_tracker": plate_tracker,
            self.namespace + ".interactive.plate_panel_shortcuts": shortcuts,
            "draftutils.todo": self.todo,
        })
        return modules

    def _factory(self, document, contour, **kwargs):
        plate = types.SimpleNamespace(TypeId="Part::FeaturePython", Name="StructuralPlate",
                                      ContourData=contour.to_data(), SourceObject=None, **kwargs)
        document.Objects.append(plate)
        self.created.append(plate)
        return plate

    def activate(self, face=None, factory=None, on_closed=None, plane_placement=None):
        tool = self.module.StructuralPlateRectangleTool(factory=factory, on_closed=on_closed)
        tool.Activated(plane_face=face, plane_placement=plane_placement)
        return tool

    def flush(self):
        while self.timers:
            self.timers.pop(0)()

    def assert_restored(self):
        self.assertEqual(self.plane.get_parameters(), self.initial_parameters)
        self.assertEqual(self.plane._stored, self.initial_stored)

    def test_inherits_rectangle_and_point_ui_precedes_plate_options(self):
        self.assertTrue(issubclass(self.module.StructuralPlateRectangleTool, self.native_rectangle))
        tool = self.activate()
        self.assertIs(self.ui.extra, tool.options)
        self.assertEqual(self.ui.pointButton.text, "Adicionar ponto (P)")
        self.assertTrue(self.ui.makeFace.hidden)

    def test_global_points_create_only_structural_plate_with_unchanged_schema(self):
        self.plane = Plane(self.face_frame)
        self.active_plane = self.plane
        tool = self.activate()
        tool.options.thickness.setValue(12.5)
        tool.options.offset.setValue(-3.0)
        tool.numericInput(*self.face_frame.multVec((2, 3, 0)))
        self.assertTrue(self.ui.relative)
        tool.numericInput(*self.face_frame.multVec((7, 11, 0)))
        self.flush()
        self.assertEqual(self.original_creations, 0)
        self.assertEqual(len(self.document.Objects), 1)
        plate = self.document.Objects[0]
        self.assertEqual(plate.Name, "StructuralPlate")
        self.assertEqual(plate.thickness, 12.5)
        self.assertEqual(plate.offset, -3.0)
        self.assertFalse(plate.reverse_extrusion)
        self.assertEqual(plate.source_mode, "InteractiveRectangle")
        self.assertIsNone(plate.SourceObject)
        contour = self.geometry.PlateContour2D.from_data(plate.ContourData)
        self.assertEqual(contour.vertices, ((2, 3), (7, 3), (7, 11), (2, 11)))
        self.assertEqual(tuple(plate.placement.Base), tuple(self.face_frame.Base))
        self.assertEqual(plate.placement.Rotation, self.face_frame.Rotation)
        self.assertEqual((self.document.commits, self.document.aborts), (1, 0))

    def test_reverse_extrusion_hint_reacts_and_factory_receives_direction(self):
        tool = self.activate()
        self.assertFalse(hasattr(tool.options, "extrusion_hint"))
        self.assertIn("0 até 10 mm", tool.options.reverse.tooltip)
        tool.options.thickness.setValue(6)
        tool.options.offset.setValue(2)
        self.assertIn("2 até 8 mm", tool.options.reverse.tooltip)
        tool.options.reverse.setChecked(True)
        self.assertIn("-4 até 2 mm", tool.options.reverse.tooltip)
        tool.numericInput(1, 2, 0)
        tool.numericInput(11, 12, 0)
        self.flush()
        self.assertTrue(self.created[0].reverse_extrusion)
        self.assertEqual(self.created[0].thickness, 6)
        self.assertEqual(self.created[0].offset, 2)
        self.assert_restored()

    def test_captured_face_frame_overrides_later_face_placement_and_restores_wp(self):
        snapshot = Frame((7, 8, 9), ((0, 1, 0), (0, 0, 1), (1, 0, 0)))
        face = object()
        tool = self.activate(face=face, plane_placement=snapshot)
        self.assertEqual([], self.face_calls)
        self.assertEqual(tuple(tool.placement.Base), tuple(snapshot.Base))
        self.assertEqual(tool.placement.Rotation, snapshot.Rotation)
        tool.numericInput(*snapshot.multVec((0, 0, 0)))
        tool.numericInput(*snapshot.multVec((20, 30, 0)))
        self.flush()
        plate = self.created[0]
        self.assertEqual(tuple(plate.placement.Base), tuple(snapshot.Base))
        self.assertEqual(plate.placement.Rotation, snapshot.Rotation)
        self.assert_restored()

    def test_current_wp_is_captured_and_tracker_sees_frozen_frame(self):
        tool = self.activate()
        self.assertFalse(self.plane.parameters["auto"])
        self.assertEqual(self.plane.alignments, [False])
        self.assertEqual(self.trackers[0].frame_at_creation["position"], tool.placement.Base)
        self.assertEqual(tool.placement.Rotation, self.plane.frame.Rotation)
        tool.finish()
        self.assert_restored()
        self.flush()
        self.assert_restored()

    def test_selected_face_frame_is_frozen_before_tracker_and_not_source(self):
        face = object()
        tool = self.activate(face=face)
        self.assertEqual(self.face_calls, [face])
        self.assertEqual(self.trackers[0].frame_at_creation["axis"], Vector(1, 0, 0))
        self.face_frame = Frame((100, 200, 300))
        tool.numericInput(10, 20, 30)
        tool.numericInput(10, 25, 37)
        self.assertIsNone(self.created[0].SourceObject)
        self.assertEqual(tuple(self.created[0].placement.Base), (10, 20, 30))
        self.flush()
        self.assert_restored()

    def test_rectangle_contour_local_transform_signed_diagonal_and_rejection(self):
        for opposite in ((8, 9, 0), (-8, 9, 0), (8, -9, 0), (-8, -9, 0)):
            with self.subTest(opposite=opposite):
                contour = self.module.rectangle_contour([
                    self.face_frame.multVec((0, 0, 0)), self.face_frame.multVec(opposite)], self.face_frame)
                self.assertEqual(contour.area, 72)
                self.assertEqual(contour.vertices[2], opposite[:2])
        for points in ([], [Vector(0, 0, 0)], [Vector(0, 0, 0), Vector(2, 3, 0.1)],
                       [Vector(0, 0, 0), Vector(float("nan"), 2, 0)],
                       [Vector(0, 0, 0), Vector(float("inf"), 2, 0)],
                       [Vector(0, 0, 0), Vector(0, 2, 0)]):
            with self.subTest(points=points), self.assertRaises(ValueError):
                self.module.rectangle_contour(points, Frame())

    def test_invalid_points_leave_session_usable(self):
        tool = self.activate()
        tool.numericInput(1, 2, 0.1)
        self.assertEqual(tool.node, [])
        tool.numericInput(1, 2, 0)
        tool.numericInput(1, 5, 0)
        self.assertEqual(len(tool.node), 1)
        self.assertEqual(self.created, [])
        self.assertTrue(tool.is_active())
        tool.numericInput(5, 6, 0)
        self.assertEqual(len(self.created), 1)

    def test_native_numeric_delegation_keeps_relative_and_global_independent(self):
        tool = self.activate()
        self.ui.global_axes = True
        tool.numericInput(2, 3, 0)
        self.assertEqual(self.native_numeric, [(2, 3, 0)])
        self.assertTrue(self.ui.relative)
        self.assertTrue(self.ui.global_axes)
        self.ui.relative = False
        tool.numericInput(12, 13, 0)
        self.assertEqual(self.native_numeric[-1], (12, 13, 0))
        self.assertEqual(len(self.created), 1)
        # Conversion belongs to Draft: adapter accepts already-global values.

    def test_cancel_before_and_after_first_point_is_idempotent_and_blocks_late_calls(self):
        for first in (False, True):
            with self.subTest(first=first):
                tool = self.activate()
                if first:
                    tool.numericInput(0, 0, 0)
                closed = []
                tool._on_closed = closed.append
                tracker = tool.rect
                tool.finish()
                self.assertEqual(tool._state, self.module.FINISHING)
                self.assert_restored()
                tool.finish()
                tool.action({"point": Vector(10, 10, 0)})
                tool.numericInput(10, 10, 0)
                tool.appendPoint(Vector(10, 10, 0))
                tool.createObject()
                self.flush()
                tool.finish()
                self.assertEqual(tool._state, self.module.FINISHED)
                self.assertEqual(closed, [tool])
                self.assertEqual(tracker.finalize_calls, 1)
                self.assertEqual(self.created, [])

    def test_esc_uses_native_action_then_restores_without_creation(self):
        tool = self.activate()
        tool.action({"Type": "SoKeyboardEvent", "Key": "ESCAPE"})
        self.assertEqual(len(self.native_actions), 1)
        self.flush()
        self.assert_restored()
        self.assertEqual(self.created, [])

    def test_factory_failure_aborts_transaction_and_restores_wp(self):
        def failed_factory(document, contour, **kwargs):
            document.Objects.append("partial plate")
            raise RuntimeError("factory failed")

        tool = self.activate(factory=failed_factory)
        tool.numericInput(0, 0, 0)
        tool.numericInput(10, 20, 0)
        self.flush()
        self.assertEqual((self.document.commits, self.document.aborts), (0, 1))
        self.assertEqual(self.document.Objects, [])
        self.assertTrue(any("factory failed" in message for message in self.errors))
        self.assert_restored()
        self.assertEqual(tool._state, self.module.FINISHED)

    def test_continue_reuses_callback_tracker_panel_snapshot_for_two_plates(self):
        tool = self.activate()
        self.ui.continueMode = True
        tracker, panel, call = tool.rect, self.ui.panel, tool.call
        for origin in (0, 20):
            tool.numericInput(origin, origin, 0)
            tool.numericInput(origin + 10, origin + 15, 0)
            self.assertTrue(tool.is_active())
            self.assertEqual(tool.node, [])
            self.assertIs(tool.rect, tracker)
            self.assertIs(self.ui.panel, panel)
            self.assertEqual(tool.call, call)
            self.assertFalse(self.ui.relative)
        self.assertEqual(len(self.created), 2)
        self.assertEqual(len(self.view.callbacks), 1)
        self.assertEqual(len(self.trackers), 1)
        tool.finish()
        self.flush()
        self.assert_restored()
        self.assertEqual(self.view.callbacks, {})

    def test_inactive_owner_restore_updates_only_live_active_plane(self):
        tool = self.activate()
        other_plane = Plane(Frame((100, 200, 300)))
        self.active_plane = other_plane
        self.active_view = View()
        tool._view_changed()
        self.flush()
        self.assert_restored()
        self.assertEqual(self.plane.updates, [])
        self.assertTrue(other_plane.updates)
        self.assertTrue(all(history is False for history in other_plane.updates))

    def test_closed_owner_never_touches_old_view_or_grid(self):
        tool = self.activate()
        self.documents.clear()
        self.owner_views = []
        self.active_view = None
        self.observers[0].slotDeletedDocument(self.document)
        self.flush()
        self.assert_restored()
        self.assertEqual(self.view.removed, [])
        self.assertEqual(self.plane.updates, [])
        self.assertEqual(tool._state, self.module.FINISHED)

    def test_destroyed_panel_restores_and_cannot_be_shown_by_queued_work(self):
        tool = self.activate()
        panel = self.ui.panel
        self.ui.baseWidget.destroyed.emit()
        for callback, argument in list(self.todo.ToDo.itinerary):
            callback(argument)
        self.assertNotIn(panel, self.shown)
        self.flush()
        self.assert_restored()

    def test_replacement_tool_is_not_closed_by_old_deferred_work(self):
        first = self.activate()
        first.finish()
        # Another native tool may own the shared UI before old teardown runs.
        replacement = object()
        self.app.activeDraftCommand = replacement
        self.ui.sourceCmd = replacement
        self.ui.panel = object()
        self.flush()
        self.assertIs(self.app.activeDraftCommand, replacement)
        self.assertIs(self.ui.sourceCmd, replacement)
        self.assertEqual(self.native_finishes, 0)
        self.assertEqual(self.closed, [])
        self.assert_restored()

    def test_new_session_after_cancel_restores_original_snapshot(self):
        first = self.activate()
        first.finish()
        self.flush()
        second = self.activate()
        second.numericInput(0, 0, 0)
        second.numericInput(3, 4, 0)
        self.flush()
        self.assertEqual(len(self.created), 1)
        self.assert_restored()

    def test_activation_failure_after_plane_alignment_restores_every_parameter(self):
        tool = self.module.StructuralPlateRectangleTool()
        with patch.object(self.creator, "Activated", side_effect=RuntimeError("activation failed")):
            with self.assertRaisesRegex(RuntimeError, "activation failed"):
                tool.Activated(plane_face=object())
        self.assert_restored()
        self.flush()
        self.assertEqual(tool._state, self.module.FINISHED)
        self.assertIsNone(self.app.activeDraftCommand)

    def test_preexisting_draft_command_is_not_replaced_or_modified(self):
        existing = object()
        self.app.activeDraftCommand = existing
        tool = self.module.StructuralPlateRectangleTool()
        with self.assertRaises(RuntimeError):
            tool.Activated()
        self.assertIs(self.app.activeDraftCommand, existing)
        self.assert_restored()
        self.assertEqual(self.trackers, [])

    def test_native_acquisition_errors_end_session_and_restore_wp(self):
        for method, arguments in (("action", ({"Type": "SoLocation2Event"},)),
                                  ("numericInput", (10, 20, 0))):
            with self.subTest(method=method):
                tool = self.activate()
                with patch.object(self.native_rectangle, method,
                                  side_effect=RuntimeError("native acquisition failed")):
                    getattr(tool, method)(*arguments)
                self.flush()
                self.assert_restored()
                self.assertEqual(tool._state, self.module.FINISHED)
                self.assertEqual(self.created, [])

    def test_view_liveness_guards_numeric_input_and_tracker_scene(self):
        tool = self.activate()
        tracker = tool.rect
        self.owner_views = []
        self.assertIsNone(tracker.get_scene_graph())
        tool.numericInput(5, 5, 0)
        self.assertEqual(self.native_numeric, [])
        self.flush()
        self.assert_restored()
        self.assertEqual(self.view.removed, [])

    def test_close_event_and_foreign_document_observer_are_scoped_to_owner(self):
        tool = self.activate()
        guard = tool._events
        guard.slotDeletedDocument(Document())
        self.assertTrue(tool.is_active())
        event = types.SimpleNamespace(type=lambda: self.module.QtCore.QEvent.Close)
        self.assertFalse(guard.eventFilter(object(), event))
        self.flush()
        self.assert_restored()
        self.assertEqual(tool._state, self.module.FINISHED)

    def test_destroyed_qt_disconnect_does_not_interrupt_remaining_teardown(self):
        for error in (RuntimeError("Qt object deleted"), TypeError("already disconnected")):
            with self.subTest(error=error):
                tool = self.activate()
                tracker = tool.rect
                disconnected = types.SimpleNamespace(disconnect=lambda slot: (_ for _ in ()).throw(error))
                tool._mdi = types.SimpleNamespace(subWindowActivated=disconnected)
                tool._base_widget.destroyed = disconnected
                tool.finish()
                self.flush()
                self.assert_restored()
                self.assertEqual(tracker.finalize_calls, 1)
                self.assertEqual(tool._state, self.module.FINISHED)
                self.assertEqual(self.observers, [])

    def test_numeric_input_in_another_active_view_finishes_before_native_call(self):
        tool = self.activate()
        self.active_view = View()
        self.active_plane = Plane()
        tool.numericInput(10, 20, 0)
        self.assertEqual(self.native_numeric, [])
        self.assertEqual(self.created, [])
        self.flush()
        self.assert_restored()
        self.assertEqual(tool._state, self.module.FINISHED)

    def test_callback_removal_failure_still_schedules_teardown_and_wp_restore(self):
        tool = self.activate()
        tracker = tool.rect
        with patch.object(self.view, "removeEventCallback", side_effect=RuntimeError("callback deleted")):
            with self.assertRaisesRegex(RuntimeError, "callback deleted"):
                tool.finish()
        self.assert_restored()
        self.flush()
        self.assertEqual(tool._state, self.module.FINISHED)
        self.assertEqual(tracker.finalize_calls, 1)

    def test_wp_restore_failure_detaches_callback_and_retries_in_teardown(self):
        tool = self.activate()
        tracker = tool.rect
        with patch.object(self.plane, "set_parameters", side_effect=RuntimeError("restore failed")):
            with self.assertRaisesRegex(RuntimeError, "restore failed"):
                tool.finish()
        self.assertFalse(tool._wp_session.restored)
        self.assertEqual(self.view.callbacks, {})
        tool.action({"point": Vector(10, 10, 0)})
        self.assertEqual(self.created, [])
        self.flush()
        self.assert_restored()
        self.assertEqual(tool._state, self.module.FINISHED)
        self.assertEqual(tracker.finalize_calls, 1)

    def test_tracker_failure_does_not_leave_native_command_or_panel_owned(self):
        tool = self.activate()
        with patch.object(tool.rect, "off", side_effect=RuntimeError("tracker failure")):
            tool.finish()
            self.flush()
        self.assertEqual(self.native_finishes, 1)
        self.assertIsNone(self.app.activeDraftCommand)
        self.assertIsNone(self.ui.sourceCmd)
        self.assert_restored()
        self.assertTrue(any("tracker failure" in message for message in self.errors))

    def test_partial_native_finish_releases_only_own_command_and_ui(self):
        tool = self.activate()
        with patch.object(self.creator, "finish", side_effect=RuntimeError("native finish failed")):
            tool.finish()
            self.flush()
        self.assertIsNone(self.app.activeDraftCommand)
        self.assertIsNone(self.ui.sourceCmd)
        self.assertEqual(tool._state, self.module.FINISHED)
        self.assert_restored()
        self.assertTrue(self.closed)

    def test_foreign_non_draft_panel_not_closed_when_old_box_is_detached(self):
        tool = self.activate()
        tool.finish()
        self.flush()
        task_box = tool._base_widget.parentWidget()
        task_box.parentWidget().items.clear()
        # Draft's Python panel/sourceCmd retain old values for a foreign panel.
        tool._close_owned_panel()
        self.assertEqual(self.closed, [])

    def test_dead_qt_widget_is_not_traversed_by_deferred_close(self):
        tool = self.activate()
        tool.finish()
        self.flush()
        tool._base_widget.valid = False
        with patch.object(tool._base_widget, "parentWidget", side_effect=AssertionError("dead Qt read")):
            tool._close_owned_panel()
        self.assertEqual(self.closed, [])

    def test_hidden_old_taskbox_is_not_closed_but_collapsed_own_content_is(self):
        tool = self.activate()
        tool.finish()
        self.flush()
        task_box = tool._base_widget.parentWidget()
        task_box.hide()
        tool._close_owned_panel()
        self.assertEqual(self.closed, [])
        task_box.hidden = False
        tool._base_widget.hide()  # Collapsing content preserves its TaskBox.
        tool._close_owned_panel()
        self.assertEqual(self.closed, [True])

    def test_native_panel_reject_ends_own_acquisition_without_document_edit_reset(self):
        tool = self.activate()
        self.assertTrue(tool.ui.panel.reject())
        self.assertFalse(tool.ui.isTaskOn)
        self.assertEqual(tool._state, self.module.FINISHING)
        self.flush()
        self.assert_restored()

    def test_native_numeric_shortcut_guard_and_original_connections_restore(self):
        calls = []
        original = calls.append
        for name in ("xValue", "yValue", "zValue", "lengthValue", "radiusValue", "angleValue"):
            field = getattr(self.ui, name)
            field.textEdited.disconnect(self.ui.checkSpecialChars)
            field.textEdited.connect(original)
        self.ui.checkSpecialChars = original
        module = sys.modules[self.namespace + ".interactive.plate_panel_shortcuts"]
        module.editable_focus = lambda focus: True
        tool = self.activate()
        guarded = self.ui.xValue.textEdited.slots[0]
        self.ui.xValue.textEdited.emit("R")
        self.ui.xValue.textEdited.emit("mm")
        self.ui.xValue.textEdited.emit("-12 mm")
        self.assertEqual(calls, ["-12 mm"])
        shortcuts = tool._shortcuts
        tool.finish()
        self.assertTrue(shortcuts.disposed)
        self.assertIs(self.ui.xValue.textEdited.slots[0], original)
        guarded("45")
        self.assertEqual(calls, ["-12 mm"])

    def test_native_axis_shortcuts_call_existing_constraint_and_presentation(self):
        calls = []
        self.ui.constrain = lambda axis: calls.append(("constrain", axis))
        self.ui.new_point = "candidate"
        self.ui.get_last_point = lambda: "last"
        self.ui.displayPoint = lambda point, last: calls.append(("display", point, last))
        tool = self.activate()
        for axis in ("X", "Y", "Z"):
            tool._shortcuts.callbacks[axis]()
            self.assertEqual(calls[-2:], [("constrain", axis.lower()), ("display", "candidate", "last")])
        tool._shortcuts.callbacks["L"]()
        self.assertEqual(calls[-2:], [("constrain", "angle"), ("display", "candidate", "last")])

    def test_graphical_motion_releases_only_completed_native_numeric_editing(self):
        tool = self.activate()
        focus = tool._coordinate_focus
        focus.set_editing(True)
        self.ui.mouse = False
        tool.action({"Type": "SoLocation2Event"})
        self.assertTrue(focus.editing, "Respect native MouseDelay while typing")
        self.ui.mouse = True
        tool.action({"Type": "SoLocation2Event"})
        self.assertFalse(focus.editing)
        self.ui.xValue.textEdited.emit("-12 mm")
        self.assertTrue(focus.editing)
        tool.finish()
        self.assertTrue(focus.disposed)
        tool.action({"Type": "SoLocation2Event"})
        self.assertTrue(focus.editing, "Late native events cannot change disposed input")

    def test_fresh_native_close_wrapper_is_guarded_before_foreign_panel(self):
        tool = self.activate()
        class NativeClose:
            __name__ = "closeDialog"
            def __call__(callback):
                self.closed.append(True)
            def __eq__(callback, other):
                return False
        self.ui.offUi = lambda: self.todo.ToDo.itinerary.append((NativeClose(), None))
        tool.finish()
        self.flush()
        tool._base_widget.parentWidget().parentWidget().items.clear()
        for callback, argument in list(self.todo.ToDo.itinerary):
            if argument is None:
                callback()
            else:
                callback(argument)
        self.assertEqual(self.closed, [])


if __name__ == "__main__":
    unittest.main()
