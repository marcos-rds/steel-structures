"""C4-B surgical physical + truss/Qt gate. Only creates a new document.

Load by file path (other workbenches can own the package 'tests'). Call run().
The modeless editor exists only within this call and is closed in finally.
"""
from dataclasses import replace
import importlib.util
import json
import math
from pathlib import Path


def run(output_directory):
    import FreeCAD as App
    import FreeCADGui as Gui
    from PySide import QtWidgets
    from freecad.SteelStructures import assembly, truss
    from freecad.SteelStructures.assemblies import MemberFrame, SectionTransform
    from freecad.SteelStructures.assemblies.attachment import resolve_pair_attachment
    from freecad.SteelStructures.trusses.interconnector_options import default_connector
    from freecad.SteelStructures.trusses.assemblies import configure_assembly
    from freecad.SteelStructures.interactive.assembly_editor import AssemblyEditor
    from freecad.SteelStructures.interactive.truss_controller import TrussController
    from freecad.SteelStructures.interactive.truss_task_panel import TrussTaskPanel

    loader = importlib.util.spec_from_file_location("ss_c4b_specs", Path(__file__).with_name("assemblies_c4a_fixtures.py"))
    fixtures = importlib.util.module_from_spec(loader)
    loader.loader.exec_module(fixtures)
    specs = fixtures.proof_specs()
    output = Path(output_directory)
    output.mkdir(parents=True, exist_ok=True)
    doc = App.newDocument("AssembliesC4B")
    doc.UndoMode = 1
    checks, owners, inputs = [], [], []

    def check(name, valid):
        checks.append(dict(check=name, passed=bool(valid)))
        (output/"progress.json").write_text(json.dumps(checks, ensure_ascii=False, indent=2), encoding="utf8")
        if not valid:
            raise AssertionError(name)

    def snapshot(owner):
        return (owner.AssemblyState, {c.GenerationKey: (c.Name, c.Shape.Volume, tuple(c.StartPoint),
                tuple(c.EndPoint), tuple(c.Placement.Rotation.Q), c.StartExtension.Value,
                c.EndFixedReferenceOffset.Value) for c in owner.AssemblyMembers})

    def same(a,b):
        return a[0]==b[0] and a[1].keys()==b[1].keys() and all(
            x[0]==b[1][k][0] and math.isclose(x[1],b[1][k][1],abs_tol=1e-5,rel_tol=1e-12)
            and all(math.dist(x[j],b[1][k][j])<1e-7 for j in (2,3,4)) and x[5:]==b[1][k][5:]
            for k,x in a[1].items())

    cases = (("SpacerPlate","InnerFaces",specs[4]),("Battens","FaceA",specs[4]),
             ("Battens","Both",specs[4]),("SingleLacing","FaceA",specs[5]),
             ("DoubleLacing","Both",specs[5]),("SpacerPlate","InnerFaces",specs[6]),
             ("DoubleLacing","Both",specs[5]))
    for index,(kind,plane,base) in enumerate(cases):
        connector=replace(default_connector(kind), attachment_plane=plane, start_offset=100.,end_offset=150.)
        spec=replace(base,interconnectors=(connector,))
        x,y=(index%4)*700.,(index//4)*1500.
        axis=((x,y,0.),(x,y,1000.))
        u=(1.,0.,0.)
        if index==6:
            axis=((x,y,0.),(x+600.,y+600.,600.))
            u=(1.,-1.,0.)
        frame=MemberFrame.from_axis(axis,u)
        owner=doc.addObject("App::FeaturePython","AttachmentProof")
        owner.Label=f"{index+1:02d} · {kind} · {plane}"
        children=assembly.apply_assembly(owner,axis,frame,spec,allow_structural=True)
        realized,_,_,_=assembly.prepare_assembly(owner,axis,frame,spec)
        pair=resolve_pair_attachment(axis,realized.components,("A","B"))
        reference=App.Placement(App.Vector(*pair.origin),App.Rotation(
            App.Vector(*pair.d),App.Vector(*pair.n),App.Vector(*pair.w),"ZXY"))
        valid=True
        for item in realized.elements:
            child=children[item.stable_identity]
            valid=valid and child.Shape.isValid() and child.Shape.Volume>0 and child.GenerationStatus=="Valid"
            valid=valid and (child.StartPoint-App.Vector(*item.start_global)).Length<1e-7
            valid=valid and (child.EndPoint-App.Vector(*item.end_global)).Length<1e-7
            valid=valid and (child.Placement.Rotation.multVec(App.Vector(0,0,1))-App.Vector(*item.orientation.w)).Length<1e-7
        for item in realized.interconnectors:
            child=children[item.stable_identity]
            projected=child.Shape.copy()
            projected.Placement=reference.inverse().multiply(projected.Placement)
            if kind=="SpacerPlate":
                valid=valid and abs(child.Length.Value-pair.inner_gap)<1e-7
            else:
                face=pair.face_plane(item.attachment_plane)
                bound=projected.BoundBox.YMin if item.attachment_plane=="FaceA" else projected.BoundBox.YMax
                valid=valid and abs(bound-face)<2e-5
                if kind=="Battens":
                    valid=valid and abs(child.Length.Value-pair.outer_span)<1e-7
                    valid=valid and abs(projected.BoundBox.XMin-pair.a_d[0])<2e-5
                    valid=valid and abs(projected.BoundBox.XMax-pair.b_d[1])<2e-5
        # Actual OCC intersection on the representative face members, not only inputs.
        if kind!="SpacerPlate":
            representative=[realized.interconnectors[0]]
            if plane=="Both":
                representative.append(next(c for c in realized.interconnectors if c.attachment_plane=="FaceB"))
            for item in representative:
                child=children[item.stable_identity]
                for component in realized.components:
                    common=child.Shape.common(children[component.stable_identity].Shape)
                    valid=valid and common.Volume<1e-4
        check(f"{index+1}. {kind}/{plane}: sólidos, span, tangência e frame"+(" inclinado" if index==6 else ""),valid)
        owners.append(owner)
        inputs.append((axis,frame,spec))

    owner=owners[1]
    axis,frame,spec=inputs[1]
    before=snapshot(owner)
    invalid=replace(spec,components=(spec.components[0],replace(spec.components[1],section_transform=SectionTransform(90))))
    try:
        assembly.apply_assembly(owner,axis,frame,invalid)
    except ValueError as exc:
        check("8. Faces não coplanares: conflito sem mutação","não são coplanares" in str(exc) and same(before,snapshot(owner)))
    else:
        raise AssertionError("Faces não coplanares aceitas")

    child=next(c for c in owner.AssemblyMembers if c.AssemblyElementKind=="Interconnector")
    child.StartExtension=11.
    child.EndAdjustmentMode="Fixed"
    child.EndFixedReferenceOffset=-7.
    doc.recompute()
    names={c.GenerationKey:c.Name for c in owner.AssemblyMembers}
    face_b=replace(spec,interconnectors=(replace(spec.interconnectors[0],attachment_plane="FaceB",start_offset=120.),))
    assembly.apply_assembly(owner,axis,frame,face_b)
    check("9. FaceA→FaceB: mesmos objetos e ajustes preservados",
        names=={c.GenerationKey:c.Name for c in owner.AssemblyMembers} and child.StartExtension.Value==11.
        and child.EndFixedReferenceOffset.Value==-7.)
    inputs[1]=axis,frame,face_b

    before=snapshot(owner)
    both=replace(face_b,interconnectors=(replace(face_b.interconnectors[0],attachment_plane="Both"),))
    assembly.apply_assembly(owner,axis,frame,both,allow_structural=True)
    after=snapshot(owner)
    doc.undo();doc.recompute()
    undo=same(before,snapshot(owner))
    doc.redo();doc.recompute()
    redo=same(after,snapshot(owner))
    assembly.apply_assembly(owner,axis,frame,face_b,allow_structural=True)
    check("10. Both e retorno: Undo/Redo e ramo primário preservado",undo and redo and same(before,snapshot(owner)))

    names_before={o.Name for o in doc.Objects}
    before=snapshot(owner)
    original=assembly.apply_result
    def fail_on_new(child,result,color=None):
        original(child,result,color)
        if child.Name not in names_before:
            raise RuntimeError("falha C4-B injetada")
    assembly.apply_result=fail_on_new
    try:
        try:
            assembly.apply_assembly(owner,axis,frame,both,allow_structural=True)
        except RuntimeError as exc:
            if "injetada" not in str(exc):raise
        else:raise AssertionError("Rollback não exercitado")
    finally:
        assembly.apply_result=original
    check("11. Rollback após criação parcial",same(before,snapshot(owner)) and names_before=={o.Name for o in doc.Objects})

    config=truss.default_config()
    config.update(span=2400.,height=700.,panel_count=4,start=[0.,3500.,0.],end=[2400.,3500.,0.])
    config["role_specs"]["TOP_CHORD"]=configure_assembly(dict(config["role_specs"]["TOP_CHORD"],rotation=0.),
        "SpacedPair",240.,interconnectors=(replace(default_connector("DoubleLacing"),attachment_plane="Both"),))
    obj=truss.apply_truss(doc,config)
    top=next(g for g in obj.RoleGroups if g.TrussRole=="TOP_CHORD")
    subgroup=next(g for g in top.Group if getattr(g,"AssemblyInterconnectorGroup",False))
    all_top=[c for c in obj.GeneratedMembers if c.RunKey.startswith("TOP_CHORD")]
    # Use actual subgroup membership (run key vocabulary is not a label contract).
    connectors=list(subgroup.Group)
    valid=len(connectors)==12 and all(c.AssemblyElementKind=="Interconnector" for c in connectors)
    valid=valid and all(c.GenerationOwner==obj and c not in obj.OutList for c in obj.GeneratedMembers)
    top.ViewObject.Visibility=False
    valid=valid and all(not c.ViewObject.Visibility for c in connectors)
    top.ViewObject.Visibility=True
    valid=valid and all(c.ViewObject.Visibility for c in connectors)
    obj.ViewObject.Visibility=False
    valid=valid and all(not c.ViewObject.Visibility for c in obj.GeneratedMembers)
    obj.ViewObject.Visibility=True
    controller=TrussController(doc,obj)
    before_names={o.Name for o in doc.Objects}
    controller.preview3d(config)
    valid=valid and len(controller._preview.shape.Solids)==len(obj.GeneratedMembers) and before_names=={o.Name for o in doc.Objects}
    controller.cancel()
    check("12. Treliça: árvore, DAG, visibilidade e preview 3D sem objetos temporários",valid)

    original_state=obj.AppliedState
    editor=AssemblyEditor(doc,"Banzo superior",config["role_specs"]["TOP_CHORD"],nominal_lengths=(2400.,))
    editor.setModal(False)
    def events():
        QtWidgets.QApplication.processEvents();QtWidgets.QApplication.processEvents()
    try:
        editor.show();events()
        editor.connectors.kind.setCurrentIndex(editor.connectors.kind.findData("Battens"));events()
        editor.connectors.plane.setCurrentIndex(editor.connectors.plane.findData("Both"));events()
        editor.grab().save(str(output/"editor-battens.png"))
        valid=editor._valid_composition and len(editor.preview.model["attachments"])==2
        editor.connectors.kind.setCurrentIndex(editor.connectors.kind.findData("SingleLacing"));events()
        editor.connectors.start_side.setCurrentIndex(1);events()
        editor.connectors.distribution.setCurrentIndex(1)
        editor.connectors.spacing.setValue(600.)
        editor.connectors.start.setValue(100.);events()
        valid=valid and editor._valid_composition and editor.role_spec()["assembly_spec"]["spec"]["interconnectors"][0]["start_side"]=="B"
        editor.grab().save(str(output/"editor-lacing.png"))
        editor.connectors.kind.setCurrentIndex(editor.connectors.kind.findData("SpacerPlate"));events()
        valid=valid and editor._valid_composition and editor.connectors.inner_position.isVisible()
        editor.grab().save(str(output/"editor-spacer.png"))
        editor.connectors.start.setValue(3000.);events()
        valid=valid and not editor._valid_composition and not editor.buttons.button(QtWidgets.QDialogButtonBox.Ok).isEnabled()
        editor.reject()
        valid=valid and obj.AppliedState==original_state and before_names=={o.Name for o in doc.Objects}
    finally:
        editor.close();editor.deleteLater()
    panel=TrussTaskPanel(doc,TrussController(doc,obj),config)
    try:
        panel.show_3d.setChecked(False)
        valid=valid and panel._role_nominal_lengths("TOP_CHORD")== (2400.,)
        panel.reject()
    finally:
        panel.form.close();panel.form.deleteLater()
    check("13. Qt real: controles, previews, validação e Cancelar sem mutação",valid)

    # Removing Both's secondary subgroup members must not be an external-reference conflict.
    changed=json.loads(json.dumps(config))
    role=changed["role_specs"]["TOP_CHORD"]
    connector=truss.build_candidate(changed).config["role_specs"]["TOP_CHORD"]["assembly_spec"]["spec"]["interconnectors"][0]
    role["assembly_spec"]["spec"]["interconnectors"][0]["attachment_plane"]="FaceB"
    old_names={c.GenerationKey:c.Name for c in obj.GeneratedMembers}
    truss.apply_truss(doc,changed,obj)
    primary=all(old_names[c.GenerationKey]==c.Name for c in obj.GeneratedMembers)
    role["assembly_spec"]["spec"]["interconnectors"]=[]
    truss.apply_truss(doc,changed,obj)
    check("14. Regeneração na Treliça remove ramos/subgrupo e preserva sobreviventes",primary and
        not any(getattr(g,"AssemblyInterconnectorGroup",False) for group in obj.RoleGroups for g in group.Group))
    truss.apply_truss(doc,config,obj)

    before={owner.Name:snapshot(owner) for owner in owners}
    truss_name=obj.Name
    members_before={c.GenerationKey:c.Name for c in obj.GeneratedMembers}
    path=output/"AssembliesC4B.FCStd"
    doc.recompute();doc.saveAs(str(path))
    App.closeDocument(doc.Name)
    doc=App.openDocument(str(path))
    for child in doc.Objects:
        if hasattr(child,"GenerationOwner"):child.touch()
    doc.recompute()
    obj=doc.getObject(truss_name)
    valid=all(same(state,snapshot(doc.getObject(name))) for name,state in before.items())
    valid=valid and members_before=={c.GenerationKey:c.Name for c in obj.GeneratedMembers} and not obj.NeedsRegeneration
    valid=valid and all(c.Shape.isValid() and c.Shape.Volume>0 and c.GenerationStatus=="Valid" for c in obj.GeneratedMembers)
    check("15. Save/reopen/recompute: assemblies e Treliça preservadas",valid)
    Gui.activeDocument().activeView().viewAxonometric();Gui.activeDocument().activeView().fitAll()
    Gui.activeDocument().activeView().saveImage(str(output/"assemblies-c4b.png"),1500,1100,"Current")
    report=dict(passed=True,freecad_version=App.Version()[:3],checks=checks,document=str(path))
    (output/"report.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf8")
    print(json.dumps(report,ensure_ascii=False))
    return report
