# SPDX-License-Identifier: LGPL-2.1-or-later
"""Independent C1 integration gate, run inside FreeCAD 1.1.3 (not discovery).

Call run(output_directory=..., reload_modules=True). Only new temporary
documents are modified. Results and FCStd artifacts go to the output directory.
Each phase is isolated; all failures are reported, then an AssertionError is
raised. No screenshot is used as geometric evidence.
"""
import copy
from dataclasses import asdict
from contextlib import contextmanager
import importlib
import json
import math
from pathlib import Path
import tempfile
import traceback


def run(output_directory=None, reload_modules=False, keep_documents=False, phases=None):
    import FreeCAD as App
    import FreeCADGui as Gui
    from freecad.SteelStructures import member, member_batch, truss, profile_catalog
    from freecad.SteelStructures.interactive import truss_controller
    from freecad.SteelStructures.profiles import ProfileLibrary
    from freecad.SteelStructures.paths import CATALOGS_DIR
    from freecad.SteelStructures.trusses.realization import build_candidate
    from freecad.SteelStructures.trusses.serialization import decode_state, dumps

    if reload_modules:
        for name in ("envelope", "panelization", "patterns", "runs", "validation", "serialization", "realization"):
            module = importlib.import_module("freecad.SteelStructures.trusses." + name)
            importlib.reload(module)
        from freecad.SteelStructures.trusses.realization import build_candidate
        from freecad.SteelStructures.trusses.serialization import decode_state, dumps
        for module in (member, member_batch, truss, truss_controller):
            importlib.reload(module)
    output = Path(output_directory) if output_directory else Path(tempfile.mkdtemp(prefix="ss-truss-c1-qa-"))
    output.mkdir(parents=True, exist_ok=True)
    original_names = set(App.listDocuments())
    original_active = App.ActiveDocument.Name if App.ActiveDocument else None
    created_names = set()
    report = {"freecad_version": App.Version()[:3], "checks": [], "phases": [],
              "observations": {}, "output_directory": str(output), "passed": False}
    active_phase = "setup"

    def check(label, condition, observed=None):
        row = {"phase": active_phase, "check": label, "passed": bool(condition)}
        if observed is not None:
            row["observed"] = observed
        report["checks"].append(row)
        if not condition:
            raise AssertionError(label + (": " + repr(observed) if observed is not None else ""))

    def near(a, b, tolerance=1e-7):
        return math.isclose(float(a), float(b), rel_tol=1e-8, abs_tol=tolerance)

    def point(vector):
        return [float(vector.x), float(vector.y), float(vector.z)]

    def same(a, b):
        if isinstance(a, str) and isinstance(b, str) and a.startswith("{") and b.startswith("{"):
            try:
                return same(json.loads(a), json.loads(b))
            except ValueError:
                pass
        if isinstance(a, dict) and isinstance(b, dict):
            return set(a) == set(b) and all(same(a[key], b[key]) for key in a)
        if isinstance(a, (list, tuple)) and isinstance(b, (list, tuple)):
            return len(a) == len(b) and all(same(x, y) for x, y in zip(a, b))
        if isinstance(a, (int, float)) and isinstance(b, (int, float)):
            return near(a, b)
        return a == b

    def new_doc(suffix):
        doc = App.newDocument("SSTrussQA_" + suffix)
        created_names.add(doc.Name)
        doc.UndoMode = 1
        return doc

    profiles = ProfileLibrary(CATALOGS_DIR).list_profiles()
    selected = [next(profile for profile in profiles if profile.ref.profile_id == key) for key in (
        "round-bar-20-64", "square-bar-20-64", "flat-bar-50-8x6-35")]

    def configuration(kind="Parallel", preset="Warren", profile_index=1):
        value = truss.default_config()
        value.update(envelope_type=kind, topology_preset=preset, span=6000., height=1200.,
                     panel_count=4, start=[30., 40., 50.], end=[6030., 40., 50.],
                     plane_normal=[0., -1., 0.], apex_position=.35)
        for index, role in enumerate(value["role_specs"]):
            spec = value["role_specs"][role]
            spec["profile_ref"] = asdict(selected[profile_index].ref)
            spec["rotation"] = 17.0 if role == "DIAGONAL" else 0.0
            spec["color"] = [0.15 + index*.1, .45, .7]
        return value

    def children(obj):
        return {child.GenerationKey: child for child in obj.GeneratedMembers}

    def child_state(child):
        shape = child.Shape
        # OCC's ordinary BoundBox can depend on cached triangulation of circles.
        bbox = shape.optimalBoundingBox(False, False)
        solid_volume = sum(solid.Volume for solid in shape.Solids)
        center = [sum(solid.Volume * point(solid.CenterOfMass)[axis] for solid in shape.Solids)
                  / solid_volume for axis in range(3)]
        state = {"name": child.Name, "key": child.GenerationKey,
                 "start": point(child.StartPoint), "end": point(child.EndPoint),
                 "effective_start": point(child.EffectiveStartPoint),
                 "effective_end": point(child.EffectiveEndPoint),
                 "placement": point(child.Placement.Base) + list(child.Placement.Rotation.Q),
                 "volume": shape.Volume, "area": shape.Area, "center": center,
                 "bbox": [bbox.XMin, bbox.YMin, bbox.ZMin, bbox.XMax, bbox.YMax, bbox.ZMax],
                 "profile": str(child.Profile), "category": str(child.ProfileCategory),
                 "series": str(child.ProfileSeries), "insertion": str(child.Insertion),
                 "rotation": child.Rotation.Value, "geometry_mode": str(child.SectionGeometryMode),
                 "mass_per_meter": child.MassPerMeter, "total_mass": child.TotalMass,
                 "catalog_area": child.CatalogArea, "length": child.Length.Value,
                 "adjusted_length": child.AdjustedLength.Value,
                 "start_extension": child.StartExtension.Value, "end_extension": child.EndExtension.Value,
                 "color": [round(value*255) for value in child.ViewObject.ShapeColor[:3]],
                 "controlled": child.ControlledState}
        for prefix in ("Start", "End"):
            for suffix in ("AdjustmentMode", "AdjustmentGeometryMode", "AdjustmentReference",
                           "AdjustmentGap", "FixedReferenceOffset", "FixedPlaneNormal"):
                value = getattr(child, prefix+suffix)
                state[prefix+suffix] = (point(value) if isinstance(value, App.Vector) else
                                       value.Value if hasattr(value, "Value") else str(value))
        return state

    def snapshot(obj):
        return {"applied": obj.AppliedState,
                "children": {key: child_state(child) for key, child in children(obj).items()},
                "groups": {group.Name: [child.Name for child in group.Group] for group in obj.RoleGroups},
                "left": obj.LeftPanels, "right": obj.RightPanels}

    def check_snapshot(label, obj, before):
        actual = snapshot(obj)
        differences = [key for key in before if not same(actual.get(key), before[key])]
        if actual["applied"] != before["applied"] and "applied" not in differences:
            differences.append("applied")
        if differences:
            artifact = output / ("snapshot-diff-" + str(len(report["checks"])) + ".json")
            artifact.write_text(json.dumps({"phase": active_phase, "label": label,
                "before": before, "after": actual}, ensure_ascii=False, indent=2), encoding="utf-8")
            report["observations"][active_phase + " " + label] = str(artifact)
        check(label, not differences, differences)

    def check_model(label, obj):
        candidate = build_candidate(decode_state(obj.AppliedState)["candidate"]["config"])
        actual = children(obj)
        check(label + " binding set", set(actual) == {item.key for item in candidate.items})
        check(label + " parent valid", obj.GenerationState == "Valid" and not obj.NeedsRegeneration,
              {"state": obj.GenerationState, "message": obj.GenerationMessage})
        for item in candidate.items:
            child = actual[item.key]
            check(label + " " + item.key + " shape", child.TypeId == "Part::FeaturePython"
                  and not child.Shape.isNull() and child.Shape.isValid() and child.Shape.Volume > 0
                  and "Invalid" not in child.State and child.GenerationStatus == "Valid")
            check(label + " " + item.key + " nominal", same(point(child.StartPoint), item.start_global)
                  and same(point(child.EndPoint), item.end_global))
            check(label + " " + item.key + " ownership", child.GenerationOwner == obj
                  and str(child.AxisDefinitionMode) == "Independent" and not child.AxisSource)
            check(label + " " + item.key + " mass", child.MassPerMeter > 0 and child.TotalMass > 0
                  and near(child.TotalMass, child.Shape.Volume / (child.CatalogArea * 100.) / 1000.
                           * child.MassPerMeter))
            check(label + " " + item.key + " color", [round(value*255) for value in child.ViewObject.ShapeColor[:3]]
                  == [round(value*255) for value in item.spec.color])
            u = child.Placement.Rotation.multVec(App.Vector(1, 0, 0))
            normal = App.Vector(*item.section_u_global)
            check(label + " " + item.key + " roll", near(u.dot(normal), math.cos(math.radians(item.spec.rotation))))
        grouped = [child.Name for group in obj.RoleGroups for child in group.Group]
        check(label + " unique role membership", sorted(grouped) == sorted(child.Name for child in actual.values()))
        check(label + " native dependency direction", not any(child in obj.OutList for child in actual.values())
              and all(obj in child.OutList for child in actual.values()))
        report["observations"][label] = {"parent": obj.Name, "members": len(actual),
            "roles": len(obj.RoleGroups), "total_volume": sum(child.Shape.Volume for child in actual.values())}

    @contextmanager
    def patched(module, name, replacement):
        previous = getattr(module, name)
        setattr(module, name, replacement)
        try:
            yield previous
        finally:
            setattr(module, name, previous)

    def expected_error(label, action):
        try:
            action()
        except Exception as exc:
            check(label, True, type(exc).__name__ + ": " + str(exc))
        else:
            check(label, False, "operation unexpectedly succeeded")

    def phase(name, action):
        nonlocal active_phase
        if phases is not None and name not in phases:
            return
        active_phase = name
        try:
            action()
            report["phases"].append({"name": name, "passed": True})
        except Exception as exc:
            report["phases"].append({"name": name, "passed": False,
                "error": type(exc).__name__ + ": " + str(exc), "traceback": traceback.format_exc()})
        finally:
            (output / "truss-c1-qa-results.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    def geometry_and_persistence(kind, preset, index):
        doc = new_doc(kind + preset)
        obj = truss.apply_truss(doc, configuration(kind, preset, index % 3))
        name = obj.Name
        check_model(kind+preset+" created", obj)
        original_names_by_key = {key: child.Name for key, child in children(obj).items()}
        allocation = (obj.LeftPanels, obj.RightPanels)
        doc.openTransaction("QA dimension edit")
        obj.Span, obj.Height = 7200., 1600.
        if kind == "DuoPitch":
            obj.ApexPosition = .75
        doc.recompute()
        doc.commitTransaction()
        check_model(kind+preset+" dimensions", obj)
        check("dimension changes preserve object identity", original_names_by_key == {
            key: child.Name for key, child in children(obj).items()})
        check("dimension changes preserve station allocation", allocation == (obj.LeftPanels, obj.RightPanels))
        before = snapshot(obj)
        names_before = sorted(o.Name for o in doc.Objects)
        obj.PanelCount = 6
        obj.TopologyPreset = "Pratt" if preset == "Warren" else "Warren"
        doc.recompute()
        check("topological changes remain pending", obj.NeedsRegeneration and obj.GenerationState == "Pending")
        check_snapshot("pending retains complete realization", obj, before)
        check("execute creates/removes no objects", names_before == sorted(o.Name for o in doc.Objects))
        config_pending = truss.config_from_object(obj)
        obj = truss.apply_truss(doc, config_pending, obj)
        after = snapshot(obj)
        check_model(kind+preset+" regenerated", obj)
        doc.undo()
        doc.recompute()
        obj = doc.getObject(name)
        check_snapshot("structural Undo restores previous realization", obj, before)
        check("structural Undo retains requested pending definition", obj.GenerationState == "Pending")
        doc.redo()
        doc.recompute()
        obj = doc.getObject(name)
        check_snapshot("structural Redo restores accepted realization", obj, after)
        check_model(kind+preset+" redo", obj)
        path = output / (kind+preset+".FCStd")
        doc.saveAs(str(path))
        App.closeDocument(doc.Name)
        doc = App.openDocument(str(path))
        created_names.add(doc.Name)
        doc.recompute()
        obj = doc.getObject(name)
        check_snapshot("save/reopen retains numerical realization", obj, after)
        check_model(kind+preset+" restored", obj)
        stable = snapshot(obj)
        for _ in range(3):
            doc.recompute()
        check_snapshot("three recomputes are idempotent", obj, stable)
        obj.Height = 1750.
        doc.recompute()
        check_model(kind+preset+" restored edit", obj)

    def manual_adjustments():
        doc = new_doc("ManualFit")
        obj = truss.apply_truss(doc, configuration())
        child = children(obj)["BC_MAIN"]
        child.StartExtension, child.EndExtension = 20., 30.
        child.EndAdjustmentMode = "Fixed"
        child.EndAdjustmentGeometryMode = "LengthLimit"
        child.EndFixedReferenceOffset, child.EndAdjustmentGap = 45., 4.
        doc.recompute()
        check("manual extensions and fixed LengthLimit", near(child.AdjustedLength.Value, 6000+20-45-4)
              and child.GenerationStatus == "Valid")
        child.StartAdjustmentMode = "Fixed"
        child.StartAdjustmentGeometryMode = "PlaneCut"
        child.StartFixedReferenceOffset, child.StartAdjustmentGap = 100., 2.
        child.StartFixedPlaneNormal = App.Vector(.2, 0., 1.)
        doc.recompute()
        check("manual oblique Fixed PlaneCut valid", child.Shape.isValid() and child.Shape.Volume > 0
              and child.GenerationStatus == "Valid")
        preserved = {key: value for key, value in child_state(child).items()
                     if key.startswith(("Start", "End")) or key.endswith("extension")}
        obj.Span = 6500.
        obj.Height = 1400.
        doc.recompute()
        check_model("manual fitting after geometry edit", obj)
        check("manual slots gaps normals extensions preserved", same(preserved, {
            key: value for key, value in child_state(child).items() if key in preserved}))
        check("fixed physical stations follow changed nominal length", near(child.AdjustedLength.Value, 6500-100-2-45-4))
        before_volume = child.Shape.Volume
        child.StartFixedReferenceOffset = 10000.
        doc.recompute()
        check("invalid child fit preserves last Shape", near(child.Shape.Volume, before_volume)
              and child.Shape.isValid() and child.GenerationStatus != "Valid")
        before = snapshot(obj)
        obj.Height = 1500.
        doc.recompute()
        check("invalid fit rejects whole owner batch", obj.GenerationState == "Conflict")
        check_snapshot("invalid fit does not partially move siblings", obj, before)
        child.StartFixedReferenceOffset = 100.
        doc.recompute()
        obj.touch()
        doc.recompute()
        check_model("manual fit recovery", obj)

    def controlled_conflict_and_removal():
        doc = new_doc("Conflicts")
        obj = truss.apply_truss(doc, configuration())
        child = children(obj)["BC_MAIN"]
        original = App.Vector(child.EndPoint)
        original_volume = child.Shape.Volume
        child.EndPoint = original.add(App.Vector(100., 0., 0.))
        doc.recompute()
        check("direct controlled edit does not replace previous Shape", near(child.Shape.Volume, original_volume)
              and child.GenerationStatus != "Valid")
        before = snapshot(obj)
        obj.Height = 1300.
        doc.recompute()
        check("owner reports controlled-property conflict", obj.GenerationState == "Conflict")
        check_snapshot("controlled conflict does not mutate siblings", obj, before)
        child.EndPoint = original
        doc.recompute()
        obj.touch()
        doc.recompute()
        check_model("controlled edit corrected", obj)
        top = children(obj)["TC_MAIN"]
        reference = doc.addObject("App::FeaturePython", "QAExternalReference")
        reference.addProperty("App::PropertyLinkSub", "Support")
        reference.Support = (top, ["Face1"])
        doc.recompute()
        before = snapshot(obj)
        target = truss.config_from_object(obj)
        target["top_continuity"] = "SegmentAtEveryNode"
        expected_error("external face reference blocks removal", lambda: truss.apply_truss(doc, target, obj))
        check_snapshot("blocked removal retains complete realization", obj, before)
        check("external reference remains bound", reference.Support[0] == top)
        doc.removeObject(reference.Name)
        top.StartExtension = 25.
        doc.recompute()
        before = snapshot(obj)
        expected_error("manual extension blocks destructive removal", lambda: truss.apply_truss(doc, target, obj))
        check_snapshot("manual data preserved on blocked removal", obj, before)

    def missing_child():
        doc = new_doc("MissingChild")
        obj = truss.apply_truss(doc, configuration())
        removed = children(obj)["TC_MAIN"].Name
        accepted = obj.AppliedState
        survivors = {child.Name: child_state(child) for child in obj.GeneratedMembers if child.Name != removed}
        doc.removeObject(removed)
        obj.Height = 1400.
        doc.recompute()
        check("deleted generated child is not silently recreated", doc.getObject(removed) is None)
        check("missing binding is exposed", obj.NeedsRegeneration and obj.GenerationState == "Conflict"
              and obj.AppliedState == accepted)
        check("missing child preserves other members", same(survivors,
              {name: child_state(doc.getObject(name)) for name in survivors}))

    def fault_automatic(kind):
        doc = new_doc("Fault_" + kind)
        obj = truss.apply_truss(doc, configuration())
        before = snapshot(obj)
        counter = [0]
        name = "prepare_member" if kind == "preflight" else "apply_result" if kind == "apply" else "accept_state"
        real = getattr(truss, name)

        def fail_once(*args, **kwargs):
            counter[0] += 1
            if kind == "accept":
                result = real(*args, **kwargs)
                if counter[0] == 1:
                    raise RuntimeError("QA fault after accepted state was assigned")
                return result
            if counter[0] == 2:
                raise RuntimeError("QA fault at second " + kind)
            return real(*args, **kwargs)

        with patched(truss, name, fail_once):
            obj.Height = 1500.
            doc.recompute()
        check(kind + " injection was reached", counter[0] >= (1 if kind == "accept" else 2), counter[0])
        check(kind + " failure exposed", obj.GenerationState == "Conflict" and obj.NeedsRegeneration)
        check_snapshot(kind + " failure restores complete accepted realization", obj, before)
        obj.touch()
        doc.recompute()
        check_model(kind + " recovery", obj)

    def fault_transaction(existing):
        doc = new_doc("FaultTransaction" + str(existing))
        obj = truss.apply_truss(doc, configuration()) if existing else None
        config_value = truss.config_from_object(obj) if obj else configuration()
        config_value["panel_count"] = 6
        before = snapshot(obj) if obj else None
        before_objects = sorted(o.Name for o in doc.Objects)
        real = truss.apply_result
        counter = [0]

        def fail_second(*args, **kwargs):
            counter[0] += 1
            if counter[0] == 2:
                raise RuntimeError("QA transaction fault on second child")
            return real(*args, **kwargs)

        with patched(truss, "apply_result", fail_second):
            expected_error("transaction rejects partial child application",
                           lambda: truss.apply_truss(doc, config_value, obj))
        check("failed transaction leaves no orphan objects", before_objects == sorted(o.Name for o in doc.Objects))
        if obj:
            check_snapshot("failed structural Apply rolls back existing realization", obj, before)
        result = truss.apply_truss(doc, config_value, obj)
        check_model("transaction retry", result)

    def controller_preview_and_cancel():
        from pivy import coin
        doc = new_doc("Controller")
        gui_doc = Gui.getDocument(doc.Name)
        scene = gui_doc.activeView().getSceneGraph()
        scene_count = scene.getNumChildren()
        controller = truss_controller.TrussController(doc)
        value = configuration()
        before = sorted(o.Name for o in doc.Objects)
        check("preview starts from clean document", not gui_doc.Modified)
        controller.preview3d(value)
        preview = controller._preview
        check("preview is scene-only valid compound", sorted(o.Name for o in doc.Objects) == before
              and preview.shape.isValid() and preview.shape.Volume > 0
              and scene.getNumChildren() == scene_count+1 and scene.findChild(preview.node) >= 0)
        check("preview is unpickable and keeps document clean", not gui_doc.Modified
              and preview.node.getChild(0).getChild(0).style.getValue() == coin.SoPickStyle.UNPICKABLE)
        volume = preview.shape.Volume
        changed = copy.deepcopy(value)
        for spec in changed["role_specs"].values():
            spec["profile_ref"] = asdict(selected[2].ref)
            spec["insertion"] = "top"
            spec["rotation"] = 90.
            spec["color"] = [.8, .2, .1]
        controller.preview3d(changed)
        check("preview follows profile without adding objects", controller._preview == preview
              and not near(preview.shape.Volume, volume) and sorted(o.Name for o in doc.Objects) == before)
        check("preview follows role color", all([round(value*255) for value in color] == [204, 51, 26]
                                                for color in preview.colors))
        controller.cancel()
        check("cancel removes temporary shape and callbacks", sorted(o.Name for o in doc.Objects) == before
              and controller.closed and not controller._point_callbacks and controller._view is None)
        check("cancel leaves no scene branch or dirty document", scene.getNumChildren() == scene_count
              and scene.findChild(preview.node) < 0 and not gui_doc.Modified)
        controller = truss_controller.TrussController(doc)
        controller.preview3d(value)
        original = truss_controller.apply_truss

        def fail_accept(*args, **kwargs):
            raise RuntimeError("QA deliberate accept failure")

        with patched(truss_controller, "apply_truss", fail_accept):
            expected_error("controller accepts no failed result", lambda: controller.accept(value))
        check("failed accept stays retryable and has no orphan preview", not controller.closed
              and controller.object is None and sorted(o.Name for o in doc.Objects) == before)
        obj = controller.accept(value)
        check("retry closes controller", controller.closed and controller.object == obj)
        check_model("controller accepted", obj)
        all_names = sorted(o.Name for o in doc.Objects)
        doc.undo()
        doc.recompute()
        check("creation Undo removes owner members and groups", sorted(o.Name for o in doc.Objects) == before)
        doc.redo()
        doc.recompute()
        check("creation Redo restores objects without preview", sorted(o.Name for o in doc.Objects) == all_names
              and all(not item.Name.startswith("TrussPreview") for item in doc.Objects))

    try:
        for index, (kind, preset) in enumerate((
            ("Parallel", "Warren"), ("Parallel", "Pratt"), ("DuoPitch", "Warren"), ("DuoPitch", "Pratt"))):
            phase(kind+" / "+preset, lambda k=kind, p=preset, i=index: geometry_and_persistence(k, p, i))
        phase("Manual extensions and Fixed cuts", manual_adjustments)
        phase("Controlled conflict and external removal", controlled_conflict_and_removal)
        phase("Missing child", missing_child)
        for kind in ("preflight", "apply", "accept"):
            phase("Automatic batch failure / "+kind, lambda k=kind: fault_automatic(k))
        for existing in (False, True):
            phase("Transactional failure / "+str(existing), lambda e=existing: fault_transaction(e))
        phase("Controller preview cancel accept Undo Redo", controller_preview_and_cancel)
    finally:
        if not keep_documents:
            for name in created_names:
                if name in App.listDocuments() and name not in original_names:
                    App.closeDocument(name)
        if original_active and original_active in App.listDocuments():
            App.setActiveDocument(original_active)
        report["original_documents_preserved"] = original_names <= set(App.listDocuments())
        report["passed"] = (all(row["passed"] for row in report["phases"])
                            and report["original_documents_preserved"])
        report["check_count"] = len(report["checks"])
        (output / "truss-c1-qa-results.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    failures = [row["name"] for row in report["phases"] if not row["passed"]]
    if failures:
        raise AssertionError("C1 FreeCAD QA failed: " + "; ".join(failures) + ". Results: " + str(output))
    return report
