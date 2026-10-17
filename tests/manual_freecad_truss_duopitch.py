"""Focused OCC/document gate. Run only in isolated FreeCAD 1.1.4 process."""
import copy
import json
import math
import os
from pathlib import Path
import sys
import traceback


def run(output):
    import FreeCAD as App
    import Draft
    from freecad.SteelStructures import truss, profile_catalog
    from freecad.SteelStructures.trusses.assemblies import configure_assembly
    from freecad.SteelStructures.trusses.interconnector_options import default_connector
    from freecad.SteelStructures.trusses.realization import reference_frame, transform_point
    from freecad.SteelStructures.trusses.serialization import decode_state
    from freecad.SteelStructures.trusses.preset_contracts import compatible_presets
    from freecad.SteelStructures.trusses.support_alignment_freecad import support_sections
    from freecad.SteelStructures.trusses.support_alignment_freecad import validate_support_alignment
    from dataclasses import asdict

    checks = []
    doc = App.newDocument("DuoPitchGate")
    def check(name, condition):
        if not condition:
            (output/"failure.json").write_text(json.dumps(dict(check=name,owners=[dict(
                name=o.Name,state=o.GenerationState,message=o.GenerationMessage,
                needs=o.NeedsRegeneration) for o in doc.Objects if hasattr(o,"AppliedState")]),indent=2))
            raise AssertionError(name)
        checks.append(name)
        (output / "checks.json").write_text(json.dumps(checks, indent=2))

    def valid(obj):
        truss.bound_children(obj, decode_state(obj.AppliedState))
        return (obj.GenerationState == "Valid" and not obj.NeedsRegeneration
            and all(c.Shape.isValid() and c.Shape.Volume > 0 and c.GenerationStatus == "Valid"
                    and c.GenerationOwner == obj for c in obj.GeneratedMembers))

    def snapshot(obj):
        return {c.GenerationKey: (c.Name, tuple(c.StartPoint), tuple(c.EndPoint), c.Shape.Volume)
                for c in obj.GeneratedMembers}

    def same(a,b):
        return a.keys()==b.keys() and all(a[k][:3]==b[k][:3] and
            math.isclose(a[k][3],b[k][3],rel_tol=1e-12,abs_tol=1e-5) for k in a)

    def physical(obj):
        c = truss.build_candidate(truss.config_from_object(obj))
        prepared = truss.prepare_batch(c, truss.bound_children(obj, decode_state(obj.AppliedState)))
        heights = support_sections(c, prepared)
        check("physical_OCC_sections_"+obj.Name, all(abs(y-p[1]) < 1e-5
            for y,p in zip(heights, c.config["support_reference_local"])))
        frame = reference_frame(c.config)
        for q,p in zip(c.config["support_reference_local"], (c.config["start"],c.config["end"])):
            check("support_world_coincidence_"+obj.Name, math.dist(transform_point(q,frame),p)<1e-6)

    base = truss.default_config()
    base.update(envelope_type="DuoPitch",span=3000.,end=[3000.,0.,0.],height=900.,panel_count=6)
    # A real prior axis-reference state, not a legacy label on new geometry.
    base.pop("reference_surface")
    # First exercise actual existing document with missing additive properties.
    legacy = truss.apply_truss(doc, base)
    before = snapshot(legacy)
    for name in ("LeftEndHeight","RightEndHeight","LinkEndHeights","ReferenceAlignment","NominalSpan"):
        legacy.removeProperty(name)
    path = output / "legacy.fcstd"
    doc.saveAs(str(path))
    name = doc.Name
    App.closeDocument(name)
    doc = App.openDocument(str(path))
    legacy = doc.getObject("StructuralTruss")
    doc.recompute()
    check("legacy_additive_restore_zero_bottom", valid(legacy) and legacy.LeftEndHeight.Value == 0
          and str(legacy.ReferenceAlignment)=="BottomChord" and same(snapshot(legacy),before))
    check("legacy_restore_does_not_opt_into_face", "reference_surface" not in truss.config_from_object(legacy))
    accepted=legacy.AppliedState
    original_apply=truss.apply_result
    calls=[]
    def fail_second(*args,**kwargs):
        calls.append(1)
        if len(calls)==2:
            raise RuntimeError("Injected native rollback gate failure")
        return original_apply(*args,**kwargs)
    truss.apply_result=fail_second
    try:
        legacy.LeftEndHeight=100.
        doc.recompute()
    finally:
        truss.apply_result=original_apply
    check("native_automatic_rollback",len(calls)==2 and legacy.AppliedState==accepted
          and same(snapshot(legacy),before) and len(doc.Objects)==len(legacy.GeneratedMembers)+len(legacy.RoleGroups)+1)
    legacy.LeftEndHeight=0.
    doc.recompute()
    check("native_rollback_recovery",valid(legacy))
    # Native Property View mutations, including topology changes, Undo/Redo.
    doc.openTransaction("Alturas dos apoios")
    legacy.LeftEndHeight = 180.
    doc.recompute()
    check("property_zero_to_positive_linked", valid(legacy) and legacy.RightEndHeight.Value==180.)
    doc.commitTransaction()
    raised = snapshot(legacy)
    doc.undo()
    doc.recompute()
    check("undo_support_topology", valid(legacy) and legacy.LeftEndHeight.Value==0 and same(snapshot(legacy),before))
    doc.redo()
    doc.recompute()
    check("redo_support_topology", valid(legacy) and same(snapshot(legacy),raised))
    legacy.LinkEndHeights = False
    legacy.RightEndHeight = 320.
    doc.recompute()
    check("property_independent_heights", valid(legacy) and legacy.RightEndHeight.Value==320.)
    legacy.ReferenceAlignment = "TopChordSupports"
    doc.recompute()
    check("property_upper_alignment",valid(legacy))
    physical(legacy)
    legacy.ReferenceAlignment = "BottomChord"
    doc.recompute()
    check("property_bottom_alignment",valid(legacy) and legacy.NominalSpan.Value==3000.)

    # A materialized custom web migrates automatically via Property View.
    from freecad.SteelStructures.trusses.editing import materialize
    cc=copy.deepcopy(base)
    seed=truss.build_candidate(cc)
    cc.update(topology_mode="Custom",custom_topology=materialize(seed.graph,seed.config))
    custom=truss.apply_truss(doc,cc)
    custom.LeftEndHeight=150.
    doc.recompute()
    check("custom_property_split",valid(custom))
    custom.LeftEndHeight=0.
    doc.recompute()
    check("custom_property_merge",valid(custom))
    custom.ReferenceAlignment="TopChordSupports"
    doc.recompute()
    check("zero_height_upper",valid(custom))
    physical(custom)
    custom.LeftEndHeight=160.
    doc.recompute()
    check("equal_height_upper",valid(custom))
    physical(custom)

    # Actual members for every supported DuoPitch pattern; no other type altered.
    for preset in compatible_presets("DuoPitch"):
        c = copy.deepcopy(base)
        c.update(topology_preset=preset,panel_count=12,left_end_height=140.,right_end_height=280.,
                 link_end_heights=False,reference_alignment="TopChordSupports")
        obj = truss.apply_truss(doc,c)
        check("pattern_"+preset,valid(obj))
        physical(obj)

    # Physical sections: single families, insertion, roll, reflected compositions.
    fixtures = [('U 4" x 8,04',"Single",-90.,"centroid"),
                ('U 4" x 8,04',"DoubleChannelOutward",25.,"centroid"),
                ('L 40 x 4',"DoubleAngle",0.,"centroid"),
                ('U 4" x 8,04',"SpacedPair",90.,"centroid"),
                ('Barra Chata 50,8x6,35',"Single",23.,"bottom"),
                ('Barra Chata 50,8x6,35',"Single",0.,"top"),
                ('CHS 88,90x3',"Single",37.,"centroid")]
    for designation,assembly,rotation,insertion in fixtures:
        c=copy.deepcopy(base)
        c.update(start=[100.,200.,300.],end=[2500.,200.,2100.],span=3000.,
                 left_end_height=150.,right_end_height=300.,link_end_heights=False,
                 reference_alignment="TopChordSupports")
        role=c["role_specs"]["TOP_CHORD"]
        role.update(profile_ref=asdict(profile_catalog.ref_for_designation(designation)),
                    rotation=rotation,insertion=insertion)
        c["role_specs"]["TOP_CHORD"]=configure_assembly(role,assembly,160.)
        obj=truss.apply_truss(doc,c)
        check("inclined_"+assembly,valid(obj))
        physical(obj)

    # Interconnectors and existing Gusset through a rigid alignment change.
    from freecad.SteelStructures.trusses.connections import connection_participants
    c=copy.deepcopy(base)
    c.update(left_end_height=180.,right_end_height=300.,link_end_heights=False)
    c["role_specs"]["TOP_CHORD"]["rotation"]=0.
    c["role_specs"]["TOP_CHORD"]=configure_assembly(c["role_specs"]["TOP_CHORD"],
        "DoubleChannelOutward",160.,interconnectors=(default_connector("Battens"),))
    candidate=truss.build_candidate(c)
    node=next(n.key for n in candidate.graph.nodes if "TOP_CHORD" in n.affiliations
              and len(connection_participants(candidate,n.key))>=3)
    c["connection_intents"]={node:dict(form="Gusset",gusset=dict(plate_thickness=8.))}
    composite=truss.apply_truss(doc,c)
    plates=[p.Name for p in composite.GeneratedGussetPlates]
    check("composite_gusset_materialized",valid(composite) and bool(plates)
          and any(m.AssemblyElementKind=="Interconnector" for m in composite.GeneratedMembers))
    composite.ReferenceAlignment="TopChordSupports"
    doc.recompute()
    check("gussets_connectors_survive_alignment",valid(composite)
          and [p.Name for p in composite.GeneratedGussetPlates]==plates)
    physical(composite)
    # Prove that final physical verification rejects a removed support surface.
    import Part
    candidate=truss.build_candidate(truss.config_from_object(composite))
    prepared=truss.prepare_batch(candidate,truss.bound_children(composite,decode_state(composite.AppliedState)))
    for item in candidate.items:
        if item.role=="TOP_CHORD" and item.start_local[0]==0.:
            prepared[item.key].Shape=Part.Shape()
    try:
        validate_support_alignment(candidate,prepared)
    except ValueError:
        check("cut_removed_support_rejected",True)
    else:
        check("cut_removed_support_rejected",False)

    # Snapshot / associative line: update, restore and native Draft copy.
    line=Draft.make_line(App.Vector(100.,4000.,200.),App.Vector(2500.,4000.,2000.))
    doc.recompute()
    c=copy.deepcopy(base)
    c.update(reference_mode="DraftLine",reference_linked=True,reference_source=line.Name,
        left_end_height=180.,right_end_height=300.,link_end_heights=False,reference_alignment="TopChordSupports")
    linked=truss.apply_truss(doc,c)
    snapshot_config=truss.config_from_object(linked)
    snapshot_config.update(reference_linked=False)
    frozen=truss.apply_truss(doc,snapshot_config)
    frozen_before=snapshot(frozen)
    line.End = App.Vector(3100.,4000.,2450.)
    doc.recompute()
    check("associative_source_changed",valid(linked) and abs(linked.Span.Value-3750.)<1e-5)
    check("snapshot_source_independent",snapshot(frozen)==frozen_before)
    physical(linked)
    original=snapshot(frozen)
    doc.openTransaction("Draft copy aligned truss")
    duplicate=Draft.move([frozen],App.Vector(0.,3000.,400.),copy=True)
    doc.recompute()
    doc.commitTransaction()
    check("copy_aligned_independent",valid(duplicate) and snapshot(frozen)==original
          and not set(frozen.GeneratedMembers).intersection(duplicate.GeneratedMembers))
    duplicate.Height=1000.
    doc.recompute()
    check("copy_parametric_independent",valid(duplicate) and snapshot(frozen)==original)
    physical(duplicate)
    # Parallel shares the section query/frame/OCC verification, with no span
    # derivation and no dependency on latent DuoPitch endpoint heights.
    parallel_names=[]
    for index,(designation,assembly,rotation,insertion) in enumerate(fixtures):
        c=copy.deepcopy(base)
        c.update(envelope_type="Parallel",left_end_height=8000.,right_end_height=9000.,
                 link_end_heights=False,reference_alignment="TopChordSupports")
        if index % 3 == 1:
            c.update(start=[100.,200.,300.],end=[2500.,200.,2100.])
        elif index % 3 == 2:
            c.update(start=[2500.,200.,2100.],end=[100.,200.,300.])
        role=c["role_specs"]["TOP_CHORD"]
        role.update(profile_ref=asdict(profile_catalog.ref_for_designation(designation)),
                    rotation=rotation,insertion=insertion)
        c["role_specs"]["TOP_CHORD"]=configure_assembly(role,assembly,160.)
        obj=truss.apply_truss(doc,c)
        check("parallel_fixture_"+str(index),valid(obj) and obj.NominalSpan.Value==3000.)
        physical(obj)
        parallel_names.append(obj.Name)
    p=doc.getObject(parallel_names[0])
    top_snapshot=snapshot(p)
    count=len(doc.Objects)
    doc.openTransaction("Parallel reference property")
    p.ReferenceAlignment="BottomChord"
    doc.recompute()
    doc.commitTransaction()
    check("parallel_property_bottom",valid(p) and p.NominalSpan.Value==p.Span.Value)
    doc.undo()
    doc.recompute()
    check("parallel_undo_alignment",valid(p) and same(snapshot(p),top_snapshot))
    doc.redo()
    doc.recompute()
    check("parallel_redo_alignment",valid(p) and str(p.ReferenceAlignment)=="BottomChord")
    p.ReferenceAlignment="TopChordSupports"
    p.Height=1050.
    doc.recompute()
    check("parallel_property_height",valid(p) and len(doc.Objects)==count)
    physical(p)
    from freecad.SteelStructures.trusses.serialization import dumps,loads
    roles=loads(p.RoleSpecs)
    roles["TOP_CHORD"].update(rotation=23.,insertion="bottom",
        profile_ref=asdict(profile_catalog.ref_for_designation("Barra Chata 50,8x6,35")))
    p.RoleSpecs=dumps(roles)
    doc.recompute()
    check("parallel_property_profile",valid(p) and len(doc.Objects)==count)
    physical(p)
    # Explicit structural regeneration removes obsolete members permanently.
    old={m.Name for m in p.GeneratedMembers}
    c=truss.config_from_object(p)
    c.update(panel_count=4,top_continuity="SegmentAtEveryNode")
    truss.apply_truss(doc,c,p)
    new={m.Name for m in p.GeneratedMembers}
    check("parallel_regeneration_no_residue",valid(p)
          and all(doc.getObject(n) is None for n in old-new)
          and {m.Name for m in doc.Objects if getattr(m,"GenerationOwner",None)==p}==new)
    physical(p)
    # Parallel source update / snapshot and independently moved owner.
    c=truss.config_from_object(linked)
    c.update(envelope_type="Parallel")
    plinked=truss.apply_truss(doc,c)
    c=truss.config_from_object(plinked)
    c.update(reference_linked=False)
    pfrozen=truss.apply_truss(doc,c)
    unchanged=snapshot(pfrozen)
    line.End=App.Vector(3700.,4000.,2900.)
    doc.recompute()
    check("parallel_associative_and_snapshot",valid(plinked)
          and plinked.Span.Value==4500. and snapshot(pfrozen)==unchanged)
    physical(plinked)
    doc.openTransaction("Parallel Draft copy")
    pcopied=Draft.move([pfrozen],App.Vector(0.,2000.,500.),copy=True)
    doc.recompute()
    doc.commitTransaction()
    check("parallel_copy_independent",valid(pcopied) and snapshot(pfrozen)==unchanged
          and not set(pfrozen.GeneratedMembers).intersection(pcopied.GeneratedMembers))
    physical(pcopied)
    visible=[m.ViewObject.Visibility for m in pcopied.GeneratedMembers]
    pfrozen.ViewObject.Visibility=False
    check("parallel_hide_source_independent",visible==[m.ViewObject.Visibility for m in pcopied.GeneratedMembers])
    pfrozen.ViewObject.Visibility=True
    visible=[m.ViewObject.Visibility for m in pfrozen.GeneratedMembers]
    pcopied.ViewObject.Visibility=False
    check("parallel_hide_copy_independent",visible==[m.ViewObject.Visibility for m in pfrozen.GeneratedMembers])
    pcopied.ViewObject.Visibility=True
    pcopied.Height=1150.
    doc.recompute()
    check("parallel_copy_property_independent",valid(pcopied) and snapshot(pfrozen)==unchanged)
    physical(pcopied)
    bottom_names=[]
    for kind in ("Parallel","DuoPitch"):
        for assembly in ("Single","SpacedPair"):
            cfg=truss.default_config()
            cfg.update(envelope_type=kind,span=3000.,end=[3000.,0.,0.],height=900.,
                       left_end_height=180.,right_end_height=300.,link_end_heights=False)
            cfg["role_specs"]["BOTTOM_CHORD"]["rotation"]=23.
            cfg["role_specs"]["BOTTOM_CHORD"]=configure_assembly(
                cfg["role_specs"]["BOTTOM_CHORD"],assembly,80.)
            bottom=truss.apply_truss(doc,cfg)
            check("bottom_face_valid_"+kind+assembly,valid(bottom))
            physical(bottom)
            bottom_names.append(bottom.Name)
    owner_names=[legacy.Name,composite.Name,linked.Name,frozen.Name,duplicate.Name,custom.Name,
                 *parallel_names,plinked.Name,pfrozen.Name,pcopied.Name]
    path=output/"duopitch.fcstd"
    doc.saveAs(str(path))
    App.closeDocument(doc.Name)
    doc=App.openDocument(str(path))
    doc.recompute()
    check("save_reopen_owners",all(valid(doc.getObject(n)) for n in owner_names))
    for n in owner_names[1:]:
        physical(doc.getObject(n))
    for n in bottom_names:
        check("bottom_face_reopen_"+n,valid(doc.getObject(n)))
        physical(doc.getObject(n))
    copied=doc.getObject(owner_names[-1])
    source=doc.getObject(owner_names[-2])
    unchanged=snapshot(source)
    owned_names=[m.Name for m in copied.GeneratedMembers]+[g.Name for g in copied.RoleGroups]
    copied_name=copied.Name
    import FreeCADGui as Gui
    from PySide import QtCore,QtWidgets
    # Exercise the native GUI deletion callback, not Document.removeObject
    # (the latter intentionally bypasses ViewProvider lifecycle callbacks).
    def accept_delete_warning():
        for widget in QtWidgets.QApplication.topLevelWidgets():
            if isinstance(widget,QtWidgets.QMessageBox) and widget.isVisible():
                widget.done(QtWidgets.QMessageBox.Yes)
    delete_timer=QtCore.QTimer()
    delete_timer.timeout.connect(accept_delete_warning)
    Gui.Selection.clearSelection()
    Gui.Selection.addSelection(copied)
    delete_timer.start(100)
    Gui.runCommand("Std_Delete",0)
    delete_timer.stop()
    doc.recompute()
    check("parallel_delete_copy_no_residue",valid(source) and snapshot(source)==unchanged
          and all(doc.getObject(n) is None for n in owned_names))
    doc.undo()
    doc.recompute()
    check("parallel_undo_delete",valid(doc.getObject(copied_name)) and valid(source))
    doc.redo()
    doc.recompute()
    check("parallel_redo_delete",doc.getObject(copied_name) is None
          and all(doc.getObject(n) is None for n in owned_names) and valid(source))
    # Native Qt form smoke check and reviewable capture; no user session touched.
    from PySide import QtWidgets
    from freecad.SteelStructures.interactive.truss_controller import TrussController
    from freecad.SteelStructures.interactive.truss_task_panel import TrussTaskPanel
    target=doc.getObject(owner_names[3])
    panel=TrussTaskPanel(doc,TrussController(doc,target),truss.config_from_object(target))
    panel._preview_timer.stop()
    panel.show_3d.setChecked(False)
    panel.form.resize(480,950)
    panel.form.show()
    QtWidgets.QApplication.processEvents()
    check("native_Qt_upper_controls",panel._valid and panel.left_end_height.isVisible()
          and panel.reference_alignment.isVisible() and "apoios" in panel.span_label.text())
    panel.form.grab().save(str(output/"panel.png"))
    panel.preview.grab().save(str(output/"schematic.png"))
    check("native_Qt_no_permanent_height_note",not hasattr(panel,"pitch_note"))
    for kind,left,right in (("DuoPitch",180.,300.),("DuoPitch",1.,2.),
                            ("DuoPitch",0.,0.),("Parallel",0.,0.)):
        panel.envelope_type.setCurrentIndex(panel.envelope_type.findData(kind))
        panel.link_end_heights.setChecked(False)
        panel.left_end_height.setValue(left)
        panel.right_end_height.setValue(right)
        panel._preview_timer.stop()
        panel._refresh()
        # Hiding the pitched rows posts nested layout requests. Drain these
        # before capturing the settled form, as the normal GUI event loop does.
        for _ in range(3):
            QtWidgets.QApplication.sendPostedEvents(None,QtCore.QEvent.LayoutRequest)
            QtWidgets.QApplication.processEvents()
        check("native_Qt_model_"+kind+str(left),panel._valid and panel.reference_alignment.isVisible())
        if kind=="Parallel":
            panel.form.grab().save(str(output/"panel_parallel.png"))
        from freecad.SteelStructures.interactive.truss_preview import TrussPreview2D
        preview=TrussPreview2D()
        preview.set_model(panel.controller.preview(panel.get_config()))
        for width,height in ((320,170),(480,220),(640,250)):
            preview.resize(width,height)
            preview.show()
            QtWidgets.QApplication.processEvents()
            preview.grab().save(str(output/f"preview_{kind}_{left:g}_{width}.png"))
        preview.close()
    panel.reject()
    panel.form.close()
    return dict(ok=True,checks=checks,version=App.Version()[:3],document=str(path))


if os.environ.get("SS_DUOPITCH_ROOT"):
    import FreeCAD as App
    from PySide import QtCore, QtWidgets
    root=Path(os.environ["SS_DUOPITCH_ROOT"])
    out=Path(os.environ["SS_DUOPITCH_OUT"])
    sys.path.insert(0,str(root))
    import freecad
    freecad.__path__.insert(0,str(root/"freecad"))
    def launch():
        try:
            result=run(out)
        except Exception:
            result=dict(ok=False,error=traceback.format_exc())
            App.Console.PrintError(result["error"])
        (out/"result.json").write_text(json.dumps(result,indent=2))
        for name in tuple(App.listDocuments()):
            App.closeDocument(name)
        QtCore.QTimer.singleShot(0,QtWidgets.QApplication.quit)
    QtCore.QTimer.singleShot(500,launch)
