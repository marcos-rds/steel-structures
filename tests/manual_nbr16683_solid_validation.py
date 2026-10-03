# SPDX-License-Identifier: LGPL-2.1-or-later
"""Run run() in FreeCAD 1.1.3; creates only a temporary validation document.

Use a fresh workbench session after updating its Python files. Optionally pass
an old Stage-A FCStd to check restoration without saving over the original.
"""

import json
import math
from pathlib import Path
import shutil
import tempfile


def run(output_directory=None, legacy_path=None):
    import FreeCAD as App
    import FreeCADGui as Gui
    import Draft
    import Part
    from PySide import QtWidgets, QtGui
    from freecad.SteelStructures import profile_catalog
    from freecad.SteelStructures.profiles import ProfileLibrary
    from freecad.SteelStructures.paths import CATALOGS_DIR
    from freecad.SteelStructures.member_axis_source import resolve_axis_source
    from freecad.SteelStructures.interactive.member_controller import (
        MemberController, CreationGeometryMode,
    )
    from freecad.SteelStructures.interactive.member_adjustment_controller import MemberAdjustmentController
    from freecad.SteelStructures.interactive.profile_browser import ProfileBrowserDialog
    from freecad.SteelStructures.interactive.profile_options_widget import ProfileOptionsWidget
    from freecad.SteelStructures.interactive.column_task_panel import ColumnTaskPanel
    from freecad.SteelStructures.interactive.draft_member_tool import StructuralMemberDraftTool

    directory = Path(output_directory) if output_directory else Path(tempfile.mkdtemp(prefix="ss-nbr16683-"))
    directory.mkdir(parents=True, exist_ok=True)
    doc = App.newDocument("SSNBR16683Validation")
    doc.Label = "Aço Maciço — ABNT NBR 16683:2018 (correção 2020)"
    doc.UndoMode = 1
    report = {"version": App.Version()[:3], "checks": [], "directory": str(directory)}

    def check(name, condition):
        if not condition:
            raise AssertionError(name)
        report["checks"].append(name)

    def near(a, b):
        return math.isclose(float(a), float(b), rel_tol=1e-8, abs_tol=1e-6)

    def valid(obj):
        return not obj.Shape.isNull() and obj.Shape.isValid() and obj.Shape.Volume > 0

    def same_point(a, b):
        return a.sub(b).Length < 1e-6

    library = ProfileLibrary(CATALOGS_DIR)
    profiles = library.list_profiles(category_id="solid-steel")
    chosen = [next(p for p in profiles if p.ref.profile_id == key) for key in (
        "round-bar-20-64", "square-bar-20-64", "flat-bar-50-8x6-35")]
    check("164 normative profiles", len(profiles) == 164)
    check("no public development fixtures", all(p.catalog.source.source_type == "normative" for p in profiles))
    check("three solid series", profile_catalog.series_for_category("Aço Maciço") == [
        "Barra Redonda", "Barra Quadrada", "Barra Chata"])
    objects, linked = [], []
    for index, p in enumerate(chosen):
        for element_type in ("Membro", "Pilar"):
            start = App.Vector(index * 200, 0 if element_type == "Membro" else 200, 0)
            options = ProfileOptionsWidget(doc) if element_type == "Membro" else ColumnTaskPanel(doc)
            controls = options if element_type == "Membro" else options.profile_options
            controls.set_profile_ref(p.ref)
            controls.insertion.setCurrentText("Face superior")
            controls.rotation.setValue(90)
            if element_type == "Membro":
                creation = controls.creation_options(start, start.add(App.Vector(0, 0, 1000)))
            else:
                options.height.setValue(1000)
                creation = options.creation_options(start)
            controller = MemberController(doc)
            controller.start()
            obj = controller.create(creation).member
            objects.append(obj)
            check(element_type + p.ref.profile_id, valid(obj) and str(obj.Profile) == p.designation
                  and str(obj.ElementType) == element_type and str(obj.AxisDefinitionMode) == "Independent")
            check(obj.Name + " technical area/mass", near(obj.CatalogArea, p.physical_properties.area_mm2 / 100)
                  and near(obj.MassPerMeter, p.physical_properties.mass_per_length_kg_m)
                  and near(obj.TotalMass, obj.MassPerMeter))
            check(obj.Name + " local frame/insertion/roll", near(obj.Length.Value, 1000)
                  and str(obj.Insertion) == "Face superior" and near(obj.Rotation.Value, 90))
            check(obj.Name + " radii hidden/rotation available", controls.generate_radii.isHidden()
                  and controls.rotation.isEnabled())
            options.close()

            # One linked Member and Pillar per family, created through their panels.
            line = Draft.make_line(start.add(App.Vector(0, 500, 0)), start.add(App.Vector(0, 500, 1000)))
            doc.recompute()
            source = (line, ["Edge1"])
            axis = resolve_axis_source(source)
            panel = ColumnTaskPanel(doc, axis_source=source) if element_type == "Pilar" else ProfileOptionsWidget(doc)
            controls = panel.profile_options if element_type == "Pilar" else panel
            controls.set_profile_ref(p.ref)
            if element_type == "Pilar":
                panel.axis_source_controls.keep_link.setChecked(True)
                creation = panel.axis_creation_options(axis.start, axis.end, CreationGeometryMode.SOURCE_AXIS)
            else:
                creation = controls.creation_options(axis.start, axis.end, source, True, CreationGeometryMode.SOURCE_AXIS)
            controller = MemberController(doc)
            controller.start()
            obj = controller.create(creation).member
            linked.append(obj)
            objects.append(obj)
            check(obj.Name + " linked source ownership", valid(obj) and obj.AxisSource[0] == line
                  and line in doc.Objects and not line.ViewObject.Visibility
                  and str(obj.AxisDefinitionMode) == "Linked" and str(obj.ElementType) == element_type)
            obj.StartExtension, obj.EndExtension = 10, 15
            line.Start = line.Start.add(App.Vector(5, 10, 20))
            line.End = line.End.add(App.Vector(5, 10, 120))
            doc.recompute()
            axis = resolve_axis_source(source)
            check(obj.Name + " linked recompute/extensions", valid(obj) and same_point(obj.StartPoint, axis.start)
                  and same_point(obj.EndPoint, axis.end) and near(obj.StartExtension.Value, 10)
                  and near(obj.EndExtension.Value, 15) and near(obj.Shape.Volume, p.physical_properties.area_mm2 * 1125))
            panel.close()

        for reopen in range(2):
            browser = ProfileBrowserDialog(initial_profile_ref=p.ref)
            browser.show()
            QtWidgets.QApplication.processEvents()
            check(p.ref.profile_id + " browser reopen " + str(reopen), browser.selected_profile_ref() == p.ref
                  and "ABNT NBR 16683" in browser.subtitle.text() and "fixture" not in browser.subtitle.text())
            if not reopen:
                browser.grab().save(str(directory / (p.ref.profile_id + "-browser.png")))
            browser.close()

    flat = linked[4]
    flat.Rotation = 0
    doc.recompute()
    bounds0 = flat.Shape.BoundBox
    flat.Rotation = 90
    doc.recompute()
    check("flat roll 0/90 preserves B/t", near(bounds0.XLength, 50.8) and near(bounds0.YLength, 6.35)
          and near(flat.Shape.BoundBox.XLength, 6.35) and near(flat.Shape.BoundBox.YLength, 50.8))
    flat.Rotation = 0
    doc.recompute()

    for obj in (linked[0], flat):
        controller = MemberAdjustmentController(doc, obj)
        planes = []
        for slot, station, gap in (("Start", 100, 2), ("End", 900, 3)):
            plane = doc.addObject("Part::Feature", "NormativeCutReference")
            plane.Shape = Part.makePlane(300, 300, obj.StartPoint.add(App.Vector(0, 0, station)), App.Vector(0, 0, 1))
            plane.ViewObject.Visibility = False
            controller.apply(controller.validate(geometry_mode="PlaneCut", end_choice=slot, gap=gap,
                keep_reference=True, reference=(plane, ["Face1"])))
            planes.append(plane)
        area = profile_catalog.get(str(obj.Profile)).definition.physical_properties.area_mm2
        check(obj.Name + " orthogonal dual cut", valid(obj) and near(obj.Shape.Volume, area * 795))
        planes[1].Shape = Part.makePlane(300, 300, obj.StartPoint.add(App.Vector(0, 0, 900)), App.Vector(0.3, 0, 1))
        obj.AxisSource[0].End = obj.AxisSource[0].End.add(App.Vector(20, 0, 100))
        doc.recompute()
        check(obj.Name + " oblique linked dual cut/gaps", valid(obj) and obj.StartAdjustmentReference[0] == planes[0]
              and obj.EndAdjustmentReference[0] == planes[1] and near(obj.StartAdjustmentGap.Value, 2)
              and near(obj.EndAdjustmentGap.Value, 3))
        check(obj.Name + " cut mass uses published linear mass", near(obj.TotalMass,
              obj.Shape.Volume / area / 1000 * obj.MassPerMeter))
    square = linked[2]
    square.EndAdjustmentMode = "Fixed"
    square.EndAdjustmentGeometryMode = "LengthLimit"
    square.EndFixedReferenceOffset = 50
    square.EndAdjustmentGap = 4
    doc.recompute()
    check("square LengthLimit", valid(square) and near(square.AdjustedLength.Value, square.Length.Value + 10 - 54))

    # Native SourceAxis task-panel signals: profile, insertion, rotation, color.
    names_before = [obj.Name for obj in doc.Objects]
    tool = StructuralMemberDraftTool()
    try:
        tool.Activated(axis_source=linked[1].AxisSource)
        for p in chosen:
            controls = tool.profile_options
            controls.set_profile_ref(p.ref)
            controls.insertion.setCurrentText("Face superior")
            controls.rotation.setValue(0)
            QtWidgets.QApplication.processEvents()
            center = tool.obj.Shape.CenterOfMass
            controls.rotation.setValue(90)
            controls._apply_color(QtGui.QColor(51, 153, 230))
            QtWidgets.QApplication.processEvents()
            check(p.ref.profile_id + " native SourceAxis preview", valid(tool.obj)
                  and center.sub(tool.obj.Shape.CenterOfMass).Length > 1
                  and all(near(a, b) for a, b in zip(tool.obj.ViewObject.ShapeColor[:3], (0.2, 0.6, 230 / 255))))
    finally:
        if tool.is_active():
            tool._terminate_native_session()
        QtWidgets.QApplication.processEvents()
    check("native cancellation cleanup", [obj.Name for obj in doc.Objects] == names_before)

    def state(obj):
        return (str(obj.Profile), str(obj.ProfileCategory), str(obj.ProfileSeries), str(obj.Insertion),
                obj.Rotation.Value, obj.MassPerMeter, obj.CatalogArea, obj.TotalMass, obj.Shape.Volume,
                str(obj.AxisDefinitionMode), obj.AxisSource[0].Name if obj.AxisSource else None)

    before = {obj.Name: state(obj) for obj in objects}
    path = directory / "NBR16683Validation.FCStd"
    doc.recompute()
    doc.saveAs(str(path))
    App.closeDocument(doc.Name)
    doc = App.openDocument(str(path))
    doc.recompute()
    for name, expected in before.items():
        obj = doc.getObject(name)
        check("persistence " + name, valid(obj) and all(near(a, b) if isinstance(a, float) else a == b
              for a, b in zip(state(obj), expected)))
        if obj.AxisSource:
            obj.AxisSource[0].End = obj.AxisSource[0].End.add(App.Vector(0, 0, 10))
            doc.recompute()
            check("restored AxisSource " + name, valid(obj) and same_point(obj.EndPoint, resolve_axis_source(obj.AxisSource).end))

    if legacy_path:
        copy = directory / "StageACompatibility.FCStd"
        shutil.copy2(legacy_path, copy)
        legacy = App.openDocument(str(copy))
        legacy.recompute()
        historical = [obj for obj in legacy.Objects if "Profile" in obj.PropertiesList]
        check("legacy document has solid members", len(historical) >= 3)
        for obj in historical:
            p = profile_catalog.get(str(obj.Profile)).definition
            check("legacy restoration " + obj.Name, valid(obj) and p.availability_status == "development_fixture"
                  and near(obj.MassPerMeter, p.physical_properties.mass_per_length_kg_m))
        App.closeDocument(legacy.Name)
    App.setActiveDocument(doc.Name)
    Gui.activeDocument().activeView().viewAxonometric()
    Gui.activeDocument().activeView().fitAll()
    report.update(document=doc.Name, file=str(path), count=len(report["checks"]))
    (directory / "validation-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(report)
    return report


if __name__ == "__main__":
    run()
