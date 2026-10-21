# SPDX-License-Identifier: LGPL-2.1-or-later
"""Native GUI integration gate, launched by run_simple_u_stage_b_gate.py.

Uses real Qt controls, FeaturePython members, Draft axes and truss sessions.
Assertions and captured widgets are evidence, not user design approval.
"""

from copy import deepcopy
from dataclasses import asdict
import json
import math
import os
from pathlib import Path
import shutil
import sys
import traceback


def run(output):
    import FreeCAD as App
    import FreeCADGui as Gui
    import Draft
    import DraftTools  # Initialize the native Draft Snapper.
    import shiboken6
    from PySide import QtCore, QtGui, QtWidgets
    from PySide6 import QtTest
    from freecad.SteelStructures import profile_catalog, truss
    from freecad.SteelStructures.paths import CATALOGS_DIR
    from freecad.SteelStructures.profiles import ProfileLibrary, build_section_geometry
    from freecad.SteelStructures.profiles.insertion import section_insertion_references
    from freecad.SteelStructures.member_axis_source import resolve_axis_source
    from freecad.SteelStructures.interactive.member_controller import MemberController, CreationGeometryMode
    from freecad.SteelStructures.interactive.profile_options_widget import ProfileOptionsWidget
    from freecad.SteelStructures.interactive.column_task_panel import ColumnTaskPanel
    from freecad.SteelStructures.interactive.profile_browser import ProfileBrowserDialog
    from freecad.SteelStructures.interactive.draft_member_tool import StructuralMemberDraftTool
    from freecad.SteelStructures.interactive import truss_controller as controllers
    from freecad.SteelStructures.interactive.truss_task_panel import _RoleProfileDialog, role_spec_from_options
    from freecad.SteelStructures.trusses.assemblies import configure_assembly
    from freecad.SteelStructures.trusses.physical_mass import read_physical_mass

    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    qss = os.environ.get("SS_SIMPLE_U_QSS")
    if qss:
        path = Path(qss)
        QtCore.QDir.addSearchPath("qss", str(path.parent))
        QtWidgets.QApplication.instance().setStyleSheet(path.read_text(encoding="utf-8"))
    checks, errors = [], []
    old_hook = sys.excepthook

    def qt_error(kind, error, trace):
        errors.append("".join(traceback.format_exception(kind, error, trace)))
        (output / "qt_errors.txt").write_text("\n".join(errors), encoding="utf-8")

    sys.excepthook = qt_error

    def check(name, condition):
        if not condition:
            raise AssertionError(name)
        checks.append(name)
        (output / "checks.json").write_text(json.dumps(checks, indent=2), encoding="utf-8")

    def near(a, b):
        return math.isclose(float(a), float(b), rel_tol=1e-8, abs_tol=1e-6)

    def valid(obj):
        return not obj.Shape.isNull() and obj.Shape.isValid() and obj.Shape.Volume > 0

    def drain(panel=None):
        QtWidgets.QApplication.processEvents()
        QtCore.QCoreApplication.sendPostedEvents(None, QtCore.QEvent.DeferredDelete)
        if panel is not None and not panel._closed:
            panel._preview_timer.stop()

    def grab(widget, name):
        drain()
        check("capture " + name, widget.grab().save(str(output / (name + ".png"))))

    def state(obj):
        return dict(profile=str(obj.Profile), category=str(obj.ProfileCategory), series=str(obj.ProfileSeries),
                    insertion=str(obj.Insertion), rotation=obj.Rotation.Value,
                    mode=str(obj.SectionGeometryMode), volume=obj.Shape.Volume,
                    mass=float(obj.TotalMass), linear_mass=float(obj.MassPerMeter), area=float(obj.CatalogArea),
                    axis=str(obj.AxisDefinitionMode), source=obj.AxisSource[0].Name if obj.AxisSource else None,
                    start=list(obj.StartPoint), end=list(obj.EndPoint), matrix=list(obj.Placement.toMatrix().A))

    def equal_state(actual, expected):
        for key, value in expected.items():
            current = actual[key]
            if isinstance(value, float):
                if not near(current, value):
                    return False
            elif isinstance(value, list):
                if not all(near(a, b) for a, b in zip(current, value)):
                    return False
            elif current != value:
                return False
        return True

    def create(controls, start, end, panel=None, source=None):
        controller = MemberController(doc)
        controller.start()
        if source:
            axis = resolve_axis_source(source)
            options = (panel.axis_creation_options(axis.start, axis.end, CreationGeometryMode.SOURCE_AXIS)
                       if panel else controls.creation_options(axis.start, axis.end, source, True, CreationGeometryMode.SOURCE_AXIS))
        else:
            options = panel.creation_options(start) if panel else controls.creation_options(start, end)
        return controller.create(options).member

    doc = App.newDocument("SimpleUStageB")
    doc.UndoMode = 1
    Gui.getMainWindow().resize(1500, 1000)
    try:
        library = ProfileLibrary(CATALOGS_DIR)
        profiles = library.list_profiles(series_id="u-simple-nbr-6355")
        by_id = {p.ref.profile_id: p for p in profiles}
        samples = [by_id[key] for key in ("u-50x25x1.20", "u-150x50x3.00", "u-250x100x6.35", "u-300x100x8.00")]
        check("125 unique normative profiles", len(profiles) == len(by_id) == 125)
        check("125 creation eligible", all(profile_catalog.is_creation_profile(p) for p in profiles))
        check("atypical radius retained", near(samples[2].geometry["ri"], 9.525))
        members = []
        # The native Browser and all nine mini-preview hotspots use current
        # infrastructure; screen hit tests are exercised at nonzero roll.
        for p in samples:
            options = ProfileOptionsWidget(doc)
            options.set_profile_ref(p.ref)
            options.resize(470, 650)
            options.show()
            options.rotation.setValue(37)
            drain()
            references = section_insertion_references(build_section_geometry(p))
            check(p.ref.profile_id + " nine UI choices", options.insertion.count() == len(references) == 9)
            preview = options.orientation_preview
            check(p.ref.profile_id + " schematic family", preview._schematic is not None and len(preview._references) == 9)
            target, scale = preview._layout()
            for reference in preview._references:
                x, y = preview._screen_point(reference.point, target, scale)
                check(p.ref.profile_id + " hotspot inside " + reference.id, preview.rect().contains(QtCore.QPoint(round(x), round(y))))
                QtTest.QTest.mouseClick(preview, QtCore.Qt.LeftButton, pos=QtCore.QPoint(round(x), round(y)))
                check(p.ref.profile_id + " hotspot selection " + reference.id,
                      preview._selected_reference().id == reference.id and options.insertion.currentText() == reference.label)
            grab(options, p.ref.profile_id + "-options")
            for width in (1100, 760):
                browser = ProfileBrowserDialog(mode=ProfileBrowserDialog.SELECT_MODE, initial_profile_ref=p.ref,
                    is_profile_selectable=profile_catalog.is_creation_profile, insertion=references[-1].label)
                browser.resize(width, 850)
                browser.show()
                drain()
                check(p.ref.profile_id + " browser selection " + str(width), browser.selected_profile_ref() == p.ref
                      and "Dobrado Simples" in browser.subtitle.text())
                folded_nodes = [browser.tree.topLevelItem(i) for i in range(browser.tree.topLevelItemCount())
                                if browser.tree.topLevelItem(i).text(0) == "Aço Dobrado"]
                check(p.ref.profile_id + " one folded category " + str(width), len(folded_nodes) == 1
                      and folded_nodes[0].childCount() == 2)
                # ItemIgnoresTransformations requires deviceTransform: scene
                # bounding boxes alone cannot detect overlapping real text.
                view = browser.preview
                labels = [item for item in view.scene().items() if isinstance(item, QtWidgets.QGraphicsTextItem)]
                check(p.ref.profile_id + " four dimension labels " + str(width), len(labels) == 4)
                boxes = [(item.toPlainText(), item.deviceTransform(view.viewportTransform()).mapRect(item.boundingRect()))
                         for item in labels]
                for label_index, (text, rect) in enumerate(boxes):
                    check(p.ref.profile_id + " label in viewport " + str(width) + " " + text,
                          QtCore.QRectF(view.viewport().rect()).contains(rect))
                    for other_text, other_rect in boxes[label_index + 1:]:
                        check(p.ref.profile_id + " labels separated " + str(width) + " " + text + "/" + other_text,
                              not rect.intersects(other_rect))
                grab(browser, p.ref.profile_id + "-browser-" + str(width))
                source_texts = [label.text() for label in browser.tabs.widget(2).findChildren(QtWidgets.QLabel)]
                check(p.ref.profile_id + " normative source A.2 " + str(width), source_texts.count("A.2") == 2
                      and "ABNT NBR 6355" in source_texts and "2012" in source_texts)
                if width == 1100:
                    browser.tabs.setCurrentIndex(1)
                    drain()
                    grab(browser, p.ref.profile_id + "-properties")
                    browser.tabs.setCurrentIndex(2)
                    drain()
                    grab(browser, p.ref.profile_id + "-source")
                browser.close()
                browser.deleteLater()
            options.close()
            options.deleteLater()

        # Four axes and both representations, using the standard creator.
        directions = ((1000, 0, 0), (0, 1000, 0), (0, 0, 1000), (300, 400, 866.0254037844386))
        for sample_index, p in enumerate(samples):
            for direction_index, direction in enumerate(directions):
                for detailed in (True, False):
                    controls = ProfileOptionsWidget(doc)
                    controls.set_profile_ref(p.ref)
                    controls.rotation.setValue(37)
                    controls.insertion.setCurrentText("Ponta superior da mesa")
                    controls.generate_radii.setChecked(detailed)
                    start = App.Vector(sample_index * 5000, direction_index * 2000, 0)
                    end = start.add(App.Vector(*direction))
                    obj = create(controls, start, end)
                    members.append(obj)
                    expected_area = build_section_geometry(p, controls.section_geometry_mode).area
                    check(obj.Name + " generic axis/area/mass", valid(obj) and near(obj.Shape.Volume, expected_area * 1000)
                          and near(obj.Length.Value, 1000) and near(obj.Rotation.Value, 37)
                          and near(obj.MassPerMeter, p.physical_properties.mass_per_length_kg_m)
                          and near(obj.CatalogArea, p.physical_properties.area_mm2 / 100)
                          and near(obj.TotalMass, obj.MassPerMeter)
                          and str(obj.Insertion) == "Ponta superior da mesa")
                    check(obj.Name + " actual longitudinal orientation",
                          obj.Placement.Rotation.multVec(App.Vector(0, 0, 1)).sub(App.Vector(*direction).normalize()).Length < 1e-8)
                    controls.close()
                    controls.deleteLater()

        # Persist every reference in both member and pillar consumers; the
        # family-specific labels must survive rather than falling to Centroide.
        p = samples[2]
        references = section_insertion_references(build_section_geometry(p))
        for element_type in ("Membro", "Pilar"):
            for index, reference in enumerate(references):
                panel = ColumnTaskPanel(doc) if element_type == "Pilar" else None
                controls = panel.profile_options if panel else ProfileOptionsWidget(doc)
                controls.set_profile_ref(p.ref)
                controls.insertion.setCurrentText(reference.label)
                controls.rotation.setValue(90 if index % 2 else 37)
                start = App.Vector(23000 + index * 400, 0 if panel else 1500, 0)
                if panel:
                    panel.height.setValue(1000)
                obj = create(controls, start, start.add(App.Vector(1000, 0, 0)), panel)
                members.append(obj)
                check(obj.Name + " insertion/type", valid(obj) and str(obj.Insertion) == reference.label
                      and str(obj.ElementType) == element_type)
                settings = controls.creation_settings()
                fresh = ProfileOptionsWidget(doc)
                fresh.apply_creation_settings(settings)
                check(obj.Name + " reusable settings roundtrip", fresh.insertion.currentText() == reference.label)
                fresh.close()
                fresh.deleteLater()
                (panel or controls).close()
                (panel or controls).deleteLater()

        linked = []
        for element_type in ("Membro", "Pilar"):
            line = Draft.make_line(App.Vector(0, 23000, 0), App.Vector(300, 23400, 866.0254037844386))
            doc.recompute()
            source = (line, ["Edge1"])
            panel = ColumnTaskPanel(doc, axis_source=source) if element_type == "Pilar" else None
            controls = panel.profile_options if panel else ProfileOptionsWidget(doc)
            controls.set_profile_ref(samples[0].ref)
            controls.insertion.setCurrentText("Face externa da alma")
            controls.rotation.setValue(123)
            if panel:
                panel.axis_source_controls.keep_link.setChecked(True)
            obj = create(controls, None, None, panel, source)
            members.append(obj)
            linked.append(obj)
            check(obj.Name + " linked Draft creation", valid(obj) and obj.AxisSource[0] == line and str(obj.AxisDefinitionMode) == "Linked"
                  and str(obj.ElementType) == element_type and not line.ViewObject.Visibility)
            line.End = line.End.add(App.Vector(20, 10, 30))
            obj.StartExtension, obj.EndExtension = 10, 15
            doc.recompute()
            axis = resolve_axis_source(source)
            check(obj.Name + " Draft edit recompute", valid(obj) and obj.EndPoint.sub(axis.end).Length < 1e-6)
            (panel or controls).close()
            (panel or controls).deleteLater()

        # Real native Draft SourceAxis preview reacts to profile and roll,
        # then cancellation removes the preview and callback/session objects.
        before_names = tuple(obj.Name for obj in doc.Objects)
        tool = StructuralMemberDraftTool()
        try:
            tool.Activated(axis_source=linked[0].AxisSource)
            for p in samples:
                tool.profile_options.set_profile_ref(p.ref)
                tool.profile_options.insertion.setCurrentText("Ponta superior da mesa")
                tool.profile_options.rotation.setValue(0)
                drain()
                initial = tool.obj.Shape.CenterOfMass
                tool.profile_options.rotation.setValue(90)
                drain()
                check(p.ref.profile_id + " native Draft preview roll", valid(tool.obj) and tool.obj.Shape.CenterOfMass.sub(initial).Length > 1)
            grab(tool.profile_options, "native-draft-options")
            grab(Gui.getMainWindow(), "native-draft-task-view")
        finally:
            if tool.is_active():
                tool._terminate_native_session()
            drain()
        check("native Draft cancel cleanup", before_names == tuple(obj.Name for obj in doc.Objects))

        original = members[-1]
        doc.openTransaction("Copy simple U validation")
        copied = Draft.move([original], App.Vector(0, 1500, 0), copy=True)
        doc.recompute()
        doc.commitTransaction()
        check("Draft copy preserves profile insertion roll", valid(copied) and copied is not original
              and str(copied.Insertion) == str(original.Insertion) and str(copied.Profile) == str(original.Profile)
              and near(copied.Rotation.Value, original.Rotation.Value))
        copied_name = copied.Name
        doc.undo()
        doc.recompute()
        check("member copy Undo", doc.getObject(copied_name) is None and valid(original))
        doc.redo()
        doc.recompute()
        copied = doc.getObject(copied_name)
        check("member copy Redo", copied is not None and valid(copied))
        members.append(copied)
        before_edit = state(original)
        doc.openTransaction("Edit simple U insertion validation")
        original.Insertion, original.Rotation = "Canto externo superior", 270
        original.SectionGeometryMode = "Simplified"
        doc.recompute()
        doc.commitTransaction()
        after_edit = state(original)
        doc.undo()
        doc.recompute()
        check("member edit Undo", equal_state(state(original), before_edit))
        doc.redo()
        doc.recompute()
        check("member edit Redo", equal_state(state(original), after_edit))

        # Existing role-dialog translation, assembly presets and shared modal
        # editor are used, without modifying any topology or fitting behavior.
        value = truss.default_config()
        value.update(span=6000., end=[6000., 0., 0.], height=1800., panel_count=4)
        for index, (role, spec) in enumerate(value["role_specs"].items()):
            options = ProfileOptionsWidget(doc)
            options.set_profile_ref(samples[index % len(samples)].ref)
            options.insertion.setCurrentText("Face externa da alma" if role == "VERTICAL" else "Centroide")
            options.rotation.setValue(spec["rotation"])
            options.generate_radii.setChecked(index % 2 == 0)
            value["role_specs"][role] = role_spec_from_options(spec, options)
            options.close()
            options.deleteLater()
        value["role_specs"]["TOP_CHORD"] = configure_assembly(value["role_specs"]["TOP_CHORD"], "DoubleChannelInward", 240.)
        value["role_specs"]["BOTTOM_CHORD"] = configure_assembly(value["role_specs"]["BOTTOM_CHORD"], "DoubleChannelOutward", 240.)
        owner = truss.apply_truss(doc, value)
        physical = read_physical_mass(owner)
        check("truss all simple U solids", owner.GeneratedMembers and all(valid(child)
              and str(child.ProfileSeries) == str(members[0].ProfileSeries) for child in owner.GeneratedMembers))
        check("truss double channels and single roles", {str(child.ComponentKey) for child in owner.GeneratedMembers} >= {"A", "B"})
        check("truss physical mass sum", physical.available and near(physical.volume_mm3, math.fsum(child.Shape.Volume for child in owner.GeneratedMembers))
              and near(physical.mass_kg, physical.volume_mm3 * 7.85e-6))
        check("truss mixed geometric representations", {str(child.SectionGeometryMode) for child in owner.GeneratedMembers}
              == {"Detailed", "Simplified"})
        for child in owner.GeneratedMembers:
            definition = profile_catalog.get(str(child.Profile)).definition
            check(child.Name + " truss normative properties retained", near(child.CatalogArea, definition.physical_properties.area_mm2 / 100)
                  and near(child.MassPerMeter, definition.physical_properties.mass_per_length_kg_m))
        for obj in members:
            obj.ViewObject.Visibility = False
        Gui.activeDocument().activeView().viewAxonometric()
        Gui.activeDocument().activeView().fitAll()
        Gui.updateGui()
        # Coin's offscreen renderer is necessary for a hidden GUI process:
        # grabbing the main window does not capture an unexposed GL viewport.
        Gui.activeDocument().activeView().saveImage(str(output / "simple-u-truss-3d.png"), 1400, 900, "White")
        check("native offscreen truss render", (output / "simple-u-truss-3d.png").is_file())
        grab(Gui.getMainWindow(), "simple-u-truss-axonometric")
        panel = controllers.open_truss_panel(doc, owner)
        drain(panel)
        check("truss panel shares session", panel.session is panel.controller.session and panel._valid)
        saved_specs = deepcopy(panel.session.config["role_specs"])
        for reference in references:
            spec = deepcopy(saved_specs["VERTICAL"])
            spec["insertion"] = reference.id
            dialog = _RoleProfileDialog(doc, reference.id, spec)
            check("role insertion identity " + reference.id, role_spec_from_options(spec, dialog.options)["insertion"] == reference.id)
            dialog.close()
            dialog.deleteLater()
        for role, spec in saved_specs.items():
            dialog = _RoleProfileDialog(doc, role, spec)
            roundtrip = role_spec_from_options(spec, dialog.options)
            (output / ("role-" + role + ".json")).write_text(json.dumps(dict(before=spec, after=roundtrip), indent=2), encoding="utf-8")
            # QColor.fromRgbF is float32 on this Qt build. Structural state
            # remains exact; colors allow that representation precision only.
            check("role roundtrip " + role,
                  {key: val for key, val in roundtrip.items() if key != "color"}
                  == {key: val for key, val in spec.items() if key != "color"}
                  and all(abs(a - b) < 1e-6 for a, b in zip(roundtrip["color"], spec["color"])))
            if role == "TOP_CHORD":
                dialog.show()
                grab(dialog, "truss-role-profile")
            dialog.close()
            dialog.deleteLater()
        panel.height.setValue(1900.)
        drain(panel)
        # Dispatch the real Task View Apply button.
        box = panel.form.window().findChild(QtWidgets.QDialogButtonBox)
        button = box.button(QtWidgets.QDialogButtonBox.Apply) if box else None
        check("native Task View Apply exists", button is not None)
        button.click()
        drain(panel)
        check("TaskPanel Apply keeps owner/specs", owner.Height.Value == 1900. and not panel.session.closed
              and panel.session.config["role_specs"] == saved_specs)
        grab(Gui.getMainWindow(), "truss-task-view")
        grab(panel.form, "truss-task-panel")

        def modal(label, action):
            failures, held = [], []

            def callback():
                editor = panel._topology_editor
                try:
                    held.append(editor)
                    check(label + " modal/session", editor.isModal() and editor.panel.session is panel.session)
                    action(editor)
                except Exception:
                    failures.append(traceback.format_exc())
                finally:
                    if editor is not None and shiboken6.isValid(editor) and editor.isVisible():
                        editor.reject()

            QtCore.QTimer.singleShot(0, callback)
            panel.editor_button.click()
            drain(panel)
            if failures:
                raise AssertionError("\n".join(failures))
            check(label + " editor closed/task retained", held and all(not shiboken6.isValid(widget) for widget in held)
                  and panel._topology_editor is None and not panel._closed)

        def apply_cancel(editor):
            editor.fields.controls["height"].setValue(2000.)
            editor.apply_button.click()
            drain(panel)
            check("editor Apply simple U", owner.Height.Value == 2000. and read_physical_mass(owner).available)
            grab(editor, "truss-editor")
            editor.fields.controls["height"].setValue(2100.)
            editor.cancel_button.click()

        modal("apply_cancel", apply_cancel)
        check("editor cancel keeps applied height/specs", owner.Height.Value == 2000.
              and panel.session.config["height"] == 2000. and panel.session.config["role_specs"] == saved_specs)

        def accept(editor):
            editor.fields.controls["height"].setValue(2200.)
            editor.ok_button.click()

        modal("ok", accept)
        check("editor OK applies", owner.Height.Value == 2200. and panel.session.config["role_specs"] == saved_specs)
        panel.height.setValue(2300.)
        drain(panel)
        panel.reject()
        check("TaskPanel cancel keeps last Apply", owner.Height.Value == 2200.)
        doc.undo()
        doc.recompute()
        check("truss Undo", owner.Height.Value == 2000. and read_physical_mass(owner).available)
        doc.redo()
        doc.recompute()
        check("truss Redo", owner.Height.Value == 2200. and read_physical_mass(owner).available)
        panel = controllers.open_truss_panel(doc, owner)
        drain(panel)
        check("TaskPanel OK clean", panel.accept() and panel.session.closed)
        doc.openTransaction("Copy simple U truss validation")
        truss_copy = Draft.move([owner], App.Vector(0, 12000, 0), copy=True)
        doc.recompute()
        doc.commitTransaction()
        copied_owner_name = truss_copy.Name
        copy_mass = read_physical_mass(truss_copy)
        check("truss native Draft copy independent mass", copy_mass.available and near(copy_mass.mass_kg, read_physical_mass(owner).mass_kg)
              and not {obj.Name for obj in truss_copy.GeneratedMembers}.intersection(obj.Name for obj in owner.GeneratedMembers)
              and truss_copy.RoleSpecs == owner.RoleSpecs)
        doc.undo()
        doc.recompute()
        check("truss copy Undo", doc.getObject(copied_owner_name) is None and read_physical_mass(owner).available)
        doc.redo()
        doc.recompute()
        truss_copy = doc.getObject(copied_owner_name)
        check("truss copy Redo", read_physical_mass(truss_copy).available
              and near(read_physical_mass(truss_copy).mass_kg, copy_mass.mass_kg))

        # These released family controls exercise the unchanged member pipeline
        # and the same FCStd restoration alongside the new simple-U objects.
        for series in ("w", "hp", "u", "ue-nbr-6355", "l", "shs", "rhs", "chs"):
            available = [item for item in library.list_profiles(series_id=series)
                         if profile_catalog.is_creation_profile(item)
                         and getattr(item, "geometry_status", "released") != "pending_technical_review"]
            if not available and series in ("ue-nbr-6355", "l"):
                # Series identities are not inferred from their localized label.
                available = [item for item in library.list_profiles()
                             if item.geometry_variant == ("stiffened_u" if series == "ue-nbr-6355" else "equal_leg")
                             and profile_catalog.is_creation_profile(item)]
            check("existing family available " + series, bool(available))
            controls = ProfileOptionsWidget(doc)
            controls.set_profile_ref(available[0].ref)
            controls.rotation.setValue(37)
            controls.insertion.setCurrentIndex(controls.insertion.count() - 1)
            start = App.Vector(0, 30000 + len(members) * 500, 0)
            obj = create(controls, start, start.add(App.Vector(0, 0, 1000)))
            members.append(obj)
            (output / ("family-" + series + ".json")).write_text(json.dumps(dict(
                selected=available[0].designation, selected_ref=asdict(available[0].ref),
                actual=str(obj.Profile), state=list(obj.State), valid=valid(obj),
                generation_status=getattr(obj, "GenerationStatus", None)), indent=2), encoding="utf-8")
            check("existing family native create " + series, valid(obj)
                  and profile_catalog.ref_for_designation(str(obj.Profile)) == available[0].ref)
            controls.close()
            controls.deleteLater()

        # Restoration compares all family-specific insertion values and actual
        # placements, not only the Part shapes persisted in Stage A.
        expected = {obj.Name: state(obj) for obj in members}
        linked_name = linked[0].Name
        owner_name, owner_state, owner_mass = owner.Name, owner.AppliedState, read_physical_mass(owner).mass_kg
        path = output / "simple_u_stage_b.FCStd"
        doc.recompute()
        doc.saveAs(str(path))
        App.closeDocument(doc.Name)
        doc = App.openDocument(str(path))
        doc.recompute()
        for name, previous in expected.items():
            obj = doc.getObject(name)
            check("FeaturePython FCStd roundtrip " + name, valid(obj) and equal_state(state(obj), previous))
        owner = doc.getObject(owner_name)
        check("truss FCStd roundtrip", owner.AppliedState == owner_state and near(read_physical_mass(owner).mass_kg, owner_mass))
        truss_copy = doc.getObject(copied_owner_name)
        check("copied truss FCStd roundtrip", truss_copy.RoleSpecs == owner.RoleSpecs
              and near(read_physical_mass(truss_copy).mass_kg, owner_mass))
        panel = controllers.open_truss_panel(doc, owner)
        drain(panel)
        check("restored truss session refs", panel._valid and panel.session.config["role_specs"] == saved_specs)
        panel.reject()
        # Check restored associative editing as well as the initial save.
        obj = doc.getObject(linked_name)
        obj.AxisSource[0].End = obj.AxisSource[0].End.add(App.Vector(0, 0, 50))
        doc.recompute()
        check("restored Draft linked edit", valid(obj) and obj.EndPoint.sub(resolve_axis_source(obj.AxisSource).end).Length < 1e-6)
        # Preexisting FCStd is opened from a disposable copy. Never save over
        # the committed/user fixture, even when restoration marks it touched.
        legacy_source = Path(__file__).resolve().parent / "copiatreliça.FCStd"
        if legacy_source.is_file():
            legacy_copy = output / "preexisting_truss_compatibility.FCStd"
            shutil.copy2(legacy_source, legacy_copy)
            legacy = App.openDocument(str(legacy_copy))
            legacy.recompute()
            historical = [item for item in legacy.Objects if "Profile" in item.PropertiesList]
            check("preexisting FCStd contains structural members", bool(historical))
            for item in historical:
                check("preexisting FCStd valid " + item.Name, valid(item)
                      and profile_catalog.get(str(item.Profile)) is not None)
            App.closeDocument(legacy.Name)
            App.setActiveDocument(doc.Name)
        check("no Qt callback exceptions", not errors)
        return dict(ok=True, version=App.Version()[:3], theme=os.environ.get("SS_SIMPLE_U_THEME"),
                    checks=checks, member_count=len(members), profile_count=len(profiles), file=str(path),
                    note="Automated real Qt/FreeCAD gate; human visual approval remains pending.")
    finally:
        sys.excepthook = old_hook


if os.environ.get("SS_SIMPLE_U_ROOT"):
    import FreeCAD as App
    from PySide import QtCore, QtWidgets
    root = Path(os.environ["SS_SIMPLE_U_ROOT"])
    out = Path(os.environ["SS_SIMPLE_U_OUT"])
    sys.path.insert(0, str(root))
    import freecad
    freecad.__path__.insert(0, str(root / "freecad"))

    def launch():
        try:
            result = run(out)
        except Exception:
            result = dict(ok=False, error=traceback.format_exc())
            App.Console.PrintError(result["error"])
        (out / "result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        for name in tuple(App.listDocuments()):
            App.closeDocument(name)
        QtCore.QTimer.singleShot(0, QtWidgets.QApplication.quit)

    QtCore.QTimer.singleShot(500, launch)
