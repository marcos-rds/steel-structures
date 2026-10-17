"""Modal enlarged editor entry, shared draft and cleanup gate, FreeCAD 1.1.4."""
from copy import deepcopy
from math import isclose
import json
import os
from pathlib import Path
import sys
import traceback


def run(output):
    import FreeCAD as App
    import FreeCADGui as Gui
    import DraftTools
    import shiboken6
    from PySide6 import QtTest
    from PySide import QtCore, QtGui, QtWidgets
    from freecad.SteelStructures import truss
    from freecad.SteelStructures.interactive import truss_controller as controllers
    from freecad.SteelStructures.interactive.truss_topology_editor import TopologyCanvas
    from freecad.SteelStructures.trusses.assemblies import configure_assembly
    from freecad.SteelStructures.trusses.interconnector_options import default_connector

    # Optional real installed theme, confined to this isolated FreeCAD process.
    theme_path = os.environ.get("SS_TRUSS_EDITOR_QSS")
    if theme_path:
        theme_path = Path(theme_path)
        QtCore.QDir.addSearchPath("qss", str(theme_path.parent))
        QtWidgets.QApplication.instance().setStyleSheet(theme_path.read_text(encoding="utf8"))

    checks, observations = [], {}

    def check(name, condition):
        if not condition:
            current=controllers._active_panel
            if current is not None and current.form is not None:
                (output/"failure_state.json").write_text(json.dumps(dict(
                    check=name,message=current.message.text(),draft=current.session.config),indent=2))
                editor=current._topology_editor
                if editor is not None:
                    editor.grab().save(str(output/"failure.png"))
                    (output/"failure_layout.json").write_text(json.dumps(dict(
                        size=[editor.width(),editor.height()],connection_hint=[editor.connections_page.sizeHint().width(),editor.connections_page.sizeHint().height()],
                        connection_scroll=[editor.connections_scroll.horizontalScrollBar().maximum(),editor.connections_scroll.verticalScrollBar().maximum()],
                        controls_height=editor.connections_scroll.viewport().height(),canvas_height=editor.canvas.height()),indent=2))
            raise AssertionError(name)
        checks.append(name)
        (output / "checks.json").write_text(json.dumps(checks, indent=2))

    def drain():
        QtWidgets.QApplication.processEvents()

    def settle(panel):
        drain()
        if not panel._closed:
            panel._preview_timer.stop()

    def persisted(document, owner):
        return dict(requested=truss.config_from_object(owner, resolve_reference=False),
                    applied_state=owner.AppliedState,
                    objects=sorted(value.Name for value in document.Objects),
                    undo=document.UndoCount, redo=document.RedoCount)

    def old_button(panel):
        return next(button for button in panel.form.findChildren(QtWidgets.QPushButton)
                    if button.text().startswith("Editar alma"))

    def modal(label, panel, trigger, action, *, keyboard=False):
        """Assert inside the actual exec loop; exceptions always release the modal."""
        errors, seen, added, removed, held = [], [], [], [], []
        native_add, native_remove = App.addDocumentObserver, App.removeDocumentObserver

        def add(observer):
            if type(observer).__name__ == "ActivationObserver":
                added.append(id(observer))
            return native_add(observer)

        def remove(observer):
            if type(observer).__name__ == "ActivationObserver":
                removed.append(id(observer))
            return native_remove(observer)

        def callback():
            editor = panel._topology_editor
            try:
                check(label + "_modal_instance", editor is not None and editor.isModal())
                # Isolate navigation/resize from the panel's deferred 3D update.
                panel._preview_timer.stop()
                seen.append(id(editor))
                held.extend((editor, editor.canvas, editor.transverse_preview))
                action(editor)
            except Exception:
                errors.append(traceback.format_exc())
            finally:
                if editor is not None:
                    try:
                        editor.reject()
                    except RuntimeError:
                        pass  # Native document/task destruction already disposed it.

        def timeout():
            errors.append("Modal callback timed out: " + label)
            editor = panel._topology_editor
            if editor is not None:
                editor.reject()

        watchdog = QtCore.QTimer()
        watchdog.setSingleShot(True)
        watchdog.timeout.connect(timeout)
        if keyboard:
            trigger.setFocus()
            drain()
            check(label+"_button_keyboard_focus",trigger.hasFocus())
        App.addDocumentObserver, App.removeDocumentObserver = add, remove
        try:
            watchdog.start(15000)
            QtCore.QTimer.singleShot(0, callback)
            if keyboard:
                QtTest.QTest.keyClick(trigger,QtCore.Qt.Key_Space)
            else:
                trigger.click()
        finally:
            watchdog.stop()
            App.addDocumentObserver, App.removeDocumentObserver = native_add, native_remove
        observations[label] = dict(instances=seen, observer_add=added,
                                   observer_remove=removed, errors=errors)
        (output / "observations.json").write_text(json.dumps(observations, indent=2))
        if errors:
            raise AssertionError("\n".join(errors))
        check(label + "_callback_ran", len(seen) == 1)
        check(label + "_scoped_observer_balanced", len(added) == 1 and added == removed)
        check(label + "_unique_slot_released", panel._topology_editor is None)
        QtCore.QCoreApplication.sendPostedEvents(None, QtCore.QEvent.DeferredDelete)
        check(label + "_qt_children_destroyed", all(not shiboken6.isValid(widget) for widget in held))
        settle(panel)

    def click_canvas(editor, position):
        canvas = editor.canvas
        canvas.centerOn(position)
        drain()
        point = canvas.mapFromScene(position)
        for kind, buttons in ((QtCore.QEvent.MouseButtonPress, QtCore.Qt.LeftButton),
                              (QtCore.QEvent.MouseButtonRelease, QtCore.Qt.NoButton)):
            event = QtGui.QMouseEvent(kind, QtCore.QPointF(point), QtCore.Qt.LeftButton,
                                     buttons, QtCore.Qt.NoModifier)
            QtWidgets.QApplication.sendEvent(canvas.viewport(), event)

    def nested_profile(label,editor,action):
        errors,held=[],[]
        def callback():
            dialog=QtWidgets.QApplication.activeModalWidget()
            held.append(dialog)
            try:
                check(label+"_specialized_child",dialog is not editor and dialog.parentWidget() is editor)
                action(dialog)
            except Exception:
                errors.append(traceback.format_exc())
            finally:
                if shiboken6.isValid(dialog): dialog.reject()
        QtCore.QTimer.singleShot(0,callback)
        editor.fields.role_buttons["TOP_CHORD"][0].click()
        QtCore.QCoreApplication.sendPostedEvents(None,QtCore.QEvent.DeferredDelete)
        if errors: raise AssertionError("\n".join(errors))
        check(label+"_specialized_child_released",len(held)==1 and not shiboken6.isValid(held[0]))

    document = App.newDocument("TrussEditorGate")
    document.UndoMode = 1
    config = truss.default_config()
    config.update(span=2400., end=[2400., 0., 0.], height=1000., panel_count=6)
    config["role_specs"]["TOP_CHORD"] = configure_assembly(
        config["role_specs"]["TOP_CHORD"], "SpacedPair", 240.,
        interconnectors=(default_connector("Battens"),))
    config["connection_intents"] = {"B_S_MAIN_1_3": dict(
        form="Gusset", direct_policy="BalancedMiter", gusset=dict(
            plate_thickness=12., edge_margin=31., member_overlap=163., chord_contact="TrussInterior"))}
    owner = truss.apply_truss(document, config)
    panel = controllers.open_truss_panel(document, owner)
    settle(panel)
    check("new_entry_visible", panel.editor_button.isVisibleTo(panel.form)
          and panel.editor_button.parentWidget() is panel.form
          and panel.editor_button.text() == "Editor de Treliças...")
    old = old_button(panel)
    check("compact_panel_owns_hidden_projection",panel._editor_controls.parentWidget() is panel.form
          and panel._editor_controls.isHidden() and panel.form.layout().indexOf(panel._editor_controls)==-1)
    check("compact_panel_only_reference_section_visible",all(
        not panel.sections[name][0].isVisibleTo(panel.form) for name in ("Geometria","Alma","Perfis"))
        and panel.sections["Referência"][0].isChecked()
        and panel.reference_mode.isVisibleTo(panel.form))
    check("compact_panel_reference_alignment_accessible",panel.reference_alignment.isVisibleTo(panel.form)
          and panel.reference_alignment_label.isVisibleTo(panel.form)
          and panel.pick_button.isVisibleTo(panel.form))
    # The hidden Editar alma entry checks its legacy callback only. Users open
    # the shared editor through the one visible Editor de Treliças button.
    check("compact_panel_single_visible_editor_entry",not old.isVisibleTo(panel.form)
          and panel.editor_button.isVisibleTo(panel.form))
    check("compact_panel_has_no_permanent_summary",not hasattr(panel,"summary")
          and not hasattr(panel,"plane_label"))
    for _ in range(3):
        QtCore.QCoreApplication.sendPostedEvents(None,QtCore.QEvent.LayoutRequest)
        drain()
    # TaskView is hidden in this process; rendering activates its deferred layout.
    panel.form.grab().save(str(output/"entry_panel.png"))
    (output/"entry_layout.json").write_text(json.dumps(dict(
        button_y=panel.editor_button.mapTo(panel.form,QtCore.QPoint()).y(),
        preview_y=panel.preview.mapTo(panel.form,QtCore.QPoint()).y(),
        icon_null=panel.editor_button.icon().isNull(),auto_default=panel.editor_button.autoDefault(),
        default=panel.editor_button.isDefault(),button_index=panel.form.layout().indexOf(panel.editor_button),
        reference_y=panel.reference_mode.mapTo(panel.form,QtCore.QPoint()).y(),
        items=[type(panel.form.layout().itemAt(i).widget()).__name__ for i in range(panel.form.layout().count())]),indent=2))
    check("editor_entry_before_preview",panel.editor_button.mapTo(panel.form,QtCore.QPoint()).y()
          < panel.preview.mapTo(panel.form,QtCore.QPoint()).y()
          and not panel.editor_button.icon().isNull()
          and not panel.editor_button.autoDefault() and not panel.editor_button.isDefault())
    check("quick_panel_basic_controls_visible",all(getattr(panel,key).isVisibleTo(panel.form)
        for key in ("envelope_type","span","height","preset","driver","panel_count","reference_alignment")))
    check("quick_panel_creation_mode_first",panel.reference_mode.mapTo(panel.form,QtCore.QPoint()).y()
          < panel.preview.mapTo(panel.form,QtCore.QPoint()).y())
    check("reference_labels_are_simple",panel.reference_alignment_label.text()=="Linha de referência"
          and [panel.reference_alignment.itemText(i) for i in range(2)]==["Banzo inferior","Banzo superior"])
    check("advanced_collapsed_and_compact",panel.advanced.isHidden()
          and [group.title() for group in panel.advanced.point_groups+[panel.advanced.normal_group]]
          ==["Ponto inicial","Ponto final","Normal do plano"])
    panel.advanced_header.button.setChecked(True)
    for _ in range(3):
        QtCore.QCoreApplication.sendPostedEvents(None,QtCore.QEvent.LayoutRequest)
        drain()
    # Exercise the real widgets at both TaskPanel widths, without rebuilding
    # any numeric field or changing its pending text/focus.
    held_fields=panel.start_inputs+panel.end_inputs+panel.normal_inputs
    original_width_limits=(panel.form.minimumWidth(),panel.form.maximumWidth())
    original_minimum_height=panel.form.minimumHeight()
    original_size=panel.form.size()
    field=panel.start_inputs[0]
    original_value=field.value()
    QtWidgets.QApplication.setActiveWindow(Gui.getMainWindow())
    field.setFocus()
    drain()
    field.setText("1e")
    field.setSelection(0,1)
    original_selection=(field.cursorPosition(),field.selectedText())
    try:
        for width in (560,220):
            panel.form.setFixedWidth(width)
            for _ in range(4):
                QtCore.QCoreApplication.sendPostedEvents(None,QtCore.QEvent.LayoutRequest)
                drain()
            # The main window is hidden: size the captured TaskView content
            # to its new minimum, as its visible scroll area normally does.
            for _ in range(2):
                panel.form.grab()  # Polish hidden QFormLayout rows at this width first.
                panel.form.layout().invalidate()
                panel.form.layout().activate()
                capture_height=max(panel.form.height(),panel.form.minimumSizeHint().height(),
                                   panel.form.layout().totalHeightForWidth(width))
                panel.form.setMinimumHeight(capture_height)
                panel.form.resize(width,capture_height)
                panel.form.layout().activate()
            panel.form.grab().save(str(output/("advanced_width_"+str(width)+".png")))
            start,end=panel.advanced.point_groups
            check("responsive_points_"+str(width),(start.y()==end.y() and start.geometry().right()<end.x())
                  if width==560 else start.geometry().bottom()<end.y())
            if width==560:
                check("responsive_normal_horizontal",len({value.mapTo(panel.advanced,QtCore.QPoint()).y()
                      for value in panel.normal_inputs})==1)
            check("responsive_preserves_numeric_edit_"+str(width),field.hasFocus() and field.text()=="1e"
                  and (field.cursorPosition(),field.selectedText())==original_selection
                  and held_fields==panel.start_inputs+panel.end_inputs+panel.normal_inputs)
            (output/("responsive_form_"+str(width)+".json")).write_text(json.dumps(dict(
                form=[panel.form.width(),panel.form.height(),panel.form.minimumSizeHint().height(),
                      panel.form.layout().totalHeightForWidth(width),panel.form.maximumHeight(),panel.form.minimumHeight()],
                advanced=[panel.advanced.y(),panel.advanced.height(),panel.advanced.minimumHeight()],
                fields=[[value.width(),value.height(),value.mapTo(panel.form,QtCore.QPoint()).y()]
                        for value in held_fields]),indent=2))
            check("responsive_fields_fit_"+str(width),all(value.width()>=110
                  and panel.form.rect().contains(QtCore.QRect(value.mapTo(panel.form,QtCore.QPoint()),value.size()))
                  for value in held_fields))
            (output/("responsive_metrics_"+str(width)+".json")).write_text(json.dumps(dict(
                advanced=[panel.advanced.width(),panel.advanced.height(),panel.advanced.minimumHeight(),panel.advanced.minimumSizeHint().height()],
                groups=[dict(title=group.title(),height=group.height(),hint=group.minimumSizeHint().height(),
                    fields=[[value.mapTo(group,QtCore.QPoint()).y(),value.height()] for value in values])
                    for group,values in ((start,panel.start_inputs),(end,panel.end_inputs),(panel.advanced.normal_group,panel.normal_inputs))]),indent=2))
            check("responsive_fields_fit_groups_"+str(width),all(group.rect().contains(
                  QtCore.QRect(value.mapTo(group,QtCore.QPoint()),value.size()))
                  for group,values in ((start,panel.start_inputs),(end,panel.end_inputs),(panel.advanced.normal_group,panel.normal_inputs))
                  for value in values))
    finally:
        field.clearFocus()
        field.setValue(original_value)
        panel.form.setMinimumWidth(original_width_limits[0])
        panel.form.setMaximumWidth(original_width_limits[1])
        panel.form.setMinimumHeight(original_minimum_height)
        panel.form.resize(original_size)
        drain()
    precise=[1.123456789012,2.987654321098,3.141592653589]
    original=panel._read_vector(panel.start_inputs)
    panel._write_vector(panel.start_inputs,precise)
    check("advanced_exact_values_survive_compact_display",panel._read_vector(panel.start_inputs)==precise
          and panel.start_inputs[0].text()==App.Units.Quantity(precise[0],App.Units.Length).UserString)
    panel._write_vector(panel.start_inputs,original)
    vector_groups=panel.advanced.point_groups+[panel.advanced.normal_group]
    check("advanced_xyz_identified",all([label.text() for label in group.findChildren(QtWidgets.QLabel)]==list("XYZ")
          for group in vector_groups))
    all_fields=panel.start_inputs+panel.end_inputs+panel.normal_inputs
    check("advanced_fields_keep_native_height",all(field.height()>=field.minimumHeight()
          and field.height()>=field.fontMetrics().height()+4 for field in all_fields))
    check("advanced_text_fields_without_spinners",all(isinstance(field,QtWidgets.QLineEdit)
          and not isinstance(field,QtWidgets.QAbstractSpinBox) for field in all_fields))
    check("editor_entry_native_style",not panel.editor_button.styleSheet()
          and panel.editor_button.minimumHeight()>=36 and panel.editor_button.isEnabled())
    button=panel.editor_button
    images={}
    try:
        for state in ("normal","hover","pressed","disabled"):
            button.setEnabled(state!="disabled")
            button.setDown(state=="pressed")
            button.setAttribute(QtCore.Qt.WA_UnderMouse,state=="hover")
            button.update()
            image=button.grab().toImage()
            images[state]=image
            image.save(str(output/("editor_button_"+state+".png")))
        check("editor_button_native_states",images["normal"]!=images["pressed"]
              and images["normal"]!=images["disabled"])
    finally:
        button.setEnabled(True)
        button.setDown(False)
        button.setAttribute(QtCore.Qt.WA_UnderMouse,False)
    panel.form.grab().save(str(output/"advanced_panel.png"))
    # Include ancestor backgrounds: a transparent child grab can otherwise
    # show a light background behind FreeCAD Dark's inherited white text.
    Gui.getMainWindow().grab().save(str(output/"advanced_taskview.png"))
    # Real TaskView focus, unit parsing and Enter must not submit the document.
    QtWidgets.QApplication.setActiveWindow(Gui.getMainWindow())
    field=panel.start_inputs[0]
    field.setFocus()
    drain()
    check("coordinate_native_focus",field.hasFocus())
    before=deepcopy(panel.get_config())
    accepted_objects=sorted(value.Name for value in document.Objects)
    undo_before=document.UndoCount
    field.selectAll()
    QtTest.QTest.keyClicks(field,"-2.123456789 cm")
    QtTest.QTest.keyClick(field,QtCore.Qt.Key_Return)
    check("coordinate_enter_updates_one_shared_draft",panel._valid
          and isclose(panel.session.config["start"][0],-21.23456789,abs_tol=1e-12)
          and not panel._closed and document.UndoCount==undo_before
          and sorted(value.Name for value in document.Objects)==accepted_objects)
    # An incomplete edit survives Tab and blocks Apply/OK, rather than becoming zero.
    field.selectAll()
    QtTest.QTest.keyClicks(field,"1e")
    QtTest.QTest.keyClick(field,QtCore.Qt.Key_Tab)
    drain()
    check("partial_coordinate_kept_and_blocks_apply",field.text()=="1e" and not panel._valid
          and not panel.apply() and document.UndoCount==undo_before and "P0 X" in panel.message.text())
    field.setText("0 mm")
    check("coordinate_repair_commit",field.commit() and panel._valid)
    normal=panel.normal_inputs[0]
    normal.setText("1 mm")
    check("normal_rejects_length",not normal.commit() and not panel._valid
          and "Normal X" in panel.message.text())
    normal.setText("0")
    check("normal_repair_commit",normal.commit() and panel._valid)
    original_schema=App.Units.getSchema()
    try:
        for schema in (3,9):
            App.Units.setSchema(schema)
            panel._write_vector(panel.start_inputs,before["start"])
            field.setText("2")
            expected=2*field._unit_factor
            check("coordinate_unit_schema_"+str(schema),field.commit() and panel._valid
                  and isclose(panel.session.config["start"][0],expected,abs_tol=1e-10))
            normal.setValue(0.)
            check("normal_has_no_length_unit_"+str(schema),normal.text()==App.Units.Quantity(0.).UserString)
    finally:
        App.Units.setSchema(original_schema)
        for key,fields in (("start",panel.start_inputs),("end",panel.end_inputs),("plane_normal",panel.normal_inputs)):
            panel._write_vector(fields,before[key])
        panel._points_changed()
        panel._preview_timer.stop()
    check("numeric_probe_restores_frame",all(panel.get_config()[key]==before[key]
          for key in ("start","end","plane_normal")) and panel._valid)
    panel.advanced_header.button.setChecked(False)
    panel.form.grab().save(str(output/"quick_panel.png"))
    roles = deepcopy(panel.session.config["role_specs"])
    intents = deepcopy(panel.session.config["connection_intents"])
    initial = persisted(document, owner)
    initial_candidate = panel.controller.last_candidate
    panel.form.grab().save(str(output / "panel.png"))
    panel._pick_points()
    check("capture_active_before_modal", len(panel.controller._point_callbacks) == 3)

    def inspect(editor):
        check("title_and_shared_session", editor.windowTitle() == "Editor de Treliças"
              and editor.session is panel.session)
        check("three_functional_tabs_one_shared_canvas", editor.tabs.count() == 3
              and [editor.tabs.tabText(i) for i in range(3)] == ["Geometria", "Perfis", "Ligações"]
              and editor.connections_scroll.widget() is editor.connections_page
              and len(editor.findChildren(TopologyCanvas)) == 1
              and editor.canvas.parentWidget() is editor)
        available = editor.screen().availableGeometry()
        check("initial_size_fits_screen", editor.width() <= available.width()
              and editor.height() <= available.height())
        candidate=panel.session.validated_candidate
        check("information_uses_validated_candidate",candidate is not None
              and editor.fields.information_box.isEnabled()
              and editor.fields.information_values["nodes"].text()==str(len(candidate.graph.nodes))
              and editor.fields.information_values["bars"].text()==str(len(candidate.graph.edges))
              and editor.fields.information_values["panels"].text()==str(candidate.config["panelization_result"]["panel_count"]))
        check("no_permanent_generated_topology_text",not panel.topology_state.text()
              and editor.fields.geometry_status.isHidden())
        panel.session.invalidate("Gate: candidato desatualizado")
        editor.fields.sync()
        check("stale_revision_clears_information",panel._valid
              and all(label.text()=="—" for label in editor.fields.information_values.values()))
        panel.session.record_candidate(candidate)
        editor.fields.sync()
        drain()  # Measure the shown dialog after Qt has laid out both columns.
        fields=editor.fields
        (output/"geometry_layout.json").write_text(json.dumps(dict(
            viewport_width=fields.geometry_scroll.viewport().width(),
            content_width=fields.geometry_controls.width(),
            span_width=fields.controls["span"].width(),
            span_maximum=fields.controls["span"].maximumWidth()),indent=2))
        check("geometry_uses_bounded_content_with_compact_fields",
              fields.geometry_scroll.viewport().width()*.8 < fields.geometry_controls.width() <= 1040
              and 0 < fields.controls["span"].width() <= 180)
        check("capture_canceled_on_entry", not panel.controller._point_callbacks
              and panel.controller._view is None and panel.pick_button.isEnabled())
        canvas = editor.canvas
        panel.editor_button.click()
        old.click()
        check("both_reentries_reuse_modal_canvas", panel._topology_editor is editor
              and editor.canvas is canvas and len(editor.findChildren(TopologyCanvas)) == 1)
        observations["theme_qss"] = str(theme_path) if theme_path else "isolated default"
        for mode, button in editor.mode_buttons.items():
            editor.mode_buttons["select" if mode != "select" else "create"].click()
            unchecked = button.grab().toImage().pixelColor(6,6).name()
            button.click()
            checked = button.grab().toImage().pixelColor(6,6).name()
            check("theme_toolbar_"+mode,button.size()==QtCore.QSize(32,32)
                  and checked!=unchecked and editor.current_mode()==mode
                  and sum(value.isChecked() for value in editor.mode_group.buttons())==1)
        editor.mode_buttons["select"].click()
        check("theme_instant_commands_not_checked",not editor.invert_button.isCheckable()
              and not editor.copy_button.isCheckable())
        # Render hover explicitly: this process is hidden, so moving the system
        # cursor cannot reliably enter a widget. Capture the dialog background,
        # not an isolated transparent child (which loses its parent's QSS fill).
        def toolbar_image():
            return editor.grab().copy(editor.topology_toolbar.geometry()).toImage()
        for button in editor.mode_buttons.values():
            button.setAttribute(QtCore.Qt.WA_UnderMouse, False)
        active_image=toolbar_image()
        active_image.save(str(output / "toolbar_active.png"))
        for mode,filename in (("create","toolbar_hover.png"),("select","toolbar_active_hover.png")):
            button=editor.mode_buttons[mode]
            button.setAttribute(QtCore.Qt.WA_UnderMouse, True)
            button.update()
            drain()
            hover_image=toolbar_image()
            check("theme_hover_visible_"+mode,hover_image!=active_image)
            hover_image.save(str(output / filename))
            button.setAttribute(QtCore.Qt.WA_UnderMouse, False)
            button.update()
        app=QtWidgets.QApplication.instance()
        (output / "theme.json").write_text(json.dumps(dict(
            theme=App.ParamGet("User parameter:BaseApp/Preferences/MainWindow").GetString("Theme"),
            style=app.style().objectName(), qss=observations["theme_qss"],
            stylesheet_length=len(app.styleSheet()),
            window_color=editor.palette().color(QtGui.QPalette.Window).name()),indent=2))
        editor.grab().save(str(output / "editor.png"))
        check("canvas_height_respects_geometry_hint", editor.canvas.height()
              <= editor.canvas.heightForWidth(editor.canvas.width())+2)
        editor.resize(760, 560)
        drain()
        editor.tabs.setCurrentWidget(editor.connections_scroll)
        editor.select_node("B_S_MAIN_1_3")
        drain()
        check("small_window_has_local_scroll", editor.connections_scroll.verticalScrollBar().maximum() > 0)
        buttons = editor.action_buttons
        check("localized_editor_actions",[button.text() for button in
            (editor.cancel_button,editor.apply_button,editor.ok_button)]==["Cancelar","Aplicar","OK"])
        check("small_window_keeps_canvas_and_close", editor.rect().contains(editor.canvas.geometry())
              and editor.rect().contains(buttons.geometry()) and editor.canvas.isVisible())
        editor.connections_scroll.ensureWidgetVisible(editor.gusset_position)
        drain()
        check("small_window_reaches_position_controls", editor.connections_scroll.viewport().rect().contains(
              editor.gusset_position.mapTo(editor.connections_scroll.viewport(),QtCore.QPoint())))
        editor.grab().save(str(output / "editor_small.png"))

    modal("new_entry", panel, panel.editor_button, inspect, keyboard=True)
    check("closing_editor_has_no_document_transaction", persisted(document, owner) == initial)
    check("closing_editor_preserves_semantic_candidate",
          panel.controller.last_candidate.config == initial_candidate.config)
    panel._pick_points()
    check("picker_can_restart_after_modal", len(panel.controller._point_callbacks) == 3
          and not panel.pick_button.isEnabled())
    panel.controller.cancel_picker()

    def edit_fields(editor):
        fields=editor.fields
        controls=fields.controls
        editor.tabs.setCurrentWidget(fields.geometry_scroll)
        old_height=panel.height.value()
        roles_before=deepcopy(panel.session.config["role_specs"])
        intents_before=deepcopy(panel.session.config["connection_intents"])
        calls=[]
        native_preview=panel.controller.preview
        def preview(value):
            calls.append(1)
            return native_preview(value)
        panel.controller.preview=preview
        try:
            controls["height"].setValue(1200.)
            check("quick_and_editor_fields_visible",controls["height"].isVisibleTo(fields.geometry_page)
                  and panel.height.isVisibleTo(panel.form) and not panel.height.isHidden())
            settle(panel)
            check("editor_height_uses_single_panel_validation", len(calls)==1
                  and panel.height.value()==1200. and panel.session.config["height"]==1200.
                  and editor.canvas._last_model["envelope"]["top"][0][1]==1200.)
            panel.height.setValue(1300.)
            settle(panel)
            check("live_panel_to_editor_sync",controls["height"].value()==1300.)
            controls["height"].setValue(0.)
            settle(panel)
            check("invalid_geometry_keeps_draft_disables_stale_graph",not panel._valid
                  and panel.session.config["height"]==0. and not editor.canvas.isEnabled()
                  and not editor.topology_toolbar.isEnabled() and not editor.connections_scroll.isEnabled()
                  and "desatualizado" in editor.message.text())
            check("invalid_geometry_clears_information",not fields.information_box.isEnabled()
                  and all(label.text()=="—" for label in fields.information_values.values()))
            controls["height"].setValue(old_height)
            settle(panel)
            check("geometry_repair_reenables_same_canvas",panel._valid and editor.canvas.isEnabled())
            check("geometry_repair_restores_information",fields.information_box.isEnabled()
                  and fields.information_values["nodes"].text()==str(len(panel.controller.last_candidate.graph.nodes)))
        finally:
            panel.controller.preview=native_preview
        for key,value in (("span",2600.),("span",2400.)):
            widget=controls[key]
            if isinstance(widget,QtWidgets.QComboBox): widget.setCurrentIndex(widget.findData(value))
            elif isinstance(widget,QtWidgets.QCheckBox): widget.setChecked(value)
            else: widget.setValue(value)
            settle(panel)
            check("geometry_field_"+key+str(value),panel._valid)
        (output/"fields_roundtrip.json").write_text(json.dumps(dict(
            old_roles=roles_before,new_roles=panel.session.config["role_specs"],
            old_intents=intents_before,new_intents=panel.session.config["connection_intents"]),indent=2))
        check("new_fields_preserve_advanced_roles",panel.session.config["role_specs"]==roles_before)
        check("new_fields_preserve_intents",panel.session.config["connection_intents"]==intents_before)
        check("new_fields_preserve_document",persisted(document,owner)==initial)
        editor.tabs.setCurrentWidget(fields.geometry_scroll)
        check("reference_has_no_capture_button",not any("Selecionar dois" in b.text() or "Usar seleção Draft" in b.text()
              for b in fields.geometry_page.findChildren(QtWidgets.QPushButton)))
        check("reference_capture_stays_in_panel",not any(key in fields.controls
              for key in ("reference_mode","reference_edge","keep_reference_link")))
        controls["reference_alignment"].setCurrentIndex(controls["reference_alignment"].findData("TopChordSupports"))
        settle(panel)
        check("editor_reference_synchronizes_same_session",panel.reference_alignment.currentData()=="TopChordSupports"
              and panel._valid and persisted(document,owner)==initial)
        controls["reference_alignment"].setCurrentIndex(controls["reference_alignment"].findData("BottomChord"))
        settle(panel)
        check("geometry_form_width_bounded",fields.geometry_controls.maximumWidth()==1040
              and controls["height"].width()<=180 and controls["preset"].width()<=300
              and editor.canvas.width()>fields.geometry_controls.width()-20)
        for page,name in ((fields.geometry_scroll,"geometry"),
                          (fields.profiles_scroll,"profiles")):
            editor.tabs.setCurrentWidget(page)
            drain()
            editor.grab().save(str(output/("editor_"+name+".png")))

    modal("fields",panel,panel.editor_button,edit_fields)
    check("fields_return_synchronizes_panel",panel.height.value()==1000. and panel.span.value()==2400.
          and persisted(document,owner)==initial)

    edited_edges=[]
    def select_and_edit(editor):
        graph = panel.controller.last_candidate.graph
        node = graph.node("B_S_MAIN_1_3")
        editor.mode_buttons["select"].click()
        click_canvas(editor, QtCore.QPointF(node.position_local[0], -node.position_local[1]))
        check("node_selection_functional", editor._connection_node == node.key
              and editor.connection_box.isEnabled())
        check("gusset_transverse_preview_functional", editor.connection_type.currentData() == "Gusset"
              and bool(editor.transverse_preview.canvas._views))
        candidate=panel.controller.last_candidate
        draft=deepcopy(panel.session.config)
        for index in range(editor.tabs.count()):
            editor.tabs.setCurrentIndex(index)
            drain()
            check("three_tabs_keep_selected_node_"+str(index),editor._connection_node==node.key
                  and editor.canvas.isVisible() and panel.controller.last_candidate is candidate)
            check("toolbar_visible_in_tab_"+str(index),editor.topology_toolbar.isVisible()
                  and editor.topology_toolbar.geometry().bottom()<editor.canvas.geometry().top())
            editor.mode_buttons["create"].click()
            check("tool_active_in_tab_"+str(index),editor.current_mode()=="create")
            editor.canvas.pending=node.key
            editor.canvas.rubber=editor.canvas.scene().addLine(0,0,10,10)
            editor.tabs.setCurrentIndex((index+1)%3)
            check("navigation_cancels_only_gesture_"+str(index),editor.current_mode()=="select"
                  and editor.canvas.pending is None and editor.canvas.rubber is None
                  and editor._connection_node==node.key)
        for _ in range(3):
            editor.tabs.setCurrentWidget(editor.connections_scroll)
            drain()
            check("tab_selection_preserved_"+str(_), editor._connection_node == node.key
                  and editor.canvas.isVisible() and editor.current_mode() == "select")
            editor.tabs.setCurrentWidget(editor.fields.geometry_scroll)
            drain()
        check("tab_navigation_has_no_candidate_or_document_write", panel.controller.last_candidate is candidate
              and panel.session.config == draft and persisted(document,owner) == initial)
        editor.tabs.setCurrentWidget(editor.connections_scroll)
        drain()
        check("normal_connections_need_no_scroll", editor.connections_scroll.verticalScrollBar().maximum() == 0
              and editor.connections_scroll.horizontalScrollBar().maximum() == 0)
        editor.gusset_plate.setValue(14.)
        check("gusset_edit_uses_same_draft", panel.session.config["connection_intents"][node.key]["gusset"]["plate_thickness"] == 14.)
        editor.gusset_plate.setValue(12.)
        editor.grab().save(str(output / "editor_gusset.png"))
        editor.tabs.setCurrentWidget(editor.fields.geometry_scroll)
        drain()
        edge = next(value for value in graph.edges if value.role == "DIAGONAL")
        start, end = graph.node(edge.start_node_key).position_local, graph.node(edge.end_node_key).position_local
        midpoint = QtCore.QPointF((start[0] + end[0]) / 2., -(start[1] + end[1]) / 2.)
        click_canvas(editor, midpoint)
        check("edge_selection_functional", editor.canvas.selected == edge.key
              and editor._connection_node is None)
        edited_edges.append(edge.key)
        editor.mode_buttons["remove"].click()
        click_canvas(editor, midpoint)
        check("current_web_edit_creates_shared_custom", panel.session.config["topology_mode"] == "Custom"
              and panel.session.pending_changes
              and not any(value.key == edge.key for value in panel.controller.last_candidate.graph.edges))
        editor.allow_free.setChecked(True)
        editor.mode_buttons["add_node"].click()
        click_canvas(editor, QtCore.QPointF(1000., -300.))
        internal = next(value for value in panel.controller.last_candidate.graph.nodes
                        if value.classification == "INTERNAL_NODE")
        editor.mode_buttons["move_node"].click()
        click_canvas(editor, QtCore.QPointF(internal.position_local[0], -internal.position_local[1]))
        click_canvas(editor, QtCore.QPointF(1050., -450.))
        moved = panel.controller.last_candidate.graph.node(internal.key)
        (output / "node_gesture.json").write_text(json.dumps(dict(
            initial=internal.position_local, moved=moved.position_local,
            pending=editor.canvas.pending, message=editor.message.text()), indent=2))
        check("internal_node_add_move", abs(moved.position_local[0]-1050.) < 5.
              and abs(moved.position_local[1]-450.) < 5.)
        editor.mode_buttons["remove_node"].click()
        click_canvas(editor, QtCore.QPointF(moved.position_local[0], -moved.position_local[1]))
        check("internal_node_remove", not any(value.key == internal.key
              for value in panel.controller.last_candidate.graph.nodes))

    modal("old_entry", panel, old, select_and_edit)
    check("cancel_discards_editor_custom_gesture",panel.session.config.get("topology_mode","Preset")=="Preset"
          and persisted(document,owner)==initial and not panel._closed)
    # Seed a TaskPanel draft for the following reconciliation checks; Cancel
    # must now preserve this preopening Custom state, rather than editor edits.
    panel.apply_topology_edit("remove_edge",key=edited_edges[-1])
    custom = deepcopy(panel.session.config["custom_topology"])
    (output / "advanced_differences.json").write_text(json.dumps(dict(valid=panel._valid,
        role_equal=panel.session.config["role_specs"] == roles,
        old_intents=intents, new_intents=panel.session.config["connection_intents"],
        persistent_equal=persisted(document, owner) == initial,
        message=panel.message.text()), indent=2))
    check("custom_return_preserves_complete_advanced_draft", panel._valid
          and panel.session.config["role_specs"] == roles
          and panel.session.config["connection_intents"] == intents
          and persisted(document, owner) == initial)
    def custom_geometry(editor):
        controls=editor.fields.controls
        controls["height"].setValue(1100.)
        settle(panel)
        check("custom_geometry_uses_existing_reconciliation",panel._valid
              and panel.session.config["topology_mode"]=="Custom")
        controls["height"].setValue(1000.)
        settle(panel)
        check("repeated_open_preserves_custom",panel.session.config["custom_topology"]==custom
              and panel.controller.last_candidate.config["custom_topology"]==custom)
        controls["envelope_type"].setCurrentIndex(controls["envelope_type"].findData("DuoPitch"))
        settle(panel)
        check("custom_envelope_change_stays_explicit",controls["envelope_type"].currentData()=="Parallel"
              and panel.session.config["custom_topology"]==custom)

    modal("repeat_entry",panel,panel.editor_button,custom_geometry)

    def profiles_inside(editor):
        editor.tabs.setCurrentWidget(editor.fields.profiles_scroll)
        for role in ("VERTICAL","TOP_CHORD"):
            previous=deepcopy(panel.session.config["role_specs"][role])
            errors=[]
            for accepted in (True,False):
                def specialized():
                    dialog=QtWidgets.QApplication.activeModalWidget()
                    try:
                        check(role+"_nested_parent_"+str(accepted),dialog.parentWidget() is editor
                              and dialog.mode.currentData()==previous.get("assembly","Single"))
                        dialog.options.rotation.setValue(22. if accepted else 33.)
                        if accepted: dialog.accept()
                        else: dialog.reject()
                    except Exception:
                        errors.append(traceback.format_exc())
                        dialog.reject()
                QtCore.QTimer.singleShot(0,specialized)
                editor.fields.role_buttons[role][0].click()
                settle(panel)
                if errors: raise AssertionError("\n".join(errors))
                current=panel.session.config["role_specs"][role]
                check(role+"_nested_result_"+str(accepted),current["rotation"]==22.
                      and current["profile_ref"]==previous["profile_ref"]
                      and current.get("assembly","Single")==previous.get("assembly","Single")
                      and editor.fields.role_buttons[role][0].text()==panel.role_buttons[role].text()
                      and persisted(document,owner)==initial)
        editor.grab().save(str(output/"editor_profiles_after.png"))

    modal("profiles",panel,panel.editor_button,profiles_inside)

    for role in ("VERTICAL", "TOP_CHORD"):
        previous = deepcopy(panel.session.config["role_specs"][role])
        errors = []
        def profile_action():
            dialog = QtWidgets.QApplication.activeModalWidget()
            try:
                check(role+"_specialized_profile_dialog", dialog is not None
                      and dialog.mode.currentData() == previous.get("assembly", "Single"))
                dialog.options.rotation.setValue(15.)
                dialog.accept()
            except Exception:
                errors.append(traceback.format_exc())
                if dialog is not None:
                    dialog.reject()
        QtCore.QTimer.singleShot(0, profile_action)
        panel._edit_role(role)
        if errors:
            raise AssertionError("\n".join(errors))
        current = panel.session.config["role_specs"][role]
        check(role+"_profile_edit_stays_in_draft", current["rotation"] == 15.
              and current["profile_ref"] == previous["profile_ref"]
              and current.get("assembly", "Single") == previous.get("assembly", "Single")
              and persisted(document, owner) == initial)
        if role == "TOP_CHORD":
            check("compound_interconnectors_preserved", current["assembly_spec"]["spec"]["interconnectors"]
                  == previous["assembly_spec"]["spec"]["interconnectors"])
    before = document.UndoCount
    check("apply_after_editor_return", panel.apply() and document.UndoCount == before + 1
          and owner.TopologyMode == "Custom" and not panel.session.pending_changes)
    applied = persisted(document, owner)
    panel.height.setValue(1400.)
    settle(panel)
    modal("pending_entry", panel, panel.editor_button, lambda editor: check(
        "pending_draft_shared", editor.panel.session.config["height"] == 1400.))
    panel.reject()
    drain()
    check("cancel_after_return_keeps_applied_custom", persisted(document, owner) == applied
          and panel.controller._preview is None and controllers._active_panel is None)

    for changed in (False, True):
        panel = controllers.open_truss_panel(document, owner)
        settle(panel)
        before = document.UndoCount
        if changed:
            panel.height.setValue(1250.)
            settle(panel)
        modal("ok_return_"+str(changed), panel, panel.editor_button, lambda editor: check(
            "ok_return_shared_"+str(changed), editor.session is panel.session))
        check("ok_after_return_"+str(changed), panel.accept() and panel.session.closed
              and document.UndoCount == before + int(changed)
              and (not changed or owner.Height.Value == 1250.))
        drain()

    # All toolbar entry points also work before creation, without transactions.
    creation_before=(len(document.Objects),document.UndoCount)
    panel=controllers.open_truss_panel(document)
    settle(panel)
    def creation_toolbar(editor):
        check("creation_editor_has_no_owner",editor.session.owner is None)
        calls=[]
        native_edit=panel.apply_topology_edit
        def edit(action,**kwargs):
            calls.append((action,kwargs))
            return native_edit(action,**kwargs)
        panel.apply_topology_edit=edit
        try:
            editor.invert_button.click()
            editor.copy_actions["RightToLeft"].trigger()
            editor.copy_actions["LeftToRight"].trigger()
            check("toolbar_transform_callbacks",calls==[("mirror",{}),
                ("copy_mirrored",{"direction":"RightToLeft"}),("copy_mirrored",{"direction":"LeftToRight"})])
            check("toolbar_transform_draft_valid",panel._valid and panel.session.config["topology_mode"]=="Custom"
                  and editor.copy_direction=="LeftToRight")
            editor.allow_free.click()
            check("direct_free_node_option",editor.allow_free.isChecked()
                  and editor.allow_free.isVisible()
                  and editor.allow_free not in editor.mode_group.buttons())
        finally:
            panel.apply_topology_edit=native_edit
        check("creation_toolbar_has_no_document_write",(len(document.Objects),document.UndoCount)==creation_before)
    modal("creation_toolbar",panel,panel.editor_button,creation_toolbar)
    panel.reject()
    drain()
    check("creation_cancel_releases_preview",panel.controller._preview is None
          and controllers._active_panel is None and (len(document.Objects),document.UndoCount)==creation_before)

    # Layout-only operations across shallow, pitched and tall geometry.
    layout_metrics={}
    for label,kind,height in (("parallel_shallow","Parallel",1000.),
                              ("duopitch","DuoPitch",2000.),
                              ("parallel_tall","Parallel",4000.)):
        layout_config=truss.default_config()
        layout_config.update(span=6000.,end=[6000.,0.,0.],height=height,envelope_type=kind,
                             left_end_height=500. if kind=="DuoPitch" else 0.,
                             right_end_height=500. if kind=="DuoPitch" else 0.)
        layout_owner=truss.apply_truss(document,layout_config)
        panel=controllers.open_truss_panel(document,layout_owner)
        settle(panel)
        before_layout=persisted(document,layout_owner)

        def geometry_layout(editor):
            canvas=editor.canvas
            if label=="parallel_shallow":
                controls=editor.fields.controls
                for mode in ("ByTargetSpacing","ByTargetDiagonalAngle","CustomSpacingList","ByPanelCount"):
                    controls["driver"].setCurrentIndex(controls["driver"].findData(mode))
                    settle(panel)
                    check("editor_driver_"+mode,panel._valid and panel.session.config["panelization_mode"]==mode)
                    if mode=="ByTargetDiagonalAngle":
                        check("contextual_effective_angle_preserved","Ângulo médio efetivo" in editor.fields.geometry_status.text())
                    active_field={"ByTargetSpacing":controls["target_spacing"],
                                  "ByTargetDiagonalAngle":controls["target_angle"],
                                  "CustomSpacingList":editor.fields.spacing_editor,
                                  "ByPanelCount":controls["panel_count"]}[mode]
                    check("compact_editor_driver_visible_"+mode,active_field.isVisibleTo(editor.fields.geometry_page)
                          and panel._editor_controls.isHidden())
                    if mode=="CustomSpacingList":
                        precise=[1000.123456789,999.876543211,1000.,1000.,1000.,1000.]
                        editor.fields.spacing_editor.set_values(precise)
                        settle(panel)
                        check("editor_spacing_exact_roundtrip",panel._valid
                              and panel.spacing_editor.values()==precise
                              and panel.session.config["custom_spacings"]==precise)
                        editor.fields.spacing_editor._spins[0].setValue(950.)
                        editor.fields.spacing_editor._spins[1].setValue(1050.)
                        settle(panel)
                        check("editor_spacing_fields_sync",panel._valid
                              and panel.spacing_editor.values()==[950.,1050.,1000.,1000.,1000.,1000.]
                              and panel.session.config["custom_spacings"]==panel.spacing_editor.values())
                controls["panel_count"].setValue(6)
                settle(panel)
            if kind=="DuoPitch":
                editor.tabs.setCurrentWidget(editor.fields.geometry_scroll)
                controls=editor.fields.controls
                for key,value in (("apex",40.),("apex",50.),("left_end_height",600.),
                                  ("link_end_heights",False),("right_end_height",700.),
                                  ("right_end_height",500.),("left_end_height",500.),("link_end_heights",True)):
                    if isinstance(controls[key],QtWidgets.QCheckBox): controls[key].setChecked(value)
                    else: controls[key].setValue(value)
                    settle(panel)
                    displayed=controls[key].isChecked() if isinstance(controls[key],QtWidgets.QCheckBox) else controls[key].value()
                    check("pitched_field_"+key+str(value),panel._valid and displayed==value)
                    check("pitched_field_visible_"+key+str(value),controls[key].isVisibleTo(editor.fields.geometry_page))
                editor.grab().save(str(output/"editor_pitched_geometry.png"))
                editor.tabs.setCurrentWidget(editor.fields.geometry_scroll)
            candidate=panel.controller.last_candidate
            draft=deepcopy(panel.session.config)
            layout_metrics[label]=dict(initial_size=[editor.width(),editor.height()],
                                       canvas_size=[canvas.width(),canvas.height()],
                                       height_hint=canvas.heightForWidth(canvas.width()))
            (output/"layout_metrics.json").write_text(json.dumps(layout_metrics,indent=2))
            check(label+"_proportional_canvas", canvas.height()<=canvas.heightForWidth(canvas.width())+2)
            editor.grab().save(str(output/(label+"_alma.png")))
            for width,height_limit in ((1100,850),(760,560),(620,480)):
                editor.resize(width,height_limit)
                drain()
                for index in range(3):
                    editor.tabs.setCurrentIndex(index)
                    drain()
                    name=label+"_"+str(width)+"_"+str(index)
                    check(name+"_canvas_close_visible", canvas.isVisible()
                          and editor.rect().contains(canvas.geometry())
                          and editor.rect().contains(editor.topology_toolbar.geometry())
                          and editor.rect().contains(editor.action_buttons.geometry()))
                    check(name+"_controls_usable", editor.tabs.currentWidget().viewport().height()>=100)
                    check(name+"_undistorted_fitted_geometry", abs(canvas.transform().m11()-canvas.transform().m22())<1e-9
                          and canvas.viewport().rect().contains(canvas.mapFromScene(canvas._geometry_bounds.topLeft()))
                          and canvas.viewport().rect().contains(canvas.mapFromScene(canvas._geometry_bounds.bottomRight())))
                    if label=="parallel_shallow" and width==620 and index in (0,1):
                        target={0:editor.fields.controls["reference_alignment"],
                                1:editor.fields.role_buttons["END_POST_RIGHT"][0]}[index]
                        scroll=editor.tabs.currentWidget()
                        scroll.ensureWidgetVisible(target,0,0)
                        drain()
                        check(name+"_last_control_reachable",scroll.viewport().rect().contains(
                            target.mapTo(scroll.viewport(),target.rect().center())))
                        editor.grab().save(str(output/("small_tab_"+str(index)+".png")))
                editor.grab().save(str(output/(label+"_"+str(width)+".png")))
            check(label+"_resize_tabs_preserve_draft_candidate_document", panel.controller.last_candidate is candidate
                  and panel.session.config==draft and persisted(document,layout_owner)==before_layout)

        modal(label,panel,panel.editor_button,geometry_layout)
        panel.reject()
        drain()
    check("shallow_canvas_compacter_than_tall", layout_metrics["parallel_shallow"]["canvas_size"][1]
          <layout_metrics["parallel_tall"]["canvas_size"][1])

    import Draft
    for linked in (False,True):
        line=Draft.make_line(App.Vector(0,0,0),App.Vector(2400,0,0))
        document.recompute()
        reference_config=truss.default_config()
        reference_config.update(span=2400.,end=[2400.,0.,0.],height=1000.,reference_mode="DraftLine",
                                reference_source=line.Name,reference_edge="Edge1",reference_linked=linked)
        reference_owner=truss.apply_truss(document,reference_config)
        panel=controllers.open_truss_panel(document,reference_owner)
        settle(panel)
        reference_before=persisted(document,reference_owner)
        def reference_fields(editor):
            fields=editor.fields
            controls=fields.controls
            editor.tabs.setCurrentWidget(fields.geometry_scroll)
            check("reference_presentation_"+str(linked),panel.keep_reference_link.isChecked()==linked
                  and (line.Name in fields.reference_summary.text() and not fields.reference_summary.isHidden()
                       if linked else fields.reference_summary.text()=="" and fields.reference_summary.isHidden()))
            check("no_redundant_reference_"+str(linked),"Snapshot" not in fields.reference_summary.text()
                  and "Face externa" not in fields.reference_summary.text())
            check("reference_coordinates_only_in_panel_"+str(linked),
                  not hasattr(fields,"advanced_toggle")
                  and not any(key.startswith(("start_inputs","end_inputs","normal_inputs")) for key in controls)
                  and len(panel.start_inputs)==len(panel.end_inputs)==len(panel.normal_inputs)==3)
            check("reference_edit_does_not_write_"+str(linked),panel._valid
                  and panel.session.config["reference_linked"]==linked
                  and panel.session.config["reference_source"]==line.Name
                  and persisted(document,reference_owner)==reference_before)
            editor.grab().save(str(output/("reference_"+str(linked)+".png")))
        modal("reference_"+str(linked),panel,panel.editor_button,reference_fields)
        if not linked:
            panel.start_inputs[0].setValue(100.)
            settle(panel)
            check("snapshot_coordinate_edit_from_panel",panel._valid
                  and panel.session.config["start"][0]==100.)
            panel.start_inputs[0].setValue(0.)
            settle(panel)
        panel.reference_alignment.setCurrentIndex(panel.reference_alignment.findData("TopChordSupports"))
        settle(panel)
        modal("reference_alignment_"+str(linked),panel,panel.editor_button,lambda editor:check(
            "panel_alignment_synchronized_"+str(linked),editor.fields.controls["reference_alignment"].currentData()
            ==panel.session.config["reference_alignment"]=="TopChordSupports"))
        panel.reject()
        drain()
        if linked:
            document.removeObject(line.Name)
            invalid_before=persisted(document,reference_owner)
            panel=controllers.open_truss_panel(document,reference_owner)
            settle(panel)
            check("invalid_associative_owner_opens_panel",not panel._valid and panel.session.valid)
            def repair_reference(editor):
                editor.tabs.setCurrentWidget(editor.fields.geometry_scroll)
                check("invalid_reference_opens_editor_without_graph",not editor.canvas.isEnabled()
                      and not editor.topology_toolbar.isEnabled() and panel.keep_reference_link.isChecked())
                check("invalid_reference_open_has_no_write",persisted(document,reference_owner)==invalid_before)
            modal("invalid_reference",panel,panel.editor_button,repair_reference)
            panel.keep_reference_link.setChecked(False)
            settle(panel)
            modal("repaired_reference",panel,panel.editor_button,lambda editor:check(
                "invalid_reference_repaired_same_session",panel._valid and editor.canvas.isEnabled()
                and editor.topology_toolbar.isEnabled() and editor.connections_scroll.isEnabled()
                and not panel.session.config["reference_linked"]))
            check("invalid_reference_repair_is_still_draft",persisted(document,reference_owner)==invalid_before)
            check("reference_repair_apply",panel.apply() and not reference_owner.ReferenceLinked)
            panel.reject()
            drain()

    # Activation leaves the task session available; only its modal view closes.
    panel = controllers.open_truss_panel(document, owner)
    settle(panel)
    panel.height.setValue(1500.)
    settle(panel)
    draft = deepcopy(panel.session.config)
    others = []

    def switch_document(editor):
        nested_profile("document_switch",editor,lambda _dialog:others.append(App.newDocument("OtherTrussEditorGate")))
        check("activation_closes_only_editor", not editor.isVisible()
              and not panel._closed and not panel.session.closed
              and panel.session.config == draft)

    modal("document_switch", panel, panel.editor_button, switch_document)
    App.setActiveDocument(document.Name)
    settle(panel)
    check("return_to_document_retains_draft", panel._valid and panel.session.config == draft)
    panel.reject()
    drain()
    App.closeDocument(others[0].Name)

    # Exact Working Plane toolbar handoff destroys the task and its open editor.
    panel = controllers.open_truss_panel(document, owner)
    settle(panel)
    panel._update_preview3d()
    before_wp = persisted(document, owner)
    hidden_projection=panel._editor_controls

    def working_plane(editor):
        nested_profile("wp",editor,lambda _dialog:Gui.draftToolBar.selectplane())
        drain()
        check("wp_handoff_closes_session", panel._closed and panel.session.closed
              and panel.controller._preview is None and not panel.controller._point_callbacks)
        check("wp_command_survives_editor_cleanup", type(App.activeDraftCommand).__name__ == "Draft_SelectPlane"
              and bool(Gui.Control.activeDialog()))

    modal("working_plane", panel, panel.editor_button, working_plane)
    check("wp_releases_hidden_projection",not shiboken6.isValid(hidden_projection))
    check("wp_preserves_document", persisted(document, owner) == before_wp)
    App.activeDraftCommand.finish()
    drain()

    # Native document auto-close releases the modal and its scoped observer.
    panel = controllers.open_truss_panel(document, owner)
    settle(panel)
    panel._update_preview3d()
    document_name = document.Name
    save_path=output/"editor_tabs.FCStd"
    saved_owner=owner.Name
    saved_config=truss.config_from_object(owner,resolve_reference=False)
    saved_applied=owner.AppliedState
    document.saveAs(str(save_path))

    def close_document(editor):
        nested_profile("document_close",editor,lambda _dialog:App.closeDocument(document_name))
        drain()
        check("document_close_releases_session", panel._closed and panel.session.closed
              and panel.controller._preview is None and not panel.controller._point_callbacks
              and controllers._active_panel is None)

    modal("document_close", panel, panel.editor_button, close_document)
    check("no_remaining_truss_editor", controllers._active_panel is None
          and panel._topology_editor is None)
    reopened=App.openDocument(str(save_path))
    restored=reopened.getObject(saved_owner)
    (output/"save_reopen_state.json").write_text(json.dumps(dict(
        before=saved_config,after=truss.config_from_object(restored,resolve_reference=False),
        applied_before=saved_applied,applied_after=restored.AppliedState),indent=2))
    restored_config=truss.config_from_object(restored,resolve_reference=False)
    # Native Placement matrix/quaternion round-trip has floating point roundoff.
    # All non-vector settings (including Custom, assemblies and intents) stay exact.
    for key in ("start","end","plane_normal"):
        check("save_reopen_"+key,len(restored_config[key])==len(saved_config[key])
              and all(isclose(a,b,rel_tol=1e-12,abs_tol=1e-8)
                      for a,b in zip(restored_config[key],saved_config[key])))
    check("editor_changes_save_reopen",{k:v for k,v in restored_config.items()
          if k not in ("start","end","plane_normal")}=={k:v for k,v in saved_config.items()
          if k not in ("start","end","plane_normal")} and restored.AppliedState==saved_applied)
    App.closeDocument(reopened.Name)
    legacy_doc=App.newDocument("TrussTaskPanelLegacy")
    legacy_config=truss.default_config()
    legacy_config.pop("reference_surface")
    legacy_config.update(topology_preset="Warren",span=2400.,end=[2400.,0.,0.],height=1000.)
    legacy=truss.apply_truss(legacy_doc,legacy_config)
    for name in ("LeftEndHeight","RightEndHeight","LinkEndHeights","ReferenceAlignment","NominalSpan"):
        legacy.removeProperty(name)
    legacy_path=output/"legacy_taskpanel.fcstd"
    legacy_doc.saveAs(str(legacy_path))
    App.closeDocument(legacy_doc.Name)
    legacy_doc=App.openDocument(str(legacy_path))
    legacy_doc.UndoMode=1
    legacy=legacy_doc.getObject("StructuralTruss")
    legacy_doc.recompute()
    from freecad.SteelStructures.trusses.physical_mass import read_physical_mass
    legacy_mass=read_physical_mass(legacy)
    check("legacy_physical_mass_available",legacy_mass.available)
    legacy_before=persisted(legacy_doc,legacy)
    shapes_before=[(member.Name,member.Shape.Volume,list(member.Placement.toMatrix().A))
                   for member in legacy.GeneratedMembers]
    check("legacy_restored_without_face_marker","reference_surface" not in legacy_before["requested"])
    panel=controllers.open_truss_panel(legacy_doc,legacy)
    settle(panel)
    check("legacy_fields_load_exact_frame",panel._valid and all(panel._read_vector(fields)==legacy_before["requested"][key]
          for key,fields in (("start",panel.start_inputs),("end",panel.end_inputs),("plane_normal",panel.normal_inputs))))
    panel.reject()
    drain()
    check("legacy_open_cancel_preserves_document",persisted(legacy_doc,legacy)==legacy_before
          and [(member.Name,member.Shape.Volume,list(member.Placement.toMatrix().A))
               for member in legacy.GeneratedMembers]==shapes_before)
    check("legacy_open_cancel_preserves_mass",read_physical_mass(legacy).mass_kg==legacy_mass.mass_kg)
    App.closeDocument(legacy_doc.Name)
    pending_doc=App.newDocument("TrussPartialInputClose")
    pending_errors=[]
    previous_hook=sys.excepthook
    sys.excepthook=lambda kind,error,trace:pending_errors.append(str(error))
    try:
        for index in range(3):
            panel=controllers.open_truss_panel(pending_doc)
            settle(panel)
            panel.advanced_header.button.setChecked(True)
            panel.form.grab()
            QtWidgets.QApplication.setActiveWindow(Gui.getMainWindow())
            field=panel.start_inputs[0]
            field.setFocus()
            drain()
            check("partial_close_focus_"+str(index),field.hasFocus())
            field.selectAll()
            QtTest.QTest.keyClicks(field,"-")
            form=panel.form
            panel.reject()
            QtCore.QCoreApplication.sendPostedEvents(None,QtCore.QEvent.DeferredDelete)
            drain()
            check("partial_close_releases_fields_"+str(index),panel._closed and panel.session.closed
                  and panel.controller.closed and not shiboken6.isValid(field)
                  and not shiboken6.isValid(form) and not pending_doc.Objects and not pending_errors)
    finally:
        sys.excepthook=previous_hook
        App.closeDocument(pending_doc.Name)
    return dict(ok=True, version=App.Version()[:3], checks=checks)


if os.environ.get("SS_DUOPITCH_ROOT"):
    import FreeCAD as App
    from PySide import QtCore, QtWidgets
    root = Path(os.environ["SS_DUOPITCH_ROOT"])
    out = Path(os.environ["SS_DUOPITCH_OUT"])
    sys.path.insert(0, str(root))
    import freecad
    freecad.__path__.insert(0, str(root / "freecad"))

    def launch():
        try:
            result = run(out)
        except Exception:
            result = dict(ok=False, error=traceback.format_exc())
            App.Console.PrintError(result["error"])
        (out / "result.json").write_text(json.dumps(result, indent=2))
        for name in tuple(App.listDocuments()):
            App.closeDocument(name)
        QtCore.QTimer.singleShot(0, QtWidgets.QApplication.quit)

    QtCore.QTimer.singleShot(500, launch)
