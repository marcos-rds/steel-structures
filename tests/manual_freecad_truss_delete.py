"""Native GUI aggregate deletion gate, including multi-selection and Undo.

Launch using TRUSS_COPY_ROOT/TRUSS_COPY_RUN in an isolated FreeCAD process.
"""
import json
import os
from pathlib import Path
import sys
import traceback


def run(out):
    import FreeCAD as App
    import FreeCADGui as Gui
    import Draft
    from PySide import QtCore, QtWidgets
    from freecad.SteelStructures import truss
    from freecad.SteelStructures.trusses.assemblies import configure_assembly
    from freecad.SteelStructures.trusses.interconnector_options import default_connector
    from freecad.SteelStructures.trusses.connections import connection_participants
    from freecad.SteelStructures.trusses.serialization import decode_state

    checks=[]
    def check(name, condition):
        if not condition:
            raise AssertionError(name)
        checks.append(name)
    def valid(owner):
        truss.bound_children(owner, decode_state(owner.AppliedState))
        truss.bound_gusset_plates(owner)
        return owner.GenerationState=="Valid" and all(m.GenerationOwner==owner
            and m.Shape.isValid() and m.Shape.Volume>0 for m in owner.GeneratedMembers)
    def owned(owner):
        groups=list(owner.RoleGroups)
        groups += [s for g in owner.RoleGroups for s in g.Group
                   if getattr(s,"AssemblyInterconnectorGroup",False)]
        return {o.Name for o in [owner]+list(owner.GeneratedMembers)
                +list(owner.GeneratedGussetPlates)+groups}
    def accept_warning():
        for w in QtWidgets.QApplication.topLevelWidgets():
            if isinstance(w,QtWidgets.QMessageBox) and w.isVisible():
                w.done(QtWidgets.QMessageBox.Yes)
    timer=QtCore.QTimer()
    timer.timeout.connect(accept_warning)
    def delete(owner, multiselect=False):
        Gui.Selection.clearSelection()
        Gui.Selection.addSelection(owner)
        if multiselect:
            Gui.Selection.addSelection(owner.GeneratedMembers[0])
        timer.start(100)
        try:
            Gui.runCommand("Std_Delete",0)
        finally:
            timer.stop()

    for kind in ("Parallel","DuoPitch"):
        doc=App.newDocument("NativeDelete"+kind)
        doc.UndoMode=1
        line=Draft.make_line(App.Vector(100.,0.,200.), App.Vector(2500.,0.,900.))
        doc.recompute()
        config=truss.default_config()
        config.update(envelope_type=kind,reference_mode="DraftLine",reference_linked=True,
            reference_source=line.Name,reference_alignment="TopChordSupports",height=700.,
            left_end_height=100.,right_end_height=200.,link_end_heights=False,panel_count=4)
        if kind=="DuoPitch":
            config["role_specs"]["TOP_CHORD"]=configure_assembly(
                dict(config["role_specs"]["TOP_CHORD"],rotation=0.),
                "DoubleChannelOutward",160.,interconnectors=(default_connector("Battens"),))
            candidate=truss.build_candidate(dict(config,start=list(line.Start),end=list(line.End),
                span=(line.End-line.Start).Length))
            node=next(n.key for n in candidate.graph.nodes if "TOP_CHORD" in n.affiliations
                and len(connection_participants(candidate,n.key))>=3)
            config["connection_intents"]={node:dict(form="Gusset",gusset=dict(plate_thickness=8.))}
        source=truss.apply_truss(doc,config)
        doc.openTransaction("Draft copy")
        copied=Draft.move([source],App.Vector(0.,3000.,0.),copy=True)
        doc.recompute()
        doc.commitTransaction()
        source_name,copied_name=source.Name,copied.Name
        source_names,copy_names=owned(source),owned(copied)
        before={o.Name for o in doc.Objects}
        check(kind+"_independent",valid(source) and valid(copied) and not source_names.intersection(copy_names))
        delete(source, multiselect=True)
        doc.recompute()
        check(kind+"_delete_source_multiselection_exact",{o.Name for o in doc.Objects}==before-source_names
              and valid(copied) and doc.getObject(line.Name) is not None)
        doc.undo()
        doc.recompute()
        check(kind+"_undo_complete",{o.Name for o in doc.Objects}==before
              and valid(doc.getObject(source_name)) and valid(copied))
        path=out/(kind+"_undo.FCStd")
        doc.saveAs(str(path))
        doc.redo()
        doc.recompute()
        check(kind+"_redo_exact",{o.Name for o in doc.Objects}==before-source_names and valid(copied))
        delete(copied)
        doc.recompute()
        check(kind+"_delete_copy_exact",{o.Name for o in doc.Objects}==before-source_names-copy_names)
        App.closeDocument(doc.Name)
        doc=App.openDocument(str(path))
        doc.recompute()
        check(kind+"_save_reopen_after_undo",{o.Name for o in doc.Objects}==before
              and valid(doc.getObject(source_name)) and valid(doc.getObject(copied_name)))
        App.closeDocument(doc.Name)
    return dict(ok=True,checks=checks,version=App.Version()[:3])


if os.environ.get("TRUSS_COPY_ROOT"):
    import FreeCAD as App
    from PySide import QtCore,QtWidgets
    root=Path(os.environ["TRUSS_COPY_ROOT"])
    out=Path(os.environ["TRUSS_COPY_RUN"])
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
        QtWidgets.QApplication.quit()
    QtCore.QTimer.singleShot(500,launch)
