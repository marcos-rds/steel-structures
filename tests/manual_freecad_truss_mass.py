"""Isolated FreeCAD 1.1.4 physical-mass, applied-state and numeric gate."""
from copy import deepcopy
from dataclasses import asdict
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
    import Part
    from PySide import QtCore, QtWidgets
    from PySide6 import QtTest
    from freecad.SteelStructures import truss
    from freecad.SteelStructures.interactive import truss_controller as controllers
    from freecad.SteelStructures.interactive.truss_topology_editor import TopologyEditor
    from freecad.SteelStructures.trusses.assemblies import configure_assembly
    from freecad.SteelStructures.trusses.interconnector_options import default_connector
    from freecad.SteelStructures.trusses.physical_mass import read_physical_mass
    checks,results=[],{}
    def check(name,condition):
        if not condition: raise AssertionError(name)
        checks.append(name)
        (output/"checks.json").write_text(json.dumps(checks,indent=2))
    def report(label,owner,available=True):
        result=read_physical_mass(owner)
        results[label]=dict(asdict(result),mass_kg=result.mass_kg,linear_mass=result.linear_mass_kg_m,
                           owner_state=list(owner.State),children_states={child.Name:list(child.State) for child in owner.GeneratedMembers})
        (output/"mass_reports.json").write_text(json.dumps(results,indent=2))
        check(label+"_availability",result.available==available)
        if available:
            physical=list({child.Name:child for child in list(owner.GeneratedMembers)+list(owner.GeneratedGussetPlates)}.values())
            check(label+"_final_piece_sum",math.isclose(result.volume_mm3,math.fsum(child.Shape.Volume for child in physical),rel_tol=1e-12))
            check(label+"_density_and_linear",math.isclose(result.mass_kg,result.volume_mm3*.00000785,rel_tol=1e-12)
                  and math.isclose(result.linear_mass_kg_m,result.mass_kg/(result.support_distance_mm*.001),rel_tol=1e-12))
        return result
    def config(**changes):
        value=truss.default_config()
        value.update(span=2400.,end=[2400.,0.,0.],height=1000.,panel_count=6)
        value.update(changes)
        return value
    def settle(panel=None):
        QtWidgets.QApplication.processEvents()
        if panel is not None: panel._preview_timer.stop()
    doc=App.newDocument("TrussPhysicalMassGate")
    doc.UndoMode=1
    class Observer:
        count=0
        def slotRecomputedDocument(self,current):
            if current is doc: self.count+=1
    observer=Observer()
    App.addDocumentObserver(observer)
    try:
        plain=truss.apply_truss(doc,config())
        first=report("parallel_simple",plain)
        before=(observer.count,doc.UndoCount,plain.AppliedState,tuple(obj.Name for obj in doc.Objects))
        for _ in range(5): read_physical_mass(plain)
        check("reading_has_no_recompute_transaction_or_objects",before==(observer.count,doc.UndoCount,plain.AppliedState,tuple(obj.Name for obj in doc.Objects)))
        plain.ViewObject.Visibility=False
        check("hidden_pieces_are_counted",read_physical_mass(plain).mass_kg==first.mass_kg)
        plain.ViewObject.Visibility=True
        # Use the existing supported manual fitting pipeline; reader only sees final solids.
        child=plain.GeneratedMembers[0]
        previous={key:getattr(child,key) for key in ('StartExtension','StartAdjustmentMode','StartAdjustmentGeometryMode','StartFixedReferenceOffset','StartAdjustmentGap','StartFixedPlaneNormal')}
        child.StartExtension=20.
        child.StartAdjustmentMode='Fixed'
        child.StartAdjustmentGeometryMode='PlaneCut'
        child.StartFixedReferenceOffset=100.
        child.StartAdjustmentGap=2.
        child.StartFixedPlaneNormal=App.Vector(.2,0.,1.)
        doc.recompute()
        reduced=report('final_cut_shape',plain)
        check('cut_reduces_physical_mass',reduced.mass_kg<first.mass_kg)
        for key,value in previous.items(): setattr(child,key,value)
        doc.recompute()
        report('restored_cut_fixture',plain)
        duo=truss.apply_truss(doc,config(envelope_type="DuoPitch",start=[50.,100.,200.],end=[1490.,100.,2120.],
              left_end_height=200.,right_end_height=500.,link_end_heights=False,reference_alignment="TopChordSupports"))
        duo_mass=report("duopitch_inclined",duo)
        check("support_distance_is_not_nominal_span",math.isclose(duo_mass.support_distance_mm,2400.)
              and abs(duo_mass.support_distance_mm-duo_mass.nominal_span_mm)>1.)
        for kind in ("SpacerPlate","Battens","SingleLacing","DoubleLacing"):
            value=config()
            value["role_specs"]["TOP_CHORD"]=configure_assembly(value["role_specs"]["TOP_CHORD"],"SpacedPair",240.,
                interconnectors=(default_connector(kind),))
            if kind=="Battens":
                value["connection_intents"]={"B_S_MAIN_1_3":dict(form="Gusset",gusset=dict(plate_thickness=12.))}
            owner=truss.apply_truss(doc,value)
            result=report("composite_"+kind,owner)
            check("connector_identified_"+kind,any(child.AssemblyElementKind=="Interconnector" for child in owner.GeneratedMembers))
            if kind=="Battens": composite=owner
        check("physical_gusset_included",len(composite.GeneratedGussetPlates)==1
              and sum(piece.kind=="Gusset" for piece in read_physical_mass(composite).pieces)==1)
        # UI reads last applied solids. Pending drafts cannot acquire their mass.
        panel=controllers.open_truss_panel(doc,composite)
        settle(panel)
        editor=TopologyEditor(panel)
        editor.show()
        settle(panel)
        fields=editor.fields
        fields.sync()
        from freecad.SteelStructures.trusses.serialization import decode_state
        requested=panel.session.validated_candidate.config
        applied=decode_state(composite.AppliedState)["candidate"]["config"]
        (output/"ui_mass_state.json").write_text(json.dumps(dict(status=fields.mass_status.text(),tooltip=fields.mass_status.toolTip(),
            differences={key:[requested.get(key),applied.get(key)] for key in set(requested)|set(applied) if requested.get(key)!=applied.get(key)}),indent=2))
        check("applied_ui_mass",fields.information_values["mass"].text().endswith(" kg")
              and fields.mass_status.isHidden())
        check("mass_tooltip_density_supports_and_nominal_span","7850 kg/m³" in fields.mass_status.toolTip()
              and "P0–P1" in fields.mass_status.toolTip() and "Vão nominal derivado" in fields.mass_status.toolTip())
        panel.height.setValue(1200.1234567890123)
        settle(panel)
        fields.sync()
        check("draft_mass_waits_for_application",fields.mass_status.text()=="Aguardando aplicação"
              and fields.information_values["mass"].text()=="—")
        check("height_exact_after_sync",panel.height.value()==1200.1234567890123
              and fields.controls["height"].value()==1200.1234567890123)
        before=(observer.count,doc.UndoCount)
        check("physical_apply",panel.apply())
        settle(panel)
        check("apply_one_recompute",observer.count==before[0]+1)
        fields.sync()
        applied_mass=report("after_apply",composite)
        check("mass_updated_after_apply",fields.mass_status.isHidden()
              and fields.information_values["mass"].text()==fields.geometry_page.locale().toString(applied_mass.mass_kg,"f",2)+" kg")
        fields.geometry_page.grab().save(str(output/"mass_information.png"))
        before=(observer.count,doc.UndoCount)
        check("repeat_apply_no_extra_recompute",panel.apply() and before==(observer.count,doc.UndoCount))
        # A partial field must survive a sync and block application.
        spin=fields.controls["height"]
        QtWidgets.QApplication.setActiveWindow(editor)
        spin.setFocus()
        settle(panel)
        spin.lineEdit().selectAll()
        QtTest.QTest.keyClicks(spin,"1e")
        fields.sync()
        check("partial_editor_length_preserved",spin.lineEdit().text()=="1e")
        QtTest.QTest.keyClick(spin,QtCore.Qt.Key_Return)
        fields.sync()
        check("partial_editor_invalidates_without_overwriting",not panel._valid and spin.lineEdit().text()=="1e"
              and fields.information_values["mass"].text()=="—")
        # Panel owns the candidate; do not apply an uncommitted mirror edit.
        QtTest.QTest.keyClick(spin,QtCore.Qt.Key_Escape)
        fields.sync()
        check("editor_escape_recovers_candidate",panel._valid and fields.mass_status.isHidden())
        editor.close()
        editor.deleteLater()
        QtWidgets.QApplication.setActiveWindow(Gui.getMainWindow())
        panel.height.setFocus()
        settle(panel)
        panel.height.lineEdit().selectAll()
        QtTest.QTest.keyClicks(panel.height,"1300.12345678900 mm")
        panel.height.lineEdit().setSelection(3,5)
        panel._refresh()
        check("valid_pending_source_text_survives_refresh",panel.height.lineEdit().text()=="1300.12345678900 mm"
              and panel.height.lineEdit().selectedText()=="0.123")
        QtTest.QTest.keyClick(panel.height,QtCore.Qt.Key_Escape)
        check("valid_pending_escape_restores_applied_height",panel._valid and panel.height.value()==1200.1234567890123)
        panel.span.setFocus()
        settle(panel)
        panel.span.lineEdit().selectAll()
        QtTest.QTest.keyClicks(panel.span,"1e")
        before=(observer.count,doc.UndoCount,composite.AppliedState)
        check("partial_span_blocks_apply",not panel.apply() and before==(observer.count,doc.UndoCount,composite.AppliedState)
              and panel.span.lineEdit().text()=="1e")
        QtTest.QTest.keyClick(panel.span,QtCore.Qt.Key_Escape)
        check("span_escape_recovers_candidate",panel._valid)
        panel.height.setValue(1400.)
        settle(panel)
        panel.reject()
        check("cancel_after_apply_keeps_physical_mass",read_physical_mass(composite).mass_kg==applied_mass.mass_kg)
        doc.undo()
        doc.recompute()
        undo_mass=report("undo_apply",composite)
        check("undo_restores_previous_mass",not math.isclose(undo_mass.mass_kg,applied_mass.mass_kg,rel_tol=1e-8))
        doc.redo()
        doc.recompute()
        report("redo_apply",composite)
        check("redo_restores_applied_mass",math.isclose(read_physical_mass(composite).mass_kg,applied_mass.mass_kg,rel_tol=1e-12))
        before=read_physical_mass(composite).mass_kg
        doc.openTransaction("Copy for quantity gate")
        copied=Draft.move([composite],App.Vector(0.,5000.,0.),copy=True)
        doc.recompute()
        doc.commitTransaction()
        copy_mass=report("independent_copy",copied)
        check("copy_same_mass_disjoint_pieces",math.isclose(copy_mass.mass_kg,before,rel_tol=1e-12)
              and not set(piece.name for piece in copy_mass.pieces).intersection(piece.name for piece in read_physical_mass(composite).pieces))
        doc.removeObject(copied.Name)
        doc.recompute()
        check("delete_copy_preserves_source_mass",math.isclose(read_physical_mass(composite).mass_kg,before,rel_tol=1e-12))
        # Incomplete final geometry cannot be certified, even when an old positive Volume survives.
        child=composite.GeneratedMembers[0]
        old_status=child.GenerationStatus
        child.GenerationStatus="Erro: geometria anterior preservada"
        report("invalid_piece",composite,False)
        child.GenerationStatus=old_status
        doc.recompute()
        missing=composite.GeneratedGussetPlates
        composite.GeneratedGussetPlates=[]
        report("missing_gusset",composite,False)
        composite.GeneratedGussetPlates=missing
        doc.recompute()
        owner_names=[plain.Name,duo.Name,composite.Name]
        expected={name:read_physical_mass(doc.getObject(name)).mass_kg for name in owner_names}
        path=output/"physical_mass.FCStd"
        doc.saveAs(str(path))
        App.removeDocumentObserver(observer)
        App.closeDocument(doc.Name)
        doc=App.openDocument(str(path))
        doc.recompute()
        for name in owner_names:
            restored=report("reopened_"+name,doc.getObject(name))
            check("reopen_same_mass_"+name,math.isclose(restored.mass_kg,expected[name],rel_tol=1e-12))
        return dict(ok=True,version=App.Version()[:3],checks=checks)
    finally:
        App.removeDocumentObserver(observer)


if os.environ.get("SS_DUOPITCH_ROOT"):
    import FreeCAD as App
    from PySide import QtCore, QtWidgets
    root=Path(os.environ["SS_DUOPITCH_ROOT"])
    out=Path(os.environ["SS_DUOPITCH_OUT"])
    sys.path.insert(0,str(root))
    import freecad
    freecad.__path__.insert(0,str(root/"freecad"))
    def launch():
        try: result=run(out)
        except Exception:
            result=dict(ok=False,error=traceback.format_exc())
            App.Console.PrintError(result["error"])
        (out/"result.json").write_text(json.dumps(result,indent=2))
        for name in tuple(App.listDocuments()): App.closeDocument(name)
        QtCore.QTimer.singleShot(0,QtWidgets.QApplication.quit)
    QtCore.QTimer.singleShot(500,launch)
