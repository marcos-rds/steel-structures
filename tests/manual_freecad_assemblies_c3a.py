"""Surgical C3-A fixture. Run run() inside FreeCAD; never unittest discovery.

Creates only a new document. Five labelled cases plus an inclined pair remain
open for visual review. A reflected hollow-section OCC check remains hidden.
The saved document is reopened and recomputed; no user document is modified.
"""
from dataclasses import replace
import json
import math
from pathlib import Path
import tempfile


def run(output_directory=None):
    import FreeCAD as App
    import FreeCADGui as Gui
    from freecad.SteelStructures import profile_catalog
    from freecad.SteelStructures.assembly import apply_assembly, prepare_assembly
    from freecad.SteelStructures.assemblies import MemberFrame, SectionTransform
    from freecad.SteelStructures.assemblies.presets import single, double_angle, double_channel, spaced_pair
    from freecad.SteelStructures.profiles.geometry import build_section_geometry
    from freecad.SteelStructures.assemblies.transforms import transform_section
    from freecad.SteelStructures.profiles.freecad_geometry import section_geometry_to_face

    output = Path(output_directory or tempfile.mkdtemp(prefix="ss-c3a-"))
    output.mkdir(parents=True, exist_ok=True)
    doc = App.newDocument("AssembliesC3A")
    checks = []

    def check(name, condition):
        checks.append(dict(check=name, passed=bool(condition)))
        if not condition:
            raise AssertionError(name)

    channel = profile_catalog.ref_for_designation('U 4" x 8,04')
    angle = profile_catalog.ref_for_designation('L 40 x 4')
    cases = [single("Single U", channel), double_angle("Double Angle", angle, 40),
             double_channel("U outward ][", channel, 100),
             double_channel("U inward []", channel, 130, mouths="inward"),
             spaced_pair("Spaced Pair", channel, 260,
                         (SectionTransform(), SectionTransform(reflect_x=True)))]
    owners, members = [], []
    for i, spec in enumerate(cases):
        axis = ((i*350., 0., 0.), (i*350., 0., 300.))
        frame = MemberFrame.from_axis(axis, (1, 0, 0))
        owner = doc.addObject("App::FeaturePython", "AssemblyProof")
        owner.Label = spec.assembly_key
        result = apply_assembly(owner, axis, frame, spec, allow_structural=True)
        owners.append(owner)
        members.extend(result.values())
        realized, plan, _, _ = prepare_assembly(owner, axis, frame, spec)
        check(spec.assembly_key+" unchanged plan", not plan.structural and all(a.action == "UNCHANGED" for a in plan.actions))
        for item in realized.components:
            child = result[item.stable_identity]
            check(child.Name+" valid solid", child.Shape.isValid() and child.Shape.Volume > 0)
            check(child.Name+" physical axis", (child.StartPoint-App.Vector(*item.start_global)).Length < 1e-7
                  and (child.EndPoint-App.Vector(*item.end_global)).Length < 1e-7)
            check(child.Name+" no double offset", child.OffsetX.Value == child.OffsetY.Value == 0)
            check(child.Name+" longitudinal placement", (child.Placement.Rotation.multVec(App.Vector(0, 0, 1))-App.Vector(*frame.w)).Length < 1e-7)
            geometry = build_section_geometry(profile_catalog.get(str(child.Profile)).definition)
            transformed, refs = transform_section(geometry, item.section_transform)
            insertion = next(r.point for r in refs if r.id == item.insertion_reference)
            face = section_geometry_to_face(transformed)
            face.translate(App.Vector(-insertion.x, -insertion.y, 0))
            # Check physical local bounds against transformed contour, not only Rotation.
            local = child.Shape.copy()
            local.Placement = App.Placement()
            check(child.Name+" physical section orientation", all(abs(getattr(local.BoundBox, k)-getattr(face.BoundBox, k)) < 1e-6
                  for k in ("XMin", "XMax", "YMin", "YMax")))
            if i in (2, 3):
                # At mid-height only the web exists. Check actual solid occupancy.
                rear = dict(geometry.dimension_stations)["web_back_x"]
                inner = dict(geometry.dimension_stations)["web_inner_x"]
                from freecad.SteelStructures.profiles.geometry import Point2D
                web = item.section_transform.point(Point2D((rear+inner)/2, 0))
                check(child.Name+" mouth direction in solid", local.isInside(App.Vector(web.x, web.y, 150), 1e-7, True)
                      and not local.isInside(App.Vector(-web.x, web.y, 150), 1e-7, True))
        if len(result) == 2:
            a, b = result.values()
            check(spec.assembly_key+" spacing", abs((a.StartPoint-b.StartPoint).Length-spec.component_spacing) < 1e-7)

    # Stable identities, ordinary extensions/offsets, transformed noncentral insertion.
    owner = owners[1]
    old = {c.ComponentKey: c.Name for c in owner.AssemblyMembers}
    a = next(c for c in owner.AssemblyMembers if c.ComponentKey == "A")
    a.StartExtension = 11
    a.EndAdjustmentMode = "Fixed"
    a.EndFixedReferenceOffset = -7
    doc.recompute()
    adjusted_mode = str(a.EndAdjustmentMode)
    spec = double_angle("Double Angle", angle, 55)
    spec = replace(spec, components=tuple(replace(c, insertion_reference="outer_corner",
                        section_transform=SectionTransform(90, c.section_transform.reflect_x)) for c in spec.components))
    axis = ((350., 0., 0.), (350., 0., 300.))
    frame = MemberFrame.from_axis(axis, (1, 0, 0))
    result = apply_assembly(owner, axis, frame, spec)
    check("update preserves names/extensions/adjustment", {c.ComponentKey: c.Name for c in result.values()} == old
          and a.StartExtension.Value == 11 and str(a.EndAdjustmentMode) == adjusted_mode
          and a.EndFixedReferenceOffset.Value == -7)
    check("insertion transformed after update", all(c.Shape.isValid() and c.Shape.Volume > 0 for c in result.values()))
    for component in spec.components:
        child = result[(spec.assembly_key, component.component_key)]
        geometry = build_section_geometry(profile_catalog.get(str(child.Profile)).definition)
        transformed, refs = transform_section(geometry, component.section_transform)
        point = next(r.point for r in refs if r.id == "outer_corner")
        local = child.Shape.copy()
        local.Placement = App.Placement()
        check(child.Name+" noncentral insertion coordinates",
              abs(local.BoundBox.XMin-(transformed.bounds.min_x-point.x)) < 1e-7
              and abs(local.BoundBox.YMin-(transformed.bounds.min_y-point.y)) < 1e-7)
    changed_profile = double_channel("Double Angle", channel, 100)
    result = apply_assembly(owner, axis, frame, changed_profile)
    check("profile update preserves physical identities", {c.ComponentKey: c.Name for c in result.values()} == old
          and all(c.Profile == profile_catalog.property_designation('U 4" x 8,04') for c in result.values())
          and a.StartExtension.Value == 11 and a.EndFixedReferenceOffset.Value == -7)
    # Restore common visual configuration; fitting remains present on component A.
    apply_assembly(owner, axis, frame, cases[1])

    # Deliberate failure after the first mutation proves the transaction rollback.
    from freecad.SteelStructures import assembly as adapter
    original_apply = adapter.apply_result
    saved_state = owner.AssemblyState
    saved = {c.Name: (c.Shape.Volume, c.AssemblySectionTransform, list(c.StartPoint)) for c in owner.AssemblyMembers}
    calls = []

    def fail_second(*args, **kwargs):
        calls.append(1)
        if len(calls) == 2:
            raise RuntimeError("C3-A injected apply failure")
        return original_apply(*args, **kwargs)

    adapter.apply_result = fail_second
    try:
        try:
            apply_assembly(owner, axis, frame, changed_profile)
        except RuntimeError as exc:
            check("injected apply failure reached", "injected" in str(exc))
        else:
            raise AssertionError("injection not reached")
    finally:
        adapter.apply_result = original_apply
    check("rollback restores complete batch", owner.AssemblyState == saved_state and all(
        abs(c.Shape.Volume-saved[c.Name][0]) < 1e-6 and c.AssemblySectionTransform == saved[c.Name][1]
        and list(c.StartPoint) == saved[c.Name][2] for c in owner.AssemblyMembers))

    # Structural gate and a preflight failure must leave document untouched.
    owner = owners[0]
    axis = ((0., 0., 0.), (0., 0., 300.))
    before = [(o.Name, getattr(o, "AssemblyState", "")) for o in doc.Objects]
    pair = spaced_pair("Single U", channel, 120)
    try:
        apply_assembly(owner, axis, frame, pair)
    except ValueError:
        pass
    else:
        raise AssertionError("structural gate missing")
    check("structural gate leaves document unchanged", before == [(o.Name, getattr(o, "AssemblyState", "")) for o in doc.Objects])
    original_a = owner.AssemblyMembers[0].Name
    result = apply_assembly(owner, axis, frame, pair, allow_structural=True)
    check("Single to Double reuses A", result[("Single U", "A")].Name == original_a)
    doc.undo()
    doc.recompute()
    check("Undo structural transition", len(owner.AssemblyMembers) == 1 and owner.AssemblyMembers[0].Name == original_a)
    doc.redo()
    doc.recompute()
    check("Redo structural transition", len(owner.AssemblyMembers) == 2 and all(c.Shape.isValid() for c in owner.AssemblyMembers))
    apply_assembly(owner, axis, frame, cases[0], allow_structural=True)
    check("Double to Single reuses A", owner.AssemblyMembers[0].Name == original_a and len(owner.AssemblyMembers) == 1)
    bad = replace(pair, components=(pair.components[0], replace(pair.components[1], insertion_reference="missing")))
    before = [(o.Name, getattr(o, "AssemblyState", "")) for o in doc.Objects]
    try:
        apply_assembly(owner, axis, frame, bad, allow_structural=True)
    except ValueError:
        pass
    else:
        raise AssertionError("bad insertion accepted")
    check("failed complete preflight is atomic", before == [(o.Name, getattr(o, "AssemblyState", "")) for o in doc.Objects])

    axis = ((400., 450., 0.), (700., 750., 300.))
    frame = MemberFrame.from_axis(axis, (1, -1, 0))
    spec = spaced_pair("Inclined Pair", channel, 180)
    owner = doc.addObject("App::FeaturePython", "AssemblyInclined")
    owner.Label = "Par em plano inclinado"
    result = apply_assembly(owner, axis, frame, spec, allow_structural=True)
    members.extend(result.values())
    a, b = result.values()
    shift = b.StartPoint-a.StartPoint
    check("inclined offset follows local u", (shift-App.Vector(*frame.u)*180).Length < 1e-7)
    check("inclined lengths parallel", (a.EndPoint-a.StartPoint-(b.EndPoint-b.StartPoint)).Length < 1e-7)

    # Genuine curved inner/outer contour reflection through OCC (no family hack).
    hollow = next(p for p in profile_catalog.profiles().values()
                  if p.definition is not None and p.definition.geometry_type == "hollow_section"
                  and p.definition.geometry_variant == "rectangular")
    geometry = build_section_geometry(hollow.definition)
    transformed, refs = transform_section(geometry, SectionTransform(37, True))
    solid = section_geometry_to_face(transformed).extrude(App.Vector(0, 0, 100))
    check("reflected hollow arcs and holes OCC", solid.isValid() and solid.Volume > 0
          and abs(solid.Volume-geometry.area*100) < 1e-4)

    names = {c.Name: (c.Shape.Volume, list(c.StartPoint), list(c.EndPoint), c.AssemblySectionTransform,
                      list(c.Placement.Rotation.Q), str(c.Insertion), c.StartExtension.Value,
                      str(c.EndAdjustmentMode), c.EndFixedReferenceOffset.Value) for c in members}
    path = output / "AssembliesC3A.FCStd"
    doc.recompute()
    doc.saveAs(str(path))
    App.closeDocument(doc.Name)
    doc = App.openDocument(str(path))
    for c in doc.Objects:
        if hasattr(c, "AssemblySectionTransform"):
            c.touch()
    doc.recompute()
    for name, expected in names.items():
        c = doc.getObject(name)
        check(name+" save reopen recompute", c.Shape.isValid() and abs(c.Shape.Volume-expected[0]) < 1e-5
              and list(c.StartPoint) == expected[1] and list(c.EndPoint) == expected[2]
              and c.AssemblySectionTransform == expected[3]
              and math.dist(c.Placement.Rotation.Q, expected[4]) < 1e-7
              and str(c.Insertion) == expected[5] and c.StartExtension.Value == expected[6]
              and str(c.EndAdjustmentMode) == expected[7] and c.EndFixedReferenceOffset.Value == expected[8]
              and c.GenerationStatus == "Valid")
    Gui.activeDocument().activeView().viewTop()
    Gui.activeDocument().activeView().fitAll()
    report = dict(freecad_version=App.Version()[:3], checks=checks, document=str(path), passed=True)
    (output / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(dict(passed=True, checks=len(checks), document=str(path))))
    return report
