"""Session lifecycle and incremental presentation without a FreeCAD runtime."""
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = "_structural_reference_view_test"


class Signal:
    def __init__(self): self.slots = []
    def connect(self, slot): self.slots.append(slot)
    def disconnect(self, slot=None):
        if slot is None: self.slots.clear()
        else: self.slots.remove(slot)


class Timer:
    def __init__(self): self.timeout, self.active, self.deleted = Signal(), False, False
    def setSingleShot(self, value): pass
    def setInterval(self, value): self.interval = value
    def start(self, *args): self.active = True
    def stop(self): self.active = False
    def isActive(self): return self.active
    def deleteLater(self): self.deleted = True


class Document:
    def __init__(self, name): self.Name, self.objects = name, {}
    @property
    def Objects(self): return list(self.objects.values())
    def getObject(self, name): return self.objects.get(name)
    def recompute(self): raise AssertionError("presentation cannot recompute solids")


class Member:
    TypeId = "Part::FeaturePython"
    PropertiesList = ("StartPoint", "EndPoint")
    def __init__(self, doc, name):
        self.Document, self.Name = doc, name
        self.StartPoint, self.EndPoint = (0, 0, 0), (0, 0, 1000)
        self.ViewObject = types.SimpleNamespace(Visibility=True)
        self.parent, self.rejected = None, ""
        doc.objects[name] = self
    def getParentGeoFeatureGroup(self): return self.parent


class Layer:
    def __init__(self, view):
        self.view, self.cleared, self.updates = view, False, []
        self.on_top = False
        self.presentation = Presentation(view)
    def update(self, axes, a, b): self.updates.append((axes, a, b))
    def clear(self):
        self.cleared, self.view = True, None
        self.on_top = False
        self.presentation.close()
    def refresh_style(self): pass
    def set_on_top(self, enabled): self.on_top = enabled


class Presentation:
    def __init__(self, view): self.mode, self.closed = "physical", False
    def update(self, mode, revision=None): self.mode = mode
    def clear(self): self.mode = "physical"
    def close(self): self.closed = True


class Action:
    def __init__(self): self.checked, self.blocked = False, False
    def blockSignals(self, value):
        previous, self.blocked = self.blocked, value
        return previous
    def setCheckable(self, value): self.checkable = value
    def setChecked(self, value): self.checked = value
    def setText(self, value): self.text = value
    def setToolTip(self, value): self.tooltip = value


class Field:
    def __init__(self): self.values = []
    def setValue(self, *values): self.values = list(values)
    def setValues(self, start, count, values): self.values[start:start+count] = list(values)
    def setNum(self, count): self.values = self.values[:count]
    def getValue(self): return self.values[0] if len(self.values) == 1 else self.values


class CoinNode:
    UNPICKABLE, BASE_COLOR, LEQUAL = 0, 1, 2
    CIRCLE_FILLED_9_9, SQUARE_FILLED_9_9 = 3, 4
    CIRCLE_FILLED_5_5, SQUARE_FILLED_5_5 = 5, 6
    marker_registry = {}
    @classmethod
    def getNumDefinedMarkers(cls): return 1000 + len(cls.marker_registry)
    @classmethod
    def addMarker(cls, index, size, data, lsb, top_down):
        cls.marker_registry[index] = (size, data, lsb, top_down)
    def __init__(self):
        object.__setattr__(self, "fields", {name: Field() for name in (
            "style", "model", "test", "write", "function", "point", "whichChild",
            "rgb", "lineWidth", "linePattern", "linePatternScaleFactor", "numPoints", "numVertices", "markerIndex")})
        self.children = []
        self.pins = 0
    def __getattr__(self, name):
        if name in self.fields: return self.fields[name]
        raise AttributeError(name)
    def __setattr__(self, name, value):
        if name in self.fields: self.fields[name].setValue(value)
        else: object.__setattr__(self, name, value)
    def write(self): raise AssertionError("Pivy write method is not the field")
    def getField(self, name): return self.fields[name]
    def setName(self, name): self.name = name
    def addChild(self, node): self.children.append(node)
    def findChild(self, node): return self.children.index(node) if node in self.children else -1
    def removeChild(self, node): self.children.remove(node)
    def replaceChild(self, old, new): self.children[self.children.index(old)] = new
    def removeAllChildren(self): self.children.clear()
    def ref(self): self.pins += 1
    def unref(self):
        self.pins -= 1
        if self.pins < 0: raise AssertionError("unbalanced reference-layer pin")


class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.docs, self.views, self.app_observers, self.gui_observers = {}, {}, [], []
        self.reads = []
        self.mdi = types.SimpleNamespace(subWindowActivated=Signal())
        self.native_actions = {name: Action() for name in (
            "SteelStructures_ToggleMemberAxes", "SteelStructures_ToggleMemberEndpoints",
            "SteelStructures_DisplayPhysical", "SteelStructures_DisplayStructural", "SteelStructures_DisplayXRay")}
        self.actions = [self.native_actions["SteelStructures_ToggleMemberAxes"],
                        self.native_actions["SteelStructures_ToggleMemberEndpoints"]]
        self.app = types.SimpleNamespace(ActiveDocument=None, listDocuments=lambda: self.docs,
            addDocumentObserver=self.app_observers.append, removeDocumentObserver=self.app_observers.remove,
            Console=types.SimpleNamespace(PrintWarning=lambda text: None))
        def gui_doc(name):
            return types.SimpleNamespace(mdiViewsOfType=lambda kind: self.views.get(name, []),getInEdit=lambda: None)
        self.gui = types.SimpleNamespace(addDocumentObserver=self.gui_observers.append,
            removeDocumentObserver=self.gui_observers.remove, getDocument=gui_doc,
            getMainWindow=lambda: types.SimpleNamespace(findChild=lambda kind: self.mdi),
            Command=types.SimpleNamespace(get=lambda name: types.SimpleNamespace(getAction=lambda: (
                self.native_actions[name],))))
        self.gui.Control = types.SimpleNamespace(activeDialog=lambda: None)
        def resolve(member, **kwargs):
            self.reads.append(member.Name)
            self.last_context = kwargs.get("context")
            axis = (None if member.rejected else types.SimpleNamespace(
                key=member.Name, start=member.StartPoint, end=member.EndPoint))
            return types.SimpleNamespace(axis=axis, reason=member.rejected)
        package = types.ModuleType(PACKAGE)
        package.__path__ = [str(ROOT / "freecad/SteelStructures")]
        interactive = types.ModuleType(PACKAGE + ".interactive")
        interactive.__path__ = [str(ROOT / "freecad/SteelStructures/interactive")]
        resolver = types.ModuleType(PACKAGE + ".structural_reference")
        resolver.resolve_member_axis = resolve
        resolver.AxisReadContext = lambda **kwargs: types.SimpleNamespace(**kwargs)
        resolver.axis_state_signature = lambda obj, **kwargs: (obj.Name, obj.StartPoint, obj.EndPoint)
        self.injected = patch.dict(sys.modules, {
            PACKAGE: package, PACKAGE + ".interactive": interactive,
            resolver.__name__: resolver, "FreeCAD": types.SimpleNamespace(**vars(self.app), Gui=self.gui),
            "PySide": types.SimpleNamespace(QtCore=types.SimpleNamespace(QTimer=Timer),
                QtWidgets=types.SimpleNamespace(QMdiArea=object))})
        self.injected.start()
        spec = importlib.util.spec_from_file_location(PACKAGE + ".interactive.structural_reference_view",
            ROOT / "freecad/SteelStructures/interactive/structural_reference_view.py")
        self.module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = self.module
        spec.loader.exec_module(self.module)
        self.module.ViewportPresentation = Presentation
        self.layer_type = self.module.ReferenceLayer
        self.module.ReferenceLayer = Layer
        self.service = self.module.StructuralReferenceService()
        self.service.activate()
        self.doc = self.add_doc("First")
        self.a, self.b = Member(self.doc, "A"), Member(self.doc, "B")

    def tearDown(self):
        self.service.deactivate()
        self.injected.stop()
        for name in tuple(sys.modules):
            if name.startswith(PACKAGE): sys.modules.pop(name, None)

    def add_doc(self, name):
        doc = Document(name)
        self.docs[name], self.views[name] = doc, [object()]
        self.module.App.ActiveDocument = doc
        return doc

    def flush(self): self.service.refresh_now()
    def session(self, doc=None): return self.service._sessions[(doc or self.doc).Name]

    def test_flags_are_independent_and_all_off_releases_resources(self):
        self.service.toggle("endpoints", True)
        self.flush()
        self.assertEqual(self.service.state(), (False, True))
        self.assertEqual(self.actions[1].checked, True)
        self.service.toggle("axes", True)
        self.flush()
        self.assertEqual(self.service.state(), (True, True))
        layer = self.session().layers[0]
        timer = self.service._view_timer
        self.service.toggle("endpoints", False)
        self.service.toggle("axes", False)
        self.assertTrue(layer.cleared and timer.deleted)
        self.assertFalse(self.service._sessions or self.app_observers or self.gui_observers)
        self.assertFalse(self.mdi.subWindowActivated.slots)

    def test_presets_keep_physical_flags_and_allow_independent_layers(self):
        self.service.toggle("axes",True)
        self.flush()
        self.service.set_mode("structural")
        self.flush()
        self.assertEqual(self.service.state(),(True,True))
        self.service.toggle("axes",False)
        self.service.toggle("endpoints",False)
        self.flush()
        self.assertEqual(self.service.mode(),"structural")
        self.assertTrue(self.service._sessions)
        self.service.set_mode("xray")
        self.flush()
        self.assertEqual(self.service.state(),(False,False))
        self.service.set_mode("physical")
        self.flush()
        self.assertEqual(self.service.state(),(True,False))
        self.assertEqual(self.service.mode(),"physical")

    def test_modes_suspend_for_tasks_and_inactive_documents(self):
        self.service.set_mode("xray")
        self.flush()
        layer=self.session().layers[0]
        self.assertEqual(layer.presentation.mode,"xray")
        self.assertTrue(layer.on_top)
        self.reads.clear()
        self.gui.Control.activeDialog=lambda: object()
        self.flush()
        self.assertEqual(layer.presentation.mode,"physical")
        self.assertFalse(layer.on_top)
        self.assertEqual(self.service.mode(),"xray")
        self.gui.Control.activeDialog=lambda: None
        other=self.add_doc("Other")
        self.flush()
        self.assertEqual(layer.presentation.mode,"physical")
        self.assertFalse(layer.on_top)
        self.assertEqual(self.service.mode(other),"physical")
        self.module.App.ActiveDocument=self.doc
        self.flush()
        self.assertEqual(layer.presentation.mode,"xray")
        self.assertTrue(layer.on_top)
        self.assertFalse(self.reads)

    def test_presentation_failure_returns_physical_without_property_fallback(self):
        self.service.set_mode("xray")
        self.flush()
        with patch.object(self.session().layers[0].presentation,"update",side_effect=RuntimeError("copy failed")):
            self.flush()
        self.assertEqual(self.service.mode(),"physical")
        self.assertFalse(self.service._sessions or self.service._observing)

    def test_visual_revision_and_expired_provider_do_not_read_member_geometry(self):
        self.service.set_mode("xray")
        self.flush()
        self.reads.clear()
        revision=self.session().graph_revision
        self.a.ViewObject.Object=self.a
        self.service._gui_observer.slotChangedObject(self.a.ViewObject,"ShapeColor")
        self.flush()
        self.assertGreater(self.session().graph_revision,revision)
        self.assertFalse(self.reads)
        class Expired:
            @property
            def Object(self): raise Exception("expired native provider")
        self.service._gui_observer.slotChangedObject(Expired(),"ShapeColor")

    def test_gui_document_close_releases_graphics_before_native_destruction(self):
        self.service.set_mode("xray")
        self.flush()
        layer=self.session().layers[0]
        self.service._gui_observer.slotDeletedDocument(types.SimpleNamespace(Document=self.doc))
        self.assertTrue(layer.cleared and layer.presentation.closed)
        self.assertFalse(self.service._sessions)
        self.flush()
        self.assertFalse(self.service._observing)

    def test_only_material_changes_resolve_and_periodic_view_check_does_not(self):
        self.service.toggle("axes", True)
        self.flush()
        self.assertEqual(set(self.reads), {"A", "B"})
        self.reads.clear()
        self.service.slotChangedObject(self.a, "Label")
        self.service._reconcile_views()
        self.flush()
        self.assertEqual(self.reads, [])
        self.a.EndPoint = (1, 2, 3)
        self.service.slotChangedObject(self.a, "EndPoint")
        self.service.slotRecomputedObject(self.a)
        self.flush()
        self.assertEqual(self.reads, ["A"])
        self.assertEqual(self.session().axes["A"].end, (1, 2, 3))

    def test_visibility_changes_redraw_without_resolving_or_writing(self):
        self.service.toggle("axes", True)
        self.flush()
        self.reads.clear()
        self.a.ViewObject.Object = self.a
        self.a.ViewObject.Visibility = False
        self.service._gui_observer.slotChangedObject(self.a.ViewObject, "Visibility")
        self.flush()
        self.assertEqual(self.reads, [])
        shown = self.session().layers[0].updates[-1][0]
        self.assertEqual([axis.key for axis in shown], ["B"])
        self.assertFalse(self.a.ViewObject.Visibility)

    def test_parent_motion_invalidates_descendants_without_dynamic_shape_lookup(self):
        self.service.toggle("axes", True)
        self.flush()
        class Parent:
            TypeId, PropertiesList = "App::Part", ("Placement",)
            Name, Document = "Part", self.doc
            def __getattr__(self, name):
                raise AssertionError("must not resolve dynamic native subobject " + name)
        self.reads.clear()
        self.service.slotChangedObject(Parent(), "Placement")
        self.flush()
        self.assertEqual(set(self.reads), {"A", "B"})

    def test_rejected_pending_axis_retries_on_document_recompute(self):
        self.a.rejected = "pending"
        self.service.toggle("axes", True)
        self.flush()
        self.assertNotIn("A", self.session().axes)
        self.a.rejected = ""
        self.service.slotRecomputedDocument(self.doc)
        self.flush()
        self.assertIn("A", self.session().axes)

    def test_two_documents_and_reused_name_never_share_flags(self):
        self.service.toggle("axes", True)
        self.flush()
        other = self.add_doc("Other")
        Member(other, "A")
        self.assertEqual(self.service.state(), (False, False))
        self.service.toggle("endpoints", True)
        self.flush()
        self.assertEqual(self.service.state(self.doc), (True, False))
        self.assertEqual(self.service.state(other), (False, True))
        old_layers = self.session(other).layers[:]
        del self.docs["Other"]
        self.service.slotDeletedDocument(other)
        replacement = self.add_doc("Other")
        self.flush()
        self.assertEqual(self.service.state(replacement), (False, False))
        self.assertTrue(all(layer.cleared for layer in old_layers))

    def test_new_and_closed_inactive_views_have_exactly_one_layer_each(self):
        self.service.toggle("axes", True)
        self.flush()
        first = self.session().layers[0]
        second_view = object()
        self.views[self.doc.Name].append(second_view)
        self.service._reconcile_views()
        self.flush()
        self.assertEqual(len(self.session().layers), 2)
        self.views[self.doc.Name].remove(first.view)
        self.service._reconcile_views()
        self.flush()
        self.assertTrue(first.cleared)
        self.assertEqual([layer.view for layer in self.session().layers], [second_view])

    def test_delete_history_and_queued_flush_after_deactivate(self):
        self.service.toggle("axes", True)
        self.flush()
        del self.doc.objects["A"]
        self.service.slotDeletedObject(self.a)
        self.flush()
        self.assertNotIn("A", self.session().axes)
        self.doc.objects["A"] = self.a
        self.service.slotUndoDocument(self.doc)
        self.flush()
        self.assertIn("A", self.session().axes)
        self.service.slotChangedObject(self.a, "Placement")
        self.service.deactivate()
        self.service._flush()
        self.assertFalse(self.service._sessions or self.app_observers)
        self.service.activate()
        self.assertEqual(self.service.state(), (False, False))

    def test_same_batch_replacement_by_foreign_object_discards_axis_and_replay(self):
        self.service.toggle("axes", True)
        self.flush()
        self.assertIn("A", self.session().trusted)
        self.service.slotDeletedObject(self.a)
        foreign = types.SimpleNamespace(Document=self.doc, Name="A", TypeId="Part::Box", PropertiesList=())
        self.doc.objects["A"] = foreign
        self.service.slotCreatedObject(foreign)
        self.flush()
        self.assertNotIn("A", self.session().axes)
        self.assertNotIn("A", self.session().trusted)
        self.assertEqual([axis.key for axis in self.session().layers[0].updates[-1][0]], ["B"])
        del self.doc.objects["B"]
        self.service.slotDeletedObject(self.b)
        self.flush()
        self.assertFalse(self.session().axes)
        self.assertIn("B", self.session().trusted)  # Needed by Undo deletion.

    def test_full_scan_discards_replay_for_removed_or_foreign_sources(self):
        self.service.toggle("axes", True)
        self.flush()
        del self.doc.objects["A"]
        self.doc.objects["B"] = types.SimpleNamespace(Document=self.doc, Name="B", TypeId="Part::Box", PropertiesList=())
        self.service.slotUndoDocument(self.doc)
        self.flush()
        self.assertFalse(self.session().axes)
        self.assertEqual(set(self.session().trusted), {"A"})  # Absent, not replaced.

    def test_renderer_batch_shrinks_to_empty_and_keeps_depth_and_picking_local(self):
        coin = types.SimpleNamespace(**{name: CoinNode for name in (
            "SoSeparator", "SoAnnotation", "SoPickStyle", "SoLightModel", "SoDepthBuffer", "SoCoordinate3",
            "SoSwitch", "SoBaseColor", "SoDrawStyle", "SoLineSet", "SoMarkerSet")},
            SO_SWITCH_ALL=-3, SO_SWITCH_NONE=-1, SbVec2s=lambda *values: values)
        scene = CoinNode()
        view = types.SimpleNamespace(getSceneGraph=lambda: scene)
        a = types.SimpleNamespace(start=(0, 0, 0), end=(1, 0, 0))
        # Distinct in depth, coincident in an X/Z front projection. Rendering
        # preserves both segments and all four ends; it creates no node graph.
        b = types.SimpleNamespace(start=(0, 1, 0), end=(1, 1, 0))
        with patch.dict(sys.modules, {"pivy": types.SimpleNamespace(coin=coin)}):
            layer = self.layer_type(view)
            layer.update((a, b), True, False)
            self.assertEqual(len(layer.coordinates.point.values), 4)
            self.assertEqual(layer.coordinates.point.values, [a.start, a.end, b.start, b.end])
            self.assertEqual(layer._lines[0].numVertices.values, [2, 2])
            self.assertEqual(layer.point_switch.whichChild.getValue(), -1)
            self.assertFalse(layer.root.children[2].getField("write").getValue())
            self.assertTrue(layer.root.children[2].test.getValue())
            self.assertEqual(layer.root.children[0].style.getValue(), coin.SoPickStyle.UNPICKABLE)
            updates = layer.geometry_updates
            layer.update((a, b), False, True)
            self.assertEqual(layer.geometry_updates, updates)
            layer.update((a,), True, True)
            self.assertEqual(len(layer.coordinates.point.values), 2)
            self.assertEqual(layer._lines[0].numVertices.values, [2])
            layer.update((), True, True)
            self.assertEqual(layer.coordinates.point.values, [])
            self.assertTrue(all(marker.numPoints.getValue() == 0 for marker in layer._markers))
            layer.clear()
            layer.clear()
            self.assertFalse(scene.children)

    def test_filled_circle_map_is_symmetric_round_and_matches_the_pivy_contract(self):
        diameter = 15
        bitmap = self.module._circle_bitmap(diameter)
        self.assertIsInstance(bitmap, str)
        self.assertEqual(len(bitmap), diameter*diameter)
        self.assertEqual(set(bitmap), {"#", " "})
        def filled(x, y): return bitmap[y*diameter+x] == "#"
        for y in range(diameter):
            for x in range(diameter):
                self.assertEqual(filled(x, y), filled(diameter-1-x, y))
                self.assertEqual(filled(x, y), filled(x, diameter-1-y))
        self.assertTrue(filled(7, 7) and filled(7, 0))
        self.assertFalse(filled(0, 0) or filled(14, 14))

    def test_annotation_reuses_batch_preserves_toggles_and_releases_native_pins(self):
        coin = types.SimpleNamespace(**{name: CoinNode for name in (
            "SoSeparator", "SoAnnotation", "SoPickStyle", "SoLightModel", "SoDepthBuffer", "SoCoordinate3",
            "SoSwitch", "SoBaseColor", "SoDrawStyle", "SoLineSet", "SoMarkerSet")},
            SO_SWITCH_ALL=-3, SO_SWITCH_NONE=-1, SbVec2s=lambda *values: values)
        scene = CoinNode()
        view = types.SimpleNamespace(getSceneGraph=lambda: scene)
        with patch.dict(sys.modules, {"pivy": types.SimpleNamespace(coin=coin)}):
            layer = self.layer_type(view)
            root, annotation = layer.root, layer._annotation
            layer.update((types.SimpleNamespace(start=(0,0,0), end=(1,0,0)),), True, False)
            coordinates, updates = layer.coordinates, layer.geometry_updates
            for _ in range(20):
                layer.set_on_top(True)
                self.assertEqual(scene.children, [annotation])
                self.assertEqual(annotation.children, [root])
                self.assertIs(layer.coordinates, coordinates)
                self.assertFalse(layer.depth.test.getValue())
                self.assertFalse(layer.depth.getField("write").getValue())
                self.assertEqual(layer.point_switch.whichChild.getValue(), -1)
                layer.set_on_top(False)
                self.assertEqual(scene.children, [root])
                self.assertFalse(annotation.children)
                self.assertTrue(layer.depth.test.getValue())
            self.assertEqual(layer.geometry_updates, updates)
            layer.set_on_top(True)
            layer.update((), False, True)
            self.assertEqual(layer.coordinates.point.values, [])
            layer.clear()
            layer.clear()
            self.assertFalse(scene.children or annotation.children or root.children)
            self.assertEqual((root.pins, annotation.pins), (0,0))

    def test_missing_attachment_cannot_reparent_unowned_scene_content(self):
        coin = types.SimpleNamespace(**{name: CoinNode for name in (
            "SoSeparator", "SoAnnotation", "SoPickStyle", "SoLightModel", "SoDepthBuffer", "SoCoordinate3",
            "SoSwitch", "SoBaseColor", "SoDrawStyle", "SoLineSet", "SoMarkerSet")},
            SO_SWITCH_ALL=-3, SO_SWITCH_NONE=-1, SbVec2s=lambda *values: values)
        scene = CoinNode()
        with patch.dict(sys.modules, {"pivy": types.SimpleNamespace(coin=coin)}):
            layer = self.layer_type(types.SimpleNamespace(getSceneGraph=lambda: scene))
            scene.removeChild(layer.root)
            foreign = CoinNode()
            scene.addChild(foreign)
            with self.assertRaisesRegex(RuntimeError, "ausente"):
                layer.set_on_top(True)
            self.assertFalse(layer.on_top)
            self.assertEqual(scene.children, [foreign])
            layer.clear()
            self.assertEqual(scene.children, [foreign])

    def test_presentation_close_failure_still_releases_reference_attachment(self):
        coin = types.SimpleNamespace(**{name: CoinNode for name in (
            "SoSeparator", "SoAnnotation", "SoPickStyle", "SoLightModel", "SoDepthBuffer", "SoCoordinate3",
            "SoSwitch", "SoBaseColor", "SoDrawStyle", "SoLineSet", "SoMarkerSet")},
            SO_SWITCH_ALL=-3, SO_SWITCH_NONE=-1, SbVec2s=lambda *values: values)
        scene = CoinNode()
        with patch.dict(sys.modules, {"pivy": types.SimpleNamespace(coin=coin)}):
            layer = self.layer_type(types.SimpleNamespace(getSceneGraph=lambda: scene))
            layer.set_on_top(True)
            root, annotation = layer.root, layer._annotation
            def failing_close():
                self.assertFalse(scene.children)
                self.assertIsNone(layer.node)
                raise RuntimeError("native close failed")
            with patch.object(layer.presentation, "close", side_effect=failing_close):
                with self.assertRaisesRegex(RuntimeError, "native close failed"):
                    layer.clear()
            self.assertFalse(scene.children or annotation.children or root.children)
            self.assertEqual((root.pins, annotation.pins), (0,0))
            self.assertIsNone(layer.node)
            layer.clear()

    def test_refined_style_dpi_and_marker_registry_are_shared_without_geometry_updates(self):
        coin = types.SimpleNamespace(**{name: CoinNode for name in (
            "SoSeparator", "SoAnnotation", "SoPickStyle", "SoLightModel", "SoDepthBuffer", "SoCoordinate3",
            "SoSwitch", "SoBaseColor", "SoDrawStyle", "SoLineSet", "SoMarkerSet")},
            SO_SWITCH_ALL=-3, SO_SWITCH_NONE=-1, SbVec2s=lambda *values: values)
        scene = CoinNode()
        view = types.SimpleNamespace(getSceneGraph=lambda: scene)
        with patch.dict(sys.modules, {"pivy": types.SimpleNamespace(coin=coin)}), \
                patch.object(self.module, "_display_scale", return_value=1.0) as scale:
            before = coin.SoMarkerSet.getNumDefinedMarkers()
            layer = self.layer_type(view)
            self.assertEqual(coin.SoMarkerSet.getNumDefinedMarkers()-before, 3)
            duplicate = self.layer_type(view)
            self.assertEqual(coin.SoMarkerSet.getNumDefinedMarkers()-before, 3)
            self.assertEqual([s.lineWidth.getValue() for s in layer._line_styles], [4.5, 2.5])
            self.assertTrue(all(s.linePattern.getValue() == 0x03FF for s in layer._line_styles))
            self.assertEqual(self.module.AXIS_PATTERN.bit_count(), 10)
            self.assertTrue(all(s.linePatternScaleFactor.getValue() == 2 for s in layer._line_styles))
            colors = [branch.children[0].rgb.getValue() for branch in layer.point_switch.children]
            self.assertEqual(colors[1], list(self.module.ENDPOINT_OUTLINE_COLOR))
            self.assertEqual(colors[2], list(self.module.ENDPOINT_COLOR))
            self.assertEqual(len(layer._markers), 3)
            layer.update((types.SimpleNamespace(start=(0,0,0), end=(1,0,0)),), True, True)
            indices = [node.markerIndex.getValue() for node in layer._markers]
            self.assertEqual([coin.SoMarkerSet.marker_registry[i][0] for i in indices], [(15,15), (13,13), (9,9)])
            self.assertTrue(all(coin.SoMarkerSet.marker_registry[i][2:] == (False, True) for i in indices))
            updates = layer.geometry_updates
            scale.return_value = 1.5
            layer.refresh_style()
            self.assertEqual(layer.geometry_updates, updates)
            self.assertEqual([s.lineWidth.getValue() for s in layer._line_styles], [6.75, 3.75])
            indices = [node.markerIndex.getValue() for node in layer._markers]
            self.assertEqual([coin.SoMarkerSet.marker_registry[i][0] for i in indices], [(23,23), (21,21), (15,15)])
            self.assertTrue(all(s.linePatternScaleFactor.getValue() == 3 for s in layer._line_styles))
            layer.clear()
            duplicate.clear()

    def load_commands(self):
        spec = importlib.util.spec_from_file_location(PACKAGE + ".interactive.structural_reference_commands",
            ROOT / "freecad/SteelStructures/interactive/structural_reference_commands.py")
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        module.service = self.service
        return module

    def test_commands_have_no_transaction_and_toggle_canonical_session_state(self):
        self.gui.activeDocument = lambda: types.SimpleNamespace(
            activeView=lambda: self.views[self.doc.Name][0],
            mdiViewsOfType=lambda kind: self.views[self.doc.Name])
        module = self.load_commands()
        command = module.StructuralReferenceCommand("axes")
        self.assertTrue(command.IsActive())
        self.assertEqual(command.GetResources()["CmdType"], "NoTransaction")
        self.assertTrue(command.GetResources()["Checkable"])
        self.assertIn("nominal", command.GetResources()["ToolTip"])
        command.Activated(0)
        self.assertEqual(self.service.state(), (True, False))
        command.Activated(1)
        self.assertEqual(self.service.state(), (False, False))
        self.service.deactivate()
        self.assertFalse(command.IsActive())

    def test_three_mode_commands_replace_selector_and_reuse_distinct_icons(self):
        module = self.load_commands()
        registered = {}
        self.gui.addCommand = lambda name, command: registered.setdefault(name, command)
        expected = ["SteelStructures_DisplayPhysical", "SteelStructures_DisplayStructural",
                    "SteelStructures_DisplayXRay", "SteelStructures_ToggleMemberAxes",
                    "SteelStructures_ToggleMemberEndpoints"]
        self.assertEqual(module.register_commands(), expected)
        self.assertEqual(list(registered), expected)
        resources = [registered[name].GetResources() for name in expected[:3]]
        self.assertEqual([r["MenuText"] for r in resources], ["Físico", "Estrutural", "Raio X"])
        self.assertEqual(len({r["Pixmap"] for r in resources}), 3)
        self.assertTrue(all(Path(r["Pixmap"]).is_file() for r in resources))
        self.assertTrue(all(r["Checkable"] and r["CmdType"] == "NoTransaction" for r in resources))
        self.assertNotIn("SteelStructures_StructuralDisplayMode", registered)

    def test_mode_actions_are_exclusive_and_selected_button_cannot_toggle_off(self):
        module = self.load_commands()
        self.gui.activeDocument = lambda: types.SimpleNamespace(
            activeView=lambda: self.views[self.doc.Name][0],
            mdiViewsOfType=lambda kind: self.views[self.doc.Name])
        self.service.toggle("axes", True)
        self.flush()
        for mode in ("structural", "xray", "physical"):
            command = module.StructuralDisplayModeCommand(mode)
            command.Activated()
            action = self.native_actions[module.MODE_COMMANDS[mode]]
            self.assertTrue(action.checked)
            self.assertEqual(sum(self.native_actions[n].checked for n in module.MODE_COMMANDS.values()), 1)
            action.checked = False  # Native QAction toggles before callback.
            command.Activated(0)
            self.assertTrue(action.checked)
        self.assertEqual(self.service.state(), (True, False))
        self.service.deactivate()
        self.assertFalse(any(self.native_actions[n].checked for n in module.MODE_COMMANDS.values()))

    def test_replay_uses_only_previously_clean_signatures_and_material_edits_revoke(self):
        self.service.toggle("axes", True)
        self.flush()
        self.assertIn("A", self.session().trusted)
        self.assertIsNone(self.last_context.trusted_replay)
        self.service.slotUndoDocument(self.doc)
        self.flush()
        self.assertIn("A", self.last_context.trusted_replay)
        self.service.slotChangedObject(self.a, "Label")
        self.assertTrue(self.session().replay)
        self.a.EndPoint = (1, 2, 3)
        self.service.slotChangedObject(self.a, "EndPoint")
        self.assertFalse(self.session().replay)
        self.flush()
        self.assertIsNone(self.last_context.trusted_replay)

    def test_full_restore_discards_replay_evidence_and_history_is_bounded(self):
        self.service.toggle("axes", True)
        for i in range(40):
            self.a.EndPoint = (1, 2, i)
            self.service.slotChangedObject(self.a, "EndPoint")
            self.flush()
        self.assertEqual(len(self.session().trusted["A"]), 32)
        self.service.slotFinishRestoreDocument(self.doc)
        self.assertFalse(self.session().trusted or self.session().replay)


if __name__ == "__main__": unittest.main()
