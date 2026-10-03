"""Real official adjustment tool, manual precedence and generator reopening."""
import importlib
import json
from dataclasses import replace
from pathlib import Path
import FreeCAD as App
import Part
for module in ('member_batch','connections.resolver','connections','trusses.connections',
               'trusses.fitting','truss','interactive.truss_controller'):
    importlib.reload(importlib.import_module('freecad.SteelStructures.'+module))
from freecad.SteelStructures import truss
from freecad.SteelStructures.interactive.member_adjustment_controller import MemberAdjustmentController
from freecad.SteelStructures.interactive.truss_controller import TrussController
from freecad.SteelStructures.interactive.truss_task_panel import TrussTaskPanel
from freecad.SteelStructures.fitting.freecad_adapter import has_manual_adjustment
from freecad.SteelStructures.trusses.realization import build_candidate
from freecad.SteelStructures.trusses.serialization import decode_state
checks=[]
def check(label,value):
    if not value: raise AssertionError(label)
    checks.append(label)
output=Path(r'C:\Users\marco\Desktop\FREECAD\MINHA BANCADA\SteelStructures\test-results\connections-c5b-overrides')
output.mkdir(parents=True,exist_ok=True)
for geometry in ('LengthLimit','PlaneCut'):
    for associative in (False,True):
        doc=App.newDocument('C5BManualOverride')
        value=truss.default_config()
        value.update(span=6000.,end=[6000.,0.,0.],height=1600.,panel_count=4,topology_preset='K')
        owner=truss.apply_truss(doc,value)
        child=next(m for m in owner.GeneratedMembers if m.GenerationKey.startswith('DIAGONAL'))
        axis=child.EndPoint.sub(child.StartPoint); axis.normalize()
        reference=doc.addObject('Part::Feature','ManualReference')
        reference.Shape=Part.makePlane(2000,2000,child.StartPoint.add(axis*200),axis)
        doc.recompute()
        tool=MemberAdjustmentController(doc,child)
        tool.apply(tool.validate(geometry_mode=geometry,end_choice='Start',gap=3.,
            keep_reference=associative,reference=(reference,['Face1'])))
        check('official adjustment recognized as manual',has_manual_adjustment(child))
        check('official adjustment valid',child.GenerationStatus=='Valid' and child.Shape.isValid())
        before=(str(child.StartAdjustmentMode),str(child.StartAdjustmentGeometryMode),
                child.StartFixedReferenceOffset.Value,child.StartAdjustmentGap.Value,child.Shape.Volume)
        child.Proxy._last_generated_result=None
        controller=TrussController(doc,owner)
        panel=TrussTaskPanel(doc,controller,truss.config_from_object(owner))
        controller.preview3d(truss.config_from_object(owner))
        controller.remove_preview()
        check('generator opens without Python snapshot',controller.last_candidate is not None)
        children=truss.bound_children(owner,decode_state(owner.AppliedState))
        candidate=build_candidate(truss.config_from_object(owner))
        removed=replace(candidate,items=tuple(i for i in candidate.items if i.key!=child.GenerationKey))
        conflicts=truss.conflicts_for(owner,children,removed)
        check('manual member removal remains protected',child.GenerationKey in conflicts)
        check('unchanged member has no conflict',child.GenerationKey not in truss.conflicts_for(owner,children,candidate))
        truss.apply_truss(doc,truss.config_from_object(owner),owner)
        after=(str(child.StartAdjustmentMode),str(child.StartAdjustmentGeometryMode),
               child.StartFixedReferenceOffset.Value,child.StartAdjustmentGap.Value,child.Shape.Volume)
        check('Manual wins over AutoFit after generator apply',before[:4]==after[:4] and abs(before[4]-after[4])<1e-5)
        owner_name,child_name=owner.Name,child.Name
        path=output/(geometry+str(associative)+'.FCStd')
        doc.saveAs(str(path))
        App.closeDocument(doc.Name)
        doc=App.openDocument(str(path))
        owner,child=doc.getObject(owner_name),doc.getObject(child_name)
        controller=TrussController(doc,owner)
        controller.preview3d(truss.config_from_object(owner)); controller.remove_preview()
        check('saved manual override allows generator reopening',has_manual_adjustment(child))
(output/'gate-result.json').write_text(json.dumps(dict(passed=len(checks),checks=checks),indent=2),encoding='utf-8')
print(json.dumps(dict(passed=len(checks),checks=checks)))
