"""Economical C4-A proof in real FreeCAD; creates only a new document.

Run run(output_directory) after loading current modules. Leaves six labelled
cases for inspection, saves/reopens optionally, and never edits user documents.
"""
from dataclasses import replace
import json
import math
from pathlib import Path


def run(output_directory=None):
    import FreeCAD as App
    import FreeCADGui as Gui
    from freecad.SteelStructures import assembly, profile_catalog
    from freecad.SteelStructures.assemblies import MemberFrame, DistributionSpec, SectionTransform
    from freecad.SteelStructures.assemblies.serialization import loads
    from freecad.SteelStructures.profiles.models import ProfileRef
    from freecad.SteelStructures.profiles.geometry import build_section_geometry
    from freecad.SteelStructures.assemblies.transforms import transform_section
    from freecad.SteelStructures.profiles.freecad_geometry import section_geometry_to_face
    # Other workbenches may already own the top-level package named "tests".
    import importlib.util
    loader = importlib.util.spec_from_file_location("ss_c4a_specs", Path(__file__).with_name("assemblies_c4a_fixtures.py"))
    fixtures = importlib.util.module_from_spec(loader)
    loader.loader.exec_module(fixtures)

    output = Path(output_directory) if output_directory else None
    if output:
        output.mkdir(parents=True, exist_ok=True)
    doc = App.newDocument("AssembliesC4A")
    doc.UndoMode = 1
    specs = fixtures.proof_specs()
    cases = [specs[0], specs[4], specs[5], specs[3], specs[6], specs[3]]
    cases[-1] = replace(cases[-1], interconnectors=(replace(cases[-1].interconnectors[0],
        section_transform=SectionTransform(37, True)),))
    titles = ("01 · U espaçados sem conexão", "02 · U com presilhas", "03 · U com treliçamento simples",
              "04 · U com treliçamento duplo", "05 · Cantoneiras com treliçamento", "06 · Conjunto inclinado")
    owners, inputs, checks = [], [], []

    def check(name, condition):
        checks.append(dict(check=name, passed=bool(condition)))
        if not condition:
            raise AssertionError(name)

    def snapshot(owner):
        return (owner.AssemblyState, {c.GenerationKey: (c.Name, c.Shape.Volume,
            tuple(c.StartPoint), tuple(c.EndPoint), tuple(c.Placement.Rotation.Q),
            c.AssemblySectionTransform, c.StartExtension.Value, c.EndFixedReferenceOffset.Value)
            for c in owner.AssemblyMembers})

    def same(before, after):
        if before[0] != after[0] or before[1].keys() != after[1].keys():
            return False
        for key, a in before[1].items():
            b = after[1][key]
            if (a[0] != b[0] or not math.isclose(a[1], b[1], rel_tol=1e-12, abs_tol=1e-5)
                    or any(math.dist(a[i], b[i]) > 1e-8 for i in (2, 3, 4)) or a[5:] != b[5:]):
                return False
        return True

    for i, spec in enumerate(cases):
        x, y = (i % 3)*700., (i//3)*1500.
        axis = ((x, y, 0.), (x, y, 1000.))
        u = (1., 0., 0.)
        if i == 5:
            axis = ((x, y, 0.), (x+600., y+600., 600.))
            u = (1., -1., 0.)
        frame = MemberFrame.from_axis(axis, u)
        owner = doc.addObject("App::FeaturePython", "AssemblyProof")
        owner.Label = titles[i]
        result = assembly.apply_assembly(owner, axis, frame, spec, allow_structural=True)
        realized, plan, _, _ = assembly.prepare_assembly(owner, axis, frame, spec)
        valid = not plan.structural and all(a.action == "UNCHANGED" for a in plan.actions)
        for item in realized.elements:
            child = result[item.stable_identity]
            valid = valid and child.Shape.isValid() and child.Shape.Volume > 0 and child.GenerationStatus == "Valid"
            valid = valid and (child.StartPoint-App.Vector(*item.start_global)).Length < 1e-7
            valid = valid and (child.EndPoint-App.Vector(*item.end_global)).Length < 1e-7
            valid = valid and all((child.Placement.Rotation.multVec(App.Vector(*local))-App.Vector(*expected)).Length < 1e-7
                for local, expected in (((1, 0, 0), item.orientation.u), ((0, 1, 0), item.orientation.v), ((0, 0, 1), item.orientation.w)))
            valid = valid and child.GenerationOwner == owner and child not in owner.OutList and owner in child.OutList
            valid = valid and child.OffsetX.Value == child.OffsetY.Value == 0
            if child.AssemblyElementKind == "Interconnector":
                valid = valid and child.ComponentKey == "" and child.InterconnectorKey == "WEB"
                geometry = build_section_geometry(profile_catalog.get(str(child.Profile)).definition)
                geometry, refs = transform_section(geometry, item.section_transform)
                insertion = next(r.point for r in refs if r.id == item.insertion_reference)
                face = section_geometry_to_face(geometry)
                face.translate(App.Vector(-insertion.x, -insertion.y, 0))
                local_shape = child.Shape.copy()
                local_shape.Placement = App.Placement()
                valid = valid and all(abs(getattr(local_shape.BoundBox, k)-getattr(face.BoundBox, k)) < 1e-6
                    for k in ("XMin", "XMax", "YMin", "YMax"))
        if spec.interconnectors:
            connector = spec.interconnectors[0]
            stations = realized.distributions[0][1]
            valid = valid and stations.effective_count == 4
            valid = valid and stations.stations[0].position == connector.start_offset
            valid = valid and abs(stations.stations[-1].position-(math.dist(*axis)-connector.end_offset)) < 1e-8
            physical = realized.interconnectors
            if connector.kind == "SingleLacing":
                a, b = realized.components
                for j, item in enumerate(physical):
                    start_component = a if j % 2 == 0 else b
                    end_component = b if j % 2 == 0 else a
                    valid = valid and math.dist(item.start_global, tuple(v+stations.stations[j].position*w
                        for v, w in zip(start_component.start_global, frame.w))) < 1e-7
                    valid = valid and math.dist(item.end_global, tuple(v+stations.stations[j+1].position*w
                        for v, w in zip(end_component.start_global, frame.w))) < 1e-7
            elif connector.kind == "DoubleLacing":
                valid = valid and len(physical) == 6
                for a, b in zip(physical[::2], physical[1::2]):
                    valid = valid and math.dist(tuple((x+y)/2 for x, y in zip(a.start_global, a.end_global)),
                        tuple((x+y)/2 for x, y in zip(b.start_global, b.end_global))) < 1e-7
        check(titles[i]+": sólidos, eixos, orientação, distribuição e DAG", valid)
        owners.append(owner)
        inputs.append((axis, frame, spec))

    # Existing C3 state: absent field and metadata remain readable, no migration on prepare.
    owner = owners[0]
    axis, frame, spec = inputs[0]
    payload = json.loads(owner.AssemblyState)
    old_spec = json.loads(payload["spec"])
    old_spec["spec"].pop("interconnectors")
    payload["spec"] = json.dumps(old_spec)
    owner.AssemblyState = json.dumps(payload)
    for child in owner.AssemblyMembers:
        for name in ("AssemblyElementKind", "InterconnectorKey", "InterconnectorSlotKey", "GeneratedElementKey"):
            child.removeProperty(name)
    before = snapshot(owner)
    assembly.prepare_assembly(owner, axis, frame, spec)
    check("C3 sem campo/metadata: preflight sem migração", same(before, snapshot(owner)))

    # Structural change is explicit and undoable; return case 1 to no connectors.
    added = replace(spec, interconnectors=specs[1].interconnectors)
    try:
        assembly.apply_assembly(owner, axis, frame, added)
    except ValueError:
        pass
    else:
        raise AssertionError("Cardinalidade aplicada sem intenção estrutural")
    assembly.apply_assembly(owner, axis, frame, added, allow_structural=True)
    updated = snapshot(owner)
    doc.undo()
    doc.recompute()
    check("Regeneração explícita e Undo", same(before, snapshot(owner)))
    doc.redo()
    doc.recompute()
    check("Redo recupera membros e estado", same(updated, snapshot(owner)))
    assembly.apply_assembly(owner, axis, frame, spec, allow_structural=True)

    # Nominal stationing remains independent from physical extensions/adjustments.
    owner = owners[1]
    axis, frame, spec = inputs[1]
    child = next(c for c in owner.AssemblyMembers if c.AssemblyElementKind == "Interconnector")
    child.StartExtension = 11
    child.EndAdjustmentMode = "Fixed"
    child.EndFixedReferenceOffset = -7
    doc.recompute()
    names = {c.GenerationKey: c.Name for c in owner.AssemblyMembers}
    connector = replace(spec.interconnectors[0], start_offset=120., end_offset=180.)
    changed = replace(spec, interconnectors=(connector,))
    assembly.apply_assembly(owner, axis, frame, changed)
    check("Update conserva objetos, extensão e ajuste; offsets continuam nominais",
          {c.GenerationKey: c.Name for c in owner.AssemblyMembers} == names
          and child.StartExtension.Value == 11 and child.EndFixedReferenceOffset.Value == -7
          and str(child.EndAdjustmentMode) == "Fixed" and abs(child.StartPoint.z-120.) < 1e-8)
    inputs[1] = axis, frame, changed
    before = snapshot(owner)
    for bad in (replace(connector, profile_ref=ProfileRef("missing", "missing")),
                replace(connector, start_offset=1000.)):
        try:
            assembly.apply_assembly(owner, axis, frame, replace(changed, interconnectors=(bad,)))
        except (ValueError, KeyError):
            pass
        else:
            raise AssertionError("Preflight inválido aceito")
    check("Perfil inexistente e offsets inválidos preservam último estado", same(before, snapshot(owner)))

    # Fail after mutation AND creation to exercise actual document transaction rollback.
    owner = owners[3]
    axis, frame, spec = inputs[3]
    changed = replace(spec, interconnectors=(replace(spec.interconnectors[0],
        distribution=DistributionSpec(station_count=5)),))
    before, before_objects = snapshot(owner), {o.Name for o in doc.Objects}
    original_apply = assembly.apply_result
    def fail_on_new(child, result, color=None):
        original_apply(child, result, color)
        if child.Name not in before_objects:
            raise RuntimeError("C4-A: falha injetada após criar membro")
    assembly.apply_result = fail_on_new
    try:
        try:
            assembly.apply_assembly(owner, axis, frame, changed, allow_structural=True)
        except RuntimeError as exc:
            if "falha injetada" not in str(exc):
                raise
        else:
            raise AssertionError("Falha injetada não executou")
    finally:
        assembly.apply_result = original_apply
    check("Rollback real remove novos objetos e restaura estado e geometria",
          {o.Name for o in doc.Objects} == before_objects and same(before, snapshot(owner)))

    if output:
        path = output / "AssembliesC4A.FCStd"
        before = {o.Name: snapshot(o) for o in owners}
        doc.recompute()
        doc.saveAs(str(path))
        App.closeDocument(doc.Name)
        doc = App.openDocument(str(path))
        for o in doc.Objects:
            if hasattr(o, "GenerationOwner"):
                o.touch()
        doc.recompute()
        valid = True
        for name, previous in before.items():
            owner = doc.getObject(name)
            valid = valid and same(previous, snapshot(owner))
            state = json.loads(owner.AssemblyState)
            _, plan, _, _ = assembly.prepare_assembly(owner, state["nominal_axis"],
                MemberFrame(**state["member_frame"]), loads(state["spec"]))
            valid = valid and all(a.action == "UNCHANGED" for a in plan.actions)
        check("Save/reopen/recompute e bindings preservados", valid)
    Gui.activeDocument().activeView().viewAxonometric()
    Gui.activeDocument().activeView().fitAll()
    report = dict(passed=True, freecad_version=App.Version()[:3], checks=checks)
    if output:
        Gui.activeDocument().activeView().saveImage(str(output / "assemblies-c4a.png"), 1400, 1000, "Current")
        report["document"] = str(path)
        (output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))
    return report
