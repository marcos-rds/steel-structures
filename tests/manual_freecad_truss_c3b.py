"""Surgical C3-B gate inside FreeCAD. New small document only; ten phase checks.

Call run(output_directory). Leaves the final inclined truss open for review.
No UI automation, broad audit or temporary FeaturePython preview objects.
"""
import copy
import json
import math
from pathlib import Path
import tempfile


def run(output_directory=None):
    import FreeCAD as App
    import FreeCADGui as Gui
    from freecad.SteelStructures import truss
    from freecad.SteelStructures.trusses.assemblies import configure_assembly
    from freecad.SteelStructures.trusses.serialization import decode_state, dumps
    from freecad.SteelStructures.interactive.truss_controller import TrussController

    output = Path(output_directory or tempfile.mkdtemp(prefix="ss-truss-c3b-"))
    output.mkdir(parents=True, exist_ok=True)
    doc = App.newDocument("TrussC3BProof")
    config = truss.default_config()
    config.update(span=2400., height=700., end=[2400., 0., 0.], panel_count=4)
    obj = truss.apply_truss(doc, config)
    checks = []

    def check(name, condition):
        checks.append(dict(check=name, passed=bool(condition)))
        if not condition:
            (output / "failure-details.json").write_text(json.dumps(dict(
                phase=name, generation_state=obj.GenerationState, message=obj.GenerationMessage,
                needs_regeneration=obj.NeedsRegeneration, before=before, after=snapshot(),
                children=[dict(name=c.Name, status=c.GenerationStatus, valid=c.Shape.isValid(),
                               owner_in_dependencies=obj in c.OutList, child_in_owner=c in obj.OutList)
                          for c in obj.GeneratedMembers]), default=str, indent=2), encoding="utf-8")
            raise AssertionError(name)

    def members(role):
        return [c for c in obj.GeneratedMembers if c.GenerationKey in
                {i.key for i in truss.build_candidate(config).items if i.role == role}]

    def valid():
        groups = list(obj.RoleGroups)
        return (not obj.NeedsRegeneration and obj.GenerationState == "Valid"
                and all(c.Shape.isValid() and c.Shape.Volume > 0 and c.GenerationStatus == "Valid"
                        and c.GenerationOwner == obj and c not in obj.OutList
                        and c.OffsetX.Value == c.OffsetY.Value == 0
                        for c in obj.GeneratedMembers)
                and sorted(c.Name for g in groups for c in g.Group) == sorted(c.Name for c in obj.GeneratedMembers))

    def snapshot():
        return {c.GenerationKey: (c.Name, c.Shape.Volume, list(c.StartPoint), list(c.EndPoint),
                list(c.Placement.Rotation.Q)) for c in obj.GeneratedMembers}

    def names():
        return {c.GenerationKey: c.Name for c in obj.GeneratedMembers}

    def same_snapshot(before, after):
        # OCC serialization can change the last few floating-point volume bits.
        return before.keys() == after.keys() and all(before[k][0] == after[k][0]
            and math.isclose(before[k][1], after[k][1], rel_tol=1e-12, abs_tol=1e-5)
            and all(math.dist(before[k][i], after[k][i]) < 1e-8 for i in (2, 3, 4)) for k in before)

    def composition(role, mode, spacing=100):
        base = dict(config["role_specs"][role], rotation=0.)
        config["role_specs"][role] = configure_assembly(base, mode, spacing)

    def pair_geometry(role, spacing):
        candidate = truss.build_candidate(config)
        bindings = {c.GenerationKey: c for c in obj.GeneratedMembers}
        for run in (r for r in candidate.runs if r.role == role):
            items = [i for i in candidate.items if i.run_key == run.key]
            if len(items) != 2:
                return False
            a, b = (bindings[i.key] for i in items)
            logical_a = candidate.graph.node(run.start_node_key).position_local
            nominal = truss.reference_frame(config)
            from freecad.SteelStructures.trusses.realization import transform_point
            midpoint = App.Vector(*transform_point(logical_a, nominal))
            if ((a.StartPoint+b.StartPoint)*.5-midpoint).Length > 1e-7:
                return False
            if abs((a.StartPoint-b.StartPoint).Length-spacing) > 1e-7:
                return False
            if (a.EndPoint-a.StartPoint-(b.EndPoint-b.StartPoint)).Length > 1e-7:
                return False
            expected = App.Vector(*items[0].section_u_global)*spacing
            if (b.StartPoint-a.StartPoint-expected).Length > 1e-7:
                return False
        return True

    def channel_mouths():
        from freecad.SteelStructures import member, profile_catalog
        for child in members("TOP_CHORD"):
            geometry = member._section_geometry(profile_catalog.get(str(child.Profile)))
            stations = dict(geometry.dimension_stations)
            x = (stations["web_back_x"]+stations["web_inner_x"])/2
            if json.loads(child.AssemblySectionTransform)["reflect_x"]:
                x = -x
            local = child.Shape.copy()
            local.Placement = App.Placement()
            z = child.MemberLength.Value/2
            if not local.isInside(App.Vector(x, 0, z), 1e-7, True) or local.isInside(App.Vector(-x, 0, z), 1e-7, True):
                return False
        return True

    # Produce a schema-2 fixture without assembly fields or component metadata.
    before = snapshot()
    for role in config["role_specs"].values():
        role.pop("assembly", None)
        role.pop("assembly_spec", None)
    state = decode_state(obj.AppliedState)
    state["candidate"]["config"]["role_specs"] = copy.deepcopy(config["role_specs"])
    for item in state["candidate"]["items"]:
        for key in ("run_key", "assembly_key", "component_key", "section_transform"):
            item.pop(key, None)
        item["spec"].pop("assembly_spec", None)
        item["spec"].pop("assembly", None)
    obj.Proxy._updating = True
    obj.RoleSpecs = dumps(config["role_specs"])
    obj.AppliedState = dumps(state)
    for child in obj.GeneratedMembers:
        for key in ("RunKey", "AssemblyKey", "ComponentKey"):
            child.removeProperty(key)
    obj.Proxy._updating = False
    path = output / "legacy-single.FCStd"
    obj_name = obj.Name
    doc.saveAs(str(path))
    App.closeDocument(doc.Name)
    doc = App.openDocument(str(path))
    obj = doc.getObject(obj_name)
    doc.recompute()
    check("1. C2 sem assembly: U simples, restore sem regeneração ou mudança física", valid() and same_snapshot(before, snapshot()))

    composition("TOP_CHORD", "DoubleChannelInward")
    obj = truss.apply_truss(doc, config, obj)
    inward_names = names()
    top = members("TOP_CHORD")
    check("2. U duplo para dentro: sólidos, simetria, árvore e ownership", valid() and pair_geometry("TOP_CHORD", 100) and channel_mouths()
          and {c.ComponentKey: json.loads(c.AssemblySectionTransform)["reflect_x"] for c in top} == {"A": False, "B": True})

    composition("TOP_CHORD", "DoubleChannelOutward")
    obj = truss.apply_truss(doc, config, obj)
    check("3. U para fora: mudança física sem recriação", valid() and names() == inward_names and channel_mouths()
          and {c.ComponentKey: json.loads(c.AssemblySectionTransform)["reflect_x"] for c in members("TOP_CHORD")} == {"A": True, "B": False})

    composition("BOTTOM_CHORD", "DoubleChannelInward")
    composition("DIAGONAL", "DoubleAngle", 40)
    obj = truss.apply_truss(doc, config, obj)
    check("4. Caso A: diagonais duplas L, montantes/fechamentos simples", valid() and pair_geometry("DIAGONAL", 40)
          and all(c.ComponentKey == "A" for c in members("VERTICAL")+members("END_POST")))

    composition("TOP_CHORD", "SpacedPair", 180)
    composition("BOTTOM_CHORD", "SpacedPair", 180)
    composition("DIAGONAL", "Single")
    obj = truss.apply_truss(doc, config, obj)
    check("5. Caso B: par espaçado de U paralelo e diagonais simples", valid() and pair_geometry("TOP_CHORD", 180)
          and all(not json.loads(c.AssemblySectionTransform)["reflect_x"] for c in members("TOP_CHORD")))

    config["plane_normal"] = [0., -.6, .8]
    obj = truss.apply_truss(doc, config, obj)
    check("6. Plano inclinado segue o frame local", valid() and pair_geometry("TOP_CHORD", 180))

    before_names = names()
    a = next(c for c in members("TOP_CHORD") if c.ComponentKey == "A")
    a.StartExtension = 12
    doc.recompute()
    composition("TOP_CHORD", "SpacedPair", 230)
    obj = truss.apply_truss(doc, config, obj)
    check("7. Spacing atualiza mesmos objetos e preserva extensão", valid() and names() == before_names
          and pair_geometry("TOP_CHORD", 230) and a.StartExtension.Value == 12)

    composition("TOP_CHORD", "Single")
    single_name = a.Name
    obj = truss.apply_truss(doc, config, obj)
    one = (len(members("TOP_CHORD")) == 1 and members("TOP_CHORD")[0].Name == single_name
           and " / " not in a.Label and a.StartExtension.Value == 12)
    doc.undo()
    doc.recompute()
    restored_pair = len([c for c in obj.GeneratedMembers if getattr(c, "RunKey", "") == a.RunKey]) == 2
    doc.redo()
    doc.recompute()
    restored_single = len(members("TOP_CHORD")) == 1
    composition("TOP_CHORD", "SpacedPair", 230)
    obj = truss.apply_truss(doc, config, obj)
    check("8. Single ↔ Double, Undo/Redo e identidade A", one and restored_pair and restored_single and valid()
          and next(c for c in members("TOP_CHORD") if c.ComponentKey == "A").Name == single_name)

    controller = TrussController(doc, obj)
    before_objects = [c.Name for c in doc.Objects]
    candidate_config = copy.deepcopy(config)
    candidate_config["role_specs"]["DIAGONAL"] = configure_assembly(candidate_config["role_specs"]["DIAGONAL"], "DoubleAngle", 40)
    accepted = obj.AppliedState
    controller.preview3d(candidate_config)
    preview_count = len(controller._preview.shape.Solids)
    controller.cancel()
    check("9. Preview 3D usa componentes do candidate sem mutar documento", before_objects == [c.Name for c in doc.Objects]
          and obj.AppliedState == accepted and preview_count == len(truss.build_candidate(candidate_config).items)
          and controller._preview is None)

    # Leave the practical mixed case in the final artifact.
    composition("DIAGONAL", "DoubleAngle", 40)
    obj = truss.apply_truss(doc, config, obj)
    before = snapshot()
    path = output / "TrussC3B.FCStd"
    doc.saveAs(str(path))
    App.closeDocument(doc.Name)
    doc = App.openDocument(str(path))
    obj = doc.getObject(obj_name)
    for c in obj.GeneratedMembers:
        c.touch()
    doc.recompute()
    after = snapshot()
    persisted = same_snapshot(before, after)
    check("10. Save/reopen/recompute conserva componentes, Shapes e Placement", valid() and persisted)
    Gui.activeDocument().activeView().viewAxonometric()
    Gui.activeDocument().activeView().fitAll()
    Gui.activeDocument().activeView().saveImage(str(output / "truss-isometric.png"), 1400, 900, "Current")
    report = dict(passed=True, freecad_version=App.Version()[:3], checks=checks, document=str(path))
    (output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(dict(passed=True, phases=len(checks), document=str(path))))
    return report


def run_editor(document, output_directory):
    """One real-Qt UI smoke: mode, family conflict, transforms, cancel and role rows."""
    from PySide import QtGui, QtWidgets
    from freecad.SteelStructures import truss, profile_catalog
    from freecad.SteelStructures.interactive.assembly_editor import AssemblyEditor
    from freecad.SteelStructures.interactive.truss_task_panel import TrussTaskPanel
    from freecad.SteelStructures.interactive.truss_controller import TrussController
    output = Path(output_directory)
    obj = document.getObject("StructuralTruss")
    config = truss.config_from_object(obj)
    original = copy.deepcopy(config)
    accepted = obj.AppliedState
    dialog = AssemblyEditor(document, "Banzo superior", config["role_specs"]["TOP_CHORD"])
    dialog.setModal(False)  # modeless only for automation; normal user flow uses exec().
    dialog.show()

    def events():
        QtWidgets.QApplication.processEvents()
        QtWidgets.QApplication.processEvents()

    try:
        events()
        dialog.mode.setCurrentIndex(dialog.mode.findData("DoubleChannelInward"))
        dialog.spacing.setValue(125.)
        events()
        assert dialog._valid_composition and dialog.preview.model["spacing"] == 125.
        assert len(dialog.preview.model["components"]) == 2
        dialog.grab().save(str(output / "editor-channel-inward.png"))
        dialog.mode.setCurrentIndex(dialog.mode.findData("DoubleChannelOutward"))
        events()
        dialog.grab().save(str(output / "editor-channel-outward.png"))
        try:
            dialog.options.set_profile_ref(profile_catalog.ref_for_designation('L 40 x 4'))
        except ValueError:
            pass
        else:
            raise AssertionError("Incompatible selection accepted")
        dialog.mode.setCurrentIndex(dialog.mode.findData("DoubleAngle"))
        events()
        dialog.options.set_profile_ref(profile_catalog.ref_for_designation('L 40 x 4'))
        dialog.spacing.setValue(40.)
        events()
        assert dialog._valid_composition
        dialog.grab().save(str(output / "editor-double-angle.png"))
        dialog.mode.setCurrentIndex(dialog.mode.findData("SpacedPair"))
        dialog.component_orientations[1].setCurrentIndex(4)
        events()
        assert dialog.role_spec()["assembly_spec"]["spec"]["components"][1]["section_transform"]["reflect_x"]
        palette = dialog.preview.palette()
        palette.setColor(QtGui.QPalette.Base, QtGui.QColor(35, 39, 43))
        dialog.preview.setPalette(palette)
        events()
        dialog.preview.grab().save(str(output / "preview-dark-palette.png"))
        dialog.reject()
        assert config == original and obj.AppliedState == accepted
    finally:
        dialog.close()
        dialog.deleteLater()
    controller = TrussController(document, obj)
    panel = TrussTaskPanel(document, controller, config)
    try:
        panel.show_3d.setChecked(False)
        panel.sections["Perfis"][0].setChecked(True)
        panel.form.resize(420, 800)
        panel.form.show()
        events()
        assert all("Composição:" in button.text() for button in panel.role_buttons.values())
        panel.form.grab().save(str(output / "role-panel.png"))
        panel.reject()
        assert obj.AppliedState == accepted
    finally:
        panel.form.close()
        panel.form.deleteLater()
    return dict(passed=True, cancel_preserved_document=True, incompatible_family_blocked=True)
