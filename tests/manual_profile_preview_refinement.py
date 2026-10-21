# SPDX-License-Identifier: LGPL-2.1-or-later
"""Focused real Qt/FreeCAD probe; screenshots still need visual review.

Launch with scripts/run_simple_u_stage_b_gate.py --refinement --theme ...
The launcher supplies isolated preferences and never changes user documents.
"""

import json
import math
import os
from pathlib import Path
import sys
import traceback


def run(output):
    import FreeCAD as App
    import FreeCADGui as Gui
    import Draft
    import DraftTools
    from PySide import QtCore, QtGui, QtWidgets
    from PySide6 import QtTest
    from freecad.SteelStructures import profile_catalog, truss
    from freecad.SteelStructures.paths import CATALOGS_DIR
    from freecad.SteelStructures.profiles import ProfileLibrary, build_section_geometry
    from freecad.SteelStructures.interactive.profile_browser import ProfileBrowserDialog
    from freecad.SteelStructures.interactive.profile_options_widget import ProfileOptionsWidget
    from freecad.SteelStructures.interactive.column_task_panel import ColumnTaskPanel
    from freecad.SteelStructures.interactive.member_controller import MemberController
    from freecad.SteelStructures.interactive.draft_member_tool import StructuralMemberDraftTool
    from freecad.SteelStructures.interactive.truss_task_panel import _RoleProfileDialog, role_spec_from_options

    qss = os.environ.get("SS_SIMPLE_U_QSS")
    if qss:
        path = Path(qss)
        QtCore.QDir.addSearchPath("qss", str(path.parent))
        QtWidgets.QApplication.instance().setStyleSheet(path.read_text(encoding="utf-8"))
    checks, errors = [], []
    old_hook = sys.excepthook
    sys.excepthook = lambda kind, error, trace: errors.append(
        "".join(traceback.format_exception(kind, error, trace)))

    def check(name, condition):
        if not condition:
            raise AssertionError(name)
        checks.append(name)
        (output / "checks.json").write_text(json.dumps(checks, indent=2), encoding="utf-8")

    def drain():
        QtWidgets.QApplication.processEvents()

    def grab(widget, name):
        drain()
        check("capture " + name, widget.grab().save(str(output / (name + ".png"))))

    def close(widget):
        widget.close()
        widget.deleteLater()
        drain()

    def labels_fit(browser, name):
        view = browser.preview
        labels = [i for i in view.scene().items() if isinstance(i, QtWidgets.QGraphicsTextItem)]
        boxes = [i.deviceTransform(view.viewportTransform()).mapRect(i.boundingRect()) for i in labels]
        for index, rect in enumerate(boxes):
            check(name + " label in viewport " + str(index), QtCore.QRectF(view.viewport().rect()).contains(rect))
            for other in boxes[index + 1:]:
                check(name + " labels separated " + str(index), not rect.intersects(other))

    def outer_tip_at_axis(obj, insertion, name):
        # Strip the object's global placement, retaining its generated local
        # section. The external tip must coincide with the insertion axis.
        local = obj.Shape.copy()
        local.Placement = App.Placement()
        box = local.BoundBox
        check(name + " tip X at axis", abs(box.XMax) < 1e-7)
        y = box.YMax if insertion == "Ponta superior da mesa" else box.YMin
        check(name + " external tip Y at axis", abs(y) < 1e-7)
        check(name + " solid valid", local.isValid() and local.Volume > 0)

    doc = App.newDocument("PreviewRefinement")
    Gui.getMainWindow().resize(1500, 1000)
    library = ProfileLibrary(CATALOGS_DIR)
    profiles = library.list_profiles()
    simple = [p for p in profiles if p.geometry_variant == "simple_u"]
    ue = next(p for p in profiles if p.geometry_variant == "stiffened_u")
    try:
        for p in (simple[0], simple[116], simple[-1]):
            for width in (760, 1100):
                browser = ProfileBrowserDialog(initial_profile_ref=p.ref)
                browser.resize(width, 850)
                browser.show()
                drain()
                labels_fit(browser, p.ref.profile_id + str(width))
                texts = [i.toPlainText() for i in browser.preview.scene().items()
                         if isinstance(i, QtWidgets.QGraphicsTextItem)]
                check("radius R notation " + p.ref.profile_id, any("(ri)" in t and "R " in t for t in texts))
                check("four dimensions " + p.ref.profile_id, len(texts) == 4)
                arrows = [i for i in browser.preview.scene().items()
                          if isinstance(i, QtWidgets.QGraphicsPathItem)
                          and i.flags() & QtWidgets.QGraphicsItem.ItemIgnoresTransformations]
                check("one filled technical arrow " + p.ref.profile_id,
                      len(arrows) == 1 and arrows[0].brush().style() == QtCore.Qt.SolidPattern
                      and arrows[0].brush().color() == arrows[0].pen().color())
                arrow = arrows[0].path()
                check("closed triangular arrow " + p.ref.profile_id,
                      arrow.elementCount() == 4 and arrow.elementAt(0).x == arrow.elementAt(3).x
                      and arrow.elementAt(0).y == arrow.elementAt(3).y)
                grab(browser, p.ref.profile_id + "-browser-" + str(width))
                close(browser)

        # All actual catalog extremes, including the most slender flat bar.
        bars = []
        for variant in ("circular", "rectangular"):
            available = [p for p in profiles if p.geometry_type == "solid_section" and p.geometry_variant == variant]
            key = "d" if variant == "circular" else "b"
            bars.extend((min(available, key=lambda p: p.geometry[key]),
                         max(available, key=lambda p: p.geometry[key])))
            if variant == "rectangular":
                bars.append(max(available, key=lambda p: p.geometry["b"] / p.geometry["t"]))
        for index, p in enumerate(bars):
            for width in (760, 1100):
                browser = ProfileBrowserDialog(initial_profile_ref=p.ref)
                browser.resize(width, 850)
                browser.show()
                drain()
                for tab in (0, 1):
                    browser.tabs.setCurrentIndex(tab)
                    drain()
                    labels_fit(browser, p.designation + str((width, tab)))
                    if tab == 1:
                        ellipses = [i for i in browser.preview.scene().items()
                                    if isinstance(i, QtWidgets.QGraphicsEllipseItem)]
                        check("one centroid " + p.designation, len(ellipses) == 1)
                        ellipse = ellipses[0]
                        rect = ellipse.deviceTransform(browser.preview.viewportTransform()).mapRect(ellipse.rect())
                        check("centroid six pixels " + p.designation, abs(rect.width() - 6.) < .01)
                    grab(browser, f"bar-{index}-{width}-tab-{tab}")
                close(browser)

        for is_column in (False, True):
            panel = ColumnTaskPanel(doc) if is_column else ProfileOptionsWidget(doc)
            options = panel.profile_options if is_column else panel
            title = "column" if is_column else "member"
            panel.resize(470, 760)
            panel.show()
            for p in (simple[0], ue):
                options.set_profile_ref(p.ref)
                options.insertion.setCurrentText("Face externa da alma")
                options.rotation.setValue(37.)
                changes = []
                receiver = lambda value: changes.append(value)
                options.rotation.valueChanged.connect(receiver)
                options.rotation_buttons[0].click()
                check(title + " clockwise", options.rotation.value() == -53. and changes == [-53.])
                options.rotation_buttons[1].click()
                check(title + " counterclockwise", options.rotation.value() == 37. and changes == [-53., 37.])
                options.rotation.valueChanged.disconnect(receiver)
                check(title + " live preview rotation", options.orientation_preview._rotation == 37.)
                drain()
                for width in (340, 620):
                    panel.resize(width, 760)
                    drain()
                    grab(panel, title + "-" + p.geometry_variant + "-" + str(width))
                before = options.state()
                # Exercise the real modal catalog button, cancellation and OK.
                for accepted in (False, True):
                    failures = []

                    def inspect_catalog():
                        dialog = QtWidgets.QApplication.activeModalWidget()
                        try:
                            check(title + " modal catalog", isinstance(dialog, ProfileBrowserDialog))
                            check(title + " neutral catalog " + p.geometry_variant, dialog.insertion is None)
                            check(title + " catalog profile retained", dialog.selected_profile_ref() == p.ref)
                            check(title + " no insertion target", not any(
                                isinstance(i, QtWidgets.QGraphicsEllipseItem)
                                and i.pen().color() == QtGui.QColor(0, 112, 132)
                                for i in dialog.preview.scene().items()))
                            grab(dialog, title + "-catalog-" + p.geometry_variant + "-" + str(accepted))
                        except Exception:
                            failures.append(traceback.format_exc())
                        finally:
                            dialog.accept() if accepted else dialog.reject()

                    QtCore.QTimer.singleShot(20, inspect_catalog)
                    options.profile_browser_button.click()
                    check(title + " catalog callbacks", not failures)
                    check(title + " catalog keeps options", options.state() == before)

            options.set_profile_ref(simple[0].ref)
            preview = options.orientation_preview
            references = {r.id: r.point for r in preview._references}
            check(title + " web center restored", references["web_center"].y == references["web_back"].y == 0.)
            check(title + " schematic external tips", references["flange_top_tip"].y == references["outer_top_mid"].y
                  and references["flange_bottom_tip"].y == references["outer_bottom_mid"].y)
            for angle in (0, 37, 90, 180, 270):
                options.rotation.setValue(angle)
                drain()
                target, scale = preview._layout()
                # Hit-test actual native widgets for all nine reference ids.
                for reference in preview._references:
                    x, y = preview._screen_point(reference.point, target, scale)
                    QtTest.QTest.mouseClick(preview, QtCore.Qt.LeftButton, pos=QtCore.QPoint(round(x), round(y)))
                    check(title + " hotspot " + str(angle) + " " + reference.id,
                          preview._selected_reference().id == reference.id)
                grab(preview, title + "-mini-" + str(angle))
            # Buttons retain the same roundtrip through native member creation.
            controller = MemberController(doc)
            controller.start()
            options.rotation.setValue(37.)
            start = App.Vector(0, 0, 0)
            creation = panel.creation_options(start) if is_column else options.creation_options(start, App.Vector(1000, 0, 0))
            obj = controller.create(creation).member
            check(title + " native solid", obj.Shape.isValid() and obj.Shape.Volume > 0 and obj.Rotation.Value == 37.)
            for p in (simple[0], simple[-1]):
                options.set_profile_ref(p.ref)
                for detailed in (True, False):
                    options.generate_radii.setChecked(detailed)
                    for insertion in ("Ponta superior da mesa", "Ponta inferior da mesa"):
                        options.insertion.setCurrentText(insertion)
                        creation = panel.creation_options(start) if is_column else options.creation_options(start, App.Vector(1000, 0, 0))
                        obj = controller.create(creation).member
                        outer_tip_at_axis(obj, insertion, title + " " + p.ref.profile_id + str(detailed) + insertion)
            close(panel)

        role = _RoleProfileDialog(doc, "Banzo", truss.default_config()["role_specs"]["TOP_CHORD"])
        role.show()
        check("role reuses shared rotation buttons", role.rotation_buttons == role.options.rotation_buttons
              and len(role.rotation_buttons) == 2)
        grab(role, "truss-role-shared-buttons")
        close(role)
        config = truss.default_config()
        config.update(span=6000., start=[0., 0., 0.], end=[6000., 0., 0.], height=1800., panel_count=4)
        for index, (key, spec) in enumerate(config["role_specs"].items()):
            dialog = _RoleProfileDialog(doc, key, spec)
            dialog.options.set_profile_ref(simple[0].ref)
            insertion = "Ponta superior da mesa" if index % 2 else "Ponta inferior da mesa"
            dialog.options.insertion.setCurrentText(insertion)
            dialog.options.rotation.setValue(37.)
            config["role_specs"][key] = role_spec_from_options(spec, dialog.options)
            dialog.show()
            if index < 2:
                grab(dialog, "truss-" + ("upper" if index % 2 else "lower") + "-external-tip")
            close(dialog)
        owner = truss.apply_truss(doc, config)
        check("truss both external tip insertions", {str(o.Insertion) for o in owner.GeneratedMembers}
              == {"Ponta superior da mesa", "Ponta inferior da mesa"})
        for child in owner.GeneratedMembers:
            outer_tip_at_axis(child, str(child.Insertion), "truss " + child.Name)
        line = Draft.make_line(App.Vector(), App.Vector(0, 0, 1000))
        doc.recompute()
        before_names = tuple(o.Name for o in doc.Objects)
        tool = StructuralMemberDraftTool()
        try:
            tool.Activated(axis_source=(line, ["Edge1"]))
            options = tool.profile_options
            options.set_profile_ref(simple[0].ref)
            options.rotation.setValue(0)
            options.rotation_buttons[1].click()
            drain()
            check("Draft rotation live", options.rotation.value() == 90 and tool.obj.Shape.isValid())
            grab(options, "native-member-options")
        finally:
            if tool.is_active():
                tool._terminate_native_session()
            drain()  # Draft removes its temporary object on the next event turn.
        check("Draft cancel cleanup", before_names == tuple(o.Name for o in doc.Objects))
        check("no callback exceptions", not errors)
        return dict(ok=True, checks=checks, theme=os.environ["SS_SIMPLE_U_THEME"], version=App.Version()[:3],
                    note="Automated native GUI probe with captures; user manual approval pending.")
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
        (out / "result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        for name in tuple(App.listDocuments()):
            App.closeDocument(name)
        QtCore.QTimer.singleShot(0, QtWidgets.QApplication.quit)

    QtCore.QTimer.singleShot(500, launch)
