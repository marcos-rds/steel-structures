"""Real FreeCAD 1.1.3 Stage-A validation; run run() from its Python console.

Creates a new temporary document and FCStd, never edits an existing document.
Leaves the reopened validation document available for visual inspection.
"""

from dataclasses import replace
import math
from pathlib import Path
import tempfile


def run():
    import FreeCAD as App
    import FreeCADGui as Gui
    import Draft
    import Part
    from PySide import QtWidgets, QtGui
    from freecad.SteelStructures import profile_catalog
    from freecad.SteelStructures.member import create_member
    from freecad.SteelStructures.profiles import build_section_geometry, ProfileLibrary
    from freecad.SteelStructures.profiles.presentation import profile_preview_dimension_rows
    from freecad.SteelStructures.paths import CATALOGS_DIR
    from freecad.SteelStructures.interactive.member_controller import (
        MemberController, MemberCreationOptions, CreationGeometryMode,
    )
    from freecad.SteelStructures.interactive.member_adjustment_controller import MemberAdjustmentController
    from freecad.SteelStructures.interactive.member_creation_preview import PreviewState, update_member_preview
    from freecad.SteelStructures.interactive.profile_browser import ProfileBrowserDialog
    from freecad.SteelStructures.interactive.profile_options_widget import ProfileOptionsWidget
    from freecad.SteelStructures.interactive.profile_browser_preview import SectionPreviewView
    from freecad.SteelStructures.interactive.draft_member_tool import StructuralMemberDraftTool
    from freecad.SteelStructures.member_axis_source import resolve_axis_source

    directory = Path(tempfile.mkdtemp(prefix="steelstructures-solid-a-"))
    doc = App.newDocument("SSSolidStageAValidation")
    doc.Label = "Aço Maciço — validação Etapa A (fixtures)"
    doc.UndoMode = 1
    report = {"version": App.Version()[:3], "directory": str(directory), "checks": []}

    def check(name, condition):
        if not condition:
            raise AssertionError(name)
        report["checks"].append(name)

    def near(a, b):
        return math.isclose(float(a), float(b), abs_tol=1e-6, rel_tol=1e-8)

    def point_equal(a, b):
        return a.sub(b).Length < 1e-6

    def valid(obj):
        return not obj.Shape.isNull() and obj.Shape.isValid() and obj.Shape.Volume > 0

    profiles = ProfileLibrary(CATALOGS_DIR).list_profiles(category_id="solid-steel")
    by_id = {p.ref.profile_id: p for p in profiles}
    chosen = [by_id[key] for key in ("round-bar-20", "square-bar-20", "flat-bar-50x6-35")]
    check("six development fixtures", len(profiles) == 6)
    created, linked = [], []
    for index, p in enumerate(profiles):
        start = App.Vector(150 * index, 0, 0)
        end = start.add(App.Vector(0, 0, 1000))
        obj = create_member(doc, start, end, p.designation)
        created.append(obj)
        check(p.ref.profile_id + " valid member", valid(obj) and obj.TypeId == "Part::FeaturePython")
        area = p.physical_properties.area_mm2
        check(p.ref.profile_id + " nominal area", near(obj.CatalogArea, area / 100))
        check(p.ref.profile_id + " volume and mass", near(obj.Shape.Volume, area * 1000)
              and near(obj.MassPerMeter, area * 0.00785) and near(obj.TotalMass, area * 0.00785))
        obj.SectionGeometryMode = "Simplified"
        doc.recompute()
        check(p.ref.profile_id + " mode equivalence", valid(obj) and near(obj.Shape.Volume, area * 1000))
        obj.StartExtension, obj.EndExtension = 10, 15
        doc.recompute()
        check(p.ref.profile_id + " extensions", near(obj.Shape.Volume, area * 1025)
              and near(obj.Length.Value, 1000))

    flat = created[4]
    bounds0 = flat.Shape.BoundBox
    properties_before = dict(by_id["flat-bar-50x6-35"].section_properties)
    flat.Rotation = 90
    doc.recompute()
    bounds90 = flat.Shape.BoundBox
    check("flat 0/90 bounds", near(bounds0.XLength, 50) and near(bounds0.YLength, 6.35)
          and near(bounds90.XLength, 6.35) and near(bounds90.YLength, 50))
    check("local properties independent from roll", dict(profile_catalog.get(str(flat.Profile)).definition.section_properties) == properties_before)
    flat.Insertion = "Canto superior direito"
    doc.recompute()
    check("flat eccentric insertion", valid(flat))
    round_bar = created[0]
    round_bar.Insertion = "Face superior"
    doc.recompute()
    center0 = round_bar.Shape.CenterOfMass
    round_bar.Rotation = 90
    doc.recompute()
    check("round eccentric roll moves physical center", center0.sub(round_bar.Shape.CenterOfMass).Length > 1)

    # X/Y/Z and inclined nominal axes use the unchanged member pipeline.
    orient = created[2]
    for direction in (App.Vector(1000, 0, 0), App.Vector(0, 1000, 0),
                      App.Vector(0, 0, 1000), App.Vector(300, 400, 500)):
        orient.EndPoint = orient.StartPoint.add(direction)
        doc.recompute()
        check("orientation " + str(tuple(direction)), valid(orient) and near(orient.Length.Value, direction.Length))

    for index, p in enumerate(chosen):
        start = App.Vector(index * 200, 250, 0)
        line = Draft.make_line(start, start.add(App.Vector(0, 0, 1000)))
        doc.recompute()
        link = (line, ["Edge1"])
        axis = resolve_axis_source(link)
        controller = MemberController(doc)
        controller.start()
        obj = controller.create(MemberCreationOptions(
            axis.start, axis.end, p.designation, "Membro", "Centroide", 0,
            (0.8, 0.35, 0.1), "Linked " + p.designation, link, True,
            CreationGeometryMode.SOURCE_AXIS,
        )).member
        linked.append(obj)
        check(p.ref.profile_id + " linked creation", valid(obj) and obj.AxisSource[0] == line
              and str(obj.AxisDefinitionMode) == "Linked" and not line.ViewObject.Visibility)
        obj.StartExtension, obj.EndExtension = 12, 18
        line.Start = line.Start.add(App.Vector(5, 10, 20))
        line.End = line.End.add(App.Vector(5, 10, 120))
        doc.recompute()
        axis = resolve_axis_source(link)
        check(p.ref.profile_id + " linked recompute", point_equal(obj.StartPoint, axis.start)
              and point_equal(obj.EndPoint, axis.end) and valid(obj)
              and near(obj.StartExtension.Value, 12) and near(obj.EndExtension.Value, 18))
        check(p.ref.profile_id + " linked extensions volume", near(obj.Shape.Volume,
              p.physical_properties.area_mm2 * (axis.end.sub(axis.start).Length + 30)))

        preview = doc.addObject("Part::Feature", "SolidValidationPreview")
        state = PreviewState()
        for profile in chosen:
            for insertion, roll, color in (("Centroide", 0, (0.8, 0.3, 0.1)),
                                           ("Face superior", 90, (0.2, 0.6, 0.9))):
                state = update_member_preview(preview, state, profile.designation,
                    axis.start, axis.end, insertion, roll, color)
                check("SourceAxis preview " + profile.ref.profile_id + insertion,
                      valid(preview) and all(near(a, b) for a, b in zip(preview.ViewObject.ShapeColor[:3], color)))
        doc.removeObject(preview.Name)

    # Existing adjustment controller: limits and dual-end orthogonal/oblique cuts.
    for obj in (linked[0], linked[2]):
        start, end = obj.StartPoint, obj.EndPoint
        controller = MemberAdjustmentController(doc, obj)
        planes = []
        for slot, station, normal in (("Start", 100, App.Vector(0, 0, 1)),
                                     ("End", 900, App.Vector(0, 0, 1))):
            plane = doc.addObject("Part::Feature", "SolidCutReference")
            plane.Shape = Part.makePlane(300, 300, start.add(App.Vector(0, 0, station)), normal)
            plane.ViewObject.Visibility = False
            planes.append(plane)
            resolved = controller.validate(geometry_mode="PlaneCut", end_choice=slot,
                gap=2 if slot == "Start" else 3, keep_reference=True, reference=(plane, ["Face1"]))
            controller.apply(resolved)
            check(obj.Name + " orthogonal " + slot, valid(obj))
        check(obj.Name + " orthogonal volume", near(obj.Shape.Volume,
              profile_catalog.get(str(obj.Profile)).definition.physical_properties.area_mm2 * 795))
        planes[1].Shape = Part.makePlane(300, 300, start.add(App.Vector(0, 0, 900)), App.Vector(0.3, 0, 1))
        doc.recompute()
        check(obj.Name + " oblique dual cut", valid(obj))
        source = obj.AxisSource[0]
        source.End = source.End.add(App.Vector(20, 0, 100))
        doc.recompute()
        check(obj.Name + " linked adjustments preserved", valid(obj)
              and obj.StartAdjustmentReference[0] == planes[0] and obj.EndAdjustmentReference[0] == planes[1]
              and near(obj.StartAdjustmentGap.Value, 2) and near(obj.EndAdjustmentGap.Value, 3)
              and str(obj.StartAdjustmentGeometryMode) == "PlaneCut"
              and str(obj.EndAdjustmentGeometryMode) == "PlaneCut")
        check(obj.Name + " cut mass", near(obj.TotalMass, obj.Shape.Volume * 7.85e-6))

    square = linked[1]
    square.EndAdjustmentMode = "Fixed"
    square.EndAdjustmentGeometryMode = "LengthLimit"
    square.EndFixedReferenceOffset = 50
    square.EndAdjustmentGap = 4
    doc.recompute()
    check("square fixed LengthLimit", valid(square) and near(square.AdjustedLength.Value, square.Length.Value + 12 - 54))

    # Source placement (including parent transform) is resolved before member creation.
    part = doc.addObject("App::Part", "SolidSourceContainer")
    line = Draft.make_line(App.Vector(0, 0, 0), App.Vector(0, 0, 500))
    part.addObject(line)
    line.Placement = App.Placement(App.Vector(20, 40, 30), App.Rotation(App.Vector(0, 1, 0), 30))
    part.Placement = App.Placement(App.Vector(600, 300, 20), App.Rotation(App.Vector(0, 0, 1), 40))
    doc.recompute()
    axis = resolve_axis_source((line, ["Edge1"]))
    placed = create_member(doc, axis.start, axis.end, chosen[0].designation,
                           axis_source=(line, ["Edge1"]), link_axis=True)
    check("placed line global frame", valid(placed) and point_equal(placed.StartPoint, axis.start)
          and point_equal(placed.EndPoint, axis.end))

    # Real Qt browser, close/reopen, options and screen-space dimensions.
    for index, p in enumerate(chosen):
        for reopen in range(2):
            browser = ProfileBrowserDialog(initial_profile_ref=p.ref)
            browser.show()
            QtWidgets.QApplication.processEvents()
            check("browser reload " + p.ref.profile_id, browser.selected_profile_ref() == p.ref)
            check("visible fixture subtitle " + p.ref.profile_id,
                  "fixture de desenvolvimento" in browser.subtitle.text())
            if not reopen:
                browser.grab().save(str(directory / (p.ref.profile_id + "-browser.png")))
            browser.close()
        options = ProfileOptionsWidget(doc)
        options.set_profile_ref(p.ref)
        options.show()
        QtWidgets.QApplication.processEvents()
        check("radii hidden " + p.ref.profile_id, options.generate_radii.isHidden())
        check("rotation available " + p.ref.profile_id, options.rotation.isEnabled())
        options.grab().save(str(directory / (p.ref.profile_id + "-options.png")))
        options.close()

    # Thin bars keep their real aspect ratio in the native screen-space renderer.
    for width, thickness in ((50, 6.35), (100, 10), (100, 3)):
        profile = replace(chosen[2], geometry={"b": width, "t": thickness})
        geometry = build_section_geometry(profile)
        preview = SectionPreviewView()
        preview.resize(560, 250)
        preview.show()
        preview.set_geometry(geometry, profile_preview_dimension_rows(profile))
        QtWidgets.QApplication.processEvents()
        transform = preview.transform()
        check("thin preview ratio " + str(thickness), near(transform.m11(), transform.m22())
              and near((geometry.bounds.max_x - geometry.bounds.min_x)
                       / (geometry.bounds.max_y - geometry.bounds.min_y), width / thickness))
        check("thin preview dimensions " + str(thickness), len([
            item for item in preview.scene().items() if hasattr(item, "toPlainText")
        ]) == 2)
        preview.grab().save(str(directory / (f"flat-{width}x{thickness}-preview.png")))
        preview.close()

    # Exercise actual task-panel signals, rather than invoking its preview updater.
    source = linked[0].AxisSource[0]
    source_visibility = source.ViewObject.Visibility
    object_names = [obj.Name for obj in doc.Objects]
    tool = StructuralMemberDraftTool()
    try:
        tool.Activated(axis_source=(source, ["Edge1"]))
        for profile in chosen:
            tool.profile_options.set_profile_ref(profile.ref)
            tool.profile_options.insertion.setCurrentText("Centroide")
            tool.profile_options.rotation.setValue(0)
            QtWidgets.QApplication.processEvents()
            check("native profile signal " + profile.ref.profile_id, valid(tool.obj))
            tool.profile_options.insertion.setCurrentText("Face superior")
            QtWidgets.QApplication.processEvents()
            center = tool.obj.Shape.CenterOfMass
            tool.profile_options.rotation.setValue(90)
            QtWidgets.QApplication.processEvents()
            check("native insertion and rotation " + profile.ref.profile_id,
                  center.sub(tool.obj.Shape.CenterOfMass).Length > 1)
            tool.profile_options._apply_color(QtGui.QColor(51, 153, 230))
            QtWidgets.QApplication.processEvents()
            check("native color " + profile.ref.profile_id, all(near(a, b) for a, b in zip(
                tool.obj.ViewObject.ShapeColor[:3], (51 / 255, 153 / 255, 230 / 255))))
            tool.profile_options._apply_color(QtGui.QColor(220, 100, 30))
    finally:
        if tool.is_active():
            tool._terminate_native_session()
        QtWidgets.QApplication.processEvents()
    check("native cancel cleanup", [obj.Name for obj in doc.Objects] == object_names
          and source.ViewObject.Visibility == source_visibility)

    objects = created + linked + [placed]
    snapshot = {obj.Name: (str(obj.Profile), str(obj.ProfileCategory), str(obj.ProfileSeries),
        str(obj.Insertion), obj.Rotation.Value, obj.MassPerMeter, obj.CatalogArea,
        obj.TotalMass, obj.Shape.Volume, str(obj.AxisDefinitionMode),
        obj.AxisSource[0].Name if obj.AxisSource else None) for obj in objects}
    path = directory / "SolidStageA.FCStd"
    doc.recompute()
    doc.saveAs(str(path))
    name = doc.Name
    App.closeDocument(name)
    doc = App.openDocument(str(path))
    doc.recompute()
    for name, expected in snapshot.items():
        obj = doc.getObject(name)
        actual = (str(obj.Profile), str(obj.ProfileCategory), str(obj.ProfileSeries),
            str(obj.Insertion), obj.Rotation.Value, obj.MassPerMeter, obj.CatalogArea,
            obj.TotalMass, obj.Shape.Volume, str(obj.AxisDefinitionMode),
            obj.AxisSource[0].Name if obj.AxisSource else None)
        check("persistence " + name, valid(obj) and all(near(a, b) if isinstance(a, float) else a == b
                                                       for a, b in zip(actual, expected)))
        if obj.AxisSource:
            obj.AxisSource[0].End = obj.AxisSource[0].End.add(App.Vector(0, 0, 10))
            doc.recompute()
            axis = resolve_axis_source(obj.AxisSource)
            check("restored link " + name, valid(obj) and point_equal(obj.EndPoint, axis.end))
    Gui.activeDocument().activeView().viewAxonometric()
    Gui.activeDocument().activeView().fitAll()
    report.update(document=doc.Name, file=str(path), count=len(report["checks"]))
    print(report)
    return report


if __name__ == "__main__":
    run()
