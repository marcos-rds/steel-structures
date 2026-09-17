"""Short real FreeCAD gate: generic through participants, OCC and editor."""
import importlib
import json
from pathlib import Path
import FreeCAD as App
from PySide import QtWidgets
for name in ('connections.models','connections.resolver','connections.presentation','connections',
             'trusses.connections','trusses.fitting','trusses.realization','member_batch',
             'interactive.truss_topology_editor'):
    importlib.reload(importlib.import_module('freecad.SteelStructures.'+name))
from freecad.SteelStructures import truss, member_batch
from freecad.SteelStructures.trusses.realization import build_candidate
from freecad.SteelStructures.trusses.connections import connection_participants
from freecad.SteelStructures.trusses.editing import materialize
from freecad.SteelStructures.interactive.truss_task_panel import TrussTaskPanel
from freecad.SteelStructures.interactive.truss_controller import TrussController
from freecad.SteelStructures.interactive.truss_topology_editor import TopologyEditor
checks=[]
def check(label,result):
    if not result: raise AssertionError(label)
    checks.append(label)
def actions(m):
    plan=json.loads(getattr(m,'PhysicalFitPlan','') or '{}')
    return [a for a in [plan.get('start_action'),plan.get('end_action')]+plan.get('additional_actions',[]) if a]
doc=App.newDocument('C5BThroughValidation')
for custom in (False,True):
    value=truss.default_config()
    value.update(span=6000.,end=[6000.,0.,0.],height=1600.,panel_count=4,topology_preset='K')
    base=build_candidate(value)
    if custom:
        value.update(topology_mode='Custom',topology_preset='Custom',base_preset='K',
                     custom_topology=materialize(base.graph,base.config))
        base=build_candidate(value)
    node=next(n.key for n in base.graph.nodes if any(p.role=='VERTICAL' and p.end=='Through'
              for p in connection_participants(base,n.key)))
    through=next(p for p in connection_participants(base,node) if p.role=='VERTICAL')
    for primary in ('',through.run_key):
        value['connection_intents']={node:dict(form='Direct',direct_policy='Priority',priority_run_key=primary)}
        candidate=build_candidate(value)
        owner=truss.apply_truss(doc,value)
        lookup={i.key:i for i in candidate.items}
        primaries=[m for m in owner.GeneratedMembers if lookup[m.GenerationKey].run_key in through.physical_run_keys]
        secondaries=[m for m in owner.GeneratedMembers if any(a['source']=='ConnectionIntent' for a in actions(m))]
        check('two primary runs preserved',len(primaries)==2 and all(not any(a['source']=='ConnectionIntent' for a in actions(m)) for m in primaries))
        check('two diagonals fitted',len(secondaries)==2)
        check('valid OCC solids',all(m.Shape.isValid() and m.Shape.Volume>0 for m in owner.GeneratedMembers))
        check('zero physical penetration',all(s.Shape.common(p.Shape).Volume<1e-5 for s in secondaries for p in primaries))
        owner.ViewObject.Visibility=False
# Exercise the previous snapshot failure with real members.
child=secondaries[0]
accepted=child.Proxy._last_generated_result
snapshot=member_batch.snapshot(child)
if hasattr(snapshot,'PhysicalFitStatus'): del snapshot.PhysicalFitStatus
member_batch.apply_fit_properties(child,snapshot)
check('old snapshot without PhysicalFitStatus',child.PhysicalFitStatus=='')
child.EndAdjustmentGeometryMode='LengthLimit'
child.EndAdjustmentMode='Associative'
child.EndAdjustmentReference=(primaries[0],['Face1'])
doc.recompute()
check('direct child edit has no internal snapshot exception','PhysicalFitStatus' not in child.GenerationStatus and 'AttributeError' not in child.GenerationStatus)
# An independent generated-child control guard remains a clean diagnostic.
child.StartPoint=App.Vector(1,2,3)
doc.recompute()
check('controlled property diagnostic','controlada' in child.GenerationStatus)
member_batch.apply_result(child,accepted)
child.ControlledState=member_batch.controlled_state(child)
doc.recompute()
panel=TrussTaskPanel(doc,TrussController(doc,owner),truss.config_from_object(owner))
editor=TopologyEditor(panel)
editor.canvas.refresh_candidate()
editor.select_node(node)
check('human through label','Montante (passante)' in editor.participants.text())
check('Independent absent',editor.direct_policy.findData('Independent')==-1)
check('only Automatic and Through Priority options',editor.priority_member.count()==2)
check('BalancedMiter absent with Through',editor.direct_policy.findData('BalancedMiter')==-1)
check('halo exists',len([i for i in editor.canvas.scene().items() if i.data(0)=='selection_halo'])==1)
editor.show()
QtWidgets.QApplication.processEvents()
output=Path(r'C:\Users\marco\Desktop\FREECAD\MINHA BANCADA\SteelStructures\test-results\connections-c5b-through')
output.mkdir(parents=True,exist_ok=True)
editor.grab().save(str(output/'editor.png'))
(output/'gate-result.json').write_text(json.dumps(dict(checks=checks),indent=2),encoding='utf-8')
print(json.dumps(dict(passed=len(checks),checks=checks)))
