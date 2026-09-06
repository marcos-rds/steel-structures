"""C1 reproducible timing/section-frame checks; run inside FreeCAD, not discovery."""
from dataclasses import asdict
from pathlib import Path
import json
from time import perf_counter


def run(output_directory):
    import FreeCAD as App
    import FreeCADGui as Gui
    from freecad.SteelStructures import truss, member_batch, profile_catalog
    from freecad.SteelStructures.interactive.truss_controller import TrussController
    from freecad.SteelStructures.interactive.member_adjustment_controller import is_structural_member
    from freecad.SteelStructures.trusses.realization import build_candidate, plan_regeneration
    from freecad.SteelStructures.profiles import ProfileLibrary
    from freecad.SteelStructures.paths import CATALOGS_DIR

    output = Path(output_directory)
    output.mkdir(parents=True, exist_ok=True)
    active = App.ActiveDocument.Name if App.ActiveDocument else None
    profiles = ProfileLibrary(CATALOGS_DIR).list_profiles()
    chosen = {}
    for key,geometry in (("U","channel_section"),("L","equal_angle"),("RHS","hollow_section")):
        choices = [p for p in profiles if p.geometry_type == geometry
                   and (key != "RHS" or p.geometry_variant == "rectangular")]
        chosen[key] = choices[len(choices)//2]
    rows = []
    try:
        for panels in (6,12,24):
            doc = App.newDocument("SSTrussPerformance"+str(panels))
            doc.UndoMode = 1
            controller = None
            try:
                config = truss.default_config()
                config.update(panel_count=panels, topology_preset="Pratt", span=12000.,
                              start=[0.,0.,0.], end=[12000.,0.,0.], height=2200.)
                for role,spec in config["role_specs"].items():
                    key = "L" if role == "DIAGONAL" else "RHS" if role == "BOTTOM_CHORD" else "U"
                    spec["profile_ref"] = asdict(chosen[key].ref)
                    spec["rotation"] = 90. if role == "TOP_CHORD" else 0.
                started = perf_counter()
                for _ in range(20):
                    candidate = build_candidate(config)
                pure_ms = (perf_counter()-started)*1000/20
                started = perf_counter()
                for _ in range(100):
                    plan_regeneration(candidate, candidate)
                plan_ms = (perf_counter()-started)*1000/100
                controller = TrussController(doc)
                started = perf_counter()
                controller.preview3d(config)
                preview_ms = (perf_counter()-started)*1000
                assert not doc.Objects
                controller.cancel()
                started = perf_counter()
                obj = truss.apply_truss(doc, config)
                create_ms = (perf_counter()-started)*1000
                names = [c.Name for c in obj.GeneratedMembers]
                started = perf_counter()
                doc.recompute()
                recompute_ms = (perf_counter()-started)*1000
                started = perf_counter()
                obj.Height = 2300.
                doc.recompute()
                geometric_ms = (perf_counter()-started)*1000
                assert names == [c.Name for c in obj.GeneratedMembers]
                assert obj.GenerationState == "Valid", obj.GenerationMessage
                realized = {i.key:i for i in build_candidate(truss.config_from_object(obj)).items}
                for child in obj.GeneratedMembers:
                    assert is_structural_member(child)
                    assert child.Shape.isValid() and child.Shape.Volume > 0
                    item = realized[child.GenerationKey]
                    u = App.Vector(*item.section_u_global)
                    w = App.Vector(*item.end_global).sub(App.Vector(*item.start_global))
                    w.normalize()
                    v = w.cross(u)
                    user_roll = App.Rotation(w,item.spec.rotation)
                    assert child.Placement.Rotation.multVec(App.Vector(1,0,0)).sub(user_roll.multVec(u)).Length < 1e-7
                    assert child.Placement.Rotation.multVec(App.Vector(0,1,0)).sub(user_roll.multVec(v)).Length < 1e-7
                rows.append(dict(panels=panels, members=len(names), pure_ms=pure_ms, plan_ms=plan_ms,
                                 preview_ms=preview_ms, create_ms=create_ms, recompute_ms=recompute_ms,
                                 geometric_update_ms=geometric_ms))
                if panels == 6:
                    Gui.activeDocument().activeView().viewAxonometric()
                    Gui.activeDocument().activeView().fitAll()
                    Gui.activeDocument().activeView().saveImage(str(output/"u-angle-rhs-orientation.png"),1600,900,"White")
                    doc.saveAs(str(output/"U_Angle_RHS.FCStd"))
            finally:
                if controller:
                    controller.cancel()
                App.closeDocument(doc.Name)
    finally:
        if active and active in App.listDocuments():
            App.setActiveDocument(active)
    result = dict(version=App.Version()[:3], profiles={key:p.designation for key,p in chosen.items()}, timings=rows)
    (output/"performance.json").write_text(json.dumps(result,indent=2),encoding="utf-8")
    return result
