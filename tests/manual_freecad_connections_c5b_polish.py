"""Small FreeCAD 1.1.3 gate for final C5-B polish; run via MCP."""
import copy
import importlib
import json
from pathlib import Path
import FreeCAD as App

for name in ('fitting.precedence','fitting.freecad_adapter','connections.models','connections.validation',
             'connections.serialization','connections.resolver','connections','trusses.connections',
             'trusses.fitting','trusses.realization','member_batch','truss',
             'interactive.truss_controller','interactive.truss_topology_editor','interactive.truss_task_panel'):
    importlib.reload(importlib.import_module('freecad.SteelStructures.'+name))
from freecad.SteelStructures import truss
from freecad.SteelStructures.trusses.realization import build_candidate
from freecad.SteelStructures.trusses.connections import connection_participants
from freecad.SteelStructures.trusses.assemblies import configure_assembly
from freecad.SteelStructures.trusses.editing import restore_preset
from freecad.SteelStructures.fitting.freecad_adapter import has_manual_adjustment
from freecad.SteelStructures.interactive.truss_task_panel import TrussTaskPanel
from freecad.SteelStructures.interactive.truss_controller import TrussController
from freecad.SteelStructures.interactive.truss_topology_editor import TopologyEditor

checks=[]
def check(label, condition):
    if not condition: raise AssertionError(label)
    checks.append(label)

def config(preset):
    value=truss.default_config()
    value.update(span=6000.,end=[6000.,0.,0.],height=1600.,panel_count=4,topology_preset=preset)
    return value

def webs(c,node):
    return [p for p in connection_participants(c,node) if p.role in ('DIAGONAL','VERTICAL','END_POST')]

def actions(m):
    p=json.loads(getattr(m,'PhysicalFitPlan','') or '{}')
    return [a for a in (p.get('start_action'),p.get('end_action')) if a]+p.get('additional_actions',[])

def valid(owner):
    return all(m.Shape.isValid() and m.Shape.Volume>0 for m in owner.GeneratedMembers)

doc=App.newDocument('C5BPolishGate')
doc.UndoMode=1
value=config('Pratt')
base=build_candidate(value)
node=next(n.key for n in base.graph.nodes if len(webs(base,n.key))==3)
participants=webs(base,node)
vertical=next(p for p in participants if p.role=='VERTICAL')
value['connection_intents']={node:dict(form='Direct',direct_policy='Priority')}
owner=truss.apply_truss(doc,value)
check('Pratt Automatic three webs valid',valid(owner))
primary_key=next(i.key for i in base.items if i.run_key==vertical.run_key)
primary=next(m for m in owner.GeneratedMembers if m.GenerationKey==primary_key)
check('vertical primary has no connection cut',not any(a['source']=='ConnectionIntent' for a in actions(primary)))
secondaries=[m for m in owner.GeneratedMembers if any(a['source']=='ConnectionIntent' for a in actions(m))]
check('both diagonals have composed ToChord Priority',len(secondaries)==2 and all(
    any(a['source']=='AutoFit' for a in actions(m)) for m in secondaries))
for m in secondaries:
    check('secondary no penetration into primary',m.Shape.common(primary.Shape).Volume<1e-5)

panel=TrussTaskPanel(doc,TrussController(doc,owner),truss.config_from_object(owner))
editor=TopologyEditor(panel)
editor.select_node(node)
check('BalancedMiter absent',editor.direct_policy.findData('BalancedMiter')==-1)
check('vertical selectable by stable key',editor.priority_member.findData(vertical.run_key)>=0)
check('semantic vertical name',editor.priority_member.itemText(editor.priority_member.findData(vertical.run_key))=='Montante')
check('Direct display name',editor.connection_type.itemText(editor.connection_type.findData('Direct'))=='Ligação direta')
check('direct policy label',editor._connection_form.labelForField(editor.direct_policy).text()=='Tipo de encontro:')
for form,policy,expected in (('GeometricOnly','Independent',(False,False,False)),
                            ('Direct','Independent',(True,False,False)),
                            ('Direct','Priority',(True,True,False)),
                            ('Gusset','Independent',(False,False,True))):
    for widget,data in ((editor.connection_type,form),(editor.direct_policy,policy)):
        old=widget.blockSignals(True); widget.setCurrentIndex(widget.findData(data)); widget.blockSignals(old)
    editor._update_connection_visibility()
    check(form+policy+' conditional rows',all(widget.isHidden()!=visible and
        editor._connection_form.labelForField(widget).isHidden()!=visible
        for widget,visible in zip((editor.direct_policy,editor.priority_member,editor.gusset_plate),expected)))
check('no help tooltip overlay on canvas',not editor.canvas.toolTip())
editor.close(); editor.deleteLater(); panel._preview_timer.stop(); panel._closed=True
panel.controller.remove_preview(); panel.form.deleteLater()
value['connection_intents'][node]['priority_run_key']=vertical.run_key
owner=truss.apply_truss(doc,value,owner)
check('manual vertical primary fits two diagonals',sum(any(a['source']=='ConnectionIntent' for a in actions(m))
    for m in owner.GeneratedMembers)==2)

for double in (False,True):
    value=config('WarrenVerticals')
    c=build_candidate(value)
    node=next(n.key for n in c.graph.nodes if len(webs(c,n.key))==3)
    if double:
        value['role_specs']['DIAGONAL']=configure_assembly(value['role_specs']['DIAGONAL'],'DoubleAngle',100.)
    value['connection_intents']={node:dict(form='Gusset',gusset=dict(plate_thickness=8.,normal_clearance=2.,axial_clearance=20.))}
    host=truss.apply_truss(doc,value)
    # Recompute and reapply expose FreeCAD normal serialization/normalization.
    doc.recompute()
    host=truss.apply_truss(doc,truss.config_from_object(host),host)
    check('autofit provenance survives recompute '+str(double),not any(has_manual_adjustment(m) for m in host.GeneratedMembers))
    legacy=next(m for m in host.GeneratedMembers if getattr(m,'PhysicalFitAutoState',''))
    legacy.PhysicalFitAutoState=''
    check('lost old auto snapshot recognized without writes',not has_manual_adjustment(legacy) and legacy.PhysicalFitAutoState=='')
    for preset in ('Pratt','K','X','Custom'):
        changed=truss.config_from_object(host)
        changed['topology_preset']=preset
        if preset=='Custom': changed['base_preset']='X'
        changed.setdefault('connection_intents',{})['DELETED_NODE']=dict(form='Gusset')
        before=host.AppliedState
        candidate=build_candidate(changed)
        check('stale intent cleaned in detached candidate', 'DELETED_NODE' not in candidate.config['connection_intents'] and host.AppliedState==before)
        host=truss.apply_truss(doc,changed,host)
        check('preset '+preset+' double '+str(double),valid(host))
    host=truss.apply_truss(doc,restore_preset(truss.config_from_object(host)),host)
    check('restore X after Custom '+str(double),truss.config_from_object(host)['topology_preset']=='X' and valid(host))
    changed=truss.config_from_object(host); changed['topology_preset']='Pratt'
    after={i.key for i in build_candidate(changed).items}
    manual=next(m for m in host.GeneratedMembers if m.GenerationKey not in after)
    manual.StartAdjustmentMode='Fixed'; manual.StartAdjustmentGeometryMode='PlaneCut'
    manual.StartFixedReferenceOffset=60.; manual.StartFixedPlaneNormal=App.Vector(.2,0.,1.)
    doc.recompute()
    before=host.AppliedState
    try:
        truss.apply_truss(doc,changed,host)
    except ValueError as exc:
        check('real manual PlaneCut blocks removal '+str(double),'ajustes manuais' in str(exc))
    else: raise AssertionError('manual removal allowed')
    check('failed removal preserves document',host.AppliedState==before and doc.getObject(manual.Name) is not None)

output=Path(__file__).resolve().parents[1]/'test-results'/'connections-c5b-polish'
output.mkdir(parents=True,exist_ok=True)
doc.recompute(); doc.saveAs(str(output/'C5BPolish.FCStd'))
owner_name=owner.Name
filename=doc.FileName
App.closeDocument(doc.Name)
doc=App.openDocument(filename)
owner=doc.getObject(owner_name)
check('stable manual primary survives save reopen',
    next(iter(truss.config_from_object(owner)['connection_intents'].values()))['priority_run_key']==vertical.run_key)
check('reopened Priority fits both secondaries',valid(owner) and sum(
    any(a['source']=='ConnectionIntent' for a in actions(m)) for m in owner.GeneratedMembers)==2)
(output/'gate-result.json').write_text(json.dumps(dict(version=App.Version()[:3],checks=checks),ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(dict(passed=len(checks),checks=checks),ensure_ascii=False))
