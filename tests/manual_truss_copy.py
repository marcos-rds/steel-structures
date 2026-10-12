"""Focused real-FreeCAD GUI regression for native Draft Move copies.

Run run(output_directory) in FreeCAD 1.1.4, or launch with TRUSS_COPY_ROOT and
TRUSS_COPY_RUN set. All documents and FCStd fixtures belong to this gate.
"""
import json
import os
from pathlib import Path
import sys
import traceback


def run(output_directory):
    import FreeCAD as App
    import FreeCADGui as Gui
    import Draft
    from freecad.SteelStructures import truss
    from freecad.SteelStructures.trusses.assemblies import configure_assembly
    from freecad.SteelStructures.trusses.interconnector_options import default_connector
    from freecad.SteelStructures.trusses.connections import connection_participants
    from freecad.SteelStructures.trusses.serialization import decode_state

    out = Path(output_directory)
    out.mkdir(parents=True, exist_ok=True)
    checks = []

    def check(name, condition):
        if not condition:
            (out / "failure.json").write_text(json.dumps(dict(check=name, passed=checks,
                source_status=source.GenerationState, copy_status=copied.GenerationState,
                source_hidden_cache=getattr(source.ViewObject.Proxy, "_hidden_children", {}),
                copy_hidden_cache=getattr(copied.ViewObject.Proxy, "_hidden_children", {}),
                copied_name_map=getattr(copied.Proxy, "_copied_names", {}),
                parent_visibility=[source.ViewObject.Visibility, copied.ViewObject.Visibility],
                source_visibility=[c.ViewObject.Visibility for c in source.GeneratedMembers],
                copy_visibility=[c.ViewObject.Visibility for c in copied.GeneratedMembers]), indent=2))
            raise AssertionError(name)
        checks.append(name)
        (out / "checks.json").write_text(json.dumps(checks, indent=2))

    def snapshot(owner):
        return {child.GenerationKey: (child.Name, tuple(child.StartPoint), tuple(child.EndPoint),
                                      str(child.Profile), tuple(child.ViewObject.ShapeColor))
                for child in owner.GeneratedMembers}

    def valid(owner):
        truss.bound_children(owner, decode_state(owner.AppliedState))
        truss.bound_gusset_plates(owner)
        return (owner.GenerationState == "Valid" and not owner.NeedsRegeneration
                and all(child.GenerationOwner == owner and child.Shape.isValid()
                        and child.Shape.Volume > 0 and child.GenerationStatus == "Valid"
                        for child in owner.GeneratedMembers))

    def disjoint(a, b):
        def owned(owner):
            groups = list(owner.RoleGroups)
            groups += [child for group in owner.RoleGroups for child in group.Group
                       if getattr(child, "AssemblyInterconnectorGroup", False)]
            return set(list(owner.GeneratedMembers) + list(owner.GeneratedGussetPlates) + groups)
        return not owned(a).intersection(owned(b))

    def translated(a, b, vector):
        old = {child.GenerationKey: child for child in a.GeneratedMembers}
        return all((child.StartPoint-old[child.GenerationKey].StartPoint-vector).Length < 1e-6
                   and (child.EndPoint-old[child.GenerationKey].EndPoint-vector).Length < 1e-6
                   for child in b.GeneratedMembers)

    def copy_move(doc, source, vector):
        doc.openTransaction("Draft Move Copy")
        copied = Draft.move([source], vector, copy=True)
        doc.recompute()
        doc.commitTransaction()
        return copied

    def base():
        config = truss.default_config()
        config.update(span=2400., height=700., panel_count=4,
                      start=[50., -20., 100.], end=[2450., -20., 100.],
                      plane_normal=[0., -1., 1.])
        return config

    doc = App.newDocument("TrussCopyRegression")
    doc.UndoMode = 1
    source = truss.apply_truss(doc, base())
    source.GeneratedMembers[1].ViewObject.Visibility = False
    original = snapshot(source)
    count_before = len(doc.Objects)
    vector = App.Vector(125., 2800., 400.)
    copied = copy_move(doc, source, vector)
    source_name, copied_name = source.Name, copied.Name
    count_after = len(doc.Objects)
    check("copy_independent_members_groups_bindings", valid(source) and valid(copied) and disjoint(source, copied))
    check("inclined_placement_applied_once", translated(source, copied, vector))
    check("profiles_and_role_parameters_preserved", source.RoleSpecs == copied.RoleSpecs)
    check("copy_preserves_source_snapshot", snapshot(source) == original)
    check("individual_visibility_copied", not source.GeneratedMembers[1].ViewObject.Visibility
          and not copied.GeneratedMembers[1].ViewObject.Visibility)
    doc.undo()
    doc.recompute()
    check("undo_copy_removes_its_entire_aggregate", len(doc.Objects) == count_before
          and doc.getObject(copied_name) is None and snapshot(source) == original)
    doc.redo()
    doc.recompute()
    copied = doc.getObject(copied_name)
    check("redo_copy_restores_one_aggregate", len(doc.Objects) == count_after
          and valid(copied) and disjoint(source, copied) and translated(source, copied, vector))
    delta = App.Vector(80., 30., -50.)
    doc.openTransaction("Draft Move")
    Draft.move([copied], delta, copy=False)
    doc.recompute()
    doc.commitTransaction()
    check("move_copy_without_double_translation", translated(source, copied, vector+delta))
    doc.undo()
    doc.recompute()
    check("undo_move", translated(source, copied, vector))
    doc.redo()
    doc.recompute()
    check("redo_move", translated(source, copied, vector+delta))
    copy_visibility = [c.ViewObject.Visibility for c in copied.GeneratedMembers]
    source.ViewObject.Visibility = False
    check("hide_source_does_not_hide_copy", copy_visibility == [c.ViewObject.Visibility for c in copied.GeneratedMembers])
    source.ViewObject.Visibility = True
    source_visibility = [c.ViewObject.Visibility for c in source.GeneratedMembers]
    copied.ViewObject.Visibility = False
    check("hide_copy_does_not_hide_source", source_visibility == [c.ViewObject.Visibility for c in source.GeneratedMembers])
    copied.ViewObject.Visibility = True
    check("individual_visibility_preserved", not source.GeneratedMembers[1].ViewObject.Visibility
          and not copied.GeneratedMembers[1].ViewObject.Visibility)
    copied.Height = copied.Height.Value + 120.
    doc.recompute()
    check("copy_dimension_change_is_independent", valid(copied) and snapshot(source) == original)
    config = truss.config_from_object(copied)
    config["panel_count"] = 6
    truss.apply_truss(doc, config, copied)
    check("regenerate_copy_independently", valid(copied) and snapshot(source) == original and disjoint(source, copied))
    copy_snapshot = snapshot(copied)
    source.Height = source.Height.Value + 60.
    doc.recompute()
    truss.apply_truss(doc, truss.config_from_object(source), source)
    check("regenerate_source_independently", valid(source) and snapshot(copied) == copy_snapshot)
    before_reopen = len(doc.Objects)
    source_snapshot = snapshot(source)
    path = out / "independent-trusses.FCStd"
    doc.saveAs(str(path))
    App.closeDocument(doc.Name)
    doc = App.openDocument(str(path))
    doc.recompute()
    source, copied = doc.getObject(source_name), doc.getObject(copied_name)
    check("save_reopen_without_duplicate_children", len(doc.Objects) == before_reopen
          and valid(source) and valid(copied) and disjoint(source, copied)
          and snapshot(source) == source_snapshot and snapshot(copied) == copy_snapshot)
    doc.removeObject(copied.Name)
    doc.recompute()
    check("delete_copy_preserves_source", valid(source) and snapshot(source) == source_snapshot)
    App.closeDocument(doc.Name)

    doc = App.newDocument("TrussCopyAssemblies")
    config = base()
    config["role_specs"]["TOP_CHORD"] = configure_assembly(
        dict(config["role_specs"]["TOP_CHORD"], rotation=0.), "SpacedPair", 240.,
        interconnectors=(default_connector("Battens"),))
    config["role_specs"]["DIAGONAL"] = configure_assembly(config["role_specs"]["DIAGONAL"], "DoubleAngle", 40.)
    source = truss.apply_truss(doc, config)
    copied = copy_move(doc, source, vector)
    check("compound_profiles_and_interconnectors", valid(source) and valid(copied) and disjoint(source, copied)
          and translated(source, copied, vector)
          and any(c.AssemblyElementKind == "Interconnector" for c in copied.GeneratedMembers))
    check("interconnector_subgroups_remapped", all(
        all(child.GenerationOwner == copied for child in subgroup.Group)
        for group in copied.RoleGroups for subgroup in group.Group
        if getattr(subgroup, "AssemblyInterconnectorGroup", False)))
    preserved = snapshot(copied)
    doc.removeObject(source.Name)
    doc.recompute()
    check("delete_source_preserves_compound_copy", valid(copied) and snapshot(copied) == preserved)
    App.closeDocument(doc.Name)

    doc = App.newDocument("TrussCopyGussets")
    config = base()
    config["topology_preset"] = "Pratt"
    candidate = truss.build_candidate(config)
    node = next(node.key for node in candidate.graph.nodes if sum(
        p.role in ("DIAGONAL", "VERTICAL", "END_POST")
        for p in connection_participants(candidate, node.key)) >= 2)
    config["connection_intents"] = {node: dict(form="Gusset", gusset=dict(
        plate_thickness=8., normal_clearance=2., axial_clearance=20.,
        edge_margin=25., member_overlap=150., side="Center"))}
    source = truss.apply_truss(doc, config)
    copied = copy_move(doc, source, vector)
    check("gusset_ownership_independent", valid(source) and valid(copied) and disjoint(source, copied)
          and len(copied.GeneratedGussetPlates) == len(source.GeneratedGussetPlates) == 1
          and copied.GeneratedGussetPlates[0].ParentTruss == copied)
    a, b = source.GeneratedGussetPlates[0], copied.GeneratedGussetPlates[0]
    check("gusset_translation_once", (b.Shape.CenterOfMass-a.Shape.CenterOfMass-vector).Length < 1e-6
          and abs(a.Shape.Volume-b.Shape.Volume) < 1e-5)
    source.ViewObject.Visibility = False
    check("gusset_visibility_independent", not a.ViewObject.Visibility and b.ViewObject.Visibility)
    App.closeDocument(doc.Name)

    doc = App.newDocument("TrussCopyLinkedReference")
    line = Draft.make_line(App.Vector(), App.Vector(2400, 0, 0))
    doc.recompute()
    config = base()
    config.update(reference_linked=True, reference_mode="DraftLine", reference_source=line.Name,
                  reference_edge="Edge1")
    source = truss.apply_truss(doc, config)
    copied = copy_move(doc, source, vector)
    check("external_link_preserved_without_implicit_detach", copied.ReferenceLinked
          and copied.ReferenceSource[0] == source.ReferenceSource[0] == line
          and disjoint(source, copied) and valid(copied))
    check("linked_position_remains_source_governed", translated(source, copied, App.Vector()))
    App.closeDocument(doc.Name)

    doc = App.newDocument("TrussCopyHiddenOwner")
    source = truss.apply_truss(doc, base())
    source.GeneratedMembers[1].ViewObject.Visibility = False
    source.ViewObject.Visibility = False
    copied = copy_move(doc, source, vector)
    copied.ViewObject.Visibility = True
    check("show_copy_of_hidden_owner", not source.ViewObject.Visibility
          and not any(c.ViewObject.Visibility for c in source.GeneratedMembers)
          and any(c.ViewObject.Visibility for c in copied.GeneratedMembers)
          and not copied.GeneratedMembers[1].ViewObject.Visibility)
    App.closeDocument(doc.Name)
    doc = App.newDocument("TrussRepeatedCopy")
    owners = [truss.apply_truss(doc, base())]
    for index in range(3):
        source = owners[-1]
        copied = copy_move(doc, source, vector)
        check("copy_of_copy_" + str(index+1), valid(copied)
              and translated(owners[-1], copied, vector)
              and all(disjoint(owner, copied) for owner in owners))
        owners.append(copied)
    unchanged = [snapshot(owner) for owner in owners[:-1]]
    owners[-1].Height = owners[-1].Height.Value + 90.
    doc.recompute()
    check("copy_chain_property_independence", all(valid(owner) for owner in owners)
          and [snapshot(owner) for owner in owners[:-1]] == unchanged)
    names = [owner.Name for owner in owners]
    object_count = len(doc.Objects)
    path = out / "repeated-copies.FCStd"
    doc.saveAs(str(path))
    App.closeDocument(doc.Name)
    doc = App.openDocument(str(path))
    doc.recompute()
    owners = [doc.getObject(name) for name in names]
    source, copied = owners[0], owners[-1]
    check("copy_chain_persistence", len(doc.Objects) == object_count
          and all(valid(owner) for owner in owners)
          and all(disjoint(owner, other) for index, owner in enumerate(owners)
                  for other in owners[index+1:]))
    App.closeDocument(doc.Name)
    return dict(ok=True, version=App.Version(), checks=checks)


def _launch():
    from PySide import QtCore, QtWidgets
    import FreeCAD as App
    out = Path(os.environ["TRUSS_COPY_RUN"])
    try:
        result = run(out)
    except Exception:
        result = dict(ok=False, error=traceback.format_exc())
        App.Console.PrintError(result["error"])
    (out / "result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    for name in tuple(App.listDocuments()):
        App.closeDocument(name)
    QtCore.QTimer.singleShot(0, QtWidgets.QApplication.quit)


if os.environ.get("TRUSS_COPY_ROOT") and os.environ.get("TRUSS_COPY_RUN"):
    sys.path.insert(0, os.environ["TRUSS_COPY_ROOT"])
    import freecad
    freecad.__path__.insert(0, str(Path(os.environ["TRUSS_COPY_ROOT"]) / "freecad"))
    from PySide import QtCore
    QtCore.QTimer.singleShot(500, _launch)
